"""Epic account page: sign in, sign out, and what the account is used for."""
from __future__ import annotations

import wx

from lib.hub import account_ops, sounds, theme
from lib.hub.page import HubPage
from lib.hub.controls import TextLine
from lib.hub.widgets import Card, button, text

ACCOUNT_PAGES = account_ops.ACCOUNT_PAGES


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
        info = account_ops.account_info()
        signed_in = info["signed_in"]
        self.account_text.set_lines([
            TextLine(info["name"], theme.heading_font(self.card, 2)),
            TextLine(info["detail"], colour=theme.TEXT_SECONDARY, gap=4),
        ])
        self.signin_button.SetLabel("&Sign in again" if signed_in else "&Sign in")
        self.signin_button.Show(not info["valid"])
        self.signout_button.Show(signed_in)
        self.Layout()

    def sign_in(self) -> None:
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
        account_ops.after_sign_in(auth)
        self.hub.reset_views(ACCOUNT_PAGES)
        sounds.ui("done")
        self.refresh()
        account_ops.legendary_login(auth)
        self.signout_button.SetFocus()

    def sign_out(self) -> None:
        if wx.MessageBox("Sign out of your Epic account? Locker, friends, quests and Fortnite downloads "
                         "will stop working until you sign in again.", "Sign out",
                         wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, self) != wx.YES:
            return
        account_ops.sign_out()
        self.hub.reset_views(ACCOUNT_PAGES)
        self.hub.services.speak("Signed out.")
        self.refresh()
        self.signin_button.SetFocus()
