"""
Social Manager for FA11y
Background monitoring and virtual navigation for friends and party management
"""
import os
import json
import time
import logging
import threading
from typing import Optional, List, Dict
from datetime import datetime
from accessible_output2.outputs.auto import Auto

from lib.utilities.epic_social import (
    EpicSocial, Friend, FriendRequest, PartyInvite, PartyMember
)

logger = logging.getLogger(__name__)
speaker = Auto()


class SocialManager:
    """Manages social features with background monitoring and virtual UI navigation"""

    # Social views (navigation modes)
    VIEW_ALL_FRIENDS = "all_friends"
    VIEW_ONLINE_FRIENDS = "online_friends"
    VIEW_INCOMING_REQUESTS = "incoming_requests"
    VIEW_OUTGOING_REQUESTS = "outgoing_requests"
    VIEW_PARTY_MEMBERS = "party_members"
    VIEW_PARTY_INVITES = "party_invites"

    def __init__(self, epic_auth_instance):
        """
        Initialize Social Manager

        Args:
            epic_auth_instance: Instance of EpicAuth for authentication
        """
        self.auth = epic_auth_instance
        self.social_api = EpicSocial(epic_auth_instance) if epic_auth_instance else None

        # Cache file
        self.cache_file = "social_cache.json"

        # State management
        self.current_view = self.VIEW_ALL_FRIENDS
        self.current_index = 0

        # Data storage
        self.all_friends: List[Friend] = []
        self.online_friends: List[Friend] = []
        self.incoming_requests: List[FriendRequest] = []
        self.outgoing_requests: List[FriendRequest] = []
        self.party_members: List[PartyMember] = []
        self.party_invites: List[PartyInvite] = []

        # Previous state for change detection
        self.prev_incoming_count = 0
        self.prev_outgoing_count = 0
        self.prev_party_invite_count = 0

        # Notification system
        self.pending_notification = None  # Current notification awaiting action
        self.notification_timer = None  # Timer for 15-second auto-decline
        self.notification_lock = threading.Lock()

        # Background monitoring
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.update_interval = 7  # seconds
        self.lock = threading.Lock()

        # Load cached data
        self.load_cache()

    def _validate_auth_token(self) -> bool:
        """
        Validate that the auth token is still valid

        Returns:
            True if valid, False if expired or invalid
        """
        if not self.auth or not self.auth.access_token:
            logger.debug("No auth or access token")
            return False

        # Check token expiration
        try:
            from datetime import datetime, timezone
            if hasattr(self.auth, 'expires_at') and self.auth.expires_at:
                # Parse expires_at to datetime
                if isinstance(self.auth.expires_at, str):
                    # Handle ISO format with Z or timezone offset
                    expires_at_str = self.auth.expires_at.replace('Z', '+00:00')
                    expires_at = datetime.fromisoformat(expires_at_str)
                else:
                    expires_at = self.auth.expires_at

                # Get current time in UTC for comparison
                now = datetime.now(timezone.utc)

                # Make expires_at timezone-aware if it isn't already
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)

                # Check if token expired
                if now >= expires_at:
                    logger.warning("Auth token expired")
                    return False
            else:
                # No expiration info - assume token might be invalid, return False to be safe
                logger.warning("No expiration info for auth token")
                return False

        except Exception as e:
            logger.error(f"Error validating token expiration: {e}")
            # If we can't validate, assume invalid to be safe
            return False

        return True

    def _is_account_id(self, text: str) -> bool:
        """
        Check if a string looks like an Epic account ID (UUID format)

        Args:
            text: String to check

        Returns:
            True if it looks like an account ID
        """
        import re
        # Epic account IDs are 32 hex characters (no dashes)
        # Example: fd598199500c4044a0c4f66083349548
        return bool(re.match(r'^[a-f0-9]{32}$', text.lower()))

    def _ensure_display_name(self, display_name: str) -> str:
        """
        Ensure we have a real display name, not an account ID.
        If it's an ID, try to fetch the real name.

        Args:
            display_name: Name to verify

        Returns:
            Real display name or original if fetch fails
        """
        if not self._is_account_id(display_name):
            return display_name

        # It's an account ID - try to fetch real name
        if self.social_api:
            try:
                real_name = self.social_api._get_display_name(display_name, use_placeholder=False)
                if real_name and not self._is_account_id(real_name):
                    logger.info(f"Fetched real name for {display_name}: {real_name}")
                    return real_name
            except Exception as e:
                logger.debug(f"Failed to fetch display name for {display_name}: {e}")

        # Return original if fetch failed
        return display_name

    def start_monitoring(self):
        """Start background monitoring thread"""
        if self.running:
            logger.warning("Social monitoring already running")
            return

        if not self.auth or not self.auth.access_token:
            logger.warning("Cannot start social monitoring: not authenticated")
            return

        # Validate token before starting monitoring
        if not self._validate_auth_token():
            logger.warning("Cannot start social monitoring: auth token expired")
            speaker.speak("Cannot start social features: authentication expired. Please re-authenticate.")
            return

        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Social monitoring started")

    def stop_monitoring(self):
        """Stop background monitoring thread"""
        if not self.running:
            return

        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        logger.info("Social monitoring stopped")

    def _monitor_loop(self):
        """Background monitoring loop"""
        # Delay initial fetch to let FA11y start without blocking
        logger.info("Social monitor starting, waiting 3 seconds before initial refresh...")
        time.sleep(3)

        # Initial fetch (now non-blocking thanks to lock refactor)
        self.refresh_all_data()
        logger.info("Initial social data refresh complete")

        while self.running:
            try:
                time.sleep(self.update_interval)
                if not self.running:
                    break

                # Refresh data
                self.refresh_all_data()

                # Check for new items and announce
                self._check_for_new_items()

            except Exception as e:
                logger.error(f"Error in social monitoring loop: {e}")
                time.sleep(5)  # Wait before retrying

    def refresh_all_data(self):
        """Refresh all social data from API"""
        if not self.social_api:
            return

        # Validate auth token first
        if not self._validate_auth_token():
            logger.warning("Skipping social data refresh due to invalid auth token")
            return

        try:
            # Make ALL API calls WITHOUT holding lock (can take 60+ seconds)
            friends = self.social_api.get_friends_list()
            requests = self.social_api.get_pending_requests()
            party = self.social_api.get_current_party()
            invites = self.social_api.get_party_invites()

            # Now acquire lock ONLY to update shared state (takes < 1ms)
            with self.lock:
                if friends is not None:
                    self.all_friends = friends
                    self.online_friends = [f for f in friends if f.status in ["online", "away"]]

                if requests is not None:
                    # Split into incoming and outgoing
                    self.incoming_requests = [r for r in requests if r.direction == "inbound"]
                    self.outgoing_requests = [r for r in requests if r.direction == "outbound"]

                if party is not None:
                    self.party_members = party

                if invites is not None:
                    self.party_invites = invites

                # Save to cache
                self.save_cache()

        except Exception as e:
            logger.error(f"Error refreshing social data: {e}")

    def _check_for_new_items(self):
        """Check for new friend requests or party invites and show notifications"""
        with self.lock:
            # Check for new incoming friend requests
            current_incoming_count = len(self.incoming_requests)
            if current_incoming_count > self.prev_incoming_count:
                new_count = current_incoming_count - self.prev_incoming_count
                if new_count == 1 and self.incoming_requests:
                    # Show notification for single new request
                    latest_request = self.incoming_requests[0]  # Assuming newest first
                    self._show_notification(latest_request, "friend_request")
                elif new_count > 1:
                    speaker.speak(f"{new_count} new incoming friend requests. Open social menu to review.")

            self.prev_incoming_count = current_incoming_count

            # Check for new outgoing friend requests (less common but tracked)
            current_outgoing_count = len(self.outgoing_requests)
            self.prev_outgoing_count = current_outgoing_count

            # Check for new party invites
            current_invite_count = len(self.party_invites)
            if current_invite_count > self.prev_party_invite_count:
                new_count = current_invite_count - self.prev_party_invite_count
                if new_count == 1 and self.party_invites:
                    latest_invite = self.party_invites[0]
                    self._show_notification(latest_invite, "party_invite")
                elif new_count > 1:
                    speaker.speak(f"{new_count} new party invites. Open social menu to review.")

            self.prev_party_invite_count = current_invite_count

    def _show_notification(self, item, item_type):
        """
        Show notification with 15-second timer

        Args:
            item: FriendRequest or PartyInvite object
            item_type: "friend_request" or "party_invite"
        """
        with self.notification_lock:
            # Cancel existing notification timer
            if self.notification_timer:
                self.notification_timer.cancel()

            # Store pending notification
            self.pending_notification = (item, item_type)

            # Announce notification
            name = self._ensure_display_name(
                item.display_name if item_type == "friend_request" else item.from_display_name
            )

            if item_type == "friend_request":
                speaker.speak(f"New friend request from {name}. Press Alt Y to accept, Alt D to decline. Auto-declines in 15 seconds.")
            else:  # party_invite
                speaker.speak(f"New party invite from {name}. Press Alt Y to accept, Alt D to decline. Auto-declines in 15 seconds.")

            # Start 15-second timer
            self.notification_timer = threading.Timer(15.0, self._notification_timeout)
            self.notification_timer.start()

    def _notification_timeout(self):
        """Auto-decline notification after 15 seconds"""
        with self.notification_lock:
            if self.pending_notification:
                item, item_type = self.pending_notification
                name = self._ensure_display_name(
                    item.display_name if item_type == "friend_request" else item.from_display_name
                )
                speaker.speak(f"Notification from {name} auto-declined.")
                self.pending_notification = None

    def accept_notification(self):
        """Accept pending notification (Alt+Y)"""
        with self.notification_lock:
            if not self.pending_notification:
                speaker.speak("No pending notification")
                return

            item, item_type = self.pending_notification
            self.pending_notification = None

            # Cancel timer
            if self.notification_timer:
                self.notification_timer.cancel()
                self.notification_timer = None

        # Perform accept action (outside lock)
        if item_type == "friend_request":
            self._accept_friend_request(item)
        else:  # party_invite
            self._accept_party_invite(item)

    def decline_notification(self):
        """Decline pending notification (Alt+D)"""
        with self.notification_lock:
            if not self.pending_notification:
                speaker.speak("No pending notification")
                return

            item, item_type = self.pending_notification
            self.pending_notification = None

            # Cancel timer
            if self.notification_timer:
                self.notification_timer.cancel()
                self.notification_timer = None

        # Perform decline action (outside lock)
        if item_type == "friend_request":
            self._decline_friend_request(item)
        else:  # party_invite
            self._decline_party_invite(item)

    def save_cache(self):
        """Save social data to cache file"""
        try:
            cache_data = {
                "all_friends": [f.to_dict() for f in self.all_friends],
                "online_friends": [f.to_dict() for f in self.online_friends],
                "pending_requests": [r.to_dict() for r in self.pending_requests],
                "party_members": [m.to_dict() for m in self.party_members],
                "party_invites": [i.to_dict() for i in self.party_invites],
                "last_updated": datetime.now().isoformat()
            }

            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

        except Exception as e:
            logger.error(f"Error saving social cache: {e}")

    def load_cache(self):
        """Load social data from cache file"""
        if not os.path.exists(self.cache_file):
            return

        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)

            self.all_friends = [Friend.from_dict(f) for f in cache_data.get("all_friends", [])]
            self.online_friends = [Friend.from_dict(f) for f in cache_data.get("online_friends", [])]
            self.pending_requests = [FriendRequest.from_dict(r) for r in cache_data.get("pending_requests", [])]
            self.party_members = [PartyMember.from_dict(m) for m in cache_data.get("party_members", [])]
            self.party_invites = [PartyInvite.from_dict(i) for i in cache_data.get("party_invites", [])]

            logger.info(f"Loaded social cache from {cache_data.get('last_updated')}")

        except Exception as e:
            logger.error(f"Error loading social cache: {e}")

    # ========== Navigation Methods ==========

    def cycle_view(self, direction: str = "forwards"):
        """
        Cycle between social views

        Args:
            direction: 'forwards' or 'backwards'
        """
        try:
            logger.info(f"Cycle view called (direction: {direction})")
            current_idx = self.view_order.index(self.current_view)

            if direction == "forwards":
                new_idx = (current_idx + 1) % len(self.view_order)
            else:
                new_idx = (current_idx - 1) % len(self.view_order)

            self.current_view = self.view_order[new_idx]
            self.current_index = 0  # Reset to first item in new view

            # Announce view change
            self._announce_view_switch()

            # Announce first item in new view
            self._announce_current_item()

        except Exception as e:
            logger.error(f"Error cycling view: {e}")
            speaker.speak("Error switching view")

    def navigate(self, direction: str):
        """
        Navigate within current view

        Args:
            direction: 'up' or 'down'
        """
        try:
            logger.info(f"Navigate called (direction: {direction})")
            items = self._get_current_view_items()

            if not items:
                speaker.speak(f"No items in {self._get_view_friendly_name()}")
                return

            if direction == "down":
                self.current_index = (self.current_index + 1) % len(items)
            else:  # up
                self.current_index = (self.current_index - 1) % len(items)

            # Announce current item
            self._announce_current_item()

        except Exception as e:
            logger.error(f"Error navigating: {e}")
            speaker.speak("Navigation error")

    def _get_current_view_items(self) -> List:
        """Get items for current view (copy-on-read, no blocking)"""
        with self.lock:
            # Copy list reference (instant, no blocking)
            if self.current_view == self.VIEW_ALL_FRIENDS:
                return list(self.all_friends)
            elif self.current_view == self.VIEW_ONLINE_FRIENDS:
                return list(self.online_friends)
            elif self.current_view == self.VIEW_INCOMING_REQUESTS:
                return list(self.incoming_requests)
            elif self.current_view == self.VIEW_OUTGOING_REQUESTS:
                return list(self.outgoing_requests)
            elif self.current_view == self.VIEW_PARTY_MEMBERS:
                return list(self.party_members)
            elif self.current_view == self.VIEW_PARTY_INVITES:
                return list(self.party_invites)
            else:
                return []

    def _get_view_friendly_name(self) -> str:
        """Get friendly name for current view"""
        names = {
            self.VIEW_ALL_FRIENDS: "All Friends",
            self.VIEW_ONLINE_FRIENDS: "Online Friends",
            self.VIEW_INCOMING_REQUESTS: "Incoming Friend Requests",
            self.VIEW_OUTGOING_REQUESTS: "Outgoing Friend Requests",
            self.VIEW_PARTY_MEMBERS: "Party Members",
            self.VIEW_PARTY_INVITES: "Party Invites"
        }
        return names.get(self.current_view, "Unknown")

    def _announce_view_switch(self):
        """Announce view change with summary"""
        # Read data with lock, release immediately
        view_name = self._get_view_friendly_name()
        items = self._get_current_view_items()  # Copy-on-read, lock released
        count = len(items)

        # Prepare announcement without holding lock
        if self.current_view == self.VIEW_ALL_FRIENDS:
            with self.lock:
                online_count = len(self.online_friends)
            speaker.speak(f"{view_name}. {count} total friends, {online_count} online")
        elif self.current_view == self.VIEW_ONLINE_FRIENDS:
            speaker.speak(f"{view_name}. {count} friends online")
        elif self.current_view == self.VIEW_INCOMING_REQUESTS:
            speaker.speak(f"{view_name}. {count} incoming requests")
        elif self.current_view == self.VIEW_OUTGOING_REQUESTS:
            speaker.speak(f"{view_name}. {count} outgoing requests")
        elif self.current_view == self.VIEW_PARTY_MEMBERS:
            speaker.speak(f"{view_name}. {count} members in party")
        elif self.current_view == self.VIEW_PARTY_INVITES:
            speaker.speak(f"{view_name}. {count} pending invites")

    def _announce_current_item(self):
        """Announce the currently selected item"""
        items = self._get_current_view_items()

        if not items or self.current_index >= len(items):
            return

        item = items[self.current_index]

        # Announce based on item type with index
        position_info = f"{self.current_index + 1} of {len(items)}, "

        if isinstance(item, Friend):
            self._announce_friend(item, position_info)
        elif isinstance(item, FriendRequest):
            self._announce_friend_request(item, position_info)
        elif isinstance(item, PartyInvite):
            self._announce_party_invite(item, position_info)
        elif isinstance(item, PartyMember):
            self._announce_party_member(item, position_info)

    def _announce_friend(self, friend: Friend, position_info: str = ""):
        """Announce friend details"""
        # Ensure we have real display name, not account ID
        display_name = self._ensure_display_name(friend.display_name)
        parts = [display_name]

        if friend.status == "online":
            parts.append("online")
            if friend.currently_playing:
                parts.append(f"playing {friend.currently_playing}")
        elif friend.status == "away":
            parts.append("away")
        else:
            parts.append("offline")

        # Add position info at the end (e.g., "Thanos, offline, 26 of 160")
        if position_info:
            parts.append(position_info.rstrip(", "))

        speaker.speak(", ".join(parts))

    def _announce_friend_request(self, request: FriendRequest, position_info: str = ""):
        """Announce friend request details"""
        # Ensure we have real display name, not account ID
        display_name = self._ensure_display_name(request.display_name)

        if request.direction == "inbound":
            if position_info:
                speaker.speak(f"Friend request from {display_name}, {position_info.rstrip(', ')}")
            else:
                speaker.speak(f"Friend request from {display_name}")
        else:
            if position_info:
                speaker.speak(f"Friend request sent to {display_name}, {position_info.rstrip(', ')}")
            else:
                speaker.speak(f"Friend request sent to {display_name}")

    def _announce_party_invite(self, invite: PartyInvite, position_info: str = ""):
        """Announce party invite details"""
        # Ensure we have real display name, not account ID
        display_name = self._ensure_display_name(invite.from_display_name)

        if position_info:
            speaker.speak(f"Party invite from {display_name}, {position_info.rstrip(', ')}")
        else:
            speaker.speak(f"Party invite from {display_name}")

    def _announce_party_member(self, member: PartyMember, position_info: str = ""):
        """Announce party member details"""
        # Ensure we have real display name, not account ID
        display_name = self._ensure_display_name(member.display_name)

        if member.is_leader:
            if position_info:
                speaker.speak(f"{display_name}, party leader, {position_info.rstrip(', ')}")
            else:
                speaker.speak(f"{display_name}, party leader")
        else:
            if position_info:
                speaker.speak(f"{display_name}, {position_info.rstrip(', ')}")
            else:
                speaker.speak(display_name)

    # ========== Action Methods ==========

    def select_current(self):
        """
        Context-based select action (Enter key)
        Performs the primary action for the current view
        """
        items = self._get_current_view_items()

        if not items or self.current_index >= len(items):
            speaker.speak("No item selected")
            return

        item = items[self.current_index]

        # Context-based actions
        if self.current_view in [self.VIEW_ALL_FRIENDS, self.VIEW_ONLINE_FRIENDS]:
            # Friends view: Invite to party
            if isinstance(item, Friend):
                self._invite_friend_to_party(item)
        elif self.current_view == self.VIEW_INCOMING_REQUESTS:
            # Incoming requests: Accept
            if isinstance(item, FriendRequest):
                self._accept_friend_request(item)
        elif self.current_view == self.VIEW_OUTGOING_REQUESTS:
            # Outgoing requests: Cancel
            if isinstance(item, FriendRequest):
                self._decline_friend_request(item)
        elif self.current_view == self.VIEW_PARTY_MEMBERS:
            # Party members: Promote to leader
            if isinstance(item, PartyMember):
                if not item.is_leader:
                    self._promote_party_member(item)
                else:
                    speaker.speak("This member is already the party leader")
        elif self.current_view == self.VIEW_PARTY_INVITES:
            # Party invites: Accept
            if isinstance(item, PartyInvite):
                self._accept_party_invite(item)

    def accept_current(self):
        """
        Context-based accept/confirm action (Alt+Y)
        Quick accept for requests, promote for party, invite for friends
        """
        items = self._get_current_view_items()

        if not items or self.current_index >= len(items):
            speaker.speak("No item selected")
            return

        item = items[self.current_index]

        # Context-based accept actions
        if self.current_view in [self.VIEW_ALL_FRIENDS, self.VIEW_ONLINE_FRIENDS]:
            # Friends: Invite to party
            if isinstance(item, Friend):
                self._invite_friend_to_party(item)
        elif self.current_view == self.VIEW_INCOMING_REQUESTS:
            # Incoming requests: Accept
            if isinstance(item, FriendRequest):
                self._accept_friend_request(item)
        elif self.current_view == self.VIEW_PARTY_MEMBERS:
            # Party members: Promote
            if isinstance(item, PartyMember):
                if not item.is_leader:
                    self._promote_party_member(item)
                else:
                    speaker.speak("This member is already the party leader")
        elif self.current_view == self.VIEW_PARTY_INVITES:
            # Party invites: Accept
            if isinstance(item, PartyInvite):
                self._accept_party_invite(item)
        else:
            speaker.speak("No accept action for this view")

    def decline_current(self):
        """
        Context-based decline/remove action (Alt+D)
        Decline requests, remove friends, leave party, etc
        """
        items = self._get_current_view_items()

        if not items or self.current_index >= len(items):
            speaker.speak("No item selected")
            return

        item = items[self.current_index]

        # Context-based decline actions
        if self.current_view in [self.VIEW_ALL_FRIENDS, self.VIEW_ONLINE_FRIENDS]:
            # Friends: Remove friend
            if isinstance(item, Friend):
                self._remove_friend(item)
        elif self.current_view in [self.VIEW_INCOMING_REQUESTS, self.VIEW_OUTGOING_REQUESTS]:
            # Any requests: Decline/cancel
            if isinstance(item, FriendRequest):
                self._decline_friend_request(item)
        elif self.current_view == self.VIEW_PARTY_MEMBERS:
            # Party members: Leave party
            self.leave_party()
        elif self.current_view == self.VIEW_PARTY_INVITES:
            # Party invites: Decline
            if isinstance(item, PartyInvite):
                self._decline_party_invite(item)
        else:
            speaker.speak("No decline action for this view")

    def _accept_friend_request(self, request: FriendRequest):
        """Accept a friend request"""
        speaker.speak(f"Accepting friend request from {request.display_name}")

        try:
            success = self.social_api.accept_friend_request(request.account_id)

            if success:
                speaker.speak(f"{request.display_name} added as friend")
                # Refresh data
                threading.Thread(target=self.refresh_all_data, daemon=True).start()
            else:
                speaker.speak("Failed to accept friend request")

        except Exception as e:
            logger.error(f"Error accepting friend request: {e}")
            speaker.speak("Error accepting friend request")

    def _decline_friend_request(self, request: FriendRequest):
        """Decline a friend request"""
        speaker.speak(f"Declining friend request")

        try:
            success = self.social_api.decline_friend_request(request.account_id)

            if success:
                speaker.speak("Friend request declined")
                # Refresh data
                threading.Thread(target=self.refresh_all_data, daemon=True).start()
            else:
                speaker.speak("Failed to decline friend request")

        except Exception as e:
            logger.error(f"Error declining friend request: {e}")
            speaker.speak("Error declining friend request")

    def _accept_party_invite(self, invite: PartyInvite):
        """Accept a party invite"""
        speaker.speak(f"Joining {invite.from_display_name}'s party")

        try:
            success = self.social_api.accept_party_invite(invite.party_id)

            if success:
                speaker.speak("Joined party")
                # Refresh data
                threading.Thread(target=self.refresh_all_data, daemon=True).start()
            else:
                speaker.speak("Failed to join party")

        except Exception as e:
            logger.error(f"Error accepting party invite: {e}")
            speaker.speak("Error joining party")

    def _decline_party_invite(self, invite: PartyInvite):
        """Decline a party invite"""
        speaker.speak("Declining party invite")

        try:
            success = self.social_api.decline_party_invite(invite.party_id, invite.invite_id)

            if success:
                speaker.speak("Party invite declined")
                # Refresh data
                threading.Thread(target=self.refresh_all_data, daemon=True).start()
            else:
                speaker.speak("Failed to decline party invite")

        except Exception as e:
            logger.error(f"Error declining party invite: {e}")
            speaker.speak("Error declining party invite")

    def _remove_friend(self, friend: Friend):
        """Remove a friend"""
        speaker.speak(f"Removing {friend.display_name} from friends list")

        try:
            success = self.social_api.remove_friend(friend.account_id)

            if success:
                speaker.speak(f"{friend.display_name} removed from friends")
                # Refresh data
                threading.Thread(target=self.refresh_all_data, daemon=True).start()
            else:
                speaker.speak("Failed to remove friend")

        except Exception as e:
            logger.error(f"Error removing friend: {e}")
            speaker.speak("Error removing friend")

    def send_friend_request_prompt(self):
        """Prompt for username and send friend request"""
        try:
            import wx

            # Create text entry dialog
            dlg = wx.TextEntryDialog(
                None,
                "Enter Epic Games display name:",
                "Send Friend Request"
            )

            if dlg.ShowModal() == wx.ID_OK:
                username = dlg.GetValue().strip()
                dlg.Destroy()

                if username:
                    self._send_friend_request(username)
                else:
                    speaker.speak("No username entered")
            else:
                dlg.Destroy()
                speaker.speak("Cancelled")

        except Exception as e:
            logger.error(f"Error showing friend request prompt: {e}")
            speaker.speak("Error opening prompt")

    def _send_friend_request(self, username: str):
        """Send a friend request"""
        speaker.speak(f"Sending friend request to {username}")

        try:
            success = self.social_api.send_friend_request(username)

            if success:
                speaker.speak(f"Friend request sent to {username}")
                # Refresh data
                threading.Thread(target=self.refresh_all_data, daemon=True).start()
            else:
                speaker.speak(f"Failed to send friend request. User may not exist or is already a friend")

        except Exception as e:
            logger.error(f"Error sending friend request: {e}")
            speaker.speak("Error sending friend request")

    def _invite_friend_to_party(self, friend: Friend):
        """Invite a friend to party"""
        # Ensure real display name
        display_name = self._ensure_display_name(friend.display_name)
        speaker.speak(f"Inviting {display_name} to party")

        try:
            success = self.social_api.send_party_invite(friend.account_id)

            if success:
                speaker.speak(f"Party invite sent to {display_name}")
            else:
                speaker.speak("Failed to send party invite. Make sure you're in a party")

        except Exception as e:
            logger.error(f"Error sending party invite: {e}")
            speaker.speak("Error sending party invite")

    def _promote_party_member(self, member: PartyMember):
        """Promote a party member to leader"""
        # Ensure real display name
        display_name = self._ensure_display_name(member.display_name)
        speaker.speak(f"Promoting {display_name} to party leader")

        try:
            success = self.social_api.promote_party_member(member.account_id)

            if success:
                speaker.speak(f"{display_name} promoted to party leader")
                # Refresh party data
                self.refresh_all_data()
            else:
                speaker.speak("Failed to promote member. You may not be the party leader")

        except Exception as e:
            logger.error(f"Error promoting party member: {e}")
            speaker.speak("Error promoting party member")

    def leave_party(self):
        """Leave current party"""
        with self.lock:
            party_size = len(self.party_members)

        if party_size == 0:
            speaker.speak("You are not in a party")
            return

        speaker.speak(f"Leaving party of {party_size} members")

        try:
            success = self.social_api.leave_party()

            if success:
                speaker.speak("Left party")
                # Refresh party data
                self.refresh_all_data()
            else:
                speaker.speak("Failed to leave party")

        except Exception as e:
            logger.error(f"Error leaving party: {e}")
            speaker.speak("Error leaving party")

    def read_status(self):
        """Read current social status summary"""
        with self.lock:
            total_friends = len(self.all_friends)
            online_friends = len(self.online_friends)
            pending_in = sum(1 for r in self.pending_requests if r.direction == "inbound")
            pending_out = sum(1 for r in self.pending_requests if r.direction == "outbound")
            party_size = len(self.party_members)
            party_invites = len(self.party_invites)

            parts = [
                f"{total_friends} total friends",
                f"{online_friends} online"
            ]

            if pending_in > 0:
                parts.append(f"{pending_in} incoming friend requests")

            if pending_out > 0:
                parts.append(f"{pending_out} outgoing friend requests")

            if party_size > 0:
                parts.append(f"in party with {party_size} members")

            if party_invites > 0:
                parts.append(f"{party_invites} party invites")

            speaker.speak(". ".join(parts))


# Global social manager instance
_social_manager: Optional[SocialManager] = None


def get_social_manager(epic_auth_instance=None) -> SocialManager:
    """Get or create global social manager instance"""
    global _social_manager

    if _social_manager is None:
        _social_manager = SocialManager(epic_auth_instance)

    return _social_manager
