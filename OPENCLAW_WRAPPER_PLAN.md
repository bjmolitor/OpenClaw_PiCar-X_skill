# OpenClaw Wrapper Plan (v0.1)

Goal: expose `aiagentctrl.py` as OpenClaw tools and enforce safety gates.

## Option A: Skill wrapper (preferred)

- Provide a skill folder (in the OpenClaw skills registry) that defines tools:
  - `picarx.snapshot`
  - `picarx.ultrasonic`
  - `picarx.drive`
  - `picarx.steer`
  - `picarx.head`
  - `picarx.stop`
- Each tool calls `python3 aiagentctrl.py ... --json`.

### GO gate
- Wrapper checks either:
  - `PICARX_GO=1` env var for one command, or
  - a state file `/opt/picar-x/go_state.json` with TTL
- If missing: refuse motion command and return `{ok:false,error:"Motion blocked until human says GO"}`

## Option B: MCP server

Expose the same methods as HTTP endpoints (JSON RPC). More work; not required for v0.1.

## Why wrapper, not direct agent prompt

Prompt-only safety is brittle.
A wrapper provides a hard enforcement layer.
