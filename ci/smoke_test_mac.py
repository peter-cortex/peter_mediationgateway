import torch, sys, os
mps = torch.backends.mps.is_available() and torch.backends.mps.is_built()
print(f"[torch] {torch.__version__} mps={mps}")
dev = "mps" if mps else "cpu"
x = torch.randn(2,2).to(dev); y = (x @ x).sum().item()
print(f"[torch] device={dev} sample={y:.4f}")

try:
    import whisperx
    whisperx.load_model("tiny", device="cpu", compute_type="int8")
    print("[whisperx] OK (CPU)")
except Exception as e:
    print("[whisperx] WARN:", e)

for name in ["thinc","sudachipy","praat_parselmouth","TTS"]:
    try:
        __import__(name.replace("-", "_"))
        print(f"[{name}] import OK")
    except Exception as e:
        print(f"[{name}] FAIL:", e); sys.exit(1)
