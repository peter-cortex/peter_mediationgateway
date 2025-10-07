import json
import logging
from pathlib import Path
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


#peter import
import whisperx
from transformers import MarianMTModel, MarianTokenizer, pipeline, AutoModelForSequenceClassification, AutoTokenizer
import torch
import librosa
import parselmouth
from parselmouth.praat import call
import re
import time
import asyncio
import uuid

from mgw_svc_peter.load_models import get_whisper_model, get_translation_model, get_emotion_model

#logger = logging.getLogger(__name__)
log_dir = "/logs"
os.makedirs(log_dir, exist_ok=True)
log_path = os.path.join(log_dir, "pipeline.log")

logger = logging.getLogger("AudioPipeline")
logger.setLevel(logging.INFO)

#logger for save the log for time compute table
if not logger.handlers:
    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)


temp_dir = tempfile.mkdtemp()
save_path = os.path.join(temp_dir, "temp.wav")

_model_cache = {}

class AudioPETERtoDataTransformChannel(AudioDataTransformChannel):
    
    MAX_CHUNK_DURATION = float(os.environ.get("MAX_CHUNK_DURATION", "5.0"))  # max seconds for chunk
    OVERLAP_MS = int(float(os.environ.get("OVERLAP_MS", "300")))  # overlap between chunk in ms

    def __init__(
            self, track, channel, transform, event_emitter,
            params: Dict[str, str] = None
    ):
        super().__init__(track, channel, transform, event_emitter, params)
        logger.info(f"[PETER] Initialized with params: {params}")
        if os.path.exists(log_path):
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("")
            logger.info("[PETER] Log cleaned for new session")
        src_lang = os.environ.get("SRC_LANG", "en")
        trg_lang = os.environ.get("TRG_LANG", "fr")
        self.src_lang = src_lang
        self.trg_lang = trg_lang
        self.MAX_SILENCE_DURATION = 2.0

        self.tail = pydub.AudioSegment.silent(duration=0)
        
        logger.info("Whisper temporaly folder: " + temp_dir)

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.urgency_from = os.environ.get("URGENCY_FROM", "both")

        models = load_models(src_lang=self.src_lang, trg_lang=self.trg_lang, device=self.device, urgency_from=self.urgency_from)
        self.whisper_model = models["whisper_model"]
        #self.whisper_model = get_whisper_model(src_lang)
        #if self.whisper_model is None:
        #    raise RuntimeError("WhisperX model not preloaded!")
        self.translation_model = models["translation_model"]
        self.translation_tokenizer = models["translation_tokenizer"]
        self.emotion_classifier = models["emotion_classifier"]
        self.emotion_tokenizer = models["emotion_tokenizer"]
        self.emotion_model = models["emotion_model"]

        self.transcription_input = asyncio.Queue()
        self.audio_urgency_input = asyncio.Queue()
        self.transcription_queue = asyncio.Queue()
        self.translated_queue = asyncio.Queue()
        self.emotion_input_queue = asyncio.Queue()
        self.emotion_queue = asyncio.Queue()
        self.audio_urgency_queue = asyncio.Queue()

        asyncio.create_task(self._transcribe_worker())
        asyncio.create_task(self._translate_worker())
        if self.urgency_from in {"audio", "both"}:
            asyncio.create_task(self._urgency_worker())
        if self.urgency_from in {"text", "both"}:
            asyncio.create_task(self._classify_emotion_worker())



        
    @staticmethod
    def create_transformer(
            track, channel, transform, event_emitter,
            params: Dict[str, str] = None
    ):
        logger.info(f"[PETER] create_transformer called with params: {params}")
        return AudioPETERtoDataTransformChannel(
            track, channel, transform, event_emitter, params=params)

    async def recv(self):
        try:
            if self.track.readyState != "live":
                #if self.sound_chunk.duration_seconds > 0:
                    #logger.info("[PETER] Track non live, flush finale del chunk residuo.")
                    #await self._flush_chunk()
                raise MediaStreamError
                #return None
            audio_frame = await self.track.recv()


            sound = pydub.AudioSegment(
                data=audio_frame.to_ndarray().tobytes(),
                sample_width=audio_frame.format.bytes,
                frame_rate=audio_frame.sample_rate,
                channels=len(audio_frame.layout.channels),
            ).set_channels(1)

            if not self.vad.is_speech(sound.raw_data, sound.frame_rate):
                self.silent_count += sound.duration_seconds
                if self.silent_count > self.MAX_SILENCE_DURATION:
                    # if it's not too quiet
                    if (self.sound_chunk.duration_seconds > 0
                            and self.sound_chunk.max_dBFS > -20.0): #first was 30
                        await self._flush_chunk()
                    self.sound_chunk = pydub.AudioSegment.empty()

                    if self.tail is None:
                        self.tail = pydub.AudioSegment.silent(duration=0)

                return audio_frame


             #self.sound_chunk += sound
            if len(self.sound_chunk) == 0 and len(self.tail) > 0:
                self.sound_chunk += self.tail
            self.sound_chunk += sound

            #forced flush at MAX_CHUNK_DURATION (5s)
            if self.sound_chunk.duration_seconds >= self.MAX_CHUNK_DURATION:
                if self.sound_chunk.max_dBFS > -20.0: #first was 30
                    await self._flush_chunk()
                else:
                    logger.debug("Silent chunk at 5s, skip _flush_chunk()")
                    self.sound_chunk = pydub.AudioSegment.empty()
                    self.tail = pydub.AudioSegment.silent(duration=0)
                self.silent_count = 0
                return audio_frame

            return audio_frame

        except MediaStreamError:
            raise
            #logger.info("[PETER] MediaStream terminated")
            #return None
        except Exception as e:
            logger.error(e)
            return audio_frame

    async def _flush_chunk(self):
        try:
            chunk_id = str(uuid.uuid4())

            if self.sound_chunk and len(self.sound_chunk) > 0:
                overlap = min(self.OVERLAP_MS, int(self.sound_chunk.duration_seconds * 1000))
                self.tail = self.sound_chunk[-overlap:] if overlap > 0 else pydub.AudioSegment.silent(duration=0)
            else:
                self.tail = pydub.AudioSegment.silent(duration=0)

            await asyncio.to_thread(self.sound_chunk.export, save_path, "wav")
            logger.info(f"Start pipeline for chunk {chunk_id}")

            # Send to worker
            await asyncio.wait_for(self.transcription_input.put({"chunk_id": chunk_id, "path": save_path}), timeout=1.0)
            await asyncio.wait_for(self.audio_urgency_input.put({"chunk_id": chunk_id, "path": save_path}), timeout=1.0)

            # Results of translate worker
            result = await asyncio.wait_for(self.translated_queue.get(), timeout=30.0)
            if not result:
                logger.info("[FlushChunk] Skipped (no result).")
                return

            if isinstance(result, dict):
                tagged_str = result.get("tagged") or result.get("text") or result.get("translation") or ""
                meta = {
                    "chunk_id":     result.get("chunk_id"),
                    "transcription": result.get("transcription"),
                    "translation":   result.get("translation"),
                    "urgency":       result.get("urgency"),
                    "emotion":       result.get("emotion"),
                }
            else:
                tagged_str = str(result)
                meta = None

            msg = {
                "sid": getattr(self.channel, "sid", None),
                "type": "transcript",          
                "data": tagged_str,            
                "language": self.language_mode,
            }
            if meta:
                msg["meta"] = meta            

            send_fn = getattr(self.channel, "send", None)

            if asyncio.iscoroutinefunction(send_fn):
                # Checkbox OFF:  "websocket" channel of target -> target emits tts_request
                await send_fn(json.dumps(msg, ensure_ascii=False))
                logger.info(f"[PETER] Sent to target websocket channel: {msg}")
            else:
                # Checkbox ON: true RTCDataChannel -> send to UI
                if self.channel and getattr(self.channel, "readyState", "") == "open":
                    try:
                        while getattr(self.channel, "bufferedAmount", 0) > 1_000_000:
                            await asyncio.sleep(0.01)
                        self.channel.send(json.dumps(msg, ensure_ascii=False))
                        logger.info(f"[PETER] DC->UI: {msg}")
                    except Exception as e:
                        logger.error(f"[PETER-DC] send failed: {e}")
                else:
                    logger.warning("[PETER-DC] channel not open, dropping message")

                # In parallel warn the TTS
                try:
                    if hasattr(self, "ee") and self.ee:
                        tts_msg = {
                            "sid": getattr(self.channel, "sid", None),
                            "voice": (self.params or {}).get("voice", "af"),
                            "text": tagged_str, 
                            "language": getattr(self, "trg_lang", (self.params or {}).get("language", "it")),
                            "action": "start",
                            # log
                            "transcription": meta.get("transcription") if meta else None,
                            "urgency": meta.get("urgency") if meta else None,
                            "emotion": meta.get("emotion") if meta else None,
                            "chunk_id": meta.get("chunk_id") if meta else chunk_id,
                        }
                        self.ee.emit("tts_request", tts_msg)
                        logger.info(f"[PETER] Emitted tts_request: {tts_msg}")
                except Exception as e:
                    logger.warning(f"[PETER-EE] emit tts_request failed: {e}")

        except Exception as e:
            logger.error(f"[PETER-TTS] Error in _flush_chunk: {e}")
        finally:
            self.sound_chunk = pydub.AudioSegment.empty()

    async def _transcribe_worker(self):
        while True:
            try:
                item = await self.transcription_input.get()
                chunk_id, audio_path = item["chunk_id"], item["path"]
                start_time = time.time()
                audio_chunk_np = await asyncio.to_thread(whisperx.load_audio, audio_path)
                result = await asyncio.to_thread(
                    lambda: self.whisper_model.transcribe(
                        audio_chunk_np,
                        batch_size=16,
                        language=self.src_lang
                    )
                )
                if not result["segments"]:
                    logger.warning("[WhisperX] No segments found.")
                    await self.transcription_queue.put({"chunk_id": chunk_id, "text": None})
                    #await self.audio_urgency_queue.put({"chunk_id": chunk_id, "text": None})
                    await self.emotion_queue.put({"chunk_id": chunk_id, "emotion": None})
                    continue

                transcription = " ".join(segment['text'] for segment in result["segments"])
                logger.info(f"[WhisperX] Transcription complete: {transcription}")
                stt_time = time.time() - start_time
                logger.info(f"[Time] chunk_id={chunk_id} | STT={stt_time:.3f}")
                await self.transcription_queue.put({"chunk_id": chunk_id, "text": transcription})
                await self.emotion_input_queue.put({"chunk_id": chunk_id, "text": transcription})
                torch.cuda.empty_cache()
            except Exception as e:
                logger.error(f"[WhisperX] Transcription error: {e}")

    async def _translate_worker(self):
      partials = {}
      while True:
        try:
            # Collect next available item from any source
                transcription_task = asyncio.create_task(self.transcription_queue.get())
                emotion_task = asyncio.create_task(self.emotion_queue.get())
                urgency_task = asyncio.create_task(self.audio_urgency_queue.get())

                done, pending = await asyncio.wait(
                  [transcription_task, emotion_task, urgency_task],
                  return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                  item = task.result()
                  chunk_id = item.get("chunk_id")
                  if chunk_id not in partials:
                      partials[chunk_id] = {}
                  partials[chunk_id].update(item)

                for task in pending:
                  task.cancel()

                current = partials[chunk_id]

                if ("text" in current) and (current["text"] is None):
                    logger.warning(f"[TranslateWorker] Skipping chunk_id={chunk_id} because transcription returned None")
                    await self.translated_queue.put(None)
                    del partials[chunk_id]
                    continue

                transcription_ready = ("text" in current)           # chiave presente
                emotion_ready       = ("emotion" in current) or (self.urgency_from == "audio")
                urgency_ready       = ("urgency" in current) or (self.urgency_from == "text")

                if not (transcription_ready and emotion_ready and urgency_ready):
                    continue

                    
                if not (transcription_ready and emotion_ready and urgency_ready):
                    logger.debug(
                        f"[TranslateWorker] Skipping chunk_id={chunk_id} "
                        f"(transcription: {transcription_ready}, "
                        f"emotion: {emotion_ready}, urgency: {urgency_ready})"
                    )
                    continue

                logger.debug(f"[TranslateWorker] Processing chunk_id: {chunk_id}")
                start_translation = time.time()
                # Translation
                transcription_for_out = current["text"].strip()
                src_text = re.sub(r'[,.!]', '', current["text"].strip())
                inputs = self.translation_tokenizer(src_text, return_tensors="pt", padding=True).to(self.device)
                translated = self.translation_model.generate(**inputs)
                translated_text = self.translation_tokenizer.decode(translated[0], skip_special_tokens=True)

                if translated_text.strip() == "==References====External links==":
                    translated_text = src_text


                urgency_audio = current.get("urgency") or "NOT URGENT"
                emotion = current.get("emotion") or "neutral"
                if urgency_audio is None:
                    urgency_audio = "NOT URGENT"
                if emotion is None:
                    emotion = "neutral"
                # Final decision about urgency
                final_urgency = "NOT URGENT"
                if self.urgency_from == "text":
                    if emotion in {"anger", "fear"}:
                        final_urgency = "URGENT"
                elif self.urgency_from == "audio":
                    final_urgency = urgency_audio
                elif self.urgency_from == "both":
                    if urgency_audio == "URGENT" or emotion in {"anger", "fear"}:
                        final_urgency = "URGENT"

                urgency_tag = "[URGENT]" if final_urgency == "URGENT" else "[NOT URGENT]"
                tagged_text = f"{urgency_tag} {translated_text}"

                await self.translated_queue.put({"chunk_id": chunk_id, "text": tagged_text, "transcription": transcription_for_out })
                translation_time = time.time() - start_translation
                logger.info(f"[Time] chunk_id={chunk_id} | Translation_time={translation_time:.3f}")
                logger.info(f"[Translation] chunk_id={chunk_id} | Translation={translated_text}")
                del partials[chunk_id]
        except Exception as e:
          logger.error(f"[TranslationLoop] Error: {e}")

    async def _classify_emotion_worker(self):
        while True:
            try:
                item = await self.emotion_input_queue.get()
                chunk_id, text = item["chunk_id"], item["text"]
                if text is None:
                    await self.emotion_queue.put({"chunk_id": chunk_id, "emotion": None})
                    continue
                start_time = time.perf_counter()
                if self.src_lang == "en":
                    result = self.emotion_classifier(text)
                    label = result[0]["label"] if result else "neutral"
                elif self.src_lang in {"fr", "de", "it"}:
                    with torch.no_grad():
                        inputs = self.emotion_tokenizer(text, return_tensors="pt", padding=True, truncation=True,
                                                        max_length=512).to(self.device)
                        outputs = self.emotion_model(**inputs)
                        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
                        label_idx = probs.argmax().item()

                        if self.src_lang == "fr":
                            label = self.emotion_model.config.id2label.get(label_idx, str(label_idx))
                        elif self.src_lang == "de":
                            german_labels = {
                                0: "anger", 1: "fear", 2: "disgust", 3: "sadness", 4: "joy", 5: "neutral"
                            }
                            label = german_labels.get(label_idx, f"LABEL_{label_idx}")
                        elif self.src_lang == "it":
                            italian_labels = ["sadness", "joy", "love", "anger", "fear", "surprise"]
                            label = italian_labels[label_idx] if label_idx < len(italian_labels) else f"LABEL_{label_idx}"
                else:
                    label = "unknown"
            except Exception as e:
                logger.warning(f"[Emotion] Classification failed: {e}")
                await self.emotion_queue.put({"chunk_id": chunk_id, "emotion": "error"})

            elapsed = time.perf_counter() - start_time
            logger.info(f"[Time] chunk_id={chunk_id} | Emotion_time={elapsed:.3f}")
            logger.info(f"[Emotion] chunk_id={chunk_id} | Emotion={label}")
            await self.emotion_queue.put({"chunk_id": chunk_id, "emotion": label})

    async def _urgency_worker(self):
        while True:
            try:
                item = await self.audio_urgency_input.get()
                chunk_id, audio_path = item["chunk_id"], item["path"]
                urgency = await self._classify_urgency(audio_path, chunk_id)
                logger.info(f"[Urgency-Audio] {urgency}")
                await self.audio_urgency_queue.put({"chunk_id": chunk_id, "urgency": urgency})
            except Exception as e:
                logger.error(f"[UrgencyWorker] Error: {e}")
                await self.audio_urgency_queue.put({"chunk_id": chunk_id, "urgency": "NOT URGENT"})

    async def _classify_urgency(self, audio_path: str, chunk_id: str) -> str:
        start = time.time()
        features = await asyncio.to_thread(extract_urgency_features, audio_path)
        f0_mean_threshold = 210
        f0_std_threshold = 40
        pitch_range_threshold = 50
        avg_pause_duration_threshold = 0.7
        avg_phrase_length_threshold = 4.0 #changed from 3.0 to 4.0
        rms_amplitude_threshold = 0.04 #changed from 1 (too strict) to 0.07 (maybe 0.06) and now to 0.04 cause he's blocking too many urgent audio
        is_urgent = (
                features["f0_mean"] > f0_mean_threshold and
                features["f0_std"] > f0_std_threshold and
                features["pitch_range"] > pitch_range_threshold and
                features["avg_pause_duration"] < avg_pause_duration_threshold and
                features["avg_phrase_length"] < avg_phrase_length_threshold and
                features["rms_amplitude"] > rms_amplitude_threshold
        )
        #(Optional) check of features and thresholds
        logger.info("\n[FEATURE CHECK] Valori estratti e confronto con soglie:")
        for key, value in features.items():
            logger.info(f" - {key}: {value:.3f}")

        logger.info("\n[SOGGETTO A SOGLIE]:")
        logger.info(f"f0_mean > {f0_mean_threshold}? {'✔' if features['f0_mean'] > f0_mean_threshold else '✘'}")
        logger.info(f"f0_std > {f0_std_threshold}? {'✔' if features['f0_std'] > f0_std_threshold else '✘'}")
        logger.info(f"pitch_range > {pitch_range_threshold}? {'✔' if features['pitch_range'] > pitch_range_threshold else '✘'}")
        logger.info(f"avg_pause_duration < {avg_pause_duration_threshold}? {'✔' if features['avg_pause_duration'] < avg_pause_duration_threshold else '✘'}")
        logger.info(f"avg_phrase_length < {avg_phrase_length_threshold}? {'✔' if features['avg_phrase_length'] < avg_phrase_length_threshold else '✘'}")
        logger.info(f"rms_amplitude > {rms_amplitude_threshold}? {'✔' if features['rms_amplitude'] > rms_amplitude_threshold else '✘'}")

        urgency_time = time.time() - start
        logger.info(f"[Time] chunk_id={chunk_id} | Urgency Audio={urgency_time:.3f}")
        return "URGENT" if is_urgent else "NOT URGENT"


def load_models(src_lang="en", trg_lang="it", device="cuda", compute_type="float32", urgency_from="both"):

    key = f"{src_lang}_{trg_lang}_{device}"
    
    if key in _model_cache:
        logger.info(f"[ModelCache] Using cached models for {key}")
        return _model_cache[key]

    logger.info(f"[ModelCache] Loading models for {key}...")


    # Load WhisperX
    logger.info("Loading WhisperX model...")
    #whisper_model = whisperx.load_model(
    #    "turbo",
    #    device=device,
    #    compute_type=compute_type,
    #    asr_options={
    #        "max_new_tokens": 500,
    #        "clip_timestamps": True,
    #        "hallucination_silence_threshold": 0.5,
    #    },
    #)
    whisper_model = get_whisper_model(src_lang, device=device)

    # Warm-up
    #try:
    #    fake_audio = np.zeros(16000, dtype=np.float32)
    #    whisper_model.transcribe(fake_audio, batch_size=1, language=src_lang)
    #    logger.info("WhisperX warm-up complete.")
    #except Exception as e:
    #    logger.warning(f"WhisperX warm-up failed: {e}")

    # Load MarianMT translation model
    logger.info("Loading MarianMT model...")
    #translation_model_name = f"Helsinki-NLP/opus-mt-{src_lang}-{trg_lang}"
    #translation_tokenizer = MarianTokenizer.from_pretrained(translation_model_name)
    #translation_model = MarianMTModel.from_pretrained(translation_model_name).to(device)
    translation_tokenizer, translation_model = get_translation_model(src_lang, trg_lang, device=device)

    # Load emotion classifier
    if urgency_from in ["both", "text"]:
        emotion_data = get_emotion_model(src_lang, device=device)

        if src_lang == "en":
            emotion_classifier = emotion_data["classifier"]
            emotion_tokenizer = None
            emotion_model = None
        else:
            emotion_classifier = None
            emotion_tokenizer = emotion_data["tokenizer"]
            emotion_model = emotion_data["model"]
    else:
        emotion_classifier = None
        emotion_tokenizer = None
        emotion_model = None

    _model_cache[key] = {
        "whisper_model": whisper_model,
        "translation_model": translation_model,
        "translation_tokenizer": translation_tokenizer,
        "emotion_classifier": emotion_classifier,
        "emotion_tokenizer": emotion_tokenizer,
        "emotion_model": emotion_model,
    }
    return _model_cache[key]
    

def calculate_phrase_lengths(audio_file):
    y, sr = librosa.load(audio_file, sr=16000)
    non_silent_intervals = librosa.effects.split(y, top_db=30)
    phrase_lengths = [
        (end - start) / sr
        for start, end in non_silent_intervals
    ]
    return phrase_lengths

def extract_urgency_features(audio_file):
        y, sr = librosa.load(audio_file, sr=16000)
        duration = librosa.get_duration(y=y, sr=sr)
        non_silent_intervals = librosa.effects.split(y, top_db=30)
        speaking_time = sum([(end - start) / sr for start, end in non_silent_intervals])
        snd = parselmouth.Sound(audio_file)
        pitch = snd.to_pitch()
        f0_mean = call(pitch, "Get mean", 0, 0, "Hertz")
        f0_std = call(pitch, "Get standard deviation", 0, 0, "Hertz")
        f0_min = call(pitch, "Get minimum", 0, 0, "Hertz", "Parabolic")
        f0_max = call(pitch, "Get maximum", 0, 0, "Hertz", "Parabolic")
        pause_durations = [
            (non_silent_intervals[i][0] - non_silent_intervals[i - 1][1]) / sr
            for i in range(1, len(non_silent_intervals))
        ]
        avg_pause_duration = float(np.mean(pause_durations)) if pause_durations else 0.0
        num_pauses = int(len(pause_durations))
        phrase_lengths = calculate_phrase_lengths(audio_file)
        avg_phrase_length = float(np.mean(phrase_lengths)) if phrase_lengths else 0.0
        pitch_range = float(f0_max - f0_min)
        rms_amplitude = float(librosa.feature.rms(y=y).mean())
        return {
            "f0_mean": float(f0_mean),
            "f0_std": float(f0_std),
            "f0_min": float(f0_min),
            "f0_max": float(f0_max),
            "pitch_range": pitch_range,
            "avg_pause_duration": avg_pause_duration,
            "num_pauses": num_pauses,
            "avg_phrase_length": avg_phrase_length,
            "rms_amplitude": rms_amplitude,
            "speaking_time": float(speaking_time),
            "duration": float(duration),
        }
