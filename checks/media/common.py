"""Shared helpers for Navis health checks.

This package contains **implementation code** used by the check entrypoints in
`checks/*_check.py`.

Design goals:
- Read-only checks (no destructive actions)
- Deterministic, JSON-friendly behavior
- Minimal dependencies; optional numpy where helpful
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CmdResult:
    cmd: List[str]
    rc: Optional[int]
    out: str


def run_cmd(cmd: List[str], *, timeout_s: int = 20, max_chars: int = 8000) -> CmdResult:
    """Run a command and capture stdout+stderr.

    Never raises; returns rc=None on unexpected runner errors.
    Output is truncated to `max_chars`.
    """
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        out = (p.stdout or "").strip()
        if max_chars and len(out) > max_chars:
            out = out[:max_chars] + "\n...[truncated]"
        return CmdResult(cmd=cmd, rc=p.returncode, out=out)
    except Exception as e:  # pragma: no cover
        return CmdResult(cmd=cmd, rc=None, out=str(e))


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)
