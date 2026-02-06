#!/usr/bin/env python3
import json
import os
import subprocess
from datetime import datetime


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run_cmd(cmd, timeout_s=5, max_chars=4000):
    """Best-effort command runner; returns rc+output."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout_s, check=False)
        out = (p.stdout or "")
        if max_chars and len(out) > max_chars:
            out = out[:max_chars] + "\n...[truncated]"
        return {"cmd": cmd, "rc": p.returncode, "out": out.strip()}
    except Exception as e:
        return {"cmd": cmd, "rc": None, "out": str(e)}


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def base_result(area: str, check: str):
    return {
        "ok": True,
        "area": area,
        "check": check,
        "ts": now_iso(),
        "artifacts": [],
        "metrics": {},
        "evidence": {"commands": []},
        "notes": [],
    }
