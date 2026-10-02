"""Requests for the Epic account page. The sign in dialog is still wx, so it runs on the wx thread."""
from __future__ import annotations

from lib.hub import account_ops, get_hub, sounds
from lib.shell.bridge import handler
from lib.shell.wx_thread import call_on_wx


def _changed() -> None:
    hub = get_hub()
    if hub is not None:
        hub.reset_views(account_ops.ACCOUNT_PAGES)
        hub.send("home.changed")


@handler("account.state")
def account_state(_params: dict) -> dict:
    return account_ops.account_info()


@handler("account.sign_in")
def sign_in(_params: dict) -> dict:
    """Show the Epic sign in dialog and wait for it to close."""
    def run() -> bool:
        from lib.guis.epic_login_dialog import LoginDialog
        from lib.utilities.epic_auth import get_epic_auth_instance
        dialog = LoginDialog(None, get_epic_auth_instance())
        dialog.ShowModal()
        authenticated = bool(dialog.authenticated)
        dialog.Destroy()
        if authenticated:
            auth = get_epic_auth_instance()
            account_ops.after_sign_in(auth)
            account_ops.legendary_login(auth)
        return authenticated

    authenticated = call_on_wx(run)
    if authenticated:
        _changed()
        sounds.ui("done")
    return {"authenticated": authenticated, **account_ops.account_info()}


@handler("account.sign_out")
def sign_out(_params: dict) -> dict:
    call_on_wx(account_ops.sign_out)
    _changed()
    return account_ops.account_info()
