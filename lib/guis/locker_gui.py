"""
Unified Locker GUI for FA11y
Browse your cosmetics collection and equip them in Fortnite
"""
import os
import sys
import json
import time
import logging
import gc
from typing import List, Optional, Dict
import ctypes
import ctypes.wintypes

import wx
import pyautogui
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import (
    AccessibleDialog, BoxSizerHelper, messageBox,
    ensure_window_focus_and_center_mouse, SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS
)

# Initialize logger
logger = logging.getLogger(__name__)

# Global speaker instance
speaker = Auto()

# Map backend types to friendly names and slot info
COSMETIC_TYPE_MAP = {
    "AthenaCharacter": {"name": "Outfit", "category": "Character", "slot": 1},
    "AthenaBackpack": {"name": "Back Bling", "category": "Character", "slot": 2},
    "AthenaPickaxe": {"name": "Pickaxe", "category": "Character", "slot": 3},
    "AthenaGlider": {"name": "Glider", "category": "Character", "slot": 4},
    "AthenaShoes": {"name": "Kicks", "category": "Character", "slot": 5},
    "AthenaSkyDiveContrail": {"name": "Contrail", "category": "Character", "slot": 6},
    "AthenaDance": {"name": "Emote", "category": "Emotes", "slot": None},  # Multiple slots
    "AthenaPetCarrier": {"name": "Pet", "category": "Sidekicks", "slot": 1},
    "AthenaItemWrap": {"name": "Wrap", "category": "Wraps", "slot": None},  # Multiple slots
    "AthenaLoadingScreen": {"name": "Loading Screen", "category": "Lobby", "slot": 3},
    "AthenaMusicPack": {"name": "Music", "category": "Lobby", "slot": 2},
    "VehicleCosmetics_Body": {"name": "Car Body", "category": "Cars", "slot": 1}
}

# Slot coordinates for automation
SLOT_COORDS = {
    1: (260, 400),
    2: (420, 400),
    3: (570, 400),
    4: (720, 400),
    5: (260, 560),
    6: (420, 560),
    7: (560, 550),
    8: (720, 550)
}

# Category positions in Fortnite UI
CATEGORY_COORDS = {
    'Character': (110, 280),
    'Emotes': (110, 335),
    'Sidekicks': (110, 390),
    'Wraps': (110, 445),
    'Lobby': (110, 500),
    'Cars': (110, 555),
    'Instruments': (110, 610),
    'Music': (110, 665)
}

SORT_OPTIONS = [
    "Rarity (Highest First)",
    "Rarity (Lowest First)",
    "Name (A-Z)",
    "Name (Z-A)",
    "Type",
    "Newest First",
    "Oldest First",
    "Favorites First"
]


