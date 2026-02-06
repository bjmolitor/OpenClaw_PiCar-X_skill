#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from checks._common import base_result, emit, run_cmd


def main():
    r = base_result("storage", "snapshot")

    # Disk usage / filesystem type
    r["evidence"]["commands"].append(run_cmd(["df", "-hT", "/"], timeout_s=4, max_chars=4000))

    # Block devices overview (SD/NVMe visibility)
    r["evidence"]["commands"].append(run_cmd(["lsblk", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL"], timeout_s=4, max_chars=6000))

    # Kernel log hints for SD / ext4 issues
    # Keep it best-effort and short.
    r["evidence"]["commands"].append(
        run_cmd(
            [
                "bash",
                "-lc",
                "dmesg --color=never | egrep -i 'mmc|sdhci|i/o error|ext4-fs error|buffer i/o|corrupt|reset' | tail -n 120 || true",
            ],
            timeout_s=6,
            max_chars=8000,
        )
    )

    # journald kernel (if available)
    r["evidence"]["commands"].append(
        run_cmd(
            [
                "bash",
                "-lc",
                "journalctl -k --no-pager -n 200 2>/dev/null | egrep -i 'mmc|sdhci|i/o error|ext4-fs error|buffer i/o|corrupt|reset' | tail -n 120 || true",
            ],
            timeout_s=8,
            max_chars=8000,
        )
    )

    emit(r)


if __name__ == "__main__":
    main()
