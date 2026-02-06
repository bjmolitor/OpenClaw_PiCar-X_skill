"""End-to-end speaker→mic soundcheck.

Approach:
- Generate a deterministic multi-tone reference waveform (WAV)
- Play it through the speaker
- Simultaneously record from the mic
- Compare via normalized cross-correlation (peak + lag)

This is designed to answer: "does the mic pick up what the speaker plays?"
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None

from checks.media.audio import AudioPaths, _enable_robot_hat_speaker_best_effort
from checks.media.common import CmdResult, ensure_dir, run_cmd


@dataclass
class SoundcheckConfig:
    rate: int = 16000
    seconds: float = 4.0
    freqs: Tuple[int, ...] = (220, 440, 880, 1760)
    max_lag_s: float = 0.80
    min_corr: float = 0.05


def _wav_write_mono_s16(path: str, samples: "np.ndarray", rate: int) -> None:
    import wave

    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.astype("<i2").tobytes())


def _wav_read_mono_s16(path: str) -> Tuple[int, "np.ndarray"]:
    """Read mono 16-bit WAV into float32 in range ~[-1,1]."""
    import wave

    with wave.open(path, "rb") as wf:
        rate = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    return rate, a


def _tone_ref(cfg: SoundcheckConfig) -> "np.ndarray":
    """Generate deterministic multi-tone reference.

    Mirrors the original `navis_media.py` approach: sequential tone segments.
    """
    seg_s = float(cfg.seconds) / float(len(cfg.freqs))
    x_all = []
    for f in cfg.freqs:
        n = int(cfg.rate * seg_s)
        t = np.arange(n, dtype=np.float32) / float(cfg.rate)
        x = 0.35 * np.sin(2.0 * math.pi * float(f) * t)
        fade_n = max(16, int(0.01 * cfg.rate))
        fade = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
        x[:fade_n] *= fade
        x[-fade_n:] *= fade[::-1]
        x_all.append(x)

    y = np.concatenate(x_all)
    pcm = np.clip(y * 32767.0, -32768.0, 32767.0)
    return pcm


def default_paths(workspace: str) -> Tuple[str, str]:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    ref = os.path.join(workspace, "audio", f"soundcheck-ref-{ts}.wav")
    rec = os.path.join(workspace, "audio", f"soundcheck-rec-{ts}.wav")
    return ref, rec


def run_soundcheck(
    *,
    workspace: str,
    mic_device: Optional[str] = None,
    spk_device: Optional[str] = None,
    cfg: Optional[SoundcheckConfig] = None,
) -> Dict:
    if np is None:
        raise RuntimeError("numpy is required for soundcheck")

    cfg = cfg or SoundcheckConfig()

    ensure_dir(os.path.join(workspace, "audio"))
    ref_path, rec_path = default_paths(workspace)

    ref = _tone_ref(cfg)
    _wav_write_mono_s16(ref_path, ref, cfg.rate)

    # Default to enabling onboard speaker amp for reliable acoustic path checks.
    os.environ.setdefault("NAVIS_ENABLE_ROBOT_HAT_SPEAKER", "1")
    _enable_robot_hat_speaker_best_effort()

    import shutil

    arecord_exe = shutil.which("arecord")
    if not arecord_exe:
        raise FileNotFoundError("arecord not found")
    aplay_exe = shutil.which("aplay")
    if not aplay_exe:
        raise FileNotFoundError("aplay not found")

    # Start recording first to avoid missing the beginning.
    arecord_cmd = [arecord_exe]
    dev = mic_device or os.environ.get("NAVIS_MIC_DEVICE", "").strip() or "plughw:3,0"
    if dev:
        arecord_cmd += ["-D", dev]
    # Record slightly longer than playback to ensure we capture the full played signal.
    dur_s = max(1, int(round(float(cfg.seconds) + 0.2)))
    arecord_cmd += ["-f", "S16_LE", "-r", str(cfg.rate), "-c", "1", "-d", str(dur_s), rec_path]

    aplay_cmd = [aplay_exe]
    spk = spk_device or os.environ.get("NAVIS_SPK_DEVICE", "").strip() or "plughw:2,0"
    if spk:
        aplay_cmd += ["-D", spk]
    aplay_cmd += [ref_path]

    import subprocess

    evidence_cmds = []

    # Best-effort: stop listener to avoid "device busy".
    evidence_cmds.append(run_cmd(["bash", "-lc", "systemctl --user stop navis-listen.service 2>/dev/null || true"], timeout_s=6, max_chars=1000))

    # Launch arecord in background, then play.
    arec = subprocess.Popen(arecord_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        import time

        time.sleep(0.12)
        play_res = run_cmd(aplay_cmd, timeout_s=int(dur_s) + 20, max_chars=2000)
        out_arec, _ = arec.communicate(timeout=int(dur_s) + 25)
        arec_rc = arec.returncode
    finally:
        # Best-effort: restart listener.
        evidence_cmds.append(run_cmd(["bash", "-lc", "systemctl --user start navis-listen.service 2>/dev/null || true"], timeout_s=6, max_chars=1000))

    # Ensure recording exists
    if not os.path.exists(rec_path) or os.path.getsize(rec_path) == 0:
        raise RuntimeError(f"arecord produced no file rc={arec_rc} out={(out_arec or '').strip()[:2000]}")

    # Load recorded + reference from disk and compute correlation
    rr, y = _wav_read_mono_s16(rec_path)
    xr, x = _wav_read_mono_s16(ref_path)

    eps = 1e-9
    rms_ref = float(np.sqrt((x * x).mean() + eps))
    rms_rec = float(np.sqrt((y * y).mean() + eps))

    # normalized cross-correlation over +/- max_lag
    max_lag = int(min(len(x) - 1, max(1, int(cfg.rate * cfg.max_lag_s))))

    x0 = x - float(x.mean())
    y0 = y - float(y.mean())

    best = 0.0
    best_lag = 0
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            a = x0[-lag:]
            b = y0[: len(a)]
        elif lag > 0:
            a = x0[:-lag]
            b = y0[lag : lag + len(a)]
        else:
            a = x0
            b = y0
        if len(a) < 1024:
            continue
        # Use lag-local normalization; robust against startup latency and unequal tails.
        den = float(np.sqrt((a * a).sum() + eps) * np.sqrt((b * b).sum() + eps))
        c = float((a * b).sum() / (den + eps))
        if abs(c) > abs(best):
            best = c
            best_lag = lag

    ok = bool(abs(best) >= cfg.min_corr) and bool(rms_rec > 0.005)

    return {
        "ok": ok,
        "action": "soundcheck",
        "speaker_enabled": bool(os.environ.get("NAVIS_ENABLE_ROBOT_HAT_SPEAKER")),
        "spk_device": spk or None,
        "mic_device": dev or None,
        "ref": {"path": ref_path, "rate": cfg.rate, "seconds": cfg.seconds, "freqs": list(cfg.freqs)},
        "rec": {"path": rec_path},
        "metrics": {"corr_peak": best, "corr_lag_s": best_lag / float(cfg.rate), "rms_ref": rms_ref, "rms_rec": rms_rec, "min_corr": cfg.min_corr, "max_lag_s": cfg.max_lag_s},
        "evidence": {
            "commands": [
                *[{"cmd": c.cmd, "rc": c.rc, "out": c.out} for c in evidence_cmds],
                {"cmd": arecord_cmd, "rc": arec_rc, "out": (out_arec or "").strip()[:2000]},
                {"cmd": aplay_cmd, "rc": play_res.rc, "out": (play_res.out or "").strip()[:2000]},
            ]
        },
    }
