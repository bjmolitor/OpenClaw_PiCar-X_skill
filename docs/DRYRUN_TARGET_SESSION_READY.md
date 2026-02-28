# Dry-Run Vorbereitung: Fahrtest auf Zielmarke

Stand: 2026-02-18

## Ziel
Sofort startklar sein, sobald Akku ausreichend geladen ist.

## Vor dem GO (2 Minuten)
1. Zielmarke aufstellen (klar sichtbar, mittig im Startbild).
2. Teststrecke freimachen (keine Personen/Tiere im Fahrweg).
3. Startposition fixieren (gleichbleibender Startpunkt für Vergleichbarkeit).
4. Kurzcheck ausführen:
   - `./aiagentctrl.py snapshot --json`
   - `python3 decision_schema.py --json '{"action":"continue","steer":0,"distance_cm":20,"reason":"ready"}'`

## Startprofil (Default)
- siehe `config/target-test-defaults.json`
- Kernwerte: 30 cm, speed 30, 1 Turn je Entscheidung, stop-on-stuck aktiv.

## Turn-by-Turn Ablauf
1. Pre-Snapshot
2. Decision (Schema v0) validieren
3. Bei `continue`: kurzer Move (`picarx.turn` / `agentic_drive.py`)
4. Post-Snapshot
5. Fortschritt bewerten
6. Nächster Turn oder Stop

## Ausführungskommandos (Basis)
```bash
cd ~/picar-x/OpenClaw_PiCar-X_skill

# 1) Initiales Bild
./aiagentctrl.py snapshot --json

# 2) Ein Turn mit Default-Charakter
python3 agentic_drive.py --distance-cm 30 --speed 30 --direction forward --invert 1 --loops 1 --stop-on-stuck

# 3) Sofortstop (bei Bedarf)
./aiagentctrl.py stop --json
```

## Abbruchbedingungen (hart)
- blocked
- kritisches uncertain
- Zielmarke >2 Turns nicht sichtbar
- stuck in 2 aufeinanderfolgenden Turns
- unerwartete Richtungsabweichung
- Human-Stop

## Session-Output (minimal)
- Turn-Anzahl bis Ziel/Abbruch
- Manuelle Eingriffe
- Auffälligkeiten (Drift/Stuck/Unsicherheit)
- Nächste Parameteranpassung (nur 1 Änderung pro Lauf)
