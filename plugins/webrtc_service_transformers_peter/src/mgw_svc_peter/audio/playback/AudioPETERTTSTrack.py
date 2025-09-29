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
import threading

#PETER import
from TTS.api import TTS
#import soundfile as sf
import wave
#import math
from io import BytesIO

from torch.serialization import safe_globals
from TTS.tts.models.xtts import Xtts
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import XttsAudioConfig, XttsArgs
from TTS.config.shared_configs import BaseDatasetConfig
import torch
#import torchaudio

from mgw_svc_peter.load_models import get_tts_model


AUDIO_PTIME = 0.020  # 20 ms
SAMPLE_RATE = 48000
FRAME_SIZE = int(AUDIO_PTIME * SAMPLE_RATE)


#logger = logging.getLogger(__name__)
log_dir = "/logs"
os.makedirs(log_dir, exist_ok=True)
log_path = os.path.join(log_dir, "pipeline.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_path, mode="a", encoding="utf-8"),
        logging.StreamHandler()  
    ]
)

logger = logging.getLogger("AudioPipeline") 

_tts_model_cache = {}

"""
def load_tts_model(device="cuda"):
      key = f"xtts_v2_{device}"
      if key in _tts_model_cache:
          logger.info(f"[TTS Cache] Using cached TTS model for {key}")
          return _tts_model_cache[key]

      logger.info(f"[TTS Cache] Loading new TTS model for {key}")
      os.environ["COQUI_TOS_AGREED"] = "1"
      with safe_globals([XttsConfig, XttsAudioConfig, BaseDatasetConfig, XttsArgs]):
          model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2").to(device)
      _tts_model_cache[key] = model
      return model
"""

"""
Custom Exception Class for MediaStream Errors
Raise MediaStreamError for exceptions in the audio stream
"""


class MediaStreamError(Exception):
    pass


class TTSTask:
    def __init__(self, sid, text, language, chunk_id=None):
        self.sid = sid
        self.text = text
        #self.voice = voice
        self.language = language
        self.chunk_id = chunk_id


