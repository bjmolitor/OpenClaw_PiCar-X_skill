#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""PiCar-X / Robot-HAT health checks.

MVP v0.1 goals:
- Deterministic JSON output for host + robot body health.
- Optional voltage logging to detect supply sag / undervoltage during load.

This script is SAFE by default (no motion).

New in v0.1:
- `perceive` command: environment perception snapshot (camera + ultrasonic) without driving.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, List


def _now_iso() -> str:
    # Europe/Berlin is fine for logs; avoid tz deps if missing.
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Europe/Berlin")).isoformat()
    except Exception:
        return datetime.now().isoformat()


def _run(cmd, timeout=3) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    return (p.stdout or "").strip()


def _vcgencmd(arg: str) -> Optional[str]:
    exe = shutil.which("vcgencmd") if 'shutil' in globals() else None
    if exe is None:
        try:
            import shutil as _sh

            exe = _sh.which("vcgencmd")
        except Exception:
            exe = None
    if not exe:
        return None
    return _run([exe, arg], timeout=2)


@dataclass
class ThrottleFlags:
    raw: str
    value: int

    @property
    def undervoltage_now(self) -> bool:
        return bool(self.value & (1 << 0))

    @property
    def throttled_now(self) -> bool:
        return bool(self.value & (1 << 1))

    @property
    def freq_capped_now(self) -> bool:
        return bool(self.value & (1 << 2))

    @property
    def throttling_now(self) -> bool:
        return bool(self.value & (1 << 3))

    @property
    def undervoltage_seen(self) -> bool:
        return bool(self.value & (1 << 16))

    @property
    def throttled_seen(self) -> bool:
        return bool(self.value & (1 << 17))

    @property
    def freq_capped_seen(self) -> bool:
        return bool(self.value & (1 << 18))

    @property
    def throttling_seen(self) -> bool:
        return bool(self.value & (1 << 19))


def parse_get_throttled(s: Optional[str]) -> Optional[ThrottleFlags]:
    if not s:
        return None
    # expected: throttled=0xe0000
    if "=" in s:
        _, rhs = s.split("=", 1)
    else:
        rhs = s
    rhs = rhs.strip()
    try:
        val = int(rhs, 16)
        return ThrottleFlags(raw=rhs, value=val)
    except Exception:
        return None


def read_battery_voltage() -> Optional[float]:
    """Best-effort battery voltage from Robot-HAT.

    On SunFounder Robot-HAT, get_battery_voltage() returns volts.
    """
    try:
        from robot_hat.utils import get_battery_voltage  # type: ignore

        v = float(get_battery_voltage())
        if v <= 0:
            return None
        return v
    except Exception:
        return None


def read_pi_temp_c() -> Optional[float]:
    s = _vcgencmd("measure_temp")
    if not s:
        return None
    # temp=61.5'C
    try:
        rhs = s.split("=", 1)[1].strip()
        rhs = rhs.replace("'C", "")
        return float(rhs)
    except Exception:
        return None


def health_json() -> Dict[str, Any]:
    ts = _now_iso()
    throttled_s = _vcgencmd("get_throttled")
    thr = parse_get_throttled(throttled_s)
    temp_c = read_pi_temp_c()
    batt_v = read_battery_voltage()

    res: Dict[str, Any] = {
        "ok": True,
        "ts": ts,
        "host": {
            "temp_c": temp_c,
            "throttled": (thr.raw if thr else None),
            "undervoltage_now": (thr.undervoltage_now if thr else None),
            "undervoltage_seen": (thr.undervoltage_seen if thr else None),
            "throttled_now": (thr.throttled_now if thr else None),
        },
        "power": {
            "battery_v": batt_v,
            # heuristic thresholds for 2S Li-Ion/LiPo pack
            "battery_low": (batt_v is not None and batt_v < float(os.environ.get("PICARX_BATTERY_LOW_V", "7.0"))),
            "battery_critical": (batt_v is not None and batt_v < float(os.environ.get("PICARX_BATTERY_CRIT_V", "6.6"))),
        },
        "notes": [],
    }

    notes = res["notes"]
    if thr and (thr.undervoltage_now or thr.undervoltage_seen):
        notes.append("undervoltage detected (now or historically) - check PSU/battery, especially under load")
    if batt_v is None:
        notes.append("battery voltage unavailable")

    return res


