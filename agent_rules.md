# Agent Rules (PiCar-X / OpenClaw)

These rules are meant to be copied into an OpenClaw agent skill prompt / operational policy.

## Safety first

- **No driving by default.** Only drive when the human explicitly says **"GO"**.
- Prefer **`stop`** over any other action when uncertain.
- Use **short durations** for movement (`--seconds <= 1.0`) and **low speeds** (`<= 35`) unless explicitly approved.
- Keep a physical emergency stop ready (pick up robot / cut power).

## Deterministic control only

- Use `aiagentctrl.py` for all robot actions.
- Always call it with `--json` and read the returned JSON.
- Do not chain multiple movement commands without a stop/verification step.

## Camera & sensing

- Camera snapshots are allowed anytime (no motion risk).
- Ultrasonic reads are allowed anytime.

## After each action

- Expect the controller to **dead-man stop** after each command.
- If anything behaves unexpectedly: immediately run `aiagentctrl.py stop --json`.

## Logging

- Log *what was commanded* and *what the controller returned* (JSON) when debugging.
- Never log secrets.
