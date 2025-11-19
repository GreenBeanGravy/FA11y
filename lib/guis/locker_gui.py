<<<<<<< HEAD
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
        self.category_cosmetics = self._filter_by_category()
        self.filtered_cosmetics = self.category_cosmetics.copy()

        # Search state
        self.current_search = ""

        # Category-specific settings
        self.show_random = self._should_show_random()
        self.unequip_search_term = self._get_unequip_search_term()

        self.setupDialog()
        self.SetSize((900, 700))
        self.CentreOnScreen()

    def _should_show_random(self) -> bool:
        """Check if Random option should be shown for this category"""
        # Emotes don't have random option
        return self.category_name != "Emote"

    def _get_unequip_search_term(self) -> str:
        """Get the search term for unequipping based on category"""
        if self.category_name in ["Outfit", "Pickaxe"]:
            return "Default"
        elif self.category_name == "Glider":
            return "Glider"
        else:
            return "Empty"

    def _filter_by_category(self) -> List[dict]:
        """Filter cosmetics to this category only"""
        filtered = []

        for cosmetic in self.cosmetics_data:
            # Owned filter
            if self.owned_only:
                cosmetic_id = cosmetic.get("id", "").lower()
                if cosmetic_id not in self.owned_ids:
                    continue

            # Category filter
            cosmetic_type = cosmetic.get("type", "")
            type_info = COSMETIC_TYPE_MAP.get(cosmetic_type, {})
            friendly_type = type_info.get("name", cosmetic_type)

            if friendly_type == self.category_name:
                filtered.append(cosmetic)

        # Sort by rarity (highest first) by default
        filtered = sorted(filtered, key=lambda x: (-x.get("rarity_value", 0), x.get("name", "")))

        return filtered

    def makeSettings(self, sizer: BoxSizerHelper):
        """Create category view content"""

        # Results count
        self.results_label = wx.StaticText(self, label="")
        sizer.addItem(self.results_label)

        # Search box
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_label = wx.StaticText(self, label="Search:")
        search_sizer.Add(search_label, flag=wx.ALIGN_CENTER_VERTICAL)
        search_sizer.AddSpacer(10)

        self.search_box = wx.TextCtrl(self, size=(400, -1))
        self.search_box.Bind(wx.EVT_TEXT, self.on_search_changed)
        search_sizer.Add(self.search_box, flag=wx.ALIGN_CENTER_VERTICAL)

        search_sizer.AddSpacer(10)
        clear_btn = wx.Button(self, label="Clear")
        clear_btn.Bind(wx.EVT_BUTTON, lambda e: self.search_box.SetValue(""))
        search_sizer.Add(clear_btn, flag=wx.ALIGN_CENTER_VERTICAL)

        sizer.addItem(search_sizer)

        # Cosmetics list
        self.cosmetics_list = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_VRULES
        )

        # Setup columns
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

        self.equip_btn = wx.Button(self, label="&Equip Selected")
        self.equip_btn.Bind(wx.EVT_BUTTON, self.on_equip_clicked)
        button_sizer.Add(self.equip_btn)

        button_sizer.AddSpacer(10)

        self.back_btn = wx.Button(self, label="&Back to Categories")
        self.back_btn.Bind(wx.EVT_BUTTON, self.on_back)
        button_sizer.Add(self.back_btn)

        button_sizer.AddStretchSpacer()

        self.close_btn = wx.Button(self, label="&Close")
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

        event.Skip()

    def on_search_changed(self, event):
        """Handle search text changes"""
        self.current_search = self.search_box.GetValue()
        self.update_list()

    def filter_cosmetics(self) -> List[dict]:
        """Filter cosmetics based on search"""
        if not self.current_search:
            return self.category_cosmetics.copy()

        filtered = []
        search_lower = self.current_search.lower()

        for cosmetic in self.category_cosmetics:
            name = cosmetic.get("name", "").lower()
            description = cosmetic.get("description", "").lower()
            rarity = cosmetic.get("rarity", "").lower()

            if search_lower in name or search_lower in description or search_lower in rarity:
                filtered.append(cosmetic)

        return filtered

    def update_list(self):
        """Update the cosmetics list"""
        self.filtered_cosmetics = self.filter_cosmetics()

        # Update results label
        count = len(self.filtered_cosmetics)
        if self.current_search:
            self.results_label.SetLabel(f"Showing {count} {self.category_name} cosmetics matching '{self.current_search}'")
        else:
            self.results_label.SetLabel(f"Showing {count} {self.category_name} cosmetics")

        # Clear and populate list
        self.cosmetics_list.Freeze()
        try:
            self.cosmetics_list.DeleteAllItems()

            list_offset = 0

            # Add Random option at top (if applicable for this category)
            if self.show_random:
                idx = self.cosmetics_list.InsertItem(list_offset, "🔄 Random")
                self.cosmetics_list.SetItem(idx, 1, "Special")
                self.cosmetics_list.SetItem(idx, 2, "-")
                self.cosmetics_list.SetItemData(idx, -1)  # Special marker
                self.cosmetics_list.SetItemTextColour(idx, wx.Colour(0, 217, 217))
                list_offset += 1

            # Add Unequip option (with category-specific label)
            unequip_label = f"❌ Unequip ({self.unequip_search_term})"
            idx = self.cosmetics_list.InsertItem(list_offset, unequip_label)
            self.cosmetics_list.SetItem(idx, 1, "Special")
            self.cosmetics_list.SetItem(idx, 2, "-")
            self.cosmetics_list.SetItemData(idx, -2)  # Special marker
            self.cosmetics_list.SetItemTextColour(idx, wx.Colour(255, 100, 100))
            list_offset += 1

            # Add regular cosmetics
            for cosmetic_idx, cosmetic in enumerate(self.filtered_cosmetics):
                name = cosmetic.get("name", "Unknown")
                if cosmetic.get("favorite", False):
                    name = "⭐ " + name

                # Format rarity with series suffix
                rarity_raw = cosmetic.get("rarity", "common").lower()
                special_rarities = ["marvel", "dc", "starwars", "icon", "gaminglegends"]
                if rarity_raw in special_rarities:
                    rarity = f"{rarity_raw.title()} series"
                else:
                    rarity = rarity_raw.title()

                season = f"C{cosmetic.get('introduction_chapter', '?')}S{cosmetic.get('introduction_season', '?')}"

                list_idx = self.cosmetics_list.InsertItem(cosmetic_idx + list_offset, name)
                self.cosmetics_list.SetItem(list_idx, 1, rarity)
                self.cosmetics_list.SetItem(list_idx, 2, season)
                self.cosmetics_list.SetItemData(list_idx, cosmetic_idx)

                # Color code
                color = self.get_rarity_color(rarity_raw)
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

    def on_item_selected(self, event):
        """Handle item selection"""
        index = event.GetIndex()
        cosmetic_idx = self.cosmetics_list.GetItemData(index)

        if cosmetic_idx == -1:  # Random
            self.details_text.SetValue("Random\n\nEquip a random cosmetic for this category.")
        elif cosmetic_idx == -2:  # Unequip
            self.details_text.SetValue(f"Unequip\n\nSearches for '{self.unequip_search_term}' to remove the cosmetic from this slot.")
        elif 0 <= cosmetic_idx < len(self.filtered_cosmetics):
            cosmetic = self.filtered_cosmetics[cosmetic_idx]
            self.show_cosmetic_details(cosmetic)

    def show_cosmetic_details(self, cosmetic: dict):
        """Show cosmetic details"""
        details = []
        details.append(f"Name: {cosmetic.get('name', 'Unknown')}")

        cosmetic_type = cosmetic.get("type", "Unknown")
        type_info = COSMETIC_TYPE_MAP.get(cosmetic_type, {})
        friendly_type = type_info.get("name", cosmetic_type)
        details.append(f"Type: {friendly_type}")

        # Format rarity with series suffix
        rarity_raw = cosmetic.get("rarity", "common").lower()
        special_rarities = ["marvel", "dc", "starwars", "icon", "gaminglegends"]
        if rarity_raw in special_rarities:
            rarity_display = f"{rarity_raw.title()} series"
        else:
            rarity_display = rarity_raw.title()
        details.append(f"Rarity: {rarity_display}")
        details.append(f"Season: Chapter {cosmetic.get('introduction_chapter', '?')}, Season {cosmetic.get('introduction_season', '?')}")

        if cosmetic.get("description"):
            details.append(f"\nDescription: {cosmetic['description']}")

        if cosmetic.get("favorite"):
            details.append("\n⭐ FAVORITE")

        self.details_text.SetValue("\n".join(details))

    def on_item_activated(self, event):
        """Handle double-click"""
        self.on_equip_clicked(None)

    def on_equip_clicked(self, event):
        """Handle Equip button"""
        index = self.cosmetics_list.GetFirstSelected()
        if index == -1:
            speaker.speak("No item selected")
            messageBox("Please select an item to equip", "No Selection", wx.OK | wx.ICON_WARNING, self)
            return

        cosmetic_idx = self.cosmetics_list.GetItemData(index)

        if cosmetic_idx == -1:  # Random
            self.equip_special("Rando")
        elif cosmetic_idx == -2:  # Unequip
            self.equip_special(self.unequip_search_term)
        elif 0 <= cosmetic_idx < len(self.filtered_cosmetics):
            cosmetic = self.filtered_cosmetics[cosmetic_idx]
            self.equip_cosmetic(cosmetic)

    def equip_special(self, search_term: str):
        """Equip Random or Unequip by searching"""
        # Create a fake cosmetic entry for the search term
        fake_cosmetic = {
            "name": search_term,
            "type": self._get_type_from_category(),
            "rarity": "common",
            "description": ""
        }
        self.equip_cosmetic(fake_cosmetic)

    def _get_type_from_category(self) -> str:
        """Get backend type from category name"""
        for backend_type, info in COSMETIC_TYPE_MAP.items():
            if info["name"] == self.category_name:
                return backend_type
        return "Unknown"

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

            # For items with multiple slots, ask user
            if slot is None:
                slot = self.ask_for_slot(cosmetic_type, name)
                if slot is None:
                    return

            speaker.speak(f"Equipping {name}")
            logger.info(f"Equipping {name} to {category} slot {slot}")

            # Minimize dialog
            self.Iconize(True)
            time.sleep(0.1)

            try:
                success = self.perform_equip_automation(category, slot, name)
                wx.CallLater(100, self._show_after_equip, success, name)
            except Exception as automation_error:
                logger.error(f"Error during automation: {automation_error}")
                wx.CallAfter(self._show_after_equip, False, name)
                raise

        except Exception as e:
            logger.error(f"Error equipping cosmetic: {e}")
            speaker.speak("Error equipping cosmetic")
            if not self.IsShown():
                wx.CallAfter(self.Show)
            wx.CallAfter(lambda: messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self))

    def _show_after_equip(self, success: bool, name: str):
        """Show dialog after equip"""
        try:
            time.sleep(0.2)
            self.Iconize(False)
            self.Raise()
            self.SetFocus()

            if success:
                speaker.speak(f"{name} equipped!")
            else:
                speaker.speak("Equip failed")
                wx.CallAfter(lambda: messageBox("Failed to equip cosmetic. Make sure Fortnite is open and in the locker.", "Equip Failed", wx.OK | wx.ICON_ERROR, self))
        except Exception as e:
            logger.error(f"Error showing dialog after equip: {e}")

    def ask_for_slot(self, cosmetic_type: str, name: str) -> Optional[int]:
        """Ask user which slot to equip to"""
        if cosmetic_type == "AthenaDance":
            dlg = wx.SingleChoiceDialog(
                self,
                f"Select which emote slot to equip '{name}' to:",
                "Select Emote Slot",
                ["Emote 1", "Emote 2", "Emote 3", "Emote 4", "Emote 5", "Emote 6"]
            )
        elif cosmetic_type == "AthenaItemWrap":
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
        """Perform UI automation to equip"""
        try:
            slot_coords = SLOT_COORDS.get(slot)
            if not slot_coords:
                logger.error(f"Unknown slot number: {slot}")
                return False

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

            # Type item name
            pyautogui.write(item_name, interval=0.02)
            time.sleep(0.3)
            pyautogui.press('enter')
            time.sleep(0.1)

            # Click item twice to equip
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

    def on_back(self, event):
        """Handle Back button"""
        self.EndModal(wx.ID_CANCEL)

    def on_close(self, event):
        """Handle Close button"""
        self.EndModal(wx.ID_CLOSE)


