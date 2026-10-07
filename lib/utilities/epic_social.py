"""
Epic Games Social API Integration
Handles friends, party, and presence management for Fortnite
"""
import logging
import requests
from typing import Optional, List, Dict
from datetime import datetime
from dataclasses import dataclass, asdict
from lib.utilities.display_name_cache import get_display_name_cache

logger = logging.getLogger(__name__)


@dataclass
class Friend:
    """Represents a friend in the Epic Games friends list"""
    account_id: str
    display_name: str
    status: str  # 'online', 'offline', 'away'
    created_at: datetime
    currently_playing: Optional[str] = None
    platform: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d['created_at'] = self.created_at.isoformat() if self.created_at else None
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'Friend':
        data = data.copy()
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)


@dataclass
class FriendRequest:
    """Represents a pending friend request"""
    account_id: str
    display_name: str
    direction: str  # 'inbound', 'outbound'
    created_at: datetime

    def to_dict(self) -> dict:
        d = asdict(self)
        d['created_at'] = self.created_at.isoformat() if self.created_at else None
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'FriendRequest':
        data = data.copy()
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)


@dataclass
class PartyInvite:
    """Represents a pending party invite"""
    party_id: str
    invite_id: str
    from_account_id: str
    from_display_name: str
    created_at: datetime
    expires_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d['created_at'] = self.created_at.isoformat() if self.created_at else None
        d['expires_at'] = self.expires_at.isoformat() if self.expires_at else None
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'PartyInvite':
        data = data.copy()
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'expires_at' in data and isinstance(data['expires_at'], str):
            data['expires_at'] = datetime.fromisoformat(data['expires_at'])
        return cls(**data)


@dataclass
class JoinRequest:
    """Someone asking to join our party"""
    account_id: str
    display_name: str
    created_at: datetime
    expires_at: Optional[datetime] = None


@dataclass
class PartyMember:
    """Represents a member in the current party"""
    account_id: str
    display_name: str
    is_leader: bool
    joined_at: datetime

    def to_dict(self) -> dict:
        d = asdict(self)
        d['joined_at'] = self.joined_at.isoformat() if self.joined_at else None
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'PartyMember':
        data = data.copy()
        if 'joined_at' in data and isinstance(data['joined_at'], str):
            data['joined_at'] = datetime.fromisoformat(data['joined_at'])
        return cls(**data)


