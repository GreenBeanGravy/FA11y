"""
Social Menu GUI for FA11y
Provides interface for managing friends, party, and requests
"""
import logging
import wx
from lib.hub.controls import StyledButton, TabbedBook
import threading
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import BORDER_FOR_DIALOGS
from lib.guis.view_host import EmbeddedView, show_view
from lib.managers.social_manager import (
    friend_name, friends_count_text, party_count_text, requests_count_text,
)

logger = logging.getLogger(__name__)
speaker = Auto()


class SocialView(EmbeddedView):
    """View for managing social features"""

    view_title = "Social Menu"

    def __init__(self, parent, social_manager):
        super().__init__(parent)
        self.social_manager = social_manager
        self._is_destroying = False  # True while the view is hidden or closing
        self._activated_once = False

        # Type-to-search state
        self.type_search_buffer = ""
        self.type_search_timer = None

        self._build_controls()

    def _build_controls(self):
        """Create view content"""
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Create notebook for tabs
        self.notebook = TabbedBook(self)
        sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, BORDER_FOR_DIALOGS)
        self.SetSizer(sizer)

        # Create tabs
        self.friends_panel = self._create_friends_panel()
        self.requests_panel = self._create_requests_panel()
        self.party_panel = self._create_party_panel()
        self.me_panel = self._create_me_panel()

        self.notebook.AddPage(self.friends_panel, "Friends")
        self.notebook.AddPage(self.requests_panel, "Friend Requests")
        self.notebook.AddPage(self.party_panel, "Party")
        self.notebook.AddPage(self.me_panel, "Me")

        # Bind tab change event
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_changed)

    def activate(self):
        """The view became visible"""
        self._is_destroying = False
        if not self._activated_once:
            self._activated_once = True
            # Refresh the initial tab
            self.refresh_friends_list()
            return
        # Later activations just redraw the current tab from cached data
        page = self.notebook.GetSelection()
        if page == 0:
            self.refresh_friends_list()
        elif page == 1:
            self.refresh_requests_list()
        elif page == 2:
            self.refresh_party_list()

    def deactivate(self):
        """The view was hidden or its host is closing"""
        self._is_destroying = True
        if self.type_search_timer:
            self.type_search_timer.Stop()
            self.type_search_timer = None
        self.type_search_buffer = ""

    def initial_focus(self):
        return self.friends_list

    def _create_me_panel(self):
        """Create Me tab showing account information in 3 separate boxes"""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Title
        title = wx.StaticText(panel, label="Account Information")
        title_font = title.GetFont()
        title_font.PointSize += 2
        title_font = title_font.Bold()
        title.SetFont(title_font)
        sizer.Add(title, 0, wx.ALL, 10)

        # Epic Account Stats Box
        epic_label = wx.StaticText(panel, label="Epic Account Stats")
        epic_label_font = epic_label.GetFont()
        epic_label_font = epic_label_font.Bold()
        epic_label.SetFont(epic_label_font)
        sizer.Add(epic_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.epic_account_text = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(-1, 80)
        )
        font = self.epic_account_text.GetFont()
        font.PointSize += 1
        self.epic_account_text.SetFont(font)
        sizer.Add(self.epic_account_text, 0, wx.ALL | wx.EXPAND, 10)

        # Fortnite Stats Box
        fn_label = wx.StaticText(panel, label="Fortnite Stats")
        fn_label_font = fn_label.GetFont()
        fn_label_font = fn_label_font.Bold()
        fn_label.SetFont(fn_label_font)
        sizer.Add(fn_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.fortnite_stats_text = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(-1, 200)
        )
        font = self.fortnite_stats_text.GetFont()
        font.PointSize += 1
        self.fortnite_stats_text.SetFont(font)
        sizer.Add(self.fortnite_stats_text, 1, wx.ALL | wx.EXPAND, 10)

        # Fortnite Ranked Stats Box
        ranked_label = wx.StaticText(panel, label="Fortnite Ranked Stats")
        ranked_label_font = ranked_label.GetFont()
        ranked_label_font = ranked_label_font.Bold()
        ranked_label.SetFont(ranked_label_font)
        sizer.Add(ranked_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self.ranked_stats_text = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(-1, 150)
        )
        font = self.ranked_stats_text.GetFont()
        font.PointSize += 1
        self.ranked_stats_text.SetFont(font)
        sizer.Add(self.ranked_stats_text, 1, wx.ALL | wx.EXPAND, 10)

        # Refresh button
        refresh_btn = StyledButton(panel, label="Refresh Account Information")
        refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh_account_info)
        sizer.Add(refresh_btn, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        panel.SetSizer(sizer)

        # Set initial loading message (will be loaded when tab is first shown)
        loading_msg = "Loading... (switch to this tab to load data)"
        self.epic_account_text.SetValue(loading_msg)
        self.fortnite_stats_text.SetValue(loading_msg)
        self.ranked_stats_text.SetValue(loading_msg)

        return panel

    def load_account_info(self):
        """Load account information from Epic Games API into 3 separate boxes"""
        epic, fortnite, ranked = self.social_manager.account_info_texts()
        self.epic_account_text.SetValue(epic)
        self.epic_account_text.SetInsertionPoint(0)
        self.fortnite_stats_text.SetValue(fortnite)
        self.fortnite_stats_text.SetInsertionPoint(0)
        self.ranked_stats_text.SetValue(ranked)
        self.ranked_stats_text.SetInsertionPoint(0)

    def on_refresh_account_info(self, event):
        """Refresh account information"""
        speaker.speak("Refreshing account information")
        self.load_account_info()
        speaker.speak("Account information refreshed")

    def _create_friends_panel(self):
        """Create friends tab"""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Filter buttons for All/Favorites
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.all_friends_btn = wx.RadioButton(panel, label="All Friends", style=wx.RB_GROUP)
        self.favorite_friends_btn = wx.RadioButton(panel, label="Favorites")
        self.all_friends_btn.SetValue(True)
        filter_sizer.Add(self.all_friends_btn, 0, wx.ALL, 5)
        filter_sizer.Add(self.favorite_friends_btn, 0, wx.ALL, 5)
        sizer.Add(filter_sizer, 0, wx.ALL, 5)

        # Search box
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_label = wx.StaticText(panel, label="Search:")
        search_sizer.Add(search_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        self.search_box = wx.TextCtrl(panel, size=(300, -1), style=wx.TE_PROCESS_ENTER)
        self.search_box.Bind(wx.EVT_TEXT, self.on_search_changed)
        self.search_box.Bind(wx.EVT_TEXT_ENTER, self.on_search_changed)  # Enter also triggers search
        search_sizer.Add(self.search_box, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        clear_btn = StyledButton(panel, label="Clear")
        clear_btn.Bind(wx.EVT_BUTTON, lambda e: self.search_box.SetValue(""))
        search_sizer.Add(clear_btn, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        sizer.Add(search_sizer, 0, wx.EXPAND)

        # Friends list (no online filter - presence API not available)
        self.friends_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        sizer.Add(self.friends_list, 1, wx.EXPAND | wx.ALL, 5)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.add_friend_btn = StyledButton(panel, label="Add Friend")
        self.invite_btn = StyledButton(panel, label="Invite to Party")
        self.request_join_btn = StyledButton(panel, label="Request to Join")
        self.remove_friend_btn = StyledButton(panel, label="Remove Friend")
        btn_sizer.Add(self.add_friend_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.invite_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.request_join_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.remove_friend_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER, 5)

        # Bind events
        self.all_friends_btn.Bind(wx.EVT_RADIOBUTTON, self.refresh_friends_list)
        self.favorite_friends_btn.Bind(wx.EVT_RADIOBUTTON, self.refresh_friends_list)
        self.add_friend_btn.Bind(wx.EVT_BUTTON, self.on_add_friend)
        self.invite_btn.Bind(wx.EVT_BUTTON, self.on_invite_to_party)
        self.request_join_btn.Bind(wx.EVT_BUTTON, self.on_request_to_join)
        self.remove_friend_btn.Bind(wx.EVT_BUTTON, self.on_remove_friend)
        self.friends_list.Bind(wx.EVT_KEY_DOWN, self.on_friends_key_down)
        self.friends_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_friends_double_click)

        # Store search state
        self.current_search = ""

        panel.SetSizer(sizer)
        return panel

    def _create_requests_panel(self):
        """Create friend requests tab"""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Filter buttons
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.incoming_req_btn = wx.RadioButton(panel, label="Incoming", style=wx.RB_GROUP)
        self.outgoing_req_btn = wx.RadioButton(panel, label="Outgoing")
        self.incoming_req_btn.SetValue(True)
        filter_sizer.Add(self.incoming_req_btn, 0, wx.ALL, 5)
        filter_sizer.Add(self.outgoing_req_btn, 0, wx.ALL, 5)
        sizer.Add(filter_sizer, 0, wx.ALL, 5)

        # Requests list
        self.requests_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        sizer.Add(self.requests_list, 1, wx.EXPAND | wx.ALL, 5)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.accept_req_btn = StyledButton(panel, label="Accept")
        self.decline_req_btn = StyledButton(panel, label="Decline")
        btn_sizer.Add(self.accept_req_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.decline_req_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER, 5)

        # Bind events
        self.incoming_req_btn.Bind(wx.EVT_RADIOBUTTON, self.refresh_requests_list)
        self.outgoing_req_btn.Bind(wx.EVT_RADIOBUTTON, self.refresh_requests_list)
        self.accept_req_btn.Bind(wx.EVT_BUTTON, self.on_accept_request)
        self.decline_req_btn.Bind(wx.EVT_BUTTON, self.on_decline_request)
        self.requests_list.Bind(wx.EVT_KEY_DOWN, self.on_requests_key_down)

        panel.SetSizer(sizer)
        return panel

    def _create_party_panel(self):
        """Create party tab"""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Party members list
        self.party_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        sizer.Add(self.party_list, 1, wx.EXPAND | wx.ALL, 5)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.promote_btn = StyledButton(panel, label="Promote to Leader")
        self.kick_btn = StyledButton(panel, label="Kick Member")
        self.leave_party_btn = StyledButton(panel, label="Leave Party")
        btn_sizer.Add(self.promote_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.kick_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.leave_party_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER, 5)

        # Bind events
        # Bind events
        self.promote_btn.Bind(wx.EVT_BUTTON, self.on_promote_member)
        self.kick_btn.Bind(wx.EVT_BUTTON, self.on_kick_member)
        self.leave_party_btn.Bind(wx.EVT_BUTTON, self.on_leave_party)

        panel.SetSizer(sizer)
        return panel

    def on_tab_changed(self, event):
        """Handle tab change - refresh data asynchronously"""
        page = event.GetSelection()

        def _refresh_task():
            if page == 0:  # Friends
                self.social_manager.force_refresh_data("friends")
                wx.CallAfter(self.refresh_friends_list)
            elif page == 1:  # Requests
                self.social_manager.force_refresh_data("requests")
                wx.CallAfter(self.refresh_requests_list)
            elif page == 2:  # Party
                self.social_manager.force_refresh_data("party")
                wx.CallAfter(self.refresh_party_list)
            elif page == 3:  # Me tab
                # Load account info (fresh data from API)
                wx.CallAfter(self.load_account_info)

        # Run refresh in background thread to avoid UI freeze
        import threading
        threading.Thread(target=_refresh_task, daemon=True).start()

    def on_search_changed(self, event):
        """Handle search text changes"""
        self.current_search = self.search_box.GetValue()
        self.refresh_friends_list()

    def refresh_friends_list(self, event=None):
        """Refresh friends list with filtering and search"""
        # Check if dialog is being destroyed or widget is invalid
        if self._is_destroying or not self.friends_list or not hasattr(self.friends_list, 'Clear'):
            return

        # Additional safety check - verify widget hasn't been deleted
        try:
            self.friends_list.GetCount()
        except RuntimeError:
            # Widget has been deleted
            return

        self.friends_list.Clear()

        favorites_only = self.favorite_friends_btn.GetValue()
        friends = self.social_manager.friends_view(favorites_only, self.current_search)

        # Add to list - screen readers will auto-announce position
        for friend in friends:
            name = friend_name(friend)
            label = f"★ {name}" if self.social_manager.is_favorite(friend) else name
            self.friends_list.Append(label, friend)

        if friends:
            self.friends_list.SetSelection(0)
        speaker.speak(friends_count_text(len(friends), favorites_only))

    def refresh_requests_list(self, event=None):
        """Refresh requests list"""
        # Check if dialog is being destroyed or widget is invalid
        if self._is_destroying or not self.requests_list or not hasattr(self.requests_list, 'Clear'):
            return

        # Additional safety check - verify widget hasn't been deleted
        try:
            self.requests_list.GetCount()
        except RuntimeError:
            # Widget has been deleted
            return

        self.requests_list.Clear()

        incoming = self.incoming_req_btn.GetValue()
        requests = self.social_manager.requests_view(incoming)

        # Use cached display names - screen readers will auto-announce position
        for req in requests:
            direction = "from" if req.direction == "inbound" else "to"
            self.requests_list.Append(f"Request {direction} {friend_name(req)}", req)

        if requests:
            self.requests_list.SetSelection(0)
        speaker.speak(requests_count_text(len(requests), incoming))

    def refresh_party_list(self, event=None):
        """Refresh party members list"""
        # Check if dialog is being destroyed or widget is invalid
        if self._is_destroying or not self.party_list or not hasattr(self.party_list, 'Clear'):
            return

        # Additional safety check - verify widget hasn't been deleted
        try:
            self.party_list.GetCount()
        except RuntimeError:
            # Widget has been deleted
            return

        self.party_list.Clear()

        members, am_i_leader = self.social_manager.party_view()

        # Use cached display names - screen readers will auto-announce position
        for member in members:
            name = friend_name(member)
            self.party_list.Append(f"{name} (Leader)" if member.is_leader else name, member)

        if members:
            self.party_list.SetSelection(0)
        speaker.speak(party_count_text(len(members)))

        # Only the leader can promote or kick
        self.promote_btn.Enable(am_i_leader)
        self.kick_btn.Enable(am_i_leader)

    def on_friends_key_down(self, event):
        """Handle key press in friends list with arrow wrapping and type-to-search"""
        keycode = event.GetKeyCode()

        # Arrow key handling - consume them to prevent tab navigation
        if keycode == wx.WXK_UP:
            sel = self.friends_list.GetSelection()
            if sel == 0 or sel == wx.NOT_FOUND:
                # Wrap to last item
                last = self.friends_list.GetCount() - 1
                if last >= 0:
                    self.friends_list.SetSelection(last)
            else:
                # Normal up navigation
                self.friends_list.SetSelection(sel - 1)
            return  # Don't Skip - prevents tab navigation

        elif keycode == wx.WXK_DOWN:
            sel = self.friends_list.GetSelection()
            last = self.friends_list.GetCount() - 1
            if sel == last or sel == wx.NOT_FOUND:
                # Wrap to first item
                self.friends_list.SetSelection(0)
            else:
                # Normal down navigation
                self.friends_list.SetSelection(sel + 1)
            return  # Don't Skip - prevents tab navigation

        elif keycode == wx.WXK_LEFT or keycode == wx.WXK_RIGHT:
            # Consume left/right to prevent tab switching
            return

        # Enter key sends party invite
        elif keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            self.on_invite_to_party(event)
            return
        # F key toggles favorite
        elif keycode == ord('F'):
            self.on_toggle_favorite(event)
            return
        # Type-to-search (alphanumeric keys)
        elif keycode >= 32 and keycode <= 126:  # Printable ASCII
            self._handle_type_to_search(chr(keycode), self.friends_list)
            return

        event.Skip()  # Allow other keys to be processed normally

    def _handle_type_to_search(self, char, listbox):
        """Handle type-to-search functionality for list boxes"""
        # Cancel existing timer
        if self.type_search_timer:
            self.type_search_timer.Stop()
            self.type_search_timer = None

        # Add character to buffer
        self.type_search_buffer += char.lower()

        # Search for matching item
        count = listbox.GetCount()
        for i in range(count):
            item_text = listbox.GetString(i).lower()
            # Remove optional star prefix "★ "
            if item_text.startswith("★ "):
                item_text = item_text[2:].strip()

            if item_text.startswith(self.type_search_buffer):
                listbox.SetSelection(i)
                # Speak the found item
                speaker.speak(listbox.GetString(i))
                break

        # Set timer to clear buffer after 1 second of no typing
        self.type_search_timer = wx.CallLater(1000, self._clear_type_search_buffer)

    def _clear_type_search_buffer(self):
        """Clear type-to-search buffer"""
        self.type_search_buffer = ""
        self.type_search_timer = None

    def _refresh_after_operation(self, data_type):
        """
        Force backend refresh and update GUI after an operation

        Args:
            data_type: 'friends' or 'requests' to determine which data to refresh
        """
        self.social_manager.refresh_after_operation(data_type)
        if data_type == 'friends':
            wx.CallAfter(self.refresh_friends_list)
        elif data_type == 'requests':
            wx.CallAfter(self.refresh_requests_list)

    def on_requests_key_down(self, event):
        """Handle key press in requests list with arrow wrapping and type-to-search"""
        keycode = event.GetKeyCode()

        # Arrow key handling - consume them to prevent tab navigation
        if keycode == wx.WXK_UP:
            sel = self.requests_list.GetSelection()
            if sel == 0 or sel == wx.NOT_FOUND:
                # Wrap to last item
                last = self.requests_list.GetCount() - 1
                if last >= 0:
                    self.requests_list.SetSelection(last)
            else:
                # Normal up navigation
                self.requests_list.SetSelection(sel - 1)
            return  # Don't Skip - prevents tab navigation

        elif keycode == wx.WXK_DOWN:
            sel = self.requests_list.GetSelection()
            last = self.requests_list.GetCount() - 1
            if sel == last or sel == wx.NOT_FOUND:
                # Wrap to first item
                self.requests_list.SetSelection(0)
            else:
                # Normal down navigation
                self.requests_list.SetSelection(sel + 1)
            return  # Don't Skip - prevents tab navigation

        elif keycode == wx.WXK_LEFT or keycode == wx.WXK_RIGHT:
            # Consume left/right to prevent tab switching
            return

        # Enter key accepts request
        elif keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            self.on_accept_request(event)
            return
        # DEL key declines request
        elif keycode == wx.WXK_DELETE or keycode == wx.WXK_NUMPAD_DELETE:
            self.on_decline_request(event)
            return
        # Type-to-search (alphanumeric keys)
        elif keycode >= 32 and keycode <= 126:  # Printable ASCII
            self._handle_type_to_search(chr(keycode), self.requests_list)
            return

        event.Skip()  # Allow other keys to be processed normally

    def on_toggle_favorite(self, event):
        """Toggle selected friend as favorite"""
        sel = self.friends_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No friend selected")
            return

        friend = self.friends_list.GetClientData(sel)
        self.social_manager.toggle_favorite(friend)
        # Refresh to update the star and sorting
        wx.CallAfter(self.refresh_friends_list)

    def on_friends_double_click(self, event):
        """Handle double-click on friend - sends party invite"""
        self.on_invite_to_party(event)

    def on_invite_to_party(self, event):
        """Invite selected friend to party"""
        sel = self.friends_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No friend selected")
            return

        friend = self.friends_list.GetClientData(sel)
        self.social_manager._invite_friend_to_party(friend)

    def on_request_to_join(self, event):
        """Request to join selected friend's party"""
        sel = self.friends_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No friend selected")
            return

        friend = self.friends_list.GetClientData(sel)
        self.social_manager._request_to_join_party(friend)

    def on_remove_friend(self, event):
        """Remove selected friend"""
        sel = self.friends_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No friend selected")
            return

        friend = self.friends_list.GetClientData(sel)
        name = self.social_manager._ensure_display_name(friend.display_name)

        dlg = wx.MessageDialog(
            self,
            f"Are you sure you want to remove {name} from your friends list?",
            "Confirm Remove Friend",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION
        )
        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wx.ID_YES:
            self.social_manager._remove_friend(friend)
            # Force immediate backend refresh then update GUI
            wx.CallLater(500, self._refresh_after_operation, 'friends')

    def on_add_friend(self, event):
        """Open dialog to search and add friends"""
        dlg = wx.TextEntryDialog(
            self,
            "Enter Epic Games username to search:",
            "Add Friend"
        )

        if dlg.ShowModal() == wx.ID_OK:
            username = dlg.GetValue().strip()
            dlg.Destroy()

            if not username:
                speaker.speak("No username entered")
                return

            # Search for users
            speaker.speak(f"Searching for {username}")
            users = self.social_manager.social_api.search_users(username)

            if not users:
                speaker.speak(f"No users found matching {username}")
                return

            # The exact match or the only result is used; otherwise the user picks
            chosen = self.social_manager.choose_user(users)
            if chosen:
                self.social_manager._send_friend_request_by_account_id(
                    chosen["account_id"],
                    chosen["display_name"]
                )
                wx.CallLater(1000, self.refresh_requests_list)
            else:
                # Multiple results - show selection dialog
                choices = [self.social_manager.user_choice_label(u) for u in users]
                dlg = wx.SingleChoiceDialog(
                    self,
                    f"Multiple users found. Select one:",
                    "Select User",
                    choices
                )

                if dlg.ShowModal() == wx.ID_OK:
                    index = dlg.GetSelection()
                    dlg.Destroy()
                    selected_user = users[index]
                    self.social_manager._send_friend_request_by_account_id(
                        selected_user["account_id"],
                        selected_user["display_name"]
                    )
                    wx.CallLater(1000, self.refresh_requests_list)
                else:
                    dlg.Destroy()
                    speaker.speak("Cancelled")
        else:
            dlg.Destroy()
            speaker.speak("Cancelled")

    def on_accept_request(self, event):
        """Accept selected request"""
        sel = self.requests_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No request selected")
            return

        req = self.requests_list.GetClientData(sel)
        problem = self.social_manager.accept_problem(req)
        if problem:
            speaker.speak(problem)
            return
        self.social_manager._accept_friend_request(req)
        # Force immediate backend refresh then update GUI
        wx.CallLater(500, self._refresh_after_operation, 'requests')

    def on_decline_request(self, event):
        """Decline selected request"""
        sel = self.requests_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No request selected")
            return

        req = self.requests_list.GetClientData(sel)
        self.social_manager._decline_friend_request(req)
        # Force immediate backend refresh then update GUI
        wx.CallLater(500, self._refresh_after_operation, 'requests')

    def on_promote_member(self, event):
        """Promote selected member to leader"""
        sel = self.party_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No member selected")
            return

        member = self.party_list.GetClientData(sel)
        problem = self.social_manager.promote_problem(member)
        if problem:
            speaker.speak(problem)
            return

        self.social_manager._promote_party_member(member)
        wx.CallLater(1000, self.refresh_party_list)

    def on_leave_party(self, event):
        """Leave current party"""
        with self.social_manager.lock:
            if not self.social_manager.party_members:
                speaker.speak("Not in a party")
                return

        dlg = wx.MessageDialog(
            self,
            "Are you sure you want to leave the party?",
            "Confirm Leave Party",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION
        )
        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wx.ID_YES:
            self.social_manager.leave_party()
            wx.CallLater(1000, self.refresh_party_list)

    def on_kick_member(self, event):
        """Kick selected member from party"""
        sel = self.party_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No member selected")
            return

        member = self.party_list.GetClientData(sel)
        
        # Can't kick yourself (use leave instead)
        problem = self.social_manager.kick_problem(member)
        if problem:
            speaker.speak(problem)
            return

        name = self.social_manager._ensure_display_name(member.display_name)

        dlg = wx.MessageDialog(
            self,
            f"Are you sure you want to kick {name}?",
            "Confirm Kick Member",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION
        )
        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wx.ID_YES:
            self.social_manager.kick_party_member(member.account_id)
            wx.CallLater(1000, self.refresh_party_list)


def show_social_gui(social_manager):
    """Show the social menu GUI"""
    try:
        # Get or create wx App
        app = wx.GetApp()
        if app is None:
            app = wx.App(False)

        show_view('social', lambda host: SocialView(host, social_manager), size=(800, 600))

        # Dialog fallback only: return focus to Fortnite after closing
        from lib.hub import get_hub
        hub = get_hub()
        if hub is None or not hub.has_page('social'):
            try:
                from lib.utilities.window_utils import focus_window
                focus_window("Fortnite")
            except Exception as e:
                logger.debug(f"Could not return focus to game: {e}")
    except Exception as e:
        logger.error(f"Error showing social GUI: {e}")
        speaker.speak("Error opening social menu")
