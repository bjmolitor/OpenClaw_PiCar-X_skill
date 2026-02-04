# JSON Schema Reference (MVP v0.1)

This file documents the **target JSON contracts** for agent consumption.

> Current `aiagentctrl.py` already returns JSON with `--json`.
> If some fields differ, we will patch `aiagentctrl.py` to match this reference.

## Common envelope

All commands should return:

```json
{
  "ok": true,
  "cmd": "snapshot",
  "ts": "2026-02-04T15:00:00+01:00"
}
```

On error:

```json
{
  "ok": false,
  "cmd": "drive",
  "ts": "...",
  "error": "human readable error"
}
```

## snapshot

```json
{
  "ok": true,
  "cmd": "snapshot",
  "path": "aiagent_camera/snap-20260204-150000.jpg",
  "backend": "rpicam",
  "took_ms": 812
}
```

## ultrasonic

```json
{
  "ok": true,
  "cmd": "ultrasonic",
  "distance_cm": 37.2
}
```

## head

```json
{
  "ok": true,
  "cmd": "head",
  "pan": -10,
  "tilt": 5
}
```

## steer

```json
{
  "ok": true,
  "cmd": "steer",
  "angle": 12
}
```

## drive

```json
{
  "ok": true,
  "cmd": "drive",
  "direction": "forward",
  "speed": 30,
  "seconds": 0.5
}
```

## stop

```json
{
  "ok": true,
  "cmd": "stop"
}
```

## health (new in v0.1)

```json
{
  "ok": true,
  "ts": "2026-02-04T15:40:00+01:00",
  "host": {
    "temp_c": 61.5,
    "throttled": "0xe0000",
    "undervoltage_now": false,
    "undervoltage_seen": true
  },
  "power": {
    "battery_v": 8.34,
    "battery_low": false,
    "battery_critical": false
  },
  "notes": []
}
```

## voltage-log (JSONL)
Each line is a `health` object plus `cmd:"voltage_log"`.
