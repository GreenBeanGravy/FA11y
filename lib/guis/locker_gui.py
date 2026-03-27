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
from accessible_output2.outputs.auto import Auto
import pyautogui
from lib.utilities.mouse import (
    move_to, move_to_and_click, click_mouse, mouse_scroll,
    get_mouse_position
)

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
    # Character cosmetics
    "AthenaCharacter": {"name": "Outfit", "category": "Character", "slot": 1},
    "AthenaBackpack": {"name": "Back Bling", "category": "Character", "slot": 2},
    "AthenaPickaxe": {"name": "Pickaxe", "category": "Character", "slot": 3},
    "AthenaGlider": {"name": "Glider", "category": "Character", "slot": 4},
    "CosmeticShoes": {"name": "Kicks", "category": "Character", "slot": 5},  # Fixed: was AthenaShoes
    "AthenaSkyDiveContrail": {"name": "Contrail", "category": "Character", "slot": 6},
    "SparksAura": {"name": "Aura", "category": "Character", "slot": None},  # New

    # Emotes and expressions
    "AthenaDance": {"name": "Emote", "category": "Emotes", "slot": None},  # Multiple slots
    "AthenaSpray": {"name": "Spray", "category": "Emotes", "slot": None},  # New
    "AthenaEmoji": {"name": "Emoji", "category": "Emotes", "slot": None},  # New
    "AthenaToy": {"name": "Toy", "category": "Emotes", "slot": None},  # New

    # Sidekicks/Pets (all consolidated into "Pet" category)
    "AthenaPetCarrier": {"name": "Pet", "category": "Sidekicks", "slot": 1},
    "AthenaPet": {"name": "Pet", "category": "Sidekicks", "slot": None},
    "CosmeticCompanion": {"name": "Companion", "category": "Sidekicks", "slot": None},
    "CosmeticMimosa": {"name": "Sidekick", "category": "Sidekicks", "slot": None},

    # Wraps
    "AthenaItemWrap": {"name": "Wrap", "category": "Wraps", "slot": None},  # Multiple slots

    # Lobby
    "AthenaLoadingScreen": {"name": "Loading Screen", "category": "Lobby", "slot": 3},
    "AthenaMusicPack": {"name": "Music Pack", "category": "Lobby", "slot": 2},
    "SparksSong": {"name": "Jam Track", "category": "Lobby", "slot": None},  # Multiple slots
    "SparksSong_Lobby": {"name": "Lobby Track", "category": "Lobby", "slot": 2},  # Virtual type: jam track in lobby music slot
    "BannerToken": {"name": "Banner", "category": "Lobby", "slot": None},

    # Vehicles
    "VehicleCosmetics_Body": {"name": "Car Body", "category": "Cars", "slot": 1},
    "VehicleCosmetics_Skin": {"name": "Car Skin", "category": "Cars", "slot": None},
    "VehicleCosmetics_Wheel": {"name": "Wheels", "category": "Cars", "slot": None},
    "VehicleCosmetics_Booster": {"name": "Booster", "category": "Cars", "slot": None},
    "VehicleCosmetics_DriftTrail": {"name": "Drift Trail", "category": "Cars", "slot": None},

    # Instruments (Festival)
    "SparksGuitar": {"name": "Guitar", "category": "Instruments", "slot": None},
    "SparksBass": {"name": "Bass", "category": "Instruments", "slot": None},
    "SparksDrums": {"name": "Drums", "category": "Instruments", "slot": None},
    "SparksKeyboard": {"name": "Keytar", "category": "Instruments", "slot": None},
    "SparksMicrophone": {"name": "Microphone", "category": "Instruments", "slot": None},

    # LEGO
    "JunoBuildingProp": {"name": "Decor Bundle", "category": "LEGO", "slot": None},
    "JunoBuildingSet": {"name": "Build Set", "category": "LEGO", "slot": None}
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