class AudioPETERTTSTrack(MediaStreamTrack):
    """
    AudioPETERTTSTrack Class for handling CoquiAI TTS Text-to-Speech output file
    """

    kind = "audio"
    sample_rate = 48000
    channels = 2
    frame_size = int(AUDIO_PTIME * sample_rate)  # 20ms audio packetization
    _timestamp: int



    def __init__(self, event_emitter):
        """
        Constructor for AudioPETERTTSTrack class

        Args:
        event_emitter (object): Event emitter for handling TTS requests
        """
        super().__init__()
        self.ee = event_emitter

        self.session_id = None
        self.processing = False
        self.force_cancelling = False
        #self.current_voice = None
        self.blank_frame = self._create_blank_frame(self.sample_rate, self.frame_size)

        self.resampler = av.AudioResampler(
            format="s16", layout="stereo", rate=self.sample_rate
        )
        os.environ["COQUI_TOS_AGREED"] = "1"
        device = "cuda" if torch.cuda.is_available() else "cpu"
        #with safe_globals([XttsConfig, XttsAudioConfig, BaseDatasetConfig, XttsArgs]):
            #self.tts_model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2").to(device) 
            #config = XttsConfig()
            #config.load_json("/root/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2/config.json")
            #self.tts_model = Xtts.init_from_config(config)
            #self.tts_model.load_checkpoint(config, checkpoint_dir="/root/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2", use_deepspeed=True)
            #self.tts_model.cuda()
        #self.tts_model = load_tts_model(device)
        self.tts_model = get_tts_model(device)
        if self.tts_model is None:
            raise RuntimeError("TTS model not preloaded! Call load_tts_model() at init.")

        
        
        self.lock = threading.Lock()
        self.task_queue = deque()  # Queue for TTS tasks
        self.frame_list = []

        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_event_loop, name='tts-stack', args=(self.loop,))
        self.thread.start()

        # modified by Simone: this emitter couldn't mange asynchronous coroutine
        # self.ee.on("tts_request", self.handle_tts_request)
        self.ee.on("tts_request", lambda data: asyncio.create_task(self.handle_tts_request(data)))
        tts_tmp_dir = "/tmp"
        for filename in os.listdir(tts_tmp_dir):
            if filename.startswith("coqui_tts_") and filename.endswith(".wav"):
                try:
                    os.remove(os.path.join(tts_tmp_dir, filename))
                except Exception as e:
                    logger.warning(f"[PETER-TTS] Impossibile rimuovere {filename}: {e}")
        logger.info("[PETER-TTS] Pulizia iniziale completata dei file coqui_tts_*.wav in /tmp")



    
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
            text_info = data.get("text")
            if isinstance(text_info, dict):
              logger.warning(f"text field is a dict: {text_info}, extracting 'text' field inside")
              text = text_info.get("text")
              chunk_id = text_info.get("chunk_id")
            else:
              print("text is str")
              text = data.get("text")
              chunk_id = None
            #voice = data.get("voice","alloy")
            language = data.get("language", "it")
            action = data.get("action")
            action = "start"
            logger.info('========================================================Test')

            if action in {"start", "append"}:
                # await self.start_stream(sid, text, voice, action)
                self.add_task(sid, text, language, chunk_id)
            elif action == "replace":
                self.cancel_all_tasks()
                self.add_task(sid, text, language, chunk_id)
            elif action == "stop":
                self.cancel_all_tasks()
                # await self.stop_stream()

        except Exception as e:
            logger.error(f"Error handling TTS request: {e}")

    def add_task(self, sid: str, text: str, language: str, chunk_id):
        task = TTSTask(sid, text, language, chunk_id)
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
            await self.start_stream(task.sid, task.text, task.language, task.chunk_id)

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

    async def start_stream(self, sid: str, text: str, language: str, chunk_id):
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

        self.session_id = sid
        #self.current_voice = voice

        try:
            await self.fetch_tts_audio(text, language, chunk_id)
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


    async def fetch_tts_audio(self, text: str, language:str, chunk_id):
        start_time = time.time()
        hard_code_language = os.environ.get("TRG_LANG", "fr")
        logger.warning("[PETER-TTS] Entered in fetch_tts_audio with Coqui")
        logger.warning(f"The language is: {language}")

        

        if text.startswith("[URGENT]"):
            urgency_id = "URGENT"
            clean_text = text[len("[URGENT]"):].strip()
        elif text.startswith("[NOT URGENT]"):
            urgency_id = "NOT_URGENT"
            clean_text = text[len("[NOT URGENT]"):].strip()
        else:
            urgency_id = "NOT_URGENT"
            clean_text = text

        clean_text = clean_text.replace('.', ',')

        logger.info(f"[PETER-TTS] Riconosciuta urgenza: {urgency_id}, testo pulito: {clean_text}")

        try:
            output_path = f"/tmp/coqui_tts_{int(time.time() * 1000)}.wav"

            if urgency_id == "URGENT":
                multi_speaker = ["/app/speakers/my_urgent_audio_1.wav", "/app/speakers/my_urgent_audio_2.wav"]
            else:
                multi_speaker = ["/app/speakers/my_not_urgent_audio_1.wav", "/app/speakers/my_not_urgent_audio_2.wav"]

            
            buffer = BytesIO()
            self.tts_model.tts_to_file(text=clean_text, file_path=buffer, speaker_wav=multi_speaker, language=hard_code_language)
            
            
            with open(output_path, "wb") as f_out:
                f_out.write(buffer.getvalue())

            buffer.seek(0)
            logger.info(f"***************************************************[PETER-TTS] File salvato: {output_path}")
            tts_time = time.time() - start_time
            logger.info(f"[Time] chunk_id={chunk_id} | TTS={tts_time:.3f}")

            wf = wave.open(buffer, 'rb')
            total_frames = wf.getnframes()
            sample_rate = wf.getframerate()
            channels = wf.getnchannels()
            logger.info(f"[DEBUG] file '{output_path}' ha {total_frames} frame totali, "
                  f"{wf.getnchannels()} canali a {wf.getframerate()} Hz")
            #audio_buffer = np.empty((1, 0), dtype=np.int16)
            audio_chunks = []
            target_samples = 960 * 2

            chunk_count = 0
            while True:
                chunk = wf.readframes(1024) 
                chunk_count += 1
                if not chunk:
                    logger.info(f"[DEBUG] EOF raggiunto dopo {chunk_count} iterazioni, "
                          f"puntatore a frame {wf.tell()}/{total_frames}")
                    break 
                #logger.info(f"[DEBUG] Iter {chunk_count}: letti {len(chunk)} byte, "
                #      f"pointer frame = {wf.tell()}")
                pcm_array = np.frombuffer(chunk, dtype=np.int16)
                pcm_array = pcm_array.reshape(1, pcm_array.size)

                frame = av.AudioFrame.from_ndarray(pcm_array, layout="mono")
                frame.sample_rate = wf.getframerate()

                resampled_frame = self.resampler.resample(frame)
                frame_data = resampled_frame[0].to_ndarray()
                #audio_buffer = np.concatenate((audio_buffer, frame_data), axis=1)
                audio_chunks.append(frame_data)
                while sum(chunk.shape[1] for chunk in audio_chunks) >= target_samples:
                  merged = np.concatenate(audio_chunks, axis=1)
                  output_frame_data = merged[:, :target_samples]
                  remaining = merged[:, target_samples:]
                  audio_chunks = [remaining] if remaining.size > 0 else []

                  output_frame = av.AudioFrame.from_ndarray(
                    output_frame_data,
                    layout=resampled_frame[0].layout.name,
                  )
                  output_frame.sample_rate = resampled_frame[0].sample_rate

                  with self.lock:
                    self.frame_list.append(output_frame)

                    #This break was huge problem (chunk interruption in the middle)
                    #break

                await asyncio.sleep(0)

                
            logger.info("New TTS streaming done.")
        except Exception as e:
            logger.error(f"[PETER-TTS] Errore in fetch_tts_audio: {e}")

    def get_next_frame(self) -> Optional[av.AudioFrame]:
        with self.lock:
            frame = self.frame_list.pop(0) if len(self.frame_list) > 0 else None
        if frame is None:
            return None
        return frame

    async def recv(self) -> av.AudioFrame:
        if self.readyState != "live":
            logger.error("recv() failed - Track is not live!")
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
            #logger.info(f"recv() - Sending audio frame with PTS={frame.pts}")
            return frame

        # Return a blank frame if no active stream or queue is empty
        self.blank_frame.pts = self._timestamp
        return self.blank_frame

    
