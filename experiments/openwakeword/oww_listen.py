#!/usr/bin/env python3
"""OpenWakeWord live listen PoC.

Reads 16kHz PCM16 mono from arecord and runs openWakeWord scoring.

Note: This is a PoC; integration into the Navis listen daemon will follow.
"""

import argparse
import subprocess
import sys
import time

import numpy as np
from openwakeword.model import Model
from openwakeword.utils import download_models


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="plughw:3,0", help="ALSA capture device for arecord")
    ap.add_argument("--model", default="hey_jarvis_v0.1", help="openWakeWord built-in model name")
    ap.add_argument("--rate", type=int, default=16000)
    ap.add_argument("--chunk-ms", type=int, default=80, help="Audio chunk size in ms")
    ap.add_argument("--threshold", type=float, default=0.5)
    args = ap.parse_args()

    # ensure models are present
    download_models([])

    m = Model(wakeword_models=[args.model])

    chunk_bytes = int(args.rate * (args.chunk_ms / 1000.0)) * 2
    if chunk_bytes <= 0:
        raise SystemExit("invalid chunk size")

    cmd = [
        "arecord",
        "-D",
        args.device,
        "-f",
        "S16_LE",
        "-r",
        str(args.rate),
        "-c",
        "1",
        "-t",
        "raw",
        "-",
    ]

    print("[oww] starting:", " ".join(cmd), flush=True)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    assert p.stdout is not None

    last_print = 0.0
    try:
        while True:
            data = p.stdout.read(chunk_bytes)
            if not data:
                time.sleep(0.01)
                continue

            x = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            scores = m.predict(x)
            score = float(scores.get(args.model, 0.0))

            now = time.time()
            if now - last_print > 0.2:
                last_print = now
                sys.stdout.write(f"\r[oww] {args.model} score={score:.3f}    ")
                sys.stdout.flush()

            if score >= args.threshold:
                print(f"\n[oww] WAKE! score={score:.3f}")
                # simple debounce
                time.sleep(1.0)
    finally:
        try:
            p.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    main()
