"""
Locker GUI for FA11y
Provides an interface to equip cosmetic items in the Fortnite locker
"""
import os
import sys
import time
import logging
import gc
from typing import Optional

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


class LockerGUI(AccessibleDialog):
    """Locker selector GUI for equipping cosmetic items"""

    # Coordinates for each locker slot
    LOCKER_SLOTS = {
        'Outfit': (260, 400),
        'Backbling': (420, 400),
        'Pickaxe': (570, 400),
        'Glider': (720, 400),
        'Kicks': (260, 560),
        'Contrail': (420, 560)
    }

    def __init__(self, parent=None):
        super().__init__(parent, title="Locker Selector", helpId="LockerSelector")

        # Button tracking for navigation
        self.current_buttons = []
        self.current_button_index = 0

        # Setup dialog
        self.setupDialog()

    def makeSettings(self, settingsSizer: BoxSizerHelper):
        """Create dialog content"""

        # Add title label
        titleLabel = wx.StaticText(
            self,
            label="Select a cosmetic slot to equip an item",
        )
        font = titleLabel.GetFont()
        font.PointSize += 1
        font = font.Bold()
        titleLabel.SetFont(font)
        settingsSizer.addItem(titleLabel)

        # Add buttons for each locker slot
        for slot_name in self.LOCKER_SLOTS.keys():
            button = wx.Button(self, label=slot_name)
            button.Bind(wx.EVT_BUTTON, lambda evt, slot=slot_name: self.onSelectSlot(evt, slot))
            button.Bind(wx.EVT_CHAR_HOOK, self.onButtonCharHook)
            settingsSizer.addItem(button)
            self.current_buttons.append(button)

        # Bind key events
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)

    def onButtonCharHook(self, event):
        """Handle char events for buttons to implement custom navigation"""
        key_code = event.GetKeyCode()

        # TAB for navigation between areas
        if key_code == wx.WXK_TAB:
            event.Skip()
            return

        # Arrow keys for button navigation
        elif key_code == wx.WXK_UP:
            self.navigate_buttons(-1)
        elif key_code == wx.WXK_DOWN:
            self.navigate_buttons(1)

        # Enter to activate button
        elif key_code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            focused = self.FindFocus()
            if isinstance(focused, wx.Button):
                event = wx.CommandEvent(wx.wxEVT_BUTTON)
                event.SetEventObject(focused)
                focused.GetEventHandler().ProcessEvent(event)

        else:
            event.Skip()

    def navigate_buttons(self, direction: int):
        """Navigate through buttons with arrow keys"""
        focused = self.FindFocus()

        if isinstance(focused, wx.Button) and focused in self.current_buttons:
            current_index = self.current_buttons.index(focused)
            new_index = (current_index + direction) % len(self.current_buttons)
            self.current_buttons[new_index].SetFocus()
        elif self.current_buttons:
            self.current_buttons[0].SetFocus()

    def onSelectSlot(self, evt, slot_name: str):
        """Handle locker slot button click"""
        try:
            dlg = SearchDialog(self, slot_name)

            # Ensure search dialog gets proper focus and mouse centering
            wx.CallAfter(lambda: ensure_window_focus_and_center_mouse(dlg))

            if dlg.ShowModal() == wx.ID_OK:
                item_name = dlg.getSearchText()
                if item_name.strip():
                    dlg.Destroy()
                    self.EndModal(wx.ID_OK)

                    # Perform locker item equip
                    success = self.equip_item(slot_name, item_name)
                    if success:
                        speaker.speak(f"{item_name} equipped!")
                    else:
                        speaker.speak("Failed to equip item. Please try again.")
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

    def equip_item(self, slot_name: str, item_name: str) -> bool:
        """Equip a cosmetic item by automating UI interactions"""
        try:
            # Get coordinates for the selected slot
            slot_coords = self.LOCKER_SLOTS.get(slot_name)
            if not slot_coords:
                logger.error(f"Unknown slot: {slot_name}")
                return False

            # Click initial position
            pyautogui.moveTo(420, 69, duration=0.05)
            pyautogui.click()
            time.sleep(0.3)

            # Click the specific slot
            pyautogui.moveTo(slot_coords[0], slot_coords[1], duration=0.05)
            pyautogui.click()
            time.sleep(1.0)

            # Click search bar
            pyautogui.moveTo(1030, 210, duration=0.05)
            pyautogui.click()
            time.sleep(0.5)

            # Type the item name
            pyautogui.typewrite(item_name)
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
            label=f"Enter the name of the {self.slot_name.lower()} to equip:",
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
    import ctypes
    import ctypes.wintypes
    import gc

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
        dlg = LockerGUI()

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
