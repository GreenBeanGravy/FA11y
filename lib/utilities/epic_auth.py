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

        # Store cache file path for reference
        self.cache_file = cache_file

        self.access_token = None
        self.account_id = None
        self.display_name = None
        self.is_valid = False  # Track if auth is currently valid

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
                self.is_valid = True
                return True
            else:
                logger.info("Cached auth expired")
                self.is_valid = False
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
            self.is_valid = True  # Mark auth as valid when saving
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
            self.is_valid = False  # Mark auth as invalid when clearing
            logger.info("Cleared cached auth")
        except Exception as e:
            logger.error(f"Error clearing auth: {e}")

    def invalidate_auth(self):
        """Mark authentication as invalid without clearing tokens (for 401 errors)"""
        self.is_valid = False
        logger.warning(f"Authentication marked as invalid for {self.display_name or 'unknown user'}")

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

    def refresh_cosmetics(self, enrich_with_fortnitetracker: bool = True, sample_size: int = 0) -> bool:
        """
        Fetch fresh cosmetics data and save to cache

        Args:
            enrich_with_fortnitetracker: If True, enrich with FortniteTracker.gg data
            sample_size: Number of items to enrich during refresh (0 = skip bulk enrichment, recommended for speed)

        Returns:
            True if successful, False otherwise
        """
        logger.info("Fetching all cosmetics from Fortnite-API.com...")
        cosmetics = self.fetch_cosmetics_from_api()
        if not cosmetics:
            logger.error("Failed to fetch cosmetics from Fortnite-API.com")
            return False

        logger.info(f"Successfully fetched {len(cosmetics)} cosmetics from Fortnite-API.com")

        # Optionally enrich with FortniteTracker.gg data
        if enrich_with_fortnitetracker and sample_size > 0:
            logger.info(f"Will enrich {sample_size} random cosmetics with FortniteTracker.gg data (this may take {sample_size * 0.5:.0f} seconds)...")
            try:
                cosmetics = enrich_cosmetics_with_fortnitetracker(cosmetics, sample_size)
            except Exception as e:
                logger.warning(f"Failed to enrich with FortniteTracker.gg data: {e}")
        else:
            logger.info("Skipping FortniteTracker.gg bulk enrichment for faster loading")

        logger.info("Saving cosmetics to cache...")
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
            matched_ids = set()

            for cosmetic in all_cosmetics:
                cosmetic_id = cosmetic.get("id", "")
                # Check if this cosmetic is owned
                if cosmetic_id in owned_ids:
                    owned_cosmetics.append(cosmetic)
                    matched_ids.add(cosmetic_id)

            logger.info(f"Matched {len(owned_cosmetics)} owned cosmetics with Fortnite-API metadata")

            # Check for unmatched owned cosmetics
            unmatched_ids = owned_ids - matched_ids
            if unmatched_ids:
                unmatched_list = list(unmatched_ids)
                logger.info(f"Found {len(unmatched_list)} owned cosmetics not in Fortnite-API database")
                logger.info(f"Attempting FortniteTracker.gg fallback (this may take {len(unmatched_list) * 0.5:.0f} seconds)...")

                # Try to get data from FortniteTracker for unmatched cosmetics
                for idx, cosmetic_id in enumerate(unmatched_list, 1):
                    # Log progress every 5 items or for first item
                    if idx % 5 == 0 or idx == 1:
                        logger.info(f"FortniteTracker fallback progress: {idx}/{len(unmatched_list)} ({(idx/len(unmatched_list))*100:.0f}%)")

                    logger.debug(f"Fetching FortniteTracker data for unrecognized cosmetic: {cosmetic_id}")

                    try:
                        tracker_data = fetch_fortnitetracker_item(cosmetic_id)

                        if tracker_data:
                            # Create a basic cosmetic entry with FortniteTracker data
                            rarity = tracker_data.get('rarity', 'common').lower()
                            basic_cosmetic = {
                                'name': tracker_data.get('name', cosmetic_id),
                                'id': cosmetic_id,
                                'type': tracker_data.get('type', 'Unknown'),
                                'rarity': rarity,
                                'rarity_value': self.get_rarity_value(rarity),
                                'introduction_chapter': '?',
                                'introduction_season': '?',
                                'description': '',
                                'favorite': False,
                                'owned_variants': []
                            }

                            # Add FortniteTracker enrichment data if available
                            if tracker_data.get('set_name'):
                                basic_cosmetic['set_name'] = tracker_data['set_name']
                            if tracker_data.get('vbucks_price'):
                                basic_cosmetic['vbucks_price'] = tracker_data['vbucks_price']
                            if tracker_data.get('gameplay_tags'):
                                basic_cosmetic['gameplay_tags'] = tracker_data['gameplay_tags']

                            owned_cosmetics.append(basic_cosmetic)
                            logger.info(f"Successfully added cosmetic from FortniteTracker: {basic_cosmetic['name']} (Type: {basic_cosmetic['type']}, Rarity: {rarity}, ID: {cosmetic_id})")
                        else:
                            logger.warning(f"Could not fetch FortniteTracker data for: {cosmetic_id}")

                            # Create minimal entry so user can still see they own it
                            minimal_cosmetic = {
                                'name': cosmetic_id,
                                'id': cosmetic_id,
                                'type': 'Unknown',
                                'rarity': 'common',
                                'rarity_value': 1,
                                'introduction_chapter': '?',
                                'introduction_season': '?',
                                'description': 'Unrecognized cosmetic',
                                'favorite': False,
                                'owned_variants': []
                            }
                            owned_cosmetics.append(minimal_cosmetic)
                            logger.info(f"Added minimal entry for unrecognized cosmetic: {cosmetic_id}")

                    except Exception as e:
                        logger.error(f"Error processing unmatched cosmetic {cosmetic_id}: {e}")

                    # Rate limiting between FortniteTracker requests
                    import time
                    time.sleep(0.5)

                logger.info(f"FortniteTracker fallback complete: {len(owned_cosmetics)} total owned cosmetics")

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


