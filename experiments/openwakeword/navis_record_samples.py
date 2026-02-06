#!/usr/bin/env python3
"""Record wakeword training samples on-device (Navis).

This is intentionally simple and robust:
- Uses `arecord` directly (no PortAudio).
- Forces 16kHz mono PCM16 WAV files.
- Stores samples in a folder structure suitable for later training.

Recommended usage (stop the live listener first):
  systemctl --user stop navis-listen.service

Examples:
  # Record 20 positive samples (say "Navis" right after the beep)
  python experiments/openwakeword/navis_record_samples.py pos --count 20 --device plughw:3,0

  # Record 10 negative noise samples (stay quiet / type / walk)
  python experiments/openwakeword/navis_record_samples.py neg --count 10 --seconds 3 --device plughw:3,0

Then restart listener:
  systemctl --user start navis-listen.service
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "dataset"))
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HEALTHCHECK = os.path.join(REPO_ROOT, "healthcheck.py")


def run(cmd, timeout=30, check=True):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, check=check)


def beep():
    # Prefer a deterministic local WAV beep via ALSA; avoid TTS startup/hangs.
    dev = os.environ.get("NAVIS_SPK_DEVICE", "plughw:2,0").strip() or "plughw:2,0"
    aplay = shutil.which("aplay")
    tone = "/usr/share/sounds/alsa/Front_Center.wav"
    try:
        if aplay and os.path.exists(tone):
            subprocess.run([aplay, "-D", dev, tone], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4, check=False)
            return
    except Exception:
        pass

    # If direct aplay is not available, continue without beep.


def run_soundcheck_gate(mic_device: str):
    if not os.path.exists(HEALTHCHECK):
        raise SystemExit(f"[record] soundcheck gate failed: missing {HEALTHCHECK}")

    env = os.environ.copy()
    env.setdefault("NAVIS_MIC_DEVICE", mic_device)
    cmd = [sys.executable, HEALTHCHECK, "--only", "soundcheck", "--timeout", "120"]
    p = run(cmd, timeout=180, check=False)
    if p.returncode != 0:
        raise SystemExit(f"[record] soundcheck gate failed (rc={p.returncode}):\n{p.stdout}")

    try:
        payload = json.loads(p.stdout)
        if not isinstance(payload, list) or not payload:
            raise ValueError("unexpected JSON shape")
        result = payload[0]
        if not bool(result.get("ok")):
            raise SystemExit(
                "[record] soundcheck gate failed: check reported not ok.\n"
                + json.dumps(result, ensure_ascii=False, indent=2)
            )
    except SystemExit:
        raise
    except Exception as e:
        raise SystemExit(f"[record] soundcheck gate failed: could not parse output ({e}). Raw output:\n{p.stdout}")


def record_wav(out_path: str, device: str, seconds: float, rate: int = 16000):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cmd = [
        "arecord",
        "-D",
        device,
        "-f",
        "S16_LE",
        "-r",
        str(rate),
        "-c",
        "1",
        "-d",
        str(int(round(seconds))),
        out_path,
    ]
    p = run(cmd, timeout=max(10, int(seconds) + 10), check=False)
    if p.returncode != 0:
        raise SystemExit(f"arecord failed (rc={p.returncode}):\n{p.stdout}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)

    for mode in ("pos", "neg"):
        sp = sub.add_parser(mode)
        sp.add_argument("--count", type=int, default=20)
        sp.add_argument("--device", default="plughw:3,0")
        sp.add_argument("--seconds", type=float, default=1.5 if mode == "pos" else 3.0)
        sp.add_argument("--pause", type=float, default=0.8 if mode == "pos" else 0.2, help="pause between samples")
        sp.add_argument("--outdir", default=os.path.join(BASE, mode))
        sp.add_argument("--no-soundcheck-gate", action="store_true", help="skip mandatory pre-recording soundcheck gate")

    args = ap.parse_args()

    if not args.no_soundcheck_gate:
        print("[record] running soundcheck gate...")
        run_soundcheck_gate(args.device)
        print("[record] soundcheck gate passed")
    else:
        print("[record] WARNING: soundcheck gate skipped by flag")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"[record] mode={args.mode} count={args.count} device={args.device} seconds={args.seconds} outdir={args.outdir}")

    for i in range(1, args.count + 1):
        out = os.path.join(args.outdir, f"{ts}-{args.mode}-{i:03d}.wav")
        if args.mode == "pos":
            print(f"[record] {i}/{args.count} SAY 'Navis' after beep → {out}")
            beep()
            # small reaction delay to start speaking
            time.sleep(0.15)
        else:
            print(f"[record] {i}/{args.count} NEG sample (stay quiet / type / walk) → {out}")
            # no beep for neg

        record_wav(out, device=args.device, seconds=args.seconds)
        time.sleep(args.pause)

    print("[record] done")


if __name__ == "__main__":
    main()
