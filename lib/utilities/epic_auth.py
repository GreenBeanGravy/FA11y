"""
Epic Games Authentication and Locker Data Fetcher
Handles authentication with Epic Games and fetching cosmetic locker data
"""
import os
import json
import logging
import time
import requests
import webbrowser
import base64
import urllib.parse
import threading
from typing import Optional, Dict, List
from datetime import datetime, timedelta

from lib.config.config_manager import config_manager

logger = logging.getLogger(__name__)

class EpicAuth:
    """Handle Epic Games authentication and cosmetic data fetching"""

    def __init__(self, cache_file: str = "config/fortnite_locker_cache.json"):
        # Register configs with config_manager
        config_manager.register('epic_auth', 'config/epic_auth_cache.json',
                               format='json', default={})
        config_manager.register('fortnite_locker', cache_file,
                               format='json', default={})

        # Store cache file path for reference
        self.cache_file = cache_file

        self.access_token = None
        self.account_id = None
        self.display_name = None
        self.is_valid = False  # Track if auth is currently valid
        self.refresh_token = None
        self.refresh_token_expires_at = None
        self._reauth_lock = threading.Lock()

        # Epic Games Fortnite client credentials (public)
        self.CLIENT_ID = "ec684b8c687f479fadea3cb2ad83f5c6"
        self.CLIENT_SECRET = "e1f31c211f28413186262d37a13fc84d"

        # Epic Games API endpoints
        self.OAUTH_TOKEN_URL = "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/token"
        self.OAUTH_DEVICE_AUTH_URL = "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/deviceAuthorization"
        self.ACCOUNT_URL = "https://account-public-service-prod03.ol.epicgames.com/account/api/public/account"
        self.MCP_URL = "https://fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api/game/v2/profile"

        # Fortnite API for cosmetic metadata
        self.FORTNITE_API_BASE = "https://fortnite-api.com/v2"

        # EOS Connect / Locker Service
        self.EOS_TOKEN_URL = "https://api.epicgames.dev/auth/v1/oauth/token"
        self.LOCKER_SERVICE_URL = "https://fngw-svc-gc-livefn.ol.epicgames.com/api/locker/v4"
        self.DEPLOYMENT_ID = "62a9473a2dca46b29ccf17577fcf42d7"
        self._eos_token = None
        self._eos_token_expires_at = None

        # Load cached auth if available
        self.load_auth()

    def load_auth(self) -> bool:
        """Load cached authentication data"""
        try:
            data = config_manager.get('epic_auth')
            if not data:
                return False

            self.access_token = data.get('access_token')
            self.account_id = data.get('account_id')
            self.display_name = data.get('display_name')
            self.refresh_token = data.get('refresh_token')
            expiry = data.get('expires_at')

            refresh_expiry = data.get('refresh_token_expires_at')
            if refresh_expiry:
                self.refresh_token_expires_at = datetime.fromisoformat(refresh_expiry)

            # Check if token is still valid
            if expiry and datetime.fromisoformat(expiry) > datetime.now():
                self.is_valid = True
                return True
            else:
                logger.warning("Cached auth expired")
                self.is_valid = False
                return False
        except Exception as e:
            logger.error(f"Error loading cached auth: {e}")
            return False

    def save_auth(self, access_token: str, account_id: str, display_name: str, expires_in: int,
                  refresh_token: str = None, refresh_token_expires_in: int = None):
        """Save authentication data to cache"""
        try:
            expires_at = datetime.now() + timedelta(seconds=expires_in)
            data = {
                'access_token': access_token,
                'account_id': account_id,
                'display_name': display_name,
                'expires_at': expires_at.isoformat()
            }
            if refresh_token:
                data['refresh_token'] = refresh_token
                self.refresh_token = refresh_token
                if refresh_token_expires_in:
                    refresh_expires_at = datetime.now() + timedelta(seconds=refresh_token_expires_in)
                    data['refresh_token_expires_at'] = refresh_expires_at.isoformat()
                    self.refresh_token_expires_at = refresh_expires_at
            config_manager.set('epic_auth', data=data)
            self.is_valid = True  # Mark auth as valid when saving
        except Exception as e:
            logger.error(f"Error saving auth: {e}")

    def clear_auth(self):
        """Clear cached authentication data"""
        try:
            config_manager.set('epic_auth', data={})
            self.access_token = None
            self.account_id = None
            self.display_name = None
            self.refresh_token = None
            self.refresh_token_expires_at = None
            self.is_valid = False  # Mark auth as invalid when clearing
        except Exception as e:
            logger.error(f"Error clearing auth: {e}")

    def invalidate_auth(self):
        """Mark authentication as invalid and attempt automatic re-authentication"""
        was_valid = self.is_valid
        self.is_valid = False
        logger.warning(f"Authentication marked as invalid for {self.display_name or 'unknown user'}")

        if not was_valid:
            return  # Already invalid, don't re-trigger

        # Attempt automatic re-authentication in a background thread
        def _auto_reauth():
            if not self._reauth_lock.acquire(blocking=False):
                logger.debug("Auto re-auth already in progress, skipping")
                return
            try:
                if self.attempt_auto_reauth():
                    try:
                        import FA11y
                        FA11y._on_auth_success(self)
                    except Exception:
                        pass
                else:
                    logger.error("Epic Games authentication expired; prompting user to re-authenticate")
                    try:
                        import FA11y
                        FA11y.handle_auth_expiration()
                    except Exception:
                        pass
            finally:
                self._reauth_lock.release()

        threading.Thread(target=_auto_reauth, daemon=True, name="auto-reauth").start()

    def try_silent_webview_auth(self, timeout: float = 10.0) -> bool:
        """
        Attempt silent authentication using hidden wx WebView.
        Uses wx's native cookie management.

        Args:
            timeout: Maximum time to wait for auth

        Returns:
            True if authentication succeeded silently
        """
        try:
            # Import here to avoid circular dependency
            from lib.guis.epic_browser_login import silent_webview_auth

            logger.debug("Attempting silent WebView authentication")
            return silent_webview_auth(self, timeout)
        except Exception as e:
            logger.error(f"Error in silent WebView auth: {e}")
            return False

    def get_authorization_url(self) -> str:
        """
        Get the authorization URL for manual login
        User visits this URL, logs in, and gets a code to paste back
        """
        # Using Epic's authorization code flow
        auth_url = (
            "https://www.epicgames.com/id/api/redirect"
            f"?clientId={self.CLIENT_ID}"
            "&responseType=code"
        )
        return auth_url

    def exchange_code_for_token(self, authorization_code: str) -> bool:
        """
        Exchange authorization code for access token
        Returns True if successful, False otherwise
        """
        try:
            auth = base64.b64encode(f"{self.CLIENT_ID}:{self.CLIENT_SECRET}".encode()).decode()

            headers = {
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            data = {
                "grant_type": "authorization_code",
                "code": authorization_code,
                "token_type": "eg1"
            }

            response = requests.post(
                self.OAUTH_TOKEN_URL,
                headers=headers,
                data=data,
                timeout=30
            )

            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data["access_token"]
                self.account_id = token_data["account_id"]

                # Capture refresh token if provided
                refresh_token = token_data.get("refresh_token")
                refresh_expires_in = token_data.get("refresh_expires", token_data.get("refresh_expires_in"))

                # Get display name
                account_info = self.get_account_info()
                if account_info:
                    self.display_name = account_info.get("displayName", "Unknown")

                # Save auth
                self.save_auth(
                    self.access_token,
                    self.account_id,
                    self.display_name,
                    token_data["expires_in"],
                    refresh_token=refresh_token,
                    refresh_token_expires_in=refresh_expires_in
                )

                return True
            else:
                logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error exchanging code for token: {e}")
            return False

    def refresh_access_token(self) -> bool:
        """Use refresh_token to obtain a new access_token without user interaction."""
        if not self.refresh_token:
            logger.debug("No refresh token available")
            return False

        # Check if refresh token has expired
        if self.refresh_token_expires_at and datetime.now() >= self.refresh_token_expires_at:
            logger.warning("Refresh token has expired")
            self.refresh_token = None
            return False

        try:
            auth = base64.b64encode(f"{self.CLIENT_ID}:{self.CLIENT_SECRET}".encode()).decode()

            headers = {
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "token_type": "eg1"
            }

            response = requests.post(
                self.OAUTH_TOKEN_URL,
                headers=headers,
                data=data,
                timeout=30
            )

            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data["access_token"]
                self.account_id = token_data["account_id"]

                new_refresh_token = token_data.get("refresh_token")
                refresh_expires_in = token_data.get("refresh_expires", token_data.get("refresh_expires_in"))

                if not self.display_name:
                    account_info = self.get_account_info()
                    if account_info:
                        self.display_name = account_info.get("displayName", "Unknown")

                self.save_auth(
                    self.access_token,
                    self.account_id,
                    self.display_name,
                    token_data["expires_in"],
                    refresh_token=new_refresh_token,
                    refresh_token_expires_in=refresh_expires_in
                )

                logger.info(f"Successfully refreshed access token for {self.display_name}")
                return True
            else:
                logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                self.refresh_token = None
                return False

        except Exception as e:
            logger.error(f"Error refreshing access token: {e}")
            return False

    def attempt_auto_reauth(self) -> bool:
        """Attempt automatic re-authentication without user interaction."""
        logger.info("Attempting automatic re-authentication via refresh token...")
        if self.refresh_access_token():
            logger.info("Auto re-auth succeeded via refresh token")
            return True

        logger.warning("Automatic re-authentication failed (no valid refresh token)")
        return False

    # ========================================================================
    # EOS Connect / Locker Service
    # ========================================================================

    def get_eos_connect_token(self) -> Optional[str]:
        """
        Exchange Epic Games access token for an EOS Connect token.
        The EOS token is required for the Locker Service API.
        Returns the EOS access token string, or None on failure.
        """
        import uuid as _uuid

        # Return cached token if still valid
        if self._eos_token and self._eos_token_expires_at:
            if datetime.now() < self._eos_token_expires_at:
                return self._eos_token

        if not self.access_token:
            return None

        try:
            credentials = f"{self.CLIENT_ID}:{self.CLIENT_SECRET}"
            basic_auth = base64.b64encode(credentials.encode()).decode()

            data = {
                "grant_type": "external_auth",
                "external_auth_type": "epicgames_access_token",
                "external_auth_token": self.access_token,
                "deployment_id": self.DEPLOYMENT_ID,
                "nonce": str(_uuid.uuid4()),
            }

            response = requests.post(
                self.EOS_TOKEN_URL,
                headers={
                    "Authorization": f"Basic {basic_auth}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=data,
                timeout=30,
            )

            if response.status_code == 200:
                eos_data = response.json()
                self._eos_token = eos_data["access_token"]
                expires_in = eos_data.get("expires_in", 3600)
                self._eos_token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)
                logger.info("EOS Connect token obtained successfully")
                return self._eos_token
            else:
                logger.error(f"EOS Connect token exchange failed: {response.status_code} - {response.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Error getting EOS Connect token: {e}")
            return None

    def query_locker_items(self) -> Optional[Dict]:
        """
        Query the Locker Service for equipped cosmetics and loadout presets.
        Returns dict with 'activeLoadoutGroup' and 'loadoutPresets', or None on failure.
        """
        eos_token = self.get_eos_connect_token()
        if not eos_token:
            logger.error("Cannot query locker: no EOS token")
            return None

        try:
            url = f"{self.LOCKER_SERVICE_URL}/{self.DEPLOYMENT_ID}/account/{self.account_id}/items"
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {eos_token}"},
                timeout=30,
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Locker Service query failed: {response.status_code} - {response.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Error querying locker items: {e}")
            return None

    def get_equipped_cosmetics(self) -> Optional[Dict[str, Dict]]:
        """
        Get currently equipped cosmetics from the Locker Service.

        Returns dict mapping loadout schema to slot data, e.g.:
        {
            'Character': {
                'LoadoutSlot_Character': 'AthenaCharacter:cid_xxx',
                'LoadoutSlot_Backpack': 'AthenaBackpack:bid_xxx',
                ...
            },
            'Emotes': { ... },
            ...
        }
        Returns None on failure.
        """
        locker_data = self.query_locker_items()
        if not locker_data:
            return None

        active_loadout = locker_data.get("activeLoadoutGroup", {})
        loadouts = active_loadout.get("loadouts", {})

        result = {}
        for schema, loadout_data in loadouts.items():
            # Extract friendly name from schema (e.g. LoadoutSchema_Character -> Character)
            friendly_name = schema.split("_", 1)[-1] if "_" in schema else schema
            slots = {}
            for slot in loadout_data.get("loadoutSlots", []):
                slot_template = slot.get("slotTemplate", "")
                slot_name = slot_template.split(":")[-1] if ":" in slot_template else slot_template
                equipped_id = slot.get("equippedItemId", "")
                slots[slot_name] = {
                    "equipped_id": equipped_id,
                    "customizations": slot.get("itemCustomizations", []),
                }
            result[friendly_name] = {
                "slots": slots,
                "shuffle_type": loadout_data.get("shuffleType", "DISABLED"),
            }

        return result

    def get_saved_loadouts(self) -> Optional[List[Dict]]:
        """
        Get saved loadout presets from the Locker Service.

        Returns list of preset dicts, each with:
        {
            'display_name': str,
            'loadout_type': str,
            'preset_id': str,
            'preset_index': int,
            'slots': [{'slot_template': str, 'equipped_id': str}, ...]
        }
        Returns None on failure.
        """
        locker_data = self.query_locker_items()
        if not locker_data:
            return None

        presets = locker_data.get("loadoutPresets", [])
        result = []
        for preset in presets:
            slots = []
            for slot in preset.get("loadoutSlots", []):
                slot_template = slot.get("slotTemplate", "")
                slot_name = slot_template.split(":")[-1] if ":" in slot_template else slot_template
                slots.append({
                    "slot_name": slot_name,
                    "equipped_id": slot.get("equippedItemId", ""),
                    "customizations": slot.get("itemCustomizations", []),
                })

            result.append({
                "display_name": preset.get("displayName", ""),
                "loadout_type": preset.get("loadoutType", ""),
                "preset_id": preset.get("presetId", ""),
                "preset_index": preset.get("presetIndex", 0),
                "slots": slots,
            })

        return result

    def update_active_loadout(self, loadout_data: Dict) -> bool:
        """
        Update the active loadout group via the Locker Service.

        Args:
            loadout_data: Dict matching the ActiveLoadoutGroup PUT body format.
                         Keys are loadout schemas, values have loadoutSlots and shuffleType.

        Returns True on success, False on failure.
        """
        eos_token = self.get_eos_connect_token()
        if not eos_token:
            logger.error("Cannot update loadout: no EOS token")
            return False

        try:
            url = f"{self.LOCKER_SERVICE_URL}/{self.DEPLOYMENT_ID}/account/{self.account_id}/active-loadout-group"
            body = {"loadouts": loadout_data}

            response = requests.put(
                url,
                headers={
                    "Authorization": f"Bearer {eos_token}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=30,
            )

            if response.status_code == 200:
                logger.info("Active loadout updated successfully")
                return True
            else:
                logger.error(f"Loadout update failed: {response.status_code} - {response.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Error updating loadout: {e}")
            return False

    def get_account_info(self) -> Optional[Dict]:
        """Get account information"""
        try:
            if not self.access_token:
                return None

            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }

            response = requests.get(
                f"{self.ACCOUNT_URL}/{self.account_id}",
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get account info: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return None

    def get_exchange_code(self) -> Optional[str]:
        """
        Generate an exchange code for XMPP authentication

        Returns:
            Exchange code string if successful, None otherwise
        """
        try:
            if not self.access_token:
                logger.error("Not authenticated, cannot get exchange code")
                return None

            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }

            response = requests.get(
                "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/exchange",
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                exchange_data = response.json()
                exchange_code = exchange_data.get("code")
                return exchange_code
            else:
                logger.error(f"Failed to get exchange code: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error getting exchange code: {e}")
            return None

    def exchange_code_for_xmpp_token(self, exchange_code: str) -> Optional[Dict]:
        """
        Exchange code for XMPP access token

        Args:
            exchange_code: The exchange code to use

        Returns:
            Dict with access_token and account_id if successful, None otherwise
        """
        try:
            auth = base64.b64encode(f"{self.CLIENT_ID}:{self.CLIENT_SECRET}".encode()).decode()

            headers = {
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            data = {
                "grant_type": "exchange_code",
                "exchange_code": exchange_code
            }

            response = requests.post(
                self.OAUTH_TOKEN_URL,
                headers=headers,
                data=data,
                timeout=30
            )

            if response.status_code == 200:
                token_data = response.json()
                return {
                    "access_token": token_data["access_token"],
                    "account_id": token_data["account_id"]
                }
            else:
                logger.error(f"Failed to exchange code for XMPP token: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error exchanging code for XMPP token: {e}")
            return None

    def get_account_info(self) -> Optional[Dict]:
        """
        Get account information from Epic Games Account Service

        Returns:
            Dict with account details if successful, None otherwise
            Fields: id, displayName, email, country, preferredLanguage, tfaEnabled,
                   emailVerified, canUpdateDisplayName, numberOfDisplayNameChanges,
                   lastDisplayNameChange, lastLogin, ageGroup, minorStatus
        """
        try:
            if not self.access_token or not self.account_id:
                logger.error("Not authenticated, cannot get account info")
                return None

            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }

            response = requests.get(
                f"{self.ACCOUNT_URL}/{self.account_id}",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                account_data = response.json()
                return account_data
            elif response.status_code == 401:
                logger.warning("Authentication expired while getting account info")
                self.invalidate_auth()
                return None
            else:
                logger.error(f"Failed to get account info: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return None

    def get_player_stats(self) -> Optional[Dict]:
        """
        Get player Fortnite statistics from StatsProxyService

        Returns:
            Dict with processed stats if successful, None otherwise
            Keys: wins, kills, matches_played, kd_ratio, win_rate,
                  minutes_played, players_outlived
        """
        try:
            if not self.access_token or not self.account_id:
                logger.error("Not authenticated, cannot get player stats")
                return None

            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }

            # Use StatsProxyService for stats (alltime)
            response = requests.get(
                f"https://statsproxy-public-service-live.ol.epicgames.com/statsproxy/api/statsv2/account/{self.account_id}",
                headers=headers,
                params={
                    "startTime": 0,
                    "endTime": 9223372036854775807  # Max long value for alltime
                },
                timeout=10
            )

            if response.status_code == 204:
                # Stats are private
                return {"private": True}
            elif response.status_code == 200:
                stats_data = response.json()
                raw_stats = stats_data.get("stats", {})

                # Process stats - aggregate across all input types and playlists
                processed = {
                    "wins": 0,
                    "kills": 0,
                    "matches_played": 0,
                    "minutes_played": 0,
                    "players_outlived": 0,
                    "top1": 0,
                    "top3": 0,
                    "top5": 0,
                    "top6": 0,
                    "top10": 0,
                    "top12": 0,
                    "top25": 0,
                    "score": 0
                }

                # Aggregate stats from all keys
                for key, value in raw_stats.items():
                    # br_placetop1_* = wins
                    if "placetop1_" in key or key.endswith("_placetop1"):
                        processed["wins"] += value
                    # br_kills_* = kills
                    elif "_kills_" in key or key.endswith("_kills"):
                        processed["kills"] += value
                    # br_matchesplayed_* = matches played
                    elif "matchesplayed" in key:
                        processed["matches_played"] += value
                    # br_minutesplayed_* = time played
                    elif "minutesplayed" in key:
                        processed["minutes_played"] += value
                    # br_playersoutlived_* = players outlived
                    elif "playersoutlived" in key:
                        processed["players_outlived"] += value
                    # Top placements
                    elif "placetop3_" in key:
                        processed["top3"] += value
                    elif "placetop5_" in key:
                        processed["top5"] += value
                    elif "placetop6_" in key:
                        processed["top6"] += value
                    elif "placetop10_" in key:
                        processed["top10"] += value
                    elif "placetop12_" in key:
                        processed["top12"] += value
                    elif "placetop25_" in key:
                        processed["top25"] += value
                    # Score
                    elif "_score_" in key or key.endswith("_score"):
                        processed["score"] += value

                # Calculate derived stats
                if processed["matches_played"] > 0:
                    processed["kd_ratio"] = processed["kills"] / max(processed["matches_played"] - processed["wins"], 1)
                    processed["win_rate"] = (processed["wins"] / processed["matches_played"]) * 100
                else:
                    processed["kd_ratio"] = 0.0
                    processed["win_rate"] = 0.0

                # Parse per-gamemode breakdowns from raw stats
                mode_breakdown = self._parse_mode_breakdown(raw_stats)
                processed["mode_breakdown"] = mode_breakdown

                return processed

            elif response.status_code == 401:
                logger.warning("Authentication expired while getting stats")
                self.invalidate_auth()
                return None
            else:
                logger.error(f"Failed to get player stats: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error getting player stats: {e}")
            return None

    def _parse_mode_breakdown(self, raw_stats: Dict) -> Dict:
        """
        Parse raw stats to extract per-gamemode breakdowns

        Stats keys format: br_[stat]_[input]_m0_playlist_[playlistname]

        Returns:
            Dict with mode breakdowns (solo, duo, trio, squad)
        """
        modes = {
            "solo": {"wins": 0, "kills": 0, "matches": 0},
            "duo": {"wins": 0, "kills": 0, "matches": 0},
            "trio": {"wins": 0, "kills": 0, "matches": 0},
            "squad": {"wins": 0, "kills": 0, "matches": 0}
        }

        for key, value in raw_stats.items():
            # Identify mode type from playlist name
            key_lower = key.lower()
            mode_type = None

            # Identify team size
            if "solo" in key_lower:
                mode_type = "solo"
            elif "duo" in key_lower:
                mode_type = "duo"
            elif "trio" in key_lower:
                mode_type = "trio"
            elif "squad" in key_lower:
                mode_type = "squad"

            if mode_type:
                # Aggregate stats for this mode
                if "placetop1" in key_lower:
                    modes[mode_type]["wins"] += value
                elif "kills" in key_lower:
                    modes[mode_type]["kills"] += value
                elif "matchesplayed" in key_lower:
                    modes[mode_type]["matches"] += value

        # Calculate K/D and win rate for each mode
        for mode in modes.values():
            if mode["matches"] > 0:
                mode["kd_ratio"] = mode["kills"] / max(mode["matches"] - mode["wins"], 1)
                mode["win_rate"] = (mode["wins"] / mode["matches"]) * 100
            else:
                mode["kd_ratio"] = 0.0
                mode["win_rate"] = 0.0

        return modes

    def get_ranked_progress(self) -> Optional[Dict]:
        """
        Get ranked progress for all main competitive modes (current season only)

        Returns:
            Dict mapping ranking type to progress data if successful, None otherwise
            Keys per mode: currentDivision, highestDivision, promotionProgress, trackguid
        """
        try:
            if not self.access_token or not self.account_id:
                logger.error("Not authenticated, cannot get ranked progress")
                return None

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            # Ranking types to query (excluding Ballistic, Rocket Racing, Getaway)
            ranking_types = [
                'ranked-br-combined',           # Battle Royale (Build + Zero Build combined)
                'ranked_blastberry_build',      # Reload Build
                'ranked_blastberry_nobuild',    # Reload Zero Build
                'ranked-figment-build',         # OG Build
                'ranked-figment-nobuild',       # OG Zero Build
                'ranked-squareclub'             # Arena Box Fights
            ]

            # Use current date as endsAfter to only get current/active season data
            # This filters out old season ranks
            from datetime import datetime
            current_date = datetime.utcnow().isoformat() + 'Z'

            ranked_data = {}

            for ranking_type in ranking_types:
                try:
                    # Use bulkByRankingType endpoint with endsAfter parameter
                    # endsAfter filters to only include tracks that end after this date (i.e., active tracks)
                    response = requests.post(
                        "https://fn-service-habanero-live-public.ogs.live.on.epicgames.com/api/v1/games/fortnite/trackprogress/bulkByRankingType",
                        headers=headers,
                        params={
                            "rankingType": ranking_type,
                            "endsAfter": current_date  # Only get current season data
                        },
                        json={"accountIds": [self.account_id]},
                        timeout=10
                    )

                    if response.status_code == 200:
                        results = response.json()
                        if results and len(results) > 0:
                            # Get the first result (should be our account for current season)
                            progress = results[0]
                            ranked_data[ranking_type] = {
                                "currentDivision": progress.get("currentDivision", 0),
                                "highestDivision": progress.get("highestDivision", 0),
                                "promotionProgress": progress.get("promotionProgress", 0.0),
                                "trackguid": progress.get("trackguid", ""),
                                "lastUpdated": progress.get("lastUpdated", "")
                            }
                    elif response.status_code == 401:
                        logger.warning("Authentication expired while getting ranked progress")
                        self.invalidate_auth()
                        return None
                    else:
                        # No ranked data for this type, continue with others
                        pass

                except Exception as e:
                    # Continue with other ranking types
                    pass

            return ranked_data if ranked_data else {}

        except Exception as e:
            logger.error(f"Error getting ranked progress: {e}")
            return None

    def fetch_owned_cosmetics(self) -> Optional[List[str]]:
        """
        Fetch list of owned cosmetic IDs from Epic Games
        Returns list of template IDs for owned items
        """
        try:
            if not self.access_token or not self.account_id:
                logger.error("Not authenticated")
                return None

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            # Query the athena profile (Fortnite locker)
            url = f"{self.MCP_URL}/{self.account_id}/client/QueryProfile?profileId=athena"

            response = requests.post(
                url,
                headers=headers,
                json={},
                timeout=30
            )

            if response.status_code == 200:
                profile_data = response.json()
                items = profile_data.get("profileChanges", [{}])[0].get("profile", {}).get("items", {})

                # Extract template IDs (these are the cosmetic IDs)
                owned_ids = []
                for item_id, item_data in items.items():
                    template_id = item_data.get("templateId", "")
                    if template_id:
                        # Template IDs are like "AthenaCharacter:CID_123_Athena"
                        # We want just the ID part
                        if ":" in template_id:
                            cosmetic_id = template_id.split(":")[1]
                            owned_ids.append(cosmetic_id)

                return owned_ids
            elif response.status_code == 401:
                # Token expired or invalid
                logger.error(f"Auth token expired: {response.text}")
                # Clear cached auth
                self.clear_auth()
                self.access_token = None
                self.account_id = None
                self.display_name = None
                # Notify about auth expiration
                try:
                    import FA11y
                    FA11y.handle_auth_expiration()
                except:
                    pass  # FA11y might not be available in all contexts
                # Return special marker to indicate auth expired
                return "AUTH_EXPIRED"
            else:
                logger.error(f"Failed to fetch owned cosmetics: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error fetching owned cosmetics: {e}")
            return None

    def _format_br_cosmetic(self, item: Dict) -> Dict:
        """Format a BR cosmetic item from fortnite-api.com to our standard format"""
        return {
            'name': item.get('name', 'Unknown'),
            'id': item.get('id', ''),
            'type': item.get('type', {}).get('backendValue', 'Unknown'),
            'rarity': item.get('rarity', {}).get('value', 'common').lower(),
            'rarity_value': self.get_rarity_value(item.get('rarity', {}).get('value', 'common')),
            'introduction_chapter': item.get('introduction', {}).get('chapter', '?'),
            'introduction_season': item.get('introduction', {}).get('season', '?'),
            'description': item.get('description', ''),
            'favorite': False,
            'owned_variants': []
        }

    def _fetch_endpoint(self, endpoint: str, timeout: int = 30) -> Optional[List[Dict]]:
        """Fetch data from a fortnite-api.com endpoint, returning the 'data' list or None"""
        try:
            response = requests.get(f"{self.FORTNITE_API_BASE}/{endpoint}", timeout=timeout)
            if response.status_code == 200:
                return response.json().get('data', [])
            else:
                logger.warning(f"Failed to fetch {endpoint}: {response.status_code}")
                return None
        except Exception as e:
            logger.warning(f"Error fetching {endpoint}: {e}")
            return None

    def fetch_cosmetics_from_api(self) -> Optional[List[Dict]]:
        """
        Fetch cosmetics data from Fortnite-API.com
        Pulls from all available endpoints: BR, tracks, instruments, cars, and LEGO kits
        """
        try:
            # Fetch BR cosmetics (main catalog)
            br_data = self._fetch_endpoint("cosmetics/br")
            if br_data is None:
                logger.error("Failed to fetch BR cosmetics - aborting")
                return None

            formatted_cosmetics = [self._format_br_cosmetic(item) for item in br_data]
            logger.info(f"Fetched {len(formatted_cosmetics)} BR cosmetics")

            # Track existing IDs to avoid duplicates
            seen_ids = {c['id'].lower() for c in formatted_cosmetics}

            # Fetch Jam Tracks
            tracks_data = self._fetch_endpoint("cosmetics/tracks")
            if tracks_data:
                tracks_added = 0
                for track in tracks_data:
                    track_id = track.get('id', '')
                    if track_id.lower() not in seen_ids:
                        seen_ids.add(track_id.lower())
                        formatted_cosmetics.append({
                            'name': track.get('title', track.get('devName', 'Unknown Track')),
                            'id': track_id,
                            'type': 'SparksSong',
                            'rarity': 'common',
                            'rarity_value': 1,
                            'introduction_chapter': '?',
                            'introduction_season': '?',
                            'description': f"{track.get('artist', '')} ({track.get('releaseYear', '')})".strip(),
                            'favorite': False,
                            'owned_variants': []
                        })
                        tracks_added += 1
                logger.info(f"Fetched {tracks_added} Jam Tracks")

            # Fetch Festival Instruments
            instruments_data = self._fetch_endpoint("cosmetics/instruments")
            if instruments_data:
                # Map API backend types to profile types
                instrument_type_map = {
                    'SparksMic': 'SparksMicrophone',
                    'SparksDrum': 'SparksDrums',
                }
                instruments_added = 0
                for inst in instruments_data:
                    inst_id = inst.get('id', '')
                    if inst_id.lower() not in seen_ids:
                        seen_ids.add(inst_id.lower())
                        api_type = inst.get('type', {}).get('backendValue', 'SparksGuitar')
                        profile_type = instrument_type_map.get(api_type, api_type)
                        formatted_cosmetics.append({
                            'name': inst.get('name', 'Unknown Instrument'),
                            'id': inst_id,
                            'type': profile_type,
                            'rarity': inst.get('rarity', {}).get('value', 'common').lower(),
                            'rarity_value': self.get_rarity_value(inst.get('rarity', {}).get('value', 'common')),
                            'introduction_chapter': '?',
                            'introduction_season': '?',
                            'description': inst.get('description', ''),
                            'favorite': False,
                            'owned_variants': []
                        })
                        instruments_added += 1
                logger.info(f"Fetched {instruments_added} Festival Instruments")

            # Fetch Vehicle/Car Cosmetics
            cars_data = self._fetch_endpoint("cosmetics/cars")
            if cars_data:
                cars_added = 0
                for car in cars_data:
                    car_id = car.get('id', '')
                    if car_id.lower() not in seen_ids:
                        seen_ids.add(car_id.lower())
                        formatted_cosmetics.append({
                            'name': car.get('name', 'Unknown Vehicle Cosmetic'),
                            'id': car_id,
                            'type': car.get('type', {}).get('backendValue', 'VehicleCosmetics_Body'),
                            'rarity': car.get('rarity', {}).get('value', 'common').lower(),
                            'rarity_value': self.get_rarity_value(car.get('rarity', {}).get('value', 'common')),
                            'introduction_chapter': '?',
                            'introduction_season': '?',
                            'description': car.get('description', ''),
                            'favorite': False,
                            'owned_variants': []
                        })
                        cars_added += 1
                logger.info(f"Fetched {cars_added} Vehicle Cosmetics")

            # Fetch LEGO Kits (Building Props & Sets)
            lego_data = self._fetch_endpoint("cosmetics/lego/kits")
            if lego_data:
                lego_added = 0
                for kit in lego_data:
                    kit_id = kit.get('id', '')
                    if kit_id.lower() not in seen_ids:
                        seen_ids.add(kit_id.lower())
                        formatted_cosmetics.append({
                            'name': kit.get('name', 'Unknown LEGO Kit'),
                            'id': kit_id,
                            'type': kit.get('type', {}).get('backendValue', 'JunoBuildingProp'),
                            'rarity': 'common',
                            'rarity_value': 1,
                            'introduction_chapter': '?',
                            'introduction_season': '?',
                            'description': '',
                            'favorite': False,
                            'owned_variants': []
                        })
                        lego_added += 1
                logger.info(f"Fetched {lego_added} LEGO Kits")

            logger.info(f"Total cosmetics fetched: {len(formatted_cosmetics)}")
            return formatted_cosmetics

        except Exception as e:
            logger.error(f"Error fetching cosmetics: {e}")
            return None

    def get_rarity_value(self, rarity: str) -> int:
        """Convert rarity name to numeric value for sorting"""
        rarity_map = {
            'common': 1,
            'uncommon': 2,
            'rare': 3,
            'epic': 4,
            'legendary': 5,
            'mythic': 6,
            'marvel': 6,
            'dc': 6,
            'starwars': 6,
            'icon': 6,
            'gaminglegends': 6,
            'dark': 6,
            'frozen': 6,
            'lava': 6,
            'shadow': 6,
            'slurp': 6
        }
        return rarity_map.get(rarity.lower(), 1)

    def save_cosmetics_cache(self, cosmetics: List[Dict]) -> bool:
        """Save cosmetics data to cache file"""
        try:
            config_manager.set('fortnite_locker', data=cosmetics)
            return True
        except Exception as e:
            logger.error(f"Error saving cosmetics cache: {e}")
            return False

    def load_cosmetics_cache(self) -> Optional[List[Dict]]:
        """Load cosmetics data from cache file"""
        try:
            cosmetics = config_manager.get('fortnite_locker')
            return cosmetics if cosmetics else None
        except Exception as e:
            logger.error(f"Error loading cosmetics cache: {e}")
            return None

    def refresh_cosmetics(self) -> bool:
        """
        Fetch fresh cosmetics data and save to cache

        Returns:
            True if successful, False otherwise
        """
        cosmetics = self.fetch_cosmetics_from_api()
        if not cosmetics:
            logger.error("Failed to fetch cosmetics from Fortnite-API.com")
            return False

        return self.save_cosmetics_cache(cosmetics)

    def get_owned_cosmetics_data(self) -> Optional[List[Dict]]:
        """
        Get cosmetics data filtered to only owned items
        Requires authentication
        """
        try:
            # Get owned item IDs
            owned_ids = self.fetch_owned_cosmetics()
            if not owned_ids:
                return None

            # Get all cosmetics metadata
            all_cosmetics = self.fetch_cosmetics_from_api()
            if not all_cosmetics:
                return None

            # Filter to only owned cosmetics
            owned_cosmetics = []
            for cosmetic in all_cosmetics:
                cosmetic_id = cosmetic.get("id", "")
                # Check if this cosmetic is owned
                if cosmetic_id in owned_ids:
                    owned_cosmetics.append(cosmetic)

            return owned_cosmetics

        except Exception as e:
            logger.error(f"Error getting owned cosmetics: {e}")
            return None


def get_or_create_cosmetics_cache(force_refresh: bool = False, owned_only: bool = False) -> Optional[List[Dict]]:
    """
    Get cosmetics data, creating cache if it doesn't exist

    Args:
        force_refresh: If True, fetch fresh data even if cache exists
        owned_only: If True, only return owned cosmetics (requires authentication)

    Returns:
        List of cosmetic items or None if failed
    """
    auth = EpicAuth()

    # If owned_only, require authentication
    if owned_only:
        if not auth.access_token:
            logger.error("Authentication required for owned_only mode")
            return None

        return auth.get_owned_cosmetics_data()

    # Otherwise, return all cosmetics
    # Auto-refresh if cache is missing or stale (older than 7 days)
    cache_stale = False
    if os.path.exists(auth.cache_file):
        try:
            cache_age_seconds = time.time() - os.path.getmtime(auth.cache_file)
            cache_age_days = cache_age_seconds / 86400
            if cache_age_days > 7:
                logger.info(f"Cosmetics cache is {cache_age_days:.1f} days old, auto-refreshing")
                cache_stale = True
        except Exception as e:
            logger.warning(f"Could not check cache age: {e}")

    if force_refresh or cache_stale or not os.path.exists(auth.cache_file):
        if not auth.refresh_cosmetics():
            logger.error("Failed to fetch cosmetics data")
            # If stale refresh failed but cache exists, fall back to stale data
            if cache_stale:
                logger.info("Using stale cache as fallback")
            else:
                return None

    # Load and return cached data
    return auth.load_cosmetics_cache()


def get_epic_auth_instance() -> EpicAuth:
    """Get or create Epic auth instance"""
    return EpicAuth()


# ============================================================================
# LOCKER API - Direct cosmetic equipping via Epic's MCP endpoints
# ============================================================================

class LockerAPI:
    """Direct API integration for equipping cosmetics (no UI automation!)"""

    def __init__(self, auth: EpicAuth):
        self.auth = auth
        self.profile_data = None
        self.owned_items = {}
        self.template_id_map = {}

    def _mcp_operation(self, operation: str, profile_id: str = "athena", body: Optional[Dict] = None) -> Optional[Dict]:
        """Execute an MCP operation"""
        if not self.auth.access_token or not self.auth.account_id:
            return None

        url = f"{self.auth.MCP_URL}/{self.auth.account_id}/client/{operation}"
        body = body or {}

        try:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {self.auth.access_token}", "Content-Type": "application/json"},
                params={"profileId": profile_id},
                json=body,
                timeout=30
            )
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"MCP {operation} error: {e}")
            return None

    def load_profile(self) -> bool:
        """Load athena profile"""
        result = self._mcp_operation("QueryProfile", "athena")
        if not result:
            return False

        self.profile_data = result.get("profileChanges", [{}])[0].get("profile", {})
        items = self.profile_data.get("items", {})

        self.owned_items = {}
        self.template_id_map = {}
        for guid, item_data in items.items():
            template_id = item_data.get("templateId", "")
            if template_id:
                self.owned_items[guid] = item_data
                self.template_id_map[template_id] = guid

        return True

    def equip_cosmetic(self, template_id: str, category: str = "Character", slot_index: int = 0) -> bool:
        """
        Equip a cosmetic item directly via API

        Args:
            template_id: Full ID like "AthenaCharacter:CID_029_Athena_Commando_F_Halloween"
            category: Character, Backpack, Pickaxe, Glider, Dance, ItemWrap, etc.
            slot_index: Slot (0 for most, 0-5 for emotes, 0-6 for wraps)
        """
        body = {
            "lockerItem": "",
            "category": category,
            "itemToSlot": template_id,
            "slotIndex": slot_index,
            "variantUpdates": []
        }
        return self._mcp_operation("SetCosmeticLockerSlot", "athena", body) is not None

    def build_template_id(self, cosmetic_type: str, cosmetic_id: str) -> str:
        """Build template ID from type and CID"""
        type_map = {
            "Outfit": "AthenaCharacter", "Back Bling": "AthenaBackpack",
            "Pickaxe": "AthenaPickaxe", "Glider": "AthenaGlider",
            "Emote": "AthenaDance", "Wrap": "AthenaItemWrap",
            "Contrail": "AthenaSkyDiveContrail", "Music": "AthenaMusicPack",
            "Loading Screen": "AthenaLoadingScreen", "Pet": "AthenaPetCarrier",
            "Kicks": "AthenaShoes"
        }
        backend = type_map.get(cosmetic_type, cosmetic_type)
        return f"{backend}:{cosmetic_id}"

    def set_favorite(self, template_id: str, is_favorite: bool) -> bool:
        """
        Set favorite status for a cosmetic item

        Args:
            template_id: Full template ID like "AthenaCharacter:CID_029_Athena_Commando_F_Halloween"
            is_favorite: True to mark as favorite, False to unmark

        Returns:
            True if successful, False otherwise
        """
        # Get the item GUID from template ID
        guid = self.template_id_map.get(template_id)

        if not guid:
            logger.warning(f"Could not find GUID for template ID: {template_id}")
            # If not in map, try to load profile first
            if not self.load_profile():
                return False
            guid = self.template_id_map.get(template_id)
            if not guid:
                logger.error(f"Template ID not found in owned items: {template_id}")
                return False

        # Use SetItemFavoriteStatusBatch API
        body = {
            "itemIds": [guid],
            "itemFavStatus": [is_favorite]
        }

        result = self._mcp_operation("SetItemFavoriteStatusBatch", "athena", body)

        if result:
            return True
        else:
            logger.error(f"Failed to set favorite status for {template_id}")
            return False

    def equip_multiple_cosmetics(self, items: List[Dict[str, any]]) -> bool:
        """
        Equip multiple cosmetics at once

        Args:
            items: List of dicts with keys: template_id, category, slot_index

        Returns:
            True if successful, False otherwise
        """
        loadout_data = []
        for item in items:
            loadout_data.append({
                "category": item.get("category", "Character"),
                "itemToSlot": item.get("template_id", ""),
                "slotIndex": item.get("slot_index", 0),
                "variantUpdates": []
            })

        body = {
            "lockerItem": "",
            "loadoutData": loadout_data
        }

        result = self._mcp_operation("SetCosmeticLockerSlots", "athena", body)
        return result is not None

    def save_loadout(self, loadout_type: str, preset_id: int, slots: List[Dict], display_name: str = "") -> bool:
        """
        Save a cosmetic loadout

        Args:
            loadout_type: Type like "CosmeticLoadout:LoadoutSchema_Character"
            preset_id: Loadout index (0-9)
            slots: List of slot dicts with slot_template and equipped_item
            display_name: Optional loadout name

        Returns:
            True if successful, False otherwise
        """
        import json

        loadout_data = {
            "slots": slots
        }
        if display_name:
            loadout_data["display_name"] = display_name

        body = {
            "loadoutType": loadout_type,
            "presetId": preset_id,
            "loadoutData": json.dumps(loadout_data)
        }

        result = self._mcp_operation("PutModularCosmeticLoadout", "athena", body)

        if result:
            return True
        else:
            logger.error("Failed to save loadout")
            return False

    def load_loadout(self, loadout_type: str, preset_id: int) -> bool:
        """
        Load a saved cosmetic loadout via the Locker Service.
        Fetches the preset's slots from the Locker Service, then applies them
        as the active loadout group.

        Args:
            loadout_type: Type like "CosmeticLoadout:LoadoutSchema_Character"
            preset_id: Loadout index (string like "0001" or int like 1)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Fetch all presets from the Locker Service
            locker_data = self.auth.query_locker_items()
            if not locker_data:
                logger.error("Failed to query locker items for loadout equip")
                return False

            # Find the matching preset
            presets = locker_data.get("loadoutPresets", [])
            target_preset = None
            preset_id_str = str(preset_id).zfill(4) if isinstance(preset_id, int) else str(preset_id)

            for preset in presets:
                if (preset.get("loadoutType") == loadout_type and
                        preset.get("presetId") == preset_id_str):
                    target_preset = preset
                    break

            if not target_preset:
                # Also try matching by preset_index
                for preset in presets:
                    if (preset.get("loadoutType") == loadout_type and
                            preset.get("presetIndex") == int(preset_id)):
                        target_preset = preset
                        break

            if not target_preset:
                logger.error(f"Preset not found: type={loadout_type}, id={preset_id}")
                return False

            # Build the PUT body from the preset's slots
            formatted_slots = []
            for slot in target_preset.get("loadoutSlots", []):
                formatted_slot = {
                    "slotTemplate": slot["slotTemplate"],
                    "itemCustomizations": slot.get("itemCustomizations", []),
                }
                if slot.get("equippedItemId"):
                    formatted_slot["equippedItemId"] = slot["equippedItemId"]
                formatted_slots.append(formatted_slot)

            # Apply via the Locker Service active-loadout-group endpoint
            return self.auth.update_active_loadout({
                loadout_type: {
                    "loadoutSlots": formatted_slots,
                    "shuffleType": "DISABLED",
                }
            })

        except Exception as e:
            logger.error(f"Error loading loadout: {e}")
            return False

    def equip_preset(self, preset_data: Dict) -> bool:
        """
        Equip a loadout preset directly from its raw data dict
        (as returned by EpicAuth.get_saved_loadouts()).

        Args:
            preset_data: Dict with 'loadout_type' and 'slots' keys

        Returns:
            True if successful, False otherwise
        """
        try:
            loadout_type = preset_data.get("loadout_type", "")
            if not loadout_type:
                logger.error("No loadout_type in preset data")
                return False

            # Re-fetch the raw preset from the Locker Service to get exact slot format
            locker_data = self.auth.query_locker_items()
            if not locker_data:
                logger.error("Failed to query locker items")
                return False

            # Find matching preset
            presets = locker_data.get("loadoutPresets", [])
            preset_id = preset_data.get("preset_id", "")
            target = None
            for p in presets:
                if p.get("presetId") == preset_id and p.get("loadoutType") == loadout_type:
                    target = p
                    break

            if not target:
                logger.error(f"Could not find preset {preset_id} of type {loadout_type}")
                return False

            # Build slots for PUT
            formatted_slots = []
            for slot in target.get("loadoutSlots", []):
                fs = {
                    "slotTemplate": slot["slotTemplate"],
                    "itemCustomizations": slot.get("itemCustomizations", []),
                }
                if slot.get("equippedItemId"):
                    fs["equippedItemId"] = slot["equippedItemId"]
                formatted_slots.append(fs)

            return self.auth.update_active_loadout({
                loadout_type: {
                    "loadoutSlots": formatted_slots,
                    "shuffleType": "DISABLED",
                }
            })

        except Exception as e:
            logger.error(f"Error equipping preset: {e}")
            return False


def get_locker_api(auth: EpicAuth) -> LockerAPI:
    """Get LockerAPI instance"""
    return LockerAPI(auth)
