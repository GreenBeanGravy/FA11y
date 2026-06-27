"""
Display-mode announcement action.

``announce_display_mode`` — lalt+r hotkey; reads Fortnite's local log to find
the most recent window mode (Fullscreen / Windowed Fullscreen / Windowed) and
render resolution, then announces them in the order window-mode, resolution.

Fortnite writes a small block to ``FortniteGame.log`` every time the video
settings are applied (and on most map / menu transitions), for example::

    - Resolution: 1920x1080@200.0Hz at 100.0% 3D Resolution
    - Fullscreen mode: WindowedFullscreen, VSync: 0

These lines carry no leading timestamp, so we simply scan for the *last*
occurrence of each. Only the live ``FortniteGame.log`` is read (not the rotated
backups), and we read a tail of the file first since these lines are emitted
frequently — falling back to a full scan if the tail doesn't contain them.
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


def announce_display_mode() -> None:
    """Announce the current window mode then resolution from the Fortnite log."""
    speaker = state.speaker

    text = _read_log_text()
    if text is None:
        speaker.speak("Fortnite log not found.")
        return

    # If the tail didn't contain the block, fall back to a full scan.
    mode, res = _parse_display_mode(text)
    if mode is None and res is None:
        try:
            with open(_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                mode, res = _parse_display_mode(f.read())
        except OSError as e:
            state.logger.error(f"Could not read Fortnite log: {e}")

    if mode is None and res is None:
        speaker.speak("Could not determine display mode from the Fortnite log.")
        return

    parts = []
    if mode is not None:
        parts.append(mode)
    if res is not None:
        parts.append(f"{res[0]} by {res[1]}")

    speaker.speak(", ".join(parts))
