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
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None

from checks.media.audio import AudioPaths, _enable_robot_hat_speaker_best_effort, _set_speaker_volume_best_effort
from checks.media.common import CmdResult, ensure_dir, run_cmd


@dataclass
class SoundcheckConfig:
    rate: int = 16000
    seconds: float = 4.0
    freqs: Tuple[int, ...] = (220, 440, 880, 1760)
    max_lag_s: float = 0.80
    min_corr: float = 0.05


def _norm_text(s: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", (s or "").lower()).split())


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


def _default_vosk_model_dir() -> str:
    env = os.environ.get("NAVIS_VOSK_MODEL_DIR", "").strip()
    if env:
        return env
    candidates = [
        "/home/admin/.openclaw/workspace/models/vosk-model-small-de-0.15",
        "/home/admin/picar-x/OpenClaw_PiCar-X_skill/models/vosk-model-small-de-0.15",
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


def _synth_activation_ref(path: str, text: str) -> Dict:
    pico2wave = __import__("shutil").which("pico2wave")
    if not pico2wave:
        raise FileNotFoundError("pico2wave not found")
    # Prefer German voice for Navis wake phrase context.
    cmd = [pico2wave, "-l", "de-DE", "-w", path, text]
    p = run_cmd(cmd, timeout_s=12, max_chars=2000)
    if p.rc != 0:
        raise RuntimeError(f"pico2wave failed rc={p.rc}: {p.out}")
    return {"cmd": cmd, "rc": p.rc, "out": p.out}


def _play_and_record(ref_path: str, rec_path: str, *, rate: int, seconds: float, mic_device: str, spk_device: str) -> Dict:
    import shutil
    import subprocess
    import time

    arecord_exe = shutil.which("arecord")
    if not arecord_exe:
        raise FileNotFoundError("arecord not found")
    aplay_exe = shutil.which("aplay")
    if not aplay_exe:
        raise FileNotFoundError("aplay not found")

    arecord_cmd = [arecord_exe]
    if mic_device:
        arecord_cmd += ["-D", mic_device]
    dur_s = max(1, int(round(float(seconds) + 0.3)))
    arecord_cmd += ["-f", "S16_LE", "-r", str(rate), "-c", "1", "-d", str(dur_s), rec_path]

    aplay_cmd = [aplay_exe]
    if spk_device:
        aplay_cmd += ["-D", spk_device]
    aplay_cmd += [ref_path]

    arec = subprocess.Popen(arecord_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(0.12)
    play_res = run_cmd(aplay_cmd, timeout_s=int(dur_s) + 20, max_chars=2000)
    out_arec, _ = arec.communicate(timeout=int(dur_s) + 25)

    return {
        "arecord_cmd": arecord_cmd,
        "arecord_rc": arec.returncode,
        "arecord_out": (out_arec or "").strip()[:2000],
        "aplay_cmd": aplay_cmd,
        "aplay_rc": play_res.rc,
        "aplay_out": (play_res.out or "").strip()[:2000],
    }


def _vosk_text_from_wav(wav_path: str, model_dir: str, expected_phrases: List[str]) -> str:
    import json
    import wave
    from vosk import KaldiRecognizer, Model as VoskModel, SetLogLevel

    if not os.path.isdir(model_dir):
        raise FileNotFoundError(f"Vosk model missing: {model_dir}")

    with wave.open(wav_path, "rb") as wf:
        rate = wf.getframerate()
        if wf.getnchannels() != 1:
            raise RuntimeError("Vosk check requires mono WAV")
        SetLogLevel(-1)
        model = VoskModel(model_dir)
        try:
            rec = KaldiRecognizer(model, rate, json.dumps(expected_phrases, ensure_ascii=False))
        except Exception:
            rec = KaldiRecognizer(model, rate)
        rec.SetWords(False)
        best_partial = ""
        while True:
            data = wf.readframes(4000)
            if not data:
                break
            rec.AcceptWaveform(data)
            try:
                p = json.loads(rec.PartialResult() or "{}")
                pt = _norm_text(p.get("partial", "") or "")
                if len(pt) > len(best_partial):
                    best_partial = pt
            except Exception:
                pass
        try:
            r = json.loads(rec.FinalResult() or "{}")
        except Exception:
            r = {}
    final_text = _norm_text(r.get("text", "") or "")
    return final_text or best_partial


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
    _set_speaker_volume_best_effort(device=spk_device)

    dev = mic_device or os.environ.get("NAVIS_MIC_DEVICE", "").strip() or "plughw:3,0"
    spk = spk_device or os.environ.get("NAVIS_SPK_DEVICE", "").strip() or "plughw:2,0"

    evidence_cmds = []

    # Best-effort: stop listener to avoid "device busy".
    evidence_cmds.append(run_cmd(["bash", "-lc", "systemctl --user stop navis-listen.service 2>/dev/null || true"], timeout_s=6, max_chars=1000))

    # Launch arecord in background, then play.
    tone_io = _play_and_record(ref_path, rec_path, rate=cfg.rate, seconds=cfg.seconds, mic_device=dev, spk_device=spk)

    # Ensure recording exists
    if not os.path.exists(rec_path) or os.path.getsize(rec_path) == 0:
        raise RuntimeError(f"arecord produced no file rc={tone_io['arecord_rc']} out={tone_io['arecord_out']}")

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

    tone_ok = bool(abs(best) >= cfg.min_corr) and bool(rms_rec > 0.005)

    # Wakeword verification: synthesize activation phrase, record loopback, then run Vosk decode.
    # Default wake phrases (baseline): Navis 01 / Navis null eins
    wake_phrases_raw = os.environ.get("NAVIS_WAKE_PHRASES") or os.environ.get(
        "NAVIS_WAKE_PHRASE",
        "navis 01,navis null eins,navis null 1,navis eins",
    )
    wake_phrases = [_norm_text(x) for x in wake_phrases_raw.split(",") if _norm_text(x)]
    if not wake_phrases:
        wake_phrases = ["navis"]
    activation_text = wake_phrases[0]
    wake_ref_path = os.path.join(workspace, "audio", f"soundcheck-wake-ref-{datetime.now().strftime('%Y%m%d-%H%M%S')}.wav")
    wake_rec_path = os.path.join(workspace, "audio", f"soundcheck-wake-rec-{datetime.now().strftime('%Y%m%d-%H%M%S')}.wav")

    wake_tts = _synth_activation_ref(wake_ref_path, activation_text)
    wake_seconds = 2.0
    try:
        import wave as _wave
        with _wave.open(wake_ref_path, "rb") as wf:
            wake_seconds = max(1.2, float(wf.getnframes()) / float(max(1, wf.getframerate())))
    except Exception:
        pass

    wake_io = _play_and_record(wake_ref_path, wake_rec_path, rate=cfg.rate, seconds=wake_seconds, mic_device=dev, spk_device=spk)
    if not os.path.exists(wake_rec_path) or os.path.getsize(wake_rec_path) == 0:
        raise RuntimeError(f"wake arecord produced no file rc={wake_io['arecord_rc']} out={wake_io['arecord_out']}")

    vosk_model_dir = _default_vosk_model_dir()
    heard_text = _vosk_text_from_wav(wake_rec_path, vosk_model_dir, wake_phrases)
    wake_ok = bool(heard_text and any(wp in heard_text for wp in wake_phrases))
    ok = bool(tone_ok and wake_ok)

    # Best-effort: restart listener after the full check sequence.
    evidence_cmds.append(run_cmd(["bash", "-lc", "systemctl --user start navis-listen.service 2>/dev/null || true"], timeout_s=6, max_chars=1000))

    return {
        "ok": ok,
        "action": "soundcheck",
        "speaker_enabled": bool(os.environ.get("NAVIS_ENABLE_ROBOT_HAT_SPEAKER")),
        "spk_device": spk or None,
        "mic_device": dev or None,
        "ref": {"path": ref_path, "rate": cfg.rate, "seconds": cfg.seconds, "freqs": list(cfg.freqs)},
        "rec": {"path": rec_path},
        "wake_ref": {"path": wake_ref_path, "text": activation_text},
        "wake_rec": {"path": wake_rec_path},
        "metrics": {
            "corr_peak": best,
            "corr_lag_s": best_lag / float(cfg.rate),
            "rms_ref": rms_ref,
            "rms_rec": rms_rec,
            "min_corr": cfg.min_corr,
            "max_lag_s": cfg.max_lag_s,
            "tone_ok": tone_ok,
            "wake_ok": wake_ok,
            "wake_heard_text": heard_text,
            "wake_expected_phrases": wake_phrases,
            "wake_vosk_model_dir": vosk_model_dir,
        },
        "evidence": {
            "commands": [
                *[{"cmd": c.cmd, "rc": c.rc, "out": c.out} for c in evidence_cmds],
                {"cmd": tone_io["arecord_cmd"], "rc": tone_io["arecord_rc"], "out": tone_io["arecord_out"]},
                {"cmd": tone_io["aplay_cmd"], "rc": tone_io["aplay_rc"], "out": tone_io["aplay_out"]},
                {"cmd": wake_tts["cmd"], "rc": wake_tts["rc"], "out": wake_tts["out"]},
                {"cmd": wake_io["arecord_cmd"], "rc": wake_io["arecord_rc"], "out": wake_io["arecord_out"]},
                {"cmd": wake_io["aplay_cmd"], "rc": wake_io["aplay_rc"], "out": wake_io["aplay_out"]},
            ]
        },
    }
