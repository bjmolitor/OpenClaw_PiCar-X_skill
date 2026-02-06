#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from checks._common import base_result, emit


def main():
    r = base_result("camera", "movement")

    # Baseline assumption: standard hardware includes camera pan/tilt.
    # If it's missing, that is BROKEN relative to the expected baseline.
    expect = True

    r["metrics"] = {
        "expected": expect,
        "supported": True,  # check exists; hardware may be broken
        "detected": False,
    }

    # We currently do not have a safe, reliable servo probe without risking further damage.
    # Given known physical damage/removal, we report BROKEN.
    r["ok"] = False
    r["error"] = "camera_movement_broken"
    r["metrics"].update({"reason": "pan_tilt_unavailable"})
    r["notes"].append("Camera pan/tilt is expected on baseline hardware but is currently unavailable (broken/dismantled).")

    emit(r)


if __name__ == "__main__":
    main()
