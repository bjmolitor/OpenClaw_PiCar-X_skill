#!/usr/bin/env python3
"""Health check: end-to-end speaker→mic verification.

Produces reference + recorded WAV artifacts and correlation metrics.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from checks._common import base_result, emit
from checks.media.soundcheck import run_soundcheck


def main() -> None:
    ws = os.path.dirname(os.path.dirname(__file__))
    r = base_result("audio", "soundcheck")

    try:
        sc = run_soundcheck(workspace=ws)
        r["ok"] = bool(sc.get("ok"))
        r["metrics"].update(sc.get("metrics") or {})

        ref = (sc.get("ref") or {}).get("path")
        rec = (sc.get("rec") or {}).get("path")
        if ref:
            r["artifacts"].append({"kind": "audio", "path": ref, "desc": "soundcheck reference"})
        if rec:
            r["artifacts"].append({"kind": "audio", "path": rec, "desc": "soundcheck recording"})
        wake_ref = (sc.get("wake_ref") or {}).get("path")
        wake_rec = (sc.get("wake_rec") or {}).get("path")
        if wake_ref:
            r["artifacts"].append({"kind": "audio", "path": wake_ref, "desc": "wakeword reference"})
        if wake_rec:
            r["artifacts"].append({"kind": "audio", "path": wake_rec, "desc": "wakeword recording"})

        for c in (sc.get("evidence") or {}).get("commands") or []:
            r["evidence"]["commands"].append(c)

    except Exception as e:
        r["ok"] = False
        r["error"] = "soundcheck_failed"
        r["notes"].append(str(e))
    finally:
        # Ensure listener returns after active soundcheck, even on failure.
        subprocess.run(
            ["bash", "-lc", "systemctl --user start navis-listen.service 2>/dev/null || true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    emit(r)


if __name__ == "__main__":
    main()
