#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Purpose: Agentic driving turn wrapper for PiCar-X.
# One turn = snapshot -> (optional steer) -> drive -> snapshot

import argparse
import json
import os
import subprocess
import time
from datetime import datetime
from typing import Dict, Any, Optional

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
AIAGENT = os.path.join(REPO_DIR, "aiagentctrl.py")

# Calibrated seconds for 40cm at given speeds
CALIB_40CM = {
    30: 1.48,
    50: 1.29,
    60: 1.25,
}


def _seconds_for_distance(speed: int, distance_cm: float) -> Optional[float]:
    if not CALIB_40CM:
        return None
    # exact match
    if speed in CALIB_40CM:
        return CALIB_40CM[speed] * (distance_cm / 40.0)
    # linear interpolation between nearest speeds
    speeds = sorted(CALIB_40CM.keys())
    lo = max([s for s in speeds if s < speed], default=None)
    hi = min([s for s in speeds if s > speed], default=None)
    if lo is None:
        base = CALIB_40CM[speeds[0]]
        return base * (distance_cm / 40.0)
    if hi is None:
        base = CALIB_40CM[speeds[-1]]
        return base * (distance_cm / 40.0)
    # interpolate base seconds for 40cm
    base = CALIB_40CM[lo] + (CALIB_40CM[hi] - CALIB_40CM[lo]) * ((speed - lo) / (hi - lo))
    return base * (distance_cm / 40.0)


def _image_diff_ratio(path_a: str, path_b: str) -> Optional[float]:
    """Return mean absolute pixel diff ratio [0..1], or None if unavailable."""
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return None
    try:
        im1 = Image.open(path_a).convert("L").resize((160, 120))
        im2 = Image.open(path_b).convert("L").resize((160, 120))
        p1 = im1.load()
        p2 = im2.load()
        w, h = im1.size
        total = 0
        for y in range(h):
            for x in range(w):
                total += abs(p1[x, y] - p2[x, y])
        # normalize by max per-pixel diff (255)
        return total / (w * h * 255.0)
    except Exception:
        return None


def _run(cmd, env=None) -> Dict[str, Any]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    out = p.stdout.strip() if p.stdout else ""
    if p.returncode != 0:
        return {"ok": False, "error": f"cmd failed ({p.returncode})", "cmd": cmd, "stdout": out, "stderr": p.stderr}
    try:
        return json.loads(out)
    except Exception:
        return {"ok": False, "error": "invalid json", "cmd": cmd, "stdout": out, "stderr": p.stderr}


def do_turn(args) -> Dict[str, Any]:
    env = os.environ.copy()
    if args.invert is not None:
        env["PICARX_DRIVE_INVERT"] = "1" if args.invert else "0"

    # Decide seconds either from explicit --seconds, or from calibrated distance.
    seconds = args.seconds
    if seconds is None:
        seconds = _seconds_for_distance(args.speed, args.distance_cm)
        if seconds is None:
            seconds = 1.48  # fallback

    result: Dict[str, Any] = {
        "ok": True,
        "cmd": "agentic_turn",
        "ts": datetime.utcnow().isoformat() + "Z",
        "requested": {
            "speed": args.speed,
            "seconds": float(seconds),
            "distance_cm": args.distance_cm,
            "direction": args.direction,
            "steer": args.steer,
            "invert": env.get("PICARX_DRIVE_INVERT", None),
        },
    }

    # 1) Pre snapshot
    pre = _run([AIAGENT, "snapshot", "--json"], env=env)
    result["pre_snapshot"] = pre
    if not pre.get("ok"):
        result["ok"] = False
        return result

    # 2) Optional steer
    if args.steer is not None:
        steer = _run([AIAGENT, "steer", "--angle", str(args.steer), "--json"], env=env)
        result["steer"] = steer
        if not steer.get("ok"):
            result["ok"] = False
            return result

    # 3) Drive
    drive = _run([
        AIAGENT, "drive",
        "--speed", str(args.speed),
        "--seconds", str(seconds),
        "--direction", args.direction,
        "--json",
    ], env=env)
    result["drive"] = drive
    if not drive.get("ok"):
        result["ok"] = False
        return result

    if args.pause_after > 0:
        time.sleep(args.pause_after)

    # 4) Post snapshot
    post = _run([AIAGENT, "snapshot", "--json"], env=env)
    result["post_snapshot"] = post
    if not post.get("ok"):
        result["ok"] = False
        return result

    # 5) Optional image diff (stuck detection)
    pre_path = pre.get("path")
    post_path = post.get("path")
    if pre_path and post_path:
        diff_ratio = _image_diff_ratio(pre_path, post_path)
        result["diff_ratio"] = diff_ratio
        if diff_ratio is not None:
            result["moved"] = diff_ratio >= args.min_diff
            if args.stop_on_stuck and not result["moved"]:
                result["ok"] = False
                result["error"] = "stuck_detected"

    return result


def main():
    ap = argparse.ArgumentParser(description="Agentic driving turn wrapper: snapshot -> steer? -> drive -> snapshot")
    ap.add_argument("--speed", type=int, default=30)
    ap.add_argument("--distance-cm", type=float, default=40.0, help="Target distance for this turn; used if --seconds not provided")
    ap.add_argument("--seconds", type=float, default=None, help="Override drive duration in seconds (else uses calibration)")
    ap.add_argument("--direction", choices=["forward", "backward"], default="forward")
    ap.add_argument("--steer", type=int, default=None, help="Steering angle (-35..35) before driving")
    ap.add_argument("--invert", type=int, choices=[0,1], default=1, help="Set PICARX_DRIVE_INVERT (1 default)")
    ap.add_argument("--pause-after", type=float, default=0.0, help="Sleep seconds between drive and post-snapshot")
    ap.add_argument("--min-diff", type=float, default=0.01, help="Min diff ratio [0..1] to consider movement")
    ap.add_argument("--stop-on-stuck", action="store_true", help="Return ok=false if movement not detected")
    ap.add_argument("--loops", type=int, default=1, help="Repeat turns N times")
    args = ap.parse_args()

    if args.loops <= 1:
        res = do_turn(args)
        print(json.dumps(res, separators=(",", ":")))
    else:
        results = []
        ok = True
        for i in range(1, args.loops + 1):
            turn = do_turn(args)
            turn["iter"] = i
            results.append(turn)
            if not turn.get("ok"):
                ok = False
                break
        print(json.dumps({"ok": ok, "cmd": "agentic_loop", "turns": results}, separators=(",", ":")))


if __name__ == "__main__":
    main()
