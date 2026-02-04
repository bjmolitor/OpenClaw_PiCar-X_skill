# OpenClaw PiCar-X Skill (SunFounder)

A minimal, agent-friendly control surface for the **SunFounder PiCar‑X v2.0** so OpenClaw (and other agents) can use it as a robot body.

This repo intentionally keeps the control interface **deterministic** and **machine-readable**.

## What you get (MVP)

- `aiagentctrl.py` — a single-file CLI that controls:
  - drive / steer
  - camera head pan/tilt
  - ultrasonic distance
  - camera snapshot
  - stop (emergency)
- JSON output (`--json`) designed for agents.

## Quickstart

### 1) On the PiCar‑X device

You need the SunFounder v2 stack installed (`robot_hat`, camera libs, etc.).

From the repo root:

```bash
python3 aiagentctrl.py --help
python3 aiagentctrl.py snapshot --json
python3 aiagentctrl.py ultrasonic --json
```

### 2) Driving (only with explicit human GO)

```bash
python3 aiagentctrl.py drive --speed 30 --seconds 0.5 --direction forward --json
python3 aiagentctrl.py stop --json
```

## OpenClaw integration

The intended integration pattern:

- Treat `aiagentctrl.py` as a **tool** / **MCP-like** deterministic interface.
- Always use `--json`.
- Enforce operational constraints in the agent prompt (see `agent_rules.md`).

## Documentation

- Full CLI docs: `aiagentctrl_aiguide.md`
- Operational rules: `agent_rules.md`

## Status

MVP: usable.

Next steps (foundations before contributors):
- add a minimal OpenClaw SKILL.md wrapper
- add a stable command schema reference (JSON fields per command)
- add a small test harness (dry-run / mock)

## License

GPL-2.0-or-later (see `LICENSE`).
