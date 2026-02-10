# Roadmap: Agentic Driving (PiCar‑X + OpenClaw)

Stand: 2026‑02‑10

## Zielbild
Ein OpenClaw‑Agent soll ein Ziel („fahre zum braunen Spielzeugauto“) autonom erreichen, indem er in Turns arbeitet:
1) Snapshot → 2) LMM‑Interpretation + Intent → 3) Drive/Steer → 4) Snapshot → repeat bis „arrived“.

---

## Phase 0 — Stabilisierung (jetzt)
- [x] `PICARX_DRIVE_INVERT` + `applied_direction` in `aiagentctrl.py`
- [x] Wrapper `agentic_drive.py` (turn composition)
- [x] Stuck Detection (pixel diff) + Loop mode
- [x] Baseline‑Kalibrierung Zeit→cm (Speed 30/50/60)

Deliverable: reproduzierbare Turn‑Ausführung mit Artefakten (pre/post image) und „moved“ Flag.

---

## Phase 1 — Safety & Policy (1–2 Tage)
- [ ] GO‑Gate als **enforced TTL** (z.B. `--go-ttl 2h` erzeugt state file; Bewegungen ohne gültiges Token → fail)
- [ ] Battery guardrail: bei <15% nur langsame Moves + Hinweis; bei <10% stop + require human.
- [ ] Default speed profiles (indoor safe / corridor / demo)
- [ ] Hard stop: nach jedem Drive explizit `stop` (defensive)

---

## Phase 2 — Observability & Debuggability (1 Woche)
- [ ] JSONL Turn log (`logs/agentic_drive.jsonl`) inkl. turn_id, timestamps, params, diff_ratio, outcome.
- [ ] Optional: Save thumbnails for quick review.
- [ ] Replay mode (re-run decision step on recorded snapshots ohne Hardware).

---

## Phase 3 — Robust Motion (1–2 Wochen)
- [ ] Stuck Recovery Strategies:
  - reverse 10–15cm
  - steering wiggle
  - reduced speed
  - alternative path suggestion
- [ ] Better motion estimation:
  - optical flow / feature matching (ORB) für „moved“ + rough distance
- [ ] Calib model: speed→cm/s curve (nicht nur 40cm points), saturations berücksichtigen.

---

## Phase 4 — Goal Reaching (2–4 Wochen)
- [ ] Add a small “planner” prompt/template: goal → propose next turn params (steer + distance)
- [ ] Simple waypointing: door threshold / mat edge crossing / avoid chair legs.
- [ ] Optional: object‑centric driving: detect target bbox → steer to center → advance.

---

## Phase 5 — Integration in OpenClaw Skill Wrapper (später)
- [ ] Expose wrapper as a proper OpenClaw skill namespace (`picarx.turn`, `picarx.navigate_to_object`).
- [ ] Channel injection: pre/post snapshots automatically injected into the active agent session.
- [ ] Regression tests (mocked images) + CI.

