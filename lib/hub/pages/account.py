"""Epic account page: sign in, sign out, and what the account is used for."""
from __future__ import annotations

import threading

import wx

from lib.hub import sounds, theme
from lib.hub.page import HubPage
from lib.hub.controls import TextLine
from lib.hub.widgets import Card, button, text

ACCOUNT_PAGES = ("social", "quests", "locker", "discover")


class AccountPage(HubPage):
    title = "Epic account"

    def build(self) -> None:
        self.add_heading()
        self.card = Card(self, "Account")
        # One tab stop for the account's name and state, read as "Name. Signed in."
        self.account_text = text(self.card, wrap=600)
        self.account_text.separator = ". "
        self.card.body.Add(self.account_text)
        self.content.Add(self.card, 0, wx.EXPAND)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.signin_button = button(self, "&Sign in", "user", "primary")
        self.signout_button = button(self, "Sign &out")
        self.signin_button.Bind(wx.EVT_BUTTON, lambda e: self.sign_in())
        self.signout_button.Bind(wx.EVT_BUTTON, lambda e: self.sign_out())
        buttons.Add(self.signin_button, 0, wx.RIGHT, 8)
        buttons.Add(self.signout_button)
        self.content.Add(buttons, 0, wx.TOP, 12)

        self.content.Add(text(self, "Your Epic account is used for the locker, friends and party, quests, "
                                     "Discover, and downloading and updating Fortnite. FA11y keeps you signed "
                                     "in between restarts.", theme.TEXT_SECONDARY, wrap=640), 0, wx.TOP, 18)

    def on_show(self) -> None:
        self.refresh()

    def first_focus(self) -> wx.Window:
        # Who is signed in first, then the buttons.
        return self.account_text

    def refresh(self) -> None:
        from lib.utilities.epic_auth import get_epic_auth_instance
        auth = get_epic_auth_instance()
        signed_in = bool(auth and auth.access_token)
        if signed_in and auth.is_valid:
            name, detail = auth.display_name or "Signed in", "Signed in."
        elif signed_in:
            name = auth.display_name or "Session expired"
            detail = "Your session expired. Sign in again to keep using account features."
        else:
            name, detail = "Signed out", "Sign in to use your locker, friends, quests, and Fortnite downloads."
        self.account_text.set_lines([
            TextLine(name, theme.heading_font(self.card, 2)),
            TextLine(detail, colour=theme.TEXT_SECONDARY, gap=4),
        ])
        self.signin_button.SetLabel("&Sign in again" if signed_in else "&Sign in")
        self.signin_button.Show(not (signed_in and auth.is_valid))
        self.signout_button.Show(signed_in)
        self.Layout()

    def sign_in(self) -> None:
        from lib.app.auth_actions import on_auth_success
        from lib.guis.epic_login_dialog import LoginDialog
        from lib.utilities.epic_auth import get_epic_auth_instance

        dialog = LoginDialog(self.hub, get_epic_auth_instance())
        dialog.ShowModal()
        authenticated = dialog.authenticated
        dialog.Destroy()
        if not authenticated:
            self.signin_button.SetFocus()
            return
        auth = get_epic_auth_instance()
        on_auth_success(auth)
        self.hub.reset_views(ACCOUNT_PAGES)
        sounds.ui("done")
        self.refresh()
        self._sign_in_downloads(auth)
        self.signout_button.SetFocus()

    def _sign_in_downloads(self, auth) -> None:
        """Also sign legendary in, so Fortnite downloads work without a second login."""
        def work():
            try:
                from lib.fortnite import get_manager
                get_manager().login_with_exchange_code(auth.get_exchange_code())
            except Exception:
                pass
        threading.Thread(target=work, name="LegendaryLogin", daemon=True).start()

    def sign_out(self) -> None:
        if wx.MessageBox("Sign out of your Epic account? Locker, friends, quests and Fortnite downloads "
                         "will stop working until you sign in again.", "Sign out",
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) != wx.YES:
            return
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
        self.hub.reset_views(ACCOUNT_PAGES)
        self.hub.services.speak("Signed out.")
        self.refresh()
        self.signin_button.SetFocus()
