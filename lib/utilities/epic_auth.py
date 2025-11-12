"""
Epic Games Authentication and Locker Data Fetcher
Handles authentication with Epic Games and fetching cosmetic locker data
"""
import os
import json
import logging
import requests
import webbrowser
from typing import Optional, Dict, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class EpicAuth:
    """Handle Epic Games authentication and cosmetic data fetching"""

    def __init__(self, cache_file: str = "fortnite_locker_cache.json"):
        self.cache_file = cache_file
        self.auth_file = "epic_auth_cache.json"
        self.access_token = None
        self.account_id = None
        self.display_name = None

        # Epic Games API endpoints
        self.OAUTH_TOKEN_URL = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
        self.ACCOUNT_URL = "https://account-public-service-prod.ol.epicgames.com/account/api/public/account"

        # Fortnite API for cosmetic data
        self.FORTNITE_API_BASE = "https://fortnite-api.com/v2"

        # Load cached auth if available
        self.load_auth()

    def load_auth(self) -> bool:
        """Load cached authentication data"""
        if not os.path.exists(self.auth_file):
            return False

        try:
            with open(self.auth_file, 'r') as f:
                data = json.load(f)
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
            with open(self.auth_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved auth for {display_name}")
        except Exception as e:
            logger.error(f"Error saving auth: {e}")

    def authenticate_device_code(self) -> bool:
        """
        Authenticate using device code flow
        Returns True if successful, False otherwise
        """
        try:
            # This is a simplified version - in reality you'd need to:
            # 1. Get device code from Epic
            # 2. Show user the code and verification URL
            # 3. Poll for authentication
            # 4. Get access token

            logger.warning("Device code authentication not fully implemented yet")
            logger.warning("Please use manual authentication or Epic Games Launcher")
            return False

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False

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
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cosmetics, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(cosmetics)} cosmetics to cache")
            return True
        except Exception as e:
            logger.error(f"Error saving cosmetics cache: {e}")
            return False

    def load_cosmetics_cache(self) -> Optional[List[Dict]]:
        """Load cosmetics data from cache file"""
        if not os.path.exists(self.cache_file):
            return None

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cosmetics = json.load(f)
            logger.info(f"Loaded {len(cosmetics)} cosmetics from cache")
            return cosmetics
        except Exception as e:
            logger.error(f"Error loading cosmetics cache: {e}")
            return None

    def refresh_cosmetics(self) -> bool:
        """Fetch fresh cosmetics data and save to cache"""
        cosmetics = self.fetch_cosmetics_from_api()
        if cosmetics:
            return self.save_cosmetics_cache(cosmetics)
        return False


def get_or_create_cosmetics_cache(force_refresh: bool = False) -> Optional[List[Dict]]:
    """
    Get cosmetics data, creating cache if it doesn't exist

    Args:
        force_refresh: If True, fetch fresh data even if cache exists

    Returns:
        List of cosmetic items or None if failed
    """
    auth = EpicAuth()

    # If force refresh or no cache exists, fetch new data
    if force_refresh or not os.path.exists(auth.cache_file):
        logger.info("Fetching cosmetics data from Fortnite-API...")
        if not auth.refresh_cosmetics():
            logger.error("Failed to fetch cosmetics data")
            return None

    # Load and return cached data
    return auth.load_cosmetics_cache()
