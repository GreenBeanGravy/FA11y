"""
Locker Selector GUI for FA11y
Provides an interface to equip cosmetic items in the Fortnite locker
"""
import os
import sys
import time
import logging
import gc
from typing import Optional, Tuple, Dict, List
import ctypes
import ctypes.wintypes

import wx
import pyautogui
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import (
    AccessibleDialog, BoxSizerHelper, ButtonHelper,
    messageBox, force_focus_window, ensure_window_focus_and_center_mouse,
    center_mouse_in_window, BORDER_FOR_DIALOGS
)

# Initialize logger
logger = logging.getLogger(__name__)

# Global speaker instance
speaker = Auto()


class DisplayableError(Exception):
    """Error that can be displayed to the user"""

    def __init__(self, displayMessage: str, titleMessage: str = "Error"):
        self.displayMessage = displayMessage
        self.titleMessage = titleMessage

    def displayError(self, parentWindow=None):
        wx.CallAfter(
            messageBox,
            message=self.displayMessage,
            caption=self.titleMessage,
            style=wx.OK | wx.ICON_ERROR,
            parent=parentWindow
        )


class LockerSelectorGUI(AccessibleDialog):
    """Locker selector GUI for equipping cosmetic items"""

    # Slot coordinates (reused across categories)
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

    # Category positions
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

    # Sub-category positions (clicked after main category)
    SUBCATEGORY_COORDS = {
        'SUV/Truck': (120, 670),  # Under Cars
        'Game Moments': (110, 790)  # Under Music
    }

    # Category structure: {category: [(slot_name, slot_number), ...]}
    CATEGORY_ITEMS = {
        'Character': [
            ('Outfit', 1),
            ('Backbling', 2),
            ('Pickaxe', 3),
            ('Glider', 4),
            ('Kicks', 5),
            ('Contrail', 6)
        ],
        'Emotes': [
            ('Emote 1', 1),
            ('Emote 2', 2),
            ('Emote 3', 3),
            ('Emote 4', 4),
            ('Emote 5', 5),
            ('Emote 6', 6)
        ],
        'Sidekicks': [
            ('Pet', 1)
        ],
        'Wraps': [
            ('Rifles', 1),
            ('Shotguns', 2),
            ('Submachine Guns', 3),
            ('Snipers', 4),
            ('Pistols', 5),
            ('Utility', 6),
            ('Vehicles', 7)
        ],
        'Lobby': [
            ('Homebase Icon', 1),
            ('Lobby Music', 2),
            ('Loading Screen', 3)
        ],
        'Cars': [
            ('Car Body', 1),
            ('Car Decal', 2),
            ('Car Tires', 3),
            ('Car Trail', 4),
            ('Car Boost', 5)
        ],
        'Instruments': [
            ('Bass', 1),
            ('Guitar', 2),
            ('Drums', 3),
            ('Keytar', 4),
            ('Microphone', 5)
        ],
        'Music': [
            ('Jam Track 1', 1),
            ('Jam Track 2', 2),
            ('Jam Track 3', 3),
            ('Jam Track 4', 4),
            ('Jam Track 5', 5),
            ('Jam Track 6', 6),
            ('Jam Track 7', 7),
            ('Jam Track 8', 8)
        ],
        'SUV/Truck': [  # Sub-category under Cars
            ('SUV Body', 1),
            ('SUV Decal', 2),
            ('SUV Tires', 3),
            ('SUV Trail', 4),
            ('SUV Boost', 5)
        ],
        'Game Moments': [  # Sub-category under Music
            ('Intro Music', 1),
            ('Celebration Music', 2)
        ]
    }

    def __init__(self, parent=None):
        super().__init__(parent, title="Locker Selector", helpId="LockerSelector")
        self.notebook = None
        self.setupDialog()

    def makeSettings(self, settingsSizer: BoxSizerHelper):
        """Create dialog content with tabbed interface"""

        # Add title label
        titleLabel = wx.StaticText(
            self,
            label="Select a category and cosmetic slot to equip an item",
        )
        font = titleLabel.GetFont()
        font.PointSize += 1
        font = font.Bold()
        titleLabel.SetFont(font)
        settingsSizer.addItem(titleLabel)

        # Create notebook (tabbed interface)
        self.notebook = wx.Notebook(self)

        # Add tabs in order with sub-categories next to their parent categories
        # Character
        panel = self.create_category_panel('Character', self.notebook)
        self.notebook.AddPage(panel, 'Character')

        # Emotes
        panel = self.create_category_panel('Emotes', self.notebook)
        self.notebook.AddPage(panel, 'Emotes')

        # Sidekicks
        panel = self.create_category_panel('Sidekicks', self.notebook)
        self.notebook.AddPage(panel, 'Sidekicks')

        # Wraps
        panel = self.create_category_panel('Wraps', self.notebook)
        self.notebook.AddPage(panel, 'Wraps')

        # Lobby
        panel = self.create_category_panel('Lobby', self.notebook)
        self.notebook.AddPage(panel, 'Lobby')

        # Cars + SUV/Truck sub-category
        panel = self.create_category_panel('Cars', self.notebook)
        self.notebook.AddPage(panel, 'Cars')

        suv_panel = self.create_category_panel('SUV/Truck', self.notebook, parent_category='Cars')
        self.notebook.AddPage(suv_panel, 'SUV/Truck')

        # Instruments
        panel = self.create_category_panel('Instruments', self.notebook)
        self.notebook.AddPage(panel, 'Instruments')

        # Music + Game Moments sub-category
        panel = self.create_category_panel('Music', self.notebook)
        self.notebook.AddPage(panel, 'Music')

        game_moments_panel = self.create_category_panel('Game Moments', self.notebook, parent_category='Music')
        self.notebook.AddPage(game_moments_panel, 'Game Moments')

        settingsSizer.addItem(self.notebook, proportion=1, flag=wx.EXPAND)

        # Bind notebook page change event for announcements
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.onPageChanged)

        # Bind key events
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)

    def onPageChanged(self, event):
        """Handle notebook page change and announce tab"""
        page_index = event.GetSelection()
        if page_index >= 0 and page_index < self.notebook.GetPageCount():
            tab_text = self.notebook.GetPageText(page_index)
            speaker.speak(tab_text)
        event.Skip()

    def onButtonFocus(self, event):
        """Handle button focus to announce with index"""
        button = event.GetEventObject()
        wx.CallAfter(self.announceButtonWithIndex, button)
        event.Skip()

    def announceButtonWithIndex(self, button):
        """Announce button with index after focus"""
        if hasattr(button, 'index') and hasattr(button, 'total'):
            label = button.GetLabel()
            wx.CallLater(150, lambda: speaker.speak(f"Option {button.index} of {button.total}: {label}"))

    def create_category_panel(self, category: str, parent, parent_category: str = None) -> wx.Panel:
        """Create a panel for a category with its items"""
        panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)

        items = self.CATEGORY_ITEMS.get(category, [])
        total_items = len(items)

        for index, (item_name, slot_number) in enumerate(items, 1):
            button = wx.Button(panel, label=item_name)
            button.Bind(wx.EVT_BUTTON, lambda evt, cat=category, name=item_name, slot=slot_number, parent_cat=parent_category:
                        self.onSelectSlot(evt, cat, name, slot, parent_cat))

            # Store index information for focus announcements
            button.index = index
            button.total = total_items

            # Bind focus event for index announcements
            button.Bind(wx.EVT_SET_FOCUS, self.onButtonFocus)

            sizer.Add(button, 0, wx.ALL | wx.EXPAND, 5)

        panel.SetSizer(sizer)
        return panel

    def onSelectSlot(self, evt, category: str, item_name: str, slot_number: int, parent_category: str = None):
        """Handle locker slot button click"""
        try:
            dlg = SearchDialog(self, item_name)

            # Ensure search dialog gets proper focus and mouse centering
            wx.CallAfter(lambda: ensure_window_focus_and_center_mouse(dlg))

            if dlg.ShowModal() == wx.ID_OK:
                item_to_equip = dlg.getSearchText()
                if item_to_equip.strip():
                    dlg.Destroy()
                    self.EndModal(wx.ID_OK)

                    # Perform locker item equip
                    success = self.equip_item(category, item_name, slot_number, item_to_equip, parent_category)
                    if success:
                        speaker.speak(f"{item_to_equip} selected!")
                else:
                    dlg.Destroy()
            else:
                dlg.Destroy()
        except Exception as e:
            error = DisplayableError(
                f"Error opening item search: {str(e)}",
                "Locker Selection Error"
            )
            error.displayError(self)

    def onKeyEvent(self, event):
        """Handle key events for shortcuts"""
        key_code = event.GetKeyCode()

        if key_code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return

        # Allow normal navigation
        event.Skip()

    def equip_item(self, category: str, item_name: str, slot_number: int, item_to_equip: str, parent_category: str = None) -> bool:
        """Equip a cosmetic item by automating UI interactions"""
        try:
            # Get slot coordinates
            slot_coords = self.SLOT_COORDS.get(slot_number)
            if not slot_coords:
                logger.error(f"Unknown slot number: {slot_number}")
                return False

            # Click initial locker button position
            pyautogui.moveTo(420, 69, duration=0.05)
            pyautogui.click()
            time.sleep(0.3)

            # Handle sub-categories (need to click parent category first)
            if parent_category:
                # Click parent category
                parent_coords = self.CATEGORY_COORDS.get(parent_category)
                if parent_coords:
                    pyautogui.moveTo(parent_coords[0], parent_coords[1], duration=0.05)
                    pyautogui.click()
                    time.sleep(0.5)

                # Click sub-category
                sub_coords = self.SUBCATEGORY_COORDS.get(category)
                if sub_coords:
                    pyautogui.moveTo(sub_coords[0], sub_coords[1], duration=0.05)
                    pyautogui.click()
                    time.sleep(0.3)

                    # Move mouse 500 pixels to the right and wait
                    current_x, current_y = pyautogui.position()
                    pyautogui.moveTo(current_x + 500, current_y, duration=0.05)
                    time.sleep(1.0)
            else:
                # Click main category
                category_coords = self.CATEGORY_COORDS.get(category)
                if category_coords:
                    pyautogui.moveTo(category_coords[0], category_coords[1], duration=0.05)
                    pyautogui.click()
                    time.sleep(0.3)

                    # Move mouse 500 pixels to the right and wait
                    current_x, current_y = pyautogui.position()
                    pyautogui.moveTo(current_x + 500, current_y, duration=0.05)
                    time.sleep(1.0)

            # Now move to slot position and click
            pyautogui.moveTo(slot_coords[0], slot_coords[1], duration=0.05)
            pyautogui.click()
            time.sleep(1.0)

            # Click search bar
            pyautogui.moveTo(1030, 210, duration=0.05)
            pyautogui.click()
            time.sleep(0.5)

            # Type the item name
            pyautogui.typewrite(item_to_equip)
            pyautogui.press('enter')
            time.sleep(0.1)

            # Click the item (twice)
            pyautogui.moveTo(1020, 350, duration=0.05)
            pyautogui.click()
            time.sleep(0.05)
            pyautogui.click()
            time.sleep(0.1)

            # Press escape
            pyautogui.press('escape')
            time.sleep(1)

            # Click final position
            pyautogui.moveTo(200, 69, duration=0.05)
            pyautogui.click()

            return True

        except Exception as e:
            logger.error(f"Error equipping item: {e}")
            return False


