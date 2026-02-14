# HITL Testplan v1 (PiCar-X Agentic Driving)

Stand: 2026-02-14

## Ziel
Geplante, kurze Human-in-the-Loop Testsessions zur Verifikation der vorbereiteten autonomen Fahrlogik.

Prinzip:
- Vorher im Stand vorbereiten.
- In Session nur feine Parameteranpassung.
- Jede Session mit klaren Abbruchkriterien.

---

## Allgemeine Sicherheits-/Abbruchregeln

Sofort abbrechen bei:
- unerwarteter Fahrtrichtung
- festgefahren > 2 Turns ohne Fortschritt
- Person/Tier plötzlich im Fahrweg
- mechanischem Auffälligkeiten (ruckeln, schleifen, ungewöhnliche Geräusche)

Abbruchkommando:
```bash
python3 picarx_tool_router.py picarx.stop
```

---

## Test A — Basisnavigation auf Zielobjekt

### Ziel
Geradeausfahrt mit kleinen Korrekturen auf ein sichtbares Zielobjekt (z. B. braunes Spielzeugauto).

### Voraussetzungen
- freie Strecke ohne kritische Hindernisse
- Zielobjekt sichtbar im initialen Snapshot

### Ablauf (kompakt)
1. Snapshot aufnehmen
2. 1 Turn fahren (`picarx.turn`)
3. Bild bewerten (LMM)
4. Weiterfahren oder „arrived“

### Kommandos (Beispiel)
```bash
python3 picarx_tool_router.py picarx.snapshot
python3 picarx_tool_router.py picarx.turn --distance-cm 30 --speed 30 --direction forward --invert 1 --loops 1 --stop-on-stuck
```

### Erfolgskriterien
- Zielobjekt nach maximal 6 Turns deutlich näher
- keine Kollision
- max. 1 manuelle Korrektur je Durchlauf

---

## Test B — Raumübergang PoC

### Ziel
Konversation bleibt nutzbar, während der Agent schrittweise von Raum A nach B fährt.

### Voraussetzungen
- Türdurchgang frei
- bekannte problematische Bereiche (Mattenrand) markiert

### Ablauf
- Sequenz aus kurzen Turns (20–40 cm)
- nach jedem Turn Snapshot + Entscheidung
- Konversation parallel weiterführen

### Kommandos (Beispiel)
```bash
python3 picarx_tool_router.py picarx.turn --distance-cm 20 --speed 30 --direction forward --invert 1 --loops 1 --stop-on-stuck
```

### Erfolgskriterien
- Raumwechsel ohne harten Stop/Kollision
- Konversation in >=80% der Turns ohne Unterbrechung fortsetzbar

---

## Test C — Mattenrand / Blockade / Recovery

### Ziel
Nachweis, dass festgefahrene Situationen erkannt und sauber behandelt werden.

### Voraussetzungen
- kontrollierter Problemspot (Mattenrand o. ä.)

### Ablauf
1. Turn in Richtung Problemspot
2. Prüfen: `moved=false` / niedriger diff
3. Recovery-Variante manuell triggern (v1: stop + kleine Gegenbewegung + erneuter Turn)

### Kommandos (Beispiel)
```bash
python3 picarx_tool_router.py picarx.turn --distance-cm 20 --speed 30 --direction forward --invert 1 --loops 1 --stop-on-stuck
python3 picarx_tool_router.py picarx.stop
```

### Erfolgskriterien
- Stuck wird zuverlässig erkannt
- Recovery führt in <=2 Versuchen wieder zu Fortschritt ODER sauberem sicheren Abbruch

---

## Session-Protokoll (pro Testlauf)

Dokumentiere jeweils:
- Datum/Uhrzeit
- Test-ID (A/B/C)
- Startparameter (distance, speed, invert)
- Turns bis Ziel/Abbruch
- manuelle Eingriffe
- Ergebnis + Lessons Learned

---

## Decision JSON Schema (v0)

Erwartetes Format für LMM-Entscheidungen je Turn:

```json
{
  "action": "arrived|continue|blocked|uncertain",
  "steer": 0,
  "distance_cm": 20,
  "reason": "kurze Begründung"
}
```

Validierung:
```bash
python3 decision_schema.py --json '{"action":"continue","steer":0,"distance_cm":20,"reason":"frei"}'
```

Regeln (v0):
- `action`: required, Enum
- `steer`: optional, int [-35..35]
- `distance_cm`: optional, number [0..80]
- `reason`: optional, string

## Nächste Iteration (v2)
- Recovery-Schritte automatisieren
- parameter-sensitives Profiling (speed 30/40/50)
- Objektzentrierte Lenkentscheidung strukturieren (JSON decision schema)

### Draft: Decision-Schema (für LMM-Ausgabe, v0)
```json
{
  "decision": "forward|left|right|stop|arrived",
  "distance_cm": 20,
  "speed": 30,
  "reason": "kurze, konkrete Begründung",
  "risk": "low|medium|high",
  "needs_human": false
}
```