class LockerGUI(AccessibleDialog):
    """Unified Locker GUI for browsing and equipping cosmetics"""

    def __init__(self, parent, cosmetics_data: List[dict], auth_instance=None, owned_only: bool = False):
        super().__init__(parent, title="Fortnite Locker", helpId="LockerGUI")
        self.cosmetics_data = cosmetics_data
        self.filtered_cosmetics = cosmetics_data.copy()
        self.auth = auth_instance
        self.owned_only = owned_only
        self.owned_ids = set()  # Will be populated when filtering by owned

        # Current filter/sort state
        self.current_search = ""
        self.current_type_filter = "All"
        self.current_sort = "Rarity (Highest First)"

        # Stats
        self.stats = self._calculate_stats()

        self.setupDialog()
        self.SetSize((900, 700))
        self.CentreOnScreen()

    def _calculate_stats(self) -> Dict[str, int]:
        """Calculate statistics about cosmetics"""
        stats = {
            "total": len(self.cosmetics_data),
            "favorites": sum(1 for c in self.cosmetics_data if c.get("favorite", False))
        }
        return stats

    def makeSettings(self, sizer: BoxSizerHelper):
        """Create the dialog content"""

        # Top bar with login status and button
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Header with stats
        header_text = f"Total Cosmetics: {self.stats['total']}"
        if self.stats.get('favorites', 0) > 0:
            header_text += f" | Favorites: {self.stats['favorites']}"

        # Add user info if logged in
        if self.auth and self.auth.display_name:
            header_text += f" | Logged in as: {self.auth.display_name}"

        header_label = wx.StaticText(self, label=header_text)
        header_font = header_label.GetFont()
        header_font.PointSize += 2
        header_font = header_font.Bold()
        header_label.SetFont(header_font)
        top_sizer.Add(header_label, flag=wx.ALIGN_CENTER_VERTICAL)

        top_sizer.AddStretchSpacer()

        # Login button
        if self.auth and self.auth.display_name:
            self.login_btn = wx.Button(self, label="Logged In", size=(120, -1))
            self.login_btn.Enable(False)
        else:
            self.login_btn = wx.Button(self, label="&Login", size=(120, -1))
            self.login_btn.Bind(wx.EVT_BUTTON, self.on_login)

        top_sizer.Add(self.login_btn, flag=wx.ALIGN_CENTER_VERTICAL)

        sizer.addItem(top_sizer, flag=wx.EXPAND)

        # Owned only checkbox
        self.owned_checkbox = wx.CheckBox(self, label="Show Only My Cosmetics")
        self.owned_checkbox.SetValue(self.owned_only)
        self.owned_checkbox.Bind(wx.EVT_CHECKBOX, self.on_owned_toggle)
        if not (self.auth and self.auth.display_name):
            self.owned_checkbox.Enable(False)
        sizer.addItem(self.owned_checkbox)

        # Instructions
        instructions = wx.StaticText(self, label="Double-click a cosmetic to equip it in Fortnite")
        sizer.addItem(instructions)

        # Search box
        self.search_box = sizer.addLabeledControl(
            "Search:",
            wx.TextCtrl,
            size=(300, -1)
        )
        self.search_box.Bind(wx.EVT_TEXT, self.on_search_changed)

        # Filter controls in horizontal layout
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Type filter
        filter_label = wx.StaticText(self, label="Type:")
        filter_sizer.Add(filter_label, flag=wx.ALIGN_CENTER_VERTICAL)
        filter_sizer.AddSpacer(10)

        type_choices = ["All"] + sorted(set(info["name"] for info in COSMETIC_TYPE_MAP.values()))
        self.type_filter = wx.Choice(self, choices=type_choices)
        self.type_filter.SetSelection(0)
        self.type_filter.Bind(wx.EVT_CHOICE, self.on_filter_changed)
        filter_sizer.Add(self.type_filter)

        filter_sizer.AddSpacer(20)

        # Sort control
        sort_label = wx.StaticText(self, label="Sort:")
        filter_sizer.Add(sort_label, flag=wx.ALIGN_CENTER_VERTICAL)
        filter_sizer.AddSpacer(10)

        self.sort_choice = wx.Choice(self, choices=SORT_OPTIONS)
        self.sort_choice.SetSelection(0)
        self.sort_choice.Bind(wx.EVT_CHOICE, self.on_sort_changed)
        filter_sizer.Add(self.sort_choice)

        sizer.addItem(filter_sizer)

        # Results count
        self.results_label = wx.StaticText(self, label="")
        sizer.addItem(self.results_label)

        # Cosmetics list
        self.cosmetics_list = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_VRULES
        )

        # Setup columns
        self.cosmetics_list.InsertColumn(0, "Name", width=300)
        self.cosmetics_list.InsertColumn(1, "Type", width=150)
        self.cosmetics_list.InsertColumn(2, "Rarity", width=100)
        self.cosmetics_list.InsertColumn(3, "Season", width=100)

        self.cosmetics_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_item_selected)
        self.cosmetics_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_item_activated)
        self.cosmetics_list.Bind(wx.EVT_LIST_ITEM_FOCUSED, self.on_item_focused)

        sizer.addItem(
            self.cosmetics_list,
            flag=wx.EXPAND,
            proportion=1
        )

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

        self.equip_btn = wx.Button(self, label="&Equip Selected")
        self.equip_btn.Bind(wx.EVT_BUTTON, self.on_equip_clicked)
        button_sizer.Add(self.equip_btn)

        button_sizer.AddSpacer(10)

        self.refresh_btn = wx.Button(self, label="&Refresh Data")
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        button_sizer.Add(self.refresh_btn)

        button_sizer.AddSpacer(10)

        self.export_btn = wx.Button(self, label="E&xport List")
        self.export_btn.Bind(wx.EVT_BUTTON, self.on_export)
        button_sizer.Add(self.export_btn)

        button_sizer.AddStretchSpacer()

        self.close_btn = wx.Button(self, label="&Close")
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        button_sizer.Add(self.close_btn)

        sizer.addItem(button_sizer, flag=wx.EXPAND)

        # Bind key events
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)

        # Defer initial population for faster startup
        wx.CallAfter(self.update_list)

    def onKeyEvent(self, event):
        """Handle key events for shortcuts"""
        key_code = event.GetKeyCode()

        if key_code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return

        # Allow normal navigation
        event.Skip()

    def on_search_changed(self, event):
        """Handle search text changes"""
        self.current_search = self.search_box.GetValue()
        self.update_list()

    def on_filter_changed(self, event):
        """Handle type filter changes"""
        self.current_type_filter = self.type_filter.GetStringSelection()
        self.update_list()

    def on_sort_changed(self, event):
        """Handle sort option changes"""
        self.current_sort = self.sort_choice.GetStringSelection()
        self.update_list()

    def filter_cosmetics(self) -> List[dict]:
        """Filter cosmetics based on current search, type filter, and owned status"""
        filtered = []
        search_lower = self.current_search.lower()

        for cosmetic in self.cosmetics_data:
            # Owned filter (check first for performance)
            if self.owned_only:
                cosmetic_id = cosmetic.get("id", "").lower()
                if cosmetic_id not in self.owned_ids:
                    continue

            # Type filter
            if self.current_type_filter != "All":
                cosmetic_type = cosmetic.get("type", "")
                type_info = COSMETIC_TYPE_MAP.get(cosmetic_type, {})
                friendly_type = type_info.get("name", cosmetic_type)
                if friendly_type != self.current_type_filter:
                    continue

            # Search filter
            if search_lower:
                name = cosmetic.get("name", "").lower()
                description = cosmetic.get("description", "").lower()
                rarity = cosmetic.get("rarity", "").lower()

                if not (search_lower in name or search_lower in description or search_lower in rarity):
                    continue

            filtered.append(cosmetic)

        return filtered

    def sort_cosmetics(self, cosmetics: List[dict]) -> List[dict]:
        """Sort cosmetics based on current sort option"""
        if self.current_sort == "Rarity (Highest First)":
            return sorted(cosmetics, key=lambda x: (-x.get("rarity_value", 0), x.get("name", "")))
        elif self.current_sort == "Rarity (Lowest First)":
            return sorted(cosmetics, key=lambda x: (x.get("rarity_value", 0), x.get("name", "")))
        elif self.current_sort == "Name (A-Z)":
            return sorted(cosmetics, key=lambda x: x.get("name", "").lower())
        elif self.current_sort == "Name (Z-A)":
            return sorted(cosmetics, key=lambda x: x.get("name", "").lower(), reverse=True)
        elif self.current_sort == "Type":
            return sorted(cosmetics, key=lambda x: (
                COSMETIC_TYPE_MAP.get(x.get("type", ""), {}).get("name", x.get("type", "")),
                x.get("name", "")
            ))
        elif self.current_sort == "Newest First":
            return sorted(cosmetics, key=lambda x: (
                -int(x.get("introduction_chapter", "1")),
                -int(x.get("introduction_season", "1")),
                x.get("name", "")
            ))
        elif self.current_sort == "Oldest First":
            return sorted(cosmetics, key=lambda x: (
                int(x.get("introduction_chapter", "1")),
                int(x.get("introduction_season", "1")),
                x.get("name", "")
            ))
        elif self.current_sort == "Favorites First":
            return sorted(cosmetics, key=lambda x: (
                not x.get("favorite", False),
                -x.get("rarity_value", 0),
                x.get("name", "")
            ))
        return cosmetics

    def update_list(self):
        """Update the cosmetics list based on current filters and sort"""
        # Filter and sort
        self.filtered_cosmetics = self.filter_cosmetics()
        self.filtered_cosmetics = self.sort_cosmetics(self.filtered_cosmetics)

        # Update results label
        if self.owned_only:
            base_count = len(self.owned_ids)
            self.results_label.SetLabel(f"Showing {len(self.filtered_cosmetics)} of {base_count} owned cosmetics")
        else:
            total = len(self.cosmetics_data)
            self.results_label.SetLabel(f"Showing {len(self.filtered_cosmetics)} of {total} cosmetics")

        # Freeze to prevent flickering and improve performance
        self.cosmetics_list.Freeze()
        try:
            # Clear list
            self.cosmetics_list.DeleteAllItems()

            # Populate list with smart limit based on mode
            # Allow more items for owned cosmetics (smaller set), fewer for all cosmetics
            if self.owned_only:
                max_items = min(5000, len(self.filtered_cosmetics))  # Higher limit for owned
            else:
                max_items = min(1000, len(self.filtered_cosmetics))  # Lower limit for all

            for idx in range(max_items):
                cosmetic = self.filtered_cosmetics[idx]

                name = cosmetic.get("name", "Unknown")
                if cosmetic.get("favorite", False):
                    name = "⭐ " + name

                cosmetic_type = cosmetic.get("type", "Unknown")
                type_info = COSMETIC_TYPE_MAP.get(cosmetic_type, {})
                friendly_type = type_info.get("name", cosmetic_type)

                rarity = cosmetic.get("rarity", "common").title()
                season = f"C{cosmetic.get('introduction_chapter', '?')}S{cosmetic.get('introduction_season', '?')}"

                # Insert item
                index = self.cosmetics_list.InsertItem(idx, name)
                self.cosmetics_list.SetItem(index, 1, friendly_type)
                self.cosmetics_list.SetItem(index, 2, rarity)
                self.cosmetics_list.SetItem(index, 3, season)

                # Set item data to index in filtered list
                self.cosmetics_list.SetItemData(index, idx)

                # Color code by rarity
                color = self.get_rarity_color(rarity.lower())
                if color:
                    self.cosmetics_list.SetItemTextColour(index, color)

            # Warn if showing truncated results
            if len(self.filtered_cosmetics) > max_items:
                current_label = self.results_label.GetLabel()
                self.results_label.SetLabel(f"{current_label} (showing first {max_items} - refine search)")

        finally:
            self.cosmetics_list.Thaw()

        # Auto-select first item if available
        if self.filtered_cosmetics:
            self.cosmetics_list.Select(0)
            self.cosmetics_list.Focus(0)

    def get_rarity_color(self, rarity: str) -> Optional[wx.Colour]:
        """Get color for rarity"""
        colors = {
            "common": wx.Colour(170, 170, 170),
            "uncommon": wx.Colour(96, 170, 58),
            "rare": wx.Colour(73, 172, 242),
            "epic": wx.Colour(177, 91, 226),
            "legendary": wx.Colour(211, 120, 65),
            "mythic": wx.Colour(255, 223, 0),
            "marvel": wx.Colour(197, 51, 52),
            "dc": wx.Colour(84, 117, 199),
            "starwars": wx.Colour(231, 196, 19),
            "icon": wx.Colour(0, 217, 217),
            "gaminglegends": wx.Colour(137, 86, 255),
        }
        return colors.get(rarity.lower())

    def on_item_focused(self, event):
        """Handle item focus for announcements"""
        index = event.GetIndex()
        cosmetic_idx = self.cosmetics_list.GetItemData(index)

        if 0 <= cosmetic_idx < len(self.filtered_cosmetics):
            cosmetic = self.filtered_cosmetics[cosmetic_idx]
            name = cosmetic.get("name", "Unknown")
            cosmetic_type = cosmetic.get("type", "")
            type_info = COSMETIC_TYPE_MAP.get(cosmetic_type, {})
            friendly_type = type_info.get("name", "Unknown")
            rarity = cosmetic.get("rarity", "common").title()

            # Announce with index
            total = len(self.filtered_cosmetics)
            announcement = f"Item {index + 1} of {total}: {name}, {friendly_type}, {rarity}"
            wx.CallLater(150, lambda: speaker.speak(announcement))

    def on_item_selected(self, event):
        """Handle item selection in list"""
        index = event.GetIndex()
        cosmetic_idx = self.cosmetics_list.GetItemData(index)

        if 0 <= cosmetic_idx < len(self.filtered_cosmetics):
            cosmetic = self.filtered_cosmetics[cosmetic_idx]
            self.show_cosmetic_details(cosmetic)

    def on_item_activated(self, event):
        """Handle item double-click/activation - equip the cosmetic"""
        index = event.GetIndex()
        cosmetic_idx = self.cosmetics_list.GetItemData(index)

        if 0 <= cosmetic_idx < len(self.filtered_cosmetics):
            cosmetic = self.filtered_cosmetics[cosmetic_idx]
            self.equip_cosmetic(cosmetic)

    def on_equip_clicked(self, event):
        """Handle Equip button click"""
        index = self.cosmetics_list.GetFirstSelected()
        if index == -1:
            speaker.speak("No cosmetic selected")
            messageBox("Please select a cosmetic to equip", "No Selection", wx.OK | wx.ICON_WARNING, self)
            return

        cosmetic_idx = self.cosmetics_list.GetItemData(index)
        if 0 <= cosmetic_idx < len(self.filtered_cosmetics):
            cosmetic = self.filtered_cosmetics[cosmetic_idx]
            self.equip_cosmetic(cosmetic)

    def show_cosmetic_details(self, cosmetic: dict):
        """Show cosmetic details in the details panel"""
        details = []

        details.append(f"Name: {cosmetic.get('name', 'Unknown')}")

        cosmetic_type = cosmetic.get("type", "Unknown")
        type_info = COSMETIC_TYPE_MAP.get(cosmetic_type, {})
        friendly_type = type_info.get("name", cosmetic_type)
        details.append(f"Type: {friendly_type}")

        details.append(f"Rarity: {cosmetic.get('rarity', 'common').title()}")
        details.append(f"Season: Chapter {cosmetic.get('introduction_chapter', '?')}, Season {cosmetic.get('introduction_season', '?')}")

        if cosmetic.get("description"):
            details.append(f"\nDescription: {cosmetic['description']}")

        if cosmetic.get("favorite"):
            details.append("\n⭐ FAVORITE")

        self.details_text.SetValue("\n".join(details))

    def equip_cosmetic(self, cosmetic: dict):
        """Equip a cosmetic using UI automation"""
        try:
            name = cosmetic.get("name", "Unknown")
            cosmetic_type = cosmetic.get("type", "")
            type_info = COSMETIC_TYPE_MAP.get(cosmetic_type, {})
            category = type_info.get("category")
            slot = type_info.get("slot")

            if not category:
                speaker.speak(f"Cannot equip {name}. Unknown category.")
                messageBox(f"Cannot equip {name}.\nUnknown cosmetic category.", "Cannot Equip", wx.OK | wx.ICON_WARNING, self)
                return

            # For items with multiple slots (emotes, wraps), ask user
            if slot is None:
                slot = self.ask_for_slot(cosmetic_type, name)
                if slot is None:
                    return

            speaker.speak(f"Equipping {name}")
            logger.info(f"Equipping {name} to {category} slot {slot}")

            # Hide dialog before automation
            self.Hide()
            wx.SafeYield()  # Process any pending UI events

            try:
                # Perform the equip automation
                success = self.perform_equip_automation(category, slot, name)

                # Always show dialog again on UI thread
                wx.CallAfter(self._show_after_equip, success, name)

            except Exception as automation_error:
                logger.error(f"Error during automation: {automation_error}")
                wx.CallAfter(self._show_after_equip, False, name)
                raise

        except Exception as e:
            logger.error(f"Error equipping cosmetic: {e}")
            speaker.speak("Error equipping cosmetic")
            # Make sure dialog shows even on error
            if not self.IsShown():
                wx.CallAfter(self.Show)
            wx.CallAfter(lambda: messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self))

    def _show_after_equip(self, success: bool, name: str):
        """Show dialog after equip automation completes"""
        try:
            self.Show()
            self.Raise()
            wx.SafeYield()

            if success:
                speaker.speak(f"{name} equipped!")
            else:
                speaker.speak("Equip failed")
                messageBox("Failed to equip cosmetic. Make sure Fortnite is open and in the locker.", "Equip Failed", wx.OK | wx.ICON_ERROR, self)
        except Exception as e:
            logger.error(f"Error showing dialog after equip: {e}")

    def ask_for_slot(self, cosmetic_type: str, name: str) -> Optional[int]:
        """Ask user which slot to equip to (for emotes, wraps, etc.)"""
        if cosmetic_type == "AthenaDance":
            # Emotes: slots 1-6
            dlg = wx.SingleChoiceDialog(
                self,
                f"Select which emote slot to equip '{name}' to:",
                "Select Emote Slot",
                ["Emote 1", "Emote 2", "Emote 3", "Emote 4", "Emote 5", "Emote 6"]
            )
        elif cosmetic_type == "AthenaItemWrap":
            # Wraps: slots 1-7
            dlg = wx.SingleChoiceDialog(
                self,
                f"Select which wrap slot to equip '{name}' to:",
                "Select Wrap Slot",
                ["Rifles", "Shotguns", "Submachine Guns", "Snipers", "Pistols", "Utility", "Vehicles"]
            )
        else:
            return None

        if dlg.ShowModal() == wx.ID_OK:
            slot = dlg.GetSelection() + 1
            dlg.Destroy()
            return slot
        else:
            dlg.Destroy()
            return None

    def perform_equip_automation(self, category: str, slot: int, item_name: str) -> bool:
        """Perform the UI automation to equip an item"""
        try:
            # Get slot coordinates
            slot_coords = SLOT_COORDS.get(slot)
            if not slot_coords:
                logger.error(f"Unknown slot number: {slot}")
                return False

            # Wait a moment for dialog to hide
            time.sleep(0.5)

            # Click locker button
            pyautogui.moveTo(420, 69, duration=0.05)
            pyautogui.click()
            time.sleep(0.3)

            # Click category
            category_coords = CATEGORY_COORDS.get(category)
            if category_coords:
                pyautogui.moveTo(category_coords[0], category_coords[1], duration=0.05)
                pyautogui.click()
                time.sleep(0.3)

                # Move mouse 500 pixels right and wait
                current_x, current_y = pyautogui.position()
                pyautogui.moveTo(current_x + 500, current_y, duration=0.05)
                time.sleep(1.0)

            # Click slot
            pyautogui.moveTo(slot_coords[0], slot_coords[1], duration=0.05)
            pyautogui.click()
            time.sleep(1.0)

            # Click search bar
            pyautogui.moveTo(1030, 210, duration=0.05)
            pyautogui.click()
            time.sleep(0.5)

            # Type the item name (use write() for better special character support)
            pyautogui.write(item_name, interval=0.02)
            time.sleep(0.3)
            pyautogui.press('enter')
            time.sleep(0.1)

            # Click the item (twice to equip)
            pyautogui.moveTo(1020, 350, duration=0.05)
            pyautogui.click()
            time.sleep(0.05)
            pyautogui.click()
            time.sleep(0.1)

            # Press escape to exit
            pyautogui.press('escape')
            time.sleep(1)

            # Click final position
            pyautogui.moveTo(200, 69, duration=0.05)
            pyautogui.click()

            return True

        except Exception as e:
            logger.error(f"Error in automation: {e}")
            return False

    def on_refresh(self, event):
        """Handle refresh button"""
        result = messageBox(
            "This will download fresh cosmetic data from Fortnite-API.com. Continue?",
            "Refresh Locker Data",
            wx.YES_NO | wx.ICON_QUESTION,
            self
        )

        if result == wx.YES:
            try:
                from lib.utilities.epic_auth import get_or_create_cosmetics_cache

                speaker.speak("Refreshing cosmetics data")
                logger.info("Fetching fresh cosmetics data...")

                fresh_data = get_or_create_cosmetics_cache(force_refresh=True)

                if fresh_data:
                    self.cosmetics_data = fresh_data
                    self.filtered_cosmetics = fresh_data.copy()
                    self.stats = self._calculate_stats()
                    self.update_list()

                    speaker.speak(f"Refreshed. {len(fresh_data)} cosmetics loaded.")
                    messageBox(
                        f"Successfully refreshed cosmetics data.\nLoaded {len(fresh_data)} items.",
                        "Refresh Complete",
                        wx.OK | wx.ICON_INFORMATION,
                        self
                    )
                else:
                    speaker.speak("Failed to refresh data")
                    messageBox(
                        "Failed to fetch fresh cosmetics data. Please check your internet connection.",
                        "Refresh Failed",
                        wx.OK | wx.ICON_ERROR,
                        self
                    )

            except Exception as e:
                logger.error(f"Error refreshing data: {e}")
                speaker.speak("Error refreshing data")
                messageBox(
                    f"Error refreshing data: {e}",
                    "Error",
                    wx.OK | wx.ICON_ERROR,
                    self
                )

    def on_export(self, event):
        """Handle export button"""
        dlg = wx.FileDialog(
            self,
            "Export Cosmetics List",
            defaultFile="fortnite_cosmetics.txt",
            wildcard="Text files (*.txt)|*.txt|CSV files (*.csv)|*.csv|JSON files (*.json)|*.json",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        )

        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            try:
                if path.endswith(".json"):
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump(self.filtered_cosmetics, f, indent=2)
                elif path.endswith(".csv"):
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write("Name,Type,Rarity,Season\n")
                        for cosmetic in self.filtered_cosmetics:
                            name = cosmetic.get('name', 'Unknown')
                            cosmetic_type = cosmetic.get('type', '')
                            type_info = COSMETIC_TYPE_MAP.get(cosmetic_type, {})
                            friendly_type = type_info.get('name', 'Unknown')
                            rarity = cosmetic.get('rarity', 'common')
                            season = f"C{cosmetic.get('introduction_chapter', '?')}S{cosmetic.get('introduction_season', '?')}"
                            f.write(f'"{name}",{friendly_type},{rarity},{season}\n')
                else:
                    with open(path, 'w', encoding='utf-8') as f:
                        for cosmetic in self.filtered_cosmetics:
                            name = cosmetic.get('name', 'Unknown')
                            cosmetic_type = cosmetic.get('type', '')
                            type_info = COSMETIC_TYPE_MAP.get(cosmetic_type, {})
                            friendly_type = type_info.get('name', 'Unknown')
                            rarity = cosmetic.get('rarity', 'common')
                            f.write(f"{name} - {friendly_type} ({rarity})\n")

                speaker.speak(f"Exported {len(self.filtered_cosmetics)} cosmetics")
                messageBox(f"Exported {len(self.filtered_cosmetics)} cosmetics to {path}", "Export Successful", wx.OK | wx.ICON_INFORMATION, self)
            except Exception as e:
                logger.error(f"Export failed: {e}")
                messageBox(f"Export failed: {e}", "Export Error", wx.OK | wx.ICON_ERROR, self)

        dlg.Destroy()

    def on_close(self, event):
        """Handle close button"""
        self.EndModal(wx.ID_CLOSE)

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
                # Login successful, enable owned checkbox
                self.owned_checkbox.Enable(True)
                self.login_btn.SetLabel("Logged In")
                self.login_btn.Enable(False)

                # Update header to show username
                speaker.speak(f"Logged in as {self.auth.display_name}")

                # Ask if they want to show owned only
                result = messageBox(
                    "Would you like to view only your owned cosmetics?",
                    "View Owned Cosmetics",
                    wx.YES_NO | wx.ICON_QUESTION,
                    self
                )

                if result == wx.YES:
                    self.owned_checkbox.SetValue(True)
                    self.on_owned_toggle(None)

        except Exception as e:
            logger.error(f"Error during login: {e}")
            speaker.speak("Error during login")
            messageBox(f"Error: {e}", "Login Error", wx.OK | wx.ICON_ERROR, self)

    def on_owned_toggle(self, event):
        """Handle owned cosmetics checkbox toggle"""
        try:
            if not self.auth or not self.auth.display_name:
                speaker.speak("Please log in first")
                self.owned_checkbox.SetValue(False)
                return

            self.owned_only = self.owned_checkbox.GetValue()

            if self.owned_only:
                speaker.speak("Filtering to owned cosmetics")
                logger.info("Filtering to owned cosmetics")

                # Fetch list of owned IDs if not already fetched
                if not self.owned_ids:
                    fetched_ids = self.auth.fetch_owned_cosmetics()
                    if fetched_ids:
                        # Convert to set of lowercase IDs for fast lookup
                        self.owned_ids = set(id.lower() for id in fetched_ids)
                        logger.info(f"Fetched {len(self.owned_ids)} owned cosmetic IDs")
                    else:
                        speaker.speak("Failed to fetch owned cosmetics list")
                        messageBox(
                            "Failed to fetch your owned cosmetics from Epic Games. Please check your connection and try again.",
                            "Error",
                            wx.OK | wx.ICON_ERROR,
                            self
                        )
                        self.owned_checkbox.SetValue(False)
                        return

                # Update list - filter_cosmetics() will now use owned_ids
                self.update_list()

                # Count how many owned cosmetics matched
                owned_count = len(self.filtered_cosmetics)
                speaker.speak(f"Showing {owned_count} owned cosmetics")
                logger.info(f"Filtered to {owned_count} owned cosmetics")
            else:
                speaker.speak("Showing all cosmetics")
                logger.info("Showing all cosmetics")

                # Update list - filter_cosmetics() will ignore owned filter
                self.update_list()

                speaker.speak(f"Showing all {len(self.filtered_cosmetics)} cosmetics")

        except Exception as e:
            logger.error(f"Error toggling owned mode: {e}")
            speaker.speak("Error filtering cosmetics")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)
            self.owned_checkbox.SetValue(not self.owned_only)


