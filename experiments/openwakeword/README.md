# OpenWakeWord PoC (Navis)

Goal: Replace the current "Vosk-as-wakeword" approach with **openWakeWord** for robust wake-word detection.

## Status
- Python venv: `.venv-oww`
- Packages installed: `openwakeword`, `onnxruntime`, `tflite-runtime`, `soundfile`, etc.
- **Important:** `tflite-runtime` currently requires **NumPy < 2** on this Pi (arm64). We pinned `numpy==1.26.4`.

## Model resources
openWakeWord ships without all model files on this platform; we download them via:

```bash
source .venv-oww/bin/activate
python -c "from openwakeword.utils import download_models; download_models([])"
```

## Run (PoC)
This PoC reads raw PCM16 mono from `arecord` and prints wake scores.

```bash
source .venv-oww/bin/activate
python experiments/openwakeword/oww_listen.py --device plughw:3,0 --model hey_jarvis_v0.1
```

## Next
- Training mode is available via `experiments/openwakeword/navis_record_samples.py`
  and is gated by `healthcheck.py --only soundcheck` before recording.
- Evaluate whether training can run on the Pi within ~30 minutes
- Integrate runtime trigger into `navis_listen_daemon.py` (wake → beep → record utterance → Whisper STT → TTS)
