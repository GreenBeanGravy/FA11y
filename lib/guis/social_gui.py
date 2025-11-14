"""
Social Menu GUI for FA11y
Provides interface for managing friends, party, and requests
"""
import logging
import wx
import threading
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

        # Filter buttons
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.all_friends_btn = wx.RadioButton(panel, label="All Friends", style=wx.RB_GROUP)
        self.online_friends_btn = wx.RadioButton(panel, label="Online Only")
        self.all_friends_btn.SetValue(True)
        filter_sizer.Add(self.all_friends_btn, 0, wx.ALL, 5)
        filter_sizer.Add(self.online_friends_btn, 0, wx.ALL, 5)
        sizer.Add(filter_sizer, 0, wx.ALL, 5)

        # Friends list
        self.friends_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        sizer.Add(self.friends_list, 1, wx.EXPAND | wx.ALL, 5)

        # Action buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.invite_btn = wx.Button(panel, label="Invite to Party")
        self.remove_friend_btn = wx.Button(panel, label="Remove Friend")
        btn_sizer.Add(self.invite_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.remove_friend_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER, 5)

        # Bind events
        self.all_friends_btn.Bind(wx.EVT_RADIOBUTTON, self.refresh_friends_list)
        self.online_friends_btn.Bind(wx.EVT_RADIOBUTTON, self.refresh_friends_list)
        self.invite_btn.Bind(wx.EVT_BUTTON, self.on_invite_to_party)
        self.remove_friend_btn.Bind(wx.EVT_BUTTON, self.on_remove_friend)
        self.friends_list.Bind(wx.EVT_KEY_DOWN, self.on_friends_key_down)

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

    def refresh_friends_list(self, event=None):
        """Refresh friends list"""
        self.friends_list.Clear()

        with self.social_manager.lock:
            if self.online_friends_btn.GetValue():
                friends = list(self.social_manager.online_friends)
            else:
                friends = list(self.social_manager.all_friends)

        # Pre-fetch all display names in one go (cached, fast)
        for friend in friends:
            name = friend.display_name or friend.account_id or "Unknown"
            status = friend.status if friend.status != "offline" else ""
            label = f"{name} ({status})" if status else name
            self.friends_list.Append(label, friend)

        if friends:
            self.friends_list.SetSelection(0)
            speaker.speak(f"{len(friends)} friends")
        else:
            filter_type = "online friends" if self.online_friends_btn.GetValue() else "friends"
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
        for req in requests:
            name = req.display_name or req.account_id or "Unknown"
            direction = "from" if req.direction == "inbound" else "to"
            label = f"Request {direction} {name}"
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
        for member in members:
            name = member.display_name or member.account_id or "Unknown"
            label = f"{name} (Leader)" if member.is_leader else name
            self.party_list.Append(label, member)

        if members:
            self.party_list.SetSelection(0)
            speaker.speak(f"{len(members)} party members")
        else:
            speaker.speak("Not in a party")

    def on_friends_key_down(self, event):
        """Handle key press in friends list"""
        keycode = event.GetKeyCode()

        # Enter key sends party invite
        if keycode == wx.WXK_RETURN or keycode == wx.WXK_NUMPAD_ENTER:
            self.on_invite_to_party(event)
        else:
            event.Skip()  # Allow other keys to be processed normally

    def on_invite_to_party(self, event):
        """Invite selected friend to party"""
        sel = self.friends_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No friend selected")
            return

        friend = self.friends_list.GetClientData(sel)
        self.social_manager._invite_friend_to_party(friend)

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
            wx.CallLater(1000, self.refresh_friends_list)

    def on_accept_request(self, event):
        """Accept selected request"""
        sel = self.requests_list.GetSelection()
        if sel == wx.NOT_FOUND:
            speaker.speak("No request selected")
            return

        req = self.requests_list.GetClientData(sel)
        if req.direction == "inbound":
            self.social_manager._accept_friend_request(req)
            wx.CallLater(1000, self.refresh_requests_list)
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
        wx.CallLater(1000, self.refresh_requests_list)

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
    except Exception as e:
        logger.error(f"Error showing social GUI: {e}")
        speaker.speak("Error opening social menu")
