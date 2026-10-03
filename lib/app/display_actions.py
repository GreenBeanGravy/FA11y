"""
Game setup checks.

Reads Fortnite's local log to find the most recent window mode and render
resolution.

Fortnite writes a small block to ``FortniteGame.log`` every time the video
settings are applied (and on most map / menu transitions), for example::

    - Resolution: 1920x1080@200.0Hz at 100.0% 3D Resolution
    - Fullscreen mode: WindowedFullscreen, VSync: 0

These lines carry no leading timestamp, so we simply scan for the *last*
occurrence of each. Only the live ``FortniteGame.log`` is read (not the rotated
backups), and we read a tail of the file first since these lines are emitted
frequently - falling back to a full scan if the tail doesn't contain them.
"""
from __future__ import annotations

import os
import re

from lib.app import state

# Live Fortnite log on Windows. Other platforms can't run Fortnite.
_LOG_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "FortniteGame", "Saved", "Logs", "FortniteGame.log",
)

# Read at most this many bytes from the end first; the resolution / fullscreen
# block is written often enough that the tail almost always contains it.
_TAIL_BYTES = 5 * 1024 * 1024

_RE_RESOLUTION = re.compile(r"Resolution:\s*(\d+)x(\d+)")
_RE_FULLSCREEN = re.compile(r"Fullscreen mode:\s*(\w+)")

# Map Fortnite's internal mode names to spoken phrases.
_MODE_NAMES = {
    "fullscreen": "Fullscreen",
    "windowedfullscreen": "Windowed Fullscreen",
    "windowed": "Windowed",
}


