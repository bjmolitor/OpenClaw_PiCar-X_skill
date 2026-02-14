# Code Inventory (Skill-Repo vs Workspace)

Stand: 2026-02-14

## Ziel
Klar trennen, was **kanonisch** im Skill-Repo lebt und was im Workspace nur als Runtime-Artefakt/Legacy gilt.

---

## A) Canonical (bleibt im Skill-Repo)

### Core Control / Driving
- `aiagentctrl.py` — hardware-nahe CLI (drive/steer/head/snapshot/ultrasonic/stop)
- `agentic_drive.py` — turn wrapper (snapshot -> move -> snapshot + diff)
- `healthcheck.py` — entrypoint für Checks

### Checks / Diagnostics
- `checks/**` inkl. `checks/media/**`
- `battery_watch.py`

### Skill Docs / Contract
- `SKILL.md`, `SCHEMA.md`, `README.md`, `agent_rules.md`
- `docs/ARCH_ASSESSMENT.md`
- `docs/ROADMAP_AGENTIC_DRIVING.md`
- `docs/WORKPLAN_2026-02-14_to_2026-02-16.md`
- `docs/CODE_INVENTORY.md` (dieses Dokument)

### Optional Runtime Support in Skill Repo
- `systemd/navis-battery-watch.*`

---

## B) Move to Skill Repo (aus Workspace übernehmen / angleichen)

### Candidate scripts currently in workspace
- `~/.openclaw/workspace/scripts/shortterm_append.py`
- `~/.openclaw/workspace/scripts/whatsapp_shortterm_sync.py`

Bewertung:
- Diese beiden sind **Legacy shortterm-memory tooling** und gehören **nicht** in die zukünftige Skill-Kernarchitektur.
- Aktion: **nicht migrieren** als aktive Komponenten; stattdessen als deprecated dokumentieren oder entfernen.

### Candidate docs in workspace checks/docs
- `~/.openclaw/workspace/docs/CHECKS_SPEC.md`
- `~/.openclaw/workspace/docs/runbook-media.md`

Aktion:
- Inhalte prüfen und relevante Teile in Skill-Doku integrieren.

---

## C) Keep in Workspace only (runtime artifacts, nicht ins Skill-Repo)

- `audio/**`, `camera/**`, `logs/**`, `memory/**`
- `models/**` (lokale Modelle)
- `navis_listen_daemon.py`, `navis_media.py` (Runtime-Stack im Workspace)
- `.venv-*`, `__pycache__/**`, temporäre Testartefakte

Hinweis:
- Diese Dateien sind produktionsnahe Runtime-/Ops-Artefakte und sollten nicht das Skill-Repo verunreinigen.

---

## D) Legacy/Deprecation candidates

- `navis-shortterm-sync.service/.timer` + zugehörige Scripts
  - Status: bereits deaktiviert
  - Aktion: in Doku als deprecated markieren; später sauber entfernen

- Doppelte/alte Runbooks im Workspace:
  - `RUNBOOK_media_test.md`
  - `RUNBOOK_MEDIA_TEST.md`
  - Aktion: konsolidieren (eine kanonische Fassung)

---

## E) Nächste konkrete Schritte (Tag 1)

1. JSON-Contract-Harmonisierung zwischen `aiagentctrl.py` und `agentic_drive.py`
2. Deprecated-Section in Skill-Doku ergänzen (shortterm-memory tooling)
3. Workspace-Doku-Relevanz prüfen und in Skill-Repo spiegeln
4. Optional: kleines `tools/` oder `runtime/` Verzeichnis definieren (für klare Trennung)
