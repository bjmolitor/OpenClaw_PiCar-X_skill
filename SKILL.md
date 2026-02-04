# OpenClaw Skill Spec (MVP v0.1)

This file defines the **Skill contract** for integrating SunFounder **PiCar‑X v2** as a robot body in OpenClaw.

> Principle: the agent never talks to hardware directly. It calls **deterministic CLI tools** that return **JSON**.

---

## 0) Safety model (non‑negotiable)

### Drive gate
- **Default: NO motion.**
- Any command that can move the robot (drive/steer/head pan/tilt) is blocked unless the human explicitly grants **GO**.
- GO can be implemented as:
  - a short-lived environment flag (e.g. `PICARX_GO=1` for the single command), or
  - a session-scoped memory state with TTL (e.g. 5 min).

### Dead‑man stop
- Every movement command must stop motors at the end (already implemented in `aiagentctrl.py`).
- The agent must call `stop` on uncertainty.

### Clamp & timebox
- Speed and angles are clamped in `aiagentctrl.py` (`PICARX_MAX_SPEED`, `PICARX_MAX_ANGLE`).
- Movement duration should be short by default (`seconds <= 1.0`).

---

## 1) Tool surface (v0.1)

### Primary tool: `aiagentctrl.py`
The CLI is the public interface.

**Invocation**
- Always call from repo root (or installed script `aiagentctrl`).
- Always use `--json`.

**Standard response fields (common)**
Every subcommand returns JSON with at least:
- `ok: bool`
- `cmd: string` (subcommand name)
- `ts: string` (ISO or timestamp)
- `error?: string` (present when ok=false)

> Note: If a field is missing today, we treat it as a follow-up patch; the contract below is the target schema.

---

## 2) Command contracts

### 2.1 `snapshot`
**Purpose:** camera photo without motion.

**Request:**
- `snapshot --path <optional> [--vflip] [--hflip] --json`

**Response (target):**
- `ok: true|false`
- `cmd: "snapshot"`
- `path: string` (file path)
- `backend: "rpicam"|"vilib"|"auto"`
- `width?: int`, `height?: int`
- `took_ms?: int`

**Env knobs:**
- `PICARX_SNAPSHOT_BACKEND=auto|rpicam|vilib`
- `PICARX_RPICAM_ZSL=0|1`
- `PICARX_RPICAM_TIMEOUT_MS`, `PICARX_RPICAM_RETRIES`
- `PICARX_CAMERA_VFLIP`, `PICARX_CAMERA_HFLIP`

---

### 2.2 `ultrasonic`
**Purpose:** distance in cm.

**Request:**
- `ultrasonic --json`

**Response (target):**
- `ok: true|false`
- `cmd: "ultrasonic"`
- `distance_cm: float`

---

### 2.3 `head` (pan/tilt)
**Purpose:** point camera head.

**Safety:** motion-like; requires GO.

**Request:**
- `head [--pan <int>] [--tilt <int>] --json`

**Response (target):**
- `ok`
- `cmd: "head"`
- `pan: int`, `tilt: int`

---

### 2.4 `steer`
**Safety:** requires GO.

**Request:**
- `steer --angle <int> --json`

**Response (target):**
- `ok`
- `cmd: "steer"`
- `angle: int`

---

### 2.5 `drive`
**Safety:** requires GO.

**Request:**
- `drive --speed <int> --seconds <float> --direction forward|backward --json`

**Response (target):**
- `ok`
- `cmd: "drive"`
- `speed: int`
- `seconds: float`
- `direction: string`

---

### 2.6 `stop`
**Purpose:** emergency stop.

**Request:**
- `stop --json`

**Response (target):**
- `ok`
- `cmd: "stop"`

---

## 3) OpenClaw integration spec

### 3.1 Skill wrapper (recommended)
Provide an OpenClaw Skill wrapper that:
- exposes tools in a single namespace (e.g. `picarx.snapshot`, `picarx.ultrasonic`, …)
- enforces GO gate (blocks motion commands without GO)
- converts outputs to consistent JSON schema (above)

### 3.2 Conversation + cross-channel context (adjacent system)
Not implemented inside this repo, but required for the robot body experience:
- Voice wake + multi-turn conversation mode.
- Short-term cross-channel memory file (last 60 min) injected into voice agent at conversation start.

---

## 4) Diagnostics (v0.1)

Add a lightweight `status`/`diag` command (can be a separate script) returning:
- `audio_out: ok|unknown`
- `mic_in: ok|unknown`
- `camera: ok|degraded`
- `battery: percent|unknown` (battery optional; best effort)

---

## 5) MVP acceptance criteria

v0.1 is acceptable when:
- `snapshot --json` works reliably and returns a path.
- `ultrasonic --json` returns a numeric distance.
- `stop` works.
- All movement commands are clamped and stop automatically.
- GO gate exists in the OpenClaw wrapper/prompt rules.

