#!/usr/bin/env python3
"""Navis 01: Wake-word + VAD listen daemon (NO MOTION).

Goal
- Offline wake-word-ish detection (keyword spotting) using Vosk (German model).
- After wake trigger: beep, then record until 3s of silence (VAD), save wav.
- Transcribe via OpenAI (default) using navis_media.py stt.
- Speak a short acknowledgement / (optionally) echo transcript using navis_media.py speak.

Notes
- This is an MVP, tuned for home use.
- Wake detection here is implemented as lightweight offline recognition over a short buffer.
  It is not a trained wake-word model, but works well for a unique keyword like "Navis".

Env
- NAVIS_WAKE_PHRASE="navis" (default) or "navis 01"
- NAVIS_VOSK_MODEL_DIR=... (default: ./models/vosk-model-small-de-0.15)
- NAVIS_ARECORD_DEVICE=default (optional)
- NAVIS_SAMPLE_RATE (default 16000)
- NAVIS_SILENCE_SECONDS (default 3.0)
- NAVIS_VAD_MODE (0-3, default 2)

Run
  ./navis_listen_daemon.py --once
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import wave
import shutil

import numpy as np
import webrtcvad

BASE = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.path.join(BASE, "navis_media.py")

# Cross-channel short-term memory log (last hour)
SHORTTERM_LOG = os.path.join(BASE, "logs", "conversation_shortterm.jsonl")
VOICE_FORMAT_INSTRUCTION_STATE = os.path.join(BASE, "logs", "voice-format-instruction.state.json")


def _norm(s: str) -> str:
    return " ".join((s or "").lower().strip().split())


def _is_filtered_stt_text(text_norm: str) -> bool:
    """Filter known recurring subtitle/noise phrases from STT.

    Rationale: Vosk (and sometimes other STT paths) may hallucinate subtitle credits from noise.
    We treat any transcript that *starts with* "Untertitel" as a false-positive.
    """
    if not text_norm:
        return False

    # Robust normalize for hard filtering (ignore punctuation/extra whitespace).
    cleaned = _norm(re.sub(r"[^\w\s]", " ", text_norm))

    # Broad class filter: "Untertitel ..."
    if cleaned.startswith("untertitel ") or cleaned == "untertitel":
        return True

    # Legacy exact phrases (kept for clarity / regression)
    blocked = [
        "untertitel der amara org community",
        "untertitel von amara org",
        "untertitel im auftrag des zdf fur funk 2017",
    ]
    return any(p in cleaned for p in blocked)


def _sanitize_voice_reply(text: str) -> str:
    """Convert model output to plain speakable text (no markdown/code/links/paths)."""
    s = (text or "").strip()
    if not s:
        return ""
    s = re.sub(r"```.*?```", " ", s, flags=re.DOTALL)
    s = re.sub(r"`[^`]*`", " ", s)
    s = re.sub(r"\[([^\]]+)\]\((?:https?://|www\.)[^)]+\)", r"\1", s)
    s = re.sub(r"https?://\S+|www\.\S+", " ", s)
    s = re.sub(r"(?im)^\s*#{1,6}\s*", "", s)
    s = re.sub(r"(?im)^\s*[-*+]\s+", "", s)
    s = re.sub(r"(?im)^\s*\d+\.\s+", "", s)
    s = re.sub(r"\b(?:[A-Za-z]:\\|/)?(?:[\w.\-]+/)+[\w.\-]+\b", " ", s)
    s = re.sub(r"[*_~>\[\]{}|]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _today_local_iso() -> str:
    # Local calendar day is enough for "once per day" gating.
    return time.strftime("%Y-%m-%d")


def _should_append_voice_instruction(session_id: str) -> bool:
    """Return True if instruction should be appended for this session today.

    Persists decision so restarts do not resend on the same day.
    """
    today = _today_local_iso()
    data = {"sessions": {}}

    try:
        if os.path.exists(VOICE_FORMAT_INSTRUCTION_STATE):
            with open(VOICE_FORMAT_INSTRUCTION_STATE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
    except Exception:
        data = {"sessions": {}}

    sessions = data.get("sessions")
    if not isinstance(sessions, dict):
        sessions = {}
        data["sessions"] = sessions

    if sessions.get(session_id) == today:
        return False

    sessions[session_id] = today
    try:
        os.makedirs(os.path.dirname(VOICE_FORMAT_INSTRUCTION_STATE), exist_ok=True)
        tmp = VOICE_FORMAT_INSTRUCTION_STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, VOICE_FORMAT_INSTRUCTION_STATE)
    except Exception:
        # Even if persist fails, keep behavior functional for this turn.
        pass

    return True


def _beep(ms: int = 200, hz: int = 880):
    # use navis_media speak with a short clicky syllable? better: speaker-test is heavy.
    # We generate a sine wave wav and aplay it via navis_media play (ensures speaker enabled).
    tmp = "/tmp/navis_beep.wav"
    sr = 16000
    dur = max(0.05, min(2.0, ms / 1000.0))
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    x = (0.25 * np.sin(2 * np.pi * hz * t)).astype(np.float32)
    # 16-bit PCM
    pcm = (x * 32767).astype(np.int16).tobytes()
    with wave.open(tmp, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm)

    subprocess.run([sys.executable, MEDIA, "play", "--path", tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _run_media(*args) -> dict:
    p = subprocess.run([sys.executable, MEDIA, *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=240)
    out = (p.stdout or "").strip()
    # navis_media prints JSON
    try:
        res = json.loads(out)
        if isinstance(res, dict):
            res["_rc"] = p.returncode
            return res
    except Exception:
        pass
    return {"ok": p.returncode == 0, "_rc": p.returncode, "log": out}


def _write_voice_shortterm_md(convo_id: str, max_items: int = 30, max_chars: int = 2500) -> None:
    """Render last-hour short-term memory into the navis-voice workspace.

    This lets the voice agent see cross-channel context without relying on WhatsApp history.
    We keep it small to avoid prompt bloat.
    """
    voice_ws = os.environ.get("NAVIS_VOICE_WORKSPACE", "/home/admin/.openclaw/agents/navis-voice/workspace")
    out_path = os.path.join(voice_ws, "SHORTTERM.md")

    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Europe/Berlin")
        now = datetime.now(tz)
        cutoff = now.timestamp() - 3600

        items = []
        if os.path.exists(SHORTTERM_LOG):
            with open(SHORTTERM_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue

                    # parse timestamp (best effort)
                    t = None
                    ts_iso = o.get("ts_iso")
                    ts = o.get("ts")
                    if ts_iso:
                        try:
                            t = datetime.fromisoformat(ts_iso).timestamp()
                        except Exception:
                            t = None
                    if t is None and ts:
                        try:
                            t = datetime.strptime(ts, "%Y%m%d-%H%M%S").replace(tzinfo=tz).timestamp()
                        except Exception:
                            t = None

                    if t is not None and t < cutoff:
                        continue

                    items.append(o)

        items = items[-max_items:]

        lines = [
            "# SHORTTERM (letzte 60 Minuten)",
            f"Aktualisiert: {now.isoformat()}",
            f"Voice convo_id: {convo_id}",
            "",
        ]

        for o in items:
            ch = o.get("channel", "?")
            direction = o.get("direction")
            prefix = f"[{ch}{'/' + direction if direction else ''}]"

            text = ""
            if ch == "voice":
                heard = (o.get("heard") or "").strip()
                said = (o.get("said") or "").strip()
                if heard:
                    text += f"U: {heard} "
                if said:
                    text += f"N: {said}"
            else:
                body = (o.get("text") or "").strip()
                if body:
                    text = body

            text = " ".join(text.split())
            if not text:
                continue
            lines.append(f"- {prefix} {text}")

        content = "\n".join(lines).strip() + "\n"
        if len(content) > max_chars:
            content = content[-max_chars:]
            # keep a clean start
            content = "# SHORTTERM (letzte 60 Minuten)\n…\n" + content

        os.makedirs(voice_ws, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        # Never break the voice loop if shortterm rendering fails.
        return


def _run_openclaw_agent(text: str) -> tuple[str, bool]:
    """Run one OpenClaw agent turn via CLI.

    Returns:
    - reply text
    - agent_error flag (True if the agent call failed)
    """
    session_id = os.environ.get("NAVIS_OPENCLAW_SESSION_ID", "navis-voice")
    agent_id = os.environ.get("NAVIS_OPENCLAW_AGENT")  # optional (recommended)
    thinking = os.environ.get("NAVIS_OPENCLAW_THINKING", "low")
    timeout_s = int(os.environ.get("NAVIS_OPENCLAW_TIMEOUT", "30"))
    openclaw_bin = os.environ.get("NAVIS_OPENCLAW_BIN", "openclaw")
    openclaw_node = os.environ.get("NAVIS_OPENCLAW_NODE")  # optional: force a specific node binary

    # Prefer calling via a fixed node binary only when the OpenClaw entrypoint is a JS file.
    # If `openclaw_bin` is a shell wrapper, execute it directly.
    openclaw_real = os.path.realpath(openclaw_bin)
    if openclaw_node and openclaw_real.endswith((".js", ".mjs")):
        cmd = [openclaw_node, openclaw_real, "agent"]
    else:
        cmd = [openclaw_bin, "agent"]
    if agent_id:
        cmd += ["--agent", agent_id]

    voice_message = f"[VOICE_INPUT]\n{text}"
    if _should_append_voice_instruction(session_id):
        voice_message += (
            "\n\n"
            "WICHTIG: Antworte fuer Voice-Ausgabe ausschliesslich als Klartext in 1-4 ganzen Saetzen. "
            "Kein Markdown. Keine Listen. Keine Aufzaehlungen. Keine Zwischenueberschriften. "
            "Kein Quellcode. Keine Dateinamen. Keine Links."
        )

    cmd += [
        "--session-id",
        session_id,
        "--message",
        voice_message,
        "--json",
        "--thinking",
        thinking,
        "--timeout",
        str(timeout_s),
    ]

    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout_s + 10)
        raw = (p.stdout or "").strip()
        if p.returncode != 0:
            print(f"[navis_listen] openclaw rc={p.returncode} out={raw[:500]}", flush=True)
            try:
                with open("/tmp/navis_openclaw_last_error.log", "w", encoding="utf-8") as f:
                    f.write(raw)
            except Exception:
                pass
            return "Entschuldigung, mein Agent ist gerade nicht erreichbar.", True

        # The CLI sometimes prints non-JSON warnings (e.g. version/config notices).
        # Extract the last JSON object from stdout and parse that.
        data = None
        try:
            data = json.loads(raw)
        except Exception:
            # try to salvage JSON payload from mixed stdout
            import re

            m = re.search(r"(\{.*\})", raw, flags=re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                except Exception:
                    data = None

        if data is None:
            try:
                with open("/tmp/navis_openclaw_last_error.log", "w", encoding="utf-8") as f:
                    f.write(raw)
            except Exception:
                pass
            raise json.JSONDecodeError("invalid JSON from openclaw", raw, 0)

        payloads = (((data or {}).get("result") or {}).get("payloads") or [])
        parts = [pp.get("text") for pp in payloads if isinstance(pp, dict) and pp.get("text")]
        reply = "\n".join(parts).strip()
        reply = _sanitize_voice_reply(reply)
        if not reply:
            return "Ich weiß gerade nicht, was ich sagen soll.", False
        return reply, False
    except FileNotFoundError:
        print(f"[navis_listen] openclaw binary not found: {openclaw_bin}", flush=True)
        return "Entschuldigung, mein Agent ist gerade nicht verfügbar.", True
    except Exception as e:
        print(f"[navis_listen] openclaw call failed: {type(e).__name__}: {e}", flush=True)
        return "Entschuldigung, ich hatte gerade ein Problem mit meinem Agenten.", True


def record_until_silence(read_bytes, sr: int, silence_s: float, vad_mode: int, start_timeout_s: float = 8.0) -> bytes:
    """Read PCM16 mono from read_bytes() until we detect speech, then stop after N seconds of silence.

    If no speech starts within start_timeout_s, returns b"".
    """
    vad = webrtcvad.Vad(vad_mode)
    frame_ms = 30
    frame_len = int(sr * frame_ms / 1000)
    bytes_per_frame = frame_len * 2  # int16 mono

    buf = bytearray()
    silence_frames_needed = int((silence_s * 1000) / frame_ms)
    silence = 0
    started = False
    start_deadline = time.time() + float(start_timeout_s)

    pending = bytearray()
    while True:
        chunk = read_bytes()
        if chunk:
            pending.extend(chunk)
        else:
            if time.time() > start_deadline and not started:
                break
            continue

        while len(pending) >= bytes_per_frame:
            frame = bytes(pending[:bytes_per_frame])
            del pending[:bytes_per_frame]
            is_speech = vad.is_speech(frame, sr)
            if is_speech:
                started = True
                silence = 0
            else:
                if started:
                    silence += 1

            if started:
                buf.extend(frame)

            if started and silence >= silence_frames_needed:
                return bytes(buf)

    return b"" if not started else bytes(buf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="Run one interaction then exit")
    args = ap.parse_args()

    # Wake phrases: comma-separated list. We match against Vosk text (normalized, punctuation-stripped).
    # The German Vosk model often mis-transcribes "Navis" as e.g. "na bis".
    wake_phrases_raw = os.environ.get("NAVIS_WAKE_PHRASES") or os.environ.get("NAVIS_WAKE_PHRASE", "navis")
    wake_phrases = [
        _norm(x)
        for x in (wake_phrases_raw or "").split(",")
        if _norm(x)
    ]
    if not wake_phrases:
        wake_phrases = ["navis"]
    # keep a single representative for legacy fields / logs
    wake_phrase = wake_phrases[0]
    model_dir = os.environ.get("NAVIS_VOSK_MODEL_DIR", os.path.join(BASE, "models", "vosk-model-small-de-0.15"))
    sr = int(os.environ.get("NAVIS_SAMPLE_RATE", "16000"))
    silence_s = float(os.environ.get("NAVIS_SILENCE_SECONDS", "3.0"))
    vad_mode = int(os.environ.get("NAVIS_VAD_MODE", "2"))
    arecord_dev = os.environ.get("NAVIS_ARECORD_DEVICE", "default")
    print(f"[navis_listen] wake_engine=vosk wake_phrases={wake_phrases} sr={sr} silence_s={silence_s} vad={vad_mode}")

    try:
        from vosk import Model as VoskModel, KaldiRecognizer
    except Exception as e:
        raise SystemExit(f"vosk not available: {type(e).__name__}: {e}")

    if not os.path.isdir(model_dir):
        raise SystemExit(f"Vosk model missing: {model_dir}")

    model = VoskModel(model_dir)

    # Wake detection: constrain recognizer to a small grammar (more robust than free dictation)
    # Vosk grammar is a JSON array of phrases.
    try:
        grammar = json.dumps(wake_phrases, ensure_ascii=False)
        rec = KaldiRecognizer(model, sr, grammar)
    except Exception:
        rec = KaldiRecognizer(model, sr)

    rec.SetWords(False)

    # Read raw PCM from arecord to avoid PortAudio / service device selection issues.
    arecord = shutil.which("arecord")
    if not arecord:
        raise SystemExit("arecord not found")

    cmd = [arecord]
    if arecord_dev and arecord_dev != "default":
        cmd += ["-D", arecord_dev]
    cmd += ["-f", "S16_LE", "-r", str(sr), "-c", "1", "-t", "raw", "-"]

    print(f"[navis_listen] using arecord cmd: {' '.join(cmd)}")

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    assert proc.stdout is not None

    def read_bytes(n=4096):
        try:
            return proc.stdout.read(n)
        except Exception:
            return b""

    # Wake loop
    try:
        debug_wake = str(os.environ.get("NAVIS_WAKE_DEBUG", "0")).strip().lower() in ("1", "true", "yes", "on")
        last_partial_log = 0.0

        text = ""
        # Optional VAD gate for wake (reduces false positives but can be too strict).
        wake_vad_gate = str(os.environ.get("NAVIS_WAKE_VAD_GATE", "1")).strip().lower() in ("1", "true", "yes", "on")

        # If disabled, fall back to the old behavior: feed recognizer continuously.
        if not wake_vad_gate:
            while True:
                chunk = read_bytes(4000)
                if not chunk:
                    time.sleep(0.05)
                    continue

                if debug_wake and (time.time() - last_partial_log) > 1.0:
                    last_partial_log = time.time()
                    try:
                        pr = json.loads(rec.PartialResult() or "{}")
                        pt = _norm(pr.get("partial", "") or "")
                        if pt:
                            print(f"[navis_listen] partial='{pt}'", flush=True)
                            if any(wp in pt for wp in wake_phrases):
                                text = pt
                                break
                    except Exception:
                        pass

                if not rec.AcceptWaveform(chunk):
                    continue

                try:
                    r = json.loads(rec.Result() or "{}")
                except Exception:
                    r = {}

                import re
                text_raw = (r.get("text", "") or "")
                text_candidate = _norm(re.sub(r"[^\w\s]", " ", text_raw))
                if debug_wake:
                    print(f"[navis_listen] final='{text_candidate}'", flush=True)
                if not (text_candidate and any(wp in text_candidate for wp in wake_phrases)):
                    continue
                break

        else:
            # Gate wake recognition through VAD to avoid false positives from keyboard clicks/noise.
            wake_vad_mode = int(os.environ.get("NAVIS_WAKE_VAD_MODE", str(vad_mode)))
            wake_vad = webrtcvad.Vad(wake_vad_mode)
            frame_ms = int(os.environ.get("NAVIS_WAKE_VAD_FRAME_MS", "20"))  # 10/20/30 supported
            frame_bytes = int(sr * (frame_ms / 1000.0)) * 2  # PCM16 mono
            if frame_bytes <= 0:
                frame_bytes = 640

            buf = b""
            speech_active = False
            last_speech_ts = 0.0
            speech_hold_s = float(os.environ.get("NAVIS_WAKE_VAD_HOLD_SECONDS", "0.8"))

            while True:
                chunk = read_bytes(4000)
                if not chunk:
                    time.sleep(0.05)
                    continue

                buf += chunk

                r_ready = None
                got_final = False
                while len(buf) >= frame_bytes:
                    frame = buf[:frame_bytes]
                    buf = buf[frame_bytes:]

                    try:
                        is_speech = wake_vad.is_speech(frame, sr)
                    except Exception:
                        is_speech = True

                    now = time.time()
                    if is_speech:
                        speech_active = True
                        last_speech_ts = now
                    elif speech_active and (now - last_speech_ts) > speech_hold_s:
                        # End of an utterance → finalize recognizer (this is important for short wake words)
                        speech_active = False
                        try:
                            r_ready = json.loads(rec.FinalResult() or "{}")
                        except Exception:
                            r_ready = {}
                        try:
                            rec.Reset()
                        except Exception:
                            pass
                        if (r_ready.get("text") or "").strip():
                            got_final = True
                            break
                        r_ready = None
                        continue

                    if not speech_active:
                        continue

                    # Debug: occasionally log partial hypotheses so we can see what Vosk hears.
                    if debug_wake and (time.time() - last_partial_log) > 1.0:
                        last_partial_log = time.time()
                        try:
                            pr = json.loads(rec.PartialResult() or "{}")
                            pt = _norm(pr.get("partial", "") or "")
                            if pt:
                                print(f"[navis_listen] partial='{pt}'", flush=True)
                        except Exception:
                            pass

                    if rec.AcceptWaveform(frame):
                        got_final = True
                        try:
                            r_ready = json.loads(rec.Result() or "{}")
                        except Exception:
                            r_ready = {}
                        break

                if not got_final:
                    continue

                r = r_ready or {}
                import re
                text_raw = (r.get("text", "") or "")
                text_candidate = _norm(re.sub(r"[^\w\s]", " ", text_raw))
                if debug_wake:
                    print(f"[navis_listen] final='{text_candidate}'", flush=True)
                if not (text_candidate and any(wp in text_candidate for wp in wake_phrases)):
                    continue
                break

        if not text:
            import re
            text_raw = (r.get("text", "") or "")
            text = _norm(re.sub(r"[^\w\s]", " ", text_raw))
            if debug_wake:
                print(f"[navis_listen] final='{text}'", flush=True)

        if text and any(wp in text for wp in wake_phrases):
                    # ACK: beep only (optional). Do NOT speak yet, otherwise we record our own output and STT fails.
                    if str(os.environ.get("NAVIS_ENABLE_BEEP", "1")).strip().lower() in ("1", "true", "yes", "on"):
                        _beep()

                    # Important: the beep can trigger VAD as "speech". Discard a short window after beep
                    # so we don't stop recording before the human starts speaking.
                    try:
                        discard_bytes = int(sr * 0.5) * 2  # 0.5s of PCM16 mono
                        _ = read_bytes(discard_bytes)
                    except Exception:
                        pass

                    ts = time.strftime("%Y%m%d-%H%M%S")
                    out_wav = os.path.join(BASE, "audio", f"listen-{ts}.wav")
                    os.makedirs(os.path.dirname(out_wav), exist_ok=True)

                    # Conversation mode: after wake, keep looping turns until abort/timeout.
                    abort_phrases = [
                        _norm(x)
                        for x in os.environ.get("NAVIS_ABORT_PHRASES", "abbruch,stop,ende,danke das war's").split(",")
                        if _norm(x)
                    ]
                    max_turns = int(os.environ.get("NAVIS_CONVO_MAX_TURNS", "8"))
                    start_timeout_s = float(os.environ.get("NAVIS_CONVO_START_TIMEOUT", "10"))

                    convo_id = time.strftime("%Y%m%d-%H%M%S")

                    # Initialize voice context once per wake with cross-channel short-term log.
                    _write_voice_shortterm_md(convo_id=convo_id)

                    last_say = ""
                    ended_reason = None

                    def _drain_mic_until_empty(max_ms: int | None = None, max_bytes: int | None = None):
                        """Drain buffered mic audio so we don't consume our own TTS on the next turn.

                        We use the beep as the hard boundary: everything between end-of-user-speech and the
                        next beep (listening-on) is thrown away.

                        Implementation: non-blocking drain of the arecord stdout pipe for up to max_ms or max_bytes.
                        """
                        try:
                            import select

                            if max_ms is None:
                                max_ms = int(os.environ.get("NAVIS_CONVO_DRAIN_MAX_MS", "8000"))
                            if max_bytes is None:
                                # allow draining long TTS bursts (up to ~60s audio)
                                max_bytes = int(os.environ.get("NAVIS_CONVO_DRAIN_MAX_BYTES", str(sr * 2 * 60)))

                            fd = proc.stdout.fileno()  # type: ignore
                            drained = 0
                            deadline = time.time() + (max_ms / 1000.0)
                            while drained < max_bytes and time.time() < deadline:
                                r, _, _ = select.select([fd], [], [], 0)
                                if not r:
                                    break
                                chunk = proc.stdout.read(min(16384, max_bytes - drained))  # type: ignore
                                if not chunk:
                                    break
                                drained += len(chunk)
                        except Exception:
                            # Fallback: drain a couple of seconds.
                            try:
                                _ = read_bytes(int(sr * 2.0) * 2)
                            except Exception:
                                pass

                    turn = 0
                    while turn < max_turns:
                        ts = time.strftime("%Y%m%d-%H%M%S")
                        out_wav = os.path.join(BASE, "audio", f"listen-{ts}.wav")
                        os.makedirs(os.path.dirname(out_wav), exist_ok=True)

                        # Before listening for the next user turn, drain any buffered audio so we don't
                        # accidentally start the next turn with our own previous TTS output.
                        _drain_mic_until_empty(max_ms=250, max_bytes=sr * 2 * 2)

                        # Record user's utterance until silence; if no speech starts soon, end convo.
                        audio_bytes = record_until_silence(
                            lambda: read_bytes(4000),
                            sr=sr,
                            silence_s=silence_s,
                            vad_mode=vad_mode,
                            start_timeout_s=start_timeout_s,
                        )
                        if not audio_bytes:
                            ended_reason = "silence_timeout"
                            # Log a convo end marker (no wav/tts)
                            try:
                                os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
                                evt_path = os.path.join(BASE, "logs", "wake-events.jsonl")
                                evt = {
                                    "ts": ts,
                                    "convo_id": convo_id,
                                    "wake_phrase": ",".join(wake_phrases),
                                    "wav": None,
                                    "heard": "",
                                    "said": "",
                                    "turn": turn + 1,
                                    "ended": ended_reason,
                                }
                                with open(evt_path, "a", encoding="utf-8") as f:
                                    f.write(json.dumps(evt, ensure_ascii=False) + "\n")
                            except Exception:
                                pass
                            break

                        with wave.open(out_wav, "wb") as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(sr)
                            wf.writeframes(audio_bytes)

                        # Beep after listening ended (silence timeout)
                        beep_after_listen = str(os.environ.get("NAVIS_BEEP_AFTER_LISTEN", "1")).strip().lower() in (
                            "1",
                            "true",
                            "yes",
                            "on",
                        )
                        if beep_after_listen:
                            end_ms = int(os.environ.get("NAVIS_BEEP_END_MS", "600"))
                            end_hz = int(os.environ.get("NAVIS_BEEP_END_HZ", "660"))
                            _beep(ms=end_ms, hz=end_hz)
                            try:
                                discard_bytes = int(sr * 0.2) * 2
                                _ = read_bytes(discard_bytes)
                            except Exception:
                                pass

                        stt = _run_media("stt", "--path", out_wav, "--backend", "openai", "--language", "de")
                        heard = (stt.get("text") or "").strip()
                        heard_norm = _norm(heard)

                        if _is_filtered_stt_text(heard_norm):
                            try:
                                print(f"[navis_listen] filtered_stt='{heard_norm}'", flush=True)
                            except Exception:
                                pass
                            # Repeat listen cue and wait for a real user utterance without consuming a turn.
                            if str(os.environ.get("NAVIS_ENABLE_BEEP", "1")).strip().lower() in ("1", "true", "yes", "on"):
                                _beep()
                                try:
                                    discard_bytes = int(sr * 0.6) * 2
                                    _ = read_bytes(discard_bytes)
                                except Exception:
                                    pass
                            continue

                        # Abort keyword?
                        if heard_norm and any(p in heard_norm for p in abort_phrases):
                            ended_reason = "abort_phrase"
                            last_say = "Alles klar."
                            tts = _run_media("speak", "--text", last_say)
                            # Convo ends on abort phrase → do NOT beep (beep means "I'm listening now")
                            _drain_mic_until_empty()

                            # Log abort turn
                            try:
                                os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
                                evt_path = os.path.join(BASE, "logs", "wake-events.jsonl")
                                evt = {
                                    "ts": ts,
                                    "convo_id": convo_id,
                                    "wake_phrase": ",".join(wake_phrases),
                                    "wav": out_wav,
                                    "heard": heard,
                                    "stt": {k: stt.get(k) for k in ("ok", "rc", "backend", "model", "language", "error") if k in stt},
                                    "said": last_say,
                                    "tts": {k: tts.get(k) for k in ("ok", "backend", "device") if k in tts},
                                    "turn": turn + 1,
                                    "ended": ended_reason,
                                }
                                with open(evt_path, "a", encoding="utf-8") as f:
                                    f.write(json.dumps(evt, ensure_ascii=False) + "\n")
                            except Exception:
                                pass

                            break

                        # Decide response
                        turn += 1
                        model_end_flag = False

                        if not heard:
                            last_say = "Ich habe nichts verstanden."
                        else:
                            last_say, agent_error = _run_openclaw_agent(heard)

                            # Model-driven end-of-convo flag
                            end_token = os.environ.get("NAVIS_END_TOKEN", "[[END_CONVO]]")
                            if end_token and end_token in last_say:
                                model_end_flag = True
                                last_say = last_say.replace(end_token, "").strip()
                            if agent_error:
                                model_end_flag = True

                            # Keep TTS responses speakable / short.
                            max_chars = int(os.environ.get("NAVIS_TTS_MAX_CHARS", "0"))
                            if max_chars > 0 and len(last_say) > max_chars:
                                last_say = last_say[: max_chars - 1].rstrip() + "…"

                        tts_timeout_s = int(os.environ.get("NAVIS_TTS_TIMEOUT", "90"))
                        tts = _run_media("speak", "--text", last_say, "--timeout", str(tts_timeout_s))

                        # Hard boundary: throw away anything captured while we were speaking/thinking.
                        # Then (and only then) beep + continue listening.
                        _drain_mic_until_empty()

                        # Optional end-of-turn beep.
                        # Default is off so each new user input requires a fresh wake word.
                        beep_after_response = str(os.environ.get("NAVIS_BEEP_AFTER_RESPONSE", "0")).strip().lower() in (
                            "1",
                            "true",
                            "yes",
                            "on",
                        )
                        if beep_after_response and not model_end_flag:
                            end_ms = int(os.environ.get("NAVIS_BEEP_END_MS", "600"))
                            end_hz = int(os.environ.get("NAVIS_BEEP_END_HZ", "660"))
                            _beep(ms=end_ms, hz=end_hz)
                            try:
                                discard_bytes = int(sr * 0.6) * 2
                                _ = read_bytes(discard_bytes)
                            except Exception:
                                pass

                        # Journal line for debugging (no secrets)
                        try:
                            print(
                                f"[navis_listen] turn={turn}/{max_turns} ts={ts} heard='{heard}' stt_ok={stt.get('ok')} rc={stt.get('rc')}",
                                flush=True,
                            )
                        except Exception:
                            pass

                        # Append event log for WhatsApp notification
                        try:
                            os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
                            evt_path = os.path.join(BASE, "logs", "wake-events.jsonl")
                            evt = {
                                "ts": ts,
                                "convo_id": convo_id,
                                "wake_phrase": ",".join(wake_phrases),
                                "wav": out_wav,
                                "heard": heard,
                                "stt": {k: stt.get(k) for k in ("ok", "rc", "backend", "model", "language", "error") if k in stt},
                                "said": last_say,
                                "tts": {k: tts.get(k) for k in ("ok", "backend", "device") if k in tts},
                                "turn": turn,
                                "model_end": bool(model_end_flag),
                            }
                            with open(evt_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps(evt, ensure_ascii=False) + "\n")
                        except Exception:
                            pass

                        # Short-term cross-channel conversation log (1h window maintained by a separate job)
                        try:
                            st_path = os.path.join(BASE, "logs", "conversation_shortterm.jsonl")
                            st_evt = {
                                "ts": ts,
                                "channel": "voice",
                                "convo_id": convo_id,
                                "turn": turn,
                                "heard": heard,
                                "said": last_say,
                                "ended": "model_intent" if model_end_flag else None,
                            }
                            with open(st_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps(st_evt, ensure_ascii=False) + "\n")
                        except Exception:
                            pass

                        # If model asked to end convo, stop after speaking.
                        if model_end_flag:
                            ended_reason = "agent_error" if "problem mit meinem agenten" in _norm(last_say) else "model_intent"
                            try:
                                os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
                                evt_path = os.path.join(BASE, "logs", "wake-events.jsonl")
                                evt = {
                                    "ts": time.strftime("%Y%m%d-%H%M%S"),
                                    "convo_id": convo_id,
                                    "wake_phrase": ",".join(wake_phrases),
                                    "wav": None,
                                    "heard": "",
                                    "said": "",
                                    "turn": turn,
                                    "ended": ended_reason,
                                }
                                with open(evt_path, "a", encoding="utf-8") as f:
                                    f.write(json.dumps(evt, ensure_ascii=False) + "\n")
                            except Exception:
                                pass
                            break

                    # If we hit the safety cap, log an explicit end marker.
                    if ended_reason is None:
                        ended_reason = "max_turns" if max_turns > 0 else "ended"
                        try:
                            os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
                            evt_path = os.path.join(BASE, "logs", "wake-events.jsonl")
                            evt = {
                                "ts": time.strftime("%Y%m%d-%H%M%S"),
                                "convo_id": convo_id,
                                "wake_phrase": ",".join(wake_phrases),
                                "wav": None,
                                "heard": "",
                                "said": "",
                                "turn": max_turns,
                                "ended": ended_reason,
                            }
                            with open(evt_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps(evt, ensure_ascii=False) + "\n")
                        except Exception:
                            pass

                    # Reset recognizer state after convo so wake detection doesn't trip on buffered audio.
                    try:
                        rec.Reset()
                    except Exception:
                        pass

                    # Journal line for debugging (no secrets)
                    try:
                        print(f"[navis_listen] wake ts={ts} heard='{heard}' stt_ok={stt.get('ok')} rc={stt.get('rc')}")
                    except Exception:
                        pass

                    if args.once:
                        return

    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    main()
