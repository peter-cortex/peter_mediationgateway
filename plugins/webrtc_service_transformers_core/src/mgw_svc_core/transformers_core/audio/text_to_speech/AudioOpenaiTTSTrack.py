import asyncio
from collections import deque
import fractions
import logging
import os
import time
from typing import Optional
import av
from aiortc import MediaStreamTrack
import numpy as np
from openai import OpenAI
import threading

"""
OpenAI TTS Stream Configuration
Audio packetization period in seconds
"""
AUDIO_PTIME = 0.020  # 20ms audio packetization

"""
OpenAI API Configuration Environment Variables
(APIKey, EndpointUrl, ModelName)
Retrieved from environment variables for OpenAI API configuration
"""
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_endpoint_url = os.getenv(
    "OPENAI_ENDPOINT_URL", "https://api.openai.com/v1/audio/speech"
)
openai_model = os.getenv("OPENAI_MODEL", "tts-1")
default_openai_voice = os.getenv("DEFAULT_OPENAI_VOICE", "alloy")

logger = logging.getLogger(__name__)

"""
Custom Exception Class for MediaStream Errors
Raise MediaStreamError for exceptions in the audio stream
"""


class MediaStreamError(Exception):
    pass


class TTSTask:
    def __init__(self, sid, text, voice):
        self.sid = sid
        self.text = text
        self.voice = voice


