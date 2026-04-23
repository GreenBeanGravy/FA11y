"""
Informational STW sub-dialogs: overview, news/MOTD, service status.
"""
from __future__ import annotations

import logging
from typing import Optional

import wx

from lib.guis.stw.base import StwSubDialog, speak_later
from lib.stw.api import (
    FORT_STAT_DISPLAY,
    FORT_STAT_ORDER,
    format_template_display,
)
from lib.stw.news import FortniteNewsAPI, LightswitchAPI

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Overview — same shape as original stw_gui overview tab but now a sub-dialog
# ---------------------------------------------------------------------------

class OverviewDialog(StwSubDialog):
    """Quick read-only snapshot: commander level, FORT stats, V-Bucks,
    resources, equipped hero, unlocked zones."""

    def __init__(self, parent, stw_api):
        self._notebook: Optional[wx.Notebook] = None
        self._overview_text: Optional[wx.TextCtrl] = None
        self._resources_list: Optional[wx.ListCtrl] = None
        self._loadout_text: Optional[wx.TextCtrl] = None
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Overview",
            help_id="SaveTheWorldOverview",
            default_size=(780, 600),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        self._notebook = wx.Notebook(self)

        overview_panel = wx.Panel(self._notebook)
        overview_sizer = wx.BoxSizer(wx.VERTICAL)
        self._overview_text = wx.TextCtrl(
            overview_panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP,
        )
        overview_sizer.Add(self._overview_text, 1, wx.EXPAND | wx.ALL, 5)
        overview_panel.SetSizer(overview_sizer)
        self._notebook.AddPage(overview_panel, "Overview")

        resources_panel = wx.Panel(self._notebook)
        resources_sizer = wx.BoxSizer(wx.VERTICAL)
        self._resources_list = wx.ListCtrl(
            resources_panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL,
        )
        self._resources_list.InsertColumn(0, "Resource", width=260)
        self._resources_list.InsertColumn(1, "Quantity", width=100)
        self._resources_list.InsertColumn(2, "Template ID", width=360)
        resources_sizer.Add(self._resources_list, 1, wx.EXPAND | wx.ALL, 5)
        resources_panel.SetSizer(resources_sizer)
        self._notebook.AddPage(resources_panel, "Resources")

        loadout_panel = wx.Panel(self._notebook)
        loadout_sizer = wx.BoxSizer(wx.VERTICAL)
        self._loadout_text = wx.TextCtrl(
            loadout_panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP,
        )
        loadout_sizer.Add(self._loadout_text, 1, wx.EXPAND | wx.ALL, 5)
        loadout_panel.SetSizer(loadout_sizer)
        self._notebook.AddPage(loadout_panel, "Loadout")

        sizer.Add(self._notebook, 1, wx.EXPAND | wx.ALL, 5)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        speak_btn = wx.Button(self, label="&Speak Summary")
        speak_btn.Bind(wx.EVT_BUTTON, self._on_speak_summary)
        sizer.Add(speak_btn, 0, wx.ALL, 5)

    def _populate(self) -> None:
        self.stw_api.query_profile()
        level, xp = self.stw_api.get_commander_level()
        fort = self.stw_api.get_fort_stats()
        vbucks_total = self.stw_api.get_total_vbucks()
        research_points = self.stw_api.get_research_points_available()
        unlocked = ", ".join(self.stw_api.get_unlocked_zones()) or "(none)"
        homebase = self.stw_api.get_homebase_name() or "(unnamed)"
        founder = "Yes" if self.stw_api.get_founder_status() else "No"
        pl = self.stw_api.get_power_level()

        overview_lines = [
            f"Commander Level: {level}",
            f"Commander XP: {xp:,}",
            f"Approximate Power Level: {pl}",
            f"Homebase: {homebase}",
            f"Founder: {founder}",
            "",
            "FORT Stats:",
        ]
        for stat in FORT_STAT_ORDER:
            overview_lines.append(f"  {FORT_STAT_DISPLAY[stat]}: {fort.get(stat, 0)}")
        overview_lines += [
            "",
            f"Unlocked zones: {unlocked}",
            "",
            f"Research Points available: {research_points}",
            f"V-Bucks (all sources): {vbucks_total:,}",
        ]
        self._overview_text.SetValue("\n".join(overview_lines))

        self._resources_list.DeleteAllItems()
        for idx, (template_id, display_name, qty) in enumerate(
            self.stw_api.get_resources()
        ):
            self._resources_list.InsertItem(idx, display_name)
            self._resources_list.SetItem(idx, 1, f"{qty:,}")
            self._resources_list.SetItem(idx, 2, template_id)

        hero = self.stw_api.get_equipped_hero()
        if hero:
            loadout_lines = [
                f"Loadout: {hero.get('loadout_name') or '(unnamed)'}",
                f"Commander: {hero.get('display_name') or format_template_display(hero.get('template_id', ''), level=hero.get('level', ''))}",
                f"Template: {hero.get('template_id') or '(unknown)'}",
                f"Level: {hero.get('level') or '-'}",
            ]
        else:
            loadout_lines = [
                "No commander currently equipped on this campaign profile.",
                "",
                "Equip a hero in-game at the Commander tab, then click Refresh.",
            ]
        self._loadout_text.SetValue("\n".join(loadout_lines))

    def _on_speak_summary(self, _evt: wx.CommandEvent) -> None:
        level, _ = self.stw_api.get_commander_level()
        fort = self.stw_api.get_fort_stats()
        vbucks = self.stw_api.get_total_vbucks()
        pl = self.stw_api.get_power_level()
        parts = [
            f"Commander level {level}. Approximate power {pl}.",
            (
                f"FORT {fort.get('fortitude', 0)} fortitude, "
                f"{fort.get('offense', 0)} offense, "
                f"{fort.get('resistance', 0)} resistance, "
                f"{fort.get('technology', 0)} tech."
            ),
            f"{vbucks:,} V-Bucks.",
        ]
        speak_later(" ".join(parts))


