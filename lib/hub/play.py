"""Starting Fortnite from the hub, shared by the Fortnite page and the Play buttons."""
from __future__ import annotations

from typing import Callable, Optional

from lib.hub import game_watch, sounds


def _exchange_code() -> str:
    """A one-time sign-in code from FA11y's Epic session, for signing legendary in. "" when signed out."""
    from lib.utilities.epic_auth import get_epic_auth_instance
    auth = get_epic_auth_instance()
    if not (auth and auth.access_token and auth.is_valid):
        return ""
    return auth.get_exchange_code() or ""


def play_fortnite(hub, manager=None, info=None,
                  on_failed: Optional[Callable[[str], None]] = None) -> None:
    """Launch Fortnite, or bring it forward when it's already running.

    info is the latest install status, if the caller has one; it only
    decides whether to point the user at the Fortnite page instead of
    trying to launch something that isn't installed. on_failed gets the
    message if the launch fails after it started.
    """
    if game_watch.is_fortnite_running():
        game_watch.focus_fortnite()
        return
    if info is not None and info.installed is False and not info.egl_install_path:
        hub.services.speak("Fortnite isn't installed. Install it on the Fortnite page.")
        hub.show_page("fortnite", summon=True)
        return
    if manager is None:
        from lib.fortnite import get_manager
        manager = get_manager()

    def launched(result):
        if not result.ok and on_failed is not None:
            on_failed(result.message)

    result = manager.launch(on_done=launched, get_exchange_code=_exchange_code)
    hub.services.speak(result.message)
    sounds.ui("done" if result.ok else "error")
