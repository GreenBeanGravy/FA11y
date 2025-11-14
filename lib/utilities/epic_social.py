"""
Epic Games Social API Integration
Handles friends, party, and presence management for Fortnite
"""
import logging
import requests
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        self.PARTY_BASE = "https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite"

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
                display_name = data.get("displayName")

                if display_name:
                    # Success! Cache it and save to file
                    self.display_cache.set(account_id, display_name)
                    self.display_cache.save_cache()
                    logger.info(f"Fetched and cached display name for {account_id}: {display_name}")
                    return display_name

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

        logger.info(f"Fetching {len(uncached_ids)} uncached display names using bulk endpoint...")

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

                    logger.info(f"Fetched {len(accounts)} display names from batch of {len(batch)}")
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
            logger.info(f"Successfully fetched and cached {len(successful_fetches)} display names")

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

                # Get actual display names using bulk account lookup
                name_map = self._get_bulk_display_names(account_ids, use_placeholders=False)

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

                logger.info(f"Retrieved {len(friends)} friends")
                return friends

            elif response.status_code == 401:
                logger.error("Authentication token expired")
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

        Args:
            account_ids: List of account IDs

        Returns:
            Dictionary mapping account ID to presence data
        """
        if not account_ids:
            return {}

        try:
            # Try the bulk presence endpoint (may not be available for all auth types)
            # Note: This endpoint may require special OAuth scopes or party authentication
            response = requests.get(
                f"{self.PRESENCE_BASE}/_/{self.auth.account_id}/settings/subscriptions",
                headers=self._get_headers(),
                timeout=5
            )

            # If presence API is not available (405 or 403), return empty dict
            # Friends will still work, just without online status
            if response.status_code in [403, 405]:
                if not self._presence_warning_shown:
                    logger.info("Presence API not available with current authentication - friends will show as offline")
                    self._presence_warning_shown = True
                return {}

            if response.status_code == 200:
                # If we got a valid response, try to parse it
                # For now, just return empty as the exact format may vary
                # This can be enhanced later when we have more info about the API
                if not self._presence_warning_shown:
                    logger.debug("Presence API available but format unknown, defaulting to offline status")
                    self._presence_warning_shown = True
                return {}
            else:
                if not self._presence_warning_shown:
                    logger.debug(f"Presence lookup returned {response.status_code}")
                    self._presence_warning_shown = True
                return {}

        except Exception as e:
            if not self._presence_warning_shown:
                logger.debug(f"Presence lookup not available: {e}")
                self._presence_warning_shown = True
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
        logger.info(f"Found {len(online_friends)} online friends")
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

                # Get display names (from cache or API, in bulk)
                name_map = self._get_bulk_display_names(all_request_ids, use_placeholders=False)

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

                logger.info(f"Retrieved {len(requests_list)} pending friend requests")
                return requests_list

            elif response.status_code == 401:
                logger.error("Authentication token expired")
                return None
            else:
                logger.error(f"Failed to get pending requests: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error getting pending requests: {e}")
            return None

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
                    logger.info(f"Successfully sent friend request to {username}")
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
                logger.info(f"Successfully accepted friend request from {account_id}")
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
                logger.info(f"Successfully declined friend request from {account_id}")
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
                logger.info(f"Successfully removed friend {account_id}")
                return True
            else:
                logger.error(f"Failed to remove friend: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error removing friend: {e}")
            return False

    # ========== Party API ==========

    def get_current_party(self) -> Optional[List[PartyMember]]:
        """
        Get current party members

        Returns:
            List of PartyMember objects or None if not in party or failed
        """
        try:
            # Get user's current party
            response = requests.get(
                f"{self.PARTY_BASE}/user/{self.auth.account_id}",
                headers=self._get_headers(),
                timeout=5
            )

            if response.status_code == 200:
                party_data = response.json()
                party_members = []

                members = party_data.get("members", [])
                leader_id = party_data.get("captain_id")

                # Get display names for all members
                member_ids = [m.get("account_id") for m in members]
                name_map = self._get_bulk_display_names(member_ids)

                for member in members:
                    member_id = member.get("account_id")
                    party_members.append(PartyMember(
                        account_id=member_id,
                        display_name=name_map.get(member_id, member_id),
                        is_leader=(member_id == leader_id),
                        joined_at=datetime.fromisoformat(member.get("joined_at", "").replace("Z", "+00:00")) if member.get("joined_at") else datetime.now()
                    ))

                logger.info(f"Retrieved {len(party_members)} party members")
                return party_members

            elif response.status_code == 404:
                logger.info("Not currently in a party")
                return []
            else:
                logger.error(f"Failed to get party info: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error getting party info: {e}")
            return None

    def get_party_invites(self) -> Optional[List[PartyInvite]]:
        """
        Get pending party invites

        Returns:
            List of PartyInvite objects or None if failed
        """
        try:
            response = requests.get(
                f"{self.PARTY_BASE}/user/{self.auth.account_id}/pings",
                headers=self._get_headers(),
                timeout=5
            )

            if response.status_code == 200:
                pings = response.json()
                invites = []

                for ping in pings:
                    from_id = ping.get("sent_by")
                    invites.append(PartyInvite(
                        party_id=ping.get("party_id"),
                        invite_id=ping.get("ping_id"),
                        from_account_id=from_id,
                        from_display_name=self._get_display_name(from_id),
                        created_at=datetime.fromisoformat(ping.get("sent_at", "").replace("Z", "+00:00")) if ping.get("sent_at") else datetime.now(),
                        expires_at=datetime.fromisoformat(ping.get("expires_at", "").replace("Z", "+00:00")) if ping.get("expires_at") else None
                    ))

                logger.info(f"Retrieved {len(invites)} party invites")
                return invites

            elif response.status_code == 404:
                logger.info("No party invites")
                return []
            else:
                logger.error(f"Failed to get party invites: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error getting party invites: {e}")
            return None

    def send_party_invite(self, account_id: str) -> bool:
        """
        Send a party invite to a friend

        Args:
            account_id: Epic account ID of friend to invite

        Returns:
            True if successful, False otherwise
        """
        try:
            # First get current party
            party_response = requests.get(
                f"{self.PARTY_BASE}/user/{self.auth.account_id}",
                headers=self._get_headers(),
                timeout=5
            )

            if party_response.status_code == 200:
                party_data = party_response.json()
                party_id = party_data.get("id")

                # Send invite
                response = requests.post(
                    f"{self.PARTY_BASE}/parties/{party_id}/invites/{account_id}",
                    headers=self._get_headers(),
                    timeout=5
                )

                if response.status_code in [200, 201, 204]:
                    logger.info(f"Successfully sent party invite to {account_id}")
                    return True
                else:
                    logger.error(f"Failed to send party invite: {response.status_code}")
                    return False
            else:
                logger.error("Not in a party, cannot send invite")
                return False

        except Exception as e:
            logger.error(f"Error sending party invite: {e}")
            return False

    def accept_party_invite(self, party_id: str) -> bool:
        """
        Accept a party invite

        Args:
            party_id: ID of party to join

        Returns:
            True if successful, False otherwise
        """
        try:
            # Join the party
            response = requests.post(
                f"{self.PARTY_BASE}/parties/{party_id}/members/{self.auth.account_id}/join",
                headers=self._get_headers(),
                json={},
                timeout=5
            )

            if response.status_code in [200, 201, 204]:
                logger.info(f"Successfully joined party {party_id}")
                return True
            else:
                logger.error(f"Failed to join party: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error accepting party invite: {e}")
            return False

    def decline_party_invite(self, party_id: str, invite_id: str) -> bool:
        """
        Decline a party invite

        Args:
            party_id: ID of party
            invite_id: ID of invite/ping

        Returns:
            True if successful, False otherwise
        """
        try:
            # Delete the ping/invite
            response = requests.delete(
                f"{self.PARTY_BASE}/user/{self.auth.account_id}/pings/{invite_id}",
                headers=self._get_headers(),
                timeout=5
            )

            if response.status_code in [200, 204]:
                logger.info(f"Successfully declined party invite {invite_id}")
                return True
            else:
                logger.error(f"Failed to decline party invite: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error declining party invite: {e}")
            return False

    def leave_party(self) -> bool:
        """
        Leave current party

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get current party
            party_response = requests.get(
                f"{self.PARTY_BASE}/user/{self.auth.account_id}",
                headers=self._get_headers(),
                timeout=5
            )

            if party_response.status_code == 200:
                party_data = party_response.json()
                party_id = party_data.get("id")

                # Leave party
                response = requests.delete(
                    f"{self.PARTY_BASE}/parties/{party_id}/members/{self.auth.account_id}",
                    headers=self._get_headers(),
                    timeout=5
                )

                if response.status_code in [200, 204]:
                    logger.info("Successfully left party")
                    return True
                else:
                    logger.error(f"Failed to leave party: {response.status_code}")
                    return False
            else:
                logger.info("Not in a party")
                return True

        except Exception as e:
            logger.error(f"Error leaving party: {e}")
            return False

    def promote_party_member(self, member_account_id: str) -> bool:
        """
        Promote a party member to leader

        Args:
            member_account_id: Account ID of member to promote

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get current party
            party_response = requests.get(
                f"{self.PARTY_BASE}/user/{self.auth.account_id}",
                headers=self._get_headers(),
                timeout=5
            )

            if party_response.status_code == 200:
                party_data = party_response.json()

                # Check if party data has the expected structure
                if "current" in party_data and len(party_data["current"]) > 0:
                    party_id = party_data["current"][0].get("id")
                else:
                    party_id = party_data.get("id")

                if not party_id:
                    logger.error("Failed to get party ID")
                    return False

                # Promote member
                response = requests.post(
                    f"{self.PARTY_BASE}/parties/{party_id}/members/{member_account_id}/promote",
                    headers=self._get_headers(),
                    timeout=5
                )

                if response.status_code in [200, 204]:
                    logger.info(f"Successfully promoted {member_account_id} to party leader")
                    return True
                else:
                    logger.error(f"Failed to promote party member: {response.status_code} - {response.text}")
                    return False
            else:
                logger.info("Not in a party")
                return False

        except Exception as e:
            logger.error(f"Error promoting party member: {e}")
            return False