class LockerGUI(AccessibleDialog):
    """Main Locker GUI - Category Selection Menu"""

    def __init__(self, parent, cosmetics_data: List[dict], auth_instance=None, owned_only: bool = False):
        super().__init__(parent, title="Fortnite Locker", helpId="LockerGUI")
        self.cosmetics_data = cosmetics_data
        self.auth = auth_instance
        self.owned_only = owned_only
        self.owned_ids = set()

        # Check auth and fetch owned IDs on startup if logged in
        if self.auth and self.auth.display_name:
            wx.CallAfter(self._check_auth_on_startup)

        self.setupDialog()
        self.SetSize((600, 700))
        self.CentreOnScreen()

    def _calculate_stats(self) -> Dict[str, int]:
        """Calculate statistics about cosmetics"""
        stats = {
            "total": len(self.cosmetics_data),
            "favorites": sum(1 for c in self.cosmetics_data if c.get("favorite", False))
        }
        return stats

    def _check_auth_on_startup(self):
        """Check auth token validity and fetch owned cosmetics on startup"""
        try:
            logger.info("Checking auth token and fetching owned cosmetics...")
            fetched_ids = self.auth.fetch_owned_cosmetics()

            # Check for auth expiration
            if fetched_ids == "AUTH_EXPIRED":
                logger.info("Auth token expired on startup")
                # Don't prompt immediately, just disable owned checkbox
                return
            elif fetched_ids:
                # Convert to set of lowercase IDs for fast lookup
                self.owned_ids = set(id.lower() for id in fetched_ids)
                logger.info(f"Fetched {len(self.owned_ids)} owned cosmetic IDs on startup")

                # Create a set of existing cosmetic IDs
                existing_ids = {c.get("id", "").lower() for c in self.cosmetics_data}

                # Find owned IDs not in the database
                missing_ids = self.owned_ids - existing_ids

                if missing_ids:
                    logger.info(f"Found {len(missing_ids)} owned items not in database, creating placeholders")

                    # Create placeholder entries for missing owned items
                    for missing_id in missing_ids:
                        placeholder = {
                            "id": missing_id,
                            "name": f"[Unknown Item] {missing_id[:20]}",
                            "description": "This item is owned but not in the Fortnite-API database",
                            "type": "Unknown",
                            "rarity": "common",
                            "rarity_value": 0,
                            "introduction_chapter": "?",
                            "introduction_season": "?",
                            "image_url": "",
                            "favorite": False
                        }
                        self.cosmetics_data.append(placeholder)

                    logger.info(f"Added {len(missing_ids)} placeholder entries")

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

            self.login_btn = wx.Button(self, label="Logged In", size=(120, -1))
            self.login_btn.Enable(False)
        else:
            status_label = wx.StaticText(self, label="Not logged in")
            login_sizer.Add(status_label, flag=wx.ALIGN_CENTER_VERTICAL)
            login_sizer.AddSpacer(10)

            self.login_btn = wx.Button(self, label="&Login", size=(120, -1))
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

        # Category list in coordinate order
        categories = ["Outfit", "Back Bling", "Pickaxe", "Glider", "Kicks", "Contrail",
                     "Emote", "Pet", "Wrap", "Loading Screen", "Music", "Car Body"]

        for category in categories:
            btn = wx.Button(self, label=category, size=(200, 40))
            btn.Bind(wx.EVT_BUTTON, lambda evt, cat=category: self.on_category_selected(cat))
            sizer.addItem(btn)

        # Bottom buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.refresh_btn = wx.Button(self, label="&Refresh Data")
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        button_sizer.Add(self.refresh_btn)

        button_sizer.AddStretchSpacer()

        self.close_btn = wx.Button(self, label="&Close")
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        button_sizer.Add(self.close_btn)

        sizer.addItem(button_sizer, flag=wx.EXPAND)

        # Bind key events
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)

    def onKeyEvent(self, event):
        """Handle key events"""
        key_code = event.GetKeyCode()

        if key_code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return

        event.Skip()

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
            result = dlg.ShowModal()
            dlg.Destroy()

            # Restore main menu focus
            ensure_window_focus_and_center_mouse(self)

        except Exception as e:
            logger.error(f"Error opening category view: {e}")
            speaker.speak("Error opening category")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)

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

            self.owned_only = self.owned_btn.GetValue()

            if self.owned_only:
                speaker.speak("Enabled: Show only owned cosmetics")
                logger.info("Filtering to owned cosmetics")

                # Fetch list of owned IDs if not already fetched
                if not self.owned_ids:
                    speaker.speak("Fetching owned cosmetics")
                    fetched_ids = self.auth.fetch_owned_cosmetics()

                    # Check for auth expiration
                    if fetched_ids == "AUTH_EXPIRED":
                        speaker.speak("Your login has expired. Please log in again.")
                        result = messageBox(
                            "Your Epic Games login has expired.\n\nWould you like to log in again?",
                            "Login Expired",
                            wx.YES_NO | wx.ICON_WARNING,
                            self
                        )

                        if result == wx.YES:
                            # Reset auth state
                            self.owned_btn.SetValue(False)
                            self.owned_btn.Enable(False)
                            self.login_btn.SetLabel("&Login")
                            self.login_btn.Enable(True)
                            # Trigger login
                            wx.CallAfter(self.on_login, None)
                        else:
                            self.owned_btn.SetValue(False)
                        return
                    elif fetched_ids:
                        # Convert to set of lowercase IDs for fast lookup
                        self.owned_ids = set(id.lower() for id in fetched_ids)
                        logger.info(f"Fetched {len(self.owned_ids)} owned cosmetic IDs")
                        speaker.speak(f"Found {len(self.owned_ids)} owned cosmetics")

                        # Create placeholders for owned items not in database
                        existing_ids = {c.get("id", "").lower() for c in self.cosmetics_data}
                        missing_ids = self.owned_ids - existing_ids

                        if missing_ids:
                            logger.info(f"Creating {len(missing_ids)} placeholders for unknown owned items")
                            for missing_id in missing_ids:
                                placeholder = {
                                    "id": missing_id,
                                    "name": f"[Unknown Item] {missing_id[:20]}",
                                    "description": "This item is owned but not in the Fortnite-API database",
                                    "type": "Unknown",
                                    "rarity": "common",
                                    "rarity_value": 0,
                                    "introduction_chapter": "?",
                                    "introduction_season": "?",
                                    "image_url": "",
                                    "favorite": False
                                }
                                self.cosmetics_data.append(placeholder)
                    else:
                        speaker.speak("Failed to fetch owned cosmetics list")
                        messageBox(
                            "Failed to fetch your owned cosmetics from Epic Games. Please check your connection and try again.",
                            "Error",
                            wx.OK | wx.ICON_ERROR,
                            self
                        )
                        self.owned_btn.SetValue(False)
                        return
            else:
                speaker.speak("Disabled: Showing all cosmetics")
                logger.info("Showing all cosmetics")

        except Exception as e:
            logger.error(f"Error toggling owned mode: {e}")
            speaker.speak("Error toggling owned filter")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)
            self.owned_btn.SetValue(not self.owned_only)


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

        # Default to owned cosmetics if authenticated
        default_owned_only = bool(auth_instance and auth_instance.display_name)
        if default_owned_only:
            logger.info(f"User authenticated as {auth_instance.display_name}, defaulting to owned cosmetics")

        # Create and show dialog with auth instance
        dlg = LockerGUI(None, cosmetics_data, auth_instance=auth_instance, owned_only=default_owned_only)

        try:
            ensure_window_focus_and_center_mouse(dlg)
            if default_owned_only:
                speaker.speak(f"Fortnite Locker. Logged in as {auth_instance.display_name}. Loading owned cosmetics.")
            else:
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
=======
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
        self.category_cosmetics = self._filter_by_category()
        self.filtered_cosmetics = self.category_cosmetics.copy()

        # Search state
        self.current_search = ""

        # Category-specific settings
        self.show_random = self._should_show_random()
        self.unequip_search_term = self._get_unequip_search_term()

        self.setupDialog()
        self.SetSize((900, 700))
        self.CentreOnScreen()

    def _should_show_random(self) -> bool:
        """Check if Random option should be shown for this category"""
        # Emotes don't have random option
        return self.category_name != "Emote"

    def _get_unequip_search_term(self) -> str:
        """Get the search term for unequipping based on category"""
        if self.category_name in ["Outfit", "Pickaxe"]:
            return "Default"
        elif self.category_name == "Glider":
            return "Glider"
        else:
            return "Empty"

    def _filter_by_category(self) -> List[dict]:
        """Filter cosmetics to this category only"""
        filtered = []

        for cosmetic in self.cosmetics_data:
            # Owned filter
            if self.owned_only:
                cosmetic_id = cosmetic.get("id", "").lower()
                if cosmetic_id not in self.owned_ids:
                    continue

            # Category filter
            cosmetic_type = cosmetic.get("type", "")
            type_info = COSMETIC_TYPE_MAP.get(cosmetic_type, {})
            friendly_type = type_info.get("name", cosmetic_type)

            if friendly_type == self.category_name:
                filtered.append(cosmetic)

        # Sort by rarity (highest first) by default
        filtered = sorted(filtered, key=lambda x: (-x.get("rarity_value", 0), x.get("name", "")))

        return filtered

    def makeSettings(self, sizer: BoxSizerHelper):
        """Create category view content"""

        # Results count
        self.results_label = wx.StaticText(self, label="")
        sizer.addItem(self.results_label)

        # Search box
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_label = wx.StaticText(self, label="Search:")
        search_sizer.Add(search_label, flag=wx.ALIGN_CENTER_VERTICAL)
        search_sizer.AddSpacer(10)

        self.search_box = wx.TextCtrl(self, size=(400, -1))
        self.search_box.Bind(wx.EVT_TEXT, self.on_search_changed)
        search_sizer.Add(self.search_box, flag=wx.ALIGN_CENTER_VERTICAL)

        search_sizer.AddSpacer(10)
        clear_btn = wx.Button(self, label="Clear")
        clear_btn.Bind(wx.EVT_BUTTON, lambda e: self.search_box.SetValue(""))
        search_sizer.Add(clear_btn, flag=wx.ALIGN_CENTER_VERTICAL)

        sizer.addItem(search_sizer)

        # Cosmetics list
        self.cosmetics_list = wx.ListCtrl(
            self,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_VRULES
        )

        # Setup columns
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

        self.equip_btn = wx.Button(self, label="&Equip Selected")
        self.equip_btn.Bind(wx.EVT_BUTTON, self.on_equip_clicked)
        button_sizer.Add(self.equip_btn)

        button_sizer.AddSpacer(10)

        self.back_btn = wx.Button(self, label="&Back to Categories")
        self.back_btn.Bind(wx.EVT_BUTTON, self.on_back)
        button_sizer.Add(self.back_btn)

        button_sizer.AddStretchSpacer()

        self.close_btn = wx.Button(self, label="&Close")
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

        event.Skip()

    def on_search_changed(self, event):
        """Handle search text changes"""
        self.current_search = self.search_box.GetValue()
        self.update_list()

    def filter_cosmetics(self) -> List[dict]:
        """Filter cosmetics based on search"""
        if not self.current_search:
            return self.category_cosmetics.copy()

        filtered = []
        search_lower = self.current_search.lower()

        for cosmetic in self.category_cosmetics:
            name = cosmetic.get("name", "").lower()
            description = cosmetic.get("description", "").lower()
            rarity = cosmetic.get("rarity", "").lower()

            if search_lower in name or search_lower in description or search_lower in rarity:
                filtered.append(cosmetic)

        return filtered

    def update_list(self):
        """Update the cosmetics list"""
        self.filtered_cosmetics = self.filter_cosmetics()

        # Update results label
        count = len(self.filtered_cosmetics)
        if self.current_search:
            self.results_label.SetLabel(f"Showing {count} {self.category_name} cosmetics matching '{self.current_search}'")
        else:
            self.results_label.SetLabel(f"Showing {count} {self.category_name} cosmetics")

        # Clear and populate list
        self.cosmetics_list.Freeze()
        try:
            self.cosmetics_list.DeleteAllItems()

            list_offset = 0

            # Add Random option at top (if applicable for this category)
            if self.show_random:
                idx = self.cosmetics_list.InsertItem(list_offset, "🔄 Random")
                self.cosmetics_list.SetItem(idx, 1, "Special")
                self.cosmetics_list.SetItem(idx, 2, "-")
                self.cosmetics_list.SetItemData(idx, -1)  # Special marker
                self.cosmetics_list.SetItemTextColour(idx, wx.Colour(0, 217, 217))
                list_offset += 1

            # Add Unequip option (with category-specific label)
            unequip_label = f"❌ Unequip ({self.unequip_search_term})"
            idx = self.cosmetics_list.InsertItem(list_offset, unequip_label)
            self.cosmetics_list.SetItem(idx, 1, "Special")
            self.cosmetics_list.SetItem(idx, 2, "-")
            self.cosmetics_list.SetItemData(idx, -2)  # Special marker
            self.cosmetics_list.SetItemTextColour(idx, wx.Colour(255, 100, 100))
            list_offset += 1

            # Add regular cosmetics
            for cosmetic_idx, cosmetic in enumerate(self.filtered_cosmetics):
                name = cosmetic.get("name", "Unknown")
                if cosmetic.get("favorite", False):
                    name = "⭐ " + name

                # Format rarity with series suffix
                rarity_raw = cosmetic.get("rarity", "common").lower()
                special_rarities = ["marvel", "dc", "starwars", "icon", "gaminglegends"]
                if rarity_raw in special_rarities:
                    rarity = f"{rarity_raw.title()} series"
                else:
                    rarity = rarity_raw.title()

                season = f"C{cosmetic.get('introduction_chapter', '?')}S{cosmetic.get('introduction_season', '?')}"

                list_idx = self.cosmetics_list.InsertItem(cosmetic_idx + list_offset, name)
                self.cosmetics_list.SetItem(list_idx, 1, rarity)
                self.cosmetics_list.SetItem(list_idx, 2, season)
                self.cosmetics_list.SetItemData(list_idx, cosmetic_idx)

                # Color code
                color = self.get_rarity_color(rarity_raw)
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

    def on_item_selected(self, event):
        """Handle item selection"""
        index = event.GetIndex()
        cosmetic_idx = self.cosmetics_list.GetItemData(index)

        if cosmetic_idx == -1:  # Random
            self.details_text.SetValue("Random\n\nEquip a random cosmetic for this category.")
        elif cosmetic_idx == -2:  # Unequip
            self.details_text.SetValue(f"Unequip\n\nSearches for '{self.unequip_search_term}' to remove the cosmetic from this slot.")
        elif 0 <= cosmetic_idx < len(self.filtered_cosmetics):
            cosmetic = self.filtered_cosmetics[cosmetic_idx]
            self.show_cosmetic_details(cosmetic)

    def show_cosmetic_details(self, cosmetic: dict):
        """Show cosmetic details"""
        details = []
        details.append(f"Name: {cosmetic.get('name', 'Unknown')}")

        cosmetic_type = cosmetic.get("type", "Unknown")
        type_info = COSMETIC_TYPE_MAP.get(cosmetic_type, {})
        friendly_type = type_info.get("name", cosmetic_type)
        details.append(f"Type: {friendly_type}")

        # Format rarity with series suffix
        rarity_raw = cosmetic.get("rarity", "common").lower()
        special_rarities = ["marvel", "dc", "starwars", "icon", "gaminglegends"]
        if rarity_raw in special_rarities:
            rarity_display = f"{rarity_raw.title()} series"
        else:
            rarity_display = rarity_raw.title()
        details.append(f"Rarity: {rarity_display}")
        details.append(f"Season: Chapter {cosmetic.get('introduction_chapter', '?')}, Season {cosmetic.get('introduction_season', '?')}")

        if cosmetic.get("description"):
            details.append(f"\nDescription: {cosmetic['description']}")

        if cosmetic.get("favorite"):
            details.append("\n⭐ FAVORITE")

        self.details_text.SetValue("\n".join(details))

    def on_item_activated(self, event):
        """Handle double-click"""
        self.on_equip_clicked(None)

    def on_equip_clicked(self, event):
        """Handle Equip button"""
        index = self.cosmetics_list.GetFirstSelected()
        if index == -1:
            speaker.speak("No item selected")
            messageBox("Please select an item to equip", "No Selection", wx.OK | wx.ICON_WARNING, self)
            return

        cosmetic_idx = self.cosmetics_list.GetItemData(index)

        if cosmetic_idx == -1:  # Random
            self.equip_special("Rando")
        elif cosmetic_idx == -2:  # Unequip
            self.equip_special(self.unequip_search_term)
        elif 0 <= cosmetic_idx < len(self.filtered_cosmetics):
            cosmetic = self.filtered_cosmetics[cosmetic_idx]
            self.equip_cosmetic(cosmetic)

    def equip_special(self, search_term: str):
        """Equip Random or Unequip by searching"""
        # Create a fake cosmetic entry for the search term
        fake_cosmetic = {
            "name": search_term,
            "type": self._get_type_from_category(),
            "rarity": "common",
            "description": ""
        }
        self.equip_cosmetic(fake_cosmetic)

    def _get_type_from_category(self) -> str:
        """Get backend type from category name"""
        for backend_type, info in COSMETIC_TYPE_MAP.items():
            if info["name"] == self.category_name:
                return backend_type
        return "Unknown"

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

            # For items with multiple slots, ask user
            if slot is None:
                slot = self.ask_for_slot(cosmetic_type, name)
                if slot is None:
                    return

            speaker.speak(f"Equipping {name}")
            logger.info(f"Equipping {name} to {category} slot {slot}")

            # Minimize dialog
            self.Iconize(True)
            time.sleep(0.1)

            try:
                success = self.perform_equip_automation(category, slot, name)
                wx.CallLater(100, self._show_after_equip, success, name)
            except Exception as automation_error:
                logger.error(f"Error during automation: {automation_error}")
                wx.CallAfter(self._show_after_equip, False, name)
                raise

        except Exception as e:
            logger.error(f"Error equipping cosmetic: {e}")
            speaker.speak("Error equipping cosmetic")
            if not self.IsShown():
                wx.CallAfter(self.Show)
            wx.CallAfter(lambda: messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self))

    def _show_after_equip(self, success: bool, name: str):
        """Show dialog after equip"""
        try:
            time.sleep(0.2)
            self.Iconize(False)
            self.Raise()
            self.SetFocus()

            if success:
                speaker.speak(f"{name} equipped!")
            else:
                speaker.speak("Equip failed")
                wx.CallAfter(lambda: messageBox("Failed to equip cosmetic. Make sure Fortnite is open and in the locker.", "Equip Failed", wx.OK | wx.ICON_ERROR, self))
        except Exception as e:
            logger.error(f"Error showing dialog after equip: {e}")

    def ask_for_slot(self, cosmetic_type: str, name: str) -> Optional[int]:
        """Ask user which slot to equip to"""
        if cosmetic_type == "AthenaDance":
            dlg = wx.SingleChoiceDialog(
                self,
                f"Select which emote slot to equip '{name}' to:",
                "Select Emote Slot",
                ["Emote 1", "Emote 2", "Emote 3", "Emote 4", "Emote 5", "Emote 6"]
            )
        elif cosmetic_type == "AthenaItemWrap":
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
        """Perform UI automation to equip"""
        try:
            slot_coords = SLOT_COORDS.get(slot)
            if not slot_coords:
                logger.error(f"Unknown slot number: {slot}")
                return False

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

            # Type item name
            pyautogui.write(item_name, interval=0.02)
            time.sleep(0.3)
            pyautogui.press('enter')
            time.sleep(0.1)

            # Click item twice to equip
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

    def on_back(self, event):
        """Handle Back button"""
        self.EndModal(wx.ID_CANCEL)

    def on_close(self, event):
        """Handle Close button"""
        self.EndModal(wx.ID_CLOSE)


