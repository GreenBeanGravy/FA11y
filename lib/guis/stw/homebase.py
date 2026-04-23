"""
Homebase-related STW sub-dialogs: name/banner, FORT research, unlock regions.
"""
from __future__ import annotations

import logging
from typing import List, Optional

import wx

from lib.guis.stw.base import StwSubDialog, speak_later
from lib.stw.api import FORT_STAT_DISPLAY, FORT_STAT_ORDER

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Homebase name + banner
# ---------------------------------------------------------------------------

class HomebaseNameBannerDialog(StwSubDialog):
    """Edit homebase name (free-text) and banner (icon + color IDs)."""

    def __init__(self, parent, stw_api):
        self._name_text: Optional[wx.TextCtrl] = None
        self._icon_text: Optional[wx.TextCtrl] = None
        self._color_text: Optional[wx.TextCtrl] = None
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Name & Banner",
            help_id="SaveTheWorldHomebaseNameBanner",
            default_size=(640, 400),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        intro = wx.StaticText(
            self,
            label=(
                "Homebase name is free-text. Banner icon/color are Epic IDs "
                "like HomebaseBannerIcon:standardbanner15 / "
                "HomebaseBannerColor:defaultcolor1. You can leave banner "
                "fields blank to keep the current banner."
            ),
        )
        sizer.Add(intro, 0, wx.ALL | wx.EXPAND, 5)

        form = wx.FlexGridSizer(rows=3, cols=2, vgap=8, hgap=8)
        form.Add(wx.StaticText(self, label="Homebase name:"),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self._name_text = wx.TextCtrl(self)
        form.Add(self._name_text, 1, wx.EXPAND)

        form.Add(wx.StaticText(self, label="Banner icon ID:"),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self._icon_text = wx.TextCtrl(self)
        form.Add(self._icon_text, 1, wx.EXPAND)

        form.Add(wx.StaticText(self, label="Banner color ID:"),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self._color_text = wx.TextCtrl(self)
        form.Add(self._color_text, 1, wx.EXPAND)

        form.AddGrowableCol(1, 1)
        sizer.Add(form, 0, wx.EXPAND | wx.ALL, 10)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        save_name_btn = wx.Button(self, label="Save &Name")
        save_name_btn.Bind(wx.EVT_BUTTON, self._on_save_name)
        sizer.Add(save_name_btn, 0, wx.ALL, 5)
        save_banner_btn = wx.Button(self, label="Save &Banner")
        save_banner_btn.Bind(wx.EVT_BUTTON, self._on_save_banner)
        sizer.Add(save_banner_btn, 0, wx.ALL, 5)

    def _populate(self) -> None:
        self.stw_api.query_profile()
        self._name_text.SetValue(self.stw_api.get_homebase_name())
        stats = self.stw_api._stats()
        self._icon_text.SetValue(str(stats.get("homebase_banner_icon_id", "") or ""))
        self._color_text.SetValue(str(stats.get("homebase_banner_color_id", "") or ""))

    def _on_save_name(self, _evt: wx.CommandEvent) -> None:
        name = (self._name_text.GetValue() or "").strip()
        if not name:
            self.show_error("Name cannot be empty.")
            return
        ok = self.stw_api.set_homebase_name(name)
        if ok:
            speak_later("Homebase name saved.")
        else:
            self.show_error("Could not save homebase name.")

    def _on_save_banner(self, _evt: wx.CommandEvent) -> None:
        icon = (self._icon_text.GetValue() or "").strip()
        color = (self._color_text.GetValue() or "").strip()
        if not icon and not color:
            self.show_error("Provide at least one of icon ID or color ID.")
            return
        ok = self.stw_api.set_homebase_banner(
            banner_icon_id=icon, banner_color_id=color
        )
        if ok:
            speak_later("Banner saved.")
        else:
            self.show_error("Could not save banner.")


# ---------------------------------------------------------------------------
# FORT research
# ---------------------------------------------------------------------------

class FortResearchDialog(StwSubDialog):
    """Spend research points on the four FORT trees."""

    def __init__(self, parent, stw_api):
        self._list: Optional[wx.ListCtrl] = None
        self._points_label: Optional[wx.StaticText] = None
        super().__init__(
            parent,
            stw_api,
            title="Save the World — FORT Research",
            help_id="SaveTheWorldFortResearch",
            default_size=(680, 440),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        self._points_label = wx.StaticText(
            self, label="Research points available: -"
        )
        sizer.Add(self._points_label, 0, wx.ALL, 10)

        self._list = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES,
        )
        self._list.InsertColumn(0, "Stat", width=180)
        self._list.InsertColumn(1, "Current Level", width=140)
        self._list.InsertColumn(2, "Stat ID", width=180)
        sizer.Add(self._list, 1, wx.EXPAND | wx.ALL, 10)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        upgrade_btn = wx.Button(self, label="&Upgrade Selected (+1)")
        upgrade_btn.Bind(wx.EVT_BUTTON, self._on_upgrade)
        sizer.Add(upgrade_btn, 0, wx.ALL, 5)

    def _populate(self) -> None:
        self.stw_api.query_profile()
        points = self.stw_api.get_research_points_available()
        self._points_label.SetLabel(f"Research points available: {points}")

        fort = self.stw_api.get_fort_stats()
        self._list.DeleteAllItems()
        for idx, stat in enumerate(FORT_STAT_ORDER):
            self._list.InsertItem(idx, FORT_STAT_DISPLAY[stat])
            self._list.SetItem(idx, 1, str(fort.get(stat, 0)))
            self._list.SetItem(idx, 2, stat)

    def _on_upgrade(self, _evt: wx.CommandEvent) -> None:
        idx = self._list.GetFirstSelected()
        if idx < 0 or idx >= len(FORT_STAT_ORDER):
            self.show_info("Select a stat first.", caption="No Selection")
            return
        stat = FORT_STAT_ORDER[idx]
        if not self.confirm(
            f"Spend research points to upgrade {FORT_STAT_DISPLAY[stat]} by 1? "
            "Permanent.",
            "Confirm Research Upgrade",
        ):
            return
        ok = self.stw_api.purchase_research_stat_upgrade(stat)
        if ok:
            speak_later(f"{FORT_STAT_DISPLAY[stat]} upgraded.")
            self._populate()
        else:
            self.show_error("Could not upgrade. Check research points balance.")


# ---------------------------------------------------------------------------
# Unlock regions
# ---------------------------------------------------------------------------

class UnlockRegionsDialog(StwSubDialog):
    """List candidate region IDs and unlock them one at a time.

    Epic's region IDs are structured like `StormShield.Plankerton.1`. We
    expose a free-text entry for power users plus a hint list of typical
    SSD upgrade region IDs."""

    HINT_REGIONS = [
        "StormShield.Plankerton.1",
        "StormShield.Plankerton.2",
        "StormShield.Plankerton.3",
        "StormShield.Plankerton.4",
        "StormShield.Plankerton.5",
        "StormShield.Plankerton.6",
        "StormShield.CannyValley.1",
        "StormShield.CannyValley.2",
        "StormShield.CannyValley.3",
        "StormShield.CannyValley.4",
        "StormShield.CannyValley.5",
        "StormShield.CannyValley.6",
        "StormShield.TwinePeaks.1",
        "StormShield.TwinePeaks.2",
        "StormShield.TwinePeaks.3",
        "StormShield.TwinePeaks.4",
        "StormShield.TwinePeaks.5",
        "StormShield.TwinePeaks.6",
    ]

    def __init__(self, parent, stw_api):
        self._region_choice: Optional[wx.Choice] = None
        self._custom_text: Optional[wx.TextCtrl] = None
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Unlock Regions",
            help_id="SaveTheWorldUnlockRegions",
            default_size=(640, 360),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        intro = wx.StaticText(
            self,
            label=(
                "Pick a region from the list or type your own region ID. "
                "Unlock will fail if you don't meet the prerequisites."
            ),
        )
        sizer.Add(intro, 0, wx.ALL | wx.EXPAND, 5)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label="Preset region:"),
                0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self._region_choice = wx.Choice(self, choices=self.HINT_REGIONS)
        self._region_choice.SetSelection(0)
        row.Add(self._region_choice, 1, wx.RIGHT, 10)
        sizer.Add(row, 0, wx.ALL | wx.EXPAND, 5)

        row2 = wx.BoxSizer(wx.HORIZONTAL)
        row2.Add(wx.StaticText(self, label="Or custom region ID:"),
                 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self._custom_text = wx.TextCtrl(self)
        row2.Add(self._custom_text, 1)
        sizer.Add(row2, 0, wx.ALL | wx.EXPAND, 5)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        unlock_btn = wx.Button(self, label="&Unlock")
        unlock_btn.Bind(wx.EVT_BUTTON, self._on_unlock)
        sizer.Add(unlock_btn, 0, wx.ALL, 5)

    def _on_unlock(self, _evt: wx.CommandEvent) -> None:
        custom = (self._custom_text.GetValue() or "").strip()
        region = custom or self._region_choice.GetStringSelection()
        if not region:
            self.show_error("Pick or enter a region ID.")
            return
        if not self.confirm(
            f"Unlock region '{region}'? Irreversible.",
            "Confirm Unlock Region",
        ):
            return
        ok = self.stw_api.unlock_region(region)
        if ok:
            speak_later("Region unlocked.")
        else:
            self.show_error(
                "Could not unlock region. Prerequisites not met or region ID is wrong."
            )