def _repo_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _run_json(cmd: list[str], timeout: float = 10.0, env: Optional[dict] = None) -> Tuple[bool, Dict[str, Any], str]:
    """Run a command expected to output JSON on the last line."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, env=env)
        out = (p.stdout or "").strip()
        last = out.splitlines()[-1] if out else ""
        obj = json.loads(last) if last.startswith("{") else {}
        ok = bool(obj.get("ok")) if isinstance(obj, dict) and "ok" in obj else (p.returncode == 0)
        return ok, (obj if isinstance(obj, dict) else {}), out[-4000:]
    except Exception as e:
        return False, {"ok": False, "error": f"{type(e).__name__}: {e}"}, ""


def _openai_api_key() -> Optional[str]:
    # prefer env, fallback to OpenClaw config if present
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if key:
        return key
    try:
        # OpenClaw stores keys under ~/.openclaw/openclaw.json
        import json as _json

        cfg_path = os.path.expanduser("/home/admin/.openclaw/openclaw.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = _json.load(f)
        return (((cfg.get("skills") or {}).get("entries") or {}).get("openai-whisper-api") or {}).get("apiKey")
    except Exception:
        return None


def _describe_with_openai(shots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Describe environment and hazards from labeled images.

    Returns a structured dict, best-effort.
    """
    key = _openai_api_key()
    if not key:
        return {"ok": False, "error": "OPENAI_API_KEY not set"}

    # Lazy import to avoid hard dependency if unused
    import base64
    import requests

    model = os.environ.get("PICARX_VISION_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    def as_data_url(path: str) -> str:
        b = open(path, "rb").read()
        enc = base64.b64encode(b).decode("ascii")
        return f"data:image/jpeg;base64,{enc}"

    content = [
        {
            "type": "text",
            "text": (
                "You are a robot health/perception module. Analyze the images (left/center/right/up/down). "
                "Return concise JSON with keys: summary, where_am_i_guess, hazards (array), risk_level (low|medium|high), "
                "and left_right_notes (object with left/center/right/up/down strings). "
                "Do NOT identify people or guess identities; describe only what is visible and safety-relevant."
            ),
        }
    ]

    for s in shots:
        path = (((s.get("snapshot") or {}).get("path")) or "")
        if not path or not os.path.exists(path):
            continue
        label = s.get("label") or "unknown"
        content.append({"type": "text", "text": f"Image label: {label}"})
        content.append({"type": "image_url", "image_url": {"url": as_data_url(path)}})

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a careful, safety-focused robot perception assistant."},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }

    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=45,
        )
        if r.status_code != 200:
            return {"ok": False, "error": f"openai_http_{r.status_code}", "detail": r.text[:500]}
        data = r.json()
        txt = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        obj = json.loads(txt) if txt.startswith("{") else {"summary": txt}
        return {"ok": True, "model": model, "result": obj}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def perceive_json(force_snapshot_backend: str = "rpicam", sweep_head: bool = False, describe: bool = False) -> Dict[str, Any]:
    """Environment perception without driving.

    Includes:
    - ultrasonic distance
    - camera snapshot(s) (best effort)

    If `sweep_head` is enabled, performs a small head scan and captures 5 images:
    - left, center, right (tilt 0)
    - up, down (pan 0)

    Head movement is treated as *low risk* (no chassis motion).
    """
    base = health_json()
    base["cmd"] = "perceive"

    env = os.environ.copy()
    if force_snapshot_backend:
        env["PICARX_SNAPSHOT_BACKEND"] = force_snapshot_backend

    ai = os.path.join(_repo_root(), "aiagentctrl.py")

    # Ultrasonic
    ok_u, obj_u, raw_u = _run_json([sys.executable, ai, "ultrasonic", "--json"], timeout=6.0, env=env)
    base["sensors"] = {
        "ultrasonic": obj_u if obj_u else {"ok": ok_u, "raw": raw_u[-400:]},
    }

    # Default single snapshot (no sweep)
    if not sweep_head:
        ok_s, obj_s, raw_s = _run_json([sys.executable, ai, "snapshot", "--json"], timeout=15.0, env=env)
        base["camera"] = obj_s if obj_s else {"ok": ok_s, "raw": raw_s[-800:]}
        base["actuators"] = {"head_pan_tilt": "unknown", "drive": "blocked_without_go"}
        return base

    # Head sweep: L, C, R, (return center no photo), Up, Down.
    pan = int(os.environ.get("PICARX_SWEEP_PAN", "20"))
    tilt = int(os.environ.get("PICARX_SWEEP_TILT", "20"))

    shots = []

    def head(p: int, t: int) -> None:
        _run_json([sys.executable, ai, "head", "--pan", str(p), "--tilt", str(t), "--json"], timeout=6.0, env=env)
        time.sleep(float(os.environ.get("PICARX_SWEEP_SETTLE_S", "0.20")))

    def snap(label: str, p: int, t: int) -> None:
        ok, obj, raw = _run_json([sys.executable, ai, "snapshot", "--json"], timeout=15.0, env=env)
        shots.append({"label": label, "pan": p, "tilt": t, "snapshot": (obj if obj else {"ok": ok, "raw": raw[-800:]})})

    # left, center, right (with photos)
    head(-pan, 0)
    snap("left", -pan, 0)

    head(0, 0)
    snap("center", 0, 0)

    head(pan, 0)
    snap("right", pan, 0)

    # return center (no photo)
    head(0, 0)

    # up, down (with photos)
    head(0, tilt)
    snap("up", 0, tilt)

    head(0, -tilt)
    snap("down", 0, -tilt)

    # back to center (no photo)
    head(0, 0)

    base["camera"] = {"ok": True, "mode": "head_sweep", "shots": shots}
    base["actuators"] = {"head_pan_tilt": "unknown", "drive": "blocked_without_go"}

    if describe:
        base["perception"] = _describe_with_openai(shots)

    return base


