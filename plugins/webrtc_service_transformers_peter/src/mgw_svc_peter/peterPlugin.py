from mgw_svc_core.helpers.lazy_import import LazyImport
import logging
import os
from mgw_svc_peter.load_models import (
    load_tts_model, load_whisper_model, load_translation_model, load_emotion_model,
    get_whisper_model, get_translation_model, get_tts_model, get_emotion_model
)
import numpy as np
import soundfile as sf
from io import BytesIO
import torch

logger = logging.getLogger("peterPlugin")

AudioTransformModule = LazyImport('mgw_svc_core.transformers_core.audio.AudioTransform')
AudioTransform = AudioTransformModule.module.AudioTransform


from mgw_svc_core.transformers_core.WebrtcServicePluginInterface import (
    WebRTCServicePluginInterface,
)


from mgw_svc_peter.audio.AudioPETERToDataTransformChannel import AudioPETERtoDataTransformChannel
from mgw_svc_peter.targets.PETERSTSTTarget import PETERSTSTTarget


class PETERPlugin(WebRTCServicePluginInterface):
    def Register(self, data):
        #logger.info("PETER Plugin registered")
        device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info(f"[PLUGIN DEBUG] PETERPlugin received data: {data}")
        logger.info("[PETERPlugin] Preloading WhisperX...")
        src_lan = os.environ.get("SRC_LANG", "en")
        trg_lan = os.environ.get("TRG_LANG", "it")
        urgency_from = os.environ.get("URGENCY_FROM", "both")
        load_whisper_model(language=src_lan, device=device)
        whisper_model = get_whisper_model(src_lan, device)
        whisper_model.transcribe("/app/speakers/audio_005_sil.wav")

        logger.info("[PETERPlugin] Preloading Marian MT model...")
        load_translation_model(src_lang = src_lan, trg_lang = trg_lan, device=device)
        tokenizer, translation_model = get_translation_model(src_lang=src_lan, trg_lang=trg_lan, device=device)
        logger.info("[Warm-up] MT dummy translation...")
        dummy_text = "This is a more long and complex phrase to warm up the translation model"
        inputs = tokenizer(dummy_text, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        _ = translation_model.generate(**inputs)

        logger.info("[PETERPlugin] Preloading XTTSv2...")
        load_tts_model(device)
        tts = get_tts_model(device)
        buffer = BytesIO()
        tts.tts_to_file(
          text="This is a more long and complex phrase to warm up the text to speech model in order to speed it up",
          speaker_wav=["/app/speakers/my_urgent_audio_1.wav", "/app/speakers/my_urgent_audio_2.wav"],
          file_path=buffer,
          language=trg_lan
        )
        if urgency_from in ["both", "text"]:
            logger.info("[PETERPlugin] Preloading Emotion model...")
            load_emotion_model(language=src_lan, device=device)
            emo = get_emotion_model(language=src_lan, device=device)
            if emo["classifier"]:
                _ = emo["classifier"]("test message")
            else:
                tokenizer = emo["tokenizer"]
                model = emo["model"]
                inputs = tokenizer("test message", return_tensors="pt").to(device)
                _ = model(**inputs)
        logger.info("[PETERPlugin] Warm-up completed.")
        AudioTransform.register_transformer(
            "PETER",
            {
                "title": "stst with PETER",
                "description": "",
                "channel": ("mgw_svc_peter", AudioPETERtoDataTransformChannel),
                "target": ("mgw_svc_peter", PETERSTSTTarget),
                "options": data
            },
        )
