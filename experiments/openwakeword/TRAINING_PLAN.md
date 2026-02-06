# Training plan (Navis wake word)

Goal: Train a robust on-device wake word model for **"Navis"** using openWakeWord.

## 0) Preconditions
- Stop the current Vosk-based live listener so it doesn't keep the mic busy:
  - `systemctl --user stop navis-listen.service`

- Make sure mic works:
  - `arecord -D plughw:3,0 -f S16_LE -r 16000 -c 1 -d 2 /tmp/mic.wav`

- Speaker test (Robot-HAT, ALSA card 2):
  - `aplay -D plughw:2,0 /usr/share/sounds/alsa/Front_Center.wav`

## 1) Collect samples (on the Pi)
### Positive samples
Record ~20–50 samples of you saying **"Navis"** in different intonations and distances.

```bash
python experiments/openwakeword/navis_record_samples.py pos --count 30 --device plughw:3,0
```

Note: recording is gated by a pre-run sound self-check (`healthcheck.py --only soundcheck`).
Use `--no-soundcheck-gate` only for debugging.

### Negative samples
Record noise / typing / fan / room ambience.

```bash
python experiments/openwakeword/navis_record_samples.py neg --count 20 --seconds 3 --device plughw:3,0
```

Data will be stored in:
- `experiments/openwakeword/dataset/pos/*.wav`
- `experiments/openwakeword/dataset/neg/*.wav`

## 2) Next (implementation TODO)
- Evaluate openWakeWord training/finetuning pipeline on arm64.
- If training is heavy, do training on a PC and deploy runtime models to the Pi.

## 3) After recording
Restart listener:
- `systemctl --user start navis-listen.service`
