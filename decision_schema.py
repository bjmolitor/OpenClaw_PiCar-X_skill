#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate LMM driving decision JSON (v0)."""

import argparse
import json
from typing import Any, Dict, List

ALLOWED_ACTIONS = {"arrived", "continue", "blocked", "uncertain"}


def validate_decision(d: Dict[str, Any]) -> List[str]:
    errs: List[str] = []

    action = d.get("action")
    if action not in ALLOWED_ACTIONS:
        errs.append("action must be one of: arrived|continue|blocked|uncertain")

    steer = d.get("steer")
    if steer is not None:
        if not isinstance(steer, int):
            errs.append("steer must be int or null")
        elif steer < -35 or steer > 35:
            errs.append("steer must be in range [-35, 35]")

    distance_cm = d.get("distance_cm")
    if distance_cm is not None:
        if not isinstance(distance_cm, (int, float)):
            errs.append("distance_cm must be number or null")
        elif distance_cm < 0 or distance_cm > 80:
            errs.append("distance_cm must be in range [0, 80]")

    reason = d.get("reason")
    if reason is not None and not isinstance(reason, str):
        errs.append("reason must be string or null")

    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate decision JSON v0")
    ap.add_argument("--json", dest="json_str", help="Decision JSON string")
    ap.add_argument("--file", help="Path to decision JSON file")
    args = ap.parse_args()

    if not args.json_str and not args.file:
        print(json.dumps({"ok": False, "error": {"code": "missing_input", "detail": "use --json or --file"}}))
        return 1

    try:
        if args.file:
            with open(args.file, "r", encoding="utf-8") as f:
                d = json.load(f)
        else:
            d = json.loads(args.json_str)
    except Exception as e:
        print(json.dumps({"ok": False, "error": {"code": "invalid_json", "detail": str(e)}}))
        return 1

    errs = validate_decision(d)
    if errs:
        print(json.dumps({"ok": False, "error": {"code": "schema_validation_failed", "detail": errs}}))
        return 1

    print(json.dumps({"ok": True, "decision": d}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
