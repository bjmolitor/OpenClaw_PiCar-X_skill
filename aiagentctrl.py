#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Purpose: Minimal, agent-friendly CLI to control SunFounder PiCar-X (drive, steer, head pan/tilt, ultrasonic),
# with safety clamps, signal-safe immediate stop, and JSON/human outputs. Compatible across 3.0.x and legacy names.

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import shutil
from typing import Any, Dict, Optional
from datetime import datetime


# ---- Globals for signal handling ----
_PX_OBJ = None  # set after we create the car instance
_STATE_PATH_DEFAULT = "/opt/picar-x/aiagentctrl_state.json"
_CAMERA_DEFAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aiagent_camera")


def _env_int(name: str, default: int) -> int:
    try:
        v = os.environ.get(name, str(default))
        return int(v)
    except Exception:
        return default


def _clamp(val: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(max_v, val))


def _safe_stop(px: Any) -> None:
    try:
        if px is None:
            return
        # Try best-effort stop using common names
        if hasattr(px, 'stop') and callable(getattr(px, 'stop')):
            px.stop()
        elif hasattr(px, 'motors') and hasattr(px.motors, 'set_power'):
            try:
                px.motors.set_power(0)
            except Exception:
                pass
    except Exception:
        pass


def _get_state_path() -> str:
    return os.environ.get("PICARX_STATE_FILE", _STATE_PATH_DEFAULT)


def _load_state() -> Dict[str, Any]:
    try:
        with open(_get_state_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    path = _get_state_path()
    tmp = path + ".tmp"
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, separators=(",", ":"))
        os.replace(tmp, path)
    except Exception:
        # fallback to home dir if /opt not writable
        try:
            home_fallback = os.path.join(os.path.expanduser("~"), ".aiagentctrl_state.json")
            with open(home_fallback, "w", encoding="utf-8") as f:
                json.dump(state, f, separators=(",", ":"))
        except Exception:
            pass


def _signal_handler(signum, frame):
    # Immediate stop and exit
    _safe_stop(_PX_OBJ)
    # Use standard shells' 128+signal exit code convention
    os._exit(128 + int(signum))


def _setup_signals():
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


def _ps_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _list_gpio_blocker_pids(timeout_s: float = 1.0):
    """Return a set of PIDs currently holding /dev/gpiochip* using fuser or lsof."""
    pids = set()
    cmds = [
        ['fuser', '-a', '/dev/gpiochip*'],
        ['lsof', '-nP', '/dev/gpiochip*'],
    ]
    for cmd in cmds:
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout_s, text=True)
            out = proc.stdout or ''
            for tok in out.replace("\n", " ").split():
                if tok.isdigit():
                    try:
                        pids.add(int(tok))
                    except Exception:
                        pass
        except Exception:
            continue
    # Filter out our own PID
    me = os.getpid()
    return {pid for pid in pids if pid != me}


