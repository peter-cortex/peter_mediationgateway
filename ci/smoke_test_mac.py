import os, sys, platform

print(f"[sys] {platform.platform()}  py={platform.python_version()}")

# Torch: MPS su Apple Silicon, CPU altrove (no CUDA su mac)
try:
    import torch
    mps_ok = torch.backends.mps.is_available() and torch.backends.mps.is_built()
    dev = "mps" if mps_ok else "cpu"
    print(f"[torch] {torch.__version__}  mps_ok={mps_ok}")
    x = torch.randn(2,2).to(dev); y = (x @ x).sum().item()
    print(f"[torch] device={dev} OK sample={y:.4f}")
except Exception as e:
    print("[torch] FAIL:", e); sys.exit(1)

# WhisperX: CPU (CT2 GPU non c'è su mac). Se non disponibile, WARNING.
try:
    import whisperx
    model = whisperx.load_model("tiny", device="cpu", compute_type="int8")
    print("[whisperx] tiny CPU load OK")
except Exception as e:
    print("[whisperx] WARN:", e)

# Coqui TTS + phonemizer/espeak: best effort
def set_espeak_env():
    for p in ("/opt/homebrew/lib/libespeak-ng.dylib", "/usr/local/lib/libespeak-ng.dylib"):
        if os.path.exists(p):
            os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = p
            return p

try:
    path = set_espeak_env()
    if path: print(f"[phonemizer] espeak-ng: {path}")
    from TTS.api import TTS
    TTS("tts_models/en/ljspeech/tacotron2-DDC")
    print("[tts] import/load OK")
except Exception as e:
    print("[tts] WARN:", e)

# Pacchetti spesso critici su mac
ok = True
for name in ("thinc", "sudachipy", "praat_parselmouth"):
    try:
        __import__(name.replace("-", "_"))
        print(f"[{name}] import OK")
    except Exception as e:
        ok = False
        print(f"[{name}] FAIL:", e)

sys.exit(0 if ok else 1)
