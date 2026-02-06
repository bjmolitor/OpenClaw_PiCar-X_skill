#!/usr/bin/env python3
"""Facade runner for Navis checks.

- Runs checks individually or as a group.
- Prints JSON array of results.
- Does NOT generate a human summary; the receiving agent should do that.
"""

import argparse
import json
import os
import subprocess
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


CHECKS = {
    "system": "checks/system_check.py",
    "power": "checks/power_thermal_check.py",
    "storage": "checks/storage_check.py",

    # audio
    "audio": "checks/audio_check.py",
    "soundcheck": "checks/soundcheck_check.py",

    # camera (split)
    "camera_capture": "checks/camera_capture_check.py",
    "camera_analysis": "checks/camera_analysis_check.py",
    "camera_movement": "checks/camera_movement_check.py",

    "openclaw": "checks/openclaw_check.py",
    "network": "checks/network_check.py",
}


def _run_check(script_path: str, timeout_s: int = 300):
    """Run one check script and parse its JSON output."""
    abs_script = script_path if os.path.isabs(script_path) else os.path.join(ROOT_DIR, script_path)
    cmd = ["python3", abs_script]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout_s, check=False)
    out = (p.stdout or "").strip()

    # Try parse JSON. If parsing fails, return a structured error result.
    try:
        obj = json.loads(out)
        # If script returned non-zero but produced JSON, keep ok as-is but attach rc.
        if isinstance(obj, dict):
            obj.setdefault("evidence", {})
            obj["evidence"].setdefault("runner", {})
            obj["evidence"]["runner"].update({"cmd": cmd, "rc": p.returncode})
        return obj
    except Exception:
        return {
            "ok": False,
            "area": "facade",
            "check": os.path.basename(abs_script),
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "error": "check_output_not_json",
            "metrics": {},
            "artifacts": [],
            "evidence": {"runner": {"cmd": cmd, "rc": p.returncode, "out": out[:12000]}},
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated list of checks (default: all)")
    ap.add_argument("--timeout", type=int, default=300, help="timeout per check in seconds")
    ap.add_argument("--jsonl", action="store_true", help="emit JSONL (one JSON per line) instead of a JSON array")
    args = ap.parse_args()

    names = list(CHECKS.keys())
    if args.only:
        wanted = [x.strip() for x in args.only.split(",") if x.strip()]
        unknown = [w for w in wanted if w not in CHECKS]
        if unknown:
            raise SystemExit(f"Unknown checks: {unknown}. Known: {list(CHECKS.keys())}")
        names = wanted

    results = []
    for name in names:
        script = CHECKS[name]
        results.append(_run_check(script, timeout_s=args.timeout))

    if args.jsonl:
        for r in results:
            print(json.dumps(r, ensure_ascii=False))
        return

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