def voltage_log(path: str, interval_s: float, duration_s: float) -> int:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    end = time.time() + duration_s if duration_s > 0 else None

    while True:
        entry = health_json()
        entry["cmd"] = "voltage_log"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        if end is not None and time.time() >= end:
            break
        time.sleep(interval_s)

    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_health = sub.add_parser("health", help="Print health JSON")
    ap_health.add_argument("--json", action="store_true", help="JSON only")

    ap_vlog = sub.add_parser("voltage-log", help="Append voltage/health samples to JSONL")
    ap_vlog.add_argument("--path", default=os.environ.get("PICARX_VOLTAGE_LOG", "logs/picarx_voltage.jsonl"))
    ap_vlog.add_argument("--interval", type=float, default=float(os.environ.get("PICARX_VOLTAGE_INTERVAL", "2.0")))
    ap_vlog.add_argument("--duration", type=float, default=float(os.environ.get("PICARX_VOLTAGE_DURATION", "120.0")))

    ap_perc = sub.add_parser("perceive", help="Environment perception (camera + ultrasonic), no driving")
    ap_perc.add_argument("--snapshot-backend", default=os.environ.get("PICARX_SNAPSHOT_BACKEND", "rpicam"))
    ap_perc.add_argument("--sweep-head", action="store_true", help="Take 5 images: left/center/right + up/down")
    ap_perc.add_argument("--describe", action="store_true", help="Use a vision model to interpret the images")

    args = ap.parse_args(argv)

    if args.cmd == "health":
        obj = health_json()
        print(json.dumps(obj, ensure_ascii=False))
        return 0

    if args.cmd == "voltage-log":
        path = args.path
        # allow repo-relative path
        if not os.path.isabs(path):
            path = os.path.join(_repo_root(), path)
        return voltage_log(path=path, interval_s=args.interval, duration_s=args.duration)

    if args.cmd == "perceive":
        obj = perceive_json(
            force_snapshot_backend=args.snapshot_backend,
            sweep_head=bool(args.sweep_head),
            describe=bool(args.describe),
        )
        print(json.dumps(obj, ensure_ascii=False))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
