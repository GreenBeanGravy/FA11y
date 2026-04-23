"""
Social & discovery keybind handlers.

Wrappers around ``social_manager`` and ``discovery_api`` that handle the
GUI-launch + thread-safe-dispatch mechanics; the underlying managers
already live in ``lib/managers``.
"""
from __future__ import annotations

from lib.app import state
from lib.utilities.window_utils import focus_window


def open_social_menu() -> None:
    """Open the social menu."""
    from lib.guis.gui_utilities import launch_gui_thread_safe

    speaker = state.speaker
    if state.social_gui_open.is_set():
        speaker.speak("Social menu is already open")
        focus_window("Social Menu")
        return

    def _open():
        social_manager = state.get_social_manager()
        if not social_manager:
            speaker.speak("Social features not enabled")
            return

        if not social_manager.initial_data_loaded.is_set():
            speaker.speak("Loading social data")
            if not social_manager.wait_for_initial_data(timeout=10):
                speaker.speak(
                    "Timeout waiting for social data, opening anyway"
                )

        state.social_gui_open.set()
        try:
            from lib.guis.social_gui import show_social_gui
            show_social_gui(social_manager)
        finally:
            state.social_gui_open.clear()

    launch_gui_thread_safe(_open)


def open_discovery_gui() -> None:
    """Open the discovery GUI (does not require authentication)."""
    from lib.guis.gui_utilities import launch_gui_thread_safe

    speaker = state.speaker
    if state.discovery_gui_open.is_set():
        speaker.speak("Discovery GUI is already open")
        focus_window("Discovery GUI")
        return

    def _open():
        discovery_api = state.get_discovery_api()
        if not discovery_api:
            from lib.utilities.epic_auth import get_epic_auth_instance
            from lib.utilities.epic_discovery import EpicDiscovery
            epic_auth = get_epic_auth_instance()
            discovery_api = EpicDiscovery(
                epic_auth if epic_auth and epic_auth.is_valid else None
            )

        state.discovery_gui_open.set()
        try:
            from lib.guis.discovery_gui import show_discovery_gui
            show_discovery_gui(discovery_api)
        finally:
            state.discovery_gui_open.clear()

    launch_gui_thread_safe(_open)


def accept_notification() -> None:
    """Accept pending notification (Alt+Y)."""
    from lib.guis.gui_utilities import run_on_main_thread

    def _do_accept():
        social_manager = state.get_social_manager()
        if social_manager:
            social_manager.accept_notification()
        else:
            state.logger.debug("Social manager not initialized")

    run_on_main_thread(_do_accept)


def decline_notification() -> None:
    """Decline pending notification (Alt+D)."""
    from lib.guis.gui_utilities import run_on_main_thread

    def _do_decline():
        social_manager = state.get_social_manager()
        if social_manager:
            social_manager.decline_notification()
        else:
            state.logger.debug("Social manager not initialized")

    run_on_main_thread(_do_decline)
