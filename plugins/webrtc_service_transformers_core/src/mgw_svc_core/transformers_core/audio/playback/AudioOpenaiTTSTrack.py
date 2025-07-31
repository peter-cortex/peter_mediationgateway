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

kokoro_client = OpenAI(
    base_url="http://host.docker.internal:8880/v1",
    api_key="not-needed"  # richiesto dal client ma ignorato
)

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

        #MODIFICATO DA ME: l'emitter in questa maniera non riesce a gestire coroutine asincrone
        #self.ee.on("tts_request", self.handle_tts_request)
        self.ee.on("tts_request", lambda data: asyncio.create_task(self.handle_tts_request(data)))

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

    async def handle_tts_request(self, data: dict):
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
        logger.info(f"Entering handle_tts_request function")
        
        try:
            """
            Get the session ID, text, voice, and action from the data
            """
            logger.info(f"handle_tts_request data : {data}")
            sid = data.get("sid")
            text = data.get("text")
            voice = data.get("voice", default_openai_voice)  # Default to DEFAULT_OPENAI_VOICE or 'alloy' if not provided
            action = data.get("action")
            action = "start"
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

            
            #logger.info(f" WebRTC Transceivers: {self.pc.getTransceivers()}")
            #for transceiver in self.pc.getTransceivers():
            #    logger.info(f" Transceiver: {transceiver.kind}, Direction: {transceiver.direction}, Mid: {transceiver.mid}, Sender:   {transceiver.sender}, Receiver: {transceiver.receiver.track}")

            #for transceiver in self.pc.getTransceivers():
            #    if transceiver.kind == "audio":
            #        transceiver.direction = "sendrecv"  # Force WebRTC to use the track
            #        logger.info(f"✅ Transceiver updated to sendrecv mode: {transceiver}")
            
            #logger.info(f" WebRTC Connection State: {self.pc.connectionState}")
            #logger.info(f" ICE Connection State: {self.pc.iceConnectionState}")
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

    async def originale_fetch_tts_audio(self, text: str, voice: str):
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

                
                logger.info(f"Raw PCM Chunk (first 20 bytes): {chunk[:20]}")

                pcm_array = np.frombuffer(chunk, dtype=np.int16)
                logger.info(f"PCM Array Sample Values (first 10 samples): {pcm_array[:10]}")  #  Log decoded values

                pcm_array = pcm_array.reshape(1, pcm_array.size)
                frame = av.AudioFrame.from_ndarray(pcm_array, layout="mono")
                frame.sample_rate = 24000

                resampled_frame = self.resampler.resample(frame)
                frame_data = resampled_frame[0].to_ndarray()
                logger.info(f"Resampled Frame Data (first 10 samples): {frame_data[:10]}")  #  Log after resampling
                audio_buffer = np.concatenate((audio_buffer, frame_data), axis=1)

                while audio_buffer.size >= target_samples:
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
                        logger.info(f"Frame added to queue. Queue size: {len(self.frame_list)}")

                    break
                await asyncio.sleep(0)  # Yield control back to the event loop
            logger.info("Streaming Done!")

    async def kokoro_fetch_tts_audio(self, text: str, voice: str):
        logger.warning("----------------------------------- recv() - SONO ENTRATO NEL FETCH TTS AUDIO DI KOKORO")
        """
        Fetch the Kokoro text-to-speech audio (OpenAI-compatible interface).

        Args:
        text: The text to be synthesized
        voice: The voice (speaker_id or combo) to be used

        Yields:
        None
        """
        with kokoro_client.audio.speech.with_streaming_response.create(
                model="kokoro",
                voice="af_alloy",  # es. "en_okabe" o "af_sky+af_bella"
                input=text,
                response_format="pcm",  # headerless PCM, come usavi già
        ) as response:
            audio_buffer = np.empty((1, 0), dtype=np.int16)
            target_samples = 960 * 2

            logger.info("Kokoro Streaming Starting.")
            for chunk in response.iter_bytes(chunk_size=1024):
                #logger.debug(f"[KOKORO-TTS] Received audio chunk of {len(chunk)} bytes")
                if not self.task_queue and self.force_cancelling:
                    logger.info("Cancelled streaming.")
                    self.processing = False
                    self.force_cancelling = False
                    return

                #logger.info(f"Raw PCM Chunk (first 20 bytes): {chunk[:20]}")
                pcm_array = np.frombuffer(chunk, dtype=np.int16)
                #logger.info(f"PCM Array Sample Values (first 10 samples): {pcm_array[:10]}")

                pcm_array = pcm_array.reshape(1, pcm_array.size)
                frame = av.AudioFrame.from_ndarray(pcm_array, layout="mono")
                frame.sample_rate = 24000  # Kokoro restituisce 24kHz

                resampled_frame = self.resampler.resample(frame)
                frame_data = resampled_frame[0].to_ndarray()
                #logger.info(f"[KOKORO-TTS] Generated frame with {frame.samples} samples at {frame.sample_rate} Hz")
                #logger.info(f"Resampled Frame Data (first 10 samples): {frame_data[:10]}")
                audio_buffer = np.concatenate((audio_buffer, frame_data), axis=1)

                while audio_buffer.size >= target_samples:
                    output_frame_data = audio_buffer[:, :target_samples]
                    audio_buffer = audio_buffer[:, target_samples:]

                    output_frame = av.AudioFrame.from_ndarray(
                        output_frame_data,
                        layout=resampled_frame[0].layout.name,
                    )
                    output_frame.sample_rate = resampled_frame[0].sample_rate
                    with self.lock:
                        self.frame_list.append(output_frame)
                        logger.info(f"Frame added to queue. Queue size: {len(self.frame_list)}")

                    break
                await asyncio.sleep(0)
            logger.info("Kokoro Streaming Done!")

    async def fetch_tts_audio(self, text: str, voice: str):
        logger.warning("----------------------------------- recv() - SONO ENTRATO NEL FETCH TTS AUDIO")
        """
        Mocked version of fetch_tts_audio to simulate TTS audio generation
        """
        import wave

        # Carica un file WAV esistente (es. 24kHz mono PCM16)
        path = "/app/assets/temp.wav"  # Sostituisci con un path reale
        wf = wave.open(path, 'rb')

        audio_buffer = np.empty((1, 0), dtype=np.int16)
        target_samples = 960 * 2

        while True:
            logger.warning("----------------- recv() - STO INVIANDO FRAME DI TEMP.WAV")
            chunk = wf.readframes(1024)
            if not chunk:
                break

            pcm_array = np.frombuffer(chunk, dtype=np.int16)
            pcm_array = pcm_array.reshape(1, pcm_array.size)

            frame = av.AudioFrame.from_ndarray(pcm_array, layout="mono")
            frame.sample_rate = wf.getframerate()

            resampled_frame = self.resampler.resample(frame)
            frame_data = resampled_frame[0].to_ndarray()
            audio_buffer = np.concatenate((audio_buffer, frame_data), axis=1)

            while audio_buffer.size >= target_samples:
                output_frame_data = audio_buffer[:, :target_samples]
                audio_buffer = audio_buffer[:, target_samples:]

                output_frame = av.AudioFrame.from_ndarray(
                    output_frame_data,
                    layout=resampled_frame[0].layout.name,
                )
                output_frame.sample_rate = resampled_frame[0].sample_rate

                with self.lock:
                    self.frame_list.append(output_frame)
                break

            await asyncio.sleep(0)

        logger.info("Mocked TTS streaming done.")

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

    async def recv_originale(self) -> av.AudioFrame:
        """
        Handle the audio frame from the stream.

        Returns:
        av.AudioFrame: The audio frame from the stream
        """

        logger.info("recv() called - Checking for audio frames...")

        if self.readyState != "live":
            logger.error("recv() failed - Track is not live!")
            raise MediaStreamError

        frame = self.get_next_frame()

        if hasattr(self, "_timestamp"):
            self._timestamp += self.frame_size
            wait = self._start + (self._timestamp / self.sample_rate) - time.time()
            logger.info(f"recv() - Sleeping for {wait:.4f} seconds to sync audio")
            await asyncio.sleep(wait)
        else:
            self._start = time.time()
            self._timestamp = 0

        if frame is not None:
            frame.pts = self._timestamp
            frame.time_base = fractions.Fraction(1, frame.sample_rate)
            logger.info(f"recv() - Sending audio frame with PTS={frame.pts}")
            return frame

        logger.warning("recv() - No available audio frames, sending blank frame TI HO CAMBIATO")
        # Return a blank frame if no active stream or queue is empty
        self.blank_frame.pts = self._timestamp
        return self.blank_frame

    async def recv(self) -> av.AudioFrame:
        """
        Handle the audio frame from the stream.

        Returns:
        av.AudioFrame: The audio frame from the stream
        """
        logger.info("recv() called - Checking for audio frames...")

        if self.readyState != "live":
            logger.error("recv() failed - Track is not live!")
            raise MediaStreamError

        timeout = 45  # secondi massimi di attesa (opzionale)
        waited = 0
        while not self.frame_list:
            if waited >= timeout:
                logger.error("recv() timeout: nessun frame audio ricevuto entro il limite.")
                return self.blank_frame  # oppure: raise eccezione
            logger.debug("recv() waiting for first audio frame...")
            await asyncio.sleep(0.1)
            waited += 0.1

        frame = self.get_next_frame()

        if hasattr(self, "_timestamp"):
            self._timestamp += self.frame_size
            wait = self._start + (self._timestamp / self.sample_rate) - time.time()
            logger.info(f"recv() - Sleeping for {wait:.4f} seconds to sync audio")
            await asyncio.sleep(max(0, wait))
        else:
            self._start = time.time()
            self._timestamp = 0

        if frame is not None:
            frame.pts = self._timestamp
            frame.time_base = fractions.Fraction(1, frame.sample_rate)
            logger.info(f"recv() - Sending audio frame with PTS={frame.pts}")
            return frame

        logger.warning("recv() - No available audio frames, sending blank frame TI HO CAMBIATO")
        self.blank_frame.pts = self._timestamp
        return self.blank_frame
