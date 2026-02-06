"""Camera capture + basic image statistics.

Uses `rpicam-still` (preferred) or `libcamera-still`.

Artifacts are written under `<workspace>/camera/`.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None

from PIL import Image  # pillow is already present on the Pi

from checks.media.common import CmdResult, ensure_dir, run_cmd


@dataclass
class CameraConfig:
    timeout_ms: int = 800
    verbose: int = 0
    camera_index: str = ""
    zsl: bool = True
    vflip: bool = False
    hflip: bool = False
    retries: int = 1


def _pick_backend() -> str:
    exe = shutil.which("rpicam-still") or shutil.which("libcamera-still")
    if not exe:
        raise FileNotFoundError("rpicam-still/libcamera-still not found")
    return exe


def load_camera_config_from_env() -> CameraConfig:
    """Load camera configuration from environment variables."""
    def _b(v: str) -> bool:
        return v.strip().lower() in ("1", "true", "yes", "on")

    cfg = CameraConfig()
    cfg.timeout_ms = max(200, min(int(os.environ.get("NAVIS_RPICAM_TIMEOUT_MS", "800")), 10000))
    cfg.verbose = max(0, min(int(os.environ.get("NAVIS_RPICAM_VERBOSE", "0")), 2))
    cfg.camera_index = os.environ.get("NAVIS_CAMERA_INDEX", "").strip()

    zsl_env = os.environ.get("NAVIS_RPICAM_ZSL")
    cfg.zsl = True if zsl_env is None else _b(str(zsl_env))

    cfg.vflip = _b(os.environ.get("NAVIS_CAMERA_VFLIP", "0"))
    cfg.hflip = _b(os.environ.get("NAVIS_CAMERA_HFLIP", "0"))
    cfg.retries = max(0, min(int(os.environ.get("NAVIS_RPICAM_RETRIES", "1")), 3))
    return cfg


def capture_snapshot(*, out_path: str, cfg: Optional[CameraConfig] = None, timeout_s: int = 20) -> Tuple[str, CmdResult]:
    """Capture a single JPEG snapshot.

    Returns `(path, cmd_result)`.
    Raises on hard failure (no backend / file not written).
    """
    cfg = cfg or load_camera_config_from_env()
    ensure_dir(os.path.dirname(out_path))

    exe = _pick_backend()

    cmd = [exe, "-n", "-t", str(cfg.timeout_ms), "-o", out_path, "-v", str(cfg.verbose)]
    if cfg.camera_index:
        cmd += ["--camera", cfg.camera_index]
    if cfg.zsl:
        cmd += ["--zsl", "1"]
    if cfg.vflip:
        cmd.append("--vflip")
    if cfg.hflip:
        cmd.append("--hflip")

    last = None
    for attempt in range(cfg.retries + 1):
        last = run_cmd(cmd, timeout_s=max(5, timeout_s), max_chars=4000)
        ok = (last.rc == 0) and os.path.exists(out_path) and (os.path.getsize(out_path) > 0)
        if ok:
            return out_path, last
        if attempt < cfg.retries:
            import time

            time.sleep(0.2 * (attempt + 1))

    raise RuntimeError(f"Camera snapshot failed. Last rc={getattr(last,'rc',None)} out={getattr(last,'out','')}")


def default_snapshot_path(workspace: str) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(workspace, "camera", f"health-{ts}.jpg")


def image_stats(path: str) -> Dict[str, float | int]:
    """Compute simple brightness statistics.

    Returns mean/std/min/max luma (8-bit), using numpy if available.
    """
    im = Image.open(path).convert("L")
    if np is None:
        # fallback without numpy
        px = list(im.getdata())
        mean = sum(px) / max(1, len(px))
        # crude std
        var = sum((p - mean) ** 2 for p in px) / max(1, len(px))
        std = var ** 0.5
        return {"mean_luma": float(mean), "std_luma": float(std), "min_luma": int(min(px)), "max_luma": int(max(px))}

    a = np.array(im)
    return {
        "mean_luma": float(a.mean()),
        "std_luma": float(a.std()),
        "min_luma": int(a.min()),
        "max_luma": int(a.max()),
    }
