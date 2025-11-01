"""
Gamemode selector GUI for FA11y
Provides an interface to select and play different gamemodes, and search for custom ones
"""
import os
import sys
import time
import logging
import gc
from typing import List, Tuple

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

# Constants
GAMEMODES_FOLDER = "gamemodes"

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


class GamemodeGUI(AccessibleDialog):
    """Gamemode selector GUI"""
    
    def __init__(self, parent=None):
        super().__init__(parent, title="Gamemode Selector", helpId="GamemodeSelector")
        
        # Load gamemodes
        self.gamemodes = self.load_gamemodes()
        
        # Button tracking for navigation
        self.current_buttons = []
        self.current_button_index = 0
        
        # Setup dialog
        self.setupDialog()
    
    def makeSettings(self, settingsSizer: BoxSizerHelper):
        """Create dialog content"""
        
        # Search button at top
        searchButton = wx.Button(self, label="Search Custom Gamemode")
        searchButton.Bind(wx.EVT_BUTTON, self.onSearchGamemode)
        searchButton.Bind(wx.EVT_CHAR_HOOK, self.onButtonCharHook)
        settingsSizer.addItem(searchButton)
        
        # Add gamemode buttons
        for gamemode in self.gamemodes:
            button = wx.Button(self, label=gamemode[0])
            button.Bind(wx.EVT_BUTTON, lambda evt, gm=gamemode: self.onSelectGamemode(evt, gm))
            button.Bind(wx.EVT_CHAR_HOOK, self.onButtonCharHook)
            settingsSizer.addItem(button)
        
        # Show message if no gamemodes found
        if not self.gamemodes:
            noModesText = wx.StaticText(self, label="No gamemodes found in gamemodes folder")
            settingsSizer.addItem(noModesText)
        
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
            return
        elif key_code == wx.WXK_DOWN:
            self.navigate_buttons(1)
            return
        
        # Allow other keys (Enter, Space, etc.)
        event.Skip()
    
    def navigate_buttons(self, direction):
        """Navigate between buttons"""
        if not self.current_buttons:
            return
        
        self.current_button_index = (self.current_button_index + direction) % len(self.current_buttons)
        self.current_buttons[self.current_button_index].SetFocus()
        
        # NVDA will announce the button automatically - no need for explicit speech
    
    def update_current_buttons(self):
        """Update list of buttons"""
        self.current_buttons = []
        for child in self.GetChildren():
            if isinstance(child, wx.Button):
                self.current_buttons.append(child)
        self.current_button_index = 0
    
    def postInit(self):
        """Post-initialization setup"""
        wx.CallAfter(self._postInitFocus)
    
    def _postInitFocus(self):
        """Delayed post-init focus handling"""
        ensure_window_focus_and_center_mouse(self)
        
        # Update button tracking and focus first button
        self.update_current_buttons()
        if self.current_buttons:
            self.current_button_index = 0
            self.current_buttons[0].SetFocus()
            # NVDA will announce the button automatically - no need for explicit speech
    
    def load_gamemodes(self) -> List[Tuple[str, str, List[str]]]:
        """Load gamemode configurations from the gamemodes folder"""
        gamemodes = []
        
        if not os.path.exists(GAMEMODES_FOLDER):
            os.makedirs(GAMEMODES_FOLDER, exist_ok=True)
            return gamemodes
        
        try:
            files = os.listdir(GAMEMODES_FOLDER)
            for filename in files:
                if filename.endswith(".txt"):
                    try:
                        file_path = os.path.join(GAMEMODES_FOLDER, filename)
                        with open(file_path, 'r', encoding='utf-8') as file:
                            lines = file.readlines()
                            if len(lines) >= 2:
                                gamemode_name = filename[:-4]
                                gamemode_text = lines[0].strip()
                                team_sizes = lines[1].strip().split(',')
                                gamemodes.append((gamemode_name, gamemode_text, team_sizes))
                    except Exception as e:
                        logger.error(f"Error reading {filename}: {e}")
        except Exception as e:
            logger.error(f"Error accessing gamemodes directory: {e}")
        
        return gamemodes
    
    def onSearchGamemode(self, evt):
        """Handle search button click"""
        try:
            dlg = SearchDialog(self)
            
            # Ensure search dialog gets proper focus and mouse centering
            wx.CallAfter(lambda: ensure_window_focus_and_center_mouse(dlg))
            
            if dlg.ShowModal() == wx.ID_OK:
                text = dlg.getSearchText()
                if text.strip():
                    dlg.Destroy()
                    self.EndModal(wx.ID_OK)
                    
                    # Perform gamemode selection
                    custom_gamemode = (text, text, [])
                    success = self.select_gamemode(custom_gamemode)
                    if success:
                        speaker.speak(f"{text} selected, Press 'P' to ready up!")
                    else:
                        speaker.speak("Failed to select gamemode. Please try again.")
                else:
                    dlg.Destroy()
            else:
                dlg.Destroy()
        except Exception as e:
            error = DisplayableError(
                f"Error opening search dialog: {str(e)}",
                "Gamemode Selection Error"
            )
            error.displayError(self)
    
    def onSelectGamemode(self, evt, gamemode: Tuple[str, str, List[str]]):
        """Handle gamemode button click"""
        try:
            self.EndModal(wx.ID_OK)
            success = self.select_gamemode(gamemode)
            if success:
                speaker.speak(f"{gamemode[0]} selected, Press 'P' to ready up!")
            else:
                speaker.speak("Failed to select gamemode. Please try again.")
        except Exception as e:
            error = DisplayableError(
                f"Error selecting gamemode: {str(e)}",
                "Gamemode Selection Error"
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
    
    def select_gamemode(self, gamemode: Tuple[str, str, List[str]]) -> bool:
        """Select a gamemode by automating UI interactions"""
        try:
            # Game automation sequence
            pyautogui.moveTo(109, 67, duration=0.04)
            pyautogui.click()
            time.sleep(0.5)
            
            pyautogui.moveTo(1280, 200, duration=0.04)
            pyautogui.click()
            time.sleep(0.1)
            
            # Clear search box and enter gamemode text
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.1)
            pyautogui.typewrite(gamemode[1])
            pyautogui.press('enter')

            # Wait for loading
            start_time = time.time()
            while not pyautogui.pixelMatchesColor(135, 401, (255, 255, 255)):
                if time.time() - start_time > 5:
                    return False
                time.sleep(0.1)
            time.sleep(0.1)

            # Select gamemode
            pyautogui.moveTo(257, 527, duration=0.04)
            pyautogui.click()
            time.sleep(0.7)
            pyautogui.moveTo(285, 910, duration=0.04)
            pyautogui.click()
            time.sleep(0.5)
            
            # Exit menus
            pyautogui.press('b', presses=2, interval=0.05)
            return True
            
        except Exception as e:
            logger.error(f"Error selecting gamemode: {e}")
            return False


