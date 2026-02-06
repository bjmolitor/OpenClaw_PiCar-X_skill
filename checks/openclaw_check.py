#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from checks._common import base_result, emit, run_cmd


def main():
    r = base_result("openclaw", "status")
    r["evidence"]["commands"].append(run_cmd(["openclaw", "status", "--all"], timeout_s=20, max_chars=8000))
    emit(r)


if __name__ == "__main__":
    main()
