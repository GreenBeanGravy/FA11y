"""
Epic auth keybind handlers + success wiring.

``handle_auth_expiration`` is invoked from EpicAuth on 401 to flag the
session as expired. ``_on_auth_success`` is the success callback used by
both interactive re-auth and the background ``auth_watcher`` refresh —
it (re)creates the social manager and the discovery API.
"""
from __future__ import annotations

from lib.app import state


def handle_auth_expiration() -> None:
    """Announce auth expiration once and set the expired flag."""
    state.auth_expired.set()
    if not state.is_auth_expiration_announced():
        state.speaker.speak(
            "Authentication expired. Press ALT+E to re-authenticate."
        )
        state.logger.warning("Epic Games authentication expired")
        state.set_auth_expiration_announced(True)


def on_auth_success(epic_auth) -> None:
    """Wire up auth-dependent singletons after a successful login/refresh."""
    state.auth_expired.clear()
    state.set_auth_expiration_announced(False)

    existing_social = state.get_social_manager()
    if existing_social:
        existing_social.stop_monitoring()

    if epic_auth and epic_auth.access_token:
        from lib.managers.social_manager import get_social_manager
        from lib.utilities.epic_discovery import EpicDiscovery

        social_manager = get_social_manager(epic_auth)
        social_manager.start_monitoring()
        state.set_social_manager(social_manager)
        state.logger.debug(
            "Social manager initialized after authentication"
        )

        state.set_discovery_api(EpicDiscovery(epic_auth))
        state.logger.debug(
            "Discovery API initialized after authentication"
        )


def open_authentication() -> None:
    """Open Epic Games authentication dialog for re-authentication (ALT+E)."""
    from lib.guis.gui_utilities import launch_gui_thread_safe

    def _do_authentication():
        try:
            from lib.utilities.epic_auth import get_epic_auth_instance
            from lib.guis.epic_login_dialog import LoginDialog
            import wx

            epic_auth = get_epic_auth_instance()

            app = wx.GetApp()
            if app is None:
                app = wx.App(False)

            state.speaker.speak("Opening authentication dialog")

            login_dialog = LoginDialog(None, epic_auth)
            login_dialog.ShowModal()
            authenticated = login_dialog.authenticated
            login_dialog.Destroy()

            if authenticated:
                epic_auth = get_epic_auth_instance()
                on_auth_success(epic_auth)
                state.logger.debug(
                    f"Re-authenticated as {epic_auth.display_name}"
                )
            else:
                state.speaker.speak("Authentication cancelled")
        except Exception as e:
            state.logger.error(f"Error opening authentication dialog: {e}")
            state.speaker.speak("Error opening authentication dialog")

    launch_gui_thread_safe(_do_authentication)


def open_browser_login() -> None:
    """Browser login is now integrated into the main auth dialog."""
    open_authentication()
