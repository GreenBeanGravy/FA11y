"""
Gamemode selector GUI for FA11y
Provides interface to select/play saved gamemodes with quick search
"""
import os
import sys
import time
import logging
import gc
from typing import List, Tuple, Optional

import wx
import pyautogui
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import (
    AccessibleDialog, BoxSizerHelper, ButtonHelper,
    messageBox, force_focus_window, ensure_window_focus_and_center_mouse,
    center_mouse_in_window, BORDER_FOR_DIALOGS
)
from lib.utilities.window_utils import focus_fortnite
from lib.managers.screenshot_manager import capture_coordinates

# Initialize logger
logger = logging.getLogger(__name__)

# Constants
GAMEMODES_FOLDER = "gamemodes"

# Global speaker instance
speaker = Auto()


def safe_speak(text: str):
    """
    Safely speak text, catching COM errors that can occur with SAPI5

    Args:
        text: Text to speak
    """
    try:
        speaker.speak(text)
    except Exception as e:
        # Log the error but don't crash
        logger.debug(f"TTS error (non-critical): {e}")


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

        # Load saved gamemodes
        self.gamemodes = self.load_gamemodes()

        # Type-to-search state
        self.type_search_buffer = ""
        self.type_search_timer = None

        # Setup dialog
        self.setupDialog()
        self.SetSize((600, 500))

    def makeSettings(self, settingsSizer: BoxSizerHelper):
        """Create dialog content"""

        # Quick search button
        search_btn = wx.Button(self, label="Quick Search Gamemode")
        search_btn.Bind(wx.EVT_BUTTON, self.on_quick_search)
        settingsSizer.addItem(search_btn, flag=wx.EXPAND | wx.ALL, border=5)

        # Saved gamemodes
        if self.gamemodes:
            saved_label = wx.StaticText(self, label="Saved Gamemodes:")
            settingsSizer.addItem(saved_label, flag=wx.ALL, border=5)

            # List of gamemode buttons
            for gamemode in self.gamemodes:
                btn = wx.Button(self, label=gamemode[0])
                btn.Bind(wx.EVT_BUTTON, lambda evt, gm=gamemode: self.on_select_gamemode(evt, gm))
                settingsSizer.addItem(btn, flag=wx.EXPAND | wx.ALL, border=5)
        else:
            no_modes_text = wx.StaticText(self, label="No saved gamemodes found")
            settingsSizer.addItem(no_modes_text, flag=wx.ALL, border=5)

        # Bind key events
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)

    def on_quick_search(self, event):
        """Quick search in simple mode"""
        dlg = wx.TextEntryDialog(
            self,
            "Enter gamemode code or search term:",
            "Quick Search"
        )

        if dlg.ShowModal() == wx.ID_OK:
            text = dlg.GetValue().strip()
            dlg.Destroy()

            if text:
                self.EndModal(wx.ID_OK)
                success, error = self.select_gamemode_by_code(text)
                if success:
                    safe_speak(f"{text} selected!")
                else:
                    safe_speak(f"Failed to select gamemode: {error}")
        else:
            dlg.Destroy()

    def on_select_gamemode(self, evt, gamemode: Tuple[str, str, List[str]]):
        """Handle saved gamemode selection"""
        try:
            self.EndModal(wx.ID_OK)
            success, error = self.select_gamemode_by_code(gamemode[1])
            if success:
                safe_speak(f"{gamemode[0]} selected!")
            else:
                safe_speak(f"Failed to select gamemode: {error}")
        except Exception as e:
            logger.error(f"Error selecting gamemode: {e}")
            safe_speak(f"Failed to select gamemode: {e}")

    def load_gamemodes(self) -> List[Tuple[str, str, List[str]]]:
        """Load saved gamemode configurations"""
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

    def select_gamemode_by_code(self, code: str) -> tuple:
        """
        Select gamemode using automation

        Returns:
            tuple: (success: bool, error_message: str or None)
        """
        try:
            # Ensure Fortnite stays in focus
            if not focus_fortnite():
                logger.error("Could not focus Fortnite window")
                return (False, "Could not focus Fortnite window")
            time.sleep(0.3)

            # Click initial position to open discovery
            pyautogui.moveTo(69, 69, duration=0.04)
            pyautogui.click()
            time.sleep(0.5)

            # Move mouse to scroll position
            pyautogui.moveTo(950, 470, duration=0.04)
            time.sleep(0.1)

            # Scroll down once
            pyautogui.scroll(-3)
            time.sleep(0.2)

            # Scroll down again
            pyautogui.scroll(-3)
            time.sleep(1.1)  # Wait extra second for UI to settle

            # Click to open search
            pyautogui.moveTo(160, 170, duration=0.04)
            pyautogui.click()
            time.sleep(0.1)

            # Type the gamemode code
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.1)
            pyautogui.typewrite(code)
            time.sleep(1.0)  # Wait an extra second before pressing enter
            pyautogui.press('enter')

            # Wait for search results - check if pixel 84,335 is white (255,255,255)
            # Using FA11y's built-in screen capture instead of pyautogui
            def check_pixel_white(x, y):
                """Check if pixel at (x, y) is white using FA11y screen capture"""
                pixel = capture_coordinates(x, y, 1, 1, 'rgb')
                if pixel is not None and pixel.shape[0] > 0 and pixel.shape[1] > 0:
                    color = tuple(pixel[0, 0])
                    print(f"Pixel at ({x}, {y}): {color}")
                    return color == (255, 255, 255)
                print(f"Pixel at ({x}, {y}): None (capture failed)")
                return False

            start_time = time.time()
            while not check_pixel_white(84, 335):
                if time.time() - start_time > 5:
                    logger.error("Timeout waiting for search results")
                    pyautogui.scroll(3)
                    time.sleep(0.2)
                    pyautogui.scroll(3)
                    time.sleep(0.2)
                    pyautogui.scroll(3)
                    time.sleep(0.2)
                    pyautogui.scroll(3)
                    return (False, "Search results not found - gamemode may not exist or something else broke")
                time.sleep(0.1)
            time.sleep(0.1)

            # Click the gamemode result
            pyautogui.moveTo(192, 493, duration=0.04)
            pyautogui.click()
            time.sleep(0.7)

            # Click to confirm/select
            pyautogui.moveTo(235, 923, duration=0.04)
            pyautogui.click()
            time.sleep(0.5)

            return (True, None)

        except Exception as e:
            logger.error(f"Error selecting gamemode: {e}")
            return (False, f"Automation error: {e}")

    def onKeyEvent(self, event):
        """Handle key events"""
        key_code = event.GetKeyCode()

        if key_code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return

        event.Skip()

    def postInit(self):
        """Post-initialization"""
        wx.CallAfter(self._postInitFocus)

    def _postInitFocus(self):
        """Delayed focus handling"""
        ensure_window_focus_and_center_mouse(self)


