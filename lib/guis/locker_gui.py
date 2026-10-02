"""
Unified Locker GUI for FA11y
Browse your cosmetics collection and equip them in Fortnite

The logic (filtering, favorites, equipping, loadouts) lives in
lib/managers/locker_manager.py, which the hub's Locker page uses as well.
"""
import time
import logging
import threading
from typing import List, Optional, Dict
import ctypes

import wx
from lib.hub.controls import StyledButton
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import (
    AccessibleDialog, BoxSizerHelper, messageBox,
    ensure_window_focus_and_center_mouse, BORDER_FOR_DIALOGS
)
from lib.guis.view_host import EmbeddedView, show_view
from lib.managers import locker_manager as lm
from lib.managers.locker_manager import (  # noqa: F401 (kept importable from here)
    COSMETIC_TYPE_MAP, LOADOUT_SCHEMA_NAMES, SLOT_TEMPLATE_TO_AUTOMATION, apply_favorite_flags,
    focus_fortnite_window,
)

# Initialize logger
logger = logging.getLogger(__name__)

# Global speaker instance
speaker = Auto()


RARITY_COLORS = {
    "common": (170, 170, 170),
    "uncommon": (96, 170, 58),
    "rare": (73, 172, 242),
    "epic": (177, 91, 226),
    "legendary": (211, 120, 65),
    "mythic": (255, 223, 0),
    "marvel": (197, 51, 52),
    "dc": (84, 117, 199),
    "starwars": (231, 196, 19),
    "icon": (0, 217, 217),
    "gaminglegends": (137, 86, 255),
}


