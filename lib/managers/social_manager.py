"""
Social Manager for FA11y
Background monitoring and virtual navigation for friends and party management
"""
import time
import logging
import threading
from typing import Optional, List, Dict
from datetime import datetime, timezone
from accessible_output2.outputs.auto import Auto
from lib.app.speech import simple

from lib.config.config_manager import config_manager
from lib.utilities.epic_social import (
    EpicSocial, Friend, FriendRequest, PartyInvite, PartyMember
)

logger = logging.getLogger(__name__)
speaker = Auto()


# Fortnite's 2026-04-16 rank expansion split Elite and Champion into I/II/III
# sub-tiers, growing the ladder from 18 ranks to 22. Track entries with a
# lastUpdated timestamp before this cutoff were stored under the old ladder
# (Elite=16, Champion=17, Unreal=18); entries at or after use the new ladder
# (Elite I/II/III=16-18, Champion I/II/III=19-21, Unreal=22). The cutoff is
# intentionally set a little before the patch's actual release so any pre-patch
# data is correctly detected as pre-expansion.
_RANK_EXPANSION_UTC = datetime(2026, 4, 16, 10, 0, 0, tzinfo=timezone.utc)


def _is_pre_rank_expansion(last_updated: str) -> bool:
    """Return True if the given ISO8601 lastUpdated timestamp is strictly
    before the 2026-04-16 rank expansion cutoff. Empty or unparseable strings
    return False so the caller defaults to the current mapping."""
    if not last_updated:
        return False
    try:
        ts = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts < _RANK_EXPANSION_UTC


def friend_name(friend) -> str:
    return friend.display_name or friend.account_id or "Unknown"


def friends_count_text(count: int, favorites_only: bool = False) -> str:
    kind = "favorite friends" if favorites_only else "friends"
    return f"{count} {kind}" if count else f"No {kind}"


def requests_count_text(count: int, incoming: bool = True) -> str:
    kind = "incoming" if incoming else "outgoing"
    return f"{count} {kind} requests" if count else f"No {kind} friend requests"


