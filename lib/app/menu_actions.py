"""GUI launchers (config, custom POI, gamemode, locker)."""
from __future__ import annotations

from typing import Callable, Optional

from lib.app import state
from lib.utilities.window_utils import focus_window


def open_config_gui(reload_config: Optional[Callable] = None) -> None:
    """Open the FA11y configuration GUI.

    ``reload_config`` is the callback invoked after the user saves — lives
    in FA11y.py and re-binds the action handlers / key bindings. Caller
    must supply it; we refuse to open the GUI without a reload path.
    """
    speaker = state.speaker
    from lib.guis.gui_utilities import launch_gui_thread_safe
    from lib.utilities.utilities import Config, read_config, save_config

    if state.config_gui_open.is_set():
        speaker.speak("Configuration is already open")
        focus_window("FA11y Configuration")
        return

    def _do_open_config():
        state.config_gui_open.set()
        try:
            from lib.guis.config_gui import launch_config_gui

            config_instance = Config()
            config_instance.config = read_config()

            def update_callback(updated_config_parser):
                save_config(updated_config_parser)
                if reload_config is not None:
                    reload_config()
                print("Configuration updated and saved to disk")

            launch_config_gui(config_instance, update_callback)

        except Exception as e:
            print(f"Error opening config GUI: {e}")
            speaker.speak("Error opening configuration GUI")
        finally:
            state.config_gui_open.clear()

    launch_gui_thread_safe(_do_open_config)


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
            from lib.detection.player_position import check_for_pixel
            from lib.guis.custom_poi_gui import launch_custom_poi_creator

            current_map = read_config().get('POI', 'current_map', fallback='main')
            use_ppi_flag = check_for_pixel()

            class PlayerDetector:
                def get_player_position(self, use_ppi_flag):
                    from lib.detection.player_position import (
                        find_player_position as find_map_player_pos,
                        find_player_icon_location,
                    )
                    return (find_map_player_pos() if use_ppi_flag
                            else find_player_icon_location())

            launch_custom_poi_creator(use_ppi_flag, PlayerDetector(), current_map)

        except Exception as e:
            print(f"Error opening custom POI GUI: {e}")
            speaker.speak("Error opening custom POI creator")
        finally:
            state.custom_poi_gui_open.clear()

    launch_gui_thread_safe(_do_custom_poi_gui)


def open_gamemode_selector() -> None:
    """Open the gamemode selector GUI."""
    speaker = state.speaker
    from lib.guis.gui_utilities import launch_gui_thread_safe

    def _do_open_gamemode():
        if state.gamemode_gui_open.is_set():
            speaker.speak("Gamemode selector is already open")
            focus_window("Game Mode Selection")
            return

        try:
            from lib.guis.gamemode_gui import launch_gamemode_selector
            state.gamemode_gui_open.set()
            try:
                launch_gamemode_selector()
            finally:
                state.gamemode_gui_open.clear()
        except Exception as e:
            print(f"Error opening gamemode selector: {e}")
            speaker.speak("Error opening gamemode selector")
            state.gamemode_gui_open.clear()

    launch_gui_thread_safe(_do_open_gamemode)


def _stop_active_pinger_for_menu() -> None:
    """Shared helper — locker stops the POI pinger when it opens."""
    pinger = state.get_active_pinger()
    if pinger:
        pinger.stop()
        state.set_active_pinger(None)
        state.speaker.speak("Continuous ping disabled.")


def open_locker_selector() -> None:
    """Open the locker GUI (cosmetic browser/equipper)."""
    speaker = state.speaker
    from lib.guis.gui_utilities import launch_gui_thread_safe

    def _do_open_locker():
        if state.locker_gui_open.is_set():
            speaker.speak("Locker is already open")
            focus_window("Locker")
            return

        _stop_active_pinger_for_menu()
        try:
            from lib.guis.locker_gui import launch_locker_gui
            state.locker_gui_open.set()
            try:
                launch_locker_gui()
            finally:
                state.locker_gui_open.clear()
        except Exception as e:
            print(f"Error opening locker: {e}")
            speaker.speak("Error opening locker")
            state.locker_gui_open.clear()

    launch_gui_thread_safe(_do_open_locker)


# ``open_locker_viewer`` is an identical alias for ``open_locker_selector`` —
# the two keybinds opened the same GUI. Kept for back-compat with existing
# FA11y action handler mapping that binds both names.
open_locker_viewer = open_locker_selector
