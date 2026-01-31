# aiagentctrl: Agent-Friendly PiCar-X Controller

SPDX-License-Identifier: GPL-2.0-or-later

What it is
- A single‑file CLI for SunFounder PiCar‑X v2.0 (robot_hat), to drive, steer, move the camera head (pan/tilt), read ultrasonic distance, capture camera snapshots, and stop.
- Outputs a one‑line dict by default or exact JSON with `--json`.

Prereqs
- v2.0 stack: uses `robot_hat` (I2C at 0x14 on bus 1) and `vilib` for camera.
- Run from repo root or install editable: `python3 -m pip install -e . --break-system-packages`.
- If not installing, prefix examples/CLI with `PYTHONPATH=.`.

Safety notes
- Motors always stop after each command (dead‑man stop), and on Ctrl‑C/SIGTERM.
- Values are clamped: speed ≤ `PICARX_MAX_SPEED` (default 60), angles within ±`PICARX_MAX_ANGLE` (default 35°).
- For any live tests, keep speed ≤ 35 and duration ≤ 1.0 s.

Command reference
- `drive --speed <int> --seconds <float, default 0.0> --direction {forward,backward}`
  - Speed is clamped to `0..PICARX_MAX_SPEED`.
  - Duration 0.0 returns immediately; motors still stop on command exit.
- `steer --angle <int>`
  - Angle clamped to `[-PICARX_MAX_ANGLE, PICARX_MAX_ANGLE]`.
- `head --pan <int?> --tilt <int?>`
  - Each angle clamped to `[-PICARX_MAX_ANGLE, PICARX_MAX_ANGLE]`.
  - Immediate movement; position persists until changed again (e.g., `--pan 0 --tilt 0`).
- `ultrasonic`
  - Prints distance in centimeters as `distance_cm`.
- `stop`
  - Immediately stops motors.
- `snapshot [--path <file>] [--vflip] [--hflip]`
  - Captures one image.
  - **Backend:** prefers `rpicam-still` / `libcamera-still` when available (recommended on Raspberry Pi 5); otherwise falls back to `vilib`.
  - Control via env `PICARX_SNAPSHOT_BACKEND=auto|rpicam|vilib`.
  - Default path: `aiagent_camera/snap-<timestamp>.jpg` (auto-created).

Environment variables
- `PICARX_MAX_SPEED` (default 60): speed clamp for `drive`.
- `PICARX_MAX_ANGLE` (default 35): clamp for steering and pan/tilt.
- `PICARX_I2C_BUS` (default 1 on v2): override I2C bus.
- `PICARX_PREFER_LOCAL` (default `1`): set `0` to prefer site‑installed module.
- `PICARX_MODULE_DIR`: prepend a specific path to import (`v2.0` checkout, etc.).
- `PICARX_STATE_FILE`: file to persist head state (default `/opt/picar-x/aiagentctrl_state.json`).

Snapshot (rpicam/libcamera) tuning
- `PICARX_SNAPSHOT_BACKEND=auto|rpicam|vilib`
- `PICARX_CAMERA_TIMEOUT` (seconds, default `3.0`): overall timeout for snapshot actions.
- `PICARX_CAMERA_WARMUP` (seconds, default `0.15`): warmup for `vilib` backend.
- `PICARX_RPICAM_TIMEOUT_MS` (default `800`): rpicam capture time.
- `PICARX_RPICAM_VERBOSE=0|1|2` (default `0`): rpicam verbosity.
- `PICARX_CAMERA_INDEX` (optional): select camera index for rpicam.
- `PICARX_RPICAM_ZSL=0|1` (default: **enabled**): reduces libcamera warnings and improves timing.
- `PICARX_RPICAM_RETRIES=0..3` (default `1`): retries on transient failures.
- `PICARX_CAMERA_VFLIP=0|1`, `PICARX_CAMERA_HFLIP=0|1` (defaults `0`): default flips.

Examples (v2)
- Plain shell
  - `python3 aiagentctrl.py --help`
  - `PICARX_PREFER_LOCAL=1 PICARX_I2C_BUS=1 python3 aiagentctrl.py drive --speed 30 --seconds 0.5 --direction forward --json`
  - `python3 aiagentctrl.py head --pan -12 --tilt 7 --json`  # smooth move and persist
  - `python3 aiagentctrl.py snapshot --path /home/admin/Pictures/test.jpg --json`
  - `PICARX_RPICAM_RETRIES=2 PICARX_RPICAM_TIMEOUT_MS=1200 python3 aiagentctrl.py snapshot --json`

Troubleshooting
- Import path: install editable or prefix with `PYTHONPATH=.` from repo root.
- Ultrasonic: if returning negative/erratic, check sensor cabling and `robot_hat` I2C on bus 1.
- Camera:
  - If snapshot hangs/fails, try forcing backend: `PICARX_SNAPSHOT_BACKEND=rpicam`.
  - If image is upside-down, set `PICARX_CAMERA_VFLIP=1` and/or `PICARX_CAMERA_HFLIP=1`.
  - If transient failures occur, raise `PICARX_RPICAM_RETRIES` and/or `PICARX_RPICAM_TIMEOUT_MS`.
- Motors keep running? Use `python3 aiagentctrl.py stop` or Ctrl‑C; the controller also stops on any error.
