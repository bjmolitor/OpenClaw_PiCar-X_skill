# HITL Target-Marker Testplan v1

Stand: 2026-02-18

## Ziel
Autonome Turn-für-Turn Navigation auf eine vom Human aufgestellte Zielmarke.

## Funktionscheck (vor Session)
- Kamera: OK
- Mikrofon: OK
- TTS: OK
- Thermik/Throttling: OK (`throttled=0x0`)
- Decision-Validator: OK
- Ultrasonic: unzuverlässig/negativ -> nicht als primäre Entscheidungsquelle verwenden

## Setup vor Start
1. Zielmarke gut sichtbar in Fahrtrichtung aufstellen.
2. Freie Teststrecke ohne Personen/Tiere im Fahrweg.
3. Startposition fixieren (Marker auf Boden für Reproduzierbarkeit).
4. Human sitzt in Reichweite für sofortigen Stop.

## Startprofil
- distance_cm: 30
- speed: 30
- steer: 0
- loops: 1
- stop-on-stuck: on
- Kamera-Gate Frischefenster: 10s

## Turn-Schleife (pro Schritt)
1. Pre-Snapshot
2. LMM-Decision (Schema v0): `arrived|continue|blocked|uncertain`, optional `steer`, `distance_cm`
3. Schema validieren
4. Bei `continue`: optional steer + kurzer drive
5. Post-Snapshot
6. Fortschritt prüfen (moved/diff + Zielmarke näher?)
7. Nächster Turn oder Stop

## Abbruchbedingungen (hard stop)
- `blocked` oder kritisches `uncertain`
- Zielmarke nicht mehr im Bild über 2 Turns
- Unerwartete Bewegungsrichtung/Drift
- Stuck über 2 Turns
- Mensch/Tier/Hindernis im Fahrweg
- Human-Stop

## Erfolgskriterien
- Zielmarke innerhalb von max. 8 Turns deutlich angenähert oder erreicht
- Keine Kollision
- Max. 2 manuelle Eingriffe

## Session-Protokoll
- Turn-ID, decision, requested/applied, pre/post snapshot
- moved/stuck, reason, abort cause (falls vorhanden)
- Kurzfazit + Parameter für nächsten Lauf
