"""
Cumulative damage-number reader (PaddleOCR).

When the ``DamageReader`` toggle is on, this monitor OCR-reads the numbers near
the center of the screen (where Fortnite hit-damage numbers pop) at up to
10 fps and tracks each *cumulative* damage burst. Fortnite damage counts UP on
the same floating number while you keep landing hits, then fades; this groups
those rising readings into one burst and remembers the peak.

A burst is only spoken AFTER it finishes — once the number stops counting up
(or disappears) for the count-up window (1 s). The ``Speak Last Damage`` keybind
re-announces the most recently completed burst.

Detection only runs when ALL of these hold:
  * ``DamageReader`` toggle is on,
  * Fortnite is the focused window, AND
  * the game is in active gameplay — i.e. the most recent
    ``LogUIActionRouter`` input-mode line in FortniteGame.log is
    ``New (ECommonInputMode::Game)`` (not a menu / inventory / map / lobby).

Plus OCR-noise guards: won't START a burst on a value already in the thousands,
ignores readings that jump > 500 above the current value (waits/re-checks), and
de-dupes identical announcements within 1.5 s.

OCR engine is PaddleOCR — GPU when paddle is a CUDA build, auto-falling back to
CPU if the GPU path throws.
"""
from __future__ import annotations

import os
import re
import time
import threading

import numpy as np
from accessible_output2.outputs.auto import Auto

from lib.monitors.base import BaseMonitor
from lib.managers.screenshot_manager import capture_region
from lib.utilities.utilities import read_config, get_config_boolean
from lib.utilities.window_utils import get_active_window_title

# Sanity bound: numeric detections above this are OCR noise and are discarded.
NUMBER_MAX = 9999
# A new burst may not START at/above this (real hits start small, then add up).
NEW_BURST_MAX = 1000
# Largest believable jump between consecutive readings of the same burst.
MAX_STEP = 500

# Capture-rate cap and the central capture box (fraction of screen per side).
TARGET_FPS = 10
REGION_HALF_W_FRAC = 0.18
REGION_HALF_H_FRAC = 0.18

# Count-up window: a burst closes (and is spoken) after this long with no
# increase / the number disappearing.
COUNT_UP_WINDOW_S = 1.0
# Suppress speaking the same total again within this window.
DEDUP_WINDOW_S = 1.5

# Fortnite log — used to gate detection to active gameplay via the same
# UIActionRouter input-mode lines MatchEventMonitor reads.
_LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                        "FortniteGame", "Saved", "Logs")
_LOG_PATH = os.path.join(_LOG_DIR, "FortniteGame.log")
# Most recent input mode: "Game" during gameplay, "Menu"/"All" in UI/lobby.
_RE_INPUT_MODE = re.compile(r"New \(ECommonInputMode::(\w+)\)")

_DIGITS = re.compile(r"\D")


def _enable_bundled_cudnn():
    """Make paddle's CUDA/cuDNN DLLs loadable from pip packages.

    paddlepaddle-gpu links cuDNN at predictor init even for CPU ops, so without
    these dirs the GPU wheel fails on BOTH gpu and cpu. Pieces needed:
      * cudnn64_8.dll + cudnn_*64_8 siblings  -> nvidia-cudnn-cu11
      * cudart64_110.dll                      -> nvidia-cuda-runtime-cu11
      * cublas64_11.dll / cublasLt64_11.dll   -> nvidia-cublas-cu11
      * zlibwapi.dll (cuDNN 8 dependency)     -> bundled with torch
    paddle's loader resolves these by NAME via PATH (it does NOT honor
    add_dll_directory), so we prepend the dirs to PATH. All no-ops if absent.
    """
    import glob
    import site
    roots = []
    try:
        roots.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        roots.append(site.getusersitepackages())
    except Exception:
        pass

    dirs = []
    for root in roots:
        if not root:
            continue
        dirs.extend(glob.glob(os.path.join(root, "nvidia", "*", "bin")))
        dirs.append(os.path.join(root, "torch", "lib"))

    seen = []
    for d in dirs:
        if d and d not in seen and os.path.isdir(d):
            seen.append(d)
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(d)
                except Exception:
                    pass
    if seen:
        os.environ["PATH"] = os.pathsep.join(
            seen + [os.environ.get("PATH", "")])


def _to_int(text):
    digits = _DIGITS.sub("", str(text))
    return int(digits) if digits else None


