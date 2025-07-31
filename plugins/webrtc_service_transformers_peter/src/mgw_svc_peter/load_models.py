from TTS.api import TTS
import os
from torch.serialization import safe_globals
from TTS.tts.models.xtts import Xtts
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import XttsAudioConfig, XttsArgs
from TTS.config.shared_configs import BaseDatasetConfig

import whisperx

from transformers import MarianMTModel, MarianTokenizer, AutoModelForSequenceClassification, pipeline, AutoTokenizer

import numpy as np

_model_cache = {}

def load_whisper_model(language="en", device="cuda"):
    #src_lang = os.environ.get("SRC_LANG", "en")
    #trg_lang = os.environ.get("TRG_LANG", "fr")
    #from whisperx import load_model
    key = f"whisper_model_{language}_{device}"
    if key not in _model_cache:
        #model, metadata = load_model("faster-whisper-large-v3-turbo", device=device)
        #_model_cache[key] = (model, metadata)
        compute_type = "float32"
        whisper_model = whisperx.load_model(
        "turbo",
        device=device,
        compute_type=compute_type,
        asr_options={
            "max_new_tokens": 500,
            "clip_timestamps": True,
            "hallucination_silence_threshold": 0.5,
         },
        )
        _model_cache[key] = whisper_model
    return _model_cache[key]

def load_translation_model(src_lang="en", trg_lang="it", device="cuda"):
    key = f"translation_model_{src_lang}_{trg_lang}_{device}"
    if key not in _model_cache:
        model_name = f"Helsinki-NLP/opus-mt-{src_lang}-{trg_lang}"
        tokenizer = MarianTokenizer.from_pretrained(model_name)
        model = MarianMTModel.from_pretrained(model_name).to(device)
        _model_cache[key] = (tokenizer, model)
    return _model_cache[key]

def load_tts_model(device="cuda"):
    key = f"xtts_v2_{device}"
    if key in _model_cache:
        return _model_cache[key]

    os.environ["COQUI_TOS_AGREED"] = "1"
    with safe_globals([XttsConfig, XttsAudioConfig, BaseDatasetConfig, XttsArgs]):
        model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    _model_cache[key] = model
    return model

def load_emotion_model(language="en", device="cuda"):
    key = f"emotion_model_{language}_{device}"
    if key in _model_cache:
        return _model_cache[key]

    
    if language == "en":
        emotion_classifier = pipeline(
            "sentiment-analysis",
            model="michellejieli/emotion_text_classifier",
            device=0 if device == "cuda" else -1
        )
        _model_cache[key] = {
            "classifier": emotion_classifier,
            "tokenizer": None,
            "model": None,
        }
    else:
        if language == "it":
            model_name = "aiknowyou/it-emotion-analyzer"
        elif language == "fr":
            model_name = "astrosbd/french_emotion_camembert"
        elif language == "de":
            model_name = "visegradmedia-emotion/Emotion_RoBERTa_german6_v7"
        else:
            raise ValueError(f"No emotion model defined for language '{language}'")

        tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=False)
        model = AutoModelForSequenceClassification.from_pretrained(model_name).to(device)
        _model_cache[key] = {
            "classifier": None,
            "tokenizer": tokenizer,
            "model": model,
        }

    return _model_cache[key]


def get_tts_model(device="cuda"):
    return _model_cache.get(f"xtts_v2_{device}")  

def get_whisper_model(language="en", device="cuda"):
    return _model_cache.get(f"whisper_model_{language}_{device}")

def get_translation_model(src_lang="en", trg_lang="it", device="cuda"):
    key = f"translation_model_{src_lang}_{trg_lang}_{device}"
    return _model_cache.get(key)

def get_emotion_model(language="en", device="cuda"):
    key = f"emotion_model_{language}_{device}"
    return _model_cache.get(key)
