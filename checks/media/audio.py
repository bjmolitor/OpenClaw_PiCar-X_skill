"""Audio helpers for Navis checks.

- Mic capture via `arecord`
- Playback via `aplay` (ALSA) or `paplay` (Pulse/PipeWire)
- TTS via `pico2wave` (default) or `espeak`

Device selection is controlled by env:
- NAVIS_MIC_DEVICE=plughw:3,0
- NAVIS_SPK_DEVICE=plughw:2,0
- NAVIS_PULSE_SINK=<sink>
- NAVIS_ENABLE_ROBOT_HAT_SPEAKER=1 (best-effort enable onboard amp)
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

from checks.media.common import CmdResult, ensure_dir, run_cmd


@dataclass
class AudioPaths:
    workspace: str

    @property
    def audio_dir(self) -> str:
        return os.path.join(self.workspace, "audio")


def _env_bool(name: str, default: str = "0") -> bool:
    return str(os.environ.get(name, default)).strip().lower() in ("1", "true", "yes", "on")


def _enable_robot_hat_speaker_best_effort() -> bool:
    """Try to enable Robot-HAT speaker amp.

    Best-effort; returns True if it *seems* executed, False otherwise.
    """
    if not _env_bool("NAVIS_ENABLE_ROBOT_HAT_SPEAKER", "0"):
        return False

    # Primary path: use `pinctrl` directly (observed working on the PiCar-X)
    pinctrl = shutil.which("pinctrl")
    if pinctrl:
        r = run_cmd([pinctrl, "set", "20", "op", "dh"], timeout_s=2, max_chars=500)
        return r.rc == 0

    # Secondary path: robot_hat python lib (if present)
    try:  # pragma: no cover
        import robot_hat  # type: ignore

        if hasattr(robot_hat, "enable_speaker"):
            robot_hat.enable_speaker()  # type: ignore
            return True
    except Exception:
        pass

    return False


def record_mic_wav(*, out_path: str, seconds: int = 3, rate: int = 16000, device: Optional[str] = None) -> Tuple[str, CmdResult, str]:
    """Record a mono WAV from the microphone using arecord."""
    ensure_dir(os.path.dirname(out_path))
    arecord = shutil.which("arecord")
    if not arecord:
        raise FileNotFoundError("arecord not found")

    # Baseline hardware default: USB mic on ALSA card 3 (plughw:3,0 @16k).
    dev = device or os.environ.get("NAVIS_MIC_DEVICE", "").strip() or "plughw:3,0"

    cmd = [arecord]
    if dev and dev != "default":
        cmd += ["-D", dev]
    cmd += ["-f", "S16_LE", "-r", str(rate), "-c", "1", "-d", str(seconds), out_path]

    # Best-effort: stop listener to avoid holding the mic device.
    _ = run_cmd(["bash", "-lc", "systemctl --user stop navis-listen.service 2>/dev/null || true"], timeout_s=6, max_chars=1000)

    r = run_cmd(cmd, timeout_s=max(5, seconds + 15), max_chars=4000)

    _ = run_cmd(["bash", "-lc", "systemctl --user start navis-listen.service 2>/dev/null || true"], timeout_s=6, max_chars=1000)
    if r.rc != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError(f"Mic record failed rc={r.rc}: {r.out}")

    return out_path, r, dev


def play_wav(*, path: str, timeout_s: int = 20, device: Optional[str] = None) -> CmdResult:
    """Play a wav file.

    Prefers paplay if available (to use default PipeWire/Pulse routing), otherwise aplay.
    """
    _enable_robot_hat_speaker_best_effort()

    # Allow forcing ALSA device
    # Baseline hardware default: onboard DAC on ALSA card 2.
    alsa_dev = device or os.environ.get("NAVIS_SPK_DEVICE", "").strip() or "plughw:2,0"

    paplay = shutil.which("paplay")
    if paplay and not alsa_dev:
        sink = os.environ.get("NAVIS_PULSE_SINK", "").strip()
        cmd = [paplay]
        if sink:
            cmd += ["--device", sink]
        cmd += [path]
        return run_cmd(cmd, timeout_s=timeout_s, max_chars=2000)

    aplay = shutil.which("aplay")
    if not aplay:
        raise FileNotFoundError("aplay/paplay not found")

    cmd = [aplay]
    if alsa_dev:
        cmd += ["-D", alsa_dev]
    cmd += [path]
    return run_cmd(cmd, timeout_s=timeout_s, max_chars=2000)


def tts_to_wav(*, text: str, out_path: str, lang: str = "en-US") -> Tuple[str, CmdResult, str]:
    """Generate a WAV using pico2wave (default) or espeak."""
    ensure_dir(os.path.dirname(out_path))

    backend = os.environ.get("NAVIS_TTS_BACKEND", "pico2wave").strip().lower()

    if backend == "pico2wave":
        pico2wave = shutil.which("pico2wave")
        if not pico2wave:
            raise FileNotFoundError("pico2wave not found")
        cmd = [pico2wave, "-l", lang, "-w", out_path, text]
        r = run_cmd(cmd, timeout_s=20, max_chars=2000)
        if r.rc != 0:
            raise RuntimeError(f"pico2wave failed rc={r.rc}: {r.out}")
        return out_path, r, backend

    if backend == "espeak":
        espeak = shutil.which("espeak")
        if not espeak:
            raise FileNotFoundError("espeak not found")
        cmd = ["bash", "-lc", f"espeak -w {out_path!s} {text!r}"]
        r = run_cmd(cmd, timeout_s=20, max_chars=2000)
        if r.rc != 0:
            raise RuntimeError(f"espeak failed rc={r.rc}: {r.out}")
        return out_path, r, backend

    raise ValueError(f"Unknown TTS backend: {backend}")


def default_mic_path(paths: AudioPaths) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(paths.audio_dir, f"health-mic-{ts}.wav")


def default_tts_path(paths: AudioPaths) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(paths.audio_dir, f"health-tts-{ts}.wav")
