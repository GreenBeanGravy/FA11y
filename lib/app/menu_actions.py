"""Menu keybinds: the window pages and the in-game dialogs."""
from __future__ import annotations

import logging
from typing import Callable, Optional

from lib.app import state
from lib.utilities.window_utils import focus_window

logger = logging.getLogger(__name__)


def open_config_gui(reload_config: Optional[Callable] = None) -> None:
    """Open the Settings page of the FA11y window (safe from any thread)."""
    from lib.hub import get_hub
    hub = get_hub()
    if hub is not None:
        hub.show_page('settings', summon=True)


def handle_custom_poi_gui(use_ppi: bool = False) -> None:
    """Open the custom POI creator with map-specific context."""
    speaker = state.speaker
    from lib.guis.gui_utilities import launch_gui_thread_safe
    from lib.utilities.utilities import read_config

    if state.custom_poi_gui_open.is_set():
        speaker.speak("Custom POI creator is already open")
        focus_window("Create Custom POI")
        return

    def _do_custom_poi_gui():
        state.custom_poi_gui_open.set()
        try:
            from lib.detection.player_position import get_player_position_for_poi_creation
            from lib.guis.custom_poi_gui import launch_custom_poi_creator

            current_map = read_config().get('POI', 'current_map', fallback='main')

            class PlayerDetector:
                def get_player_position(self, use_ppi_flag=True):
                    # Custom POI always uses the robust PPI pipeline (same as
                    # navigation), handling map open/closed automatically.
                    return get_player_position_for_poi_creation()

            launch_custom_poi_creator(True, PlayerDetector(), current_map)

        except Exception as e:
            print(f"Error opening custom POI GUI: {e}")
            speaker.speak("Error opening custom POI creator")
        finally:
            state.custom_poi_gui_open.clear()

    launch_gui_thread_safe(_do_custom_poi_gui)


def _stop_active_pinger_for_menu() -> None:
    """Shared helper - locker stops the POI pinger when it opens."""
    pinger = state.get_active_pinger()
    if pinger:
        pinger.stop()
        state.set_active_pinger(None)
        state.speaker.speak("Continuous ping disabled.")


def open_locker_selector() -> None:
    """Open the Locker page of the FA11y window."""
    from lib.hub import get_hub
    hub = get_hub()
    if hub is None:
        return
    _stop_active_pinger_for_menu()
    hub.show_page('locker', summon=True)


# ``open_locker_viewer`` is an identical alias for ``open_locker_selector`` - 
# the two keybinds opened the same GUI. Kept for back-compat with existing
# FA11y action handler mapping that binds both names.
open_locker_viewer = open_locker_selector
