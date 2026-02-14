# OpenClaw Skill Wrapper Runbook (PiCar-X)

Stand: 2026-02-14

## Ziel
Den verbleibenden Integrations-Gap schließen: `picarx.*` Namespace sauber und reproduzierbar in OpenClaw nutzen.

---

## 1) Voraussetzungen
- Repo: `~/picar-x/OpenClaw_PiCar-X_skill`
- Python3 verfügbar
- Hardware-Stack für PiCar-X installiert

Schnelltest:
```bash
cd ~/picar-x/OpenClaw_PiCar-X_skill
python3 -m py_compile aiagentctrl.py agentic_drive.py picarx_tool_router.py
```

---

## 2) Tool Namespace (vertraglich)
Folgende Tools gelten als kanonisch:
- `picarx.snapshot`
- `picarx.ultrasonic`
- `picarx.steer`
- `picarx.head`
- `picarx.drive`
- `picarx.stop`
- `picarx.turn`

Alle laufen über:
```bash
python3 picarx_tool_router.py <tool> [args]
```

---

## 3) Mapping (Router -> Controller)
- `picarx.snapshot` -> `aiagentctrl.py snapshot --json`
- `picarx.ultrasonic` -> `aiagentctrl.py ultrasonic --json`
- `picarx.steer --angle n` -> `aiagentctrl.py steer --angle n --json`
- `picarx.head [--pan n] [--tilt n]` -> `aiagentctrl.py head ... --json`
- `picarx.drive --speed n --seconds s --direction ...` -> `aiagentctrl.py drive ... --json`
- `picarx.stop` -> `aiagentctrl.py stop --json`
- `picarx.turn ...` -> `agentic_drive.py ...`

---

## 4) JSON Envelope (erwartet)
Jede Antwort soll diese Top-Level-Felder liefern:
- `ok`
- `cmd`
- `requested`
- `applied`
- `artifacts`
- `error`
- `ts`

Fehlerformat:
```json
{
  "ok": false,
  "error": {
    "code": "...",
    "detail": "..."
  }
}
```

---

## 5) Smoke Tests
```bash
cd ~/picar-x/OpenClaw_PiCar-X_skill
python3 picarx_tool_router.py picarx.snapshot
python3 picarx_tool_router.py picarx.ultrasonic
python3 picarx_tool_router.py picarx.stop
python3 picarx_tool_router.py picarx.turn --distance-cm 20 --speed 30 --direction forward --invert 1 --loops 1
```

Hinweis: Fahrkommandos nur in geplanter Testsession mit Human-in-the-Loop.

---

## 6) Definition of Done (Integrations-Gap)
Der „Skill ist integrationsreif“, wenn:
1. Namespace-Tools laufen über den Router reproduzierbar.
2. JSON-Envelope ist konsistent (inkl. Fehlerfälle).
3. SKILL.md + SCHEMA.md + Runbook sind synchron.
4. Ein kurzer HITL-Smoke-Test (snapshot/turn/stop) ist erfolgreich protokolliert.

---

## 7) Nächster Schritt danach
- HITL-Testpaket v1 (`docs/HITL_TESTPLAN_v1.md`) anlegen und mit den aktuellen Toolnamen verdrahten.