class CategoryView(AccessibleDialog):
    """Category-specific cosmetics view"""

    def __init__(self, parent, category_name: str, cosmetics_data: List[dict],
                 auth_instance=None, owned_only: bool = False, owned_ids: set = None):
        super().__init__(parent, title=f"{category_name} - Fortnite Locker", helpId="CategoryView")
        self.category_name = category_name
        self.cosmetics_data = cosmetics_data
        self.auth = auth_instance
        self.owned_only = owned_only
        self.owned_ids = owned_ids or set()

        # Filter to this category only
        self.category_cosmetics = lm.category_cosmetics(cosmetics_data, category_name, owned_only, self.owned_ids)
        self.filtered_cosmetics = self.category_cosmetics.copy()

        # Search state
        self.current_search = ""

        # Favorite filter/sort state
        self.favorites_only = False
        self.sort_favorites_first = False

        # Category-specific settings
        options = lm.category_options(category_name)
        self.show_random = options["random"]
        self.show_randomize = options["randomize"]
        self.unequip_search_term = options["unequip"]

        self.setupDialog()
        self.SetSize((900, 700))
        self.CentreOnScreen()

    def makeSettings(self, sizer: BoxSizerHelper):
        """Create category view content"""

        # Results count
        self.results_label = wx.StaticText(self, label="")
        sizer.addItem(self.results_label)

        # Favorite filter controls
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.favorites_only_btn = wx.ToggleButton(self, label="Favorites Only")
        self.favorites_only_btn.SetValue(self.favorites_only)
        self.favorites_only_btn.Bind(wx.EVT_TOGGLEBUTTON, self.on_favorites_only_toggle)
        filter_sizer.Add(self.favorites_only_btn, flag=wx.ALL, border=5)

        self.sort_favorites_btn = wx.ToggleButton(self, label="Sort Favorites First")
        self.sort_favorites_btn.SetValue(self.sort_favorites_first)
        self.sort_favorites_btn.Bind(wx.EVT_TOGGLEBUTTON, self.on_sort_favorites_toggle)
        filter_sizer.Add(self.sort_favorites_btn, flag=wx.ALL, border=5)

        sizer.addItem(filter_sizer)

        # Search box
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_label = wx.StaticText(self, label="Search:")
        search_sizer.Add(search_label, flag=wx.ALIGN_CENTER_VERTICAL)
        search_sizer.AddSpacer(10)

        self.search_box = wx.TextCtrl(self, size=(400, -1))
        self.search_box.Bind(wx.EVT_TEXT, self.on_search_changed)
        search_sizer.Add(self.search_box, flag=wx.ALIGN_CENTER_VERTICAL)

        search_sizer.AddSpacer(10)
        clear_btn = StyledButton(self, label="Clear")
        clear_btn.Bind(wx.EVT_BUTTON, lambda e: self.search_box.SetValue(""))
        search_sizer.Add(clear_btn, flag=wx.ALIGN_CENTER_VERTICAL)

        sizer.addItem(search_sizer)

        # Cosmetics list
        self.cosmetics_list = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_VRULES
        )

        # Setup columns - add Type column for All Cosmetics view
        if self.category_name == "All Cosmetics":
            self.cosmetics_list.InsertColumn(0, "Name", width=300)
            self.cosmetics_list.InsertColumn(1, "Type", width=150)
            self.cosmetics_list.InsertColumn(2, "Rarity", width=120)
            self.cosmetics_list.InsertColumn(3, "Season", width=80)
        else:
            self.cosmetics_list.InsertColumn(0, "Name", width=350)
            self.cosmetics_list.InsertColumn(1, "Rarity", width=150)
            self.cosmetics_list.InsertColumn(2, "Season", width=100)

        self.cosmetics_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_item_selected)
        self.cosmetics_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_item_activated)

        sizer.addItem(self.cosmetics_list, flag=wx.EXPAND, proportion=1)

        # Details panel
        details_box = wx.StaticBox(self, label="Cosmetic Details")
        details_sizer = wx.StaticBoxSizer(details_box, wx.VERTICAL)

        self.details_text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(-1, 100)
        )
        details_sizer.Add(self.details_text, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)

        sizer.addItem(details_sizer, flag=wx.EXPAND)

        # Buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.equip_btn = StyledButton(self, label="&Equip Selected")
        self.equip_btn.Bind(wx.EVT_BUTTON, self.on_equip_clicked)
        button_sizer.Add(self.equip_btn)

        button_sizer.AddSpacer(10)

        self.back_btn = StyledButton(self, label="&Back to Categories")
        self.back_btn.Bind(wx.EVT_BUTTON, self.on_back)
        button_sizer.Add(self.back_btn)

        button_sizer.AddStretchSpacer()

        self.close_btn = StyledButton(self, label="&Close")
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        button_sizer.Add(self.close_btn)

        sizer.addItem(button_sizer, flag=wx.EXPAND)

        # Bind key events
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)

        # Populate list
        wx.CallAfter(self.update_list)

    def onKeyEvent(self, event):
        """Handle key events"""
        key_code = event.GetKeyCode()

        if key_code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        elif key_code == ord('F') or key_code == ord('f'):
            # F key toggles favorite for selected cosmetic
            self.on_toggle_favorite()
            return

        event.Skip()

    def on_search_changed(self, event):
        """Handle search text changes"""
        self.current_search = self.search_box.GetValue()
        self.update_list()

    def on_favorites_only_toggle(self, event):
        """Handle Favorites Only toggle"""
        self.favorites_only = self.favorites_only_btn.GetValue()
        if self.favorites_only:
            speaker.speak("Filtering to favorites only")
        else:
            speaker.speak("Showing all cosmetics")
        self.update_list()

    def on_sort_favorites_toggle(self, event):
        """Handle Sort Favorites First toggle"""
        self.sort_favorites_first = self.sort_favorites_btn.GetValue()
        if self.sort_favorites_first:
            speaker.speak("Sorting favorites first")
        else:
            speaker.speak("Default sorting")
        self.update_list()

    def filter_cosmetics(self) -> List[dict]:
        """Filter cosmetics based on search and favorites"""
        return lm.filter_cosmetics(self.category_cosmetics, self.favorites_only, self.current_search)

    def _special_row(self, offset: int, label: str, marker: int, colour: wx.Colour) -> None:
        idx = self.cosmetics_list.InsertItem(offset, label)
        if self.category_name == "All Cosmetics":
            self.cosmetics_list.SetItem(idx, 1, "-")
            self.cosmetics_list.SetItem(idx, 2, "Special")
            self.cosmetics_list.SetItem(idx, 3, "-")
        else:
            self.cosmetics_list.SetItem(idx, 1, "Special")
            self.cosmetics_list.SetItem(idx, 2, "-")
        self.cosmetics_list.SetItemData(idx, marker)
        self.cosmetics_list.SetItemTextColour(idx, colour)

    def update_list(self):
        """Update the cosmetics list"""
        self.filtered_cosmetics = self.filter_cosmetics()

        # Sort favorites first if enabled
        if self.sort_favorites_first:
            self.filtered_cosmetics = lm.sort_favorites_first(self.filtered_cosmetics)

        self.results_label.SetLabel(lm.results_label(
            len(self.filtered_cosmetics), self.category_name, self.current_search,
            self.favorites_only, self.sort_favorites_first))

        # Clear and populate list
        self.cosmetics_list.Freeze()
        try:
            self.cosmetics_list.DeleteAllItems()

            list_offset = 0

            # Add Random option at top (if applicable for this category)
            if self.show_random:
                self._special_row(list_offset, "🔄 Random", -1, wx.Colour(0, 217, 217))
                list_offset += 1

            # Add Randomize Track option (picks a random cosmetic from the list)
            if self.show_randomize:
                idx = self.cosmetics_list.InsertItem(list_offset, "🎲 Randomize Track")
                self.cosmetics_list.SetItem(idx, 1, "Special")
                self.cosmetics_list.SetItem(idx, 2, "-")
                self.cosmetics_list.SetItemData(idx, -3)  # Special marker
                self.cosmetics_list.SetItemTextColour(idx, wx.Colour(0, 200, 100))
                list_offset += 1

            # Add Unequip option (with category-specific label, if applicable)
            if self.unequip_search_term:
                self._special_row(list_offset, f"❌ Unequip ({self.unequip_search_term})", -2,
                                  wx.Colour(255, 100, 100))
                list_offset += 1

            # Add regular cosmetics
            for cosmetic_idx, cosmetic in enumerate(self.filtered_cosmetics):
                name = cosmetic.get("name", "Unknown")
                if cosmetic.get("favorite", False):
                    name = "⭐ " + name

                rarity = lm.rarity_display(cosmetic)
                season = lm.season_text(cosmetic)

                list_idx = self.cosmetics_list.InsertItem(cosmetic_idx + list_offset, name)

                # Add Type column for All Cosmetics view
                if self.category_name == "All Cosmetics":
                    self.cosmetics_list.SetItem(list_idx, 1, lm.friendly_type(cosmetic.get("type", "")))
                    self.cosmetics_list.SetItem(list_idx, 2, rarity)
                    self.cosmetics_list.SetItem(list_idx, 3, season)
                else:
                    self.cosmetics_list.SetItem(list_idx, 1, rarity)
                    self.cosmetics_list.SetItem(list_idx, 2, season)

                self.cosmetics_list.SetItemData(list_idx, cosmetic_idx)

                # Color code
                color = self.get_rarity_color(cosmetic.get("rarity", "common").lower())
                if color:
                    self.cosmetics_list.SetItemTextColour(list_idx, color)

        finally:
            self.cosmetics_list.Thaw()

        # Select first item
        if self.cosmetics_list.GetItemCount() > 0:
            self.cosmetics_list.Select(0)
            self.cosmetics_list.Focus(0)

    def get_rarity_color(self, rarity: str) -> Optional[wx.Colour]:
        """Get color for rarity"""
        rgb = RARITY_COLORS.get(rarity.lower())
        return wx.Colour(*rgb) if rgb else None

    def on_item_selected(self, event):
        """Handle item selection"""
        index = event.GetIndex()
        cosmetic_idx = self.cosmetics_list.GetItemData(index)

        if cosmetic_idx == -1:  # Random
            self.details_text.SetValue(lm.special_details("random"))
        elif cosmetic_idx == -3:  # Randomize Track
            self.details_text.SetValue(lm.special_details("randomize"))
        elif cosmetic_idx == -2:  # Unequip
            self.details_text.SetValue(lm.special_details("unequip", self.unequip_search_term))
        elif 0 <= cosmetic_idx < len(self.filtered_cosmetics):
            self.details_text.SetValue(lm.cosmetic_details(self.filtered_cosmetics[cosmetic_idx]))

    def on_item_activated(self, event):
        """Handle double-click"""
        self.on_equip_clicked(None)

    def on_toggle_favorite(self):
        """Toggle favorite status for selected cosmetic"""
        # Get selected item
        index = self.cosmetics_list.GetFirstSelected()
        if index == -1:
            speaker.speak("No cosmetic selected")
            return

        cosmetic_idx = self.cosmetics_list.GetItemData(index)

        # Don't allow favoriting Random or Unequip options
        if cosmetic_idx < 0:
            speaker.speak("Cannot favorite special options")
            return

        if cosmetic_idx >= len(self.filtered_cosmetics):
            speaker.speak("Invalid cosmetic index")
            return

        cosmetic = self.filtered_cosmetics[cosmetic_idx]
        result = lm.toggle_favorite(self.auth, self.cosmetics_data, cosmetic)

        if result == "ok":
            # Refresh list to show/hide star
            wx.CallAfter(self.update_list)
        elif result == "login":
            messageBox("You must be logged in to use the favorites feature.", "Login Required",
                       wx.OK | wx.ICON_WARNING, self)
        elif result == "failed":
            messageBox("Failed to update favorite status via API. Check logs for details.", "Failed",
                       wx.OK | wx.ICON_ERROR, self)
        elif result == "error":
            messageBox("Error toggling favorite.", "Error", wx.OK | wx.ICON_ERROR, self)

    def on_equip_clicked(self, event):
        """Handle Equip button"""
        index = self.cosmetics_list.GetFirstSelected()
        if index == -1:
            speaker.speak("No item selected")
            messageBox("Please select an item to equip", "No Selection", wx.OK | wx.ICON_WARNING, self)
            return

        cosmetic_idx = self.cosmetics_list.GetItemData(index)

        if cosmetic_idx == -1:  # Random
            request = lm.EquipRequest(self.category_name, "random")
        elif cosmetic_idx == -3:  # Randomize Track
            request = lm.EquipRequest(self.category_name, "randomize", candidates=self.filtered_cosmetics)
        elif cosmetic_idx == -2:  # Unequip
            request = lm.EquipRequest(self.category_name, "unequip")
        elif 0 <= cosmetic_idx < len(self.filtered_cosmetics):
            request = lm.EquipRequest(self.category_name, "cosmetic", self.filtered_cosmetics[cosmetic_idx])
        else:
            return
        self.equip(request)

    def equip(self, request: "lm.EquipRequest"):
        """Equip using UI automation"""
        try:
            plan = lm.plan_equip(request)
            if "error" in plan:
                messageBox(plan["error"], "Cannot Equip", wx.OK | wx.ICON_WARNING, self)
                return

            # For items with multiple slots, ask user
            slot = plan["slot"]
            if slot is None:
                slot = self.ask_for_slot(plan["cosmetic_type"], plan["name"])
                if slot is None:
                    return

            # Minimize dialog
            self.Iconize(True)
            time.sleep(0.1)

            try:
                success, name = lm.run_equip(request, plan, slot)
                wx.CallLater(100, self._show_after_equip, success, name)
            except Exception as automation_error:
                logger.error(f"Error during automation: {automation_error}")
                wx.CallAfter(self._show_after_equip, False, plan["name"])
                raise

        except Exception as e:
            logger.error(f"Error equipping cosmetic: {e}")
            if not self.IsShown():
                wx.CallAfter(self.Show)
            wx.CallAfter(messageBox, f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)

    def _show_after_equip(self, success: bool, name: str):
        """Show dialog after equip"""
        try:
            time.sleep(0.2)
            self.Iconize(False)
            self.Raise()
            self.SetFocus()

            if not success:
                wx.CallAfter(lambda: messageBox(lm.EQUIP_FAILED_MESSAGE, "Equip Failed", wx.OK | wx.ICON_ERROR, self))
        except Exception as e:
            logger.error(f"Error showing dialog after equip: {e}")

    def ask_for_slot(self, cosmetic_type: str, name: str) -> Optional[int]:
        """Ask user which slot to equip to"""
        prompt = lm.slot_prompt(cosmetic_type, name)
        if prompt is None:
            # For types without multiple slots, default to slot 1
            return 1

        dlg = wx.SingleChoiceDialog(self, prompt["message"], prompt["title"], prompt["choices"])
        if dlg.ShowModal() == wx.ID_OK:
            slot = dlg.GetSelection() + 1
            dlg.Destroy()
            return slot
        dlg.Destroy()
        return None

    def on_back(self, event):
        """Handle Back button"""
        self.EndModal(wx.ID_CANCEL)

    def on_close(self, event):
        """Handle Close button"""
        self.EndModal(wx.ID_CLOSE)


