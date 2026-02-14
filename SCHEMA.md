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
  "ts": "2026-02-04T15:00:00+01:00",
  "requested": {},
  "applied": {},
  "artifacts": {},
  "error": null
}
```

On error:

```json
{
  "ok": false,
  "cmd": "drive",
  "ts": "...",
  "requested": {},
  "applied": {},
  "artifacts": {},
  "error": {
    "code": "command_failed",
    "detail": "human readable error"
  }
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

## agentic_turn (wrapper)

```json
{
  "ok": true,
  "cmd": "agentic_turn",
  "requested": {
    "speed": 30,
    "seconds": 1.48,
    "distance_cm": 40,
    "direction": "forward",
    "steer": null,
    "invert": "1"
  },
  "applied": {
    "seconds": 1.48,
    "drive": {
      "requested_direction": "forward",
      "applied_direction": "backward",
      "applied_speed": 30
    }
  },
  "artifacts": {
    "pre_snapshot": ".../snap-a.jpg",
    "post_snapshot": ".../snap-b.jpg"
  },
  "error": null
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

## perceive (new in v0.1)
Environment perception without driving.

### single snapshot
```json
{
  "ok": true,
  "cmd": "perceive",
  "ts": "2026-02-04T18:25:00+01:00",
  "sensors": {
    "ultrasonic": {"ok": true, "distance_cm": 37.2}
  },
  "camera": {"ok": true, "path": ".../snap.jpg", "backend": "rpicam"}
}
```

### head sweep (5 shots)
```json
{
  "ok": true,
  "cmd": "perceive",
  "camera": {
    "ok": true,
    "mode": "head_sweep",
    "shots": [
      {"label":"left","pan":-20,"tilt":0,"snapshot":{"ok":true,"path":"..."}},
      {"label":"center","pan":0,"tilt":0,"snapshot":{"ok":true,"path":"..."}},
      {"label":"right","pan":20,"tilt":0,"snapshot":{"ok":true,"path":"..."}},
      {"label":"up","pan":0,"tilt":20,"snapshot":{"ok":true,"path":"..."}},
      {"label":"down","pan":0,"tilt":-20,"snapshot":{"ok":true,"path":"..."}}
    ]
  },
  "perception": {
    "ok": true,
    "model": "gpt-4o-mini",
    "result": {
      "summary": "...",
      "risk_level": "low",
      "hazards": []
    }
  }
}
```
