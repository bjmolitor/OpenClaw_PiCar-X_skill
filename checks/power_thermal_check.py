#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import shutil
from checks._common import base_result, emit, run_cmd


def main():
    r = base_result("power_thermal", "pi")
    vcgencmd = shutil.which("vcgencmd")
    if not vcgencmd:
        r["ok"] = False
        r["error"] = "vcgencmd_not_found"
        emit(r)
        return

    r["evidence"]["commands"].append(run_cmd([vcgencmd, "measure_temp"], timeout_s=2))
    r["evidence"]["commands"].append(run_cmd([vcgencmd, "get_throttled"], timeout_s=2))
    r["evidence"]["commands"].append(run_cmd([vcgencmd, "measure_volts", "core"], timeout_s=2))
    emit(r)


if __name__ == "__main__":
    main()
