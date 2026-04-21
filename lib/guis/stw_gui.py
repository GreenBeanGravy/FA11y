"""
Save the World manager — main menu.

alt+shift+s opens a grouped menu of STW features. Each menu item launches
a focused sub-dialog from lib/guis/stw/. The main menu itself is lightweight:
it doesn't fetch the full campaign profile until the user picks a screen
that needs it, so it opens fast.

Sub-dialog launcher pattern:
  - Each sub-dialog takes an STWApi (or WorldInfoAPI, etc.) instance.
  - Sub-dialogs reuse the same STWApi so profile data is cached between
    screens for the session.
"""
from __future__ import annotations

import ctypes
import logging
from typing import Callable, Dict, List, Optional, Tuple

import wx
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import (
    AccessibleDialog,
    ensure_window_focus_and_center_mouse,
    messageBox,
)

logger = logging.getLogger(__name__)
speaker = Auto()


DIALOG_TITLE = "Save the World Manager"


# Menu structure. Each entry = (category label, [(screen label, launcher key)]).
# The launcher key maps to a function in _LAUNCHERS below.
MENU_STRUCTURE: List[Tuple[str, List[Tuple[str, str]]]] = [
    (
        "Missions and Rewards",
        [
            ("Mission Alerts", "mission_alerts"),
            ("Daily Quests", "daily_quests"),
            ("Expeditions", "expeditions"),
            ("Claim Mission Alert Rewards", "claim_alerts"),
        ],
    ),
    (
        "Shop and Llamas",
        [
            ("Llama Store", "llamas"),
            ("Open Llamas", "open_llamas"),
        ],
    ),
    (
        "Heroes and Squads",
        [
            ("Active Loadout", "active_loadout"),
            ("Survivor Squads", "survivor_squads"),
            ("Defender Squads", "defender_squads"),
        ],
    ),
    (
        "Items and Storage",
        [
            ("Heroes", "items_heroes"),
            ("Schematics", "items_schematics"),
            ("Survivors", "items_survivors"),
            ("Defenders", "items_defenders"),
            ("Recycle Items", "recycle_items"),
        ],
    ),
    (
        "Homebase",
        [
            ("Name and Banner", "homebase_name_banner"),
            ("FORT Research", "fort_research"),
            ("Unlock Regions", "unlock_regions"),
        ],
    ),
    (
        "Collection Book",
        [
            ("View Collection Book", "collection_book"),
            ("Claim Collection Book Rewards", "claim_collection_book"),
        ],
    ),
    (
        "Social",
        [
            ("Look Up Player", "public_profile_lookup"),
        ],
    ),
    (
        "Info",
        [
            ("Overview (my campaign)", "overview"),
            ("STW News", "news"),
            ("Service Status", "service_status"),
        ],
    ),
    (
        "Settings",
        [
            ("Alert and Poller Settings", "settings"),
        ],
    ),
]


