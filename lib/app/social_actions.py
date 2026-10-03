"""
Social & discovery keybind handlers.

Wrappers around ``social_manager`` and ``discovery_api`` that handle the
window-page and thread-safe-dispatch mechanics; the underlying managers
already live in ``lib/managers``.
"""
from __future__ import annotations

import threading

from lib.app import state


def _show_page(key: str) -> None:
    from lib.hub import get_hub
    hub = get_hub()
    if hub is not None:
        hub.show_page(key, summon=True)


def open_social_menu() -> None:
    """Open the Social page, after giving its data a moment to load."""
    speaker = state.speaker

    def _open():
        social_manager = state.get_social_manager()
        # Signed out: the page itself says how to sign in.
        if social_manager and not social_manager.initial_data_loaded.is_set():
            speaker.speak("Loading social data")
            if not social_manager.wait_for_initial_data(timeout=10):
                speaker.speak(
                    "Timeout waiting for social data, opening anyway"
                )
        _show_page("social")

    # The wait can take seconds, so it must not hold up the keybind thread or the wx loop.
    threading.Thread(target=_open, name="OpenSocial", daemon=True).start()


def open_discovery_gui() -> None:
    """Open the Discover page (does not require authentication)."""
    _show_page("discover")


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
