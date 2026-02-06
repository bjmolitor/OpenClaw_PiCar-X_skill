#!/usr/bin/env python3
"""Health check: capture + analyze snapshot brightness stats.

This is kept separate from `camera_capture_check.py` so the agent can decide
whether to attach the raw image, the stats, or both.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from checks._common import base_result, emit
from checks.media.camera import capture_snapshot, default_snapshot_path, image_stats


def main() -> None:
    ws = os.path.dirname(os.path.dirname(__file__))
    r = base_result("camera", "analysis")

    out_path = default_snapshot_path(ws)
    try:
        path, cmdres = capture_snapshot(out_path=out_path, timeout_s=30)
        r["artifacts"].append({"kind": "image", "path": path, "desc": "camera snapshot (for analysis)"})
        r["evidence"]["commands"].append({"cmd": cmdres.cmd, "rc": cmdres.rc, "out": cmdres.out})

        r["metrics"].update(image_stats(path))
    except Exception as e:
        r["ok"] = False
        r["error"] = "camera_analysis_failed"
        r["notes"].append(str(e))

    emit(r)


if __name__ == "__main__":
    main()
