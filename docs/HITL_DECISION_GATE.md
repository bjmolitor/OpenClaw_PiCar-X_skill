# Human-in-the-Loop Decision Gate (v0)

Stand: 2026-02-15

## Zweck
Kompakte, einheitliche Rückfrage an den Menschen vor risikorelevanten Fahr-Schritten.

## Standard-Format (genau 1 Frage)
1. **Kontext (1 Satz):** Aktueller Zustand + wichtigste Unsicherheit.
2. **Optionen (A/B):** Zwei klare Handlungsoptionen.
3. **Frage (eine Zeile):** „Option A oder B?“

## Vorlage
- Kontext: `<kurzer Status + Unsicherheit>`
- A: `<konservativer Schritt>`
- B: `<aggressiver/fortsetzender Schritt>`
- Frage: `Soll ich A oder B ausführen?`

## Erste Anwendung (Agentic Driving)
- Kontext: Kamera ist statisch (kein Schwenk), daher eingeschränkte Sicht seitlich.
- A: Nur Mini-Fahrten mit sehr kurzer Distanz + sofortigem Snapshot.
- B: Längere Einzelschritte mit weniger Zwischen-Snapshots.
- Frage: Soll ich A oder B als Standard für die ersten Testsessions setzen?

## Aktueller Standard (gesetzt)
- **Standard: B** (größere Einzelschritte mit weniger Snapshots), wie von Papa entschieden.
- Bei Unsicherheit/enger Umgebung darf temporär auf A zurückgefallen werden.