class LockerView(EmbeddedView):
    """Main Locker view - Category Selection Menu"""

    view_title = "Fortnite Locker"

    def __init__(self, parent, cosmetics_data: List[dict], auth_instance=None, owned_only: bool = False,
                 fetched_owned=None):
        super().__init__(parent)
        self.cosmetics_data = cosmetics_data
        self.auth = auth_instance
        self.owned_only = owned_only
        self.owned_ids = set()
        self._startup_checked = False
        # Owned cosmetic ids fetched ahead of time on a worker thread, or
        # None to fetch them the first time the view is shown.
        self._fetched_owned = fetched_owned

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        settings_sizer = BoxSizerHelper(self, orientation=wx.VERTICAL)
        self.makeSettings(settings_sizer)
        main_sizer.Add(
            settings_sizer.sizer,
            border=BORDER_FOR_DIALOGS,
            flag=wx.ALL | wx.EXPAND,
            proportion=1
        )
        self.SetSizer(main_sizer)

    def activate(self):
        # Check auth and fetch owned IDs the first time the view is shown
        if not self._startup_checked:
            self._startup_checked = True
            if self.auth and self.auth.display_name:
                if self._fetched_owned is not None:
                    self._apply_owned_ids(self._fetched_owned)
                else:
                    self._fetch_owned_in_background()

    def _fetch_owned_in_background(self):
        """Fetch owned cosmetics on a worker thread, then apply them here."""
        def work():
            try:
                fetched = self.auth.fetch_owned_cosmetics()
            except Exception as e:
                logger.error(f"Fetching owned cosmetics failed: {e}")
                return
            wx.CallAfter(lambda: self and self._apply_owned_ids(fetched))
        threading.Thread(target=work, name="LockerOwned", daemon=True).start()

    def _apply_owned_ids(self, fetched_ids):
        """Mark owned cosmetics and add placeholders for owned items the database lacks."""
        try:
            # Check for auth expiration
            if fetched_ids == "AUTH_EXPIRED":
                logger.info("Auth token expired on startup")
                # Don't prompt immediately, just disable owned checkbox
                return
            elif fetched_ids:
                self.owned_ids = lm.apply_owned_ids(self.cosmetics_data, self.auth, fetched_ids)

                # Enable the owned button
                if hasattr(self, 'owned_btn'):
                    self.owned_btn.Enable(True)

        except Exception as e:
            logger.error(f"Error checking auth on startup: {e}")

    def makeSettings(self, sizer: BoxSizerHelper):
        """Create main category menu"""

        # Header
        header_label = wx.StaticText(self, label="Fortnite Locker - Select Category")
        header_font = header_label.GetFont()
        header_font.PointSize += 3
        header_font = header_font.Bold()
        header_label.SetFont(header_font)
        sizer.addItem(header_label)

        # Login status and button
        login_sizer = wx.BoxSizer(wx.HORIZONTAL)

        if self.auth and self.auth.display_name:
            status_label = wx.StaticText(self, label=f"Logged in as: {self.auth.display_name}")
            login_sizer.Add(status_label, flag=wx.ALIGN_CENTER_VERTICAL)
            login_sizer.AddSpacer(10)

            self.login_btn = StyledButton(self, label="Logged In", size=(120, -1))
            self.login_btn.Enable(False)
        else:
            status_label = wx.StaticText(self, label="Not logged in")
            login_sizer.Add(status_label, flag=wx.ALIGN_CENTER_VERTICAL)
            login_sizer.AddSpacer(10)

            self.login_btn = StyledButton(self, label="&Login", size=(120, -1))
            self.login_btn.Bind(wx.EVT_BUTTON, self.on_login)

        login_sizer.Add(self.login_btn)
        sizer.addItem(login_sizer)

        # Owned filter toggle button
        self.owned_btn = wx.ToggleButton(self, label="Show Only My Cosmetics")
        self.owned_btn.SetValue(self.owned_only)
        self.owned_btn.Bind(wx.EVT_TOGGLEBUTTON, self.on_owned_toggle)
        if not (self.auth and self.auth.display_name):
            self.owned_btn.Enable(False)
        sizer.addItem(self.owned_btn)

        # Category buttons (in coordinate order)
        categories_label = wx.StaticText(self, label="Select a category:")
        categories_label_font = categories_label.GetFont()
        categories_label_font.PointSize += 1
        categories_label.SetFont(categories_label_font)
        sizer.addItem(categories_label)

        # Create scrolled panel for categories to prevent cutoff
        self.categories_panel = wx.ScrolledWindow(self, style=wx.VSCROLL)
        self.categories_panel.SetScrollRate(0, 20)

        categories_sizer = wx.BoxSizer(wx.VERTICAL)

        for category in lm.CATEGORIES:
            btn = StyledButton(self.categories_panel, label=category, size=(200, 40))
            btn.Bind(wx.EVT_BUTTON, lambda evt, cat=category: self.on_category_selected(cat))
            categories_sizer.Add(btn, flag=wx.ALL, border=5)

        self.categories_panel.SetSizer(categories_sizer)
        self.categories_panel.Layout()
        categories_sizer.Fit(self.categories_panel)

        sizer.addItem(self.categories_panel, flag=wx.EXPAND, proportion=1)

        # Loadout buttons (only show if logged in)
        if self.auth and self.auth.display_name:
            loadout_label = wx.StaticText(self, label="Loadouts:")
            sizer.addItem(loadout_label)

            loadout_sizer = wx.BoxSizer(wx.HORIZONTAL)

            self.view_equipped_btn = StyledButton(self, label="&View Equipped")
            self.view_equipped_btn.Bind(wx.EVT_BUTTON, self.on_view_equipped)
            loadout_sizer.Add(self.view_equipped_btn, flag=wx.RIGHT, border=5)

            self.view_loadouts_btn = StyledButton(self, label="Saved &Loadouts")
            self.view_loadouts_btn.Bind(wx.EVT_BUTTON, self.on_view_loadouts)
            loadout_sizer.Add(self.view_loadouts_btn, flag=wx.RIGHT, border=5)

            self.save_loadout_btn = StyledButton(self, label="&Save Current as Loadout")
            self.save_loadout_btn.Bind(wx.EVT_BUTTON, self.on_save_loadout)
            loadout_sizer.Add(self.save_loadout_btn, flag=wx.RIGHT, border=5)

            sizer.addItem(loadout_sizer)

        self.passes_btn = StyledButton(self, label="Battle &Passes")
        self.passes_btn.Bind(wx.EVT_BUTTON, self.on_passes)
        sizer.addItem(self.passes_btn)

        # Bottom buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        button_sizer.AddStretchSpacer()

        self.close_btn = StyledButton(self, label="&Close")
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        button_sizer.Add(self.close_btn)

        sizer.addItem(button_sizer, flag=wx.EXPAND)

    def on_passes(self, event):
        from lib.guis.passes_gui import PassesDialog
        PassesDialog(self, self.auth, self.cosmetics_data).run()

    def on_category_selected(self, category_name: str):
        """Handle category button click - open category view"""
        try:
            speaker.speak(f"Opening {category_name} category")
            logger.info(f"Opening category: {category_name}")

            # Open CategoryView dialog
            dlg = CategoryView(
                self,
                category_name,
                self.cosmetics_data,
                auth_instance=self.auth,
                owned_only=self.owned_only,
                owned_ids=self.owned_ids
            )

            ensure_window_focus_and_center_mouse(dlg)
            dlg.ShowModal()
            dlg.Destroy()

        except Exception as e:
            logger.error(f"Error opening category view: {e}")
            speaker.speak("Error opening category")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)

    def on_view_equipped(self, event):
        """Show currently equipped cosmetics from the Locker Service"""
        try:
            if not self.auth or not self.auth.is_valid:
                speaker.speak("Please log in first")
                return

            speaker.speak("Fetching equipped cosmetics")
            text = lm.equipped_text(self.auth, self.cosmetics_data)
            if text is None:
                speaker.speak("Failed to fetch equipped cosmetics")
                messageBox("Could not retrieve equipped cosmetics from Epic Games.", "Error",
                           wx.OK | wx.ICON_ERROR, self)
                return

            speaker.speak("Equipped cosmetics loaded")

            # Show in a dialog
            dlg = wx.Dialog(self, title="Currently Equipped Cosmetics", size=(500, 600))
            dlg_sizer = wx.BoxSizer(wx.VERTICAL)

            text_ctrl = wx.TextCtrl(dlg, value=text,
                                    style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP)
            dlg_sizer.Add(text_ctrl, proportion=1, flag=wx.EXPAND | wx.ALL, border=10)

            close_btn = StyledButton(dlg, wx.ID_CLOSE, "&Close")
            close_btn.Bind(wx.EVT_BUTTON, lambda e: dlg.EndModal(wx.ID_CLOSE))
            dlg_sizer.Add(close_btn, flag=wx.ALIGN_CENTER | wx.ALL, border=10)

            dlg.SetSizer(dlg_sizer)
            dlg.CentreOnScreen()

            # Allow Escape to close
            def on_dlg_key(evt):
                if evt.GetKeyCode() == wx.WXK_ESCAPE:
                    dlg.EndModal(wx.ID_CLOSE)
                else:
                    evt.Skip()
            dlg.Bind(wx.EVT_CHAR_HOOK, on_dlg_key)

            dlg.ShowModal()
            dlg.Destroy()

        except Exception as e:
            logger.error(f"Error viewing equipped cosmetics: {e}")
            speaker.speak("Error viewing equipped cosmetics")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)

    def on_view_loadouts(self, event):
        """Show saved loadout presets from the Locker Service"""
        try:
            if not self.auth or not self.auth.is_valid:
                speaker.speak("Please log in first")
                return

            speaker.speak("Fetching saved loadouts")

            merged_presets = lm.load_loadouts(self.auth)
            if merged_presets is None:
                speaker.speak("Failed to fetch loadouts")
                messageBox("Could not retrieve loadout presets from Epic Games.", "Error",
                           wx.OK | wx.ICON_ERROR, self)
                return
            if not merged_presets:
                speaker.speak("No saved loadouts found")
                messageBox("You have no saved loadout presets.", "Loadouts",
                           wx.OK | wx.ICON_INFORMATION, self)
                return

            total = len(merged_presets)
            speaker.speak(f"Found {total} loadouts")

            # Show loadout selection dialog
            dlg = wx.Dialog(self, title=f"Loadouts ({total})", size=(600, 700))
            dlg_sizer = wx.BoxSizer(wx.VERTICAL)

            # Filter by type
            filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
            filter_sizer.Add(wx.StaticText(dlg, label="Filter by type:"),
                             flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)

            type_filter = wx.Choice(dlg, choices=lm.loadout_filter_choices())
            type_filter.SetSelection(0)
            filter_sizer.Add(type_filter)
            dlg_sizer.Add(filter_sizer, flag=wx.ALL, border=10)

            # Loadout list
            list_box = wx.ListBox(dlg, style=wx.LB_SINGLE)
            dlg_sizer.Add(list_box, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)

            # Detail text
            detail_text = wx.TextCtrl(dlg, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP,
                                      size=(-1, 150))
            dlg_sizer.Add(detail_text, flag=wx.EXPAND | wx.ALL, border=10)

            filtered_entries = []

            def refresh_list(filter_type="All"):
                nonlocal filtered_entries
                list_box.Clear()
                filtered_entries = lm.filter_loadouts(merged_presets, filter_type)
                for entry in filtered_entries:
                    list_box.Append(lm.loadout_label(entry))
                detail_text.SetValue("")

            refresh_list()

            def on_filter_changed(evt):
                refresh_list(type_filter.GetString(type_filter.GetSelection()))
                speaker.speak(f"Showing {list_box.GetCount()} loadouts")

            type_filter.Bind(wx.EVT_CHOICE, on_filter_changed)

            def on_loadout_selected(evt):
                idx = list_box.GetSelection()
                if idx == wx.NOT_FOUND or idx >= len(filtered_entries):
                    return
                detail_text.SetValue(lm.loadout_detail_text(filtered_entries[idx], self.cosmetics_data))

            list_box.Bind(wx.EVT_LISTBOX, on_loadout_selected)

            # First-letter navigation
            def on_list_char(evt):
                key = evt.GetUnicodeKey()
                if key == wx.WXK_NONE:
                    evt.Skip()
                    return
                char = chr(key).lower()
                if not char.isalnum():
                    evt.Skip()
                    return
                # Find next item starting with this letter, wrapping around
                count = list_box.GetCount()
                if count == 0:
                    evt.Skip()
                    return
                current = list_box.GetSelection()
                start = (current + 1) % count if current != wx.NOT_FOUND else 0
                for offset in range(count):
                    idx = (start + offset) % count
                    item_text = list_box.GetString(idx).lower()
                    if item_text.startswith(char):
                        list_box.SetSelection(idx)
                        # Trigger the selection handler
                        sel_evt = wx.CommandEvent(wx.wxEVT_LISTBOX, list_box.GetId())
                        sel_evt.SetInt(idx)
                        wx.PostEvent(list_box, sel_evt)
                        return
                evt.Skip()

            list_box.Bind(wx.EVT_CHAR, on_list_char)

            # Buttons
            btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

            def selected_entry():
                idx = list_box.GetSelection()
                if idx == wx.NOT_FOUND or idx >= len(filtered_entries):
                    speaker.speak("No loadout selected")
                    return None
                return filtered_entries[idx]

            # Equip via API
            equip_api_btn = StyledButton(dlg, label="Equip via &API")
            equip_api_btn.SetToolTip("Equip instantly via Locker Service API. Changes apply next match or game restart.")

            def on_equip_api(evt):
                entry = selected_entry()
                if entry is None:
                    return
                result = messageBox(lm.loadout_api_prompt(entry), "Equip via API", wx.YES_NO | wx.ICON_QUESTION, dlg)
                if result == wx.YES:
                    if not lm.equip_loadout_via_api(self.auth, entry):
                        messageBox(f"Failed to equip '{entry.get('displayName', '(unnamed)')}' via API.", "Error",
                                   wx.OK | wx.ICON_ERROR, dlg)

            equip_api_btn.Bind(wx.EVT_BUTTON, on_equip_api)
            btn_sizer.Add(equip_api_btn, flag=wx.RIGHT, border=5)

            # Equip via UI automation
            equip_ui_btn = StyledButton(dlg, label="Equip in &Game (UI)")
            equip_ui_btn.SetToolTip("Equip each item one-by-one using mouse automation in the Fortnite locker UI.")

            def on_equip_ui(evt):
                entry = selected_entry()
                if entry is None:
                    return
                items_to_equip = lm.loadout_ui_items(entry, self.cosmetics_data)
                if not items_to_equip:
                    speaker.speak("No equippable items in this loadout")
                    return

                result = messageBox(lm.loadout_ui_prompt(entry, items_to_equip), "Equip in Game",
                                    wx.YES_NO | wx.ICON_QUESTION, dlg)
                if result == wx.YES:
                    dlg.Iconize(True)
                    time.sleep(0.2)
                    lm.perform_loadout_ui_automation(items_to_equip, entry.get("displayName", "(unnamed)"))
                    dlg.Iconize(False)
                    dlg.Raise()

            equip_ui_btn.Bind(wx.EVT_BUTTON, on_equip_ui)
            btn_sizer.Add(equip_ui_btn, flag=wx.RIGHT, border=5)

            # Delete local loadout button
            delete_btn = StyledButton(dlg, label="&Delete Local")
            delete_btn.SetToolTip("Delete a locally saved loadout")

            def on_delete_local(evt):
                entry = selected_entry()
                if entry is None:
                    return
                if not lm.is_local_loadout(entry):
                    speaker.speak("Can only delete locally saved loadouts")
                    messageBox("This loadout is from Epic's servers and cannot be deleted from FA11y.",
                               "Cannot Delete", wx.OK | wx.ICON_INFORMATION, dlg)
                    return
                name = entry.get("displayName", "(unnamed)")
                result = messageBox(f"Delete local loadout '{name}'?", "Delete Loadout",
                                    wx.YES_NO | wx.ICON_WARNING, dlg)
                if result == wx.YES and lm.delete_local_loadout(name):
                    # Remove from merged list too
                    merged_presets[:] = [m for m in merged_presets
                                         if not (m.get("displayName") == name and m.get("source") == "local")]
                    refresh_list(type_filter.GetString(type_filter.GetSelection()))

            delete_btn.Bind(wx.EVT_BUTTON, on_delete_local)
            btn_sizer.Add(delete_btn, flag=wx.RIGHT, border=5)

            close_btn = StyledButton(dlg, wx.ID_CLOSE, "&Close")
            close_btn.Bind(wx.EVT_BUTTON, lambda e: dlg.EndModal(wx.ID_CLOSE))
            btn_sizer.Add(close_btn)

            dlg_sizer.Add(btn_sizer, flag=wx.ALIGN_CENTER | wx.ALL, border=10)

            dlg.SetSizer(dlg_sizer)
            dlg.CentreOnScreen()

            # Allow Escape to close
            def on_dlg_key(evt):
                if evt.GetKeyCode() == wx.WXK_ESCAPE:
                    dlg.EndModal(wx.ID_CLOSE)
                else:
                    evt.Skip()
            dlg.Bind(wx.EVT_CHAR_HOOK, on_dlg_key)

            dlg.ShowModal()
            dlg.Destroy()

        except Exception as e:
            logger.error(f"Error viewing loadouts: {e}")
            speaker.speak("Error viewing loadouts")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)

    def on_save_loadout(self, event):
        """Save the currently equipped cosmetics as a local loadout preset."""
        try:
            if not self.auth or not self.auth.is_valid:
                speaker.speak("Please log in first")
                return

            # Ask which categories to save
            choice_dlg = wx.SingleChoiceDialog(
                self,
                "Which loadout type do you want to save?\n\n"
                "Select 'All Categories' to save everything at once.",
                "Save Loadout",
                [c[0] for c in lm.SAVE_LOADOUT_CHOICES]
            )
            if choice_dlg.ShowModal() != wx.ID_OK:
                choice_dlg.Destroy()
                return
            selected_idx = choice_dlg.GetSelection()
            choice_dlg.Destroy()

            friendly_name, loadout_type = lm.SAVE_LOADOUT_CHOICES[selected_idx]

            # Get a name for the loadout
            name_dlg = wx.TextEntryDialog(self, "Enter a name for this loadout:", "Loadout Name",
                                          f"My {friendly_name} Loadout")
            if name_dlg.ShowModal() != wx.ID_OK:
                name_dlg.Destroy()
                return
            loadout_name = name_dlg.GetValue().strip()
            name_dlg.Destroy()

            if not loadout_name:
                speaker.speak("No name entered, cancelled")
                return

            if lm.loadout_exists(loadout_name):
                result = messageBox(
                    f"A loadout named '{loadout_name}' already exists.\n\n"
                    "Do you want to overwrite it?",
                    "Loadout Exists",
                    wx.YES_NO | wx.ICON_WARNING, self)
                if result != wx.YES:
                    speaker.speak("Cancelled. Choose a different name.")
                    return

            result = lm.save_loadout(self.auth, friendly_name, loadout_type, loadout_name)
            if result["ok"]:
                messageBox(result["message"], "Loadout Saved", wx.OK | wx.ICON_INFORMATION, self)

        except Exception as e:
            logger.error(f"Error saving loadout: {e}")
            speaker.speak("Error saving loadout")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)

    def on_close(self, event):
        """Handle close button"""
        self.request_close(wx.ID_CLOSE)

    def on_login(self, event):
        """Handle Login button"""
        try:
            from lib.guis.epic_login_dialog import LoginDialog

            # Get auth instance if not available
            if not self.auth:
                from lib.utilities.epic_auth import get_epic_auth_instance
                self.auth = get_epic_auth_instance()

            # Show login dialog
            dlg = LoginDialog(self, self.auth)
            result = dlg.ShowModal()
            dlg.Destroy()

            if result == wx.ID_OK:
                # Login successful, enable owned button and enable it
                self.owned_btn.Enable(True)
                self.owned_btn.SetValue(True)
                self.login_btn.SetLabel("Logged In")
                self.login_btn.Enable(False)

                # Update filter state
                speaker.speak(f"Logged in as {self.auth.display_name}")
                self.on_owned_toggle(None)

        except Exception as e:
            logger.error(f"Error during login: {e}")
            speaker.speak("Error during login")
            messageBox(f"Error: {e}", "Login Error", wx.OK | wx.ICON_ERROR, self)

    def on_owned_toggle(self, event):
        """Handle owned cosmetics toggle button"""
        try:
            if not self.auth or not self.auth.display_name:
                speaker.speak("Please log in first")
                self.owned_btn.SetValue(False)
                return

            outcome = lm.set_owned_only(self.cosmetics_data, self.auth, self.owned_ids, self.owned_btn.GetValue())
            for message in outcome.messages:
                speaker.speak(message)
            self.owned_only = outcome.owned_only
            self.owned_ids = outcome.owned_ids
            self.owned_btn.SetValue(outcome.owned_only)

            if outcome.expired:
                result = messageBox(
                    "Your Epic Games login has expired.\n\nWould you like to log in again?",
                    "Login Expired",
                    wx.YES_NO | wx.ICON_WARNING,
                    self
                )
                if result == wx.YES:
                    # Reset auth state
                    self.owned_btn.Enable(False)
                    self.login_btn.SetLabel("&Login")
                    self.login_btn.Enable(True)
                    # Trigger login
                    wx.CallAfter(self.on_login, None)
            elif outcome.error:
                messageBox(outcome.error, "Error", wx.OK | wx.ICON_ERROR, self)

        except Exception as e:
            logger.error(f"Error toggling owned mode: {e}")
            speaker.speak("Error toggling owned filter")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)
            self.owned_btn.SetValue(not self.owned_only)


