# systemd units

These are optional systemd **user** units that make the PiCar-X health + battery monitoring run automatically.

## Install (user units)

```bash
mkdir -p ~/.config/systemd/user
cp systemd/navis-battery-watch.* ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable --now navis-battery-watch.timer
```

## Configure

Battery estimation + thresholds are configured via environment variables (can be placed in
`~/.config/navis01/navis_listen.env`):

- `PICARX_BATTERY_V_FULL` (default 8.40)
- `PICARX_BATTERY_V_EMPTY` (default 6.60)
- `PICARX_BATTERY_WARN_20` (default 20)
- `PICARX_BATTERY_WARN_10` (default 10)

WhatsApp target:
- `NAVIS_BATTERY_WA_TARGET` (default: +491727296893)

Disable channels:
- `NAVIS_BATTERY_WA=0`
- `NAVIS_BATTERY_VOICE=0`

State file:
- `NAVIS_BATTERY_STATE` (default: `~/.openclaw/workspace/logs/battery_watch.state.json`)
