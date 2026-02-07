#!/usr/bin/env python3
"""Capture a camera snapshot and inject it into an OpenClaw session.

This is a *session context* helper: it sends the image via OpenClaw messaging so
that the active agent can see it in the conversation history.

Required env:
- NAVIS_INJECT_CHANNEL (e.g., "whatsapp")
- NAVIS_INJECT_TARGET  (e.g., "+4917..." or channel id)

Optional env:
- NAVIS_INJECT_MESSAGE (caption text)
- NAVIS_OPENCLAW_BIN   (default: /usr/local/bin/openclaw)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, ROOT)

from checks._common import base_result, emit
from checks.media.camera import capture_snapshot, default_snapshot_path


def main() -> None:
    r = base_result("camera", "inject")

    channel = os.environ.get("NAVIS_INJECT_CHANNEL", "").strip()
    target = os.environ.get("NAVIS_INJECT_TARGET", "").strip()
    message = os.environ.get("NAVIS_INJECT_MESSAGE", "Camera snapshot (context)." ).strip()
    openclaw = os.environ.get("NAVIS_OPENCLAW_BIN", "/usr/local/bin/openclaw").strip() or "openclaw"

    if not channel or not target:
        r["ok"] = False
        r["error"] = "missing_inject_target"
        r["notes"].append("Set NAVIS_INJECT_CHANNEL and NAVIS_INJECT_TARGET to inject the image into the agent session.")
        emit(r)
        return

    try:
        out_path = default_snapshot_path(ROOT)
        path, cmdres = capture_snapshot(out_path=out_path, timeout_s=30)
        r["artifacts"].append({"kind": "image", "path": path, "desc": "camera snapshot (injected)"})
        r["evidence"]["commands"].append({"cmd": cmdres.cmd, "rc": cmdres.rc, "out": cmdres.out})

        # Send the image to the channel/target so it appears in the agent session history.
        cmd = [
            openclaw,
            "message",
            "send",
            "--channel",
            channel,
            "--target",
            target,
            "--message",
            message,
            "--media",
            path,
            "--json",
        ]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
        r["evidence"]["commands"].append({"cmd": cmd, "rc": p.returncode, "out": (p.stdout or "")[:2000]})
        if p.returncode != 0:
            r["ok"] = False
            r["error"] = "inject_failed"

    except Exception as e:
        r["ok"] = False
        r["error"] = "inject_exception"
        r["notes"].append(str(e))

    emit(r)


if __name__ == "__main__":
    main()