# ---------------------------------------------------------------------------
# News / MOTD
# ---------------------------------------------------------------------------

class NewsDialog(StwSubDialog):
    """Show the STW news/MOTD messages (no auth required)."""

    def __init__(self, parent, stw_api):
        self._text: Optional[wx.TextCtrl] = None
        self._news_api: Optional[FortniteNewsAPI] = None
        super().__init__(
            parent,
            stw_api,
            title="Save the World — News",
            help_id="SaveTheWorldNews",
            default_size=(780, 560),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        self._text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP,
        )
        sizer.Add(self._text, 1, wx.EXPAND | wx.ALL, 5)

    def _populate(self) -> None:
        if self._news_api is None:
            self._news_api = FortniteNewsAPI()
        ok = self._news_api.fetch(force=True)
        if not ok:
            self._text.SetValue("Could not fetch STW news.")
            return
        entries = self._news_api.get_motd_entries()
        if not entries:
            self._text.SetValue("No STW news entries.")
            return
        parts = []
        for entry in entries:
            title = entry.get("title") or "(untitled)"
            body = entry.get("body") or ""
            parts.append(f"{title}\n{'=' * len(title)}\n\n{body}\n")
        self._text.SetValue("\n".join(parts))


# ---------------------------------------------------------------------------
# Service status (Lightswitch)
# ---------------------------------------------------------------------------

class ServiceStatusDialog(StwSubDialog):
    """Show Fortnite's Lightswitch service status."""

    def __init__(self, parent, stw_api):
        self._text: Optional[wx.TextCtrl] = None
        self._api: Optional[LightswitchAPI] = None
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Service Status",
            help_id="SaveTheWorldServiceStatus",
            default_size=(600, 340),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        self._text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP,
        )
        sizer.Add(self._text, 1, wx.EXPAND | wx.ALL, 5)

    def _populate(self) -> None:
        if self._api is None:
            self._api = LightswitchAPI(self.stw_api.auth)
        ok = self._api.fetch(force=True)
        if not ok:
            self._text.SetValue("Could not fetch service status.")
            return
        summary = self._api.get_status_summary()
        lines = [
            f"Status: {summary.get('status', 'Unknown')}",
            f"Message: {summary.get('message', '') or '(no message)'}",
            f"Allowed actions: {summary.get('allowed_actions', '') or '(none)'}",
        ]
        self._text.SetValue("\n".join(lines))
        speak_later(f"Fortnite status: {summary.get('status', 'Unknown')}.")