# ============================================================================
# FORTNITETRACKER.GG INTEGRATION - Supplementary cosmetics data
# ============================================================================

# Cache for FortniteTracker data to avoid repeated requests
_fortnitetracker_cache = {}

def fetch_fortnitetracker_item(cosmetic_id: str) -> Optional[Dict]:
    """
    Fetch supplementary data for a single cosmetic from FortniteTracker.gg

    Args:
        cosmetic_id: The cosmetic ID (e.g., 'CID_029_Athena_Commando_F_Halloween')

    Returns:
        Dict with enrichment data or None if failed
    """
    import re
    from bs4 import BeautifulSoup

    # Check cache first
    if cosmetic_id in _fortnitetracker_cache:
        return _fortnitetracker_cache[cosmetic_id]

    try:
        logger.info(f"Fetching data from FortniteTracker.gg for {cosmetic_id}...")

        # Construct URL - FortniteTracker uses the cosmetic ID in the URL
        url = f"https://fortnitetracker.gg/item-shop/{cosmetic_id}"
        response = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

        if response.status_code != 200:
            logger.debug(f"FortniteTracker.gg returned {response.status_code} for {cosmetic_id}")
            _fortnitetracker_cache[cosmetic_id] = None
            return None

        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        enrichment_data = {}

        # Try to extract cosmetic name from title or headers
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text()
            # FortniteTracker titles are often like "Cosmetic Name - Fortnite Tracker"
            name_match = re.search(r'(.+?)\s*[-–]\s*Fortnite', title_text)
            if name_match:
                enrichment_data['name'] = name_match.group(1).strip()

        # Also try h1 tags
        if 'name' not in enrichment_data:
            h1_tags = soup.find_all('h1')
            if h1_tags:
                enrichment_data['name'] = h1_tags[0].get_text().strip()

        # Try to extract type and rarity from page content
        # FortniteTracker often shows these in specific elements
        text_content = soup.get_text()
        type_match = re.search(r'Type:\s*(\w+)', text_content, re.IGNORECASE)
        if type_match:
            enrichment_data['type'] = type_match.group(1).strip()

        rarity_match = re.search(r'Rarity:\s*(\w+)', text_content, re.IGNORECASE)
        if rarity_match:
            enrichment_data['rarity'] = rarity_match.group(1).strip().lower()

        # Try to extract set information
        # Look for elements that might contain set info
        set_elements = soup.find_all(text=re.compile(r'Set:', re.IGNORECASE))
        for elem in set_elements:
            parent = elem.find_parent()
            if parent:
                set_text = parent.get_text().strip()
                match = re.search(r'Set:\s*(.+)', set_text, re.IGNORECASE)
                if match:
                    enrichment_data['set_name'] = match.group(1).strip()
                    break

        # Try to extract price information from tables
        price_tables = soup.find_all('table')
        for table in price_tables:
            # Look for V-Bucks prices in table cells
            cells = table.find_all(['td', 'th'])
            for cell in cells:
                text = cell.get_text().strip()
                # Match patterns like "500" or "500 V-Bucks"
                price_match = re.search(r'(\d+)\s*(?:V-?Bucks)?', text, re.IGNORECASE)
                if price_match and 'price' in text.lower() or 'vbucks' in text.lower():
                    enrichment_data['vbucks_price'] = int(price_match.group(1))
                    break

        # Try to extract gameplay tags
        tags = []
        tag_elements = soup.find_all(class_=re.compile(r'tag', re.IGNORECASE))
        for tag_elem in tag_elements:
            tag_text = tag_elem.get_text().strip()
            if tag_text and len(tag_text) < 50:  # Reasonable tag length
                tags.append(tag_text)
        if tags:
            enrichment_data['gameplay_tags'] = tags

        # Cache the result (even if empty)
        _fortnitetracker_cache[cosmetic_id] = enrichment_data if enrichment_data else None

        if enrichment_data:
            logger.info(f"Enriched {cosmetic_id} with FortniteTracker.gg data: {list(enrichment_data.keys())}")

        return enrichment_data if enrichment_data else None

    except Exception as e:
        logger.debug(f"Error fetching FortniteTracker.gg data for {cosmetic_id}: {e}")
        _fortnitetracker_cache[cosmetic_id] = None
        return None