class STWMainMenuDialog(AccessibleDialog):
    """Main menu for the STW manager. Lists categories + screens."""

    def __init__(self, parent, stw_api):
        super().__init__(parent, title=DIALOG_TITLE, helpId="SaveTheWorldManager")
        self.stw_api = stw_api
        self._tree: Optional[wx.TreeCtrl] = None
        self._screen_items: Dict = {}

        self._build_ui()

    def _build_ui(self) -> None:
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        header = wx.StaticText(
            self,
            label=(
                "Save the World manager. Use arrow keys to navigate the menu, "
                "Enter to open a screen, Escape to close."
            ),
        )
        main_sizer.Add(header, 0, wx.ALL | wx.EXPAND, 10)

        self._tree = wx.TreeCtrl(
            self,
            style=wx.TR_DEFAULT_STYLE
            | wx.TR_HIDE_ROOT
            | wx.TR_SINGLE
            | wx.TR_FULL_ROW_HIGHLIGHT,
        )
        root = self._tree.AddRoot("STW Menu")
        for category_label, screens in MENU_STRUCTURE:
            cat_item = self._tree.AppendItem(root, category_label)
            for screen_label, launcher_key in screens:
                leaf = self._tree.AppendItem(cat_item, screen_label)
                self._screen_items[leaf] = launcher_key
            self._tree.Expand(cat_item)
        self._tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self._on_tree_activated)
        self._tree.Bind(wx.EVT_CHAR_HOOK, self._on_tree_key)
        main_sizer.Add(self._tree, 1, wx.ALL | wx.EXPAND, 10)

        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        open_btn = wx.Button(self, label="&Open")
        open_btn.Bind(wx.EVT_BUTTON, self._on_open_clicked)
        button_sizer.Add(open_btn, 0, wx.ALL, 5)
        close_btn = wx.Button(self, wx.ID_CLOSE, label="&Close")
        close_btn.Bind(wx.EVT_BUTTON, lambda _evt: self.EndModal(wx.ID_CLOSE))
        button_sizer.Add(close_btn, 0, wx.ALL, 5)
        main_sizer.Add(button_sizer, 0, wx.ALIGN_RIGHT)

        self.SetSizer(main_sizer)
        self.SetSize((640, 560))
        self.CentreOnScreen()
        self.SetEscapeId(wx.ID_CLOSE)

        wx.CallAfter(self._tree.SetFocus)

    # ----- Tree interaction --------------------------------------------
    def _on_tree_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_RETURN:
            self._activate_selected()
            return
        event.Skip()

    def _on_tree_activated(self, _evt: wx.TreeEvent) -> None:
        self._activate_selected()

    def _on_open_clicked(self, _evt: wx.CommandEvent) -> None:
        self._activate_selected()

    def _activate_selected(self) -> None:
        item = self._tree.GetSelection()
        if not item.IsOk():
            return
        launcher_key = self._screen_items.get(item)
        if not launcher_key:
            # Category header — toggle expand/collapse.
            if self._tree.IsExpanded(item):
                self._tree.Collapse(item)
            else:
                self._tree.Expand(item)
            return

        launcher = _LAUNCHERS.get(launcher_key)
        if not launcher:
            messageBox(
                f"Screen '{launcher_key}' not implemented.",
                "Not Implemented",
                wx.OK | wx.ICON_INFORMATION,
                parent=self,
            )
            return

        try:
            launcher(self, self.stw_api)
        except Exception as e:
            logger.error(f"STW launcher '{launcher_key}' failed: {e}", exc_info=True)
            messageBox(
                f"Could not open this screen: {e}",
                "Error",
                wx.OK | wx.ICON_ERROR,
                parent=self,
            )


# ---------------------------------------------------------------------------
# Sub-dialog launchers (delegated to stw/*.py)
# ---------------------------------------------------------------------------

def _launch_mission_alerts(parent, stw_api):
    from lib.guis.stw.missions import MissionAlertsDialog
    dlg = MissionAlertsDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_daily_quests(parent, stw_api):
    from lib.guis.stw.missions import DailyQuestsDialog
    dlg = DailyQuestsDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_expeditions(parent, stw_api):
    from lib.guis.stw.missions import ExpeditionsDialog
    dlg = ExpeditionsDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_claim_alerts(parent, stw_api):
    """One-shot action — no dialog. Just ask, run, speak result."""
    dlg = wx.MessageDialog(
        parent,
        "Claim all pending mission alert rewards from today?",
        "Confirm Claim",
        style=wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION,
    )
    answer = dlg.ShowModal()
    dlg.Destroy()
    if answer != wx.ID_YES:
        return
    ok = stw_api.claim_mission_alert_rewards()
    if ok:
        speaker.speak("Mission alert rewards claimed.")
        messageBox("Mission alert rewards claimed.", "Claimed",
                   wx.OK | wx.ICON_INFORMATION, parent=parent)
    else:
        speaker.speak("Claim failed.")
        messageBox("Could not claim mission alert rewards. "
                   "Check authentication.", "Error",
                   wx.OK | wx.ICON_ERROR, parent=parent)


def _launch_llamas(parent, stw_api):
    from lib.guis.stw.shop import LlamaStoreDialog
    dlg = LlamaStoreDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_open_llamas(parent, stw_api):
    from lib.guis.stw.shop import OpenLlamasDialog
    dlg = OpenLlamasDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_active_loadout(parent, stw_api):
    from lib.guis.stw.heroes import ActiveLoadoutDialog
    dlg = ActiveLoadoutDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_survivor_squads(parent, stw_api):
    from lib.guis.stw.heroes import SurvivorSquadsDialog
    dlg = SurvivorSquadsDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_defender_squads(parent, stw_api):
    from lib.guis.stw.heroes import DefenderSquadsDialog
    dlg = DefenderSquadsDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_items_heroes(parent, stw_api):
    from lib.guis.stw.items import ItemsDialog
    dlg = ItemsDialog(parent, stw_api, kind="heroes")
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_items_schematics(parent, stw_api):
    from lib.guis.stw.items import ItemsDialog
    dlg = ItemsDialog(parent, stw_api, kind="schematics")
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_items_survivors(parent, stw_api):
    from lib.guis.stw.items import ItemsDialog
    dlg = ItemsDialog(parent, stw_api, kind="survivors")
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_items_defenders(parent, stw_api):
    from lib.guis.stw.items import ItemsDialog
    dlg = ItemsDialog(parent, stw_api, kind="defenders")
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_recycle_items(parent, stw_api):
    from lib.guis.stw.items import RecycleBatchDialog
    dlg = RecycleBatchDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_homebase_name_banner(parent, stw_api):
    from lib.guis.stw.homebase import HomebaseNameBannerDialog
    dlg = HomebaseNameBannerDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_fort_research(parent, stw_api):
    from lib.guis.stw.homebase import FortResearchDialog
    dlg = FortResearchDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_unlock_regions(parent, stw_api):
    from lib.guis.stw.homebase import UnlockRegionsDialog
    dlg = UnlockRegionsDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_collection_book(parent, stw_api):
    from lib.guis.stw.collection_book import CollectionBookDialog
    dlg = CollectionBookDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_claim_collection_book(parent, stw_api):
    dlg = wx.MessageDialog(
        parent,
        "Claim all pending Collection Book rewards?",
        "Confirm Claim",
        style=wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION,
    )
    answer = dlg.ShowModal()
    dlg.Destroy()
    if answer != wx.ID_YES:
        return
    ok = stw_api.claim_collection_book_rewards()
    if ok:
        speaker.speak("Collection Book rewards claimed.")
        messageBox("Collection Book rewards claimed.", "Claimed",
                   wx.OK | wx.ICON_INFORMATION, parent=parent)
    else:
        speaker.speak("Claim failed.")
        messageBox("Could not claim Collection Book rewards.", "Error",
                   wx.OK | wx.ICON_ERROR, parent=parent)


