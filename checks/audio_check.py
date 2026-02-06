#!/usr/bin/env python3
"""Health check: basic audio I/O.

- Records a short mic clip (artifact)
- Plays it back
- Generates TTS and plays it back

This check does **not** attempt end-to-end speaker→mic correlation. Use
`soundcheck_check.py` for that.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from checks._common import base_result, emit
from checks.media.audio import AudioPaths, default_mic_path, default_tts_path, play_wav, record_mic_wav, tts_to_wav


def main() -> None:
    ws = os.path.dirname(os.path.dirname(__file__))
    paths = AudioPaths(workspace=ws)

    r = base_result("audio", "basic")

    # 1) Mic record a short clip (artifact)
    mic_path = default_mic_path(paths)
    try:
        path, rec_res, dev = record_mic_wav(out_path=mic_path, seconds=3, rate=16000)
        r["artifacts"].append({"kind": "audio", "path": path, "desc": f"mic recording (device={dev})"})
        r["metrics"].update({"mic_device": dev, "mic_path": path})
        r["evidence"]["commands"].append({"cmd": rec_res.cmd, "rc": rec_res.rc, "out": rec_res.out})
    except Exception as e:
        r["ok"] = False
        r["error"] = "mic_record_failed"
        r["notes"].append(str(e))
        emit(r)
        return

    # 2) Playback the mic recording (speaker path)
    try:
        play_res = play_wav(path=mic_path, timeout_s=25)
        r["evidence"]["commands"].append({"cmd": play_res.cmd, "rc": play_res.rc, "out": play_res.out})
    except Exception as e:
        r["ok"] = False
        r["error"] = "speaker_playback_failed"
        r["notes"].append(str(e))

    # 3) TTS to wav + playback
    try:
        tts_path = default_tts_path(paths)
        wav_path, tts_res, backend = tts_to_wav(text="Navis audio health check.", out_path=tts_path, lang="en-US")
        r["artifacts"].append({"kind": "audio", "path": wav_path, "desc": f"tts wav (backend={backend})"})
        r["evidence"]["commands"].append({"cmd": tts_res.cmd, "rc": tts_res.rc, "out": tts_res.out})

        play_res2 = play_wav(path=wav_path, timeout_s=25)
        r["evidence"]["commands"].append({"cmd": play_res2.cmd, "rc": play_res2.rc, "out": play_res2.out})
    except Exception as e:
        r["ok"] = False
        r["error"] = "tts_failed"
        r["notes"].append(str(e))

    emit(r)


if __name__ == "__main__":
    main()