class SearchDialog(AccessibleDialog):
    """Search dialog for cosmetic item input"""

    def __init__(self, parent, slot_name: str):
        self.slot_name = slot_name
        super().__init__(parent, title=f"Search {slot_name}", helpId="LockerSearch")
        self.setupDialog()

    def makeSettings(self, settingsSizer: BoxSizerHelper):
        """Create search dialog content"""

        # Instruction label
        instructionLabel = wx.StaticText(
            self,
            label=f"Enter the name of the item to equip to {self.slot_name}:",
        )
        settingsSizer.addItem(instructionLabel)

        # Search text control
        self.searchText = settingsSizer.addLabeledControl(
            "Item name:",
            wx.TextCtrl,
            style=wx.TE_PROCESS_ENTER
        )

        # Disable up/down arrow key cursor movement
        self.searchText.Bind(wx.EVT_CHAR_HOOK, self.onTextCharHook)

        # Bind Enter key to OK
        self.searchText.Bind(wx.EVT_TEXT_ENTER, self.onOk)

        # Bind key events
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)

    def onTextCharHook(self, event):
        """Handle char events for text controls"""
        key_code = event.GetKeyCode()

        # Allow TAB for navigation
        if key_code == wx.WXK_TAB:
            event.Skip()
            return

        # Block up/down arrow keys
        if key_code in [wx.WXK_UP, wx.WXK_DOWN]:
            return

        # Allow all other keys
        event.Skip()

    def onKeyEvent(self, event):
        """Handle key events for shortcuts"""
        key_code = event.GetKeyCode()

        if key_code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            # Enter key submits
            if self.FindFocus() == self.searchText:
                self.onOk(event)
            else:
                self.EndModal(wx.ID_CANCEL)
            return

        event.Skip()

    def postInit(self):
        """Post-initialization - ensure focus and mouse centering"""
        wx.CallAfter(self._postInitFocus)

    def _postInitFocus(self):
        """Delayed post-init focus handling"""
        ensure_window_focus_and_center_mouse(self)
        self.searchText.SetFocus()

    def getSearchText(self) -> str:
        """Get the entered search text"""
        return self.searchText.GetValue()

    def onOk(self, evt):
        """Handle OK action"""
        if not self.searchText.GetValue().strip():
            self.searchText.SetFocus()
            return
        self.EndModal(wx.ID_OK)


def launch_locker_selector():
    """Launch the locker selector GUI with proper isolation from other GUI frameworks"""

    # Store the current foreground window to restore focus later
    current_window = ctypes.windll.user32.GetForegroundWindow()

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

        # Create main dialog
        dlg = LockerSelectorGUI()

        try:
            # Ensure proper focus and mouse centering
            ensure_window_focus_and_center_mouse(dlg)

            # Show modal dialog
            result = dlg.ShowModal()

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
        # Use error handling
        error = DisplayableError(
            f"Error launching locker selector: {str(e)}",
            "Application Error"
        )
        error.displayError()
        logger.error(f"Error launching locker selector: {e}")
        speaker.speak("Error opening locker selector")

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
