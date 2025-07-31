import json
import logging
from pathlib import Path
import openai
import os
import pydub
import scipy.signal
import tempfile
import numpy as np
from aiortc.mediastreams import MediaStreamError
import aiohttp
from typing import Dict

from mgw_svc_core.transformers_core.audio.AudioDataTransformChannel import (
    AudioDataTransformChannel,
)

from openai import OpenAI

logger = logging.getLogger(__name__)

temp_dir = tempfile.mkdtemp()
save_path = os.path.join(temp_dir, "temp.wav")



# hf_model_path = "/app/covalite/models--Alevxis--wakewordcova/snapshots/"
# Check if the directory exists
#if os.path.isdir(hf_model_path):
#    logger.info(f"The directory '{hf_model_path}' exists.")
#else:


class AudioWhispertoDataTransformChannel(AudioDataTransformChannel):
    """
    A audio stream track that transforms frames into transcript text.
    """

    def __init__(
        self, track, channel, transform, event_emitter,
        params: Dict[str, str] = None
    ):
        # don't forget this!
        super().__init__(track, channel, transform, event_emitter, params)
        self.whisper_init()
        
        self.past_sentence = ""
        self.whisper_api_url = os.getenv("WHISPERX_API_URL", "http://host.docker.internal:8000/v1/audio/transcriptions")
        logger.info("******************** Whisper temporaly folder: " + temp_dir)

        @self.ee.on("active-talkers")
        async def on_activetalkers(message):
            pass

    @staticmethod
    def create_transformer(
        track, channel, transform, event_emitter,
        params: Dict[str, str] = None
    ):
        return AudioWhispertoDataTransformChannel(
            track, channel, transform, event_emitter, params=params)

    def check_stop_word(self, predicted_text: str, stop_word: str) -> bool:
        import re

        pattern = re.compile("[\W_]+", re.UNICODE)
        return pattern.sub("", predicted_text).lower() == stop_word

    def whisper_init(self):
        # Whisper init

        if os.getenv("OPENAI_API_KEY") is None:
            raise Exception("Missing openAI Api Key!")
        
        self.client = OpenAI()
        self.client.api_key = os.getenv("OPENAI_API_KEY")      
        

    async def _transcribe_original(self):
        """Reimplementation from parent """
        # TODO replace save path by a TemporaryFile
        self.sound_chunk.export(save_path, format="wav")
        with open(save_path, "rb") as audio_file:
            response = openai.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file,  
                prompt=self.past_sentence,  
                language="en"  
            )

            transcribe = response.text
            return transcribe

    async def _transcribe_forced(self):
        self.sound_chunk.export(save_path, format="wav")
        logger.info(f"******************************* SONO NELLA MIA TRANSCRIBE, IL FILE TEMPORANEO E': {save_path}")
        transcribe = "This is a fixed transcription from fake transcribe."
        return transcribe

    async def _transcribe(self):
        self.sound_chunk.export(save_path, format="wav")
        logger.info(f"************************************* NUOVA TRANSCRIBE CORRETTA, IL FILE TEMPORANEO E': {save_path}")

        async with aiohttp.ClientSession() as session:
            with open(save_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename="temp.wav", content_type='audio/wav')
                data.add_field('model', 'base')
                data.add_field('language', 'en')

                try:
                    async with session.post(self.whisper_api_url, data=data) as resp:
                        if resp.status == 200:
                            response_json = await resp.json()
                            transcript = response_json.get("text", "")
                            logger.info(f"========================================================================== QUSETA E' LA TRASCRIZIONE:{transcript}")
                            return transcript
                        else:
                            logger.error(f"WhisperX API returned status {resp.status}")
                except Exception as e:
                    logger.error(f"Failed to contact WhisperX API: {e}")

        return ""




