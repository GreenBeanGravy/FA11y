"""
Locker GUI for FA11y
Provides an interface for viewing Fortnite cosmetics
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

from lib.guis.gui_utilities import (
    AccessibleDialog, BoxSizerHelper, messageBox,
    ensure_window_focus_and_center_mouse, SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS
)

# Initialize logger
logger = logging.getLogger(__name__)

# Global speaker instance
speaker = Auto()

# Map backend types to friendly names
COSMETIC_TYPE_MAP = {
    "AthenaCharacter": "Outfit",
    "AthenaBackpack": "Back Bling",
    "AthenaDance": "Emote",
    "AthenaPickaxe": "Pickaxe",
    "AthenaGlider": "Glider",
    "AthenaItemWrap": "Wrap",
    "AthenaLoadingScreen": "Loading Screen",
    "AthenaMusicPack": "Music",
    "AthenaSkyDiveContrail": "Contrail",
    "VehicleCosmetics_Body": "Car Body",
    "AthenaShoes": "Kicks",
    "AthenaPetCarrier": "Pet"
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


class LockerDialog(AccessibleDialog):
    """Dialog for viewing Fortnite cosmetics locker"""

    def __init__(self, parent, cosmetics_data: List[dict]):
        super().__init__(parent, title="Fortnite Locker Viewer", helpId="LockerViewer")
        self.cosmetics_data = cosmetics_data
        self.filtered_cosmetics = cosmetics_data.copy()

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

        # Count by type
        for cosmetic in self.cosmetics_data:
            cosmetic_type = cosmetic.get("type", "Unknown")
            friendly_name = COSMETIC_TYPE_MAP.get(cosmetic_type, cosmetic_type)
            key = f"type_{friendly_name}"
            stats[key] = stats.get(key, 0) + 1

        # Count by rarity
        for cosmetic in self.cosmetics_data:
            rarity = cosmetic.get("rarity", "common").title()
            key = f"rarity_{rarity}"
            stats[key] = stats.get(key, 0) + 1

        return stats

    def makeSettings(self, sizer: BoxSizerHelper):
        """Create the dialog content"""

        # Header with stats
        header_text = f"Total Cosmetics: {self.stats['total']}"
        if self.stats.get('favorites', 0) > 0:
            header_text += f" | Favorites: {self.stats['favorites']}"

        header_label = wx.StaticText(self, label=header_text)
        header_font = header_label.GetFont()
        header_font.PointSize += 2
        header_font = header_font.Bold()
        header_label.SetFont(header_font)
        sizer.addItem(header_label)

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

        type_choices = ["All"] + sorted(set(COSMETIC_TYPE_MAP.values()))
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
        self.cosmetics_list.InsertColumn(0, "Name", width=250)
        self.cosmetics_list.InsertColumn(1, "Type", width=120)
        self.cosmetics_list.InsertColumn(2, "Rarity", width=100)
        self.cosmetics_list.InsertColumn(3, "Season", width=100)
        self.cosmetics_list.InsertColumn(4, "Variants", width=80)

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
            size=(-1, 120)
        )
        details_sizer.Add(self.details_text, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)

        sizer.addItem(details_sizer, flag=wx.EXPAND)

        # Buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.refresh_btn = wx.Button(self, label="&Refresh Data")
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        button_sizer.Add(self.refresh_btn)

        button_sizer.AddSpacer(10)

        self.export_btn = wx.Button(self, label="&Export List")
        self.export_btn.Bind(wx.EVT_BUTTON, self.on_export)
        button_sizer.Add(self.export_btn)

        button_sizer.AddStretchSpacer()

        self.close_btn = wx.Button(self, label="&Close")
        self.close_btn.Bind(wx.EVT_BUTTON, self.on_close)
        button_sizer.Add(self.close_btn)

        sizer.addItem(button_sizer, flag=wx.EXPAND)

        # Bind key events
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)

        # Initial population
        self.update_list()

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
        speaker.speak(f"Showing {len(self.filtered_cosmetics)} results")

    def on_filter_changed(self, event):
        """Handle type filter changes"""
        self.current_type_filter = self.type_filter.GetStringSelection()
        self.update_list()
        speaker.speak(f"Filter: {self.current_type_filter}. Showing {len(self.filtered_cosmetics)} results")

    def on_sort_changed(self, event):
        """Handle sort option changes"""
        self.current_sort = self.sort_choice.GetStringSelection()
        self.update_list()
        speaker.speak(f"Sorted by {self.current_sort}")

    def filter_cosmetics(self) -> List[dict]:
        """Filter cosmetics based on current search and type filter"""
        filtered = []

        search_lower = self.current_search.lower()

        for cosmetic in self.cosmetics_data:
            # Type filter
            if self.current_type_filter != "All":
                cosmetic_type = cosmetic.get("type", "")
                friendly_type = COSMETIC_TYPE_MAP.get(cosmetic_type, cosmetic_type)
                if friendly_type != self.current_type_filter:
                    continue

            # Search filter
            if search_lower:
                name = cosmetic.get("name", "").lower()
                description = cosmetic.get("description", "").lower()
                cosmetic_type = cosmetic.get("type", "")
                friendly_type = COSMETIC_TYPE_MAP.get(cosmetic_type, cosmetic_type).lower()
                rarity = cosmetic.get("rarity", "").lower()

                if not (search_lower in name or
                       search_lower in description or
                       search_lower in friendly_type or
                       search_lower in rarity):
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
                COSMETIC_TYPE_MAP.get(x.get("type", ""), x.get("type", "")),
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
        total = len(self.cosmetics_data)
        showing = len(self.filtered_cosmetics)
        self.results_label.SetLabel(f"Showing {showing} of {total} cosmetics")

        # Clear list
        self.cosmetics_list.DeleteAllItems()

        # Populate list
        for idx, cosmetic in enumerate(self.filtered_cosmetics):
            # Determine display values
            name = cosmetic.get("name", "Unknown")
            if cosmetic.get("favorite", False):
                name = "⭐ " + name

            cosmetic_type = cosmetic.get("type", "Unknown")
            friendly_type = COSMETIC_TYPE_MAP.get(cosmetic_type, cosmetic_type)

            rarity = cosmetic.get("rarity", "common").title()

            season = f"C{cosmetic.get('introduction_chapter', '?')}S{cosmetic.get('introduction_season', '?')}"

            variant_count = len(cosmetic.get("owned_variants", []))
            variants_str = str(variant_count) if variant_count > 0 else "-"

            # Insert item
            index = self.cosmetics_list.InsertItem(idx, name)
            self.cosmetics_list.SetItem(index, 1, friendly_type)
            self.cosmetics_list.SetItem(index, 2, rarity)
            self.cosmetics_list.SetItem(index, 3, season)
            self.cosmetics_list.SetItem(index, 4, variants_str)

            # Set item data to index in filtered list
            self.cosmetics_list.SetItemData(index, idx)

            # Color code by rarity
            color = self.get_rarity_color(rarity.lower())
            if color:
                self.cosmetics_list.SetItemTextColour(index, color)

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
            "dark": wx.Colour(138, 43, 226),
            "frozen": wx.Colour(148, 211, 246),
            "lava": wx.Colour(232, 64, 7),
            "shadow": wx.Colour(74, 74, 74),
            "slurp": wx.Colour(0, 228, 255)
        }
        return colors.get(rarity.lower())

    def on_item_focused(self, event):
        """Handle item focus for announcements"""
        index = event.GetIndex()
        cosmetic_idx = self.cosmetics_list.GetItemData(index)

        if 0 <= cosmetic_idx < len(self.filtered_cosmetics):
            cosmetic = self.filtered_cosmetics[cosmetic_idx]
            name = cosmetic.get("name", "Unknown")
            cosmetic_type = COSMETIC_TYPE_MAP.get(cosmetic.get("type", ""), "Unknown")
            rarity = cosmetic.get("rarity", "common").title()

            # Announce with index
            total = len(self.filtered_cosmetics)
            announcement = f"Item {index + 1} of {total}: {name}, {cosmetic_type}, {rarity}"
            wx.CallLater(150, lambda: speaker.speak(announcement))

    def on_item_selected(self, event):
        """Handle item selection in list"""
        index = event.GetIndex()
        cosmetic_idx = self.cosmetics_list.GetItemData(index)

        if 0 <= cosmetic_idx < len(self.filtered_cosmetics):
            cosmetic = self.filtered_cosmetics[cosmetic_idx]
            self.show_cosmetic_details(cosmetic)

    def on_item_activated(self, event):
        """Handle item double-click/activation"""
        index = event.GetIndex()
        cosmetic_idx = self.cosmetics_list.GetItemData(index)

        if 0 <= cosmetic_idx < len(self.filtered_cosmetics):
            cosmetic = self.filtered_cosmetics[cosmetic_idx]
            self.show_detailed_info(cosmetic)

    def show_cosmetic_details(self, cosmetic: dict):
        """Show cosmetic details in the details panel"""
        details = []

        details.append(f"Name: {cosmetic.get('name', 'Unknown')}")
        details.append(f"ID: {cosmetic.get('id', 'Unknown')}")

        cosmetic_type = cosmetic.get("type", "Unknown")
        friendly_type = COSMETIC_TYPE_MAP.get(cosmetic_type, cosmetic_type)
        details.append(f"Type: {friendly_type} ({cosmetic_type})")

        details.append(f"Rarity: {cosmetic.get('rarity', 'common').title()}")

        details.append(f"Season: Chapter {cosmetic.get('introduction_chapter', '?')}, Season {cosmetic.get('introduction_season', '?')}")

        if cosmetic.get("description"):
            details.append(f"\nDescription: {cosmetic['description']}")

        variants = cosmetic.get("owned_variants", [])
        if variants:
            details.append(f"\nVariants: {len(variants)}")
            for variant in variants[:5]:  # Show first 5
                details.append(f"  - {variant.get('channel', '?')}: {variant.get('stage', '?')}")
            if len(variants) > 5:
                details.append(f"  ... and {len(variants) - 5} more")

        if cosmetic.get("favorite"):
            details.append("\n⭐ FAVORITE")

        self.details_text.SetValue("\n".join(details))

    def show_detailed_info(self, cosmetic: dict):
        """Show detailed information dialog"""
        dlg = CosmeticDetailDialog(self, cosmetic)
        dlg.ShowModal()
        dlg.Destroy()

    def on_refresh(self, event):
        """Handle refresh button"""
        result = messageBox(
            "This will re-authenticate with Epic Games and download fresh cosmetic data. Continue?",
            "Refresh Locker Data",
            wx.YES_NO | wx.ICON_QUESTION,
            self
        )

        if result == wx.YES:
            speaker.speak("Refreshing locker data")
            self.EndModal(wx.ID_REFRESH)

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
                        f.write("Name,Type,Rarity,Season,Variants\n")
                        for cosmetic in self.filtered_cosmetics:
                            name = cosmetic.get('name', 'Unknown')
                            cosmetic_type = COSMETIC_TYPE_MAP.get(cosmetic.get('type', ''), 'Unknown')
                            rarity = cosmetic.get('rarity', 'common')
                            season = f"C{cosmetic.get('introduction_chapter', '?')}S{cosmetic.get('introduction_season', '?')}"
                            variants = len(cosmetic.get('owned_variants', []))
                            f.write(f'"{name}",{cosmetic_type},{rarity},{season},{variants}\n')
                else:
                    with open(path, 'w', encoding='utf-8') as f:
                        for cosmetic in self.filtered_cosmetics:
                            name = cosmetic.get('name', 'Unknown')
                            cosmetic_type = COSMETIC_TYPE_MAP.get(cosmetic.get('type', ''), 'Unknown')
                            rarity = cosmetic.get('rarity', 'common')
                            f.write(f"{name} - {cosmetic_type} ({rarity})\n")

                speaker.speak(f"Exported {len(self.filtered_cosmetics)} cosmetics")
                messageBox(f"Exported {len(self.filtered_cosmetics)} cosmetics to {path}", "Export Successful", wx.OK | wx.ICON_INFORMATION, self)
            except Exception as e:
                logger.error(f"Export failed: {e}")
                messageBox(f"Export failed: {e}", "Export Error", wx.OK | wx.ICON_ERROR, self)

        dlg.Destroy()

    def on_close(self, event):
        """Handle close button"""
        self.EndModal(wx.ID_CLOSE)


class CosmeticDetailDialog(AccessibleDialog):
    """Dialog showing detailed cosmetic information"""

    def __init__(self, parent, cosmetic: dict):
        super().__init__(parent, title=f"Cosmetic Details: {cosmetic.get('name', 'Unknown')}", helpId="CosmeticDetails")
        self.cosmetic = cosmetic
        self.setupDialog()
        self.SetSize((600, 500))
        self.CentreOnParent()

    def makeSettings(self, sizer: BoxSizerHelper):
        """Create the dialog content"""

        # Name
        name = self.cosmetic.get('name', 'Unknown')
        if self.cosmetic.get("favorite"):
            name = "⭐ " + name

        name_label = wx.StaticText(self, label=name)
        name_font = name_label.GetFont()
        name_font.PointSize += 3
        name_font = name_font.Bold()
        name_label.SetFont(name_font)
        sizer.addItem(name_label)

        # Details in a text control for easy reading
        details = []

        details.append(f"ID: {self.cosmetic.get('id', 'Unknown')}")

        cosmetic_type = self.cosmetic.get("type", "Unknown")
        friendly_type = COSMETIC_TYPE_MAP.get(cosmetic_type, cosmetic_type)
        details.append(f"Type: {friendly_type}")
        details.append(f"Backend Type: {cosmetic_type}")

        rarity = self.cosmetic.get('rarity', 'common').title()
        details.append(f"Rarity: {rarity}")

        chapter = self.cosmetic.get('introduction_chapter', '?')
        season = self.cosmetic.get('introduction_season', '?')
        details.append(f"Introduction: Chapter {chapter}, Season {season}")

        if self.cosmetic.get("description"):
            details.append(f"\nDescription:\n{self.cosmetic['description']}")

        # Variants
        variants = self.cosmetic.get("owned_variants", [])
        if variants:
            details.append(f"\n--- Owned Variants ({len(variants)}) ---")
            for variant in variants:
                details.append(f"Channel: {variant.get('channel', 'Unknown')}")
                details.append(f"  Stage: {variant.get('stage', 'Unknown')}")
                details.append("")

        details_text = wx.TextCtrl(
            self,
            value="\n".join(details),
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP
        )

        sizer.addItem(details_text, flag=wx.EXPAND, proportion=1)

        # Close button
        close_btn = wx.Button(self, label="&Close")
        close_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        sizer.addItem(close_btn)


def launch_locker_viewer():
    """Launch the locker viewer GUI with proper isolation from other GUI frameworks"""

    # Store the current foreground window to restore focus later
    current_window = ctypes.windll.user32.GetForegroundWindow()

    # Determine cache file path
    cache_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "fortnite_locker_cache.json")

    app = None
    app_created = False

    try:
        # Check if wx.App already exists and is usable
        existing_app = wx.GetApp()
        if existing_app is None:
            # Create new app only if none exists
            app = wx.App(False)  # False = don't redirect stdout/stderr
            app_created = True
        else:
            # Use existing app
            app = existing_app
            app_created = False

        # Check for cache file
        if not os.path.exists(cache_file):
            logger.warning(f"No cached locker data found at {cache_file}")
            speaker.speak("No cached locker data found. Please authenticate first.")
            messageBox(
                "No cached locker data found. Please authenticate with Epic Games first to download your locker data.",
                "No Data",
                wx.OK | wx.ICON_WARNING
            )
            return None

        # Load cosmetics data
        with open(cache_file, 'r', encoding='utf-8') as f:
            cosmetics_data = json.load(f)

        if not cosmetics_data:
            logger.warning("Cached locker data is empty")
            speaker.speak("Cached locker data is empty")
            messageBox(
                "Cached locker data is empty.",
                "No Data",
                wx.OK | wx.ICON_WARNING
            )
            return None

        logger.info(f"Loaded {len(cosmetics_data)} cosmetics from cache")

        # Create main dialog
        dlg = LockerDialog(None, cosmetics_data)

        try:
            # Ensure proper focus and mouse centering
            ensure_window_focus_and_center_mouse(dlg)

            # Announce dialog opening
            speaker.speak(f"Fortnite Locker Viewer. {len(cosmetics_data)} cosmetics loaded.")

            # Show modal dialog
            result = dlg.ShowModal()

            return result

        finally:
            # Ensure dialog cleanup
            if dlg:
                dlg.Destroy()

            # Process any remaining events but don't destroy the app
            if app:
                app.ProcessPendingEvents()

                # Only yield if we have pending events
                while app.HasPendingEvents():
                    app.Yield()

    except Exception as e:
        logger.error(f"Error launching locker viewer: {e}")
        speaker.speak("Error opening locker viewer")
        messageBox(
            f"Failed to load locker data: {e}",
            "Error",
            wx.OK | wx.ICON_ERROR
        )
        return None

    finally:
        # Enhanced cleanup to prevent conflicts with tkinter
        try:
            # Force garbage collection to clean up dialog objects
            gc.collect()

            # Reset display/window manager state that might interfere with tkinter
            try:
                # Force release of any remaining window handles
                ctypes.windll.user32.SetFocus(0)

                # Clear any remaining clipboard ownership that wx might hold
                if ctypes.windll.user32.OpenClipboard(0):
                    ctypes.windll.user32.EmptyClipboard()
                    ctypes.windll.user32.CloseClipboard()

            except Exception:
                pass

            # Small delay to allow cleanup to complete
            time.sleep(0.05)

            # One more garbage collection
            gc.collect()

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
