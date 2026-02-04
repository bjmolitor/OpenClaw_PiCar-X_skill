#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""PiCar-X / Robot-HAT health checks.

MVP v0.1 goals:
- Deterministic JSON output for host + robot body health.
- Optional voltage logging to detect supply sag / undervoltage during load.

This script is SAFE by default (no motion).
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
from typing import Any, Dict, Optional


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

    args = ap.parse_args(argv)

    if args.cmd == "health":
        obj = health_json()
        print(json.dumps(obj, ensure_ascii=False))
        return 0

    if args.cmd == "voltage-log":
        path = args.path
        # allow repo-relative path
        if not os.path.isabs(path):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
        return voltage_log(path=path, interval_s=args.interval, duration_s=args.duration)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
