"""Run code on the wx main thread and wait for its result."""
from __future__ import annotations

import threading
from typing import Any, Callable


def call_on_wx(func: Callable[[], Any]) -> Any:
    """Run func on the wx main thread, block until it finishes, and return its result.

    Re-raises whatever func raised. Runs func directly when already on the main thread.
    """
    import wx
    if wx.IsMainThread():
        return func()
    done = threading.Event()
    outcome: dict = {}

    def run() -> None:
        try:
            outcome["value"] = func()
        except BaseException as e:  # handed back to the waiting thread
            outcome["error"] = e
        finally:
            done.set()

    wx.CallAfter(run)
    done.wait()
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")
