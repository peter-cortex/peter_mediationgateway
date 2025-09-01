import os, sys, platform, torch

print(f"[sys] {platform.platform()}  py={platform.python_version()}")
dev = "cpu"
print(f"[torch] v={torch.__version__}  device={dev}")
x = torch.randn(2, 2, device=dev)
y = (x @ x).sum().item()
print(f"[torch] sample={y:.4f}")

ok = True
for name in ("thinc", "sudachipy", "parselmouth", "TTS"):
    try:
        __import__(name.replace("-", "_"))
        print(f"[{name}] import OK")
    except Exception as e:
        ok = False
        print(f"[{name}] FAIL: {e}")

# WhisperX solo best-effort su CPU
try:
    import whisperx
    whisperx.load_model("tiny", device="cpu", compute_type="int8")
    print("[whisperx] tiny CPU load OK")
except Exception as e:
    print("[whisperx] WARN:", e)

sys.exit(0 if ok else 1)