def launch_locker_gui():
    """Launch the unified locker GUI"""
    # The hub's Locker page loads its own data in the background.
    from lib.hub import get_hub
    hub = get_hub()
    if hub is not None and hub.has_page('locker'):
        hub.show_page('locker', summon=True)
        return None

    current_window = ctypes.windll.user32.GetForegroundWindow()
    app = None
    app_created = False

    try:
        # Check if wx.App already exists
        existing_app = wx.GetApp()
        if existing_app is None:
            app = wx.App(False)
            app_created = True
        else:
            app = existing_app
            app_created = False

        # Import epic auth module
        try:
            from lib.utilities.epic_auth import get_or_create_cosmetics_cache, get_epic_auth_instance
        except ImportError:
            logger.error("Failed to import epic_auth module")
            speaker.speak("Error loading authentication module")
            messageBox(
                "Failed to load authentication module. Please check installation.",
                "Error",
                wx.OK | wx.ICON_ERROR
            )
            return None

        # Get auth instance (may have cached login)
        auth_instance = get_epic_auth_instance()

        # Load cosmetics data
        logger.info("Loading cosmetics data...")
        speaker.speak("Loading cosmetics data")

        cosmetics_data = get_or_create_cosmetics_cache(force_refresh=False, owned_only=False)

        if not cosmetics_data:
            logger.error("Failed to load cosmetics data")
            speaker.speak("Failed to load cosmetics data")
            result = messageBox(
                "Failed to load cosmetics data. This could be due to:\n\n"
                "1. No internet connection\n"
                "2. Fortnite-API.com is unavailable\n\n"
                "Would you like to retry?",
                "Error Loading Data",
                wx.YES_NO | wx.ICON_ERROR
            )

            if result == wx.YES:
                cosmetics_data = get_or_create_cosmetics_cache(force_refresh=True, owned_only=False)
                if not cosmetics_data:
                    return None
            else:
                return None

        logger.info(f"Loaded {len(cosmetics_data)} cosmetics")

        # Default to owned cosmetics if authenticated
        default_owned_only = bool(auth_instance and auth_instance.display_name)
        if default_owned_only:
            logger.info(f"User authenticated as {auth_instance.display_name}, defaulting to owned cosmetics")

        if default_owned_only:
            speaker.speak(f"Fortnite Locker. Logged in as {auth_instance.display_name}. Loading owned cosmetics.")
        else:
            speaker.speak(f"Fortnite Locker. {len(cosmetics_data)} cosmetics loaded.")

        # Show as a hub page, or a modal dialog when the hub isn't running
        try:
            show_view(
                'locker',
                lambda host: LockerView(host, cosmetics_data, auth_instance=auth_instance,
                                        owned_only=default_owned_only),
                size=(600, 700)
            )
        finally:
            if app:
                app.ProcessPendingEvents()

    except Exception as e:
        logger.error(f"Error launching locker: {e}")
        speaker.speak("Error opening locker")
        messageBox(f"Failed to launch locker: {e}", "Error", wx.OK | wx.ICON_ERROR)
        return None


# Alias for backward compatibility
launch_locker_viewer = launch_locker_gui
launch_locker_selector = launch_locker_gui
