#!/usr/bin/env python3
import os, sys, json, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from checks._common import base_result, emit, run_cmd


def main():
    r = base_result("network", "snapshot")

    # Interfaces + addresses
    r["evidence"]["commands"].append(run_cmd(["ip", "-brief", "addr"], timeout_s=4, max_chars=6000))

    # Routes (default gateway)
    r["evidence"]["commands"].append(run_cmd(["ip", "route"], timeout_s=4, max_chars=4000))

    # Neighbor table (passive device view)
    r["evidence"]["commands"].append(run_cmd(["ip", "neigh"], timeout_s=4, max_chars=6000))

    # DNS sanity (non-invasive)
    r["evidence"]["commands"].append(run_cmd(["bash", "-lc", "getent hosts github.com openai.com 2>/dev/null | head"], timeout_s=6, max_chars=2000))

    # Current connections (defensive view)
    # ss is preferred; fallback to netstat if present.
    r["evidence"]["commands"].append(run_cmd(["bash", "-lc", "ss -tulpn 2>/dev/null | head -n 200 || netstat -tulpn 2>/dev/null | head -n 200 || true"], timeout_s=8, max_chars=12000))

    # Established connections (outgoing/incoming)
    r["evidence"]["commands"].append(run_cmd(["bash", "-lc", "ss -tunp state established 2>/dev/null | head -n 200 || true"], timeout_s=8, max_chars=12000))

    # Optional security-ish context (best-effort, no scanning)
    # - ufw firewall status (if installed)
    r["evidence"]["commands"].append(run_cmd(["bash", "-lc", "ufw status verbose 2>/dev/null || true"], timeout_s=6, max_chars=4000))

    # - tailscale status (if installed)
    r["evidence"]["commands"].append(run_cmd(["bash", "-lc", "tailscale status 2>/dev/null | head -n 200 || true"], timeout_s=8, max_chars=8000))

    # - open ports via lsof (if installed)
    r["evidence"]["commands"].append(run_cmd(["bash", "-lc", "lsof -i -P -n 2>/dev/null | head -n 200 || true"], timeout_s=8, max_chars=12000))

    # Speedtest (connectivity prerequisite)
    # Prefer speedtest-cli JSON (Debian/RPi default), then Ookla speedtest JSON, then fast.
    speed_metrics = None
    cmd_out = None

    if shutil.which("speedtest-cli"):
        cmd_out = run_cmd(["bash", "-lc", "speedtest-cli --json"], timeout_s=240, max_chars=12000)
        try:
            data = json.loads(cmd_out.get("out") or "{}")
            speed_metrics = {
                "tool": "speedtest-cli",
                "ping_ms": data.get("ping"),
                "down_bps": data.get("download"),
                "up_bps": data.get("upload"),
                "server": (data.get("server") or {}).get("host"),
            }
        except Exception:
            speed_metrics = {"tool": "speedtest-cli", "parse": "failed"}

    elif shutil.which("speedtest"):
        # Ookla speedtest
        cmd_out = run_cmd(["bash", "-lc", "speedtest --accept-license --accept-gdpr -f json"], timeout_s=120, max_chars=12000)
        try:
            data = json.loads(cmd_out.get("out") or "{}")
            speed_metrics = {
                "tool": "speedtest",
                "ping_ms": float((data.get("ping") or {}).get("latency")) if (data.get("ping") or {}).get("latency") is not None else None,
                "down_bps": float((data.get("download") or {}).get("bandwidth")) * 8 if (data.get("download") or {}).get("bandwidth") is not None else None,
                "up_bps": float((data.get("upload") or {}).get("bandwidth")) * 8 if (data.get("upload") or {}).get("bandwidth") is not None else None,
                "packet_loss": data.get("packetLoss"),
                "isp": (data.get("isp") or None),
                "server": (data.get("server") or {}).get("name"),
            }
        except Exception:
            speed_metrics = {"tool": "speedtest", "parse": "failed"}

    elif shutil.which("fast"):
        cmd_out = run_cmd(["bash", "-lc", "fast --json"], timeout_s=180, max_chars=12000)
        try:
            data = json.loads(cmd_out.get("out") or "{}")
            speed_metrics = {
                "tool": "fast",
                "down_mbps": data.get("downloadSpeed"),
                "up_mbps": data.get("uploadSpeed"),
                "latency_ms": (data.get("latency") or {}).get("unloaded"),
            }
        except Exception:
            speed_metrics = {"tool": "fast", "parse": "failed"}

    else:
        speed_metrics = {"supported": False, "reason": "no_speedtest_tool_installed"}

    if cmd_out is not None:
        r["evidence"]["commands"].append(cmd_out)

    r["metrics"]["speedtest"] = speed_metrics

    # If speedtest is unsupported, mark as WARN (ok=false) because connectivity is a prerequisite.
    if isinstance(speed_metrics, dict) and speed_metrics.get("supported") is False:
        r["ok"] = False
        r["error"] = "speedtest_tool_missing"

    emit(r)


if __name__ == "__main__":
    main()
