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

from lib.config.config_manager import config_manager
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

        # Register configs with config_manager
        config_manager.register('social_cache', 'config/social_cache.json',
                               format='json', default={})
        config_manager.register('favorite_friends', 'config/favorite_friends.json',
                               format='json', default=[])

        # State management
        self.current_view = self.VIEW_ALL_FRIENDS
        self.current_index = 0

        # Data storage (note: online status not available with current auth)
        self.all_friends: List[Friend] = []
        self.incoming_requests: List[FriendRequest] = []
        self.outgoing_requests: List[FriendRequest] = []
        self.party_members: List[PartyMember] = []
        self.party_invites: List[PartyInvite] = []

        # Favorite friends (store account IDs)
        self.favorite_friends: set = set()

        # Previous state for change detection
        self.prev_incoming_count = 0
        self.prev_outgoing_count = 0
        self.prev_party_invite_count = 0

        # Track outgoing join requests for auto-accept logic
        # Maps account_id -> (timestamp, display_name)
        self.outgoing_join_requests: Dict[str, tuple] = {}
        self.join_request_timeout = 30  # seconds

        # Notification system - queue based for handling multiple notifications
        self.notification_queue = []  # Queue of (item, item_type) tuples
        self.current_notification = None  # Currently active notification
        self.notification_timer = None  # Timer for 15-second auto-decline
        self.notification_lock = threading.Lock()

        # Background monitoring
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.fast_poll_interval = 5  # seconds - for invites and requests
        self.slow_poll_interval = 30  # seconds - for friends and party
        self.lock = threading.Lock()
        self.initial_data_loaded = threading.Event()  # Flag for initial data load completion

        # Load cached data
        self.load_cache()
        self.load_favorites()

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
        """
        Start background monitoring thread

        Note: Assumes auth token has already been validated by FA11y.py before calling this
        """
        if self.running:
            logger.warning("Social monitoring already running")
            return

        if not self.auth or not self.auth.access_token:
            logger.warning("Cannot start social monitoring: not authenticated")
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

    def wait_for_initial_data(self, timeout=10):
        """
        Wait for initial data to be loaded

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if data loaded, False if timeout
        """
        return self.initial_data_loaded.wait(timeout=timeout)

    def _monitor_loop(self):
        """Background monitoring loop with fast and slow polling"""
        # Delay initial fetch to let FA11y start without blocking
        logger.info("Social monitor starting, waiting 3 seconds before initial refresh...")
        time.sleep(3)

        # Initial fetch (now non-blocking thanks to lock refactor)
        self.refresh_all_data()
        logger.info("Initial social data refresh complete")
        self.initial_data_loaded.set()  # Signal that initial data is ready

        # Counter for slow poll cycles
        slow_poll_counter = 0
        cycles_per_slow_poll = self.slow_poll_interval // self.fast_poll_interval  # 30s / 5s = 6 cycles

        # Track if monitoring is paused due to invalid auth
        was_paused = False

        while self.running:
            try:
                time.sleep(self.fast_poll_interval)
                if not self.running:
                    break

                # Check if auth is still valid before making API calls
                if not self.social_api or not self.social_api.auth.is_valid:
                    if not was_paused:
                        logger.warning("Auth is invalid, pausing social monitoring (waiting for new auth)")
                        was_paused = True
                    # Wait longer when auth is invalid to avoid spamming logs
                    time.sleep(30)
                    continue

                # Auth is valid - check if we're resuming from pause
                if was_paused:
                    logger.info("Auth is now valid, resuming social monitoring")
                    was_paused = False
                    # Do a full refresh after resuming
                    self.refresh_all_data()

                # Fast poll: invites and requests (every 5 seconds)
                self.refresh_fast_data()

                # Slow poll: friends and party (every 30 seconds)
                slow_poll_counter += 1
                if slow_poll_counter >= cycles_per_slow_poll:
                    self.refresh_slow_data()
                    slow_poll_counter = 0

                # Check for new items and announce
                self._check_for_new_items()

            except Exception as e:
                logger.error(f"Error in social monitoring loop: {e}")
                time.sleep(5)  # Wait before retrying

    def refresh_all_data(self):
        """Refresh all social data from API"""
        if not self.social_api:
            return

        # Don't make API calls if auth is invalid
        if not self.social_api.auth.is_valid:
            logger.debug("Skipping social data refresh - auth is invalid")
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

    def refresh_fast_data(self):
        """Refresh fast-changing data: party invites and friend requests (5s interval)"""
        if not self.social_api:
            return

        # Don't make API calls if auth is invalid
        if not self.social_api.auth.is_valid:
            logger.debug("Skipping fast data refresh - auth is invalid")
            return

        try:
            # Make API calls WITHOUT holding lock
            requests = self.social_api.get_pending_requests()
            invites = self.social_api.get_party_invites()

            # Acquire lock ONLY to update shared state
            with self.lock:
                if requests is not None:
                    # Split into incoming and outgoing
                    self.incoming_requests = [r for r in requests if r.direction == "inbound"]
                    self.outgoing_requests = [r for r in requests if r.direction == "outbound"]

                if invites is not None:
                    self.party_invites = invites

        except Exception as e:
            logger.error(f"Error refreshing fast data: {e}")

    def refresh_slow_data(self):
        """Refresh slow-changing data: friends list and party members (30s interval)"""
        if not self.social_api:
            return

        # Don't make API calls if auth is invalid
        if not self.social_api.auth.is_valid:
            logger.debug("Skipping slow data refresh - auth is invalid")
            return

        try:
            # Make API calls WITHOUT holding lock
            friends = self.social_api.get_friends_list()
            party = self.social_api.get_current_party()

            # Acquire lock ONLY to update shared state
            with self.lock:
                if friends is not None:
                    self.all_friends = friends

                if party is not None:
                    self.party_members = party

                # Save to cache after slow refresh
                self.save_cache()

        except Exception as e:
            logger.error(f"Error refreshing slow data: {e}")

    def _cleanup_old_join_requests(self):
        """Remove join requests older than timeout period"""
        now = datetime.now()
        expired = []

        for account_id, (timestamp, display_name) in self.outgoing_join_requests.items():
            age = (now - timestamp).total_seconds()
            if age > self.join_request_timeout:
                expired.append(account_id)

        for account_id in expired:
            del self.outgoing_join_requests[account_id]
            logger.debug(f"Cleaned up expired join request for {account_id}")

    def _check_for_new_items(self):
        """Check for new friend requests or party invites and show notifications"""
        # Clean up old join requests first
        self._cleanup_old_join_requests()

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

                    # Check if this invite is from someone we sent a join request to
                    from_account_id = latest_invite.from_account_id
                    if from_account_id in self.outgoing_join_requests:
                        timestamp, display_name = self.outgoing_join_requests[from_account_id]
                        age = (datetime.now() - timestamp).total_seconds()

                        if age <= self.join_request_timeout:
                            # Check if we can auto-accept (Fortnite must be focused)
                            from lib.utilities.window_utils import get_active_window_title
                            active_title = get_active_window_title()
                            
                            if active_title and "Fortnite" in active_title:
                                # Auto-accept! They accepted our join request
                                logger.info(f"Auto-accepting invite from {display_name} (responded to our join request)")
                                # Remove from tracking
                                del self.outgoing_join_requests[from_account_id]
                                # Accept outside of lock
                                threading.Thread(
                                    target=self._auto_accept_party_invite,
                                    args=(latest_invite, display_name),
                                    daemon=True
                                ).start()
                            else:
                                # Fortnite not focused, treat as normal invite
                                logger.info(f"Cannot auto-accept invite from {display_name}: Fortnite not focused")
                                self._show_notification(latest_invite, "party_invite")
                        else:
                            # Expired, show normal notification
                            self._show_notification(latest_invite, "party_invite")
                    else:
                        # Normal invite, show notification
                        self._show_notification(latest_invite, "party_invite")
                elif new_count > 1:
                    speaker.speak(f"{new_count} new party invites. Open social menu to review.")
            
            self.prev_party_invite_count = current_invite_count

        # Check for party changes (joins/leaves)
        # We need to get the current party members to compare
        # This assumes refresh_slow_data or similar updates self.party_members periodically
        # or we rely on the fact that we just refreshed data if we are here?
        # Actually, _monitor_loop calls refresh_slow_data which updates self.party_members.
        # We need to store the *previous* state to compare.
        
        # Initialize prev_party_members if not exists
        if not hasattr(self, 'prev_party_members_ids'):
            self.prev_party_members_ids = set()
            if self.party_members:
                self.prev_party_members_ids = {m.account_id for m in self.party_members}
        
        current_member_ids = {m.account_id for m in self.party_members} if self.party_members else set()
        
        # Calculate diffs
        joined_ids = current_member_ids - self.prev_party_members_ids
        left_ids = self.prev_party_members_ids - current_member_ids
        
        # Announce joins
        for member_id in joined_ids:
            # Find member object for name
            member = next((m for m in self.party_members if m.account_id == member_id), None)
            name = member.display_name if member else "Player"
            # Don't announce our own join if we just started
            if member_id != self.social_api.auth.account_id: 
                 speaker.speak(f"{name} joined the party")
        
        # Announce leaves
        for member_id in left_ids:
            # We can't look up name in current members, need to rely on cache or generic
            # Ideally we'd have kept the old member objects, but for now:
            name = self.social_api._get_display_name(member_id) # This uses cache
            if member_id != self.social_api.auth.account_id:
                speaker.speak(f"{name} left the party")
                
        self.prev_party_members_ids = current_member_ids

    def _show_notification(self, item, item_type):
        """
        Show notification with 15-second timer (queue-based)

        Args:
            item: FriendRequest or PartyInvite object
            item_type: "friend_request" or "party_invite"
        """
        with self.notification_lock:
            # Add to queue
            self.notification_queue.append((item, item_type))

            # If no current notification is active, process this one
            if self.current_notification is None:
                self._process_next_notification()

    def _process_next_notification(self):
        """Process the next notification in queue (must be called with lock held)"""
        if not self.notification_queue:
            return

        # Get next notification from queue
        item, item_type = self.notification_queue.pop(0)
        self.current_notification = (item, item_type)

        # Announce notification
        name = self._ensure_display_name(
            item.display_name if item_type == "friend_request" else item.from_display_name
        )

        if item_type == "friend_request":
            speaker.speak(f"New friend request from {name}. Press Alt Y to accept, Alt N to decline. Auto-declines in 15 seconds.")
        else:  # party_invite
            speaker.speak(f"New party invite from {name}. Press Alt Y to accept, Alt N to decline. Auto-declines in 15 seconds.")

        # Start 15-second timer
        self.notification_timer = threading.Timer(15.0, self._notification_timeout)
        self.notification_timer.start()

    def _notification_timeout(self):
        """Handle notification timeout - do NOT auto-decline, just clear current notification"""
        with self.notification_lock:
            if self.current_notification:
                # Just clear the current notification so we can process others or wait
                # We do NOT decline it. It stays in the pending list on the server.
                self.current_notification = None
                
                # Process next notification if any
                self._process_next_notification()

    def accept_notification(self):
        """Accept current notification (Alt+Y) and process next in queue"""
        with self.notification_lock:
            if not self.current_notification:
                speaker.speak("No pending notification")
                return

            item, item_type = self.current_notification
            self.current_notification = None

            # Cancel timer
            if self.notification_timer:
                self.notification_timer.cancel()
                self.notification_timer = None

        # Perform accept action (outside lock)
        if item_type == "friend_request":
            self._accept_friend_request(item)
        else:  # party_invite
            self._accept_party_invite(item)

        # Process next notification after accepting
        with self.notification_lock:
            self._process_next_notification()

    def decline_notification(self):
        """Decline current notification (Alt+N) and process next in queue"""
        with self.notification_lock:
            if not self.current_notification:
                speaker.speak("No pending notification")
                return

            item, item_type = self.current_notification
            self.current_notification = None

            # Cancel timer
            if self.notification_timer:
                self.notification_timer.cancel()
                self.notification_timer = None

        # Perform decline action (outside lock)
        if item_type == "friend_request":
            self._decline_friend_request(item)
        else:  # party_invite
            self._decline_party_invite(item)

        # Process next notification after declining
        with self.notification_lock:
            self._process_next_notification()

    def save_cache(self):
        """Save social data to cache file"""
        try:
            cache_data = {
                "all_friends": [f.to_dict() for f in self.all_friends],
                "incoming_requests": [r.to_dict() for r in self.incoming_requests],
                "outgoing_requests": [r.to_dict() for r in self.outgoing_requests],
                "party_members": [m.to_dict() for m in self.party_members],
                "party_invites": [i.to_dict() for i in self.party_invites],
                "last_updated": datetime.now().isoformat()
            }
            config_manager.set('social_cache', data=cache_data)
        except Exception as e:
            logger.error(f"Error saving social cache: {e}")

    def load_cache(self):
        """Load social data from cache file"""
        try:
            cache_data = config_manager.get('social_cache')
            if not cache_data:
                return

            self.all_friends = [Friend.from_dict(f) for f in cache_data.get("all_friends", [])]
            # Load both old "pending_requests" and new split format for backwards compatibility
            self.incoming_requests = [FriendRequest.from_dict(r) for r in cache_data.get("incoming_requests", [])]
            self.outgoing_requests = [FriendRequest.from_dict(r) for r in cache_data.get("outgoing_requests", [])]
            # Fallback to old format if new format not available
            if not self.incoming_requests and not self.outgoing_requests:
                pending = [FriendRequest.from_dict(r) for r in cache_data.get("pending_requests", [])]
                self.incoming_requests = [r for r in pending if r.direction == "inbound"]
                self.outgoing_requests = [r for r in pending if r.direction == "outbound"]
            self.party_members = [PartyMember.from_dict(m) for m in cache_data.get("party_members", [])]
            self.party_invites = [PartyInvite.from_dict(i) for i in cache_data.get("party_invites", [])]

            logger.info(f"Loaded social cache from {cache_data.get('last_updated')}")

        except Exception as e:
            logger.error(f"Error loading social cache: {e}")

    def load_favorites(self):
        """Load favorite friends from file"""
        try:
            data = config_manager.get('favorite_friends')
            if not data:
                return

            # Handle both old format (dict with 'favorites' key) and new format (list)
            if isinstance(data, dict):
                self.favorite_friends = set(data.get("favorites", []))
            elif isinstance(data, list):
                self.favorite_friends = set(data)
            else:
                self.favorite_friends = set()

            logger.info(f"Loaded {len(self.favorite_friends)} favorite friends")
        except Exception as e:
            logger.error(f"Error loading favorites: {e}")

    def save_favorites(self):
        """Save favorite friends to file"""
        try:
            # Save as list for simpler format
            config_manager.set('favorite_friends', data=list(self.favorite_friends))
        except Exception as e:
            logger.error(f"Error saving favorites: {e}")

    def toggle_favorite(self, friend: Friend):
        """Toggle a friend as favorite"""
        if friend.account_id in self.favorite_friends:
            self.favorite_friends.remove(friend.account_id)
            display_name = self._ensure_display_name(friend.display_name)
            speaker.speak(f"{display_name} removed from favorites")
        else:
            self.favorite_friends.add(friend.account_id)
            display_name = self._ensure_display_name(friend.display_name)
            speaker.speak(f"{display_name} added to favorites")
        self.save_favorites()

    def is_favorite(self, friend: Friend) -> bool:
        """Check if a friend is favorited"""
        return friend.account_id in self.favorite_friends

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
            speaker.speak(f"{view_name}. {count} friends")
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
        """Announce friend details (online status not available)"""
        # Ensure we have real display name, not account ID
        display_name = self._ensure_display_name(friend.display_name)

        # Add position info if available (e.g., "Thanos, 26 of 160")
        if position_info:
            speaker.speak(f"{display_name}, {position_info.rstrip(', ')}")
        else:
            speaker.speak(display_name)

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

    def _minimize_social_gui_safe(self):
        """Minimize social GUI if open - thread-safe version"""
        import wx

        minimized_window = [None]  # Use list to allow modification in nested function

        def _do_minimize():
            """Run on main thread"""
            try:
                app = wx.GetApp()
                if app:
                    for window in wx.GetTopLevelWindows():
                        if window.IsShown() and window.GetTitle() == "Social Menu":
                            window.Iconize(True)
                            minimized_window[0] = window
                            break
            except Exception as e:
                logger.error(f"Error minimizing GUI: {e}")

        # Schedule on main thread and wait for completion
        if wx.IsMainThread():
            _do_minimize()
        else:
            wx.CallAfter(_do_minimize)
            time.sleep(0.3)  # Give main thread time to process

        return minimized_window[0]

    def _restore_social_gui_safe(self, window):
        """Restore social GUI - thread-safe version"""
        import wx

        if not window:
            return

        def _do_restore():
            """Run on main thread"""
            try:
                window.Iconize(False)
                window.Raise()
                window.SetFocus()
            except Exception as e:
                logger.debug(f"Could not restore window: {e}")

        # Schedule on main thread
        if wx.IsMainThread():
            _do_restore()
        else:
            wx.CallAfter(_do_restore)

    def _accept_party_invite(self, invite: PartyInvite, gui_window=None):
        """Accept a party invite using Fortnite client (ESC key method)"""
        speaker.speak(f"Joining {invite.from_display_name}'s party")

        try:
            import pyautogui
            from lib.utilities.window_utils import focus_fortnite

            # Minimize social GUI if open (thread-safe)
            minimized_window = self._minimize_social_gui_safe()

            # Focus Fortnite window (uses process name, more reliable)
            if focus_fortnite():
                time.sleep(0.3)  # Give window time to focus

                # Click center of screen to ensure Fortnite is ready
                screen_width, screen_height = pyautogui.size()
                center_x = screen_width // 2
                center_y = screen_height // 2
                pyautogui.click(center_x, center_y)
                time.sleep(0.2)

                # Hold ESC for 1.5 seconds to accept through Fortnite client
                pyautogui.keyDown('escape')
                time.sleep(1.5)
                pyautogui.keyUp('escape')

                # Extra hold escape to ensure acceptance
                time.sleep(0.2)
                pyautogui.keyDown('escape')
                time.sleep(1.5)
                pyautogui.keyUp('escape')
            else:
                logger.warning(f"Cannot accept invite: Failed to focus Fortnite")
                speaker.speak("Cannot join. Failed to focus Fortnite.")

            # Give it a moment to process
            time.sleep(2)

            # Restore the window if it was minimized (thread-safe)
            self._restore_social_gui_safe(minimized_window)

            # Check if we joined by monitoring party members
            initial_party_size = len(self.party_members)
            self.refresh_all_data()
            new_party_size = len(self.party_members)

            if new_party_size > initial_party_size:
                speaker.speak("Joined party")
            else:
                # Still might have joined, refresh again
                time.sleep(1)
                self.refresh_all_data()
                if len(self.party_members) > initial_party_size:
                    speaker.speak("Joined party")

        except Exception as e:
            logger.error(f"Error accepting party invite: {e}")
            speaker.speak("Error joining party")

    def _auto_accept_party_invite(self, invite: PartyInvite, display_name: str):
        """Auto-accept a party invite (when they respond to our join request) using Fortnite client"""
        speaker.speak(f"{display_name} accepted your request. Joining party...")

        try:
            import pyautogui
            from lib.utilities.window_utils import focus_fortnite

            # Minimize social GUI if open (thread-safe)
            minimized_window = self._minimize_social_gui_safe()

            # Focus Fortnite window (uses process name, more reliable)
            if focus_fortnite():
                time.sleep(0.3)  # Give window time to focus

                # Click center of screen to ensure Fortnite is ready
                screen_width, screen_height = pyautogui.size()
                center_x = screen_width // 2
                center_y = screen_height // 2
                pyautogui.click(center_x, center_y)
                time.sleep(0.2)

                # Hold ESC for 1.5 seconds to accept through Fortnite client
                pyautogui.keyDown('escape')
                time.sleep(1.5)
                pyautogui.keyUp('escape')

                # Extra hold escape to ensure acceptance
                time.sleep(0.2)
                pyautogui.keyDown('escape')
                time.sleep(1.5)
                pyautogui.keyUp('escape')
            else:
                logger.warning(f"Cannot auto-accept invite: Failed to focus Fortnite")
                # We don't speak here to avoid interrupting, just log

            # Monitor party status to see if join was successful
            time.sleep(2)

            # Restore the window if it was minimized (thread-safe)
            self._restore_social_gui_safe(minimized_window)

            # Check if we joined by monitoring party members
            initial_party_size = len(self.party_members)
            self.refresh_all_data()
            new_party_size = len(self.party_members)

            if new_party_size > initial_party_size:
                speaker.speak("Joined party")
            else:
                # Still might have joined, refresh again
                time.sleep(1)
                self.refresh_all_data()
                if len(self.party_members) > initial_party_size:
                    speaker.speak("Joined party")

        except Exception as e:
            logger.error(f"Error auto-accepting party invite: {e}")
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

    def _send_friend_request_by_account_id(self, account_id: str, display_name: str):
        """Send a friend request by account ID"""
        speaker.speak(f"Sending friend request to {display_name}")

        try:
            # Send friend request directly using account ID
            import requests
            response = requests.post(
                f"{self.social_api.FRIENDS_BASE}/{self.auth.account_id}/friends/{account_id}",
                headers=self.social_api._get_headers(),
                timeout=5
            )

            if response.status_code in [200, 201, 204]:
                logger.info(f"Successfully sent friend request to {display_name}")
                speaker.speak(f"Friend request sent to {display_name}")
                # Refresh data
                threading.Thread(target=self.refresh_all_data, daemon=True).start()
            else:
                logger.error(f"Failed to send friend request: {response.status_code} - {response.text}")
                speaker.speak(f"Failed to send friend request. User may have friend requests disabled")

        except Exception as e:
            logger.error(f"Error sending friend request: {e}")
            speaker.speak("Error sending friend request")

    def _invite_friend_to_party(self, friend: Friend):
        """Invite a friend to party"""
        # Ensure real display name
        display_name = self._ensure_display_name(friend.display_name)
        speaker.speak(f"Inviting {display_name} to party")

        try:
            result = self.social_api.send_party_invite(friend.account_id)

            if result == True:
                speaker.speak(f"Party invite sent to {display_name}")
            elif result == "already_sent":
                speaker.speak(f"Party invite sent to {display_name}") # Treat as success for user feedback
            else:
                # Retry logic for party detection
                logger.info("Initial invite failed, retrying party detection...")
                self.refresh_slow_data() # Refresh party info
                
                # Try 2 more times
                for i in range(2):
                    if self.social_api.send_party_invite(friend.account_id):
                        speaker.speak(f"Party invite sent to {display_name}")
                        return
                
                speaker.speak("Failed to send party invite. Make sure you're in a party")

        except Exception as e:
            logger.error(f"Error sending party invite: {e}")
            speaker.speak("Error sending party invite")

    def _request_to_join_party(self, friend: Friend):
        """Request to join a friend's party"""
        # Ensure real display name
        display_name = self._ensure_display_name(friend.display_name)
        speaker.speak(f"Requesting to join {display_name}'s party")

        try:
            result = self.social_api.request_to_join_party(friend.account_id)

            if result == True:
                # Track this join request for auto-accept logic
                self.outgoing_join_requests[friend.account_id] = (datetime.now(), display_name)
                logger.info(f"Tracking join request to {display_name} for auto-accept")
                speaker.speak(f"Join request sent to {display_name}")
            elif result == "already_sent":
                # Still track it in case we get an invite
                self.outgoing_join_requests[friend.account_id] = (datetime.now(), display_name)
                speaker.speak(f"Join request sent to {display_name}") # Treat as success
            elif result == "no_party":
                # Friend has no party, invite them to ours instead
                logger.info(f"{display_name} has no party, inviting them to join us")
                speaker.speak(f"{display_name} has no party. Inviting them to join you")

                # Send party invite
                invite_result = self.social_api.send_party_invite(friend.account_id)
                if invite_result:
                    speaker.speak(f"Invited {display_name} to your party")
                else:
                    speaker.speak(f"Failed to invite {display_name}")
            else:
                speaker.speak("Failed to send join request")

        except Exception as e:
            logger.error(f"Error sending join request: {e}")
            speaker.speak("Error sending join request")

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
            pending_in = len(self.incoming_requests)
            pending_out = len(self.outgoing_requests)
            party_size = len(self.party_members)
            party_invites = len(self.party_invites)

            parts = [f"{total_friends} friends"]

            if pending_in > 0:
                parts.append(f"{pending_in} incoming friend requests")

            if pending_out > 0:
                parts.append(f"{pending_out} outgoing friend requests")

            if party_size > 0:
                parts.append(f"in party with {party_size} members")

            if party_invites > 0:
                parts.append(f"{party_invites} party invites")

            speaker.speak(". ".join(parts))

    def kick_party_member(self, account_id: str):
        """Kick a member from the party"""
        # Get display name for speech
        member = next((m for m in self.party_members if m.account_id == account_id), None)
        name = member.display_name if member else "Player"
        
        speaker.speak(f"Kicking {name} from party")
        
        try:
            if self.social_api.kick_party_member(account_id):
                speaker.speak(f"Kicked {name}")
                self.refresh_slow_data() # Refresh party list
            else:
                speaker.speak("Failed to kick player")
        except Exception as e:
            logger.error(f"Error kicking party member: {e}")
            speaker.speak("Error kicking player")

    def force_refresh_data(self, data_type: str = "all"):
        """
        Force immediate refresh of social data
        
        Args:
            data_type: "all", "friends", "requests", or "party"
        """
        if data_type == "all":
            self.refresh_all_data()
        elif data_type == "friends":
            self.refresh_slow_data()
        elif data_type == "requests":
            self.refresh_fast_data()
        elif data_type == "party":
            self.refresh_slow_data()


# Global social manager instance
_social_manager: Optional[SocialManager] = None


def get_social_manager(epic_auth_instance=None) -> SocialManager:
    """Get or create global social manager instance"""
    global _social_manager

    if _social_manager is None:
        _social_manager = SocialManager(epic_auth_instance)

    return _social_manager