class EpicSocial:
    """Epic Games Social API wrapper for friends and party management"""

    def __init__(self, epic_auth_instance):
        """
        Initialize with an EpicAuth instance

        Args:
            epic_auth_instance: Instance of EpicAuth for authentication
        """
        self.auth = epic_auth_instance

        # Epic Games API endpoints
        self.FRIENDS_BASE = "https://friends-public-service-prod.ol.epicgames.com/friends/api/v1"
        self.ACCOUNT_BASE = "https://account-public-service-prod03.ol.epicgames.com/account/api/public/account"
        self.PRESENCE_BASE = "https://presence-public-service-prod.ol.epicgames.com/presence/api/v1"
        self.USER_SEARCH_BASE = "https://user-search-service-prod.ol.epicgames.com/api/v1/search"

        # Epic Parties client, made on first use
        self._parties = None
        self.last_party_error = ""
        self.party_chat_id = ""

        # Use persistent cache for display names (3-day expiry)
        self.display_cache = get_display_name_cache()

        # Track if we've warned about presence API
        self._presence_warning_shown = False

        # Counter for generating placeholder names
        self._placeholder_counter = 0

    def _get_headers(self) -> dict:
        """Get authorization headers for API requests"""
        if not self.auth.access_token:
            raise ValueError("Not authenticated. Please log in first.")

        return {
            "Authorization": f"Bearer {self.auth.access_token}",
            "Content-Type": "application/json"
        }

    def _get_display_name(self, account_id: str, use_placeholder: bool = True) -> str:
        """
        Get display name for an account ID (with lazy loading and persistent cache)

        Args:
            account_id: Epic account ID
            use_placeholder: If True, use "Loading..." placeholder on fetch failure

        Returns:
            Display name, placeholder, or account ID
        """
        # Check persistent cache first (survives restarts, 3-day expiry)
        cached_name = self.display_cache.get(account_id)
        if cached_name:
            return cached_name

        # Not in cache - try to fetch from Epic API
        try:
            # Try account endpoint
            response = requests.get(
                f"{self.ACCOUNT_BASE}/{account_id}",
                headers=self._get_headers(),
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                display_name = data.get("displayName", "").strip()

                if display_name:
                    # Success! Cache it and save to file
                    self.display_cache.set(account_id, display_name)
                    self.display_cache.save_cache()
                    logger.debug(f"Fetched and cached display name for {account_id}: {display_name}")
                    return display_name
                else:
                    # User exists but has no display name set
                    logger.debug(f"User {account_id} has no display name in Epic profile")

            # API call failed - log and return placeholder
            logger.debug(f"Failed to get display name for {account_id}: HTTP {response.status_code}")

        except Exception as e:
            logger.debug(f"Error fetching display name for {account_id}: {e}")

        # Fallback: return placeholder or account ID
        if use_placeholder:
            self._placeholder_counter += 1
            placeholder = f"Friend {self._placeholder_counter}"
            logger.debug(f"Using placeholder '{placeholder}' for {account_id}")
            return placeholder
        else:
            return account_id

    def _get_bulk_display_names(self, account_ids: List[str], use_placeholders: bool = True) -> Dict[str, str]:
        """
        Get display names for multiple account IDs using bulk endpoint (with persistent cache)

        Args:
            account_ids: List of Epic account IDs
            use_placeholders: If True, use "Friend N" placeholders for failed fetches

        Returns:
            Dictionary mapping account ID to display name (or placeholder)
        """
        if not account_ids:
            return {}

        result = {}

        # First pass: get all cached names
        uncached_ids = []
        for account_id in account_ids:
            cached_name = self.display_cache.get(account_id)
            if cached_name:
                result[account_id] = cached_name
            else:
                uncached_ids.append(account_id)

        if not uncached_ids:
            # All names were cached!
            return result

        logger.debug(f"Fetching {len(uncached_ids)} uncached display names using bulk endpoint...")

        # Second pass: fetch uncached names in batches of 100 (Epic's max)
        successful_fetches = {}

        for i in range(0, len(uncached_ids), 100):
            batch = uncached_ids[i:i+100]

            try:
                # Build query string with multiple accountId parameters
                params = [("accountId", account_id) for account_id in batch]

                response = requests.get(
                    f"{self.ACCOUNT_BASE}",
                    headers=self._get_headers(),
                    params=params,
                    timeout=10
                )

                if response.status_code == 200:
                    accounts = response.json()

                    # Extract display names from response
                    for account in accounts:
                        account_id = account.get("id")
                        display_name = account.get("displayName")

                        if account_id and display_name:
                            result[account_id] = display_name
                            successful_fetches[account_id] = display_name

                    logger.debug(f"Fetched {len(accounts)} display names from batch of {len(batch)}")
                else:
                    logger.warning(f"Bulk lookup failed: HTTP {response.status_code}")

            except Exception as e:
                logger.error(f"Error in bulk display name lookup: {e}")

        # For any IDs that weren't returned, use placeholders or IDs
        for account_id in uncached_ids:
            if account_id not in result:
                if use_placeholders:
                    self._placeholder_counter += 1
                    result[account_id] = f"Friend {self._placeholder_counter}"
                else:
                    result[account_id] = account_id

        # Save all successful fetches to persistent cache
        if successful_fetches:
            self.display_cache.set_bulk(successful_fetches)
            self.display_cache.save_cache()
            logger.debug(f"Successfully fetched and cached {len(successful_fetches)} display names")

        return result

    # ========== Friends API ==========

    def get_friends_list(self) -> Optional[List[Friend]]:
        """
        Get list of all friends with display names from bulk account lookup

        Returns:
            List of Friend objects or None if failed
        """
        try:
            account_id = self.auth.account_id
            if not account_id:
                logger.error("No account ID available")
                return None

            # Get friends summary to get list of friend account IDs
            response = requests.get(
                f"{self.FRIENDS_BASE}/{account_id}/summary",
                headers=self._get_headers(),
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                friends_data = data.get("friends", [])

                # Extract account IDs
                account_ids = [f.get("accountId") for f in friends_data]

                # Get actual display names using bulk account lookup (with friendly placeholders for missing names)
                name_map = self._get_bulk_display_names(account_ids, use_placeholders=True)

                # Get presence data for all friends
                presence_map = self._get_bulk_presence(account_ids)

                friends = []
                for friend_data in friends_data:
                    friend_id = friend_data.get("accountId")
                    display_name = name_map.get(friend_id, friend_id)  # Real display name from bulk lookup
                    presence = presence_map.get(friend_id, {})

                    friend = Friend(
                        account_id=friend_id,
                        display_name=display_name,
                        status=presence.get("status", "offline"),
                        created_at=datetime.fromisoformat(friend_data.get("created", "").replace("Z", "+00:00")) if friend_data.get("created") else datetime.now(),
                        currently_playing=presence.get("game"),
                        platform=presence.get("platform")
                    )
                    friends.append(friend)

                logger.debug(f"Retrieved {len(friends)} friends")
                return friends

            elif response.status_code == 401:
                logger.error("Authentication token expired - marking auth as invalid")
                # Mark auth as invalid so background tasks will pause
                self.auth.invalidate_auth()
                return None
            else:
                logger.error(f"Failed to get friends list: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error getting friends list: {e}")
            return None

    def _get_bulk_presence(self, account_ids: List[str]) -> Dict[str, dict]:
        """
        Get presence information for multiple accounts

        Note: Epic's XMPP/presence service requires different auth than web OAuth.
        This method returns empty dict - online status is not available.

        Args:
            account_ids: List of account IDs

        Returns:
            Empty dict (presence not available with current auth method)
        """
        return {}

    def get_online_friends(self) -> Optional[List[Friend]]:
        """
        Get list of currently online friends

        Returns:
            List of Friend objects who are online, or None if failed
        """
        friends = self.get_friends_list()
        if friends is None:
            return None

        online_friends = [f for f in friends if f.status in ["online", "away"]]
        logger.debug(f"Found {len(online_friends)} online friends")
        return online_friends

    def get_pending_requests(self) -> Optional[List[FriendRequest]]:
        """
        Get list of pending friend requests (inbound and outbound) with cached display names

        Returns:
            List of FriendRequest objects or None if failed
        """
        try:
            account_id = self.auth.account_id
            if not account_id:
                logger.error("No account ID available")
                return None

            # Get friend requests from summary endpoint
            response = requests.get(
                f"{self.FRIENDS_BASE}/{account_id}/summary",
                headers=self._get_headers(),
                timeout=5
            )

            if response.status_code == 200:
                summary = response.json()
                requests_list = []

                # Collect all account IDs that need display names
                all_request_ids = []
                incoming = summary.get("incoming", [])
                outgoing = summary.get("outgoing", [])

                for req in incoming:
                    all_request_ids.append(req.get("accountId"))
                for req in outgoing:
                    all_request_ids.append(req.get("accountId"))

                # Get display names (from cache or API, in bulk with friendly placeholders)
                name_map = self._get_bulk_display_names(all_request_ids, use_placeholders=True)

                # Process incoming requests
                for req in incoming:
                    account_id_req = req.get("accountId")
                    display_name = name_map.get(account_id_req, account_id_req)
                    requests_list.append(FriendRequest(
                        account_id=account_id_req,
                        display_name=display_name,
                        direction="inbound",
                        created_at=datetime.fromisoformat(req.get("created", "").replace("Z", "+00:00")) if req.get("created") else datetime.now()
                    ))

                # Process outgoing requests
                for req in outgoing:
                    account_id_req = req.get("accountId")
                    display_name = name_map.get(account_id_req, account_id_req)
                    requests_list.append(FriendRequest(
                        account_id=account_id_req,
                        display_name=display_name,
                        direction="outbound",
                        created_at=datetime.fromisoformat(req.get("created", "").replace("Z", "+00:00")) if req.get("created") else datetime.now()
                    ))

                logger.debug(f"Retrieved {len(requests_list)} pending friend requests")
                return requests_list

            elif response.status_code == 401:
                logger.error("Authentication token expired - marking auth as invalid")
                # Mark auth as invalid so background tasks will pause
                self.auth.invalidate_auth()
                return None
            else:
                logger.error(f"Failed to get pending requests: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error getting pending requests: {e}")
            return None

    def search_users(self, query: str, platform: str = "epic") -> List[Dict]:
        """
        Search for users by display name

        Args:
            query: The username to search for
            platform: Platform to search on (epic, psn, xbl, steam, nsw)

        Returns:
            List of user dictionaries with account_id and display_name
        """
        try:
            response = requests.get(
                f"{self.USER_SEARCH_BASE}/{self.auth.account_id}",
                params={"platform": platform, "prefix": query},
                headers=self._get_headers(),
                timeout=5
            )

            if response.status_code == 200:
                results = response.json()
                users = []

                for result in results:
                    account_id = result.get("accountId")
                    # Get display name from matches
                    matches = result.get("matches", [])
                    display_name = None

                    for match in matches:
                        if match.get("platform") == platform:
                            display_name = match.get("value")
                            break

                    if account_id and display_name:
                        users.append({
                            "account_id": account_id,
                            "display_name": display_name,
                            "match_type": result.get("matchType", "unknown"),
                            "mutual_friends": result.get("epicMutuals", 0)
                        })

                logger.debug(f"Found {len(users)} users matching '{query}'")
                return users
            else:
                logger.error(f"Failed to search users: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Error searching users: {e}")
            return []

    def send_friend_request(self, username: str) -> bool:
        """
        Send a friend request by display name

        Args:
            username: Epic display name of user to add

        Returns:
            True if successful, False otherwise
        """
        try:
            # First, look up account ID by display name
            response = requests.get(
                f"{self.ACCOUNT_BASE}/displayName/{username}",
                headers=self._get_headers(),
                timeout=5
            )

            if response.status_code == 200:
                account_data = response.json()
                target_account_id = account_data.get("id")

                # Send friend request
                response = requests.post(
                    f"{self.FRIENDS_BASE}/{self.auth.account_id}/friends/{target_account_id}",
                    headers=self._get_headers(),
                    timeout=5
                )

                if response.status_code in [200, 201, 204]:
                    logger.debug(f"Successfully sent friend request to {username}")
                    return True
                else:
                    logger.error(f"Failed to send friend request: {response.status_code} - {response.text}")
                    return False

            elif response.status_code == 404:
                logger.error(f"User not found: {username}")
                return False
            else:
                logger.error(f"Failed to lookup user: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error sending friend request: {e}")
            return False

    def accept_friend_request(self, account_id: str) -> bool:
        """
        Accept an incoming friend request

        Args:
            account_id: Epic account ID of requester

        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.post(
                f"{self.FRIENDS_BASE}/{self.auth.account_id}/friends/{account_id}",
                headers=self._get_headers(),
                timeout=5
            )

            if response.status_code in [200, 201, 204]:
                logger.debug(f"Successfully accepted friend request from {account_id}")
                return True
            else:
                logger.error(f"Failed to accept friend request: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error accepting friend request: {e}")
            return False

    def decline_friend_request(self, account_id: str) -> bool:
        """
        Decline an incoming friend request

        Args:
            account_id: Epic account ID of requester

        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.delete(
                f"{self.FRIENDS_BASE}/{self.auth.account_id}/friends/{account_id}",
                headers=self._get_headers(),
                timeout=5
            )

            if response.status_code in [200, 204]:
                logger.debug(f"Successfully declined friend request from {account_id}")
                return True
            else:
                logger.error(f"Failed to decline friend request: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error declining friend request: {e}")
            return False

    def remove_friend(self, account_id: str) -> bool:
        """
        Remove a friend from friends list

        Args:
            account_id: Epic account ID of friend to remove

        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.delete(
                f"{self.FRIENDS_BASE}/{self.auth.account_id}/friends/{account_id}",
                headers=self._get_headers(),
                timeout=5
            )

            if response.status_code in [200, 204]:
                logger.debug(f"Successfully removed friend {account_id}")
                return True
            else:
                logger.error(f"Failed to remove friend: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error removing friend: {e}")
            return False

    # ========== Party API (Epic Parties, the service the game uses) ==========

    @property
    def parties(self):
        if self._parties is None or self._parties.session.auth is not self.auth:
            from lib.utilities.epic_eos import EosSession, EpicParties
            self._parties = EpicParties(EosSession(self.auth))
        return self._parties

    def get_party_state(self):
        """(members, invites, join_requests) in one call, or None when it failed."""
        from lib.utilities.epic_eos import EosError
        try:
            state = self.parties.state()
        except EosError as e:
            logger.error(f"Error getting party state: {e}")
            return None
        members = []
        self.party_chat_id = state.party.chat_conversation_id if state.party else ""
        if state.party:
            names = self._get_bulk_display_names(state.party.member_ids)
            for member in state.party.members:
                member_id = member.get("account_id", "")
                if not member_id:
                    continue
                joined = member.get("joined_at") or member.get("updated_at") or ""
                members.append(PartyMember(
                    account_id=member_id,
                    display_name=names.get(member_id) or self._get_display_name(member_id),
                    is_leader=member_id == state.party.leader_id,
                    joined_at=datetime.fromisoformat(joined.replace("Z", "+00:00")) if joined else datetime.now(),
                ))
        invites = [PartyInvite(
            party_id=invite.party_id,
            invite_id=invite.inviter_id,
            from_account_id=invite.inviter_id,
            from_display_name=invite.inviter_name or self._get_display_name(invite.inviter_id),
            created_at=invite.sent_at or datetime.now(),
            expires_at=invite.expires_at,
        ) for invite in state.invites]
        join_requests = [JoinRequest(
            account_id=request.requester_id,
            display_name=request.requester_name or self._get_display_name(request.requester_id),
            created_at=request.sent_at or datetime.now(),
            expires_at=request.expires_at,
        ) for request in state.join_requests]
        return members, invites, join_requests

    def get_current_party(self) -> Optional[List[PartyMember]]:
        state = self.get_party_state()
        return state[0] if state else None

    def get_party_invites(self) -> Optional[List[PartyInvite]]:
        state = self.get_party_state()
        return state[1] if state else None

    def _party_action(self, action, *args) -> bool:
        from lib.utilities.epic_eos import EosError
        try:
            action(*args)
            return True
        except EosError as e:
            logger.error(f"Party action failed: {e}")
            self.last_party_error = str(e)
            return False

    def send_party_invite(self, account_id: str) -> bool:
        return self._party_action(self.parties.invite, account_id)

    def request_to_join_party(self, friend_account_id: str) -> bool:
        return self._party_action(self.parties.request_to_join, friend_account_id)

    def accept_party_invite(self, invite: PartyInvite) -> bool:
        from lib.utilities.epic_eos import EosInvite
        return self._party_action(self.parties.accept_invite,
                                  EosInvite(invite.party_id, invite.from_account_id, invite.from_display_name))

    def decline_party_invite(self, invite: PartyInvite) -> bool:
        return self._party_action(self.parties.decline_invite, invite.from_account_id)

    def accept_join_request(self, account_id: str) -> bool:
        return self._party_action(self.parties.accept_join_request, account_id)

    def decline_join_request(self, account_id: str) -> bool:
        return self._party_action(self.parties.decline_join_request, account_id)

    def leave_party(self) -> bool:
        return self._party_action(self.parties.leave)

    def promote_party_member(self, member_account_id: str) -> bool:
        return self._party_action(self.parties.promote, member_account_id)

    def kick_party_member(self, member_account_id: str) -> bool:
        return self._party_action(self.parties.kick, member_account_id)
