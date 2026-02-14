#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""
OpenClaw-facing router for concrete picarx.* tool namespace.

Namespace mapping:
- picarx.snapshot
- picarx.ultrasonic
- picarx.steer
- picarx.head
- picarx.drive
- picarx.stop
- picarx.turn
"""

import argparse
import json
import os
import subprocess
from datetime import datetime
from typing import Any, Dict, List

REPO = os.path.dirname(os.path.abspath(__file__))
AIAGENT = os.path.join(REPO, "aiagentctrl.py")
TURN = os.path.join(REPO, "agentic_drive.py")


def _run(cmd: List[str]) -> Dict[str, Any]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out = (p.stdout or "").strip()
    if p.returncode != 0:
        return {
            "ok": False,
            "cmd": "router",
            "ts": datetime.utcnow().isoformat() + "Z",
            "requested": {"argv": cmd},
            "applied": {},
            "artifacts": {},
            "error": {"code": "subprocess_failed", "detail": p.stderr.strip() or out},
        }
    try:
        data = json.loads(out)
    except Exception:
        return {
            "ok": False,
            "cmd": "router",
            "ts": datetime.utcnow().isoformat() + "Z",
            "requested": {"argv": cmd},
            "applied": {},
            "artifacts": {},
            "error": {"code": "invalid_json", "detail": out},
        }
    data.setdefault("ts", datetime.utcnow().isoformat() + "Z")
    data.setdefault("requested", {})
    data.setdefault("applied", {})
    data.setdefault("artifacts", {})
    data.setdefault("error", None)
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="PiCar-X tool namespace router")
    sub = ap.add_subparsers(dest="tool", required=True)

    sub.add_parser("picarx.snapshot")
    sub.add_parser("picarx.ultrasonic")

    p_steer = sub.add_parser("picarx.steer")
    p_steer.add_argument("--angle", type=int, required=True)

    p_head = sub.add_parser("picarx.head")
    p_head.add_argument("--pan", type=int)
    p_head.add_argument("--tilt", type=int)

    p_drive = sub.add_parser("picarx.drive")
    p_drive.add_argument("--speed", type=int, required=True)
    p_drive.add_argument("--seconds", type=float, required=True)
    p_drive.add_argument("--direction", choices=["forward", "backward"], required=True)

    sub.add_parser("picarx.stop")

    p_turn = sub.add_parser("picarx.turn")
    p_turn.add_argument("--distance-cm", type=float, default=40.0)
    p_turn.add_argument("--speed", type=int, default=30)
    p_turn.add_argument("--direction", choices=["forward", "backward"], default="forward")
    p_turn.add_argument("--steer", type=int)
    p_turn.add_argument("--loops", type=int, default=1)
    p_turn.add_argument("--invert", type=int, choices=[0, 1], default=1)
    p_turn.add_argument("--stop-on-stuck", action="store_true")

    args = ap.parse_args()

    if args.tool == "picarx.snapshot":
        res = _run([AIAGENT, "snapshot", "--json"])
    elif args.tool == "picarx.ultrasonic":
        res = _run([AIAGENT, "ultrasonic", "--json"])
    elif args.tool == "picarx.steer":
        res = _run([AIAGENT, "steer", "--angle", str(args.angle), "--json"])
    elif args.tool == "picarx.head":
        cmd = [AIAGENT, "head", "--json"]
        if args.pan is not None:
            cmd += ["--pan", str(args.pan)]
        if args.tilt is not None:
            cmd += ["--tilt", str(args.tilt)]
        res = _run(cmd)
    elif args.tool == "picarx.drive":
        res = _run([
            AIAGENT,
            "drive",
            "--speed",
            str(args.speed),
            "--seconds",
            str(args.seconds),
            "--direction",
            args.direction,
            "--json",
        ])
    elif args.tool == "picarx.stop":
        res = _run([AIAGENT, "stop", "--json"])
    elif args.tool == "picarx.turn":
        cmd = [
            TURN,
            "--distance-cm",
            str(args.distance_cm),
            "--speed",
            str(args.speed),
            "--direction",
            args.direction,
            "--loops",
            str(args.loops),
            "--invert",
            str(args.invert),
        ]
        if args.steer is not None:
            cmd += ["--steer", str(args.steer)]
        if args.stop_on_stuck:
            cmd += ["--stop-on-stuck"]
        res = _run(cmd)
    else:
        res = {
            "ok": False,
            "cmd": "router",
            "ts": datetime.utcnow().isoformat() + "Z",
            "requested": {},
            "applied": {},
            "artifacts": {},
            "error": {"code": "unknown_tool", "detail": args.tool},
        }

    print(json.dumps(res, separators=(",", ":"), ensure_ascii=False))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
