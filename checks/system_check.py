#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from checks._common import base_result, emit, run_cmd


def main():
    r = base_result("system", "snapshot")
    r["evidence"]["commands"].append(run_cmd(["uptime"], timeout_s=2))
    r["evidence"]["commands"].append(run_cmd(["free", "-h"], timeout_s=2))
    r["evidence"]["commands"].append(run_cmd(["df", "-hT", "/"], timeout_s=3))
    r["evidence"]["commands"].append(run_cmd(["ps", "-eo", "pid,comm,%cpu,%mem", "--sort=-%cpu"], timeout_s=3, max_chars=2500))
    r["evidence"]["commands"].append(run_cmd(["ps", "-eo", "pid,comm,%cpu,%mem", "--sort=-%mem"], timeout_s=3, max_chars=2500))
    r["evidence"]["commands"].append(run_cmd(["systemctl", "--no-pager", "--failed"], timeout_s=4, max_chars=2500))
    emit(r)


if __name__ == "__main__":
    main()
