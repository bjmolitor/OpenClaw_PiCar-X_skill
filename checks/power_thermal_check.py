#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import shutil
import glob
import re
from checks._common import base_result, emit, run_cmd


def _parse_temp_c(text: str):
    m = re.search(r"temp=([0-9]+(?:\.[0-9]+)?)'C", text or "")
    return float(m.group(1)) if m else None


def _parse_throttled_hex(text: str):
    m = re.search(r"throttled=(0x[0-9a-fA-F]+)", text or "")
    return m.group(1).lower() if m else None


def _read_int(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def _find_pwmfan_hwmon():
    for d in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        try:
            with open(os.path.join(d, "name"), "r", encoding="utf-8") as f:
                name = f.read().strip()
            if name == "pwmfan":
                return d
        except Exception:
            continue
    return None


def main():
    r = base_result("power_thermal", "pi")
    vcgencmd = shutil.which("vcgencmd")
    if not vcgencmd:
        r["ok"] = False
        r["error"] = "vcgencmd_not_found"
        emit(r)
        return

    temp_cmd = run_cmd([vcgencmd, "measure_temp"], timeout_s=2)
    thr_cmd = run_cmd([vcgencmd, "get_throttled"], timeout_s=2)
    volt_cmd = run_cmd([vcgencmd, "measure_volts", "core"], timeout_s=2)

    r["evidence"]["commands"].append(temp_cmd)
    r["evidence"]["commands"].append(thr_cmd)
    r["evidence"]["commands"].append(volt_cmd)

    temp_c = _parse_temp_c(temp_cmd.get("out", ""))
    thr_hex = _parse_throttled_hex(thr_cmd.get("out", ""))
    thr_val = int(thr_hex, 16) if thr_hex else 0

    if temp_c is not None:
        r["metrics"]["temp_c"] = temp_c
    if thr_hex:
        r["metrics"]["throttled"] = thr_hex
        # Current state bits
        r["metrics"]["undervoltage_now"] = bool(thr_val & 0x1)
        r["metrics"]["freq_capped_now"] = bool(thr_val & 0x2)
        r["metrics"]["throttling_now"] = bool(thr_val & 0x4)
        r["metrics"]["soft_temp_limit_now"] = bool(thr_val & 0x8)
        # Historical state bits
        r["metrics"]["undervoltage_seen"] = bool(thr_val & 0x10000)
        r["metrics"]["freq_capped_seen"] = bool(thr_val & 0x20000)
        r["metrics"]["throttling_seen"] = bool(thr_val & 0x40000)
        r["metrics"]["soft_temp_limit_seen"] = bool(thr_val & 0x80000)

    # Cooler telemetry (best-effort): Raspberry Pi 5 exposes pwm fan via hwmon "pwmfan".
    fan_hwmon = _find_pwmfan_hwmon()
    if fan_hwmon:
        fan_rpm = _read_int(os.path.join(fan_hwmon, "fan1_input"))
        pwm = _read_int(os.path.join(fan_hwmon, "pwm1"))
        pwm_enable = _read_int(os.path.join(fan_hwmon, "pwm1_enable"))
        if fan_rpm is not None:
            r["metrics"]["fan_rpm"] = fan_rpm
        if pwm is not None:
            r["metrics"]["fan_pwm"] = pwm
            r["metrics"]["fan_pwm_pct"] = round((float(pwm) / 255.0) * 100.0, 1)
        if pwm_enable is not None:
            r["metrics"]["fan_pwm_mode"] = pwm_enable
        r["evidence"]["commands"].append(
            run_cmd(
                [
                    "bash",
                    "-lc",
                    f"cat {fan_hwmon}/name {fan_hwmon}/fan1_input {fan_hwmon}/pwm1 {fan_hwmon}/pwm1_enable 2>/dev/null",
                ],
                timeout_s=2,
            )
        )

        # Cooler health sanity: fan is commanded but does not spin.
        if pwm is not None and pwm > 0 and fan_rpm is not None and fan_rpm <= 0:
            r["ok"] = False
            r["error"] = "cooler_fan_not_spinning"
            r["notes"].append("Fan PWM is >0 but RPM reads 0; check fan wiring/cooler.")
    else:
        r["notes"].append("No pwmfan telemetry found in /sys/class/hwmon; cooler check is temperature/throttling-based only.")

    # Thermal guardrails
    if temp_c is not None and temp_c >= 80.0:
        r["ok"] = False
        r["error"] = "cpu_temp_high"
        r["notes"].append(f"CPU temperature high: {temp_c:.1f}C (>=80C).")

    # Current throttling indicates active thermal/power instability.
    if thr_hex and (thr_val & 0xF):
        r["ok"] = False
        r["error"] = "power_or_thermal_throttling_now"
        r["notes"].append(f"Current throttling flags set: {thr_hex}.")

    # Historical flags are useful context but not a hard failure.
    if thr_hex and (thr_val & 0xF0000):
        r["notes"].append(f"Historical throttling/undervoltage flags were seen: {thr_hex}.")

    emit(r)


if __name__ == "__main__":
    main()
