"""Home page: Play button, status of Fortnite, the Epic account and FA11y, and what's new."""
from __future__ import annotations

import os
import threading

import wx

from lib.hub import game_watch, status, theme
from lib.hub.page import HubPage
from lib.hub.widgets import GAP, StatusCard, button, label, text


def latest_changelog_entry(path: str = "CHANGELOG.txt") -> str:
    """First block of CHANGELOG.txt (up to the first blank line)."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read().strip()
    except OSError:
        return ""
    return text.split("\n\n", 1)[0].strip()


class HomePage(HubPage):
    title = "Home"

    def build(self) -> None:
        top = wx.BoxSizer(wx.HORIZONTAL)
        self.welcome = label(self, "Welcome to FA11y", font=theme.heading_font(self))
        top.Add(self.welcome, 1, wx.ALIGN_CENTER_VERTICAL)
        self.play_button = button(self, "&Play Fortnite", "player-play", "primary")
        self.play_button.Bind(wx.EVT_BUTTON, lambda e: self.hub.play_fortnite())
        top.Add(self.play_button, 0, wx.ALIGN_CENTER_VERTICAL)
        self.content.Add(top, 0, wx.EXPAND | wx.BOTTOM, 16)

        cards = wx.GridSizer(1, 3, GAP, GAP)
        self.fortnite_card = StatusCard(self, "Fortnite")
        self.account_card = StatusCard(self, "Epic account")
        self.fa11y_card = StatusCard(self, "FA11y")
        for card in (self.fortnite_card, self.account_card, self.fa11y_card):
            cards.Add(card, 1, wx.EXPAND)
        self.content.Add(cards, 0, wx.EXPAND)

        self.update_button = button(self, "&Restart to update FA11y", "refresh", "primary")
        self.update_button.Bind(wx.EVT_BUTTON, lambda e: status.restart_to_update(self.hub))
        self.update_button.Hide()
        self.content.Add(self.update_button, 0, wx.TOP, GAP)

        self.keybind_text = text(self, "", theme.TEXT_SECONDARY)
        self.content.Add(self.keybind_text, 0, wx.TOP, 18)

        self.content.Add(label(self, "What's new", font=theme.heading_font(self, 1)), 0, wx.TOP, 18)
        self.whats_new = wx.TextCtrl(self, name="What's new",
                                     style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_NONE)
        self.whats_new.SetBackgroundColour(theme.CARD_BG)
        self.whats_new.SetForegroundColour(theme.TEXT)
        self.whats_new.ChangeValue(latest_changelog_entry())
        self.content.Add(self.whats_new, 1, wx.EXPAND | wx.TOP, 6)
        self.SetScrollRate(0, 0)

    def on_show(self) -> None:
        self.refresh()

    def first_focus(self) -> wx.Window:
        return self.update_button if self.update_button.IsShown() else self.play_button

    def refresh(self) -> None:
        """Fill in what's known now, then fetch the slower parts on a worker thread."""
        self.keybind_text.SetLabel(
            f"Keybinds are active. Open this window any time with {status.open_hub_keybind()}.")
        running = game_watch.is_fortnite_running()
        self.play_button.SetLabel("Fortnite is &running" if running else "&Play Fortnite")
        # Each card fills in as soon as its own check finishes; the Fortnite
        # check runs legendary and takes about a second.
        for fetch, apply in ((status.account_status, self._apply_account),
                             (status.fa11y_status, self._apply_fa11y),
                             (status.fortnite_status, self._apply_fortnite)):
            threading.Thread(target=lambda f=fetch, a=apply: wx.CallAfter(a, f()),
                             name="HomeStatus", daemon=True).start()

    def _apply_account(self, account: dict) -> None:
        if not self:
            return
        name = account.get("name")
        self.welcome.SetLabel(f"Welcome back, {name}" if name else "Welcome to FA11y")
        self.account_card.set(*_card(account))

    def _apply_fa11y(self, fa11y: dict) -> None:
        if not self:
            return
        self.fa11y_card.set(*_card(fa11y))
        self.update_button.Show(bool(fa11y.get("update")) and status.can_restart_to_update())
        self.Layout()

    def _apply_fortnite(self, fortnite: dict) -> None:
        if self:
            self.fortnite_card.set(*_card(fortnite))


def _card(info: dict):
    colours = {"ok": theme.SUCCESS, "warn": theme.WARNING, "error": theme.DANGER}
    return info.get("value", ""), info.get("detail", ""), colours.get(info.get("level"), theme.TEXT_MUTED)