class DamageTracker:
    """Tracks a single cumulative number (Fortnite damage).

    A burst starts the first time a believable number is seen (below
    ``NEW_BURST_MAX``). While it keeps counting UP by a believable step
    (<= ``MAX_STEP``) the burst extends. A reading that jumps more than
    ``MAX_STEP`` is ignored — the stall timer keeps running so we either get a
    sane next reading or the burst closes on its real peak. If nothing increases
    within ``timeout`` seconds the burst closes and its peak is reported; the
    just-closed value is then suppressed so only a genuinely lower new hit
    starts a fresh burst.
    """

    def __init__(self, timeout: float = COUNT_UP_WINDOW_S):
        self.timeout = timeout
        self.active = None            # dict(cur, peak, start, last_up, ticks)
        self._suppress_val = None
        self._suppress_until = 0.0

    def reset(self):
        self.active = None
        self._suppress_val = None
        self._suppress_until = 0.0

    def _close(self, now):
        a = self.active
        self.active = None
        self._suppress_val = a["peak"]
        self._suppress_until = now + self.timeout
        return {"peak": a["peak"], "ticks": a["ticks"],
                "duration": max(0.0, a["last_up"] - a["start"])}

    def update(self, values, now):
        """Feed this frame's integers. Returns (active_value, completed_events)."""
        events = []
        if self.active and (now - self.active["last_up"] > self.timeout):
            events.append(self._close(now))

        if values:
            if self.active:
                cur = self.active["cur"]
                # Only believable increments (>cur but no more than MAX_STEP).
                valid = [v for v in values if cur < v <= cur + MAX_STEP]
                if valid:                        # counted up -> extend burst
                    v = max(valid)
                    self.active["cur"] = v
                    self.active["peak"] = max(self.active["peak"], v)
                    self.active["last_up"] = now
                    self.active["ticks"] += 1
                # else: nothing believable (stale, or a >500 spike) -> wait.
            else:
                # New burst: ignore values already in the thousands, and any
                # value still being suppressed from the previous burst.
                cand = [v for v in values if v < NEW_BURST_MAX]
                if (self._suppress_val is not None
                        and now < self._suppress_until):
                    cand = [v for v in cand if v < self._suppress_val]
                if cand:
                    v = max(cand)
                    self.active = dict(cur=v, peak=v, start=now,
                                       last_up=now, ticks=1)

        return (self.active["cur"] if self.active else None), events


