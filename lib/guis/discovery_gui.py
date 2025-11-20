"""
Discovery GUI for FA11y
Provides interface for browsing Fortnite Creative islands and gamemodes
"""
import logging
import wx
import threading
import pyperclip
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import (
    AccessibleDialog, BoxSizerHelper, ButtonHelper,
    messageBox, BORDER_FOR_DIALOGS
)

logger = logging.getLogger(__name__)
speaker = Auto()


class DiscoveryDialog(AccessibleDialog):
    """Dialog for browsing Fortnite Creative islands"""

    def __init__(self, parent, discovery_api):
        super().__init__(parent, title="Discovery GUI", helpId="DiscoveryGUI")
        self.discovery_api = discovery_api
        self._is_destroying = False  # Flag to track if dialog is being destroyed
        self.setupDialog()
        self.SetSize((800, 600))
        self.CentreOnParent()

        # Type-to-search state
        self.type_search_buffer = ""
        self.type_search_timer = None

        # Bind Escape key to close dialog
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)
        # Bind close event to mark destruction
        self.Bind(wx.EVT_CLOSE, self.on_close)

    def makeSettings(self, sizer: BoxSizerHelper):
        """Create dialog content"""

        # Create notebook for tabs
        self.notebook = wx.Notebook(self)
        sizer.addItem(self.notebook, flag=wx.EXPAND, proportion=1)

        # Create tabs
        self.browse_panel = self._create_browse_panel()
        self.search_panel = self._create_search_panel()
        self.bycode_panel = self._create_bycode_panel()

        self.notebook.AddPage(self.browse_panel, "Browse")
        self.notebook.AddPage(self.search_panel, "Search")
        self.notebook.AddPage(self.bycode_panel, "By Code")

        # Bind tab change event
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_changed)

    def _create_browse_panel(self):
        """Create Browse tab"""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Title
        title = wx.StaticText(panel, label="Browse Creative Islands")
        title_font = title.GetFont()
        title_font.PointSize += 2
        title_font = title_font.Bold()
        title.SetFont(title_font)
        sizer.Add(title, 0, wx.ALL, 10)

        # Island list
        self.browse_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        sizer.Add(self.browse_list, 1, wx.EXPAND | wx.ALL, 5)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.copy_code_btn = wx.Button(panel, label="Copy Code")
        self.refresh_browse_btn = wx.Button(panel, label="Refresh")
        btn_sizer.Add(self.copy_code_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.refresh_browse_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER, 5)

        # Bind events
        self.copy_code_btn.Bind(wx.EVT_BUTTON, self.on_copy_code_browse)
        self.refresh_browse_btn.Bind(wx.EVT_BUTTON, self.on_refresh_browse)
        self.browse_list.Bind(wx.EVT_KEY_DOWN, self.on_browse_key_down)
        self.browse_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_copy_code_browse)

        panel.SetSizer(sizer)

        # Set initial loading message
        loading_msg = "Loading... (switch to this tab to load data)"
        self.browse_list.Append(loading_msg)

        return panel

    def _create_search_panel(self):
        """Create Search tab"""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Title
        title = wx.StaticText(panel, label="Search for Islands")
        title_font = title.GetFont()
        title_font.PointSize += 2
        title_font = title_font.Bold()
        title.SetFont(title_font)
        sizer.Add(title, 0, wx.ALL, 10)

        # Search box
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_label = wx.StaticText(panel, label="Search:")
        search_sizer.Add(search_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        self.search_box = wx.TextCtrl(panel, size=(300, -1), style=wx.TE_PROCESS_ENTER)
        self.search_box.Bind(wx.EVT_TEXT_ENTER, self.on_search_enter)
        search_sizer.Add(self.search_box, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        search_btn = wx.Button(panel, label="Search")
        search_btn.Bind(wx.EVT_BUTTON, self.on_search_click)
        search_sizer.Add(search_btn, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        sizer.Add(search_sizer, 0, wx.EXPAND)

        # Results list
        self.search_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        sizer.Add(self.search_list, 1, wx.EXPAND | wx.ALL, 5)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.copy_code_search_btn = wx.Button(panel, label="Copy Code")
        btn_sizer.Add(self.copy_code_search_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER, 5)

        # Bind events
        self.copy_code_search_btn.Bind(wx.EVT_BUTTON, self.on_copy_code_search)
        self.search_list.Bind(wx.EVT_KEY_DOWN, self.on_search_key_down)
        self.search_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_copy_code_search)

        panel.SetSizer(sizer)
        return panel

    def _create_bycode_panel(self):
        """Create By Code tab"""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Title
        title = wx.StaticText(panel, label="Lookup Island by Code")
        title_font = title.GetFont()
        title_font.PointSize += 2
        title_font = title_font.Bold()
        title.SetFont(title_font)
        sizer.Add(title, 0, wx.ALL, 10)

        # Code input
        code_sizer = wx.BoxSizer(wx.HORIZONTAL)
        code_label = wx.StaticText(panel, label="Island Code:")
        code_sizer.Add(code_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        self.code_box = wx.TextCtrl(panel, size=(200, -1), style=wx.TE_PROCESS_ENTER)
        self.code_box.Bind(wx.EVT_TEXT_ENTER, self.on_lookup_code)
        code_sizer.Add(self.code_box, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        lookup_btn = wx.Button(panel, label="Lookup")
        lookup_btn.Bind(wx.EVT_BUTTON, self.on_lookup_code)
        code_sizer.Add(lookup_btn, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        sizer.Add(code_sizer, 0, wx.EXPAND)

        # Island info display
        self.island_info_text = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(-1, 400)
        )
        font = self.island_info_text.GetFont()
        font.PointSize += 1
        self.island_info_text.SetFont(font)
        sizer.Add(self.island_info_text, 1, wx.ALL | wx.EXPAND, 10)

        panel.SetSizer(sizer)
        return panel

    def on_tab_changed(self, event):
        """Handle tab change - load data asynchronously"""
        page = event.GetSelection()

        def _load_task():
            if page == 0:  # Browse
                wx.CallAfter(self.load_browse_islands)
            # Search and By Code tabs don't need initial loading

        # Run load in background thread
        threading.Thread(target=_load_task, daemon=True).start()

    def load_browse_islands(self, event=None):
        """Load popular islands from fortnite.gg"""
        # Check if dialog is being destroyed or widget is invalid
        if self._is_destroying or not self.browse_list or not hasattr(self.browse_list, 'Clear'):
            return

        # Additional safety check
        try:
            self.browse_list.GetCount()
        except RuntimeError:
            return

        self.browse_list.Clear()
        self.browse_list.Append("Loading islands from fortnite.gg...")

        speaker.speak("Loading islands")

        def _load():
            # Scrape fortnite.gg for the most popular islands
            islands = self.discovery_api.scrape_fortnite_gg(search_query="", limit=50)
            if islands:
                wx.CallAfter(self._populate_browse_list, islands)
            else:
                wx.CallAfter(self._show_browse_error)

        threading.Thread(target=_load, daemon=True).start()

    def _populate_browse_list(self, islands):
        """Populate browse list with islands"""
        if self._is_destroying or not self.browse_list:
            return

        try:
            self.browse_list.GetCount()
        except RuntimeError:
            return

        self.browse_list.Clear()

        if not islands:
            self.browse_list.Append("No islands found")
            speaker.speak("No islands found")
            return

        for island in islands:
            creator = island.creator_name if island.creator_name else "Unknown"
            # Include player count if available
            if island.global_ccu >= 0:
                label = f"{island.title} ({island.global_ccu} playing) - {island.link_code}"
            else:
                label = f"{island.title} by {creator} - {island.link_code}"
            self.browse_list.Append(label, island)

        if islands:
            self.browse_list.SetSelection(0)
            speaker.speak(f"{len(islands)} islands loaded")

    def _show_browse_error(self):
        """Show error message in browse list"""
        if self._is_destroying or not self.browse_list:
            return

        try:
            self.browse_list.GetCount()
        except RuntimeError:
            return

        self.browse_list.Clear()
        self.browse_list.Append("Error loading islands. Please try refreshing.")
        speaker.speak("Error loading islands")

    def on_refresh_browse(self, event):
        """Refresh browse list"""
        self.load_browse_islands()

    def on_search_enter(self, event):
        """Handle Enter key in search box"""
        self.perform_search()

    def on_search_click(self, event):
        """Handle search button click"""
        self.perform_search()

    def perform_search(self):
        """Perform island search"""
        query = self.search_box.GetValue().strip()

        if not query:
            speaker.speak("Please enter a search term")
            return

        self.search_list.Clear()
        self.search_list.Append(f"Searching fortnite.gg for '{query}'...")
        speaker.speak(f"Searching for {query}")

        def _search():
            # Use fortnite.gg scraper for search
            islands = self.discovery_api.scrape_fortnite_gg(search_query=query, limit=50)
            wx.CallAfter(self._populate_search_list, islands, query)

        threading.Thread(target=_search, daemon=True).start()

    def _populate_search_list(self, islands, query):
        """Populate search list with results"""
        if self._is_destroying or not self.search_list:
            return

        try:
            self.search_list.GetCount()
        except RuntimeError:
            return

        self.search_list.Clear()

        if not islands:
            self.search_list.Append(f"No islands found matching '{query}'")
            speaker.speak(f"No results for {query}")
            return

        for island in islands:
            creator = island.creator_name if island.creator_name else "Unknown"
            label = f"{island.title} by {creator} - {island.link_code}"
            self.search_list.Append(label, island)

        if islands:
            self.search_list.SetSelection(0)
            speaker.speak(f"{len(islands)} islands found")

    def on_lookup_code(self, event):
        """Lookup island by code"""
        code = self.code_box.GetValue().strip()

        if not code:
            speaker.speak("Please enter an island code")
            return

        self.island_info_text.SetValue("Looking up island...")
        speaker.speak(f"Looking up code {code}")

        def _lookup():
            island = self.discovery_api.get_island_by_code(code)
            wx.CallAfter(self._show_island_info, island, code)

        threading.Thread(target=_lookup, daemon=True).start()

    def _show_island_info(self, island, code):
        """Show island information"""
        if self._is_destroying or not self.island_info_text:
            return

        if not island:
            self.island_info_text.SetValue(f"Island not found for code: {code}")
            speaker.speak("Island not found")
            return

        info_lines = []
        info_lines.append(f"Title: {island.title}")
        info_lines.append(f"Code: {island.link_code}")

        if island.creator_name:
            info_lines.append(f"Creator: {island.creator_name}")

        if island.description:
            info_lines.append(f"\nDescription: {island.description}")

        if island.global_ccu >= 0:
            info_lines.append(f"\nPlayers: {island.global_ccu}")

        self.island_info_text.SetValue("\n".join(info_lines))
        self.island_info_text.SetInsertionPoint(0)
        speaker.speak(f"Found: {island.title}")

    def on_copy_code_browse(self, event):
        """Copy island code from browse list"""
        sel = self.browse_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No island selected")
            return

        island = self.browse_list.GetClientData(sel)
        if island and hasattr(island, 'link_code'):
            pyperclip.copy(island.link_code)
            speaker.speak(f"Copied code: {island.link_code}")
        else:
            speaker.speak("No code available")

    def on_copy_code_search(self, event):
        """Copy island code from search list"""
        sel = self.search_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No island selected")
            return

        island = self.search_list.GetClientData(sel)
        if island and hasattr(island, 'link_code'):
            pyperclip.copy(island.link_code)
            speaker.speak(f"Copied code: {island.link_code}")
        else:
            speaker.speak("No code available")

    def on_browse_key_down(self, event):
        """Handle key press in browse list"""
        keycode = event.GetKeyCode()

        # Arrow key handling with wrapping
        if keycode == wx.WXK_UP:
            sel = self.browse_list.GetSelection()
            if sel == 0 or sel == wx.NOT_FOUND:
                last = self.browse_list.GetCount() - 1
                if last >= 0:
                    self.browse_list.SetSelection(last)
            else:
                self.browse_list.SetSelection(sel - 1)
            return

        elif keycode == wx.WXK_DOWN:
            sel = self.browse_list.GetSelection()
            last = self.browse_list.GetCount() - 1
            if sel == last or sel == wx.NOT_FOUND:
                self.browse_list.SetSelection(0)
            else:
                self.browse_list.SetSelection(sel + 1)
            return

        elif keycode == wx.WXK_LEFT or keycode == wx.WXK_RIGHT:
            return

        # Enter key copies code
        elif keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            self.on_copy_code_browse(event)
            return

        event.Skip()

    def on_search_key_down(self, event):
        """Handle key press in search list"""
        keycode = event.GetKeyCode()

        # Arrow key handling with wrapping
        if keycode == wx.WXK_UP:
            sel = self.search_list.GetSelection()
            if sel == 0 or sel == wx.NOT_FOUND:
                last = self.search_list.GetCount() - 1
                if last >= 0:
                    self.search_list.SetSelection(last)
            else:
                self.search_list.SetSelection(sel - 1)
            return

        elif keycode == wx.WXK_DOWN:
            sel = self.search_list.GetSelection()
            last = self.search_list.GetCount() - 1
            if sel == last or sel == wx.NOT_FOUND:
                self.search_list.SetSelection(0)
            else:
                self.search_list.SetSelection(sel + 1)
            return

        elif keycode == wx.WXK_LEFT or keycode == wx.WXK_RIGHT:
            return

        # Enter key copies code
        elif keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            self.on_copy_code_search(event)
            return

        event.Skip()

    def on_close(self, event):
        """Handle dialog close event"""
        self._is_destroying = True
        event.Skip()

    def on_char_hook(self, event):
        """Handle key press for dialog (Escape to close)"""
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_ESCAPE:
            self._is_destroying = True
            self.EndModal(wx.ID_CANCEL)
            wx.CallAfter(self._return_focus_to_game)
        else:
            event.Skip()

    def _return_focus_to_game(self):
        """Return focus to Fortnite using window management"""
        try:
            from lib.utilities.window_utils import focus_window

            # Try to focus Fortnite window directly
            if focus_window("Fortnite"):
                logger.debug("Focused Fortnite window")
            else:
                logger.debug("Could not find Fortnite window to focus")

        except Exception as e:
            logger.debug(f"Could not return focus to game: {e}")


def show_discovery_gui(discovery_api):
    """Show the discovery GUI"""
    try:
        # Get or create wx App
        app = wx.GetApp()
        if app is None:
            app = wx.App(False)

        dialog = DiscoveryDialog(None, discovery_api)

        # Focus window and center mouse
        try:
            from lib.guis.gui_utilities import ensure_window_focus_and_center_mouse
            ensure_window_focus_and_center_mouse(dialog)
        except Exception as e:
            logger.debug(f"Could not focus window: {e}")

        dialog.ShowModal()
        dialog.Destroy()

        # Return focus to Fortnite after closing
        try:
            from lib.utilities.window_utils import focus_window
            focus_window("Fortnite")
        except Exception as e:
            logger.debug(f"Could not return focus to game: {e}")
    except Exception as e:
        logger.error(f"Error showing discovery GUI: {e}")
        speaker.speak("Error opening discovery GUI")
