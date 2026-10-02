"""Hub sound cues.

UI cues (page change, open, close, done, error) play only while the
NavigationSounds setting is on. The update cue plays when an update is
found, whatever that setting says. Both play quietly; the update cue at
30% volume.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

SOUND_DIR = os.path.join("assets", "sounds")
UI_VOLUME = 0.5
UPDATE_VOLUME = 0.3

_enabled = True


def set_enabled(enabled: bool) -> None:
    global _enabled
    _enabled = enabled


@lru_cache(maxsize=None)
def _load(filename: str):
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        return pygame.mixer.Sound(os.path.join(SOUND_DIR, filename))
    except Exception as e:
        logger.debug(f"Could not load sound {filename}: {e}")
        return None


def _play(filename: str, volume: float) -> None:
    sound = _load(filename)
    if sound is None:
        return
    try:
        channel: Optional[object] = sound.play()
        if channel is not None:
            channel.set_volume(volume)
    except Exception as e:
        logger.debug(f"Could not play sound {filename}: {e}")


def ui(name: str) -> None:
    """Play a UI cue: navigate, open, close, done or error."""
    if _enabled:
        _play(f"ui_{name}.ogg", UI_VOLUME)


def update_available() -> None:
    _play("update.ogg", UPDATE_VOLUME)


def preload() -> None:
    """Decode the cues ahead of time so the first page change has no delay."""
    for name in ("navigate", "open", "close", "done", "error"):
        _load(f"ui_{name}.ogg")
    _load("update.ogg")
