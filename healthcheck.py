#!/usr/bin/env python3
"""Healthcheck entrypoint for PiCar-X skill.

This wrapper delegates to the checks framework runner in `checks/run_checks.py`.
"""

from __future__ import annotations

import os
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = os.path.dirname(os.path.abspath(__file__))
    runner = os.path.join(root, "checks", "run_checks.py")

    cmd = [sys.executable, runner, *argv]
    p = subprocess.run(cmd)
    return int(p.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