def party_count_text(count: int) -> str:
    return f"{count} party members" if count else "Not in a party"


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

        # Ranked progress tracking for change detection
        self.prev_ranked_progress: Dict[str, Dict] = {}  # Maps ranking_type -> {currentDivision, promotionProgress}

        # Track outgoing join requests for auto-accept logic
        # Maps account_id -> (timestamp, display_name)
        self.outgoing_join_requests: Dict[str, tuple] = {}
        self.join_request_timeout = 30  # seconds

        # Notification system - queue based for handling multiple notifications
        self.notification_queue = []  # Queue of (item, item_type) tuples
        self.current_notification = None  # Currently active notification
        self.notification_timer = None  # Timer for 15-second queue progression (if more notifications waiting)
        self.notification_lock = threading.Lock()

        # Background monitoring
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.fast_poll_interval = 5  # seconds - for invites and requests
        self.slow_poll_interval = 30  # seconds - for friends and party
        self.lock = threading.Lock()
        self.initial_data_loaded = threading.Event()  # Flag for initial data load completion

        # Windows that want to know when the lists change (the hub's Social page)
        self.change_listeners: list = []
        self._change_signature = None

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

    def resolve_name_from_partial_id(self, id_or_partial: str) -> Optional[str]:
        """
        Resolve an MCP id - full 32-char or an abbreviated
        '<prefix>...<suffix>' form that Fortnite writes in party-event log
        lines - to a display name by matching against cached friends and
        party members. Returns None when no match is found so the caller
        can fall back to speaking the id.

        Called by MatchEventMonitor via the name_resolver callback wired
        up in FA11y.main(); safe to call from any thread (read-only scan
        of caches under the social manager lock).
        """
        if not id_or_partial:
            return None

        # Split once if it's the abbreviated form. Full 32-char hex ids
        # don't contain '...', so this is a clean discriminator.
        if '...' in id_or_partial:
            parts = id_or_partial.split('...', 1)
            if len(parts) != 2 or not parts[0] or not parts[1]:
                return None
            prefix, suffix = parts
            match_fn = lambda aid: aid.startswith(prefix) and aid.endswith(suffix)
        else:
            match_fn = lambda aid: aid == id_or_partial

        with self.lock:
            for f in self.all_friends:
                if match_fn(f.account_id):
                    return self._ensure_display_name(f.display_name)
            for m in self.party_members:
                if match_fn(m.account_id):
                    return self._ensure_display_name(m.display_name)
            for r in self.incoming_requests:
                if match_fn(r.account_id):
                    return self._ensure_display_name(r.display_name)
            for r in self.outgoing_requests:
                if match_fn(r.account_id):
                    return self._ensure_display_name(r.display_name)
            for inv in self.party_invites:
                if match_fn(inv.from_account_id):
                    return self._ensure_display_name(inv.from_display_name)
        return None

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
        logger.debug("Social monitoring started")

    def stop_monitoring(self):
        """Stop background monitoring thread"""
        if not self.running:
            return

        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        logger.debug("Social monitoring stopped")

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
        logger.debug("Social monitor starting, waiting 3 seconds before initial refresh...")
        time.sleep(3)

        # Initial fetch (now non-blocking thanks to lock refactor)
        self.refresh_all_data()
        logger.debug("Initial social data refresh complete")
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
                    logger.debug("Auth is now valid, resuming social monitoring")
                    was_paused = False
                    # Do a full refresh after resuming
                    self.refresh_all_data()

                # Fast poll: invites, requests, and ranked progress (every 5 seconds)
                self.refresh_fast_data()
                self._check_ranked_progress()

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

            self.notify_changed()

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

            self.notify_changed()

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

            self.notify_changed()

        except Exception as e:
            logger.error(f"Error refreshing slow data: {e}")

    def _division_to_rank_name(self, division: int, last_updated: Optional[str] = None) -> str:
        """
        Convert division number to human-readable rank name.
        In Fortnite: I is lowest, II is middle, III is highest within each tier.

        If last_updated is supplied and predates the 2026-04-16 rank expansion,
        the legacy (pre-expansion) mapping is used so stored pre-patch ranks
        still display correctly. Omitting last_updated uses the current mapping.
        """
        if last_updated and _is_pre_rank_expansion(last_updated):
            return self._division_to_rank_name_legacy(division)
        if division == 0:
            return "Unranked"
        elif 1 <= division <= 3:
            tier = ["I", "II", "III"][division - 1]
            return f"Bronze {tier}"
        elif 4 <= division <= 6:
            tier = ["I", "II", "III"][division - 4]
            return f"Silver {tier}"
        elif 7 <= division <= 9:
            tier = ["I", "II", "III"][division - 7]
            return f"Gold {tier}"
        elif 10 <= division <= 12:
            tier = ["I", "II", "III"][division - 10]
            return f"Platinum {tier}"
        elif 13 <= division <= 15:
            tier = ["I", "II", "III"][division - 13]
            return f"Diamond {tier}"
        elif 16 <= division <= 18:
            tier = ["I", "II", "III"][division - 16]
            return f"Elite {tier}"
        elif 19 <= division <= 21:
            tier = ["I", "II", "III"][division - 19]
            return f"Champion {tier}"
        elif division == 22:
            return "Unreal"
        else:
            return f"Division {division}"

    def _division_to_rank_name_legacy(self, division: int) -> str:
        """Pre-2026-04-16 rank mapping. Elite, Champion, and Unreal each had a
        single tier and the Unreal cap was at division 18."""
        if division == 0:
            return "Unranked"
        elif 1 <= division <= 3:
            tier = ["I", "II", "III"][division - 1]
            return f"Bronze {tier}"
        elif 4 <= division <= 6:
            tier = ["I", "II", "III"][division - 4]
            return f"Silver {tier}"
        elif 7 <= division <= 9:
            tier = ["I", "II", "III"][division - 7]
            return f"Gold {tier}"
        elif 10 <= division <= 12:
            tier = ["I", "II", "III"][division - 10]
            return f"Platinum {tier}"
        elif 13 <= division <= 15:
            tier = ["I", "II", "III"][division - 13]
            return f"Diamond {tier}"
        elif division == 16:
            return "Elite"
        elif division == 17:
            return "Champion"
        elif division == 18:
            return "Unreal"
        else:
            return f"Division {division}"

    def _get_ranked_mode_name(self, ranking_type: str) -> str:
        """Get friendly name for ranked mode"""
        from lib.utilities.ranked_modes import ranked_mode_name
        return ranked_mode_name(ranking_type)

    def _check_ranked_progress(self):
        """Check for ranked progress changes and announce promotions/demotions"""
        try:
            if not self.auth or not self.auth.is_valid:
                return

            # Get current ranked progress
            current_ranked = self.auth.get_ranked_progress()
            if not current_ranked:
                return

            # Check if this is the first run (initialization)
            first_run = len(self.prev_ranked_progress) == 0

            # Check each ranking type for changes
            for ranking_type, current_data in current_ranked.items():
                current_div = current_data.get('currentDivision', 0)
                current_progress = current_data.get('promotionProgress', 0.0)

                # Check if we have previous data for this mode
                if ranking_type in self.prev_ranked_progress and not first_run:
                    prev_data = self.prev_ranked_progress[ranking_type]
                    prev_div = prev_data.get('currentDivision', 0)
                    prev_progress = prev_data.get('promotionProgress', 0.0)

                    # Check for division change (promotion or demotion)
                    # Only announce if there's an actual change and player is ranked (not unranked)
                    if current_div != prev_div and current_div > 0:
                        mode_name = self._get_ranked_mode_name(ranking_type)
                        # API uses 0-indexed divisions for ranked tiers
                        # Division 1 = Bronze II, Division 2 = Bronze III, etc.
                        # Add 1 to get the display rank.
                        # lastUpdated lets the mapping fall back to the pre-
                        # 2026-04-16 ladder for stale pre-expansion records.
                        last_updated = current_data.get('lastUpdated')
                        current_rank = self._division_to_rank_name(current_div + 1, last_updated)

                        if current_div > prev_div:
                            # Promotion!
                            next_div = current_div + 2  # +1 for offset, +1 for next tier
                            next_rank = self._division_to_rank_name(next_div, last_updated)
                            progress_pct = int(current_progress * 100)

                            announcement = f"{mode_name} ranked: Promoted to {current_rank} ({progress_pct}% towards {next_rank})!"
                            speaker.speak(simple(announcement, f"{mode_name}: promoted to {current_rank}, {progress_pct}% towards {next_rank}"))
                            logger.info(f"Ranked promotion: {announcement}")
                        elif current_div < prev_div:
                            # Demotion
                            announcement = f"{mode_name} ranked: Demoted to {current_rank}."
                            speaker.speak(simple(announcement, f"{mode_name}: demoted to {current_rank}"))
                            logger.info(f"Ranked demotion: {announcement}")

                    # Check for progress change within the same division
                    elif current_div == prev_div and current_div > 0:
                        # Only announce if progress has changed
                        if current_progress != prev_progress:
                            mode_name = self._get_ranked_mode_name(ranking_type)
                            last_updated = current_data.get('lastUpdated')
                            current_rank = self._division_to_rank_name(current_div + 1, last_updated)
                            next_div = current_div + 2  # +1 for offset, +1 for next tier
                            next_rank = self._division_to_rank_name(next_div, last_updated)

                            # Calculate the difference in percentage
                            prev_pct = int(prev_progress * 100)
                            current_pct = int(current_progress * 100)
                            diff_pct = current_pct - prev_pct

                            # Determine if gained or lost
                            if diff_pct > 0:
                                delta_text = f"Gained {diff_pct} percent"
                            else:
                                delta_text = f"Lost {abs(diff_pct)} percent"

                            announcement = f"{mode_name} ranked: {current_pct}% towards {next_rank} - {delta_text}"
                            speaker.speak(simple(announcement, f"{mode_name}: {current_pct}% towards {next_rank}, {delta_text.lower()}"))
                            logger.info(f"Ranked progress update: {current_rank} ({prev_pct}% -> {current_pct}%) - {delta_text}")

                # Update previous state (silent on first run)
                self.prev_ranked_progress[ranking_type] = {
                    'currentDivision': current_div,
                    'promotionProgress': current_progress
                }

            # Log initialization on first run
            if first_run:
                logger.debug(f"Initialized ranked progress tracking for {len(self.prev_ranked_progress)} modes")

        except Exception as e:
            logger.error(f"Error checking ranked progress: {e}")

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
                    speaker.speak(simple(f"{new_count} new incoming friend requests. Open social menu to review.", f"{new_count} new friend requests"))

            self.prev_incoming_count = current_incoming_count

            # Check for new outgoing friend requests (less common but tracked)
            current_outgoing_count = len(self.outgoing_requests)
            self.prev_outgoing_count = current_outgoing_count

            # Check for new party invites
            # NOTE: Announcements for invites come from
            # MatchEventMonitor, which parses `OnPartyInviteReceived` and
            # `OnPingReceived` from the Fortnite log with sub-second
            # latency. We keep the API-polled count-change logic here only
            # to drive auto-accept for invites that came in response to
            # join requests we sent.
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
                                logger.debug(f"Auto-accepting invite from {display_name} (responded to our join request)")
                                # Remove from tracking
                                del self.outgoing_join_requests[from_account_id]
                                # Accept outside of lock
                                threading.Thread(
                                    target=self._auto_accept_party_invite,
                                    args=(latest_invite, display_name),
                                    daemon=True
                                ).start()
                            # Else: MatchEventMonitor already announced the
                            # invite; nothing extra to do here.

            self.prev_party_invite_count = current_invite_count

        # NOTE: Party member joined/left announcements are now driven by
        # MatchEventMonitor parsing `LogParty: Verbose: Adding [<name>]`
        # and `HandleZonePlayerStateRemoved: [MCP:<id>]` from the Fortnite
        # log. Those fire instantly (vs. the 30s slow-poll cadence here)
        # and carry display names inline. The old diff-based announcements
        # here were removed to avoid duplicate speech.
        # The previous-id set itself is still tracked because other code
        # paths may rely on it.
        if not hasattr(self, 'prev_party_members_ids'):
            self.prev_party_members_ids = set()
            if self.party_members:
                self.prev_party_members_ids = {m.account_id for m in self.party_members}
        self.prev_party_members_ids = {
            m.account_id for m in self.party_members
        } if self.party_members else set()

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
            if self.notification_queue:
                # More notifications waiting
                speaker.speak(simple(f"New friend request from {name}. Press Alt Y to accept, Alt N to decline. Next notification in 15 seconds.", f"Friend request from {name}. Alt Y accept, Alt N decline. Next in 15 seconds."))
            else:
                # This is the only notification
                speaker.speak(simple(f"New friend request from {name}. Press Alt Y to accept, Alt N to decline.", f"Friend request from {name}. Alt Y accept, Alt N decline."))
        else:  # party_invite
            if self.notification_queue:
                # More notifications waiting
                speaker.speak(simple(f"New party invite from {name}. Press Alt Y to accept, Alt N to decline. Next notification in 15 seconds.", f"Party invite from {name}. Alt Y accept, Alt N decline. Next in 15 seconds."))
            else:
                # This is the only notification
                speaker.speak(simple(f"New party invite from {name}. Press Alt Y to accept, Alt N to decline.", f"Party invite from {name}. Alt Y accept, Alt N decline."))

        # Start 15-second timer only if there are more notifications in queue
        if self.notification_queue:
            self.notification_timer = threading.Timer(15.0, self._notification_timeout)
            self.notification_timer.start()
        else:
            # No timer - let user respond whenever they want
            self.notification_timer = None

    def _notification_timeout(self):
        """Handle notification timeout - move to next notification if queue has more, otherwise keep current"""
        with self.notification_lock:
            if self.current_notification:
                # Only move to next notification if there are more in queue
                if self.notification_queue:
                    # Clear current notification and process next
                    # The previous notification stays in pending list on server (not declined)
                    self.current_notification = None
                    self._process_next_notification()
                # else: queue is empty, keep current notification until user responds or it expires

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

            logger.debug(f"Loaded social cache from {cache_data.get('last_updated')}")

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

            logger.debug(f"Loaded {len(self.favorite_friends)} favorite friends")
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
        self.notify_changed()

    def is_favorite(self, friend: Friend) -> bool:
        """Check if a friend is favorited"""
        return friend.account_id in self.favorite_friends

    # ========== What the Social window shows (shared by the wx view and the hub page) ==========

    def notify_changed(self):
        """Tell the listeners the lists changed, if they did."""
        if not self.change_listeners:
            return
        with self.lock:
            signature = (
                tuple((f.account_id, f.display_name) for f in self.all_friends),
                tuple((r.account_id, r.display_name, r.direction)
                      for r in self.incoming_requests + self.outgoing_requests),
                tuple((m.account_id, m.display_name, m.is_leader) for m in self.party_members),
                frozenset(self.favorite_friends),
            )
        if signature == self._change_signature:
            return
        self._change_signature = signature
        for listener in list(self.change_listeners):
            try:
                listener()
            except Exception as e:
                logger.debug(f"Social change listener failed: {e}")

    def friends_view(self, favorites_only: bool = False, search: str = "") -> List[Friend]:
        """Friends as the list shows them: filtered, favorites first, then by name."""
        with self.lock:
            friends = list(self.all_friends)

        if favorites_only:
            friends = [f for f in friends if self.is_favorite(f)]
        if search:
            needle = search.lower()
            friends = [f for f in friends if needle in (f.display_name or "").lower()]

        def sort_key(friend):
            name = (friend.display_name or friend.account_id or "Unknown").lower()
            return (not self.is_favorite(friend), name)

        friends.sort(key=sort_key)
        return friends

    def requests_view(self, incoming: bool = True) -> List[FriendRequest]:
        with self.lock:
            return list(self.incoming_requests if incoming else self.outgoing_requests)

    def party_view(self):
        """(members, am_i_leader)."""
        with self.lock:
            members = list(self.party_members)
        my_id = self.social_api.auth.account_id if self.social_api else None
        am_leader = any(m.account_id == my_id and m.is_leader for m in members)
        return members, am_leader

    def find_friend(self, account_id: str) -> Optional[Friend]:
        with self.lock:
            return next((f for f in self.all_friends if f.account_id == account_id), None)

    def find_request(self, account_id: str, incoming: bool) -> Optional[FriendRequest]:
        with self.lock:
            pool = self.incoming_requests if incoming else self.outgoing_requests
            return next((r for r in pool if r.account_id == account_id), None)

    def find_member(self, account_id: str) -> Optional[PartyMember]:
        with self.lock:
            return next((m for m in self.party_members if m.account_id == account_id), None)

    def refresh_after_operation(self, data_type: str):
        """Force a backend refresh after an action. data_type is 'friends' or 'requests'."""
        if data_type == 'friends':
            self.refresh_slow_data()
        elif data_type == 'requests':
            self.refresh_fast_data()

    @staticmethod
    def choose_user(users: List[dict]) -> Optional[dict]:
        """The user a search means: the exact match, or the only result. None when the user must choose."""
        for user in users:
            if user["match_type"] == "exact":
                return user
        if len(users) == 1:
            return users[0]
        return None

    @staticmethod
    def user_choice_label(user: dict) -> str:
        return f"{user['display_name']} ({user['mutual_friends']} mutual friends)"

    def accept_problem(self, request: FriendRequest) -> Optional[str]:
        """Why the request can't be accepted, or None."""
        if request.direction != "inbound":
            return "Cannot accept outgoing request"
        return None

    def promote_problem(self, member: PartyMember) -> Optional[str]:
        if member.is_leader:
            return "Member is already the leader"
        return None

    def kick_problem(self, member: PartyMember) -> Optional[str]:
        if member.account_id == self.social_api.auth.account_id:
            return "Cannot kick yourself. Use Leave Party instead."
        return None

    def account_info_texts(self):
        """The three boxes of the Me tab: (Epic account, Fortnite stats, ranked stats). Calls the Epic API."""
        try:
            if not self.auth:
                return ("Not signed in. Press Left Alt + Shift + L to sign in.",
                        "Not authenticated.", "Not authenticated.")

            auth = self.auth
            expired = ("Epic sign-in expired. Sign in again on the Epic account page.",
                       "Authentication expired.", "Authentication expired.")
            if not auth.is_valid:
                return expired

            account_info = auth.get_account_info()
            if not account_info:
                if not auth.is_valid:
                    return expired
                return ("Couldn't load account information. Try refreshing.",
                        "Couldn't load stats.", "Couldn't load ranked stats.")

            epic = "\n".join([
                f"Username: {account_info.get('displayName', 'N/A')}",
                f"Email: {account_info.get('email', 'N/A')}",
                f"Account ID: {account_info.get('id', 'N/A')}",
            ])
            fortnite = "\n".join(self._fortnite_stats_lines(auth.get_player_stats()))
            ranked = "\n".join(self._ranked_stats_lines(auth.get_ranked_progress()))
            return epic, fortnite, ranked
        except Exception as e:
            logger.error(f"Error loading account info: {e}")
            message = f"Error: {e}"
            return message, message, message

    @staticmethod
    def _fortnite_stats_lines(player_stats) -> List[str]:
        lines = []
        if player_stats is None:
            lines.append("Couldn't load stats. Try refreshing.")
        elif player_stats.get('private'):
            lines.append("Statistics are set to private.")
            lines.append("Change privacy settings in-game to view stats.")
        else:
            lines.append("OVERALL CAREER STATS")
            lines.append(f"Total Wins: {player_stats.get('wins', 0):,}")
            lines.append(f"Total Kills: {player_stats.get('kills', 0):,}")
            lines.append(f"Matches Played: {player_stats.get('matches_played', 0):,}")
            lines.append(f"K/D Ratio: {player_stats.get('kd_ratio', 0):.2f}")
            lines.append(f"Win Rate: {player_stats.get('win_rate', 0):.2f}%")

            minutes = player_stats.get('minutes_played', 0)
            hours = minutes / 60
            days = hours / 24
            lines.append(f"Time Played: {minutes:,} minutes ({hours:.1f} hours / {days:.1f} days)")
            lines.append(f"Players Outlived: {player_stats.get('players_outlived', 0):,}")

            mode_breakdown = player_stats.get('mode_breakdown', {})
            if mode_breakdown:
                modes = ['solo', 'duo', 'trio', 'squad']
                if any(mode_breakdown.get(mode, {}).get('matches', 0) > 0 for mode in modes):
                    lines.append("")
                    lines.append("PER-MODE BREAKDOWN")
                    for mode_name in modes:
                        mode_data = mode_breakdown.get(mode_name, {})
                        if mode_data.get('matches', 0) > 0:
                            mode_label = mode_name.capitalize() + "s" if mode_name != "solo" else "Solos"
                            lines.append(f"{mode_label}: {mode_data['wins']:,} wins, {mode_data['kills']:,} kills, {mode_data['matches']:,} matches (K/D: {mode_data['kd_ratio']:.2f}, WR: {mode_data['win_rate']:.1f}%)")

            tops = [3, 5, 6, 10, 12, 25]
            if any(player_stats.get(f'top{i}', 0) > 0 for i in tops):
                lines.append("")
                lines.append("TOP PLACEMENTS")
                for i in tops:
                    if player_stats.get(f'top{i}', 0) > 0:
                        lines.append(f"Top {i}: {player_stats[f'top{i}']:,}")

            if player_stats.get('score', 0) > 0:
                lines.append("")
                lines.append(f"Total Score: {player_stats['score']:,}")
        return lines

    def _ranked_stats_lines(self, ranked_data) -> List[str]:
        lines = []
        if ranked_data is None:
            lines.append("Couldn't load ranked stats. Try refreshing.")
        elif not ranked_data:
            lines.append("No ranked data available.")
            lines.append("Play ranked matches to see your progress here.")
        else:
            from lib.utilities.ranked_modes import ordered_ranking_types
            for ranking_type in ordered_ranking_types(ranked_data):
                mode_data = ranked_data[ranking_type]
                mode_name = self._get_ranked_mode_name(ranking_type)
                current_div = mode_data.get('currentDivision', 0)
                highest_div = mode_data.get('highestDivision', 0)
                progress = mode_data.get('promotionProgress', 0.0)

                # The API counts divisions from 0, so add 1 for the display rank.
                # lastUpdated picks the pre-2026-04-16 ladder for stale records.
                last_updated = mode_data.get('lastUpdated')
                current_rank = self._division_to_rank_name(current_div + 1, last_updated)
                highest_rank = self._division_to_rank_name(highest_div + 1, last_updated)

                if current_div > 0:
                    next_rank = self._division_to_rank_name(current_div + 2, last_updated)
                    lines.append(f"{mode_name}: {current_rank} ({int(progress * 100)}% to {next_rank})")
                else:
                    lines.append(f"{mode_name}: {current_rank}")

                if highest_div > current_div:
                    lines.append(f"  Peak: {highest_rank}")
        return lines

    # ========== Navigation Methods ==========

    def cycle_view(self, direction: str = "forwards"):
        """
        Cycle between social views

        Args:
            direction: 'forwards' or 'backwards'
        """
        try:
            logger.debug(f"Cycle view called (direction: {direction})")
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
            logger.debug(f"Navigate called (direction: {direction})")
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
            speaker.speak(simple(f"{view_name}. {count} friends", f"{view_name}, {count}"))
        elif self.current_view == self.VIEW_INCOMING_REQUESTS:
            speaker.speak(simple(f"{view_name}. {count} incoming requests", f"{view_name}, {count}"))
        elif self.current_view == self.VIEW_OUTGOING_REQUESTS:
            speaker.speak(simple(f"{view_name}. {count} outgoing requests", f"{view_name}, {count}"))
        elif self.current_view == self.VIEW_PARTY_MEMBERS:
            speaker.speak(simple(f"{view_name}. {count} members in party", f"{view_name}, {count}"))
        elif self.current_view == self.VIEW_PARTY_INVITES:
            speaker.speak(simple(f"{view_name}. {count} pending invites", f"{view_name}, {count}"))

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
                speaker.speak(simple(f"Friend request from {display_name}, {position_info.rstrip(', ')}", f"Request from {display_name}, {position_info.rstrip(', ')}"))
            else:
                speaker.speak(simple(f"Friend request from {display_name}", f"Request from {display_name}"))
        else:
            if position_info:
                speaker.speak(simple(f"Friend request sent to {display_name}, {position_info.rstrip(', ')}", f"Sent to {display_name}, {position_info.rstrip(', ')}"))
            else:
                speaker.speak(simple(f"Friend request sent to {display_name}", f"Sent to {display_name}"))

    def _announce_party_invite(self, invite: PartyInvite, position_info: str = ""):
        """Announce party invite details"""
        # Ensure we have real display name, not account ID
        display_name = self._ensure_display_name(invite.from_display_name)

        if position_info:
            speaker.speak(simple(f"Party invite from {display_name}, {position_info.rstrip(', ')}", f"Invite from {display_name}, {position_info.rstrip(', ')}"))
        else:
            speaker.speak(simple(f"Party invite from {display_name}", f"Invite from {display_name}"))

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
        speaker.speak(simple(f"Accepting friend request from {request.display_name}", f"Accepting {request.display_name}"))

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
        speaker.speak(simple(f"Declining friend request", "Declining"))

        try:
            success = self.social_api.decline_friend_request(request.account_id)

            if success:
                speaker.speak(simple("Friend request declined", "Declined"))
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
        speaker.speak(simple(f"Joining {invite.from_display_name}'s party", f"Joining {invite.from_display_name}"))

        try:
            import pyautogui
            from lib.utilities.mouse import instant_click, get_screen_size
            from lib.utilities.window_utils import focus_fortnite

            # Minimize social GUI if open (thread-safe)
            minimized_window = self._minimize_social_gui_safe()

            # Focus Fortnite window (uses process name, more reliable)
            if focus_fortnite():
                time.sleep(0.2)  # Give window time to focus

                # Ensure focus before clicking
                focus_fortnite()
                time.sleep(0.1)

                # Click center of screen to ensure Fortnite is ready
                screen_width, screen_height = get_screen_size()
                center_x = screen_width // 2
                center_y = screen_height // 2
                instant_click(center_x, center_y)
                time.sleep(0.2)

                # Ensure focus before first escape
                focus_fortnite()
                time.sleep(0.1)

                # Hold ESC for 1.5 seconds to accept through Fortnite client
                pyautogui.keyDown('escape')
                time.sleep(1.5)
                pyautogui.keyUp('escape')

                # Extra hold escape to ensure acceptance
                time.sleep(0.2)

                # Ensure focus before second escape
                focus_fortnite()
                time.sleep(0.1)

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
        speaker.speak(simple(f"{display_name} accepted your request. Joining party...", f"{display_name} accepted. Joining party"))

        try:
            import pyautogui
            from lib.utilities.mouse import instant_click, get_screen_size
            from lib.utilities.window_utils import focus_fortnite

            # Minimize social GUI if open (thread-safe)
            minimized_window = self._minimize_social_gui_safe()

            # Focus Fortnite window (uses process name, more reliable)
            if focus_fortnite():
                time.sleep(0.2)  # Give window time to focus

                # Ensure focus before clicking
                focus_fortnite()
                time.sleep(0.1)

                # Click center of screen to ensure Fortnite is ready
                screen_width, screen_height = get_screen_size()
                center_x = screen_width // 2
                center_y = screen_height // 2
                instant_click(center_x, center_y)
                time.sleep(0.2)

                # Ensure focus before first escape
                focus_fortnite()
                time.sleep(0.1)

                # Hold ESC for 1.5 seconds to accept through Fortnite client
                pyautogui.keyDown('escape')
                time.sleep(1.5)
                pyautogui.keyUp('escape')

                # Extra hold escape to ensure acceptance
                time.sleep(0.2)

                # Ensure focus before second escape
                focus_fortnite()
                time.sleep(0.1)

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
        speaker.speak(simple("Declining party invite", "Declining"))

        try:
            success = self.social_api.decline_party_invite(invite.party_id, invite.invite_id)

            if success:
                speaker.speak(simple("Party invite declined", "Declined"))
                # Refresh data
                threading.Thread(target=self.refresh_all_data, daemon=True).start()
            else:
                speaker.speak("Failed to decline party invite")

        except Exception as e:
            logger.error(f"Error declining party invite: {e}")
            speaker.speak("Error declining party invite")

    def _remove_friend(self, friend: Friend):
        """Remove a friend"""
        speaker.speak(simple(f"Removing {friend.display_name} from friends list", f"Removing {friend.display_name}"))

        try:
            success = self.social_api.remove_friend(friend.account_id)

            if success:
                speaker.speak(simple(f"{friend.display_name} removed from friends", f"Removed {friend.display_name}"))
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
        speaker.speak(simple(f"Sending friend request to {username}", f"Sending to {username}"))

        try:
            success = self.social_api.send_friend_request(username)

            if success:
                speaker.speak(simple(f"Friend request sent to {username}", f"Sent to {username}"))
                # Refresh data
                threading.Thread(target=self.refresh_all_data, daemon=True).start()
            else:
                speaker.speak(f"Failed to send friend request. User may not exist or is already a friend")

        except Exception as e:
            logger.error(f"Error sending friend request: {e}")
            speaker.speak("Error sending friend request")

    def _send_friend_request_by_account_id(self, account_id: str, display_name: str):
        """Send a friend request by account ID"""
        speaker.speak(simple(f"Sending friend request to {display_name}", f"Sending to {display_name}"))

        try:
            # Send friend request directly using account ID
            import requests
            response = requests.post(
                f"{self.social_api.FRIENDS_BASE}/{self.auth.account_id}/friends/{account_id}",
                headers=self.social_api._get_headers(),
                timeout=5
            )

            if response.status_code in [200, 201, 204]:
                logger.debug(f"Successfully sent friend request to {display_name}")
                speaker.speak(simple(f"Friend request sent to {display_name}", f"Sent to {display_name}"))
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
        speaker.speak(simple(f"Inviting {display_name} to party", f"Inviting {display_name}"))

        try:
            result = self.social_api.send_party_invite(friend.account_id)

            if result == True:
                speaker.speak(simple(f"Party invite sent to {display_name}", f"Invited {display_name}"))
            elif result == "already_sent":
                speaker.speak(simple(f"Party invite sent to {display_name}", f"Invited {display_name}")) # Treat as success for user feedback
            else:
                # Retry logic for party detection
                logger.debug("Initial invite failed, retrying party detection...")
                self.refresh_slow_data() # Refresh party info
                
                # Try 2 more times
                for i in range(2):
                    if self.social_api.send_party_invite(friend.account_id):
                        speaker.speak(simple(f"Party invite sent to {display_name}", f"Invited {display_name}"))
                        return
                
                speaker.speak("Failed to send party invite. Make sure you're in a party")

        except Exception as e:
            logger.error(f"Error sending party invite: {e}")
            speaker.speak("Error sending party invite")

    def _request_to_join_party(self, friend: Friend):
        """Request to join a friend's party"""
        # Ensure real display name
        display_name = self._ensure_display_name(friend.display_name)
        speaker.speak(simple(f"Requesting to join {display_name}'s party", f"Requesting to join {display_name}"))

        try:
            result = self.social_api.request_to_join_party(friend.account_id)

            if result == True:
                # Track this join request for auto-accept logic
                self.outgoing_join_requests[friend.account_id] = (datetime.now(), display_name)
                logger.debug(f"Tracking join request to {display_name} for auto-accept")
                speaker.speak(f"Join request sent to {display_name}")
            elif result == "already_sent":
                # Still track it in case we get an invite
                self.outgoing_join_requests[friend.account_id] = (datetime.now(), display_name)
                speaker.speak(f"Join request sent to {display_name}") # Treat as success
            elif result == "no_party":
                # Friend has no party, invite them to ours instead
                logger.debug(f"{display_name} has no party, inviting them to join us")
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
        speaker.speak(simple(f"Promoting {display_name} to party leader", f"Promoting {display_name}"))

        try:
            success = self.social_api.promote_party_member(member.account_id)

            if success:
                speaker.speak(simple(f"{display_name} promoted to party leader", f"{display_name} promoted"))
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

        speaker.speak(simple(f"Leaving party of {party_size} members", "Leaving party"))

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
        
        speaker.speak(simple(f"Kicking {name} from party", f"Kicking {name}"))
        
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
    elif epic_auth_instance is not None:
        # Update auth on existing instance when new auth is provided
        _social_manager.auth = epic_auth_instance
        if _social_manager.social_api:
            _social_manager.social_api.auth = epic_auth_instance
        else:
            _social_manager.social_api = EpicSocial(epic_auth_instance)

    return _social_manager

