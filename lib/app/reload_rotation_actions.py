"""
Keybind handlers for Reload map rotation.

These wrap ``lib.utilities.map_rotation`` in speaker-aware action functions.
Lifted out of ``FA11y.py`` so the entry file is shorter and these can be
covered by targeted tests in the future.

Caller wires the shared ``speaker`` in; no FA11y imports.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def announce_reload_map_rotation(speaker) -> None:
    """Fetch the live Reload map rotation from fortnite.gg and speak the
    current + next map with remaining time."""
    try:
        from lib.utilities.map_rotation import speech_announcement
        speaker.speak(speech_announcement())
    except Exception as e:
        print(f"Reload map rotation failed: {e}")
        speaker.speak("Could not fetch Reload map rotation.")


def sync_current_map_to_reload_rotation(speaker) -> None:
    """Set FA11y's ``POI.current_map`` to whatever Reload arena is live now.

    No-ops quietly when already synced or when rotation data is unavailable.
    Speaks status otherwise.
    """
    try:
        from lib.utilities.map_rotation import current_reload_map
        from lib.utilities.utilities import Config, read_config, clear_config_cache

        state = current_reload_map()
        if state is None:
            speaker.speak("Rotation data unavailable.")
            return

        target = state.current.fa11y_map
        if not target:
            speaker.speak(
                f"Current map is {state.current.name}, "
                f"but FA11y has no data file for it."
            )
            return

        cfg = read_config()
        current = cfg.get('POI', 'current_map', fallback='main')
        if current.strip().lower() == target.strip().lower():
            speaker.speak(f"Already on {target}.")
            return

        adapter = Config()
        adapter.set_current_map(target)
        if adapter.save():
            clear_config_cache()
            speaker.speak(
                f"FA11y map set to {target} "
                f"(live Reload: {state.current.name})."
            )
        else:
            speaker.speak("Failed to save map setting.")
    except Exception as e:
        print(f"Reload map sync failed: {e}")
        speaker.speak("Could not sync to Reload rotation.")
