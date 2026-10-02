"""FA11y's main window ("the hub"): sidebar, pages, tray icon."""
from __future__ import annotations

from typing import Optional

_hub = None


def get_hub():
    """Return the running HubFrame, or None before it exists or after it closes."""
    return _hub


def set_hub(frame) -> None:
    global _hub
    _hub = frame
