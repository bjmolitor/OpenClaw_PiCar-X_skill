# SPEC_DRIVE_LOOP_v1

Stand: 2026-02-16

## Zweck
Autonomes, schrittweises Fahren mit LMM-Entscheidung pro Turn und strikt programmatischer Ausführung.

Leitprinzip:
- **LMM** entscheidet auf Basis von Bild + Kontext.
- **Executor** führt deterministisch aus (kurze Schritte, harte Guards, klare Abbrüche).

---

## 1) Turn-Definition (atomare Einheit)

Ein Turn besteht exakt aus:
1. Pre-Snapshot
2. Decision erzeugen + validieren (Schema v0)
3. Optional Steer setzen
4. Drive (kurzer Schritt)
5. Post-Snapshot
6. Outcome-Bewertung (`arrived|continue|blocked|uncertain`) + Fortschrittsprüfung

---

## 2) Decision-Schema (v0)

Pflichtfeld:
- `action`: `arrived | continue | blocked | uncertain`

Optionale Felder:
- `steer`: `int` in `[-35..35]`
- `distance_cm`: `number` in `[0..80]`
- `reason`: `string`

Validierungsregel:
- Ungültiges Schema => **kein Drive**, stattdessen `blocked`/`uncertain`-Pfad.

---

## 3) Startbedingungen (vor Schleifenstart)

Alle Bedingungen müssen erfüllt sein:
1. HITL-Testsession aktiv/freigegeben.
2. Kamera verfügbar (Snapshot funktioniert).
3. Drive-Stack erreichbar (Controller/Hardware antwortet).
4. Systemzustand unkritisch (kein akuter Thermal-/Undervoltage-Alarm).
5. Initiales Bild liegt vor (kein Blindfahren).

---

## 4) Default-Startprofil (Session v1)

Empfohlene Startwerte:
- `distance_cm = 30`
- `speed = 30`
- `steer = 0`
- `loops = 1` (immer ein Turn, dann neu entscheiden)
- `stop-on-stuck = on`

Hinweis:
- Richtungsmapping (`forward/backward`) folgt der aktuell kalibrierten Plattformkonfiguration.

---

## 5) Guard Conditions (vor jedem Drive)

Vor Ausführung von Bewegung muss gelten:
1. Decision ist schema-valid.
2. `action == continue`.
3. Parameter innerhalb Clamp-Grenzen.
4. Kein aktiver Hard-Block aus vorigem Turn.
5. Unsicherheit wird konservativ behandelt (Distanz reduzieren oder Stop).

---

## 6) Abbruchbedingungen (harte Stops)

Sofort `stop` + Abbruch bei:
1. `action == blocked`
2. `action == uncertain` in kritischer Szene
3. Stuck erkannt (`moved=false` oder Diff unter Schwellwert trotz Drive)
4. Unerwartete Fahrtrichtung/Drift
5. Person/Tier/Hindernis im unmittelbaren Fahrweg
6. Sicherheitsrelevanter Hardware-/Sensorfehler
7. Manuelles Stop durch Human

---

## 7) Soft-Abbruch / Replan

Bei Unsicherheit ohne akute Gefahr:
- Distanz reduzieren (z. B. 30 -> 15 cm)
- Steer neutralisieren/klein korrigieren
- Nächsten Turn neu bewerten statt langer Fahrt

---

## 8) Zielerreichung

Wenn `action == arrived`:
1. Sofort `stop`
2. Finales Snapshot
3. Turn-Ergebnis protokollieren (Turns, Korrekturen, Besonderheiten)

---

## 9) Ablauf (Pseudologik)

1. Preconditions prüfen
2. `while not arrived`:
   - Pre-Snapshot
   - Decision + Schema-Validierung
   - Bei `blocked/uncertain` -> Stop + Exit
   - Optional Steer
   - Drive (kurzer Schritt)
   - Post-Snapshot
   - Fortschritt/Stuck evaluieren
   - Bei Stuck -> Stop + Exit oder Recovery-Policy
3. Stop + Final-Log

---

## 10) Logging (Mindestumfang)

Pro Turn speichern:
- Turn-ID, Timestamp
- Requested/Applied Parameter
- Decision JSON
- Pre/Post Snapshot-Pfade
- Moved/Stuck-Status
- Outcome (`arrived|continue|blocked|uncertain`)
- Fehlercode/Detail bei Abbruch
