"""
Discovery GUI for FA11y
Provides interface for browsing Fortnite Creative islands and gamemodes
"""
import logging
import time
import re
import wx
import threading
import pyperclip
import pyautogui
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import (
    AccessibleDialog, BoxSizerHelper, ButtonHelper,
    messageBox, BORDER_FOR_DIALOGS
)
from lib.utilities.window_utils import focus_fortnite
from lib.managers.screenshot_manager import capture_coordinates

logger = logging.getLogger(__name__)
speaker = Auto()


def is_standard_code_format(code: str) -> bool:
    """
    Check if code matches standard Fortnite island code format.
    
    Standard formats:
    - ####-####-#### (12 digits with dashes)
    - ############ (12 digits without dashes)
    
    Args:
        code: Island code to check
        
    Returns:
        True if code is in standard format, False otherwise
    """
    if not code:
        return False
    return bool(re.match(r'^\d{4}-\d{4}-\d{4}$', code) or re.match(r'^\d{12}$', code))


class DiscoveryDialog(AccessibleDialog):
    """Dialog for browsing Fortnite Creative islands"""

    # Sort filter options
    SORT_OPTIONS = [
        ("Popular", "popular"),
        ("Newest", "newest"),
        ("Most Players", "players"),
        ("A-Z", "alpha"),
    ]

    def __init__(self, parent, discovery_api):
        super().__init__(parent, title="Discovery GUI", helpId="DiscoveryGUI")
        self.discovery_api = discovery_api
        self._is_destroying = False  # Flag to track if dialog is being destroyed

        # Pagination state (for browse)
        self.current_page = 1
        self.items_per_page = 50
        self.total_items = 0

        # Search pagination state
        self.search_current_page = 1
        self.search_query = ""

        # Current sort filter
        self.current_sort = "popular"

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

        # Create tabs (Epic Gamemodes first as default)
        self.epic_panel = self._create_epic_gamemodes_panel()
        self.browse_panel = self._create_browse_panel()
        self.search_panel = self._create_search_panel()
        self.creator_panel = self._create_creator_panel()
        self.bycode_panel = self._create_bycode_panel()

        self.notebook.AddPage(self.epic_panel, "Epic Gamemodes")
        self.notebook.AddPage(self.browse_panel, "Browse")
        self.notebook.AddPage(self.search_panel, "Search")
        self.notebook.AddPage(self.creator_panel, "By Creator")
        self.notebook.AddPage(self.bycode_panel, "By Code")

        # Pre-load all tabs on startup
        wx.CallAfter(self._preload_all_tabs)

        # Bind tab change event
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_changed)

    def _create_epic_gamemodes_panel(self):
        """Create Epic Gamemodes tab - Epic Games creator maps from fortnite.gg"""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Title
        title = wx.StaticText(panel, label="Epic Games - Official Gamemodes")
        title_font = title.GetFont()
        title_font.PointSize += 2
        title_font = title_font.Bold()
        title.SetFont(title_font)
        sizer.Add(title, 0, wx.ALL, 10)

        # Epic gamemodes list
        self.epic_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        sizer.Add(self.epic_list, 1, wx.EXPAND | wx.ALL, 5)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.copy_epic_btn = wx.Button(panel, label="Copy Code")
        self.launch_epic_btn = wx.Button(panel, label="Launch Gamemode")
        self.refresh_epic_btn = wx.Button(panel, label="Refresh")
        btn_sizer.Add(self.copy_epic_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.launch_epic_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.refresh_epic_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER, 5)

        # Bind events
        self.copy_epic_btn.Bind(wx.EVT_BUTTON, self.on_copy_code_epic)
        self.launch_epic_btn.Bind(wx.EVT_BUTTON, self.on_launch_epic)
        self.refresh_epic_btn.Bind(wx.EVT_BUTTON, self.on_refresh_epic)
        self.epic_list.Bind(wx.EVT_KEY_DOWN, self.on_epic_key_down)
        self.epic_list.Bind(wx.EVT_CHAR, self.on_epic_char)
        self.epic_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_launch_epic)

        panel.SetSizer(sizer)

        # Set initial loading message
        self.epic_list.Append("Loading Epic Games gamemodes from fortnite.gg...")

        return panel

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

        # Sort filter
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sort_label = wx.StaticText(panel, label="Sort by:")
        filter_sizer.Add(sort_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        sort_choices = [opt[0] for opt in self.SORT_OPTIONS]
        self.browse_sort_choice = wx.Choice(panel, choices=sort_choices)
        self.browse_sort_choice.SetSelection(0)
        self.browse_sort_choice.Bind(wx.EVT_CHOICE, self.on_browse_sort_changed)
        filter_sizer.Add(self.browse_sort_choice, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        sizer.Add(filter_sizer, 0, wx.EXPAND)

        # Island list
        self.browse_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        sizer.Add(self.browse_list, 1, wx.EXPAND | wx.ALL, 5)

        # Pagination controls
        page_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.browse_prev_btn = wx.Button(panel, label="< Previous")
        self.browse_page_label = wx.StaticText(panel, label="Page 1")
        self.browse_next_btn = wx.Button(panel, label="Next >")
        page_sizer.Add(self.browse_prev_btn, 0, wx.ALL, 5)
        page_sizer.Add(self.browse_page_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        page_sizer.Add(self.browse_next_btn, 0, wx.ALL, 5)
        sizer.Add(page_sizer, 0, wx.ALIGN_CENTER, 5)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.copy_code_btn = wx.Button(panel, label="Copy Code")
        self.launch_browse_btn = wx.Button(panel, label="Launch Gamemode")
        self.refresh_browse_btn = wx.Button(panel, label="Refresh")
        btn_sizer.Add(self.copy_code_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.launch_browse_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.refresh_browse_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER, 5)

        # Bind events
        self.copy_code_btn.Bind(wx.EVT_BUTTON, self.on_copy_code_browse)
        self.launch_browse_btn.Bind(wx.EVT_BUTTON, self.on_launch_browse)
        self.refresh_browse_btn.Bind(wx.EVT_BUTTON, self.on_refresh_browse)
        self.browse_prev_btn.Bind(wx.EVT_BUTTON, self.on_browse_prev_page)
        self.browse_next_btn.Bind(wx.EVT_BUTTON, self.on_browse_next_page)
        self.browse_list.Bind(wx.EVT_KEY_DOWN, self.on_browse_key_down)
        self.browse_list.Bind(wx.EVT_CHAR, self.on_browse_char)
        self.browse_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_launch_browse)

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

        # Pagination controls
        search_page_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.search_prev_btn = wx.Button(panel, label="< Previous")
        self.search_page_label = wx.StaticText(panel, label="Page 1")
        self.search_next_btn = wx.Button(panel, label="Next >")
        search_page_sizer.Add(self.search_prev_btn, 0, wx.ALL, 5)
        search_page_sizer.Add(self.search_page_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        search_page_sizer.Add(self.search_next_btn, 0, wx.ALL, 5)
        sizer.Add(search_page_sizer, 0, wx.ALIGN_CENTER, 5)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.copy_code_search_btn = wx.Button(panel, label="Copy Code")
        self.launch_search_btn = wx.Button(panel, label="Launch Gamemode")
        btn_sizer.Add(self.copy_code_search_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.launch_search_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER, 5)

        # Bind events
        self.copy_code_search_btn.Bind(wx.EVT_BUTTON, self.on_copy_code_search)
        self.launch_search_btn.Bind(wx.EVT_BUTTON, self.on_launch_search)
        self.search_prev_btn.Bind(wx.EVT_BUTTON, self.on_search_prev_page)
        self.search_next_btn.Bind(wx.EVT_BUTTON, self.on_search_next_page)
        self.search_list.Bind(wx.EVT_KEY_DOWN, self.on_search_key_down)
        self.search_list.Bind(wx.EVT_CHAR, self.on_search_char)
        self.search_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_launch_search)

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

    def _create_creator_panel(self):
        """Create By Creator tab"""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Title
        title = wx.StaticText(panel, label="Browse by Creator")
        title_font = title.GetFont()
        title_font.PointSize += 2
        title_font = title_font.Bold()
        title.SetFont(title_font)
        sizer.Add(title, 0, wx.ALL, 10)

        # Creator name input
        creator_sizer = wx.BoxSizer(wx.HORIZONTAL)
        creator_label = wx.StaticText(panel, label="Creator:")
        creator_sizer.Add(creator_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        self.creator_box = wx.TextCtrl(panel, size=(200, -1), style=wx.TE_PROCESS_ENTER, value="epic")
        self.creator_box.Bind(wx.EVT_TEXT_ENTER, self.on_load_creator)
        creator_sizer.Add(self.creator_box, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        load_creator_btn = wx.Button(panel, label="Load Maps")
        load_creator_btn.Bind(wx.EVT_BUTTON, self.on_load_creator)
        creator_sizer.Add(load_creator_btn, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        epic_btn = wx.Button(panel, label="Epic Games")
        epic_btn.Bind(wx.EVT_BUTTON, self.on_load_epic)
        creator_sizer.Add(epic_btn, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        sizer.Add(creator_sizer, 0, wx.EXPAND)

        # Creator islands list
        self.creator_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        sizer.Add(self.creator_list, 1, wx.EXPAND | wx.ALL, 5)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.copy_code_creator_btn = wx.Button(panel, label="Copy Code")
        self.launch_creator_btn = wx.Button(panel, label="Launch Gamemode")
        btn_sizer.Add(self.copy_code_creator_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.launch_creator_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER, 5)

        # Bind events
        self.copy_code_creator_btn.Bind(wx.EVT_BUTTON, self.on_copy_code_creator)
        self.launch_creator_btn.Bind(wx.EVT_BUTTON, self.on_launch_creator)
        self.creator_list.Bind(wx.EVT_KEY_DOWN, self.on_creator_key_down)
        self.creator_list.Bind(wx.EVT_CHAR, self.on_creator_char)
        self.creator_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_launch_creator)

        panel.SetSizer(sizer)
        return panel

    def _preload_all_tabs(self):
        """Pre-load data for tabs that need it"""
        # Load Epic Gamemodes tab (scrape Epic creator from fortnite.gg)
        self.load_epic_gamemodes()
        # Load Browse tab
        self.load_browse_islands()
        # Search and By Code tabs are loaded on-demand only
        # Creator tab is loaded on-demand only

    def on_tab_changed(self, event):
        """Handle tab change"""
        # With pre-loading, we don't need to load on tab change anymore
        # All necessary data is loaded on GUI open
        event.Skip()

    def load_epic_gamemodes(self, event=None):
        """Load Epic Games gamemodes from fortnite.gg creator page"""
        if self._is_destroying or not self.epic_list:
            return

        try:
            self.epic_list.GetCount()
        except RuntimeError:
            return

        self.epic_list.Clear()
        self.epic_list.Append("Loading Epic Games gamemodes...")
        speaker.speak("Loading Epic gamemodes")

        def _load():
            # Scrape Epic creator maps from fortnite.gg
            islands = self.discovery_api.scrape_creator_maps("epic", limit=50)
            if islands:
                wx.CallAfter(self._populate_epic_list, islands)
            else:
                wx.CallAfter(self._show_epic_error)

        threading.Thread(target=_load, daemon=True).start()

    def _populate_epic_list(self, islands):
        """Populate Epic list with gamemodes"""
        if self._is_destroying or not self.epic_list:
            return

        try:
            self.epic_list.GetCount()
        except RuntimeError:
            return

        self.epic_list.Clear()

        if not islands:
            self.epic_list.Append("No gamemodes found")
            speaker.speak("No gamemodes found")
            return

        for island in islands:
            # Display Epic gamemodes
            if island.global_ccu >= 0:
                label = f"{island.title} ({island.global_ccu} playing)"
            else:
                label = island.title
            self.epic_list.Append(label, island)

        if islands:
            self.epic_list.SetSelection(0)
            speaker.speak(f"{len(islands)} Epic gamemodes loaded")

    def _show_epic_error(self):
        """Show error message in epic list"""
        if self._is_destroying or not self.epic_list:
            return

        try:
            self.epic_list.GetCount()
        except RuntimeError:
            return

        self.epic_list.Clear()
        self.epic_list.Append("Error loading Epic gamemodes. Please try refreshing.")
        speaker.speak("Error loading Epic gamemodes")

    def on_refresh_epic(self, event):
        """Refresh epic list"""
        self.load_epic_gamemodes()

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
        self.current_page = 1
        self.load_browse_islands()

    def on_browse_sort_changed(self, event):
        """Handle sort selection change"""
        selection = self.browse_sort_choice.GetSelection()
        if selection >= 0 and selection < len(self.SORT_OPTIONS):
            self.current_sort = self.SORT_OPTIONS[selection][1]
            self.current_page = 1
            speaker.speak(f"Sorting by {self.SORT_OPTIONS[selection][0]}")
            self.load_browse_islands()

    def on_browse_prev_page(self, event):
        """Go to previous page"""
        if self.current_page > 1:
            self.current_page -= 1
            self.browse_page_label.SetLabel(f"Page {self.current_page}")
            speaker.speak(f"Page {self.current_page}")
            self.load_browse_islands()
        else:
            speaker.speak("Already on first page")

    def on_browse_next_page(self, event):
        """Go to next page"""
        self.current_page += 1
        self.browse_page_label.SetLabel(f"Page {self.current_page}")
        speaker.speak(f"Page {self.current_page}")
        self.load_browse_islands()

    def on_search_prev_page(self, event):
        """Go to previous page in search results"""
        if self.search_current_page > 1:
            self.search_current_page -= 1
            self.search_page_label.SetLabel(f"Page {self.search_current_page}")
            speaker.speak(f"Page {self.search_current_page}")
            self.perform_search(new_search=False)
        else:
            speaker.speak("Already on first page")

    def on_search_next_page(self, event):
        """Go to next page in search results"""
        self.search_current_page += 1
        self.search_page_label.SetLabel(f"Page {self.search_current_page}")
        speaker.speak(f"Page {self.search_current_page}")
        self.perform_search(new_search=False)

    def on_launch_browse(self, event):
        """Launch selected gamemode from browse list"""
        sel = self.browse_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No island selected")
            return

        island = self.browse_list.GetClientData(sel)
        if island and hasattr(island, 'link_code'):
            self._launch_gamemode(island.link_code, island.title)
        else:
            speaker.speak("No code available")

    def on_search_enter(self, event):
        """Handle Enter key in search box"""
        self.perform_search()

    def on_search_click(self, event):
        """Handle search button click"""
        self.perform_search()

    def perform_search(self, new_search=True):
        """Perform island search"""
        query = self.search_box.GetValue().strip()

        if not query:
            speaker.speak("Please enter a search term")
            return

        # Reset to page 1 for new searches
        if new_search:
            self.search_current_page = 1
            self.search_query = query
        
        self.search_list.Clear()
        self.search_list.Append(f"Searching fortnite.gg for '{self.search_query}'...")
        speaker.speak(f"Searching for {self.search_query}, page {self.search_current_page}")

        def _search():
            # Use fortnite.gg scraper for search
            islands = self.discovery_api.scrape_fortnite_gg(search_query=self.search_query, limit=50)
            wx.CallAfter(self._populate_search_list, islands, self.search_query)

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
            # Update page label
            self.search_page_label.SetLabel(f"Page {self.search_current_page}")
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

    def on_load_creator(self, event):
        """Load maps for specified creator"""
        creator_name = self.creator_box.GetValue().strip()

        if not creator_name:
            speaker.speak("Please enter a creator name")
            return

        self.load_creator_maps(creator_name)

    def on_load_epic(self, event):
        """Quick button to load Epic Games maps"""
        self.creator_box.SetValue("epic")
        self.load_creator_maps("epic")

    def load_creator_maps(self, creator_name):
        """Load maps from a specific creator"""
        if self._is_destroying or not self.creator_list:
            return

        self.creator_list.Clear()
        self.creator_list.Append(f"Loading maps from {creator_name}...")
        speaker.speak(f"Loading maps from {creator_name}")

        def _load():
            # Scrape creator maps from fortnite.gg
            islands = self.discovery_api.scrape_creator_maps(creator_name, limit=50)
            wx.CallAfter(self._populate_creator_list, islands, creator_name)

        threading.Thread(target=_load, daemon=True).start()

    def _populate_creator_list(self, islands, creator_name):
        """Populate creator list with results"""
        if self._is_destroying or not self.creator_list:
            return

        try:
            self.creator_list.GetCount()
        except RuntimeError:
            return

        self.creator_list.Clear()

        if not islands:
            self.creator_list.Append(f"No islands found for '{creator_name}'")
            speaker.speak(f"No islands found for {creator_name}")
            return

        for island in islands:
            # Include player count if available
            if island.global_ccu >= 0:
                label = f"{island.title} ({island.global_ccu} playing) - {island.link_code}"
            else:
                label = f"{island.title} - {island.link_code}"
            self.creator_list.Append(label, island)

        if islands:
            self.creator_list.SetSelection(0)
            speaker.speak(f"{len(islands)} maps loaded for {creator_name}")

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
        """Copy island code from browse list and launch (close dialog)"""
        sel = self.browse_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No island selected")
            return

        island = self.browse_list.GetClientData(sel)
        if island and hasattr(island, 'link_code'):
            pyperclip.copy(island.link_code)
            # Use title instead of code for non-standard formats
            if is_standard_code_format(island.link_code):
                speaker.speak(f"Copied code: {island.link_code}")
            else:
                speaker.speak(f"Copied code: {island.title}")
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
            # Use title instead of code for non-standard formats
            if is_standard_code_format(island.link_code):
                speaker.speak(f"Copied code: {island.link_code}")
            else:
                speaker.speak(f"Copied code: {island.title}")
        else:
            speaker.speak("No code available")

    def on_copy_code_epic(self, event):
        """Copy gamemode code from epic list"""
        sel = self.epic_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No gamemode selected")
            return

        island = self.epic_list.GetClientData(sel)
        if island and hasattr(island, 'link_code'):
            pyperclip.copy(island.link_code)
            # Use title instead of code for non-standard formats
            if is_standard_code_format(island.link_code):
                speaker.speak(f"Copied code: {island.link_code}")
            else:
                speaker.speak(f"Copied code: {island.title}")
        else:
            speaker.speak("No code available")

    def on_launch_epic(self, event):
        """Launch gamemode from epic list"""
        sel = self.epic_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No gamemode selected")
            return

        island = self.epic_list.GetClientData(sel)
        if island and hasattr(island, 'link_code'):
            self._launch_gamemode(island.link_code, island.title)
        else:
            speaker.speak("No code available")

    def on_copy_code_creator(self, event):
        """Copy island code from creator list"""
        sel = self.creator_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No island selected")
            return

        island = self.creator_list.GetClientData(sel)
        if island and hasattr(island, 'link_code'):
            pyperclip.copy(island.link_code)
            # Use title instead of code for non-standard formats
            if is_standard_code_format(island.link_code):
                speaker.speak(f"Copied code: {island.link_code}")
            else:
                speaker.speak(f"Copied code: {island.title}")
        else:
            speaker.speak("No code available")

    def on_launch_creator(self, event):
        """Launch gamemode from creator list"""
        sel = self.creator_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No island selected")
            return

        island = self.creator_list.GetClientData(sel)
        if island and hasattr(island, 'link_code'):
            self._launch_gamemode(island.link_code, island.title)
        else:
            speaker.speak("No code available")

    def on_launch_search(self, event):
        """Launch gamemode from search results"""
        sel = self.search_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No island selected")
            return

        island = self.search_list.GetClientData(sel)
        if island and hasattr(island, 'link_code'):
            self._launch_gamemode(island.link_code, island.title)
        else:
            speaker.speak("No code available")

    def on_epic_key_down(self, event):
        """Handle key press in epic list"""
        keycode = event.GetKeyCode()

        # CTRL+C to copy code/name
        if event.ControlDown() and keycode == ord('C'):
            self.on_copy_code_epic(event)
            return

        # Arrow key handling with wrapping
        if keycode == wx.WXK_UP:
            sel = self.epic_list.GetSelection()
            if sel == 0 or sel == wx.NOT_FOUND:
                last = self.epic_list.GetCount() - 1
                if last >= 0:
                    self.epic_list.SetSelection(last)
            else:
                self.epic_list.SetSelection(sel - 1)
            return

        elif keycode == wx.WXK_DOWN:
            sel = self.epic_list.GetSelection()
            last = self.epic_list.GetCount() - 1
            if sel == last or sel == wx.NOT_FOUND:
                self.epic_list.SetSelection(0)
            else:
                self.epic_list.SetSelection(sel + 1)
            return

        elif keycode == wx.WXK_LEFT or keycode == wx.WXK_RIGHT:
            return

        # Enter key launches gamemode
        elif keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            self.on_launch_epic(event)
            return

        event.Skip()

    def on_epic_char(self, event):
        """Handle char events in epic list (for ENTER key)"""
        keycode = event.GetKeyCode()
        
        # Handle ENTER key
        if keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            self.on_launch_epic(event)
            return
        
        event.Skip()

    def on_browse_key_down(self, event):
        """Handle key press in browse list"""
        keycode = event.GetKeyCode()

        # CTRL+C to copy code/name
        if event.ControlDown() and keycode == ord('C'):
            self.on_copy_code_browse(event)
            return

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

        # Enter key launches gamemode
        elif keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            self.on_launch_browse(event)
            return

        event.Skip()

    def on_browse_char(self, event):
        """Handle char events in browse list (for ENTER key)"""
        keycode = event.GetKeyCode()
        
        # Handle ENTER key
        if keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            self.on_launch_browse(event)
            return
        
        event.Skip()

    def on_search_key_down(self, event):
        """Handle key press in search list"""
        keycode = event.GetKeyCode()

        # CTRL+C to copy code/name
        if event.ControlDown() and keycode == ord('C'):
            self.on_copy_code_search(event)
            return

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

        # Enter key launches gamemode
        elif keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            self.on_launch_search(event)
            return

        event.Skip()

    def on_search_char(self, event):
        """Handle char events in search list (for ENTER key)"""
        keycode = event.GetKeyCode()
        
        # Handle ENTER key
        if keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            self.on_launch_search(event)
            return
        
        event.Skip()

    def on_creator_key_down(self, event):
        """Handle key press in creator list"""
        keycode = event.GetKeyCode()

        # CTRL+C to copy code/name
        if event.ControlDown() and keycode == ord('C'):
            self.on_copy_code_creator(event)
            return

        # Arrow key handling with wrapping
        if keycode == wx.WXK_UP:
            sel = self.creator_list.GetSelection()
            if sel == 0 or sel == wx.NOT_FOUND:
                last = self.creator_list.GetCount() - 1
                if last >= 0:
                    self.creator_list.SetSelection(last)
            else:
                self.creator_list.SetSelection(sel - 1)
            return

        elif keycode == wx.WXK_DOWN:
            sel = self.creator_list.GetSelection()
            last = self.creator_list.GetCount() - 1
            if sel == last or sel == wx.NOT_FOUND:
                self.creator_list.SetSelection(0)
            else:
                self.creator_list.SetSelection(sel + 1)
            return

        elif keycode == wx.WXK_LEFT or keycode == wx.WXK_RIGHT:
            return

        # Enter key launches gamemode
        elif keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            self.on_launch_creator(event)
            return

        event.Skip()

    def on_creator_char(self, event):
        """Handle char events in creator list (for ENTER key)"""
        keycode = event.GetKeyCode()
        
        # Handle ENTER key
        if keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            self.on_launch_creator(event)
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

    def _launch_gamemode(self, code: str, title: str):
        """Launch a gamemode by code using in-game automation"""
        speaker.speak(f"Launching {title}")

        # Close dialog first
        self._is_destroying = True
        self.EndModal(wx.ID_OK)

        # Run automation in separate thread to not block
        def _do_automation():
            try:
                # Ensure Fortnite stays in focus
                if not focus_fortnite():
                    logger.error("Could not focus Fortnite window")
                    speaker.speak("Failed to select gamemode: Could not focus Fortnite window")
                    return
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

                # Type the gamemode code or title (use title for non-standard codes)
                pyautogui.hotkey('ctrl', 'a')
                time.sleep(0.1)
                search_text = code if is_standard_code_format(code) else title
                pyautogui.typewrite(search_text)
                time.sleep(1.0)  # Wait an extra second before pressing enter
                pyautogui.press('enter')

                # Wait for search results - check if pixel 84,335 is white (255,255,255)
                # Using FA11y's built-in screen capture instead of pyautogui
                def check_pixel_white(x, y):
                    """Check if pixel at (x, y) is white using FA11y screen capture"""
                    import time as time_module

                    # Force a fresh capture by getting a full screen shot and indexing into it
                    # This bypasses any potential caching in capture_coordinates
                    from lib.managers.screenshot_manager import screenshot_manager
                    full_screen = screenshot_manager.capture_full_screen('rgb')

                    # Also get pyautogui's version for comparison
                    try:
                        pyautogui_color = pyautogui.pixel(x, y)
                    except:
                        pyautogui_color = "error"

                    if full_screen is not None:
                        # numpy arrays are indexed [y, x] not [x, y]
                        fa11y_color = tuple(full_screen[y, x])
                        timestamp = time_module.time()
                        print(f"[{timestamp:.3f}] Position ({x}, {y}) - FA11y: {fa11y_color}, PyAutoGUI: {pyautogui_color}")
                        return fa11y_color == (255, 255, 255)
                    print(f"Position ({x}, {y}) - FA11y: None (capture failed), PyAutoGUI: {pyautogui_color}")
                    return False

                start_time = time.time()
                check_count = 0
                while not check_pixel_white(84, 335):
                    if time.time() - start_time > 5:
                        logger.error("Timeout waiting for search results")
                        # Save a debug screenshot on timeout
                        try:
                            from lib.managers.screenshot_manager import screenshot_manager
                            import cv2
                            debug_shot = screenshot_manager.capture_full_screen('rgb')
                            if debug_shot is not None:
                                # Draw a marker at the pixel we were checking
                                debug_shot_bgr = cv2.cvtColor(debug_shot, cv2.COLOR_RGB2BGR)
                                cv2.circle(debug_shot_bgr, (84, 335), 10, (0, 0, 255), 2)
                                cv2.putText(debug_shot_bgr, f"(84,335)", (94, 335),
                                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                                cv2.imwrite('discovery_gui_timeout_debug.png', debug_shot_bgr)
                                print(f"[DEBUG] Saved timeout screenshot to discovery_gui_timeout_debug.png")
                        except Exception as e:
                            print(f"[DEBUG] Failed to save debug screenshot: {e}")

                        speaker.speak("Failed to select gamemode: Search results not found - gamemode may not exist or something else broke")
                        pyautogui.scroll(3)
                        time.sleep(0.2)
                        pyautogui.scroll(3)
                        time.sleep(0.2)
                        pyautogui.scroll(3)
                        time.sleep(0.2)
                        pyautogui.scroll(3)
                        return
                    check_count += 1
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

                speaker.speak(f"{title} selected!")

            except Exception as e:
                logger.error(f"Error launching gamemode: {e}")
                speaker.speak(f"Failed to select gamemode: {e}")

        threading.Thread(target=_do_automation, daemon=True).start()


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