def _free_gpio_blockers(grace_s: float = 0.8):
    """Attempt to terminate processes blocking GPIO to avoid 'GPIO busy'.

    Controlled by env PICARX_KILL_GPIO_BLOCKERS (default 1). Set to 0 to disable.
    """
    if os.environ.get('PICARX_KILL_GPIO_BLOCKERS', '1') == '0':
        return
    try:
        pids = sorted(_list_gpio_blocker_pids())
        # Also look for common daemon/candidates if nothing reported
        if not pids:
            try:
                ps = subprocess.run(['ps','aux'], stdout=subprocess.PIPE, text=True, timeout=1.0).stdout
            except Exception:
                ps = ''
            candidates = []
            for line in (ps or '').splitlines():
                low = line.lower()
                if 'pigpiod' in low or 'pigpio' in low or 'lgpio' in low or 'gpiozero' in low or 'robot_hat' in low or 'picarx' in low or 'vilib' in low:
                    parts = line.split()
                    if len(parts) > 1 and parts[1].isdigit():
                        candidates.append(int(parts[1]))
            me = os.getpid()
            pids = sorted({pid for pid in candidates if pid != me})
        for pid in pids:
            try:
                # Send SIGTERM first
                os.kill(pid, signal.SIGTERM)
            except Exception:
                continue
        if pids:
            time.sleep(grace_s)
        # Force kill remaining
        for pid in pids:
            if _ps_alive(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
    except Exception:
        # Best effort only
        pass


def _compat_patch_fusion_hat_modules():
    """Patch fusion_hat module layout differences for 3.0.x vs current.

    - Ensure fusion_hat.utils exposes LazyReader.
    - Provide fusion_hat.config module aliasing fusion_hat._config.Config.
    """
    try:
        import types, sys as _sys, contextlib, io
        # Patch utils for LazyReader, suppressing module's print
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                import fusion_hat.utils as fu  # type: ignore
            if not hasattr(fu, 'LazyReader'):
                try:
                    from fusion_hat._utils import LazyReader  # type: ignore
                    setattr(fu, 'LazyReader', LazyReader)
                except Exception:
                    pass
        except Exception:
            pass
        # Patch config module alias
        try:
            import importlib
            importlib.import_module('fusion_hat.config')
        except Exception:
            try:
                from fusion_hat import _config as _cfg  # type: ignore
                mod = types.ModuleType('fusion_hat.config')
                # Wrap to adapt signature: Config(config_file=...)
                def _CompatConfig(config_path: str = None, *a, **kw):  # type: ignore
                    # Allow both positional path and keyword config_file
                    if 'config_file' in kw:
                        return _cfg.Config(*a, **kw)
                    return _cfg.Config(*a, config_file=config_path, **kw)
                setattr(mod, 'Config', _CompatConfig)
                _sys.modules['fusion_hat.config'] = mod
            except Exception:
                pass
    except Exception:
        # Ignore; fake mode may not need this
        pass


def _compat_patch_picarx_music():
    """Provide a stub picarx.music to avoid I2C speaker init on import.

    The local PiCarX imports Music from picarx.music which, in turn, uses
    fusion_hat.music and enables the speaker via I2C. On systems without the
    HAT or I2C, this raises. Install a minimal stub before importing Picarx.
    """
    try:
        import types, sys as _sys
        if 'picarx.music' in _sys.modules:
            return  # already imported; avoid overriding

        class _StubMusic:
            def __init__(self):
                self._volume = 0
            def set_volume(self, v: int):
                self._volume = int(v)
            def stop(self):
                pass
            def play_sound_background(self, *a, **kw):
                pass

        class _StubSoundFiles:
            DOUBLE_HORN = 'DOUBLE_HORN'
            START_ENGINE = 'START_ENGINE'

        mod = types.ModuleType('picarx.music')
        setattr(mod, 'Music', _StubMusic)
        setattr(mod, 'SoundFiles', _StubSoundFiles)
        _sys.modules['picarx.music'] = mod
    except Exception:
        pass


def _maybe_set_i2c_bus_from_env_or_pi5():
    """Adjust fusion_hat I2C default bus.

    - If PICARX_I2C_BUS is set, use it.
    - Else, if /dev/i2c-11 exists (common on Pi 5), prefer 11.
    - Otherwise leave default (1).
    """
    try:
        import os as _os
        import fusion_hat._i2c as _i2c  # type: ignore
        env_bus = _os.environ.get('PICARX_I2C_BUS')
        if env_bus is not None and env_bus.strip() != '':
            _i2c.I2C.DEFAULT_BUS = int(env_bus)
            return
        if _os.path.exists('/dev/i2c-11'):
            _i2c.I2C.DEFAULT_BUS = 11
    except Exception:
        pass


# (Removed: fake hardware mock. This controller now targets real hardware only.)


def _resolve_picarx_class():
    """Best-effort to obtain the PiCar-X class across versions/layouts.

    Tries these in order:
      - picarx.Picarx
      - picarx.PiCarX
      - picarx.PicarX
      - picarx.picarx.Picarx / PiCarX / PicarX
    Returns the class object or raises ImportError.
    """
    import importlib

    candidates = [
        ('picarx', 'Picarx'),
        ('picarx', 'PiCarX'),
        ('picarx', 'PicarX'),
        ('picarx.picarx', 'Picarx'),
        ('picarx.picarx', 'PiCarX'),
        ('picarx.picarx', 'PicarX'),
    ]
    last_err = None
    for mod_name, cls_name in candidates:
        try:
            mod = importlib.import_module(mod_name)
            cls = getattr(mod, cls_name, None)
            if cls is not None:
                return cls
        except Exception as e:
            last_err = e
            continue
    # If we got here, try importing the package, then attribute from submodule
    # Some packages set attribute on __init__ at runtime
    try:
        import importlib
        pkg = importlib.import_module('picarx')
        sub = importlib.import_module('picarx.picarx')
        for name in ('Picarx', 'PiCarX', 'PicarX'):
            cls = getattr(pkg, name, None) or getattr(sub, name, None)
            if cls is not None:
                return cls
    except Exception as e:
        last_err = e
    if last_err:
        raise ImportError(f"Could not locate Picarx class: {last_err}")
    raise ImportError("Could not locate Picarx class")


def _call_method(px: Any, names, *args, **kwargs):
    """Attempt a method call by trying a list of candidate names."""
    for name in names:
        if hasattr(px, name) and callable(getattr(px, name)):
            return getattr(px, name)(*args, **kwargs)
    raise AttributeError(f"None of the methods exist: {names}")


def _do_drive(px: Any, speed: int, seconds: float, direction: str, max_speed: int) -> Dict[str, Any]:
    # Clamp speed for safety
    sp = int(_clamp(speed, 0, max_speed))

    # Some builds have forward/backward inverted. Default to inverted for this unit.
    invert = os.environ.get('PICARX_DRIVE_INVERT', '1') not in ('0', 'false', 'False')
    applied_direction = 'backward' if (invert and direction == 'forward') else \
        'forward' if (invert and direction == 'backward') else direction

    # Best-effort drive using common names; fallback to motors.set_power
    if applied_direction == 'forward':
        try:
            _call_method(px, ['forward'], sp)
        except Exception:
            if hasattr(px, 'motors') and hasattr(px.motors, 'set_power'):
                px.motors.set_power(sp, getattr(px, 'steering_angle', 0))
            else:
                raise
    else:
        try:
            _call_method(px, ['backward'], sp)
        except Exception:
            if hasattr(px, 'motors') and hasattr(px.motors, 'set_power'):
                px.motors.set_power(-sp, getattr(px, 'steering_angle', 0))
            else:
                raise

    if seconds > 0:
        time.sleep(seconds)

    return {
        'ok': True,
        'action': 'drive',
        'direction': direction,
        'applied_direction': applied_direction,
        'requested_speed': int(speed),
        'applied_speed': sp,
        'seconds': float(seconds),
        'max_speed': max_speed,
    }


def _do_steer(px: Any, angle: int, max_angle: int) -> Dict[str, Any]:
    a = int(_clamp(angle, -max_angle, max_angle))
    _call_method(px, ['set_steering_angle', 'steer', 'set_dir_servo_angle'], a)
    return {
        'ok': True,
        'action': 'steer',
        'requested_angle': int(angle),
        'applied_angle': a,
        'max_angle': max_angle,
    }


def _do_head(px: Any, pan: Optional[int], tilt: Optional[int], max_angle: int) -> Dict[str, Any]:
    applied: Dict[str, int] = {}
    state = _load_state()
    prev_head = state.get('head', {})

    target_pan = int(prev_head.get('pan', 0)) if pan is None else int(_clamp(pan, -max_angle, max_angle))
    target_tilt = int(prev_head.get('tilt', 0)) if tilt is None else int(_clamp(tilt, -max_angle, max_angle))

    _call_method(px, ['set_camera_pan_angle', 'set_cam_pan_angle', 'set_pan_angle'], target_pan)
    _call_method(px, ['set_camera_tilt_angle', 'set_cam_tilt_angle', 'set_tilt_angle'], target_tilt)

    if pan is not None:
        applied['pan'] = target_pan
    if tilt is not None:
        applied['tilt'] = target_tilt
    # Persist head state so it remains across commands
    try:
        state = _load_state()
        head = state.get('head', {})
        head['pan'] = target_pan
        head['tilt'] = target_tilt
        state['head'] = head
        _save_state(state)
    except Exception:
        pass
    return {
        'ok': True,
        'action': 'head',
        'requested_pan': None if pan is None else int(pan),
        'requested_tilt': None if tilt is None else int(tilt),
        'applied': applied,
        'max_angle': max_angle,
    }


def _with_timeout(fn, timeout_s: float, *args, **kwargs):
    """Run fn in a thread with a timeout; raise TimeoutError on expiry."""
    import threading
    res = {'val': None, 'err': None}
    def _run():
        try:
            res['val'] = fn(*args, **kwargs)
        except Exception as e:
            res['err'] = e
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        raise TimeoutError(f'operation timed out after {timeout_s:.2f}s')
    if res['err'] is not None:
        raise res['err']
    return res['val']


def _do_snapshot(px: Any, out_path: Optional[str] = None, vflip: bool = False, hflip: bool = False) -> Dict[str, Any]:
    """Capture an image.

    Backend selection:
    - Default is PICARX_SNAPSHOT_BACKEND=auto.
    - On Raspberry Pi OS (esp. Pi 5), prefer rpicam/libcamera tools when available because
      vilib can hang depending on camera stack.
    """

    backend = os.environ.get('PICARX_SNAPSHOT_BACKEND', 'auto').strip().lower()

    # rpicam-still / libcamera-still timeouts need to be a bit more forgiving than vilib.
    cam_timeout = float(os.environ.get('PICARX_CAMERA_TIMEOUT', '3.0'))
    warmup_s = float(os.environ.get('PICARX_CAMERA_WARMUP', '0.15'))

    # Determine output path
    if out_path:
        out_dir = os.path.dirname(out_path)
        base = os.path.splitext(os.path.basename(out_path))[0]
        out_name = base
    else:
        out_dir = _CAMERA_DEFAULT_DIR
        ts = datetime.now().strftime('%Y%m%d-%H%M%S')
        out_name = f'snap-{ts}'
        out_path = os.path.join(out_dir, out_name + '.jpg')
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        # Fallback to home Pictures directory
        home_dir = os.path.join(os.path.expanduser('~'), 'Pictures')
        os.makedirs(home_dir, exist_ok=True)
        out_dir = home_dir
        out_path = os.path.join(out_dir, out_name + '.jpg')

    # ---- Preferred backend: rpicam/libcamera ----
    def _try_rpicam() -> Optional[Dict[str, Any]]:
        exe = shutil.which('rpicam-still') or shutil.which('libcamera-still')
        if not exe:
            return None

        # Keep this fast by default; override via PICARX_RPICAM_TIMEOUT_MS.
        t_ms = int(os.environ.get('PICARX_RPICAM_TIMEOUT_MS', '800'))
        t_ms = max(200, min(t_ms, 10000))

        # Keep output quiet by default; override with PICARX_RPICAM_VERBOSE (0/1/2).
        verbose = int(os.environ.get('PICARX_RPICAM_VERBOSE', '0'))
        verbose = 0 if verbose < 0 else (2 if verbose > 2 else verbose)

        cam_index = os.environ.get('PICARX_CAMERA_INDEX', '').strip()

        # rpicam-still prints a warning (even at -v 0) when temporal denoise cannot be used.
        # Enabling ZSL avoids that warning and tends to improve snapshot reliability.
        # Default: enabled unless explicitly set to a falsey value.
        zsl_env = os.environ.get('PICARX_RPICAM_ZSL')
        if zsl_env is None:
            zsl = True
        else:
            zsl = str(zsl_env).strip().lower() in ('1', 'true', 'yes', 'on')

        cmd = [exe, '-n', '-v', str(verbose), '-t', str(t_ms), '-o', out_path]
        if cam_index:
            cmd += ['--camera', cam_index]
        if zsl:
            cmd += ['--zsl', '1']
        if vflip:
            cmd.append('--vflip')
        if hflip:
            cmd.append('--hflip')

        # Optionally retry once on failure/timeouts; helps with transient libcamera errors.
        retries = int(os.environ.get('PICARX_RPICAM_RETRIES', '1'))
        retries = max(0, min(retries, 3))

        def _run_once():
            return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=cam_timeout)

        try:
            last_out = ''
            for attempt in range(retries + 1):
                proc = _run_once()
                last_out = (proc.stdout or '').strip()
                if proc.returncode == 0:
                    # Basic sanity: file exists and is non-empty
                    try:
                        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                            ok_res = {
                                'ok': True,
                                'action': 'snapshot',
                                'backend': 'rpicam',
                                'backend_exe': os.path.basename(exe),
                                'path': out_path,
                                'cmd': cmd,
                                'artifacts': {
                                    'images': [out_path],
                                    'primary_image': out_path,
                                },
                                'session_context': {
                                    'kind': 'camera_snapshot',
                                    'image_path': out_path,
                                    'note': 'Inject this image into the active OpenClaw session for model vision context.',
                                },
                            }
                            if last_out and verbose > 0:
                                ok_res['log'] = last_out
                            return ok_res
                    except Exception:
                        pass
                    return {
                        'ok': False,
                        'action': 'snapshot',
                        'backend': 'rpicam',
                        'error': 'rpicam reported success but output file missing/empty',
                        'path': out_path,
                    }
                # brief backoff before retry
                if attempt < retries:
                    time.sleep(0.15)

            return {
                'ok': False,
                'action': 'snapshot',
                'backend': 'rpicam',
                'error': f'{os.path.basename(exe)} failed (code {proc.returncode}): {last_out}',
                'path': out_path,
            }
        except subprocess.TimeoutExpired:
            return {'ok': False, 'action': 'snapshot', 'backend': 'rpicam', 'error': f'rpicam timeout after {cam_timeout:.2f}s', 'path': out_path}
        except Exception as e:
            return {'ok': False, 'action': 'snapshot', 'backend': 'rpicam', 'error': str(e), 'path': out_path}

    if backend in ('auto', 'rpicam', 'libcamera'):
        r = _try_rpicam()
        if r is not None:
            if r.get('ok') or backend in ('rpicam', 'libcamera'):
                return r
            # auto-mode fallback continues below

    # ---- Fallback backend: vilib ----
    try:
        from vilib import Vilib
    except Exception as e:
        return {'ok': False, 'action': 'snapshot', 'backend': 'vilib', 'error': f'vilib import failed: {e}', 'path': out_path}

    try:
        # Ensure previous session is closed quickly
        try:
            _with_timeout(lambda: Vilib.camera_close(), 0.2)
        except Exception:
            pass

        # Start camera with timeout
        def _start():
            try:
                Vilib.camera_start(vflip=bool(vflip), hflip=bool(hflip))
            except TypeError:
                Vilib.camera_start()
        _with_timeout(_start, cam_timeout)

        # Short and bounded warm-up
        time.sleep(min(max(warmup_s, 0.0), 0.5))

        # Take photo with timeout; vilib expects (basename, dir)
        _with_timeout(Vilib.take_photo, cam_timeout, out_name, out_dir)

        # Attempt close, best effort
        try:
            _with_timeout(lambda: Vilib.camera_close(), 0.3)
        except Exception:
            pass
        snap_path = os.path.join(out_dir, out_name + '.jpg')
        return {
            'ok': True,
            'action': 'snapshot',
            'backend': 'vilib',
            'path': snap_path,
            'artifacts': {
                'images': [snap_path],
                'primary_image': snap_path,
            },
            'session_context': {
                'kind': 'camera_snapshot',
                'image_path': snap_path,
                'note': 'Inject this image into the active OpenClaw session for model vision context.',
            },
        }
    except TimeoutError as e:
        try:
            Vilib.camera_close()
        except Exception:
            pass
        return {'ok': False, 'action': 'snapshot', 'backend': 'vilib', 'error': str(e), 'path': os.path.join(out_dir, out_name + '.jpg')}
    except Exception as e:
        return {'ok': False, 'action': 'snapshot', 'backend': 'vilib', 'error': str(e), 'path': os.path.join(out_dir, out_name + '.jpg')}


