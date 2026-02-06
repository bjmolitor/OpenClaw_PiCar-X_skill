#!/usr/bin/env python3
"""Health check: capture a camera snapshot.

Outputs JSON with an image artifact path.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from checks._common import base_result, emit
from checks.media.camera import capture_snapshot, default_snapshot_path


def main() -> None:
    ws = os.path.dirname(os.path.dirname(__file__))
    r = base_result("camera", "capture")

    out_path = default_snapshot_path(ws)
    try:
        path, cmdres = capture_snapshot(out_path=out_path, timeout_s=30)
        r["artifacts"].append({"kind": "image", "path": path, "desc": "camera snapshot"})
        r["evidence"]["commands"].append({"cmd": cmdres.cmd, "rc": cmdres.rc, "out": cmdres.out})
    except Exception as e:
        r["ok"] = False
        r["error"] = "camera_capture_failed"
        r["notes"].append(str(e))

    emit(r)


if __name__ == "__main__":
    main()
