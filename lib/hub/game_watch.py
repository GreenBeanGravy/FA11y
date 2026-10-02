"""Watch for Fortnite starting and stopping.

Polls the process list on a daemon thread and reports changes on the wx
main thread, so the hub can hide itself when a match is about to start.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import win32gui
import win32process

logger = logging.getLogger(__name__)

GAME_PROCESSES = {"fortniteclient-win64-shipping.exe"}
POLL_SECONDS = 2.0

_running = False


def is_fortnite_running() -> bool:
    """Last known state; cheap enough to call from the UI."""
    return _running


def _scan() -> bool:
    import psutil
    for proc in psutil.process_iter(["name"]):
        name = (proc.info.get("name") or "").lower()
        if name in GAME_PROCESSES:
            return True
    return False


def is_fortnite_foreground() -> bool:
    try:
        import psutil
        hwnd = win32gui.GetForegroundWindow()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return psutil.Process(pid).name().lower() in GAME_PROCESSES
    except Exception:
        return False


def focus_fortnite() -> bool:
    """Bring the Fortnite window to the foreground. Returns False if not found."""
    try:
        from lib.utilities.window_utils import focus_window_by_process
        return bool(focus_window_by_process("FortniteClient-Win64-Shipping.exe"))
    except Exception as e:
        logger.debug(f"Could not focus Fortnite: {e}")
        return False


class GameWatcher:
    def __init__(self, on_change: Callable[[bool], None]):
        self._on_change = on_change
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        global _running
        _running = _scan()
        self._thread = threading.Thread(target=self._loop, name="GameWatcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        global _running
        import wx
        while not self._stop.wait(POLL_SECONDS):
            try:
                now = _scan()
            except Exception as e:
                logger.debug(f"Process scan failed: {e}")
                continue
            if now != _running:
                _running = now
                wx.CallAfter(self._on_change, now)