class SearchDialog(AccessibleDialog):
    """Search dialog for custom gamemode input"""
    
    def __init__(self, parent):
        super().__init__(parent, title="Search Gamemode", helpId="GamemodeSearch")
        self.setupDialog()
    
    def makeSettings(self, settingsSizer: BoxSizerHelper):
        """Create search dialog content"""
        
        # Search text control
        self.searchText = settingsSizer.addLabeledControl(
            "Gamemode text:",
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
        
        # Allow TAB for navigation between areas
        if key_code == wx.WXK_TAB:
            event.Skip()
            return
        
        # Block up/down arrow keys from moving cursor, allow left/right
        if key_code in [wx.WXK_UP, wx.WXK_DOWN]:
            return  # Don't skip - block the event
        
        # Allow all other keys
        event.Skip()
    
    def onKeyEvent(self, event):
        """Handle key events"""
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_ESCAPE:
            if self.searchText.GetValue().strip():
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


def launch_gamemode_selector():
    """Launch the gamemode selector GUI with proper isolation from other GUI frameworks"""
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
        dlg = GamemodeGUI()
        
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
            f"Error launching gamemode selector: {str(e)}",
            "Application Error"
        )
        error.displayError()
        logger.error(f"Error launching gamemode selector: {e}")
        speaker.speak("Error opening gamemode selector")
    
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
                    
            except:
                pass
            
            # Restore original display state
            if current_window:
                try:
                    ctypes.windll.user32.SetForegroundWindow(current_window)
                    ctypes.windll.user32.SetFocus(current_window)
                except:
                    pass
            
            # Additional delay to ensure complete framework separation
            time.sleep(0.2)
            
            # Force additional garbage collection
            gc.collect()
            
            # Clear any cached tkinter state that might be corrupted
            # This helps tkinter reinitialize cleanly
            try:
                import tkinter as tk
                # Clear any existing tkinter application state
                if hasattr(tk, '_default_root') and tk._default_root is not None:
                    try:
                        # Don't destroy if it's still valid, just clear the reference
                        if tk._default_root.winfo_exists():
                            pass
                        else:
                            tk._default_root = None
                    except:
                        tk._default_root = None
            except:
                pass
            
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup: {cleanup_error}")