def enrich_cosmetics_with_fortnitetracker(cosmetics_data: List[Dict], sample_size: int = 100) -> List[Dict]:
    """
    Enrich cosmetics data with FortniteTracker.gg information

    This uses a sampling approach to avoid overwhelming FortniteTracker servers.
    Full enrichment happens on-demand when users view individual items.

    Args:
        cosmetics_data: List of cosmetics from Fortnite-API.com
        sample_size: Number of items to enrich (0 = skip bulk enrichment)

    Returns:
        Enriched cosmetics data
    """
    import time
    import random

    if not cosmetics_data or sample_size == 0:
        return cosmetics_data

    actual_sample_size = min(sample_size, len(cosmetics_data))
    logger.info(f"Starting FortniteTracker.gg enrichment for {actual_sample_size} sample cosmetics...")
    logger.info(f"This will take approximately {actual_sample_size * 0.5:.0f} seconds due to rate limiting")

    # Sample random cosmetics to enrich
    sample_cosmetics = random.sample(cosmetics_data, actual_sample_size)

    enriched_count = 0
    for idx, cosmetic in enumerate(sample_cosmetics, 1):
        cosmetic_id = cosmetic.get("id", "")
        if not cosmetic_id:
            continue

        # Log progress every 10 items
        if idx % 10 == 0 or idx == 1:
            logger.info(f"FortniteTracker enrichment progress: {idx}/{actual_sample_size} ({(idx/actual_sample_size)*100:.0f}%)")

        # Fetch enrichment data
        enrichment = fetch_fortnitetracker_item(cosmetic_id)
        if enrichment:
            # Merge enrichment data into cosmetic
            cosmetic.update(enrichment)
            enriched_count += 1

        # Rate limiting: wait between requests
        time.sleep(0.5)  # 2 requests per second max

    logger.info(f"FortniteTracker enrichment complete: enriched {enriched_count}/{actual_sample_size} cosmetics")
    return cosmetics_data


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

        logger.info(f"Loaded {len(self.owned_items)} items")
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
            logger.info(f"Set favorite status for {template_id} to {is_favorite}")
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
            logger.info(f"Saved loadout {preset_id} for type {loadout_type}")
            return True
        else:
            logger.error(f"Failed to save loadout")
            return False

    def load_loadout(self, loadout_type: str, preset_id: int) -> bool:
        """
        Load a saved cosmetic loadout

        Args:
            loadout_type: Type like "CosmeticLoadout:LoadoutSchema_Character"
            preset_id: Loadout index (0-9)

        Returns:
            True if successful, False otherwise
        """
        body = {
            "loadoutType": loadout_type,
            "presetId": preset_id
        }

        result = self._mcp_operation("EquipModularCosmeticLoadoutPreset", "athena", body)

        if result:
            logger.info(f"Loaded loadout {preset_id} for type {loadout_type}")
            return True
        else:
            logger.error(f"Failed to load loadout")
            return False


def get_locker_api(auth: EpicAuth) -> LockerAPI:
    """Get LockerAPI instance"""
    return LockerAPI(auth)