def _do_ultrasonic(px: Any) -> Dict[str, Any]:
    distance_cm: Optional[float] = None
    err: Optional[str] = None
    try:
        if hasattr(px, 'ultrasonic'):
            u = px.ultrasonic
            # Avoid starting threads; read directly if possible
            if hasattr(u, 'read') and callable(getattr(u, 'read')):
                distance_cm = float(u.read())
            elif hasattr(u, 'get_value') and callable(getattr(u, 'get_value')):
                distance_cm = float(u.get_value())
        if distance_cm is None and hasattr(px, 'get_distance') and callable(px.get_distance):
            distance_cm = float(px.get_distance())
    except Exception as e:
        err = str(e)
    return {
        'ok': err is None,
        'action': 'ultrasonic',
        'distance_cm': distance_cm,
        'error': err,
    }


def _do_stop(px: Any) -> Dict[str, Any]:
    _safe_stop(px)
    return {'ok': True, 'action': 'stop'}


def _make_px():
    # Prefer local project path unless disabled
    # Optional explicit module dir (e.g. to point at a v2 checkout)
    module_dir = os.environ.get('PICARX_MODULE_DIR')
    added_module_dir = False
    if module_dir:
        sys.path.insert(0, os.path.abspath(module_dir))
        added_module_dir = True
    prefer_local = os.environ.get('PICARX_PREFER_LOCAL', '1') != '0'
    added_local = False
    if prefer_local:
        sys.path.insert(0, os.path.abspath('.'))
        added_local = True
    # Ensure fusion_hat compatibility before importing picarx module
    _compat_patch_fusion_hat_modules()
    _compat_patch_picarx_music()
    _maybe_set_i2c_bus_from_env_or_pi5()
    try:
        cls = _resolve_picarx_class()
        # Guard constructor with a short timeout to avoid hangs
        init_timeout = float(os.environ.get('PICARX_INIT_TIMEOUT', '1.0'))
        def _construct():
            return cls()
        return _with_timeout(_construct, init_timeout)
    except ImportError:
        # Fallback: try site-installed picarx by removing local path
        if added_local:
            try:
                sys.path.remove(os.path.abspath('.'))
            except ValueError:
                pass
        if added_module_dir:
            try:
                sys.path.remove(os.path.abspath(module_dir))
            except Exception:
                pass
        cls = _resolve_picarx_class()
        init_timeout = float(os.environ.get('PICARX_INIT_TIMEOUT', '1.0'))
        def _construct2():
            return cls()
        return _with_timeout(_construct2, init_timeout)


