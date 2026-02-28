# Pre-Drive Camera Gate Checklist (Draft)

Ziel: Vor jedem Fahrbefehl muss ein aktuelles Kamera-Bild in die Agent-Session injiziert werden.

## Minimal-Akzeptanzkriterien (v0)
- [ ] Fahrbefehl ohne frisches Bild wird blockiert.
- [ ] "Frisch" = Bildalter <= 5 Sekunden.
- [ ] Bild-Injektion erfolgt vor Entscheidungslogik (nicht danach).
- [ ] Bei Kamera-Fehler: kein Fahren, stattdessen klarer Fehlerstatus.
- [ ] Jede Blockade/Entscheidung wird im Log mit Grund markiert.

## Offene HITL-Entscheidung
- Soll das Frische-Fenster 5s bleiben oder auf 10s erhöht werden?

## Mini-Validierung (ein Schritt, manuell)
- Einmal gezielt einen Fahrbefehl **ohne** frischen Snapshot ausführen und prüfen, dass der Gate-Block mit Begründung im Log erscheint.

## Log-Mindestformat (neu)
- `camera_gate=blocked reason=stale_snapshot age_s=<wert> threshold_s=<wert> snapshot_id=<id|none>`
- `camera_gate=pass age_s=<wert> threshold_s=<wert> snapshot_id=<id>`
