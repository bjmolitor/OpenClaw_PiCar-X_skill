#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Programmatic battery watcher for PiCar-X (Robot-HAT).

- Reads battery voltage via robot_hat.utils.get_battery_voltage()
- Estimates battery percent for a 2S pack
- Sends ONE WhatsApp alert (via openclaw CLI) when crossing thresholds
- Speaks alert locally via navis_media.py (no model)

Thresholds (defaults): 20% and 10%.
State is stored in a JSON file to avoid spamming.

Note: Percent is an estimate; tune voltage mapping via env vars.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime


TARGET_WA = os.environ.get("NAVIS_BATTERY_WA_TARGET", "+491727296893").strip()
OPENCLAW_BIN = os.environ.get("NAVIS_OPENCLAW_BIN", "/home/admin/.nvm/versions/node/v22.17.0/bin/openclaw")
MEDIA = os.environ.get("NAVIS_MEDIA_BIN", "/usr/bin/python3 /home/admin/.openclaw/workspace/navis_media.py")

STATE_PATH = os.environ.get(
    "NAVIS_BATTERY_STATE",
    "/home/admin/.openclaw/workspace/logs/battery_watch.state.json",
)

# 2S Li-Ion/LiPo heuristics
V_FULL = float(os.environ.get("PICARX_BATTERY_V_FULL", "8.40"))
V_EMPTY = float(os.environ.get("PICARX_BATTERY_V_EMPTY", "6.60"))

THRESH_20 = float(os.environ.get("PICARX_BATTERY_WARN_20", "20"))
THRESH_10 = float(os.environ.get("PICARX_BATTERY_WARN_10", "10"))

VOICE_ENABLED = os.environ.get("NAVIS_BATTERY_VOICE", "1").strip() in ("1", "true", "yes", "on")
WA_ENABLED = os.environ.get("NAVIS_BATTERY_WA", "1").strip() in ("1", "true", "yes", "on")


def now_iso() -> str:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Europe/Berlin")).isoformat()
    except Exception:
        return datetime.now().isoformat()


def load_state() -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_pct": None, "sent": {"20": False, "10": False}, "updated": None}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_PATH)


def read_batt_v() -> float | None:
    try:
        from robot_hat.utils import get_battery_voltage  # type: ignore

        v = float(get_battery_voltage())
        if v <= 0:
            return None
        return v
    except Exception:
        return None


def pct_from_v(v: float) -> float:
    # linear estimate; clamp
    if V_FULL <= V_EMPTY:
        return 0.0
    pct = (v - V_EMPTY) / (V_FULL - V_EMPTY) * 100.0
    return max(0.0, min(100.0, pct))


def run(cmd: list[str]) -> int:
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode


def speak(text: str) -> None:
    if not VOICE_ENABLED:
        return
    # MEDIA is a string; execute via shell for convenience
    subprocess.run(MEDIA.split() + ["speak", "--text", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def send_whatsapp(text: str) -> None:
    if not WA_ENABLED:
        return
    # Use OpenClaw CLI so routing stays inside OpenClaw (no direct provider calls).
    run([OPENCLAW_BIN, "message", "send", "--channel", "whatsapp", "--target", TARGET_WA, "--message", text])


def main() -> int:
    v = read_batt_v()
    if v is None:
        return 0
    pct = pct_from_v(v)

    state = load_state()
    sent = state.get("sent") or {"20": False, "10": False}

    # Determine threshold crossings (only when going down)
    last_pct = state.get("last_pct")

    def should_fire(th: float, key: str) -> bool:
        if sent.get(key):
            return False
        if last_pct is None:
            # first sample: fire if already below threshold
            return pct <= th
        return last_pct > th and pct <= th

    msg = None
    if should_fire(THRESH_10, "10"):
        msg = f"⚠️ PiCar-X Akku kritisch (~{pct:.0f}% / {v:.2f}V). Bitte bald laden."
        sent["10"] = True
    elif should_fire(THRESH_20, "20"):
        msg = f"Hinweis: PiCar-X Akku niedrig (~{pct:.0f}% / {v:.2f}V). Bitte ans Laden denken."
        sent["20"] = True

    if msg:
        send_whatsapp(msg)
        speak(msg)

    state["last_pct"] = pct
    state["last_v"] = v
    state["sent"] = sent
    state["updated"] = now_iso()
    save_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
