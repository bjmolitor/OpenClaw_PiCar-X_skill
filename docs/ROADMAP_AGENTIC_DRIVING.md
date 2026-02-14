# Roadmap: Agentic Driving (PiCar‑X + OpenClaw)

Stand: 2026‑02‑14 (neu priorisiert)

## Zielbild
Autonomes, schrittweises Fahren auf Basis von Kamerabildern (LMM, low-res, geringe Sensorik),
um Konversation robust über Räume hinweg mitzunehmen (PoC).

Kernprinzip: **Turn-basiert**
1) Snapshot + Kontext
2) LMM-Entscheidung (Steer/Distanz)
3) Bewegung
4) Snapshot + Bewertung
5) Repeat bis Ziel erreicht

---

## Priorität 1 — Im Stand allein machbar (sofort)

### A) Skill-Refactoring / Quality First
- [ ] Alles Relevante aus `~/.openclaw/workspace` in das kanonische Skill-Repo konsolidieren.
- [ ] Skripte klar trennen: hardware-nah (Controller), turn-orchestration, skill-wrapper, diagnostics.
- [ ] API/JSON-Contracts vereinheitlichen (`ok`, `cmd`, `requested`, `applied`, `error`, `artifacts`).
- [ ] Unnötige Legacy-Pfade/duplizierte Skripte entfernen oder dokumentiert deprecaten.

### B) OpenClaw-Skill-Form sauber herstellen
- [ ] Skill so strukturieren, dass er wirklich als OpenClaw Skill eingebunden werden kann.
- [ ] Tool-Oberfläche definieren (z. B. `picarx.snapshot`, `picarx.turn`, `picarx.navigate_step`).
- [ ] Readme + SKILL-Doku auf Integrationsreife bringen (inkl. Beispiel-Flows).

### C) Programmatic Frame für autonomes Fahren vorbereiten
- [ ] „Step-Executor“: ein Turn = Snapshot -> Decision-Input -> Drive -> Snapshot.
- [ ] Entscheidungs-Schema festlegen (JSON-Decision statt Freitext).
- [ ] Abschlusskriterien definieren (`arrived`, `blocked`, `uncertain`, `retry`).
- [ ] Turn-Logging (leichtgewichtig) für spätere Auswertung.

---

## Priorität 2 — Testsession mit Human-in-the-Loop (geplant, vorbereitet)

### Testmodus: mit Papa, kurze geplante Sessions
- [ ] Vor jeder Session: Testplan + erwartetes Verhalten + Abbruchkriterien vorbereitet.
- [ ] Während Session: nur Feinjustage, keine großen Umbauten.
- [ ] Nach Session: Findings ins Backlog + Parameterupdate (Kalibrierung/Heuristiken).

### Erste Testpakete
1. **Navigations-Basis**: Geradeaus + leichte Korrekturen auf Zielobjekt.
2. **Raumübergang PoC**: von Raum A nach Raum B bei laufender Konversation.
3. **Robustheit**: Mattenrand/kleine Hindernisse, kontrollierte Recovery.

---

## Priorität 3 — Optional/Später
- [ ] Kooperation mit externen Agenten/Open-Source-Community (GitHub öffentlich) für Review/PRs.
- [ ] Erweiterte Recovery/Observability nur soweit nötig für PoC-Ziel.

---

## Was bewusst niedrige Prio hat (derzeit)
- Enforced GO-TTL als erstes großes Thema
- Battery-Guardrails als Hauptfokus
- Aufwändige Extras, die nicht direkt auf „autonomes Fahren via Kamera“ einzahlen

(werden nur gezogen, wenn sie blockieren oder für sichere Demos zwingend werden)