def _launch_public_profile_lookup(parent, stw_api):
    from lib.guis.stw.social import PublicProfileLookupDialog
    dlg = PublicProfileLookupDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_overview(parent, stw_api):
    from lib.guis.stw.info import OverviewDialog
    dlg = OverviewDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_news(parent, stw_api):
    from lib.guis.stw.info import NewsDialog
    dlg = NewsDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_service_status(parent, stw_api):
    from lib.guis.stw.info import ServiceStatusDialog
    dlg = ServiceStatusDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


def _launch_settings(parent, stw_api):
    from lib.guis.stw.settings import STWSettingsDialog
    dlg = STWSettingsDialog(parent, stw_api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        dlg.ShowModal()
    finally:
        dlg.Destroy()


_LAUNCHERS: Dict[str, Callable] = {
    "mission_alerts": _launch_mission_alerts,
    "daily_quests": _launch_daily_quests,
    "expeditions": _launch_expeditions,
    "claim_alerts": _launch_claim_alerts,
    "llamas": _launch_llamas,
    "open_llamas": _launch_open_llamas,
    "active_loadout": _launch_active_loadout,
    "survivor_squads": _launch_survivor_squads,
    "defender_squads": _launch_defender_squads,
    "items_heroes": _launch_items_heroes,
    "items_schematics": _launch_items_schematics,
    "items_survivors": _launch_items_survivors,
    "items_defenders": _launch_items_defenders,
    "recycle_items": _launch_recycle_items,
    "homebase_name_banner": _launch_homebase_name_banner,
    "fort_research": _launch_fort_research,
    "unlock_regions": _launch_unlock_regions,
    "collection_book": _launch_collection_book,
    "claim_collection_book": _launch_claim_collection_book,
    "public_profile_lookup": _launch_public_profile_lookup,
    "overview": _launch_overview,
    "news": _launch_news,
    "service_status": _launch_service_status,
    "settings": _launch_settings,
}


# ---------------------------------------------------------------------------
# Entry point from FA11y.py
# ---------------------------------------------------------------------------

def launch_stw_gui() -> Optional[int]:
    """Open the STW manager main menu. Returns the dialog exit code."""
    try:
        ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        pass

    app = wx.GetApp()
    if app is None:
        app = wx.App(False)

    try:
        from lib.utilities.epic_auth import get_epic_auth_instance
    except ImportError as e:
        logger.error(f"Failed to import epic_auth: {e}")
        speaker.speak("Error loading authentication module.")
        return None

    auth = get_epic_auth_instance()
    if not auth.access_token or not auth.account_id:
        speaker.speak(
            "Not signed in to Epic. Open the authentication dialog first, "
            "then try again."
        )
        messageBox(
            "You need to sign in to Epic Games before opening the Save the "
            "World manager. Use the Open Authentication keybind and complete "
            "login first.",
            "Not Authenticated",
            wx.OK | wx.ICON_WARNING,
        )
        return None

    from lib.utilities.stw_api import STWApi

    api = STWApi(auth)
    speaker.speak("Opening Save the World manager.")

    dlg = STWMainMenuDialog(None, api)
    try:
        ensure_window_focus_and_center_mouse(dlg)
        return dlg.ShowModal()
    finally:
        try:
            dlg.Destroy()
        except Exception:
            pass
