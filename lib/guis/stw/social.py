"""
Public profile lookup STW sub-dialog.

Lets the user type an Epic display name, resolves it to an account ID via
/account/api/public/account/displayName, then queries the public campaign
profile via QueryPublicProfile and shows a summary.
"""
from __future__ import annotations

import logging
from typing import Optional

import wx

from lib.guis.stw.base import StwSubDialog, speak_later
from lib.utilities.stw_api import FORT_STAT_DISPLAY, FORT_STAT_ORDER
from lib.utilities.stw_public_profile import PublicProfileAPI

logger = logging.getLogger(__name__)


class PublicProfileLookupDialog(StwSubDialog):
    """Display-name search -> public STW profile summary."""

    def __init__(self, parent, stw_api):
        self._name_text: Optional[wx.TextCtrl] = None
        self._result_text: Optional[wx.TextCtrl] = None
        self._public_api: Optional[PublicProfileAPI] = None
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Player Lookup",
            help_id="SaveTheWorldPublicProfileLookup",
            default_size=(720, 520),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        intro = wx.StaticText(
            self,
            label=(
                "Enter an Epic display name to see their public Save the "
                "World profile summary. Some profiles are private."
            ),
        )
        sizer.Add(intro, 0, wx.ALL | wx.EXPAND, 5)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label="Display name:"),
                0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self._name_text = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self._name_text.Bind(wx.EVT_TEXT_ENTER, lambda _evt: self._on_search(None))
        row.Add(self._name_text, 1, wx.RIGHT, 5)
        search_btn = wx.Button(self, label="&Look Up")
        search_btn.Bind(wx.EVT_BUTTON, self._on_search)
        row.Add(search_btn, 0)
        sizer.Add(row, 0, wx.ALL | wx.EXPAND, 5)

        self._result_text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP,
        )
        sizer.Add(self._result_text, 1, wx.EXPAND | wx.ALL, 5)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        pass

    def _ensure_api(self) -> bool:
        if self._public_api is None:
            self._public_api = PublicProfileAPI(self.stw_api.auth)
        return self._public_api is not None

    def _on_search(self, _evt) -> None:
        name = (self._name_text.GetValue() or "").strip()
        if not name:
            self.show_error("Enter a display name.")
            return
        if not self._ensure_api():
            self.show_error("Could not initialise public profile API.")
            return

        speak_later(f"Looking up {name}.")
        account_id = self._public_api.lookup_account_id(name)
        if not account_id:
            self._result_text.SetValue(f"No Epic account found for '{name}'.")
            speak_later("Not found.")
            return

        profile = self._public_api.query_public_campaign_profile(
            account_id, force=True
        )
        if profile is None:
            self._result_text.SetValue(
                f"Found account {account_id}, but the STW profile is "
                f"private or empty."
            )
            speak_later("Profile is private.")
            return

        summary = self._public_api.extract_summary(profile)
        lines = [
            f"Display name: {name}",
            f"Account ID: {account_id}",
            "",
            f"Commander Level: {summary['level']}",
            f"Approximate Power Level: {summary['power_level']}",
            f"Homebase: {summary['homebase_name'] or '(unnamed)'}",
            "",
            "FORT Stats:",
        ]
        fort = summary["fort"]
        for stat in FORT_STAT_ORDER:
            lines.append(f"  {FORT_STAT_DISPLAY[stat]}: {fort.get(stat, 0)}")
        lines.append("")
        counts = summary["counts"]
        lines.append("Collection:")
        lines.append(f"  Heroes:     {counts['heroes']}")
        lines.append(f"  Schematics: {counts['schematics']}")
        lines.append(f"  Survivors:  {counts['survivors']}")
        lines.append(f"  Defenders:  {counts['defenders']}")
        if summary["vbucks_visible"]:
            lines.append("")
            lines.append(f"V-Bucks visible on public profile: {summary['vbucks_visible']:,}")
        self._result_text.SetValue("\n".join(lines))
        speak_later(
            f"{name}. Level {summary['level']}. Approximate power "
            f"{summary['power_level']}."
        )
