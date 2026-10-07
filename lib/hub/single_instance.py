"""Keep FA11y to one running copy.

The first copy owns a named mutex and waits on a named event. A second
copy finds the mutex taken, sets the event (which brings the first copy's
window forward) and exits.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

import win32api
import win32event
import winerror

MUTEX_NAME = "Local\\FA11y.SingleInstance"
SUMMON_EVENT_NAME = "Local\\FA11y.Summon"

_mutex = None


def acquire() -> bool:
    """Return True if this is the only running FA11y, else wake the other one and return False."""
    global _mutex
    if _mutex is not None:
        return True  # this copy already owns it
    mutex = win32event.CreateMutex(None, False, MUTEX_NAME)
    if win32api.GetLastError() != winerror.ERROR_ALREADY_EXISTS:
        _mutex = mutex
        return True
    try:
        event = win32event.OpenEvent(win32event.EVENT_MODIFY_STATE, False, SUMMON_EVENT_NAME)
        win32event.SetEvent(event)
    except Exception:
        pass
    return False


def listen(on_summon: Callable[[], None], stop: threading.Event) -> Optional[threading.Thread]:
    """Call on_summon (from a worker thread) whenever another copy starts."""
    event = win32event.CreateEvent(None, False, False, SUMMON_EVENT_NAME)

    def loop():
        while not stop.is_set():
            if win32event.WaitForSingleObject(event, 500) == win32event.WAIT_OBJECT_0:
                on_summon()

    thread = threading.Thread(target=loop, name="SingleInstance", daemon=True)
    thread.start()
    return thread