def launch_locker_gui():
    """Launch the unified locker GUI"""
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

        # Create and show dialog with auth instance
        dlg = LockerGUI(None, cosmetics_data, auth_instance=auth_instance, owned_only=False)

        try:
            ensure_window_focus_and_center_mouse(dlg)
            speaker.speak(f"Fortnite Locker. {len(cosmetics_data)} cosmetics loaded.")
            result = dlg.ShowModal()
            return result

        finally:
            if dlg:
                dlg.Destroy()
            if app:
                app.ProcessPendingEvents()
                while app.HasPendingEvents():
                    app.Yield()

    except Exception as e:
        logger.error(f"Error launching locker: {e}")
        speaker.speak("Error opening locker")
        messageBox(f"Failed to launch locker: {e}", "Error", wx.OK | wx.ICON_ERROR)
        return None

    finally:
        try:
            gc.collect()
            try:
                ctypes.windll.user32.SetFocus(0)
                if ctypes.windll.user32.OpenClipboard(0):
                    ctypes.windll.user32.EmptyClipboard()
                    ctypes.windll.user32.CloseClipboard()
            except Exception:
                pass
            time.sleep(0.05)
            gc.collect()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


# Alias for backward compatibility
launch_locker_viewer = launch_locker_gui
launch_locker_selector = launch_locker_gui