def _maybe_inject_snapshot_context(result: Dict[str, Any]) -> None:
    """Best-effort: inject snapshot image into current OpenClaw chat/session.

    Controlled by env:
    - PICARX_INJECT_SNAPSHOTS (default: 0 => disabled)
    - PICARX_INJECT_CHANNEL (e.g. whatsapp)
    - PICARX_INJECT_TARGET  (chat/user id)
    - PICARX_INJECT_MESSAGE (caption, optional)
    - PICARX_OPENCLAW_BIN   (default: openclaw)

    This should never turn a successful snapshot into a failed command.
    """
    try:
        if not isinstance(result, dict):
            return
        if not result.get("ok") or result.get("action") != "snapshot":
            return

        enabled = str(os.environ.get("PICARX_INJECT_SNAPSHOTS", "0")).strip().lower() in ("1", "true", "yes", "on")
        if not enabled:
            return

        path = str(result.get("path") or "").strip()
        if not path or not os.path.exists(path):
            result["injection"] = {"ok": False, "error": "missing_snapshot_path"}
            return

        channel = str(os.environ.get("PICARX_INJECT_CHANNEL", "")).strip()
        target = str(os.environ.get("PICARX_INJECT_TARGET", "")).strip()
        if not channel or not target:
            result["injection"] = {"ok": False, "error": "missing_target", "note": "Set PICARX_INJECT_CHANNEL and PICARX_INJECT_TARGET"}
            return

        message = str(os.environ.get("PICARX_INJECT_MESSAGE", "Camera snapshot (session context)."))
        openclaw_bin = str(os.environ.get("PICARX_OPENCLAW_BIN", "openclaw")).strip() or "openclaw"

        cmd = [
            openclaw_bin,
            "message",
            "send",
            "--channel",
            channel,
            "--target",
            target,
            "--message",
            message,
            "--media",
            path,
            "--json",
        ]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=45)
        out = (p.stdout or "").strip()
        inj = {
            "ok": p.returncode == 0,
            "channel": channel,
            "target": target,
            "path": path,
            "cmd": cmd,
            "rc": p.returncode,
            "out": out[:2000],
        }
        if p.returncode != 0 and "pairing required" in out.lower():
            inj["hint"] = "Local CLI is not paired for outbound messaging. Inject via active OpenClaw runtime/tooling instead."
        result["injection"] = inj
    except Exception as e:
        result["injection"] = {"ok": False, "error": str(e)}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Agent-friendly PiCar-X controller')
    parser.add_argument('--json', action='store_true', help='Print JSON output (single object)')

    sub = parser.add_subparsers(dest='command', required=True)

    p_drive = sub.add_parser('drive', help='Drive forward/backward at speed for seconds')
    p_drive.add_argument('--json', dest='json_sub', action='store_true', default=None, help=argparse.SUPPRESS)
    p_drive.add_argument('--speed', type=int, required=True, help='Speed 0..PICARX_MAX_SPEED')
    p_drive.add_argument('--seconds', type=float, default=0.0, help='Duration seconds (0=return immediately)')
    p_drive.add_argument('--direction', choices=['forward', 'backward'], required=True)

    p_steer = sub.add_parser('steer', help='Set steering angle')
    p_steer.add_argument('--json', dest='json_sub', action='store_true', default=None, help=argparse.SUPPRESS)
    p_steer.add_argument('--angle', type=int, required=True, help='Angle -PICARX_MAX_ANGLE..PICARX_MAX_ANGLE')

    p_head = sub.add_parser('head', help='Set head pan/tilt angles')
    p_head.add_argument('--json', dest='json_sub', action='store_true', default=None, help=argparse.SUPPRESS)
    p_head.add_argument('--pan', type=int, help='Pan angle -PICARX_MAX_ANGLE..PICARX_MAX_ANGLE')
    p_head.add_argument('--tilt', type=int, help='Tilt angle -PICARX_MAX_ANGLE..PICARX_MAX_ANGLE')

    p_ultra = sub.add_parser('ultrasonic', help='Read ultrasonic distance (cm)')
    p_ultra.add_argument('--json', dest='json_sub', action='store_true', default=None, help=argparse.SUPPRESS)
    p_stop = sub.add_parser('stop', help='Stop motors immediately')
    p_stop.add_argument('--json', dest='json_sub', action='store_true', default=None, help=argparse.SUPPRESS)

    p_snap = sub.add_parser('snapshot', help='Capture an image from the camera')
    p_snap.add_argument('--json', dest='json_sub', action='store_true', default=None, help=argparse.SUPPRESS)
    p_snap.add_argument('--path', type=str, help='Output image path (default: gpt_examples/aiagent_camera/snap-<ts>.jpg)')
    p_snap.add_argument('--vflip', action='store_true', help='Vertical flip')
    p_snap.add_argument('--hflip', action='store_true', help='Horizontal flip')

    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    # Support --json both before and after the subcommand. argparse subparsers
    # can overwrite the top-level flag, so we OR them here.
    json_out = bool(getattr(args, 'json', False) or getattr(args, 'json_sub', False))

    # Safety clamps (defaults)
    max_speed = _env_int('PICARX_MAX_SPEED', 60)
    max_angle = _env_int('PICARX_MAX_ANGLE', 35)
    # Fake mode removed: controller uses only real hardware.

    _setup_signals()

    global _PX_OBJ
    _PX_OBJ = None
    # Proactively clear GPIO blockers before initializing hardware
    _free_gpio_blockers()
    try:
        _PX_OBJ = _make_px()
    except TimeoutError as e:
        result = {'ok': False, 'action': args.command, 'cmd': args.command, 'error': {'code': 'init_timeout', 'detail': str(e)}}
        if json_out:
            print(json.dumps(result, separators=(',', ':'), ensure_ascii=False))
        else:
            print(result)
        return 1
    except Exception as e:
        result = {'ok': False, 'action': args.command, 'cmd': args.command, 'error': {'code': 'init_failed', 'detail': str(e)}}
        if json_out:
            print(json.dumps(result, separators=(',', ':'), ensure_ascii=False))
        else:
            print(result)
        return 1

    # Restore previously set head position so it persists across commands
    if args.command != 'head':
        try:
            st = _load_state().get('head', {})
            if 'pan' in st:
                _call_method(_PX_OBJ, ['set_camera_pan_angle', 'set_cam_pan_angle', 'set_pan_angle'], int(_clamp(st['pan'], -max_angle, max_angle)))
            if 'tilt' in st:
                _call_method(_PX_OBJ, ['set_camera_tilt_angle', 'set_cam_tilt_angle', 'set_tilt_angle'], int(_clamp(st['tilt'], -max_angle, max_angle)))
        except Exception:
            pass

    result: Dict[str, Any] = {'ok': False}

    try:
        if args.command == 'drive':
            # Additional immediate clamp for acceptance live tests if user forgets
            seconds = float(args.seconds)
            # Execute
            result = _do_drive(_PX_OBJ, args.speed, seconds, args.direction, max_speed)

        elif args.command == 'steer':
            result = _do_steer(_PX_OBJ, args.angle, max_angle)

        elif args.command == 'head':
            result = _do_head(_PX_OBJ, args.pan, args.tilt, max_angle)

        elif args.command == 'ultrasonic':
            result = _do_ultrasonic(_PX_OBJ)

        elif args.command == 'stop':
            result = _do_stop(_PX_OBJ)

        elif args.command == 'snapshot':
            # CLI flags override env defaults.
            vflip = bool(getattr(args, 'vflip', False)) or (str(os.environ.get('PICARX_CAMERA_VFLIP', '0')).strip().lower() in ('1', 'true', 'yes', 'on'))
            hflip = bool(getattr(args, 'hflip', False)) or (str(os.environ.get('PICARX_CAMERA_HFLIP', '0')).strip().lower() in ('1', 'true', 'yes', 'on'))
            result = _do_snapshot(_PX_OBJ, getattr(args, 'path', None), vflip, hflip)

        else:
            raise ValueError(f"Unknown command: {args.command}")

        # Optional session-context injection for camera snapshots.
        _maybe_inject_snapshot_context(result)

        result.setdefault('max_speed', max_speed)
        result.setdefault('max_angle', max_angle)
        result.setdefault('cmd', result.get('action', args.command))
        result.setdefault('requested', {})
        result.setdefault('applied', {})
        result.setdefault('artifacts', {})
        if isinstance(result.get('error'), str):
            result['error'] = {'code': 'command_failed', 'detail': result['error']}

    except SystemExit:
        raise
    except Exception as e:
        result = {'ok': False, 'action': args.command, 'cmd': args.command, 'error': {'code': 'command_failed', 'detail': str(e)}}
    finally:
        # Dead-man stop after each command
        _safe_stop(_PX_OBJ)

    result.setdefault('cmd', result.get('action', args.command))
    result.setdefault('requested', {})
    result.setdefault('applied', {})
    result.setdefault('artifacts', {})

    if json_out:
        print(json.dumps(result, separators=(',', ':'), ensure_ascii=False))
    else:
        # Human-readable single-line dict
        print(result)
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
