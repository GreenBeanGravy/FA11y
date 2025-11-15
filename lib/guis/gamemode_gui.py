"""
Gamemode selector GUI for FA11y - Revamped with Simple and Advanced Discovery modes
Provides interface to select/play gamemodes with Epic Discovery integration
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
        safe_speak(text)
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
    """Gamemode selector GUI with Simple and Advanced modes"""

    def __init__(self, parent=None, epic_auth=None):
        super().__init__(parent, title="Gamemode Selector", helpId="GamemodeSelector")

        # Store auth for advanced features
        self.epic_auth = epic_auth
        self.discovery_api = None

        # Initialize discovery API if auth available
        if self.epic_auth and self.epic_auth.access_token:
            try:
                from lib.utilities.epic_discovery import EpicDiscovery
                self.discovery_api = EpicDiscovery(self.epic_auth)
            except Exception as e:
                logger.warning(f"Failed to initialize discovery API: {e}")

        # Load saved gamemodes
        self.gamemodes = self.load_gamemodes()

        # Mode state
        self.simple_mode = True  # Start in simple mode

        # Setup dialog
        self.setupDialog()
        self.SetSize((900, 700))

    def makeSettings(self, settingsSizer: BoxSizerHelper):
        """Create dialog content"""

        # Mode toggle button at top
        mode_sizer = wx.BoxSizer(wx.HORIZONTAL)

        mode_label = wx.StaticText(self, label="Mode:")
        mode_sizer.Add(mode_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        self.simple_mode_btn = wx.RadioButton(self, label="Simple", style=wx.RB_GROUP)
        self.advanced_mode_btn = wx.RadioButton(self, label="Advanced")
        self.simple_mode_btn.SetValue(True)

        mode_sizer.Add(self.simple_mode_btn, 0, wx.ALL, 5)
        mode_sizer.Add(self.advanced_mode_btn, 0, wx.ALL, 5)

        settingsSizer.addItem(mode_sizer, flag=wx.ALIGN_LEFT)

        # Bind mode change events
        self.simple_mode_btn.Bind(wx.EVT_RADIOBUTTON, self.on_mode_changed)
        self.advanced_mode_btn.Bind(wx.EVT_RADIOBUTTON, self.on_mode_changed)

        # Create panels for both modes (will show/hide based on selection)
        self.simple_panel = self._create_simple_panel()
        self.advanced_panel = self._create_advanced_panel()

        settingsSizer.addItem(self.simple_panel, flag=wx.EXPAND, proportion=1)
        settingsSizer.addItem(self.advanced_panel, flag=wx.EXPAND, proportion=1)

        # Start with simple mode visible
        self.advanced_panel.Hide()

        # Bind key events
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)

    def _create_simple_panel(self):
        """Create simple mode panel"""
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Quick search button
        search_btn = wx.Button(panel, label="Quick Search Gamemode")
        search_btn.Bind(wx.EVT_BUTTON, self.on_quick_search)
        sizer.Add(search_btn, 0, wx.EXPAND | wx.ALL, 5)

        # Saved gamemodes
        if self.gamemodes:
            saved_label = wx.StaticText(panel, label="Saved Gamemodes:")
            sizer.Add(saved_label, 0, wx.ALL, 5)

            # List of gamemode buttons
            for gamemode in self.gamemodes:
                btn = wx.Button(panel, label=gamemode[0])
                btn.Bind(wx.EVT_BUTTON, lambda evt, gm=gamemode: self.on_select_gamemode(evt, gm))
                sizer.Add(btn, 0, wx.EXPAND | wx.ALL, 5)
        else:
            no_modes_text = wx.StaticText(panel, label="No saved gamemodes found")
            sizer.Add(no_modes_text, 0, wx.ALL, 5)

        panel.SetSizer(sizer)
        return panel

    def _create_advanced_panel(self):
        """Create advanced mode panel with discovery features"""
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        if not self.discovery_api:
            # Show auth required message
            auth_label = wx.StaticText(
                panel,
                label="Advanced features require Epic Games authentication.\nPlease log in to use Discovery features."
            )
            sizer.Add(auth_label, 0, wx.ALL, 10)
            panel.SetSizer(sizer)
            return panel

        # Create notebook for tabs
        self.notebook = wx.Notebook(panel)
        sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)

        # Create tabs
        self.discovery_panel = self._create_discovery_tab()
        self.search_panel = self._create_search_tab()
        self.creator_panel = self._create_creator_tab()

        self.notebook.AddPage(self.discovery_panel, "Discovery")
        self.notebook.AddPage(self.search_panel, "Search Islands")
        self.notebook.AddPage(self.creator_panel, "Search Creators")

        panel.SetSizer(sizer)
        return panel

    def _create_discovery_tab(self):
        """Create discovery surface tab"""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Surface selection
        surface_label = wx.StaticText(panel, label="Discovery Surface:")
        sizer.Add(surface_label, 0, wx.ALL, 5)

        from lib.utilities.epic_discovery import EpicDiscovery
        self.surface_choices = {
            "Main/Featured": EpicDiscovery.SURFACE_MAIN,
            "Browse": EpicDiscovery.SURFACE_BROWSE,
            "Library": EpicDiscovery.SURFACE_LIBRARY,
            "Rocket Racing": EpicDiscovery.SURFACE_ROCKET_RACING,
            "Epic's Page": EpicDiscovery.SURFACE_EPIC_PAGE,
        }

        self.surface_combo = wx.ComboBox(
            panel,
            choices=list(self.surface_choices.keys()),
            style=wx.CB_READONLY
        )
        self.surface_combo.SetSelection(0)
        sizer.Add(self.surface_combo, 0, wx.EXPAND | wx.ALL, 5)

        # Load button
        load_btn = wx.Button(panel, label="Load Surface")
        load_btn.Bind(wx.EVT_BUTTON, self.on_load_surface)
        sizer.Add(load_btn, 0, wx.EXPAND | wx.ALL, 5)

        # Results list
        self.discovery_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        sizer.Add(self.discovery_list, 1, wx.EXPAND | wx.ALL, 5)

        # Select button
        select_btn = wx.Button(panel, label="Select Island")
        select_btn.Bind(wx.EVT_BUTTON, self.on_select_discovery_island)
        sizer.Add(select_btn, 0, wx.EXPAND | wx.ALL, 5)

        panel.SetSizer(sizer)
        return panel

    def _create_search_tab(self):
        """Create island search tab"""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Search input
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_label = wx.StaticText(panel, label="Search:")
        search_sizer.Add(search_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        self.island_search_text = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.island_search_text.Bind(wx.EVT_TEXT_ENTER, self.on_search_islands)
        search_sizer.Add(self.island_search_text, 1, wx.EXPAND | wx.ALL, 5)

        search_btn = wx.Button(panel, label="Search")
        search_btn.Bind(wx.EVT_BUTTON, self.on_search_islands)
        search_sizer.Add(search_btn, 0, wx.ALL, 5)

        sizer.Add(search_sizer, 0, wx.EXPAND)

        # Sort options
        sort_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sort_label = wx.StaticText(panel, label="Sort by:")
        sort_sizer.Add(sort_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        self.sort_combo = wx.ComboBox(
            panel,
            choices=["Players (CCU)", "Score", "Recent"],
            style=wx.CB_READONLY
        )
        self.sort_combo.SetSelection(0)
        sort_sizer.Add(self.sort_combo, 0, wx.ALL, 5)

        sizer.Add(sort_sizer, 0, wx.EXPAND)

        # Results list
        self.island_search_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        sizer.Add(self.island_search_list, 1, wx.EXPAND | wx.ALL, 5)

        # Select button
        select_btn = wx.Button(panel, label="Select Island")
        select_btn.Bind(wx.EVT_BUTTON, self.on_select_search_island)
        sizer.Add(select_btn, 0, wx.EXPAND | wx.ALL, 5)

        panel.SetSizer(sizer)
        return panel

    def _create_creator_tab(self):
        """Create creator search tab"""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Search input
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_label = wx.StaticText(panel, label="Creator Name:")
        search_sizer.Add(search_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        self.creator_search_text = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.creator_search_text.Bind(wx.EVT_TEXT_ENTER, self.on_search_creators)
        search_sizer.Add(self.creator_search_text, 1, wx.EXPAND | wx.ALL, 5)

        search_btn = wx.Button(panel, label="Search")
        search_btn.Bind(wx.EVT_BUTTON, self.on_search_creators)
        search_sizer.Add(search_btn, 0, wx.ALL, 5)

        sizer.Add(search_sizer, 0, wx.EXPAND)

        # Results list
        self.creator_search_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        sizer.Add(self.creator_search_list, 1, wx.EXPAND | wx.ALL, 5)

        # Info label
        info_label = wx.StaticText(panel, label="Select a creator to view their islands")
        sizer.Add(info_label, 0, wx.ALL, 5)

        panel.SetSizer(sizer)
        return panel

    def on_mode_changed(self, event):
        """Handle mode change between Simple and Advanced"""
        if self.simple_mode_btn.GetValue():
            self.simple_panel.Show()
            self.advanced_panel.Hide()
            safe_speak("Simple mode")
        else:
            self.simple_panel.Hide()
            self.advanced_panel.Show()
            safe_speak("Advanced mode")

        self.Layout()

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
                success = self.select_gamemode_by_code(text)
                if success:
                    safe_speak(f"{text} selected. Press P to ready up!")
                else:
                    safe_speak("Failed to select gamemode")
        else:
            dlg.Destroy()

    def on_load_surface(self, event):
        """Load selected discovery surface"""
        if not self.discovery_api:
            safe_speak("Discovery API not available")
            return

        surface_name = self.surface_combo.GetStringSelection()
        surface_id = self.surface_choices.get(surface_name)

        if not surface_id:
            return

        safe_speak(f"Loading {surface_name}")
        self.discovery_list.Clear()

        try:
            data = self.discovery_api.get_discovery_surface(surface_id)

            if not data:
                safe_speak("Failed to load surface")
                return

            # Extract islands using the helper method
            islands = self.discovery_api.get_islands_from_surface(data)

            for island in islands:
                # Display title with creator name if available
                if island.creator_name:
                    display_name = f"{island.title} by {island.creator_name}"
                else:
                    display_name = island.title

                # Add player count if available
                if island.global_ccu >= 0:
                    display_name += f" ({island.global_ccu} players)"

                # Add favorite indicator
                if island.is_favorite:
                    display_name = f"★ {display_name}"

                # Store link_code as client data, display the title
                self.discovery_list.Append(display_name, island.link_code)

            if islands:
                safe_speak(f"Loaded {len(islands)} islands")
                self.discovery_list.SetSelection(0)
            else:
                safe_speak("No islands found")

        except Exception as e:
            logger.error(f"Error loading surface: {e}")
            safe_speak("Error loading surface")

    def on_search_islands(self, event):
        """Search for islands"""
        if not self.discovery_api:
            safe_speak("Discovery API not available")
            return

        query = self.island_search_text.GetValue().strip()
        if not query:
            safe_speak("Enter search query")
            return

        # Get sort option
        sort_map = {
            "Players (CCU)": "globalCCU",
            "Score": "score",
            "Recent": "lastVisited"
        }
        sort_by = sort_map.get(self.sort_combo.GetStringSelection(), "globalCCU")

        safe_speak(f"Searching for {query}")
        self.island_search_list.Clear()

        try:
            islands = self.discovery_api.search_islands(query, order_by=sort_by)

            if not islands:
                safe_speak("No results found")
                return

            for island in islands:
                # Display title with creator name if available
                if island.creator_name:
                    display_name = f"{island.title} by {island.creator_name}"
                else:
                    display_name = island.title

                # Add player count if available
                if island.global_ccu >= 0:
                    display_name += f" ({island.global_ccu} players)"

                # Add favorite indicator
                if island.is_favorite:
                    display_name = f"★ {display_name}"

                # Store link_code as client data, display the title
                self.island_search_list.Append(display_name, island.link_code)

            safe_speak(f"Found {len(islands)} islands")
            self.island_search_list.SetSelection(0)

        except Exception as e:
            logger.error(f"Error searching islands: {e}")
            safe_speak("Error searching islands")

    def on_search_creators(self, event):
        """Search for creators"""
        if not self.discovery_api:
            safe_speak("Discovery API not available")
            return

        query = self.creator_search_text.GetValue().strip()
        if not query:
            safe_speak("Enter creator name")
            return

        safe_speak(f"Searching for {query}")
        self.creator_search_list.Clear()

        try:
            creators = self.discovery_api.search_creators(query)

            if not creators:
                safe_speak("No creators found")
                return

            for creator in creators:
                label = f"{creator.account_id} (score: {creator.score:.2f})"
                self.creator_search_list.Append(label, creator.account_id)

            safe_speak(f"Found {len(creators)} creators")
            self.creator_search_list.SetSelection(0)

        except Exception as e:
            logger.error(f"Error searching creators: {e}")
            safe_speak("Error searching creators")

    def on_select_discovery_island(self, event):
        """Select island from discovery surface"""
        sel = self.discovery_list.GetSelection()
        if sel == wx.NOT_FOUND:
            safe_speak("No island selected")
            return

        link_code = self.discovery_list.GetClientData(sel)
        self.EndModal(wx.ID_OK)

        success = self.select_gamemode_by_code(link_code)
        if success:
            safe_speak(f"{link_code} selected. Press P to ready up!")
        else:
            safe_speak("Failed to select gamemode")

    def on_select_search_island(self, event):
        """Select island from search results"""
        sel = self.island_search_list.GetSelection()
        if sel == wx.NOT_FOUND:
            safe_speak("No island selected")
            return

        link_code = self.island_search_list.GetClientData(sel)
        self.EndModal(wx.ID_OK)

        success = self.select_gamemode_by_code(link_code)
        if success:
            safe_speak(f"{link_code} selected. Press P to ready up!")
        else:
            safe_speak("Failed to select gamemode")

    def on_select_gamemode(self, evt, gamemode: Tuple[str, str, List[str]]):
        """Handle saved gamemode selection"""
        try:
            self.EndModal(wx.ID_OK)
            success = self.select_gamemode_by_code(gamemode[1])
            if success:
                safe_speak(f"{gamemode[0]} selected. Press P to ready up!")
            else:
                safe_speak("Failed to select gamemode")
        except Exception as e:
            logger.error(f"Error selecting gamemode: {e}")
            safe_speak("Error selecting gamemode")

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

    def select_gamemode_by_code(self, code: str) -> bool:
        """Select gamemode using automation"""
        try:
            pyautogui.moveTo(109, 67, duration=0.04)
            pyautogui.click()
            time.sleep(0.5)

            pyautogui.moveTo(1280, 200, duration=0.04)
            pyautogui.click()
            time.sleep(0.1)

            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.1)
            pyautogui.typewrite(code)
            pyautogui.press('enter')

            start_time = time.time()
            while not pyautogui.pixelMatchesColor(135, 401, (255, 255, 255)):
                if time.time() - start_time > 5:
                    return False
                time.sleep(0.1)
            time.sleep(0.1)

            pyautogui.moveTo(257, 527, duration=0.04)
            pyautogui.click()
            time.sleep(0.7)
            pyautogui.moveTo(285, 910, duration=0.04)
            pyautogui.click()
            time.sleep(0.5)

            pyautogui.press('b', presses=2, interval=0.05)
            return True

        except Exception as e:
            logger.error(f"Error selecting gamemode: {e}")
            return False

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


def launch_gamemode_selector(epic_auth=None):
    """Launch gamemode selector with optional Epic auth for advanced features"""
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

        dlg = GamemodeGUI(epic_auth=epic_auth)

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