def launch_gamemode_selector():
    """Launch gamemode selector"""
    import ctypes
    import ctypes.wintypes
    import gc

    current_window = ctypes.windll.user32.GetForegroundWindow()

    app = None
    app_created = False

    try:
        existing_app = wx.GetApp()
        if existing_app is None:
            app = wx.App(False)
            app_created = True
        else:
            app = existing_app
            app_created = False

        dlg = GamemodeGUI()

        try:
            ensure_window_focus_and_center_mouse(dlg)
            result = dlg.ShowModal()

        finally:
            if dlg:
                dlg.Destroy()

            if app:
                app.ProcessPendingEvents()
                while app.HasPendingEvents():
                    app.Yield()

    except Exception as e:
        error = DisplayableError(
            f"Error launching gamemode selector: {str(e)}",
            "Application Error"
        )
        error.displayError()
        logger.error(f"Error launching gamemode selector: {e}")
        safe_speak("Error opening gamemode selector")

    finally:
        try:
            gc.collect()

            try:
                ctypes.windll.user32.SetFocus(0)

                if ctypes.windll.user32.OpenClipboard(0):
                    ctypes.windll.user32.EmptyClipboard()
                    ctypes.windll.user32.CloseClipboard()

            except:
                pass

            if current_window:
                try:
                    ctypes.windll.user32.SetForegroundWindow(current_window)
                    ctypes.windll.user32.SetFocus(current_window)
                except:
                    pass

            time.sleep(0.2)
            gc.collect()

            try:
                import tkinter as tk
                if hasattr(tk, '_default_root') and tk._default_root is not None:
                    try:
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