# Emote wheel slot coordinates (circular layout)
EMOTE_SLOT_COORDS = {
    1: (450, 390),
    2: (600, 450),
    3: (650, 590),
    4: (600, 740),
    5: (450, 800),
    6: (300, 740),
    7: (250, 600),
    8: (300, 450)
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

# Mapping from Locker Service slot templates to UI automation (category, slot)
SLOT_TEMPLATE_TO_AUTOMATION = {
    # Character
    "LoadoutSlot_Character": ("Character", 1),
    "LoadoutSlot_Backpack": ("Character", 2),
    "LoadoutSlot_Pickaxe": ("Character", 3),
    "LoadoutSlot_Glider": ("Character", 4),
    "LoadoutSlot_Shoes": ("Character", 5),
    "LoadoutSlot_Contrails": ("Character", 6),
    # Emotes
    "LoadoutSlot_Emote_0": ("Emotes", 1),
    "LoadoutSlot_Emote_1": ("Emotes", 2),
    "LoadoutSlot_Emote_2": ("Emotes", 3),
    "LoadoutSlot_Emote_3": ("Emotes", 4),
    "LoadoutSlot_Emote_4": ("Emotes", 5),
    "LoadoutSlot_Emote_5": ("Emotes", 6),
    "LoadoutSlot_Emote_6": ("Emotes", 7),
    "LoadoutSlot_Emote_7": ("Emotes", 8),
    # Wraps
    "LoadoutSlot_Wrap_0": ("Wraps", 1),
    "LoadoutSlot_Wrap_1": ("Wraps", 2),
    "LoadoutSlot_Wrap_2": ("Wraps", 3),
    "LoadoutSlot_Wrap_3": ("Wraps", 4),
    "LoadoutSlot_Wrap_4": ("Wraps", 5),
    "LoadoutSlot_Wrap_5": ("Wraps", 6),
    "LoadoutSlot_Wrap_6": ("Wraps", 7),
    # Lobby / Platform
    "LoadoutSlot_LobbyMusic": ("Lobby", 2),
    "LoadoutSlot_LoadingScreen": ("Lobby", 3),
    # Vehicles
    "LoadoutSlot_Vehicle_Body": ("Cars", 1),
    "LoadoutSlot_Vehicle_Skin": ("Cars", 2),
    "LoadoutSlot_Vehicle_Wheel": ("Cars", 3),
    "LoadoutSlot_Vehicle_DriftSmoke": ("Cars", 4),
    "LoadoutSlot_Vehicle_Booster": ("Cars", 5),
    # Instruments
    "LoadoutSlot_Guitar": ("Instruments", 1),
    "LoadoutSlot_Bass": ("Instruments", 2),
    "LoadoutSlot_Drum": ("Instruments", 3),
    "LoadoutSlot_Keyboard": ("Instruments", 4),
    "LoadoutSlot_Microphone": ("Instruments", 5),
    # Jam Tracks
    "LoadoutSlot_JamSong0": ("Lobby", None),
    "LoadoutSlot_JamSong1": ("Lobby", None),
    "LoadoutSlot_JamSong2": ("Lobby", None),
    "LoadoutSlot_JamSong3": ("Lobby", None),
    "LoadoutSlot_JamSong4": ("Lobby", None),
    "LoadoutSlot_JamSong5": ("Lobby", None),
    "LoadoutSlot_JamSong6": ("Lobby", None),
    "LoadoutSlot_JamSong7": ("Lobby", None),
}

# Friendly names for loadout schema types
LOADOUT_SCHEMA_NAMES = {
    "CosmeticLoadout:LoadoutSchema_Character": "Character",
    "CosmeticLoadout:LoadoutSchema_Emotes": "Emotes",
    "CosmeticLoadout:LoadoutSchema_Platform": "Lobby",
    "CosmeticLoadout:LoadoutSchema_Sparks": "Instruments",
    "CosmeticLoadout:LoadoutSchema_Wraps": "Wraps",
    "CosmeticLoadout:LoadoutSchema_Jam": "Jam Tracks",
    "CosmeticLoadout:LoadoutSchema_Vehicle": "Vehicle (Sedan)",
    "CosmeticLoadout:LoadoutSchema_Vehicle_SUV": "Vehicle (SUV)",
    "CosmeticLoadout:LoadoutSchema_Mimosa": "Companion",
    "CosmeticLoadout:LoadoutSchema_Moments": "Moments",
}


def focus_fortnite_window() -> bool:
    """Focus the Fortnite window before automation"""
    try:
        import win32gui
        import win32con

        def callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if "fortnite" in title.lower():
                    windows.append((hwnd, title))
            return True

        windows = []
        win32gui.EnumWindows(callback, windows)

        if windows:
            hwnd = windows[0][0]
            logger.info(f"Found Fortnite window: {windows[0][1]}")

            # Restore if minimized
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.2)

            # Bring to foreground
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.3)
            return True
        else:
            logger.warning("Fortnite window not found")
            return False
    except ImportError:
        # pywin32 not available, try alternative method
        try:
            import ctypes
            user32 = ctypes.windll.user32

            # EnumWindows callback
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))

            def callback(hwnd, lParam):
                length = user32.GetWindowTextLengthW(hwnd)
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)

                if "fortnite" in buff.value.lower() and user32.IsWindowVisible(hwnd):
                    lParam.contents = ctypes.c_int(hwnd)
                    return False
                return True

            hwnd_result = ctypes.c_int(0)
            user32.EnumWindows(EnumWindowsProc(callback), ctypes.byref(hwnd_result))

            if hwnd_result.value:
                user32.SetForegroundWindow(hwnd_result.value)
                time.sleep(0.3)
                return True
            else:
                logger.warning("Fortnite window not found (ctypes method)")
                return False
        except Exception as e:
            logger.error(f"Error focusing Fortnite window: {e}")
            return False
    except Exception as e:
        logger.error(f"Error focusing Fortnite window: {e}")
        return False


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

        # Favorite filter/sort state
        self.favorites_only = False
        self.sort_favorites_first = False

        # Category-specific settings
        self.show_random = self._should_show_random()
        self.unequip_search_term = self._get_unequip_search_term()

        self.setupDialog()
        self.SetSize((900, 700))
        self.CentreOnScreen()

    def _should_show_random(self) -> bool:
        """Check if Random option should be shown for this category"""
        # Don't show Random for All Cosmetics or Emotes
        if self.category_name in ["All Cosmetics", "Emote"]:
            return False
        return True

    def _get_unequip_search_term(self) -> str:
        """Get the search term for unequipping based on category"""
        # No unequip option for All Cosmetics
        if self.category_name == "All Cosmetics":
            return None
        elif self.category_name in ["Outfit", "Pickaxe"]:
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

            # Category filter - "All Cosmetics" shows everything
            if self.category_name == "All Cosmetics":
                filtered.append(cosmetic)
            elif self.category_name == "Lobby Track":
                # Lobby Track shows Jam Track items (SparksSong) but equips to lobby music slot
                if cosmetic.get("type", "") == "SparksSong":
                    filtered.append(cosmetic)
            else:
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
        clear_btn = wx.Button(self, label="Clear")
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
        # Start with category cosmetics
        filtered = self.category_cosmetics.copy()

        # Apply favorites filter if enabled
        if self.favorites_only:
            filtered = [c for c in filtered if c.get("favorite", False)]

        # Apply search filter if provided
        if self.current_search:
            search_lower = self.current_search.lower()
            filtered = [
                c for c in filtered
                if search_lower in c.get("name", "").lower()
                or search_lower in c.get("description", "").lower()
                or search_lower in c.get("rarity", "").lower()
            ]

        return filtered

    def update_list(self):
        """Update the cosmetics list"""
        self.filtered_cosmetics = self.filter_cosmetics()

        # Sort favorites first if enabled
        if self.sort_favorites_first:
            self.filtered_cosmetics.sort(
                key=lambda x: (
                    not x.get("favorite", False),  # Favorites first (False sorts before True)
                    -x.get("rarity_value", 0),      # Then by rarity (highest first)
                    x.get("name", "")                # Then by name
                )
            )

        # Update results label
        count = len(self.filtered_cosmetics)
        filter_desc = ""
        if self.favorites_only:
            filter_desc = " (favorites only)"
        elif self.sort_favorites_first:
            filter_desc = " (favorites first)"

        if self.current_search:
            self.results_label.SetLabel(f"Showing {count} {self.category_name} cosmetics matching '{self.current_search}'{filter_desc}")
        else:
            self.results_label.SetLabel(f"Showing {count} {self.category_name} cosmetics{filter_desc}")

        # Clear and populate list
        self.cosmetics_list.Freeze()
        try:
            self.cosmetics_list.DeleteAllItems()

            list_offset = 0

            # Add Random option at top (if applicable for this category)
            if self.show_random:
                idx = self.cosmetics_list.InsertItem(list_offset, "🔄 Random")
                if self.category_name == "All Cosmetics":
                    self.cosmetics_list.SetItem(idx, 1, "-")
                    self.cosmetics_list.SetItem(idx, 2, "Special")
                    self.cosmetics_list.SetItem(idx, 3, "-")
                else:
                    self.cosmetics_list.SetItem(idx, 1, "Special")
                    self.cosmetics_list.SetItem(idx, 2, "-")
                self.cosmetics_list.SetItemData(idx, -1)  # Special marker
                self.cosmetics_list.SetItemTextColour(idx, wx.Colour(0, 217, 217))
                list_offset += 1

            # Add Randomize Track option (picks a random cosmetic from the list)
            if self.show_random and self.category_name in ["Jam Track", "Lobby Track"]:
                idx = self.cosmetics_list.InsertItem(list_offset, "🎲 Randomize Track")
                self.cosmetics_list.SetItem(idx, 1, "Special")
                self.cosmetics_list.SetItem(idx, 2, "-")
                self.cosmetics_list.SetItemData(idx, -3)  # Special marker
                self.cosmetics_list.SetItemTextColour(idx, wx.Colour(0, 200, 100))
                list_offset += 1

            # Add Unequip option (with category-specific label, if applicable)
            if self.unequip_search_term:
                unequip_label = f"❌ Unequip ({self.unequip_search_term})"
                idx = self.cosmetics_list.InsertItem(list_offset, unequip_label)
                if self.category_name == "All Cosmetics":
                    self.cosmetics_list.SetItem(idx, 1, "-")
                    self.cosmetics_list.SetItem(idx, 2, "Special")
                    self.cosmetics_list.SetItem(idx, 3, "-")
                else:
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

                # Add Type column for All Cosmetics view
                if self.category_name == "All Cosmetics":
                    cosmetic_type = cosmetic.get("type", "")
                    type_info = COSMETIC_TYPE_MAP.get(cosmetic_type, {})
                    friendly_type = type_info.get("name", cosmetic_type)
                    self.cosmetics_list.SetItem(list_idx, 1, friendly_type)
                    self.cosmetics_list.SetItem(list_idx, 2, rarity)
                    self.cosmetics_list.SetItem(list_idx, 3, season)
                else:
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
            self.details_text.SetValue("Random\n\nEquip the Random (shuffle) option for this slot.")
        elif cosmetic_idx == -3:  # Randomize Track
            self.details_text.SetValue("Randomize Track\n\nPick a random cosmetic from this list and equip it.")
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
        cosmetic_id = cosmetic.get("id", "")
        cosmetic_type = cosmetic.get("type", "")
        name = cosmetic.get("name", "Unknown")

        if not cosmetic_id or not cosmetic_type:
            speaker.speak("Cannot favorite this item. Missing data.")
            return

        # Check if user is logged in
        if not self.auth or not self.auth.access_token:
            speaker.speak("Please log in to use favorites")
            messageBox(
                "You must be logged in to use the favorites feature.",
                "Login Required",
                wx.OK | wx.ICON_WARNING,
                self
            )
            return

        # Build template ID
        template_id = f"{cosmetic_type}:{cosmetic_id}"

        # Get current favorite status
        current_favorite = cosmetic.get("favorite", False)
        new_favorite = not current_favorite

        # Update via API
        try:
            from lib.utilities.epic_auth import get_locker_api
            locker_api = get_locker_api(self.auth)

            # Load profile if not loaded
            if not locker_api.template_id_map:
                speaker.speak("Loading profile")
                locker_api.load_profile()

            speaker.speak(f"{'Unfavoriting' if current_favorite else 'Favoriting'} {name}")
            success = locker_api.set_favorite(template_id, new_favorite)

            if success:
                # Update local data
                cosmetic["favorite"] = new_favorite

                # Also update in main cosmetics_data
                for c in self.cosmetics_data:
                    if c.get("id") == cosmetic_id:
                        c["favorite"] = new_favorite
                        break

                # Speak confirmation
                if new_favorite:
                    speaker.speak(f"{name} added to favorites")
                else:
                    speaker.speak(f"{name} removed from favorites")

                # Refresh list to show/hide star
                wx.CallAfter(self.update_list)
            else:
                speaker.speak("Failed to update favorite status")
                messageBox(
                    "Failed to update favorite status via API. Check logs for details.",
                    "Failed",
                    wx.OK | wx.ICON_ERROR,
                    self
                )

        except Exception as e:
            logger.error(f"Error toggling favorite: {e}")
            speaker.speak("Error toggling favorite")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)

    def on_equip_clicked(self, event):
        """Handle Equip button"""
        index = self.cosmetics_list.GetFirstSelected()
        if index == -1:
            speaker.speak("No item selected")
            messageBox("Please select an item to equip", "No Selection", wx.OK | wx.ICON_WARNING, self)
            return

        cosmetic_idx = self.cosmetics_list.GetItemData(index)

        if cosmetic_idx == -1:  # Random
            self.equip_special("Random")
        elif cosmetic_idx == -3:  # Randomize Track
            self.equip_random_from_list()
        elif cosmetic_idx == -2:  # Unequip
            self.equip_special(self.unequip_search_term)
        elif 0 <= cosmetic_idx < len(self.filtered_cosmetics):
            cosmetic = self.filtered_cosmetics[cosmetic_idx]
            self.equip_cosmetic(cosmetic)

    def equip_random_from_list(self):
        """Pick a random cosmetic from filtered list and equip it"""
        if not self.filtered_cosmetics:
            speaker.speak("No cosmetics available to randomize")
            messageBox("No cosmetics available to randomize.", "Cannot Randomize", wx.OK | wx.ICON_WARNING, self)
            return

        import random
        random_cosmetic = random.choice(self.filtered_cosmetics)
        speaker.speak(f"Randomly selected {random_cosmetic.get('name', 'Unknown')}")
        self.equip_cosmetic(random_cosmetic)

    def _equip_random_option(self):
        """Equip the Random (shuffle) option via UI automation by scrolling to top and clicking it"""
        try:
            # Determine category and slot from current view
            if self.category_name == "Lobby Track":
                category = "Lobby"
                slot = 2
            else:
                backend_type = self._get_type_from_category()
                type_info = COSMETIC_TYPE_MAP.get(backend_type, {})
                category = type_info.get("category")
                slot = type_info.get("slot")

                if not category:
                    speaker.speak("Cannot equip Random. Unknown category.")
                    return

                if slot is None:
                    slot = self.ask_for_slot(backend_type, "Random")
                    if slot is None:
                        return

            speaker.speak("Equipping Random")
            logger.info(f"Equipping Random to {category} slot {slot}")

            self.Iconize(True)
            time.sleep(0.1)

            try:
                success = self._perform_scroll_and_click_automation(category, slot, 1175, 385)
                wx.CallLater(100, self._show_after_equip, success, "Random")
            except Exception as automation_error:
                logger.error(f"Error during random automation: {automation_error}")
                wx.CallAfter(self._show_after_equip, False, "Random")
                raise

        except Exception as e:
            logger.error(f"Error equipping random: {e}")
            speaker.speak("Error equipping cosmetic")
            if not self.IsShown():
                wx.CallAfter(self.Show)
            wx.CallAfter(lambda: messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self))

    def _equip_unequip_option(self):
        """Unequip by scrolling to top and clicking the first item (default/none)"""
        try:
            # Determine category and slot from current view
            if self.category_name == "Lobby Track":
                category = "Lobby"
                slot = 2
            else:
                backend_type = self._get_type_from_category()
                type_info = COSMETIC_TYPE_MAP.get(backend_type, {})
                category = type_info.get("category")
                slot = type_info.get("slot")

                if not category:
                    speaker.speak("Cannot unequip. Unknown category.")
                    return

                if slot is None:
                    slot = self.ask_for_slot(backend_type, "Unequip")
                    if slot is None:
                        return

            speaker.speak("Unequipping")
            logger.info(f"Unequipping {category} slot {slot}")

            self.Iconize(True)
            time.sleep(0.1)

            try:
                success = self._perform_scroll_and_click_automation(category, slot, 1020, 350)
                wx.CallLater(100, self._show_after_equip, success, "Unequip")
            except Exception as automation_error:
                logger.error(f"Error during unequip automation: {automation_error}")
                wx.CallAfter(self._show_after_equip, False, "Unequip")
                raise

        except Exception as e:
            logger.error(f"Error unequipping: {e}")
            speaker.speak("Error unequipping cosmetic")
            if not self.IsShown():
                wx.CallAfter(self.Show)
            wx.CallAfter(lambda: messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self))

    def _perform_scroll_and_click_automation(self, category: str, slot: int, click_x: int, click_y: int) -> bool:
        """Perform UI automation by scrolling to top of the list and clicking a target position"""
        try:
            if category == "Emotes":
                slot_coords = EMOTE_SLOT_COORDS.get(slot)
            else:
                slot_coords = SLOT_COORDS.get(slot)
            if not slot_coords:
                logger.error(f"Unknown slot number: {slot}")
                return False

            if not focus_fortnite_window():
                speaker.speak("Cannot find Fortnite window. Make sure the game is running.")
                return False

            time.sleep(0.5)

            # Click locker button
            move_to_and_click(350, 69)
            time.sleep(0.3)

            # Click category
            category_coords = CATEGORY_COORDS.get(category)
            if category_coords:
                move_to_and_click(category_coords[0], category_coords[1])
                time.sleep(0.3)

                current_x, current_y = get_mouse_position()
                move_to(current_x + 500, current_y)
                time.sleep(1.0)

            # Click slot
            move_to_and_click(slot_coords[0], slot_coords[1])
            time.sleep(1.0)

            # Hover over the options area and scroll up to reach the top
            move_to(click_x, click_y)
            scroll_end = time.time() + 0.5
            while time.time() < scroll_end:
                mouse_scroll(127)  # Scroll up aggressively
                time.sleep(0.05)

            time.sleep(0.3)

            # Click the target option
            move_to_and_click(click_x, click_y)
            time.sleep(0.05)
            click_mouse('left')
            time.sleep(0.1)

            # Press escape to exit
            pyautogui.press('escape')
            time.sleep(1)

            # Click PLAY tab
            move_to_and_click(130, 69)

            return True

        except Exception as e:
            logger.error(f"Error in scroll-and-click automation: {e}")
            return False

    def equip_special(self, search_term: str):
        """Equip Random or Unequip by scrolling to top and clicking"""
        if search_term == "Random":
            self._equip_random_option()
            return
        else:
            # Unequip: scroll to top and click the first item (default/none)
            self._equip_unequip_option()

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

            # Lobby Track: jam tracks equipped to the lobby music slot
            if self.category_name == "Lobby Track":
                category = "Lobby"
                slot = 2
            elif not category:
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

    def perform_equip_automation(self, category: str, slot: int, item_name: str) -> bool:
        """Perform UI automation to equip"""
        try:
            # Use emote wheel coords for emote-category items
            if category == "Emotes":
                slot_coords = EMOTE_SLOT_COORDS.get(slot)
            else:
                slot_coords = SLOT_COORDS.get(slot)
            if not slot_coords:
                logger.error(f"Unknown slot number: {slot}")
                return False

            # Focus Fortnite window first
            if not focus_fortnite_window():
                speaker.speak("Cannot find Fortnite window. Make sure the game is running.")
                return False

            time.sleep(0.5)

            # Click locker button
            move_to_and_click(350, 69)
            time.sleep(0.3)

            # Click category
            category_coords = CATEGORY_COORDS.get(category)
            if category_coords:
                move_to_and_click(category_coords[0], category_coords[1])
                time.sleep(0.3)

                current_x, current_y = get_mouse_position()
                move_to(current_x + 500, current_y)
                time.sleep(1.0)

            # Click slot
            move_to_and_click(slot_coords[0], slot_coords[1])
            time.sleep(1.0)

            # Click search bar
            move_to_and_click(1030, 210)
            time.sleep(0.5)

            # Type item name
            pyautogui.write(item_name, interval=0.02)
            time.sleep(0.3)
            pyautogui.press('enter')
            time.sleep(0.1)

            # Click item twice to equip
            move_to_and_click(1020, 350)
            time.sleep(0.05)
            click_mouse('left')
            time.sleep(0.1)

            # Press escape to exit
            pyautogui.press('escape')
            time.sleep(1)

            # Click final position (PLAY tab)
            move_to_and_click(130, 69)

            return True

        except Exception as e:
            logger.error(f"Error in automation: {e}")
            return False

    def ask_for_slot(self, cosmetic_type: str, name: str) -> Optional[int]:
        """Ask user which slot to equip to"""
        if cosmetic_type == "AthenaDance":
            dlg = wx.SingleChoiceDialog(
                self,
                f"Select which emote slot to equip '{name}' to:",
                "Select Emote Slot",
                ["Emote 1", "Emote 2", "Emote 3", "Emote 4", "Emote 5", "Emote 6", "Emote 7", "Emote 8"]
            )
        elif cosmetic_type == "AthenaItemWrap":
            dlg = wx.SingleChoiceDialog(
                self,
                f"Select which wrap slot to equip '{name}' to:",
                "Select Wrap Slot",
                ["Rifles", "Shotguns", "Submachine Guns", "Snipers", "Pistols", "Utility", "Vehicles"]
            )
        elif cosmetic_type == "SparksSong":
            dlg = wx.SingleChoiceDialog(
                self,
                f"Select which jam track slot to equip '{name}' to:",
                "Select Jam Track Slot",
                ["Jam Track 1", "Jam Track 2", "Jam Track 3", "Jam Track 4"]
            )
        else:
            # For types without multiple slots, default to slot 1
            return 1

        if dlg.ShowModal() == wx.ID_OK:
            slot = dlg.GetSelection() + 1
            dlg.Destroy()
            return slot
        else:
            dlg.Destroy()
            return None

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

        # Create scrolled panel for categories to prevent cutoff
        self.categories_panel = wx.ScrolledWindow(self, style=wx.VSCROLL)
        self.categories_panel.SetScrollRate(0, 20)

        categories_sizer = wx.BoxSizer(wx.VERTICAL)

        # Category list (All Cosmetics first, then grouped by type)
        categories = [
            "All Cosmetics",
            # Character
            "Outfit", "Back Bling", "Pickaxe", "Glider", "Kicks", "Contrail", "Aura",
            # Emotes & Expressions
            "Emote", "Spray", "Emoji", "Toy",
            # Sidekicks/Pets
            "Pet", "Companion",
            # Wraps
            "Wrap",
            # Lobby
            "Loading Screen", "Music Pack", "Jam Track", "Lobby Track", "Banner",
            # Vehicles
            "Car Body", "Car Skin", "Wheels", "Booster", "Drift Trail",
            # Instruments (Festival)
            "Guitar", "Bass", "Drums", "Keytar", "Microphone",
            # LEGO
            "Decor Bundle", "Build Set"
        ]

        for category in categories:
            btn = wx.Button(self.categories_panel, label=category, size=(200, 40))
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

            self.view_equipped_btn = wx.Button(self, label="&View Equipped")
            self.view_equipped_btn.Bind(wx.EVT_BUTTON, self.on_view_equipped)
            loadout_sizer.Add(self.view_equipped_btn, flag=wx.RIGHT, border=5)

            self.view_loadouts_btn = wx.Button(self, label="Saved &Loadouts")
            self.view_loadouts_btn.Bind(wx.EVT_BUTTON, self.on_view_loadouts)
            loadout_sizer.Add(self.view_loadouts_btn, flag=wx.RIGHT, border=5)

            self.save_loadout_btn = wx.Button(self, label="&Save Current as Loadout")
            self.save_loadout_btn.Bind(wx.EVT_BUTTON, self.on_save_loadout)
            loadout_sizer.Add(self.save_loadout_btn, flag=wx.RIGHT, border=5)

            sizer.addItem(loadout_sizer)

        # Bottom buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

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
            "This will download fresh cosmetic data from Fortnite-API.com.\n\n"
            "This will also enable new cosmetic types:\n"
            "• Spray, Emoji, Toy, Banner, Aura, and more!\n\n"
            "Continue?",
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

    def on_view_equipped(self, event):
        """Show currently equipped cosmetics from the Locker Service"""
        try:
            if not self.auth or not self.auth.is_valid:
                speaker.speak("Please log in first")
                return

            speaker.speak("Fetching equipped cosmetics")
            equipped = self.auth.get_equipped_cosmetics()
            if not equipped:
                speaker.speak("Failed to fetch equipped cosmetics")
                messageBox("Could not retrieve equipped cosmetics from Epic Games.", "Error",
                           wx.OK | wx.ICON_ERROR, self)
                return

            # Build readable text
            lines = []
            # Map schema names to friendly names
            schema_names = {
                "Character": "Character",
                "Emotes": "Emotes",
                "Platform": "Lobby",
                "Sparks": "Instruments",
                "Wraps": "Wraps",
                "Jam": "Jam Tracks",
                "Vehicle": "Vehicle (Sedan)",
                "Vehicle_SUV": "Vehicle (SUV)",
                "Mimosa": "Companion",
                "Moments": "Moments",
            }

            for schema, data in equipped.items():
                friendly = schema_names.get(schema, schema)
                lines.append(f"--- {friendly} ---")
                slots = data.get("slots", {})
                for slot_name, slot_data in slots.items():
                    # Clean up slot name
                    display_name = slot_name.replace("LoadoutSlot_", "").replace("_", " ")
                    equipped_id = slot_data.get("equipped_id", "")
                    if equipped_id:
                        # Try to find friendly name from cosmetics data
                        item_id = equipped_id.split(":")[-1] if ":" in equipped_id else equipped_id
                        friendly_item = None
                        for c in self.cosmetics_data:
                            if c.get("id", "").lower() == item_id.lower():
                                friendly_item = c.get("name", item_id)
                                break
                        display_item = friendly_item or item_id
                        lines.append(f"  {display_name}: {display_item}")
                    else:
                        lines.append(f"  {display_name}: (empty)")
                lines.append("")

            text = "\n".join(lines)
            speaker.speak("Equipped cosmetics loaded")

            # Show in a dialog
            dlg = wx.Dialog(self, title="Currently Equipped Cosmetics", size=(500, 600))
            dlg_sizer = wx.BoxSizer(wx.VERTICAL)

            text_ctrl = wx.TextCtrl(dlg, value=text,
                                    style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP)
            dlg_sizer.Add(text_ctrl, proportion=1, flag=wx.EXPAND | wx.ALL, border=10)

            close_btn = wx.Button(dlg, wx.ID_CLOSE, "&Close")
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

    def _import_epic_presets_to_local(self, presets: list):
        """
        Auto-import Epic presets to local storage so they can be edited.
        Only imports presets not already in local storage (by name + categories match).
        """
        try:
            from lib.config.config_manager import config_manager
            try:
                config_manager.register('fa11y_loadouts', 'config/fa11y_loadouts.json',
                                        format='json', default=[])
            except Exception:
                pass

            local_loadouts = config_manager.get('fa11y_loadouts') or []
            if not isinstance(local_loadouts, list):
                local_loadouts = []

            # Build set of existing local names for fast lookup
            existing_local = set()
            for ll in local_loadouts:
                existing_local.add(ll.get("display_name", ""))

            # Group Epic presets by name
            by_name = {}
            for p in presets:
                name = p.get("displayName", "") or "(unnamed)"
                ltype = p.get("loadoutType", "")
                if name not in by_name:
                    by_name[name] = {}
                by_name[name][ltype] = {
                    "loadoutSlots": p.get("loadoutSlots", []),
                    "shuffleType": p.get("shuffleType", "DISABLED"),
                }

            # Import missing ones
            imported = 0
            for name, categories in by_name.items():
                if name not in existing_local:
                    local_loadouts.append({
                        "display_name": name,
                        "categories": categories,
                        "source": "epic_import",
                    })
                    imported += 1

            if imported > 0:
                config_manager.set('fa11y_loadouts', data=local_loadouts)
                logger.info(f"Imported {imported} Epic presets to local storage")

        except Exception as e:
            logger.warning(f"Could not import Epic presets: {e}")

    def _resolve_item_name(self, equipped_id: str) -> str:
        """Look up a friendly cosmetic name from its template ID."""
        if not equipped_id:
            return "(empty)"
        item_id = equipped_id.split(":")[-1] if ":" in equipped_id else equipped_id
        for c in self.cosmetics_data:
            if c.get("id", "").lower() == item_id.lower():
                return c.get("name", item_id)
        return item_id

    def on_view_loadouts(self, event):
        """Show saved loadout presets from the Locker Service"""
        try:
            if not self.auth or not self.auth.is_valid:
                speaker.speak("Please log in first")
                return

            speaker.speak("Fetching saved loadouts")

            # Fetch raw locker data to get all preset types
            locker_data = self.auth.query_locker_items()
            if not locker_data:
                speaker.speak("Failed to fetch loadouts")
                messageBox("Could not retrieve loadout presets from Epic Games.", "Error",
                           wx.OK | wx.ICON_ERROR, self)
                return

            presets = locker_data.get("loadoutPresets", [])
            if not presets:
                speaker.speak("No saved loadouts found")
                messageBox("You have no saved loadout presets.", "Loadouts",
                           wx.OK | wx.ICON_INFORMATION, self)
                return

            # Auto-import Epic presets to local storage for editing
            self._import_epic_presets_to_local(presets)

            # Merge presets with same name across categories into combined "All" entries
            merged_presets = []  # list of dicts with 'displayName', 'categories' dict, 'source'
            name_index = {}  # name -> index in merged_presets

            for p in presets:
                name = p.get("displayName", "") or "(unnamed)"
                ltype = p.get("loadoutType", "")

                if name in name_index:
                    # Add this category to existing merged entry
                    merged_presets[name_index[name]]["categories"][ltype] = {
                        "loadoutSlots": p.get("loadoutSlots", []),
                        "shuffleType": p.get("shuffleType", "DISABLED"),
                    }
                else:
                    name_index[name] = len(merged_presets)
                    merged_presets.append({
                        "displayName": name,
                        "categories": {
                            ltype: {
                                "loadoutSlots": p.get("loadoutSlots", []),
                                "shuffleType": p.get("shuffleType", "DISABLED"),
                            }
                        },
                        "source": "epic",
                    })

            # Also load locally saved loadouts
            try:
                from lib.config.config_manager import config_manager
                try:
                    config_manager.register('fa11y_loadouts', 'config/fa11y_loadouts.json',
                                            format='json', default=[])
                except Exception:
                    pass
                local_loadouts = config_manager.get('fa11y_loadouts') or []
                for ll in local_loadouts:
                    merged_presets.append({
                        "displayName": ll.get("display_name", "(unnamed)"),
                        "categories": ll.get("categories", {}),
                        "source": "local",
                    })
            except Exception as e:
                logger.warning(f"Could not load local loadouts: {e}")

            total = len(merged_presets)
            speaker.speak(f"Found {total} loadouts")

            # Show loadout selection dialog
            dlg = wx.Dialog(self, title=f"Loadouts ({total})", size=(600, 700))
            dlg_sizer = wx.BoxSizer(wx.VERTICAL)

            # Filter by type
            filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
            filter_sizer.Add(wx.StaticText(dlg, label="Filter by type:"),
                             flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)

            type_choices = ["All", "Multi-Category Only"] + sorted(set(LOADOUT_SCHEMA_NAMES.values()))
            type_filter = wx.Choice(dlg, choices=type_choices)
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

            def _type_label(entry):
                cats = entry.get("categories", {})
                cat_names = [LOADOUT_SCHEMA_NAMES.get(k, k.split("_")[-1]) for k in cats]
                if len(cat_names) > 1:
                    return " + ".join(sorted(cat_names))
                elif cat_names:
                    return cat_names[0]
                return "?"

            def refresh_list(filter_type="All"):
                nonlocal filtered_entries
                list_box.Clear()
                filtered_entries = []
                # Reverse lookup schema key from friendly name
                schema_key_for_filter = None
                for k, v in LOADOUT_SCHEMA_NAMES.items():
                    if v == filter_type:
                        schema_key_for_filter = k
                        break

                for entry in merged_presets:
                    cats = entry.get("categories", {})

                    if filter_type == "Multi-Category Only":
                        if len(cats) < 2:
                            continue
                    elif filter_type != "All":
                        if schema_key_for_filter and schema_key_for_filter not in cats:
                            continue

                    filtered_entries.append(entry)
                    name = entry.get("displayName", "(unnamed)")
                    label = _type_label(entry)
                    list_box.Append(f"{name} [{label}]")
                detail_text.SetValue("")

            refresh_list()

            def on_filter_changed(evt):
                sel = type_filter.GetString(type_filter.GetSelection())
                refresh_list(sel)
                speaker.speak(f"Showing {list_box.GetCount()} loadouts")

            type_filter.Bind(wx.EVT_CHOICE, on_filter_changed)

            def on_loadout_selected(evt):
                idx = list_box.GetSelection()
                if idx == wx.NOT_FOUND or idx >= len(filtered_entries):
                    return
                entry = filtered_entries[idx]
                lines = [f"Loadout: {entry.get('displayName', '(unnamed)')}",
                         f"Source: {entry.get('source', '?')}",
                         f"Categories: {_type_label(entry)}", ""]

                for cat_type, cat_data in entry.get("categories", {}).items():
                    cat_name = LOADOUT_SCHEMA_NAMES.get(cat_type, cat_type)
                    lines.append(f"--- {cat_name} ---")
                    for slot in cat_data.get("loadoutSlots", []):
                        st = slot.get("slotTemplate", "")
                        slot_name = st.split(":")[-1].replace("LoadoutSlot_", "").replace("_", " ") if ":" in st else st
                        equipped_id = slot.get("equippedItemId", "")
                        display_item = self._resolve_item_name(equipped_id)
                        lines.append(f"  {slot_name}: {display_item}")
                    lines.append("")

                detail_text.SetValue("\n".join(lines))

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

            # Equip via API
            equip_api_btn = wx.Button(dlg, label="Equip via &API")
            equip_api_btn.SetToolTip("Equip instantly via Locker Service API. Changes apply next match or game restart.")

            def on_equip_api(evt):
                idx = list_box.GetSelection()
                if idx == wx.NOT_FOUND or idx >= len(filtered_entries):
                    speaker.speak("No loadout selected")
                    return
                entry = filtered_entries[idx]
                name = entry.get("displayName", "(unnamed)")
                cats = entry.get("categories", {})

                cat_names = ", ".join(LOADOUT_SCHEMA_NAMES.get(k, k) for k in cats)
                result = messageBox(
                    f"Equip loadout '{name}' via API?\n\n"
                    f"Categories: {cat_names}\n\n"
                    "This applies instantly on Epic's servers.\n"
                    "Changes will appear in-game after restarting or loading into a match.",
                    "Equip via API",
                    wx.YES_NO | wx.ICON_QUESTION, dlg)
                if result == wx.YES:
                    speaker.speak(f"Equipping '{name}' via API...")
                    # Build PUT body with all categories in this loadout
                    put_data = {}
                    for cat_type, cat_data in cats.items():
                        formatted_slots = []
                        for slot in cat_data.get("loadoutSlots", []):
                            fs = {
                                "slotTemplate": slot["slotTemplate"],
                                "itemCustomizations": slot.get("itemCustomizations", []),
                            }
                            if slot.get("equippedItemId"):
                                fs["equippedItemId"] = slot["equippedItemId"]
                            formatted_slots.append(fs)
                        put_data[cat_type] = {
                            "loadoutSlots": formatted_slots,
                            "shuffleType": cat_data.get("shuffleType", "DISABLED"),
                        }

                    success = self.auth.update_active_loadout(put_data)
                    if success:
                        speaker.speak(f"Loadout '{name}' equipped via API ({len(cats)} categories)")
                    else:
                        speaker.speak(f"Failed to equip loadout")
                        messageBox(f"Failed to equip '{name}' via API.", "Error",
                                   wx.OK | wx.ICON_ERROR, dlg)

            equip_api_btn.Bind(wx.EVT_BUTTON, on_equip_api)
            btn_sizer.Add(equip_api_btn, flag=wx.RIGHT, border=5)

            # Equip via UI automation
            equip_ui_btn = wx.Button(dlg, label="Equip in &Game (UI)")
            equip_ui_btn.SetToolTip("Equip each item one-by-one using mouse automation in the Fortnite locker UI.")

            def on_equip_ui(evt):
                idx = list_box.GetSelection()
                if idx == wx.NOT_FOUND or idx >= len(filtered_entries):
                    speaker.speak("No loadout selected")
                    return
                entry = filtered_entries[idx]
                name = entry.get("displayName", "(unnamed)")

                # Build list of items to equip across ALL categories
                items_to_equip = []
                for cat_type, cat_data in entry.get("categories", {}).items():
                    for slot in cat_data.get("loadoutSlots", []):
                        equipped_id = slot.get("equippedItemId", "")
                        if not equipped_id:
                            continue
                        st = slot.get("slotTemplate", "")
                        slot_key = st.split(":")[-1] if ":" in st else st
                        automation = SLOT_TEMPLATE_TO_AUTOMATION.get(slot_key)
                        if not automation:
                            continue
                        category, slot_num = automation
                        if slot_num is None:
                            continue
                        item_name = self._resolve_item_name(equipped_id)
                        items_to_equip.append({
                            "name": item_name,
                            "category": category,
                            "slot": slot_num,
                            "slot_key": slot_key,
                        })

                if not items_to_equip:
                    speaker.speak("No equippable items in this loadout")
                    return

                item_list = "\n".join(f"  • {i['name']} → {i['category']} slot {i['slot']}" for i in items_to_equip)
                result = messageBox(
                    f"Equip loadout '{name}' in-game?\n\n"
                    f"This will equip {len(items_to_equip)} items one by one using mouse automation:\n"
                    f"{item_list}\n\n"
                    "Make sure Fortnite is open on the lobby screen.\n"
                    "Do not move the mouse during automation.",
                    "Equip in Game",
                    wx.YES_NO | wx.ICON_QUESTION, dlg)
                if result == wx.YES:
                    dlg.Iconize(True)
                    time.sleep(0.2)
                    self._perform_loadout_ui_automation(items_to_equip, name)
                    dlg.Iconize(False)
                    dlg.Raise()

            equip_ui_btn.Bind(wx.EVT_BUTTON, on_equip_ui)
            btn_sizer.Add(equip_ui_btn, flag=wx.RIGHT, border=5)

            # Delete local loadout button
            delete_btn = wx.Button(dlg, label="&Delete Local")
            delete_btn.SetToolTip("Delete a locally saved loadout")

            def on_delete_local(evt):
                idx = list_box.GetSelection()
                if idx == wx.NOT_FOUND or idx >= len(filtered_entries):
                    speaker.speak("No loadout selected")
                    return
                entry = filtered_entries[idx]
                if entry.get("source") != "local":
                    speaker.speak("Can only delete locally saved loadouts")
                    messageBox("This loadout is from Epic's servers and cannot be deleted from FA11y.",
                               "Cannot Delete", wx.OK | wx.ICON_INFORMATION, dlg)
                    return
                name = entry.get("displayName", "(unnamed)")
                result = messageBox(f"Delete local loadout '{name}'?", "Delete Loadout",
                                    wx.YES_NO | wx.ICON_WARNING, dlg)
                if result == wx.YES:
                    try:
                        from lib.config.config_manager import config_manager
                        local_loadouts = config_manager.get('fa11y_loadouts') or []
                        local_loadouts = [l for l in local_loadouts if l.get("display_name") != name]
                        config_manager.set('fa11y_loadouts', data=local_loadouts)
                        # Remove from merged list too
                        merged_presets[:] = [m for m in merged_presets
                                             if not (m.get("displayName") == name and m.get("source") == "local")]
                        refresh_list(type_filter.GetString(type_filter.GetSelection()))
                        speaker.speak(f"Deleted '{name}'")
                    except Exception as e:
                        speaker.speak("Error deleting loadout")
                        logger.error(f"Error deleting local loadout: {e}")

            delete_btn.Bind(wx.EVT_BUTTON, on_delete_local)
            btn_sizer.Add(delete_btn, flag=wx.RIGHT, border=5)

            close_btn = wx.Button(dlg, wx.ID_CLOSE, "&Close")
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

    def _perform_loadout_ui_automation(self, items: list, loadout_name: str):
        """Equip a list of items one by one using UI automation in Fortnite."""
        try:
            if not focus_fortnite_window():
                speaker.speak("Cannot find Fortnite window. Make sure the game is running.")
                return

            time.sleep(0.5)
            succeeded = 0
            failed = 0

            for i, item in enumerate(items):
                item_name = item["name"]
                category = item["category"]
                slot = item["slot"]

                logger.info(f"UI automation: equipping '{item_name}' to {category} slot {slot} ({i+1}/{len(items)})")

                # Use emote wheel coords for emote-category items
                if category == "Emotes":
                    slot_coords = EMOTE_SLOT_COORDS.get(slot)
                else:
                    slot_coords = SLOT_COORDS.get(slot)

                if not slot_coords:
                    logger.warning(f"No coords for {category} slot {slot}, skipping")
                    failed += 1
                    continue

                try:
                    # Click locker button
                    move_to_and_click(350, 69)
                    time.sleep(0.3)

                    # Click category
                    category_coords = CATEGORY_COORDS.get(category)
                    if category_coords:
                        move_to_and_click(category_coords[0], category_coords[1])
                        time.sleep(0.3)
                        current_x, current_y = get_mouse_position()
                        move_to(current_x + 500, current_y)
                        time.sleep(1.0)

                    # Click slot
                    move_to_and_click(slot_coords[0], slot_coords[1])
                    time.sleep(1.0)

                    # Click search bar
                    move_to_and_click(1030, 210)
                    time.sleep(0.5)

                    # Type item name
                    pyautogui.write(item_name, interval=0.02)
                    time.sleep(0.3)
                    pyautogui.press('enter')
                    time.sleep(0.1)

                    # Click item twice to equip
                    move_to_and_click(1020, 350)
                    time.sleep(0.05)
                    click_mouse('left')
                    time.sleep(0.1)

                    # Press escape to exit slot picker
                    pyautogui.press('escape')
                    time.sleep(0.5)

                    succeeded += 1

                except Exception as e:
                    logger.error(f"Error equipping '{item_name}': {e}")
                    failed += 1

            # Return to PLAY tab
            pyautogui.press('escape')
            time.sleep(0.5)
            move_to_and_click(130, 69)

            msg = f"Loadout '{loadout_name}': {succeeded}/{len(items)} items equipped"
            if failed > 0:
                msg += f" ({failed} failed)"
            speaker.speak(msg)
            logger.info(msg)

        except Exception as e:
            logger.error(f"Error in loadout UI automation: {e}")
            speaker.speak("Error during automation")

    def on_save_loadout(self, event):
        """Save the currently equipped cosmetics as a local loadout preset."""
        try:
            if not self.auth or not self.auth.is_valid:
                speaker.speak("Please log in first")
                return

            # Ask which categories to save
            schema_choices = [
                ("All Categories", None),
                ("Character", "CosmeticLoadout:LoadoutSchema_Character"),
                ("Emotes", "CosmeticLoadout:LoadoutSchema_Emotes"),
                ("Lobby", "CosmeticLoadout:LoadoutSchema_Platform"),
                ("Wraps", "CosmeticLoadout:LoadoutSchema_Wraps"),
                ("Instruments", "CosmeticLoadout:LoadoutSchema_Sparks"),
                ("Jam Tracks", "CosmeticLoadout:LoadoutSchema_Jam"),
                ("Vehicle (Sedan)", "CosmeticLoadout:LoadoutSchema_Vehicle"),
            ]

            choice_dlg = wx.SingleChoiceDialog(
                self,
                "Which loadout type do you want to save?\n\n"
                "Select 'All Categories' to save everything at once.",
                "Save Loadout",
                [c[0] for c in schema_choices]
            )
            if choice_dlg.ShowModal() != wx.ID_OK:
                choice_dlg.Destroy()
                return
            selected_idx = choice_dlg.GetSelection()
            choice_dlg.Destroy()

            friendly_name, loadout_type = schema_choices[selected_idx]

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

            # Check for duplicate name
            from lib.config.config_manager import config_manager
            try:
                config_manager.register('fa11y_loadouts', 'config/fa11y_loadouts.json',
                                        format='json', default=[])
            except Exception:
                pass

            saved_loadouts = config_manager.get('fa11y_loadouts') or []
            if not isinstance(saved_loadouts, list):
                saved_loadouts = []

            existing_idx = None
            for i, ll in enumerate(saved_loadouts):
                if ll.get("display_name", "").lower() == loadout_name.lower():
                    existing_idx = i
                    break

            if existing_idx is not None:
                result = messageBox(
                    f"A loadout named '{loadout_name}' already exists.\n\n"
                    "Do you want to overwrite it?",
                    "Loadout Exists",
                    wx.YES_NO | wx.ICON_WARNING, self)
                if result != wx.YES:
                    speaker.speak("Cancelled. Choose a different name.")
                    return

            speaker.speak(f"Saving loadout '{loadout_name}'...")

            # Get current equipped items
            locker_data = self.auth.query_locker_items()
            if not locker_data:
                speaker.speak("Failed to fetch current loadout data")
                return

            active_loadout = locker_data.get("activeLoadoutGroup", {})
            all_loadouts = active_loadout.get("loadouts", {})

            if loadout_type is None:
                # Save all categories
                categories_to_save = dict(all_loadouts)
            else:
                cat_data = all_loadouts.get(loadout_type)
                if not cat_data:
                    speaker.speak(f"No equipped items found for {friendly_name}")
                    return
                categories_to_save = {loadout_type: cat_data}

            new_loadout = {
                "display_name": loadout_name,
                "categories": {}
            }

            for cat_type, cat_data in categories_to_save.items():
                new_loadout["categories"][cat_type] = {
                    "loadoutSlots": cat_data.get("loadoutSlots", []),
                    "shuffleType": cat_data.get("shuffleType", "DISABLED"),
                }

            if existing_idx is not None:
                saved_loadouts[existing_idx] = new_loadout
            else:
                saved_loadouts.append(new_loadout)
            config_manager.set('fa11y_loadouts', data=saved_loadouts)

            cat_count = len(categories_to_save)
            slot_count = sum(len(c.get("loadoutSlots", [])) for c in categories_to_save.values())
            speaker.speak(f"Loadout '{loadout_name}' saved! {cat_count} categories, {slot_count} slots.")
            messageBox(
                f"Loadout '{loadout_name}' saved locally.\n\n"
                f"Categories: {', '.join(LOADOUT_SCHEMA_NAMES.get(k, k) for k in categories_to_save)}\n"
                f"Total slots: {slot_count}",
                "Loadout Saved", wx.OK | wx.ICON_INFORMATION, self)

        except Exception as e:
            logger.error(f"Error saving loadout: {e}")
            speaker.speak("Error saving loadout")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)

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