class LockerGUI(AccessibleDialog):
    """Main Locker GUI - Category Selection Menu"""

    def __init__(self, parent, cosmetics_data: List[dict], auth_instance=None, owned_only: bool = False):
        super().__init__(parent, title="Fortnite Locker", helpId="LockerGUI")
        self.cosmetics_data = cosmetics_data
        self.auth = auth_instance
        self.owned_only = owned_only
        self.owned_ids = set()

        # Check auth and fetch owned IDs on startup if logged in
        if self.auth and self.auth.display_name:
            wx.CallAfter(self._check_auth_on_startup)

        self.setupDialog()
        self.SetSize((600, 700))
        self.CentreOnScreen()

    def _calculate_stats(self) -> Dict[str, int]:
        """Calculate statistics about cosmetics"""
        stats = {
            "total": len(self.cosmetics_data),
            "favorites": sum(1 for c in self.cosmetics_data if c.get("favorite", False))
        }
        return stats

    def _check_auth_on_startup(self):
        """Check auth token validity and fetch owned cosmetics on startup"""
        try:
            logger.info("Checking auth token and fetching owned cosmetics...")
            fetched_ids = self.auth.fetch_owned_cosmetics()

            # Check for auth expiration
            if fetched_ids == "AUTH_EXPIRED":
                logger.info("Auth token expired on startup")
                # Don't prompt immediately, just disable owned checkbox
                return
            elif fetched_ids:
                # Convert to set of lowercase IDs for fast lookup
                self.owned_ids = set(id.lower() for id in fetched_ids)
                logger.info(f"Fetched {len(self.owned_ids)} owned cosmetic IDs on startup")

                # Create a set of existing cosmetic IDs
                existing_ids = {c.get("id", "").lower() for c in self.cosmetics_data}

                # Find owned IDs not in the database
                missing_ids = self.owned_ids - existing_ids

                if missing_ids:
                    logger.info(f"Found {len(missing_ids)} owned items not in database, creating placeholders")

                    # Create placeholder entries for missing owned items
                    for missing_id in missing_ids:
                        placeholder = {
                            "id": missing_id,
                            "name": f"[Unknown Item] {missing_id[:20]}",
                            "description": "This item is owned but not in the Fortnite-API database",
                            "type": "Unknown",
                            "rarity": "common",
                            "rarity_value": 0,
                            "introduction_chapter": "?",
                            "introduction_season": "?",
                            "image_url": "",
                            "favorite": False
                        }
                        self.cosmetics_data.append(placeholder)

                    logger.info(f"Added {len(missing_ids)} placeholder entries")

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

            self.login_btn = wx.Button(self, label="Logged In", size=(120, -1))
            self.login_btn.Enable(False)
        else:
            status_label = wx.StaticText(self, label="Not logged in")
            login_sizer.Add(status_label, flag=wx.ALIGN_CENTER_VERTICAL)
            login_sizer.AddSpacer(10)

            self.login_btn = wx.Button(self, label="&Login", size=(120, -1))
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

        # Category list in coordinate order
        categories = ["Outfit", "Back Bling", "Pickaxe", "Glider", "Kicks", "Contrail",
                     "Emote", "Pet", "Wrap", "Loading Screen", "Music", "Car Body"]

        for category in categories:
            btn = wx.Button(self, label=category, size=(200, 40))
            btn.Bind(wx.EVT_BUTTON, lambda evt, cat=category: self.on_category_selected(cat))
            sizer.addItem(btn)

        # Bottom buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.refresh_btn = wx.Button(self, label="&Refresh Data")
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        button_sizer.Add(self.refresh_btn)

        button_sizer.AddStretchSpacer()

        self.close_btn = wx.Button(self, label="&Close")
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        button_sizer.Add(self.close_btn)

        sizer.addItem(button_sizer, flag=wx.EXPAND)

        # Bind key events
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)

    def onKeyEvent(self, event):
        """Handle key events"""
        key_code = event.GetKeyCode()

        if key_code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return

        event.Skip()

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
            result = dlg.ShowModal()
            dlg.Destroy()

            # Restore main menu focus
            ensure_window_focus_and_center_mouse(self)

        except Exception as e:
            logger.error(f"Error opening category view: {e}")
            speaker.speak("Error opening category")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)

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

            self.owned_only = self.owned_btn.GetValue()

            if self.owned_only:
                speaker.speak("Enabled: Show only owned cosmetics")
                logger.info("Filtering to owned cosmetics")

                # Fetch list of owned IDs if not already fetched
                if not self.owned_ids:
                    speaker.speak("Fetching owned cosmetics")
                    fetched_ids = self.auth.fetch_owned_cosmetics()

                    # Check for auth expiration
                    if fetched_ids == "AUTH_EXPIRED":
                        speaker.speak("Your login has expired. Please log in again.")
                        result = messageBox(
                            "Your Epic Games login has expired.\n\nWould you like to log in again?",
                            "Login Expired",
                            wx.YES_NO | wx.ICON_WARNING,
                            self
                        )

                        if result == wx.YES:
                            # Reset auth state
                            self.owned_btn.SetValue(False)
                            self.owned_btn.Enable(False)
                            self.login_btn.SetLabel("&Login")
                            self.login_btn.Enable(True)
                            # Trigger login
                            wx.CallAfter(self.on_login, None)
                        else:
                            self.owned_btn.SetValue(False)
                        return
                    elif fetched_ids:
                        # Convert to set of lowercase IDs for fast lookup
                        self.owned_ids = set(id.lower() for id in fetched_ids)
                        logger.info(f"Fetched {len(self.owned_ids)} owned cosmetic IDs")
                        speaker.speak(f"Found {len(self.owned_ids)} owned cosmetics")

                        # Create placeholders for owned items not in database
                        existing_ids = {c.get("id", "").lower() for c in self.cosmetics_data}
                        missing_ids = self.owned_ids - existing_ids

                        if missing_ids:
                            logger.info(f"Creating {len(missing_ids)} placeholders for unknown owned items")
                            for missing_id in missing_ids:
                                placeholder = {
                                    "id": missing_id,
                                    "name": f"[Unknown Item] {missing_id[:20]}",
                                    "description": "This item is owned but not in the Fortnite-API database",
                                    "type": "Unknown",
                                    "rarity": "common",
                                    "rarity_value": 0,
                                    "introduction_chapter": "?",
                                    "introduction_season": "?",
                                    "image_url": "",
                                    "favorite": False
                                }
                                self.cosmetics_data.append(placeholder)
                    else:
                        speaker.speak("Failed to fetch owned cosmetics list")
                        messageBox(
                            "Failed to fetch your owned cosmetics from Epic Games. Please check your connection and try again.",
                            "Error",
                            wx.OK | wx.ICON_ERROR,
                            self
                        )
                        self.owned_btn.SetValue(False)
                        return
            else:
                speaker.speak("Disabled: Showing all cosmetics")
                logger.info("Showing all cosmetics")

        except Exception as e:
            logger.error(f"Error toggling owned mode: {e}")
            speaker.speak("Error toggling owned filter")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)
            self.owned_btn.SetValue(not self.owned_only)


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

        # Default to owned cosmetics if authenticated
        default_owned_only = bool(auth_instance and auth_instance.display_name)
        if default_owned_only:
            logger.info(f"User authenticated as {auth_instance.display_name}, defaulting to owned cosmetics")

        # Create and show dialog with auth instance
        dlg = LockerGUI(None, cosmetics_data, auth_instance=auth_instance, owned_only=default_owned_only)

        try:
            ensure_window_focus_and_center_mouse(dlg)
            if default_owned_only:
                speaker.speak(f"Fortnite Locker. Logged in as {auth_instance.display_name}. Loading owned cosmetics.")
            else:
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
>>>>>>> 7c21c23a460e8f25bc96524c200b22c8b26c9b15
