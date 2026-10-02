"""Callbacks into the rest of FA11y, supplied by FA11y.py to whichever hub is running."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class HubServices:
    """Callbacks into the rest of FA11y, supplied by FA11y.py."""
    quit: Callable[[], None]
    reload_config: Callable[[], None]
    speak: Callable[[str], None]
