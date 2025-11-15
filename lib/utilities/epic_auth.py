"""
Epic Games Authentication and Locker Data Fetcher
Handles authentication with Epic Games and fetching cosmetic locker data
"""
import os
import json
import logging
import requests
import webbrowser
import base64
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
                               format='json', default=[])

        self.access_token = None
        self.account_id = None
        self.display_name = None

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
            expiry = data.get('expires_at')

            # Check if token is still valid
            if expiry and datetime.fromisoformat(expiry) > datetime.now():
                logger.info(f"Loaded cached auth for {self.display_name}")
                return True
            else:
                logger.info("Cached auth expired")
                return False
        except Exception as e:
            logger.error(f"Error loading cached auth: {e}")
            return False

    def save_auth(self, access_token: str, account_id: str, display_name: str, expires_in: int):
        """Save authentication data to cache"""
        try:
            expires_at = datetime.now() + timedelta(seconds=expires_in)
            data = {
                'access_token': access_token,
                'account_id': account_id,
                'display_name': display_name,
                'expires_at': expires_at.isoformat()
            }
            config_manager.set('epic_auth', data=data)
            logger.info(f"Saved auth for {display_name}")
        except Exception as e:
            logger.error(f"Error saving auth: {e}")

    def clear_auth(self):
        """Clear cached authentication data"""
        try:
            config_manager.set('epic_auth', data={})
            self.access_token = None
            self.account_id = None
            self.display_name = None
            logger.info("Cleared cached auth")
        except Exception as e:
            logger.error(f"Error clearing auth: {e}")

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
                "code": authorization_code
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

                # Get display name
                account_info = self.get_account_info()
                if account_info:
                    self.display_name = account_info.get("displayName", "Unknown")

                # Save auth
                self.save_auth(
                    self.access_token,
                    self.account_id,
                    self.display_name,
                    token_data["expires_in"]
                )

                logger.info(f"Successfully authenticated as {self.display_name}")
                return True
            else:
                logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error exchanging code for token: {e}")
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
                logger.info("Successfully generated exchange code for XMPP")
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
                logger.info("Successfully exchanged code for XMPP token")
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

                logger.info(f"Found {len(owned_ids)} owned cosmetics")
                return owned_ids
            elif response.status_code == 401:
                # Token expired or invalid
                logger.error(f"Auth token expired: {response.text}")
                # Clear cached auth
                self.clear_auth()
                self.access_token = None
                self.account_id = None
                self.display_name = None
                # Return special marker to indicate auth expired
                return "AUTH_EXPIRED"
            else:
                logger.error(f"Failed to fetch owned cosmetics: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error fetching owned cosmetics: {e}")
            return None

    def fetch_cosmetics_from_api(self) -> Optional[List[Dict]]:
        """
        Fetch cosmetics data from Fortnite-API.com
        This gets all cosmetics available in Fortnite, not user-specific data
        """
        try:
            # Fetch all cosmetics from Fortnite-API
            response = requests.get(
                f"{self.FORTNITE_API_BASE}/cosmetics/br",
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                cosmetics = data.get('data', [])

                # Transform to our format
                formatted_cosmetics = []
                for item in cosmetics:
                    formatted_item = {
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
                    formatted_cosmetics.append(formatted_item)

                logger.info(f"Fetched {len(formatted_cosmetics)} cosmetics from Fortnite-API")
                return formatted_cosmetics
            else:
                logger.error(f"Failed to fetch cosmetics: {response.status_code}")
                return None

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
            logger.info(f"Saved {len(cosmetics)} cosmetics to cache")
            return True
        except Exception as e:
            logger.error(f"Error saving cosmetics cache: {e}")
            return False

    def load_cosmetics_cache(self) -> Optional[List[Dict]]:
        """Load cosmetics data from cache file"""
        try:
            cosmetics = config_manager.get('fortnite_locker')
            if cosmetics:
                logger.info(f"Loaded {len(cosmetics)} cosmetics from cache")
            return cosmetics if cosmetics else None
        except Exception as e:
            logger.error(f"Error loading cosmetics cache: {e}")
            return None

    def refresh_cosmetics(self) -> bool:
        """Fetch fresh cosmetics data and save to cache"""
        cosmetics = self.fetch_cosmetics_from_api()
        if cosmetics:
            return self.save_cosmetics_cache(cosmetics)
        return False

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

            logger.info(f"Matched {len(owned_cosmetics)} owned cosmetics with metadata")
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

        logger.info("Fetching owned cosmetics...")
        return auth.get_owned_cosmetics_data()

    # Otherwise, return all cosmetics
    # If force refresh or no cache exists, fetch new data
    if force_refresh or not os.path.exists(auth.cache_file):
        logger.info("Fetching cosmetics data from Fortnite-API...")
        if not auth.refresh_cosmetics():
            logger.error("Failed to fetch cosmetics data")
            return None

    # Load and return cached data
    return auth.load_cosmetics_cache()


def get_epic_auth_instance() -> EpicAuth:
    """Get or create Epic auth instance"""
    return EpicAuth()
