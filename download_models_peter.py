import os
from transformers import (
    AutoTokenizer,
    AutoModelForSeq2SeqLM,
    AutoModelForSequenceClassification,
    pipeline,
)

# Cache path override 
os.environ["HF_HOME"] = os.path.expanduser("~/.cache/huggingface")

# terms acceptance (for coqui ai tts)
__builtins__.input = lambda _: "y"

#WhisperX
#from faster_whisper import WhisperModel
#WhisperModel("Systran/faster-whisper-turbo", device="cpu")
import whisperx
_ = whisperx.load_model('turbo', device='cpu', compute_type='float32')

# Translation model fr<->it not avaible
langs = [("en", "fr"), ("fr", "en"),
         ("en", "it"), ("it", "en"),
         ("en", "de"), ("de", "en"),
         ("fr", "de"), ("de", "fr"),
         ("de", "it"), ("it", "de")]

for src, tgt in langs:
    model_name = f"Helsinki-NLP/opus-mt-{src}-{tgt}"
    print(f"Downloading translation model: {model_name}")
    AutoTokenizer.from_pretrained(model_name)
    AutoModelForSeq2SeqLM.from_pretrained(model_name)

# Sentiment analysis EN
pipeline("sentiment-analysis", model="michellejieli/emotion_text_classifier", device=-1)

# Sentiment analysis FR
AutoTokenizer.from_pretrained("astrosbd/french_emotion_camembert")
AutoModelForSequenceClassification.from_pretrained("astrosbd/french_emotion_camembert")

# Sentiment analysis DE
AutoTokenizer.from_pretrained("visegradmedia-emotion/Emotion_RoBERTa_german6_v7", use_fast=False)
AutoModelForSequenceClassification.from_pretrained("visegradmedia-emotion/Emotion_RoBERTa_german6_v7")

# Sentiment analysis IT
AutoTokenizer.from_pretrained("aiknowyou/it-emotion-analyzer")
AutoModelForSequenceClassification.from_pretrained("aiknowyou/it-emotion-analyzer")

#Coqui ai tts 
from TTS.utils.manage import ModelManager
manager = ModelManager()
model = manager.download_model('tts_models/multilingual/multi-dataset/xtts_v2')

print("All models downloaded")
