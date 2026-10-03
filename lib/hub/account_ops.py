"""Epic account actions for the hub, without any window code.

Used by the requests the window sends.
"""
from __future__ import annotations

import threading

ACCOUNT_PAGES = ("social", "quests", "locker", "discover")


def account_info() -> dict:
    """What the Epic account page shows: name, detail line, and the sign-in state."""
    from lib.utilities.epic_auth import get_epic_auth_instance
    auth = get_epic_auth_instance()
    signed_in = bool(auth and auth.access_token)
    valid = bool(signed_in and auth.is_valid)
    if valid:
        name, detail = auth.display_name or "Signed in", "Signed in."
    elif signed_in:
        name = auth.display_name or "Session expired"
        detail = "Your session expired. Sign in again to keep using account features."
    else:
        name, detail = "Signed out", "Sign in to use your locker, friends, quests, and Fortnite downloads."
    return {"name": name, "detail": detail, "signed_in": signed_in, "valid": valid}


def legendary_login(auth) -> None:
    """Also sign legendary in, so Fortnite downloads work without a second login."""
    def work():
        try:
            from lib.fortnite import get_manager
            get_manager().login_with_exchange_code(auth.get_exchange_code())
        except Exception:
            pass
    threading.Thread(target=work, name="LegendaryLogin", daemon=True).start()


def after_sign_in(auth) -> None:
    """Wire up the account features once the user has signed in. Run on the wx thread."""
    from lib.app.auth_actions import on_auth_success
    on_auth_success(auth)


def sign_out() -> None:
    """Sign out of the Epic account and stop what depends on it."""
    from lib.app import state
    from lib.utilities.epic_auth import get_epic_auth_instance
    manager = state.get_social_manager()
    if manager is not None:
        manager.stop_monitoring()
        state.set_social_manager(None)
    state.set_discovery_api(None)
    get_epic_auth_instance().clear_auth()

    def work():
        try:
            from lib.fortnite import get_manager
            get_manager().logout()
        except Exception:
            pass
    threading.Thread(target=work, name="LegendaryLogout", daemon=True).start()
