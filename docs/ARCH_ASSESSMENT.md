# Architektur‑Assessment (OpenClaw PiCar‑X Skill)

Stand: 2026‑02‑10

## Scope
Dieses Assessment betrachtet zwei Ebenen:
1) **Skill‑Repo** `~/picar-x/OpenClaw_PiCar-X_skill` (kanonisch): Hardware‑naher, deterministischer Tool‑Surface.
2) **OpenClaw Workspace** `~/.openclaw/workspace`: Agent‑Runtime/Channel/Voice/Experimente (nicht kanonisch für Body‑Skill).

Fokus: agentisches Fahren via Kamera‑Loop (Snapshot → Decision → Drive/Steer → Snapshot), plus Safety/Observability.

---

## Was ist bereits gut gelöst

### 1) Deterministische CLI als Hardware‑Boundary
- `aiagentctrl.py` kapselt PiCar‑X APIs hinter einem CLI und liefert JSON.
- Das ist architektonisch „richtig“ für Agenten: **keine direkten Hardware‑Imports im LLM‑Code**, sondern ein „Tool‑Surface“.

### 2) Safety‑Mechaniken im Controller
- Clamps (`PICARX_MAX_SPEED`, `PICARX_MAX_ANGLE`) + timeboxed drive.
- Signal‑safe Stop (SIGINT/SIGTERM → `_safe_stop`).
- „GPIO busy“ Mitigation durch `_free_gpio_blockers` (best effort).

### 3) Wiederholbarkeit / Diagnostik
- Healthcheck‑Framework im Repo vorhanden (`checks/` + `healthcheck.py`).
- Snapshot via `rpicam-still` (robust, reproduzierbar).

---

## Technische Schulden / Risiken

### A) GO‑Gate / Autorisierung ist nicht als harte Policy verdrahtet
- GO existiert als Prompt-/Prozess‑Regel, aber nicht als **enforced policy** im Tool‑Layer.
- Empfehlung: Tool‑Layer (Wrapper) soll GO‑TTL erzwingen (env flag oder state file), nicht der LLM‑Text.

### B) Offene Loop‑Kontrolle (Open‑Loop) führt zu Drift/Stillstand
- Aktuell ist Drive zeitbasiert (seconds). Das ist ok für MVP, aber:
  - Reibung/Teppichkante/Mattenrand → **„stuck“** ohne dass es auffällt.
  - Speed‑Sättigung beobachtet (ab ~50% kaum mehr cm/s) → nicht linear.
- Konsequenz: Ohne Closed‑Loop (Vision odometry / wheel encoders / ultrasonic) braucht man mindestens **Stuck Detection** + Recovery.

### C) Sensor‑Zuverlässigkeit (Ultrasonic)
- Beobachtet: `distance_cm = -2.0` → unplausibel/Fehler.
- Folge: Safety‑Abstand kann aktuell nicht auf ultrasonic basieren; Vision muss Lücken schließen.
- Empfehlung: Sensor‑Readouts müssen „valid/invalid“ semantisch klar kodieren (z.B. `ok=false` bei negativen Werten).

### D) Richtung/Sign‑Konvention (Forward/Backward)
- Realwelt‑Mapping war invertiert/uneindeutig.
- Es existiert jetzt `PICARX_DRIVE_INVERT` + `applied_direction` in JSON.
- Empfehlung: Diese Invertierung sollte **konfigurierbar pro Hardware‑Profil** sein (nicht default=1 „für dieses Setup“ im Code), z.B. in einem config JSON.

### E) Observability / Traceability
- Es fehlt eine Turn‑ID und strukturierte Logs (JSONL) für: Snapshot path, decision, steer, drive, diff_ratio, outcome.
- Ohne Logs wird Debugging schwer (z.B. „warum SIGTERM?“ oder „warum stuck?“).

---

## Aktueller Stand Wrapper: `agentic_drive.py`

### Eigenschaften
- Ein „Turn“: pre‑snapshot → optional steer → drive → post‑snapshot.
- **Stuck Detection** via Bild‑Diff (`diff_ratio`, `moved`) mit Pillow.
- **Loop mode** (`--loops N`) zur Wiederholung.
- **Kalibrierung**: Tabelle `CALIB_40CM` (Speed→seconds) + Interpolation; optional `--distance-cm`.

### Grenzen
- Wrapper trifft keine High‑Level‑Zielentscheidung; er liefert nur saubere I/O für den Agenten.
- Stuck Detection ist heuristisch (pixel‑diff); robustere Methoden (feature matching) wären später.

---

## Architectural Recommendation (North Star)

### Layering
1) **Hardware layer:** `aiagentctrl.py` (strict, deterministic, minimal surface)
2) **Turn layer:** `agentic_drive.py` (composes multiple hardware calls into a safe/observable turn)
3) **Policy layer:** GO‑TTL, speed limits by context (night/child present), battery threshold, etc.
4) **Agent layer (OpenClaw):** interprets images in conversation context, sets intent/goal, chooses next turn params.

### Contract
- Every command returns JSON with:
  - `ok`, `cmd/action`, `ts`, `error?`
  - `requested` vs `applied` fields
  - Paths for artifacts (snapshots)
  - Optional `telemetry` (battery, temp, etc.)

---

## Quick Wins (nächste 1–2 Sessions)
- GO‑TTL enforcement in wrapper.
- `agentic_drive.py` um „recovery“ erweitern (bei stuck: stop → reverse 10cm → retry / steer wiggle).
- Ultrasonic fix: negative Werte als `ok=false`, retries, GPIO contention.
- Turn‑Logging als JSONL.

## Ergänzung 2026-02-23: Repo-Integritäts-Guardrail
- Beobachtung im Skill-Repo: lose Git-Objekte sind beschädigt (`.git/objects/... ist leer`, `git status` bricht mit Exit 128 ab).
- Kleiner, sofort wirksamer Guardrail vor jeder Sessionarbeit im Skill-Repo:
  1) `git fsck --full` ausführen.
  2) Bei Fehlern **keine riskanten Git-Operationen** (kein Rebase/GC).
  3) Änderungen als Patch/Dateikopie sichern, dann Recovery planen (fresh clone + transplant der Arbeitsstände).
- Ziel: Fortschritt bei Refactoring/Qualität sichern, ohne den aktuellen Arbeitsstand zu verlieren.