class AudioOpenaiTTSTrack(MediaStreamTrack):
    """
    AudioOpenaiTTSTrack Class for handling OpenAI Text-to-Speech Stream
    """

    kind = "audio"
    sample_rate = 48000
    channels = 2
    frame_size = int(AUDIO_PTIME * sample_rate)  # 20ms audio packetization
    _timestamp: int

    def __init__(self, event_emitter):
        """
        Constructor for AudioOpenaiTTSTrack class

        Args:
        event_emitter (object): Event emitter for handling TTS requests
        """
        super().__init__()
        self.ee = event_emitter
        self.session_id = None
        self.processing = False
        self.force_cancelling = False
        self.current_voice = None
        self.blank_frame = self._create_blank_frame(self.sample_rate, self.frame_size)

        self.resampler = av.AudioResampler(
            format="s16", layout="stereo", rate=self.sample_rate
        )

        self.openai = OpenAI(
            base_url=openai_endpoint_url.replace("/audio/speech", ""),
            api_key=openai_api_key,
        )

        self.lock = threading.Lock()
        self.task_queue = deque()  # Queue for TTS tasks
        self.frame_list = []
        
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_event_loop, name='tts-stack', args=(self.loop,))
        self.thread.start()
                 
        self.ee.on("tts_request", self.handle_tts_request)
        
        
    def _run_event_loop(self, loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()
        
    def _create_blank_frame(self, sample_rate: int, frame_size: int) -> av.AudioFrame:
        """
        Creates a blank audio frame with the appropriate properties.

        Args:
        sample_rate (int): Sample rate of the audio
        frame_size (int): Audio packet size

        Returns:
        av.AudioFrame: An empty audio frame
        """
        frame = av.AudioFrame(format="s16", layout="stereo", samples=frame_size)
        for p in frame.planes:
            p.update(bytes(p.buffer_size))
        frame.pts = 0
        frame.rate = self.sample_rate
        return frame

    def handle_tts_request(self, data: dict):
        """
        Handles the TTS request event.

        Args:
        data: The TTS request data
        data.sid ( initial conversation id )
        data.voice ( one of the voice associated )
        data.text Text to synthetize
        data.action ( start | append | replace | stop )

        Yields:
        None
        """
        try:
            """
            Get the session ID, text, voice, and action from the data
            """
            sid = data.get("sid")
            text = data.get("text")
            logger.info("Questo e' il testo:",text)
            voice = data.get("voice", default_openai_voice)  # Default to DEFAULT_OPENAI_VOICE or 'alloy' if not provided
            action = data.get("action")
            
            logger.info('========================================================Test')

            if action in {"start", "append"}:
                # await self.start_stream(sid, text, voice, action)
                self.add_task(sid, text, voice)
            elif action == "replace":
                self.cancel_all_tasks()
                self.add_task(sid, text, voice)
            elif action == "stop":
                self.cancel_all_tasks()
                # await self.stop_stream()
        except Exception as e:
            logger.error(f"Error handling TTS request: {e}")

    def add_task(self, sid: str, text: str, voice: str):
        task = TTSTask(sid, text, voice)
        with self.lock:
            self.task_queue.append(task)

        if not self.processing:
            asyncio.run_coroutine_threadsafe(self.process_tasks(), self.loop)

    async def process_tasks(self):        
        self.processing = True
        while self.task_queue:
            if self.force_cancelling:
                return

            task: TTSTask = self.task_queue.popleft()  # Get the next task
            await self.start_stream(task.sid, task.text, task.voice)

        with self.lock:
            self.processing = False

    def cancel_all_tasks(self):
        with self.lock:
            self.task_queue.clear()
            if self.processing:
                self.force_cancelling = True

        # Clear the existing frames
        with self.lock:
            self.frame_list.clear()

    async def start_stream(self, sid: str, text: str, voice: str):
        """
        Initialize the text-to-speech stream.

        Args:
        sid: The session ID
        text: The text to be synthesized
        voice: The voice to be used
        action: ( start | append | replace )

        Yields:
        None
        """
        # if action == "start" and len(self.frame_list) > 0:
        #     logger.info("Stream already active.")
        #     return

        # if action == "replace":
        #     logger.info("Remove current stream.")
        #     if self.processing:
        #         self.force_cancelling = True
        #     with self.lock:
        #         self.frame_list.clear()

        self.session_id = sid
        self.current_voice = voice

        try:
            await self.fetch_tts_audio(text, voice)
        except Exception as e:
            logger.error(f"Error fetching TTS audio: {e}")

    async def stop_stream(self):
        """
        Terminate the text-to-speech stream.

        Yields:
        None
        """
        if len(self.frame_list) == 0:
            logger.info("No active stream to stop.")
            return

        with self.lock:
            self.frame_list.clear()

    async def fetch_tts_audio(self, text: str, voice: str):
        """
        Fetch the OpenAI text-to-speech audio.

        Args:
        text: The text to be synthesized
        voice: The voice to be used

        Yields:
        None
        """
        with self.openai.audio.speech.with_streaming_response.create(
            model=openai_model,
            voice=voice,
            response_format="pcm",  # similar to WAV, but without a header chunk at the start.
            input=text,
        ) as response:
            audio_buffer = np.empty((1, 0), dtype=np.int16)
            target_samples = 960 * 2

            logger.info("Streaming Starting.")
            for chunk in response.iter_bytes(chunk_size=1024):
                if not self.task_queue and self.force_cancelling:
                    logger.info("Cancelled streaming.")
                    self.processing = False
                    self.force_cancelling = False
                    return

                pcm_array = np.frombuffer(chunk, dtype=np.int16)
                pcm_array = pcm_array.reshape(1, pcm_array.size)
                frame = av.AudioFrame.from_ndarray(pcm_array, layout="mono")
                frame.sample_rate = 24000

                resampled_frame = self.resampler.resample(frame)
                frame_data = resampled_frame[0].to_ndarray()
                audio_buffer = np.concatenate((audio_buffer, frame_data), axis=1)

                while audio_buffer.size >= target_samples:
                    # Extract the required number of samples
                    output_frame_data = audio_buffer[:, :target_samples]
                    audio_buffer = audio_buffer[:, target_samples:]

                    # Create a new AudioFrame with the extracted samples
                    output_frame = av.AudioFrame.from_ndarray(
                        output_frame_data,
                        layout=resampled_frame[0].layout.name,
                    )
                    output_frame.sample_rate = resampled_frame[0].sample_rate
                    with self.lock:
                        self.frame_list.append(output_frame)
                    break
                await asyncio.sleep(0)  # Yield control back to the event loop
            logger.info("Streaming Done!")



    async def my_fetch_tts_audio(self, text: str, voice: str):
        logger.info("SONO ENTRATO NELLA FUNZIONE DI FETCH AUDIO MIA")

        """

        Invece di chiamare OpenAI, questa funzione legge un file audio e lo suddivide in pacchetti.

        """

        audio_file_path = "temp.wav"  # Sostituisci con il tuo file audio

        try:

            with av.open(audio_file_path) as container:

                stream = next(s for s in container.streams if s.type == 'audio')

                resampler = av.AudioResampler(format="s16", layout="stereo", rate=self.sample_rate)

                audio_buffer = np.empty((1, 0), dtype=np.int16)

                target_samples = int(self.sample_rate * AUDIO_PTIME) * 2  # 20ms di audio

                for frame in container.decode(stream):

                    resampled_frames = resampler.resample(frame)

                    for resampled_frame in resampled_frames:

                        frame_data = resampled_frame.to_ndarray()

                        audio_buffer = np.concatenate((audio_buffer, frame_data), axis=1)

                        while audio_buffer.size >= target_samples:
                            # Estrai 20ms di audio

                            output_frame_data = audio_buffer[:, :target_samples]

                            audio_buffer = audio_buffer[:, target_samples:]

                            # Crea un nuovo frame audio

                            output_frame = av.AudioFrame.from_ndarray(output_frame_data, layout="stereo")

                            output_frame.sample_rate = self.sample_rate

                            with self.lock:
                                self.frame_list.append(output_frame)

                            await asyncio.sleep(0)  # Cede il controllo all'event loop

                logger.info("Streaming audio locale completato!")

        except Exception as e:
            logger.error(f"Errore durante il caricamento dell'audio: {e}")

    def get_next_frame(self) -> Optional[av.AudioFrame]:
        """
        Get the next audio frame from the queue.

        Returns:
        av.AudioFrame: The next audio frame if available, otherwise None
        """
        with self.lock:
            frame = self.frame_list.pop(0) if len(self.frame_list) > 0 else None

        if frame is None:
            # End of stream
            return None
        return frame

    async def recv(self) -> av.AudioFrame:
        """
        Handle the audio frame from the stream.

        Returns:
        av.AudioFrame: The audio frame from the stream
        """
        if self.readyState != "live":
            raise MediaStreamError

        frame = self.get_next_frame()

        if hasattr(self, "_timestamp"):
            self._timestamp += self.frame_size
            wait = self._start + (self._timestamp / self.sample_rate) - time.time()
            await asyncio.sleep(wait)
        else:
            self._start = time.time()
            self._timestamp = 0

        if frame is not None:
            frame.pts = self._timestamp
            frame.time_base = fractions.Fraction(1, frame.sample_rate)
            return frame

        # Return a blank frame if no active stream or queue is empty
        self.blank_frame.pts = self._timestamp
        return self.blank_frame