class DamageMonitor(BaseMonitor):
    """Polls the central screen region for damage numbers at up to 10 fps."""

    _THREAD_NAME = "DamageMonitor"

    def __init__(self) -> None:
        super().__init__()
        self.speaker = Auto()
        self.tracker = DamageTracker(timeout=COUNT_UP_WINDOW_S)
        self._lock = threading.Lock()
        self._last_damage = None
        self._last_spoken_val = None
        self._last_spoken_t = 0.0
        self._screen = self._screen_size()
        self._ocr = None              # lazy PaddleOCR instance
        self._ocr_failed = False
        self._device = "cpu"

        # Fortnite-log UI-state follower (gates detection to gameplay). Uses the
        # same UIActionRouter log signatures FA11y's inventory/map/sidebar/menu
        # detection uses; _gameplay is True only when the LATEST UI-determining
        # line is the gameplay one, and False on any inventory/map/sidebar/
        # lobby/menu line.
        self._log_fp = None
        self._log_inode = None
        self._log_pending = b""
        self._gameplay = False

    # ------------------------------------------------------------------
    @staticmethod
    def _screen_size():
        try:
            import win32api
            return (win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1))
        except Exception:
            return (1920, 1080)

    def _region(self):
        w, h = self._screen
        hw = int(w * REGION_HALF_W_FRAC)
        hh = int(h * REGION_HALF_H_FRAC)
        cx, cy = w // 2, h // 2
        return {"left": cx - hw, "top": cy - hh,
                "width": 2 * hw, "height": 2 * hh}

    @staticmethod
    def _enabled() -> bool:
        try:
            return get_config_boolean(read_config(), "DamageReader", False)
        except Exception:
            return False

    @staticmethod
    def _game_focused() -> bool:
        try:
            return "fortnite" in (get_active_window_title() or "").lower()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Fortnite-log UI-state follower (same signatures as FA11y's UI detection)
    # ------------------------------------------------------------------
    @staticmethod
    def _ui_state_from_line(line: str):
        """Map a UIActionRouter log line to a gameplay boolean.

        Returns True if the line means "input is on the game viewport"
        (gameplay HUD), False if it means a UI surface (inventory / map /
        sidebar / lobby tab / any other panel, or a non-Game input mode), and
        None if the line says nothing about UI state. Mirrors the exact
        signatures MatchEventMonitor uses for inventory/menu detection.
        """
        if "LogUIActionRouter:" not in line:
            return None
        # Gameplay: input handed back to the game viewport.
        if "New (ECommonInputMode::Game)" in line:
            return True
        if "AthenaHUD" in line and (
                "focusing the game viewport" in line
                or "Applying input config for leaf-most node [AthenaHUD" in line):
            return True
        # Any UI panel applying its input config = inventory/map/sidebar/lobby.
        if "Applying input config for leaf-most node [" in line:
            return False
        # Explicit non-Game input mode (Menu / All).
        m = _RE_INPUT_MODE.search(line)
        if m:
            return m.group(1) == "Game"
        return None

    def _seed_gameplay(self):
        """Learn current gameplay state from the existing log. Scans backward
        from the end in 1 MB chunks (UI lines can sit far behind unrelated log
        spam) and uses the latest UI-determining line found."""
        try:
            chunk = 1024 * 1024
            overlap = b""
            with open(_LOG_PATH, "rb") as f:
                f.seek(0, os.SEEK_END)
                pos = f.tell()
                while pos > 0:
                    step = min(chunk, pos)
                    pos -= step
                    f.seek(pos)
                    data = (f.read(step) + overlap).decode("utf-8", "replace")
                    state = None
                    for line in data.split("\n"):
                        s = self._ui_state_from_line(line)
                        if s is not None:
                            state = s            # keep latest within the chunk
                    if state is not None:
                        self._gameplay = state
                        return
                    overlap = data[:512].encode("utf-8", "replace")
        except Exception:
            pass

    def _open_log(self) -> bool:
        try:
            if not os.path.exists(_LOG_PATH):
                return False
            self._seed_gameplay()
            self._log_fp = open(_LOG_PATH, "rb")
            self._log_fp.seek(0, os.SEEK_END)
            self._log_inode = os.stat(_LOG_PATH).st_ino
            self._log_pending = b""
            return True
        except Exception:
            self._log_fp = None
            return False

    def _poll_log(self):
        """Advance the log tail and update gameplay state (latest line wins)."""
        if self._log_fp is None:
            self._open_log()
            return
        try:
            if os.stat(_LOG_PATH).st_ino != self._log_inode:  # rotated
                try:
                    self._log_fp.close()
                except Exception:
                    pass
                self._gameplay = False
                self._open_log()
                return
        except OSError:
            return
        try:
            chunk = self._log_fp.read()
        except Exception:
            return
        if not chunk:
            return
        buf = self._log_pending + chunk
        lines = buf.split(b"\n")
        self._log_pending = lines[-1]
        for raw in lines[:-1]:
            if b"LogUIActionRouter:" not in raw:
                continue
            s = self._ui_state_from_line(raw.decode("utf-8", errors="replace"))
            if s is not None:
                self._gameplay = s

    def _in_gameplay(self) -> bool:
        return self._gameplay

    # ------------------------------------------------------------------
    # PaddleOCR (lazy; GPU first with warmup, auto-fallback to CPU)
    # ------------------------------------------------------------------
    @staticmethod
    def _build_ocr(paddle, device):
        if paddle is not None:
            paddle.set_device(device)
        from paddleocr import PaddleOCR
        for kwargs in (dict(lang="en", use_angle_cls=False, show_log=False),
                       dict(lang="en", use_angle_cls=False),
                       dict(lang="en")):
            try:
                return PaddleOCR(**kwargs)
            except Exception:  # noqa: BLE001
                continue
        return None

    @staticmethod
    def _warmup(ocr):
        # Forces the predictor to actually run, surfacing runtime DLL issues
        # (e.g. missing cuDNN on a GPU build) at init instead of every frame.
        dummy = np.zeros((48, 160, 3), dtype=np.uint8)
        dummy[12:36, 10:150] = 255
        try:
            ocr.ocr(dummy, cls=False)
        except TypeError:
            ocr.ocr(dummy)

    def _ensure_ocr(self) -> bool:
        if self._ocr is not None:
            return True
        if self._ocr_failed:
            return False

        try:
            import paddleocr  # noqa: F401
        except Exception as e:  # noqa: BLE001
            print(f"DamageReader: PaddleOCR not installed ({e}); disabling. "
                  f"pip install paddleocr==2.7.3 paddlepaddle-gpu==2.6.2")
            self._ocr_failed = True
            return False

        _enable_bundled_cudnn()  # make CUDA/cuDNN DLLs discoverable on PATH

        try:
            import paddle
        except Exception:
            paddle = None

        want_gpu = False
        if paddle is not None:
            try:
                want_gpu = (paddle.device.is_compiled_with_cuda()
                            and paddle.device.cuda.device_count() > 0)
            except Exception:
                want_gpu = False

        devices = ["gpu:0", "cpu"] if want_gpu else ["cpu"]
        for device in devices:
            print(f"DamageReader: loading PaddleOCR on {device}...")
            try:
                ocr = self._build_ocr(paddle, device)
                if ocr is None:
                    print(f"DamageReader: construct failed on {device}.")
                    continue
                self._warmup(ocr)        # may raise on bad GPU runtime
            except Exception as e:  # noqa: BLE001
                first = str(e).splitlines()[0] if str(e) else type(e).__name__
                print(f"DamageReader: {device} unusable ({first}); "
                      f"trying next device.")
                continue
            self._ocr = ocr
            self._device = device
            print(f"DamageReader: PaddleOCR ready on {device}.")
            return True

        print("DamageReader: PaddleOCR failed on all devices; disabling.")
        self._ocr_failed = True
        return False

    def _read_numbers(self, img):
        vals = []
        try:
            try:
                raw = self._ocr.ocr(img, cls=False)
            except TypeError:
                raw = self._ocr.ocr(img)
        except Exception as e:  # noqa: BLE001
            print(f"DamageReader OCR error: {str(e).splitlines()[0]}")
            return vals
        if not raw:
            return vals
        page = raw[0]
        if not page:
            return vals
        for line in page:
            try:
                text = line[1][0]
            except Exception:
                continue
            v = _to_int(text)
            if v is not None and 0 <= v <= NUMBER_MAX:
                vals.append(v)
        return vals

    # ------------------------------------------------------------------
    # Keybind handler — re-announce the last completed burst (always speaks).
    # ------------------------------------------------------------------
    def speak_last_damage(self) -> None:
        if not self._enabled():
            self.speaker.speak("Damage reader is off")
            return
        with self._lock:
            dmg = self._last_damage
        if dmg is None:
            self.speaker.speak("No damage recorded")
        else:
            self.speaker.speak(str(dmg))

    def _announce(self, peak: int) -> None:
        """Speak a completed burst, de-duping identical totals within 1.5 s."""
        with self._lock:
            self._last_damage = peak
        now = time.monotonic()
        if (peak == self._last_spoken_val
                and now - self._last_spoken_t < DEDUP_WINDOW_S):
            return
        self._last_spoken_val = peak
        self._last_spoken_t = now
        self.speaker.speak(str(peak))

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------
    def _monitor_loop(self) -> None:
        period = 1.0 / TARGET_FPS
        while not self.stop_event.is_set():
            t0 = time.perf_counter()
            try:
                if self.wizard_paused():
                    if self.stop_event.wait(0.5):
                        return
                    continue

                if not self._enabled():
                    self.tracker.reset()
                    if self.stop_event.wait(0.5):
                        return
                    continue

                if not self._ensure_ocr():
                    if self.stop_event.wait(1.0):
                        return
                    continue

                # Keep the log-derived input mode fresh every tick.
                self._poll_log()

                # Gate: only read in active gameplay AND while Fortnite is
                # focused. Reset so a tab-out / menu mid-burst leaves no stale
                # state.
                if not self._game_focused() or not self._in_gameplay():
                    self.tracker.reset()
                    if self.stop_event.wait(0.2):
                        return
                    continue

                img = capture_region(self._region(), "bgr")
                vals = self._read_numbers(img) if img is not None else []

                _active, events = self.tracker.update(vals, time.monotonic())
                for ev in events:
                    print(f"Damage burst: {ev['peak']} "
                          f"({ev['ticks']} ticks, {ev['duration']:.2f}s)")
                    self._announce(ev["peak"])
            except Exception as e:  # noqa: BLE001
                print(f"Damage reader error: {e}")

            # Cap to TARGET_FPS; sleep the remainder while honoring shutdown.
            dt = time.perf_counter() - t0
            if self.stop_event.wait(max(0.0, period - dt)):
                return


# Module-level singleton (mirrors the other monitors).
damage_monitor = DamageMonitor()
