"""About and updates page: FA11y version, update check, changelog, and folders."""
from __future__ import annotations

import os
import threading

import wx

from lib.hub import sounds, status, theme
from lib.hub.page import HubPage
from lib.hub.widgets import button, label, text

REPO_URL = "https://github.com/GreenBeanGravy/FA11y"


class AboutPage(HubPage):
    title = "About and updates"

    def build(self) -> None:
        self.add_heading()
        self.version_text = text(self, "", font=theme.heading_font(self, 1))
        self.update_text = text(self, "", theme.TEXT_SECONDARY)
        self.content.Add(self.version_text)
        self.content.Add(self.update_text, 0, wx.TOP, 4)

        buttons = wx.WrapSizer(wx.HORIZONTAL)
        self.check_button = button(self, "&Check for updates", "refresh")
        self.restart_button = button(self, "&Restart to update", "download", "primary")
        logs_button = button(self, "Open &logs folder", "folder")
        config_button = button(self, "Open &settings folder", "folder")
        site_button = button(self, "FA11y on &GitHub")
        setup_button = button(self, "Run s&etup again")
        setup_button.Bind(wx.EVT_BUTTON, lambda e: self.hub.start_onboarding(self._setup_done))
        self.check_button.Bind(wx.EVT_BUTTON, lambda e: self.check_now())
        self.restart_button.Bind(wx.EVT_BUTTON, lambda e: status.restart_to_update(self.hub))
        logs_button.Bind(wx.EVT_BUTTON, lambda e: _open_folder("logs"))
        config_button.Bind(wx.EVT_BUTTON, lambda e: _open_folder("config"))
        site_button.Bind(wx.EVT_BUTTON, lambda e: wx.LaunchDefaultBrowser(REPO_URL))
        for ctrl in (self.check_button, self.restart_button, logs_button, config_button, site_button,
                     setup_button):
            buttons.Add(ctrl, 0, wx.RIGHT | wx.BOTTOM, 8)
        self.content.Add(buttons, 0, wx.TOP, 12)

        self.content.Add(label(self, "Changelog", font=theme.heading_font(self, 1)), 0, wx.TOP, 12)
        self.changelog = wx.TextCtrl(self, name="Changelog",
                                     style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_NONE)
        self.changelog.SetBackgroundColour(theme.CARD_BG)
        self.changelog.SetForegroundColour(theme.TEXT)
        self.content.Add(self.changelog, 1, wx.EXPAND | wx.TOP, 6)
        self.SetScrollRate(0, 0)

    def on_show(self) -> None:
        self.refresh()
        try:
            with open("CHANGELOG.txt", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            text = "No changelog found."
        if self.changelog.GetValue() != text:
            self.changelog.ChangeValue(text)

    def first_focus(self) -> wx.Window:
        # The version and update state first, then the buttons.
        return self.version_text

    def refresh(self) -> None:
        self.version_text.SetLabel(f"FA11y {status.local_version() or 'version unknown'}")
        update = status.available_update()
        if update:
            self.update_text.SetLabel(f"FA11y {update} is available."
                                      + ("" if status.can_restart_to_update()
                                         else " Run Updater.exe to install it."))
        else:
            self.update_text.SetLabel("FA11y checks for updates while it runs.")
        self.restart_button.Show(bool(update) and status.can_restart_to_update())
        self.Layout()

    def check_now(self) -> None:
        self.check_button.Disable()
        self.update_text.SetLabel("Checking for updates…")

        def work():
            from lib.app.updater_check import check_once
            found = check_once()
            wx.CallAfter(self._checked, found)
        threading.Thread(target=work, name="UpdateCheck", daemon=True).start()

    def _setup_done(self, egl_choice) -> None:
        from lib.hub.pages.fortnite import apply_setup_choice
        self.hub.reset_views(("settings", "keybinds"))
        apply_setup_choice(self.hub, egl_choice)

    def _checked(self, found) -> None:
        if not self:
            return
        self.check_button.Enable()
        self.refresh()
        if found is None:
            message = "Couldn't reach GitHub to check for updates."
            sounds.ui("error")
        elif found:
            message = self.update_text.GetLabel()
        else:
            message = "FA11y is up to date."
            self.update_text.SetLabel(message)
        self.hub.services.speak(message)
        self.check_button.SetFocus()


def _open_folder(name: str) -> None:
    path = os.path.abspath(name)
    os.makedirs(path, exist_ok=True)
    os.startfile(path)