def _read_log_text() -> str | None:
    """Return the tail of the live Fortnite log, or the whole file if small.

    Returns ``None`` if the log can't be read at all.
    """
    try:
        size = os.path.getsize(_LOG_PATH)
        with open(_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            if size > _TAIL_BYTES:
                f.seek(size - _TAIL_BYTES)
                f.readline()  # discard the partial first line
            return f.read()
    except OSError as e:
        state.logger.error(f"Could not read Fortnite log: {e}")
        return None


def _parse_display_mode(text: str):
    """Return ``(mode_phrase, width, height)`` from the last matching lines.

    Any piece that can't be found comes back as ``None``.
    """
    mode = None
    res = None

    fs_matches = _RE_FULLSCREEN.findall(text)
    if fs_matches:
        raw = fs_matches[-1]
        mode = _MODE_NAMES.get(raw.lower(), raw)

    res_matches = _RE_RESOLUTION.findall(text)
    if res_matches:
        res = res_matches[-1]  # (width, height)

    return mode, res


_START_FORTNITE = "Start Fortnite once so FA11y can read its display settings."
_RES_FIX = "Set Resolution to 1920 by 1080 in Fortnite's display settings."


def _check(name: str, status: str, detail: str, fix: str = "") -> dict:
    """One game check. status is ok, problem or unknown; text is what a screen reader reads."""
    label = {"ok": "OK.", "problem": "Problem.", "unknown": ""}[status]
    text = f"{name}: {detail}." + (f" {label}" if label else "") + (f" {fix}" if fix else "")
    return {"name": name, "status": status, "detail": detail, "fix": fix, "text": text}


def _is_16_9(width: int, height: int) -> bool:
    return height > 0 and abs(width * 9 - height * 16) <= max(width, height) // 100


def _window_mode_check(mode: str | None) -> dict:
    if mode is None:
        return _check("Window mode", "unknown", "Unknown", _START_FORTNITE)
    if mode == "Windowed":
        return _check("Window mode", "problem", mode, "Set Window Mode to Fullscreen in Fortnite's display settings.")
    return _check("Window mode", "ok", mode)


def _game_resolution_check(res) -> dict:
    if res is None:
        return _check("Game resolution", "unknown", "Unknown", _START_FORTNITE)
    width, height = int(res[0]), int(res[1])
    detail = f"{width} by {height}"
    if not _is_16_9(width, height):
        return _check("Game resolution", "problem", detail,
                      f"FA11y needs a 16 by 9 resolution. {_RES_FIX}")
    if (width, height) != (1920, 1080):
        return _check("Game resolution", "problem", detail,
                      f"16 by 9 works for most features, but some read fixed 1920 by 1080 positions. {_RES_FIX}")
    return _check("Game resolution", "ok", detail)


def _screen_resolution_check(size) -> dict:
    if size is None:
        return _check("Screen resolution", "unknown", "Unknown", "Windows didn't report the display size.")
    width, height = int(size[0]), int(size[1])
    detail = f"{width} by {height}"
    if not _is_16_9(width, height):
        return _check("Screen resolution", "problem", detail,
                      "FA11y needs a 16 by 9 screen. Choose a 16 by 9 resolution in Windows display settings.")
    return _check("Screen resolution", "ok", detail)


def _faker_check(connected: bool | None) -> dict:
    if connected is None:
        return _check("FakerInput driver", "unknown", "Unknown", "FA11y couldn't check the driver.")
    if connected:
        return _check("FakerInput driver", "ok", "Connected")
    return _check("FakerInput driver", "problem", "Not connected",
                  "Mouse movement and clicks need it. Restart FA11y, which installs the driver if it is missing.")


def build_game_checks(log_text: str | None, screen_size=None, faker_connected: bool | None = None) -> list[dict]:
    """The game setup checks as data: name, status (ok, problem, unknown), detail, fix, text."""
    mode, res = _parse_display_mode(log_text or "")
    return [
        _window_mode_check(mode),
        _game_resolution_check(res),
        _screen_resolution_check(screen_size),
        _faker_check(faker_connected),
    ]


def primary_screen_size():
    """The primary display's real pixel size from Windows, or None."""
    try:
        import ctypes
        from ctypes import wintypes

        class DEVMODE(ctypes.Structure):
            _fields_ = [
                ("dmDeviceName", wintypes.WCHAR * 32), ("dmSpecVersion", wintypes.WORD),
                ("dmDriverVersion", wintypes.WORD), ("dmSize", wintypes.WORD),
                ("dmDriverExtra", wintypes.WORD), ("dmFields", wintypes.DWORD),
                ("dmPosition", ctypes.c_long * 2), ("dmDisplayOrientation", wintypes.DWORD),
                ("dmDisplayFixedOutput", wintypes.DWORD), ("dmColor", ctypes.c_short),
                ("dmDuplex", ctypes.c_short), ("dmYResolution", ctypes.c_short),
                ("dmTTOption", ctypes.c_short), ("dmCollate", ctypes.c_short),
                ("dmFormName", wintypes.WCHAR * 32), ("dmLogPixels", wintypes.WORD),
                ("dmBitsPerPel", wintypes.DWORD), ("dmPelsWidth", wintypes.DWORD),
                ("dmPelsHeight", wintypes.DWORD), ("dmDisplayFlags", wintypes.DWORD),
                ("dmDisplayFrequency", wintypes.DWORD), ("dmICMMethod", wintypes.DWORD),
                ("dmICMIntent", wintypes.DWORD), ("dmMediaType", wintypes.DWORD),
                ("dmDitherType", wintypes.DWORD), ("dmReserved1", wintypes.DWORD),
                ("dmReserved2", wintypes.DWORD), ("dmPanningWidth", wintypes.DWORD),
                ("dmPanningHeight", wintypes.DWORD),
            ]

        mode = DEVMODE()
        mode.dmSize = ctypes.sizeof(DEVMODE)
        if ctypes.windll.user32.EnumDisplaySettingsW(None, -1, ctypes.byref(mode)):
            return int(mode.dmPelsWidth), int(mode.dmPelsHeight)
    except Exception as e:
        state.logger.error(f"Could not read the display size: {e}")
    return None


def faker_connected() -> bool | None:
    """Whether the FakerInput driver is connected (tries to connect if it isn't yet)."""
    try:
        from lib.mouse_passthrough import faker_input
        faker_input.ensure_loaded()
        if faker_input.is_initialized():
            return True
        if not faker_input.is_available():
            return False
        return bool(faker_input.initialize_fakerinput(100))
    except Exception as e:
        state.logger.error(f"Could not check FakerInput: {e}")
        return None


def game_checks() -> list[dict]:
    """Run the game setup checks against Fortnite's log, Windows and FakerInput."""
    text = _read_log_text()
    if text is not None and _parse_display_mode(text) == (None, None):
        try:
            with open(_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            pass
    return build_game_checks(text, primary_screen_size(), faker_connected())
