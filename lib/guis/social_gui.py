"""
Social Menu GUI for FA11y
Provides interface for managing friends, party, and requests
"""
import logging
import wx
import threading
import pyautogui
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import (
    AccessibleDialog, BoxSizerHelper, ButtonHelper,
    messageBox, BORDER_FOR_DIALOGS
)
from lib.utilities.epic_social import Friend, FriendRequest, PartyMember, PartyInvite

logger = logging.getLogger(__name__)
speaker = Auto()


class SocialDialog(AccessibleDialog):
    """Dialog for managing social features"""

    def __init__(self, parent, social_manager):
        super().__init__(parent, title="Social Menu", helpId="SocialMenu")
        self.social_manager = social_manager
        self.setupDialog()
        self.SetSize((800, 600))
        self.CentreOnParent()

        # Type-to-search state
        self.type_search_buffer = ""
        self.type_search_timer = None

        # Bind Escape key to close dialog
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)

    def makeSettings(self, sizer: BoxSizerHelper):
        """Create dialog content"""

        # Create notebook for tabs
        self.notebook = wx.Notebook(self)
        sizer.addItem(self.notebook, flag=wx.EXPAND, proportion=1)

        # Create tabs
        self.friends_panel = self._create_friends_panel()
        self.requests_panel = self._create_requests_panel()
        self.party_panel = self._create_party_panel()

        self.notebook.AddPage(self.friends_panel, "Friends")
        self.notebook.AddPage(self.requests_panel, "Friend Requests")
        self.notebook.AddPage(self.party_panel, "Party")

        # Bind tab change event
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_changed)

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

        clear_btn = wx.Button(panel, label="Clear")
        clear_btn.Bind(wx.EVT_BUTTON, lambda e: self.search_box.SetValue(""))
        search_sizer.Add(clear_btn, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)

        sizer.Add(search_sizer, 0, wx.EXPAND)

        # Friends list (no online filter - presence API not available)
        self.friends_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        sizer.Add(self.friends_list, 1, wx.EXPAND | wx.ALL, 5)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.add_friend_btn = wx.Button(panel, label="Add Friend")
        self.invite_btn = wx.Button(panel, label="Invite to Party")
        self.request_join_btn = wx.Button(panel, label="Request to Join")
        self.remove_friend_btn = wx.Button(panel, label="Remove Friend")
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
        self.accept_req_btn = wx.Button(panel, label="Accept")
        self.decline_req_btn = wx.Button(panel, label="Decline")
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
        self.promote_btn = wx.Button(panel, label="Promote to Leader")
        self.leave_party_btn = wx.Button(panel, label="Leave Party")
        btn_sizer.Add(self.promote_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.leave_party_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER, 5)

        # Bind events
        self.promote_btn.Bind(wx.EVT_BUTTON, self.on_promote_member)
        self.leave_party_btn.Bind(wx.EVT_BUTTON, self.on_leave_party)

        panel.SetSizer(sizer)
        return panel

    def on_tab_changed(self, event):
        """Handle tab change - refresh data"""
        page = event.GetSelection()
        if page == 0:  # Friends
            self.refresh_friends_list()
        elif page == 1:  # Requests
            self.refresh_requests_list()
        elif page == 2:  # Party
            self.refresh_party_list()

    def on_search_changed(self, event):
        """Handle search text changes"""
        self.current_search = self.search_box.GetValue()
        self.refresh_friends_list()

    def refresh_friends_list(self, event=None):
        """Refresh friends list with filtering and search"""
        self.friends_list.Clear()

        with self.social_manager.lock:
            all_friends = list(self.social_manager.all_friends)

        # Filter by favorites if selected
        if self.favorite_friends_btn.GetValue():
            friends = [f for f in all_friends if self.social_manager.is_favorite(f)]
        else:
            friends = all_friends

        # Apply search filter
        if self.current_search:
            search_lower = self.current_search.lower()
            friends = [f for f in friends if search_lower in (f.display_name or "").lower()]

        # Sort favorites first, then alphabetically
        def sort_key(friend):
            is_fav = self.social_manager.is_favorite(friend)
            name = (friend.display_name or friend.account_id or "Unknown").lower()
            return (not is_fav, name)  # not is_fav so True (favorite) comes before False

        friends.sort(key=sort_key)

        # Add to list with index after name: "Friend Name, 1 of 10"
        total = len(friends)
        for idx, friend in enumerate(friends, start=1):
            name = friend.display_name or friend.account_id or "Unknown"
            # Add star for favorites and index after name
            if self.social_manager.is_favorite(friend):
                label = f"★ {name}, {idx} of {total}"
            else:
                label = f"{name}, {idx} of {total}"
            self.friends_list.Append(label, friend)

        if friends:
            self.friends_list.SetSelection(0)
            filter_type = "favorite friends" if self.favorite_friends_btn.GetValue() else "friends"
            speaker.speak(f"{len(friends)} {filter_type}")
        else:
            filter_type = "favorite friends" if self.favorite_friends_btn.GetValue() else "friends"
            speaker.speak(f"No {filter_type}")

    def refresh_requests_list(self, event=None):
        """Refresh requests list"""
        self.requests_list.Clear()

        with self.social_manager.lock:
            if self.incoming_req_btn.GetValue():
                requests = list(self.social_manager.incoming_requests)
                request_type = "incoming"
            else:
                requests = list(self.social_manager.outgoing_requests)
                request_type = "outgoing"

        # Use cached display names (already fetched by background monitor)
        total = len(requests)
        for idx, req in enumerate(requests, start=1):
            name = req.display_name or req.account_id or "Unknown"
            direction = "from" if req.direction == "inbound" else "to"
            label = f"Request {direction} {name}, {idx} of {total}"
            self.requests_list.Append(label, req)

        if requests:
            self.requests_list.SetSelection(0)
            speaker.speak(f"{len(requests)} {request_type} requests")
        else:
            speaker.speak(f"No {request_type} friend requests")

    def refresh_party_list(self, event=None):
        """Refresh party members list"""
        self.party_list.Clear()

        with self.social_manager.lock:
            members = list(self.social_manager.party_members)

        # Use cached display names with fallback
        total = len(members)
        for idx, member in enumerate(members, start=1):
            name = member.display_name or member.account_id or "Unknown"
            if member.is_leader:
                label = f"{name} (Leader), {idx} of {total}"
            else:
                label = f"{name}, {idx} of {total}"
            self.party_list.Append(label, member)

        if members:
            self.party_list.SetSelection(0)
            speaker.speak(f"{len(members)} party members")
        else:
            speaker.speak("Not in a party")

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
            # Remove index suffix like ", 1 of 10" and optional star prefix "★ "
            import re
            # Match optional star, then name, then optional index
            match = re.search(r'^(?:★\s*)?(.+?)(?:,\s*\d+\s*of\s*\d+)?$', item_text)
            if match:
                item_text = match.group(1).strip()

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
        if data_type == 'friends':
            # Refresh friends data from backend
            self.social_manager.refresh_slow_data()
            # Update GUI
            wx.CallAfter(self.refresh_friends_list)
        elif data_type == 'requests':
            # Refresh requests data from backend
            self.social_manager.refresh_fast_data()
            # Update GUI
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

    def on_char_hook(self, event):
        """Handle key press for dialog (Escape to close)"""
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            wx.CallAfter(self._return_focus_to_game)
        else:
            event.Skip()

    def _return_focus_to_game(self):
        """Return focus to Fortnite with a left click"""
        try:
            pyautogui.click(1919, 540)
        except Exception as e:
            logger.debug(f"Could not return focus to game: {e}")

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

            # If exact match found, use it
            exact_match = None
            for user in users:
                if user["match_type"] == "exact":
                    exact_match = user
                    break

            if exact_match:
                # Send friend request to exact match
                self.social_manager._send_friend_request_by_account_id(
                    exact_match["account_id"],
                    exact_match["display_name"]
                )
                wx.CallLater(1000, self.refresh_requests_list)
            elif len(users) == 1:
                # Only one result, use it
                user = users[0]
                self.social_manager._send_friend_request_by_account_id(
                    user["account_id"],
                    user["display_name"]
                )
                wx.CallLater(1000, self.refresh_requests_list)
            else:
                # Multiple results - show selection dialog
                choices = [f"{u['display_name']} ({u['mutual_friends']} mutual friends)" for u in users]
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
        if req.direction == "inbound":
            self.social_manager._accept_friend_request(req)
            # Force immediate backend refresh then update GUI
            wx.CallLater(500, self._refresh_after_operation, 'requests')
        else:
            speaker.speak("Cannot accept outgoing request")

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
        if member.is_leader:
            speaker.speak("Member is already the leader")
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


def show_social_gui(social_manager):
    """Show the social menu GUI"""
    try:
        # Get or create wx App
        app = wx.GetApp()
        if app is None:
            app = wx.App(False)

        dialog = SocialDialog(None, social_manager)

        # Focus window and center mouse
        try:
            from lib.guis.gui_utilities import ensure_window_focus_and_center_mouse
            ensure_window_focus_and_center_mouse(dialog)
        except Exception as e:
            logger.debug(f"Could not focus window: {e}")

        # Refresh the initial tab
        dialog.refresh_friends_list()

        dialog.ShowModal()
        dialog.Destroy()

        # Return focus to Fortnite after closing
        try:
            pyautogui.click(1919, 540)
        except Exception as e:
            logger.debug(f"Could not return focus to game: {e}")
    except Exception as e:
        logger.error(f"Error showing social GUI: {e}")
        speaker.speak("Error opening social menu")
