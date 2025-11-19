"""
Fortnite Cosmetics Service
Fetches cosmetics data from Fortnite.gg with caching and rate limiting
"""
import os
import json
import time
import logging
import re
import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_DIR = Path("config/cosmetics_cache")
ITEMS_CACHE_FILE = CACHE_DIR / "fortnite_gg_items.json"
DETAILS_CACHE_DIR = CACHE_DIR / "item_details"
CACHE_EXPIRY_HOURS = 24  # Items list expires after 24 hours
DETAILS_CACHE_EXPIRY_DAYS = 7  # Item details expire after 7 days

# API endpoints
FORTNITE_GG_ITEMS_URL = "https://fortnite.gg/data/items/all-v2.en.js"
FORTNITE_GG_DETAILS_URL = "https://fortnite.gg/item-details"

# Rate limiting configuration
REQUEST_DELAY = 0.5  # Minimum delay between requests in seconds
last_request_time = 0


class FortniteCosmetics:
    """Service for fetching and caching Fortnite cosmetics from Fortnite.gg"""

    def __init__(self):
        """Initialize the cosmetics service"""
        self.items_cache = None
        self.sets_cache = None
        self.last_cache_update = None

        # Ensure cache directories exist
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        DETAILS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _rate_limit(self):
        """Implement rate limiting to avoid spamming the API"""
        global last_request_time
        current_time = time.time()
        time_since_last_request = current_time - last_request_time

        if time_since_last_request < REQUEST_DELAY:
            sleep_time = REQUEST_DELAY - time_since_last_request
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)

        last_request_time = time.time()

    def _is_cache_expired(self, cache_file: Path, expiry_hours: int) -> bool:
        """
        Check if cache file is expired

        Args:
            cache_file: Path to cache file
            expiry_hours: Number of hours before cache expires

        Returns:
            True if cache is expired or doesn't exist
        """
        if not cache_file.exists():
            return True

        try:
            cache_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
            age = datetime.now() - cache_time
            is_expired = age > timedelta(hours=expiry_hours)

            if is_expired:
                logger.info(f"Cache expired (age: {age})")
            else:
                logger.debug(f"Cache valid (age: {age})")

            return is_expired
        except Exception as e:
            logger.error(f"Error checking cache age: {e}")
            return True

    def _parse_javascript_items(self, js_content: str) -> Optional[Dict]:
        """
        Parse the JavaScript file to extract Sets and Items arrays

        Args:
            js_content: JavaScript file content

        Returns:
            Dict with 'sets' and 'items' keys, or None if parsing failed
        """
        try:
            # Extract Sets array
            sets_match = re.search(r'Sets=(\[.*?\]);', js_content, re.DOTALL)
            sets = json.loads(sets_match.group(1)) if sets_match else []

            # Extract Items array
            items_match = re.search(r'Items=(\[.*?\]);', js_content, re.DOTALL)
            if not items_match:
                logger.error("Could not find Items array in JavaScript")
                return None

            items = json.loads(items_match.group(1))

            logger.info(f"Parsed {len(items)} items and {len(sets)} sets from JavaScript")
            return {"sets": sets, "items": items}

        except Exception as e:
            logger.error(f"Error parsing JavaScript: {e}")
            return None

    def fetch_items_list(self, force_refresh: bool = False) -> Optional[List[Dict]]:
        """
        Fetch the complete items list from Fortnite.gg

        Args:
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            List of item dictionaries, or None if fetch failed
        """
        # Check cache first
        if not force_refresh and not self._is_cache_expired(ITEMS_CACHE_FILE, CACHE_EXPIRY_HOURS):
            logger.info("Loading items from cache")
            try:
                with open(ITEMS_CACHE_FILE, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    self.items_cache = cached_data.get('items', [])
                    self.sets_cache = cached_data.get('sets', [])
                    self.last_cache_update = datetime.fromtimestamp(ITEMS_CACHE_FILE.stat().st_mtime)
                    return self.items_cache
            except Exception as e:
                logger.error(f"Error loading cache: {e}")
                # Continue to fetch fresh data

        # Fetch fresh data
        logger.info(f"Fetching items list from {FORTNITE_GG_ITEMS_URL}")

        try:
            self._rate_limit()
            response = requests.get(FORTNITE_GG_ITEMS_URL, timeout=30)
            response.raise_for_status()

            # Parse JavaScript
            parsed_data = self._parse_javascript_items(response.text)
            if not parsed_data:
                return None

            self.items_cache = parsed_data['items']
            self.sets_cache = parsed_data['sets']
            self.last_cache_update = datetime.now()

            # Save to cache
            try:
                with open(ITEMS_CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(parsed_data, f, ensure_ascii=False, indent=2)
                logger.info(f"Saved {len(self.items_cache)} items to cache")
            except Exception as e:
                logger.error(f"Error saving cache: {e}")

            return self.items_cache

        except requests.RequestException as e:
            logger.error(f"Error fetching items list: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching items: {e}")
            return None

    def fetch_item_details(self, item_id: int, force_refresh: bool = False) -> Optional[Dict]:
        """
        Fetch detailed information for a specific item

        Args:
            item_id: The item ID to fetch details for
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            Dict with item details, or None if fetch failed
        """
        cache_file = DETAILS_CACHE_DIR / f"{item_id}.json"

        # Check cache first
        if not force_refresh and not self._is_cache_expired(cache_file, DETAILS_CACHE_EXPIRY_DAYS * 24):
            logger.debug(f"Loading item {item_id} details from cache")
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading cached details for item {item_id}: {e}")
                # Continue to fetch fresh data

        # Fetch fresh data
        logger.info(f"Fetching details for item {item_id}")

        try:
            self._rate_limit()
            response = requests.get(
                FORTNITE_GG_DETAILS_URL,
                params={'id': item_id},
                timeout=15
            )
            response.raise_for_status()

            # Parse HTML response to extract details
            details = self._parse_item_details_html(response.text, item_id)

            if details:
                # Save to cache
                try:
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(details, f, ensure_ascii=False, indent=2)
                    logger.debug(f"Saved details for item {item_id} to cache")
                except Exception as e:
                    logger.error(f"Error saving details cache: {e}")

            return details

        except requests.RequestException as e:
            logger.error(f"Error fetching item details: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching item details: {e}")
            return None

    def _parse_item_details_html(self, html_content: str, item_id: int) -> Optional[Dict]:
        """
        Parse HTML response to extract item details

        Args:
            html_content: HTML content from item-details page
            item_id: The item ID

        Returns:
            Dict with parsed details, or None if parsing failed
        """
        try:
            details = {"id": item_id}

            # Extract Character ID (e.g., "Character_BugBandit")
            character_id_match = re.search(r'ID:\s*([^\s<]+)', html_content)
            if character_id_match:
                details['character_id'] = character_id_match.group(1).strip()

            # Extract set name (e.g., "Part of the Moth Command set")
            set_match = re.search(r'Part of the (.+?) set', html_content)
            if set_match:
                details['set_name'] = set_match.group(1).strip()

            # Extract item name and rarity
            name_rarity_match = re.search(r'<h1[^>]*>(.+?)</h1>\s*<p[^>]*>(.+?)</p>', html_content, re.DOTALL)
            if name_rarity_match:
                details['name'] = re.sub(r'<[^>]+>', '', name_rarity_match.group(1)).strip()
                details['rarity'] = re.sub(r'<[^>]+>', '', name_rarity_match.group(2)).strip()

            # Extract description
            desc_match = re.search(r'<p class="description[^"]*">(.+?)</p>', html_content, re.DOTALL)
            if desc_match:
                details['description'] = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()

            # Extract release information
            # Source
            source_match = re.search(r'Source:\s*</td>\s*<td[^>]*>(.+?)</td>', html_content, re.DOTALL)
            if source_match:
                details['source'] = re.sub(r'<[^>]+>', '', source_match.group(1)).strip()

            # Introduced in
            intro_match = re.search(r'Introduced in:\s*</td>\s*<td[^>]*>(.+?)</td>', html_content, re.DOTALL)
            if intro_match:
                details['introduced_in'] = re.sub(r'<[^>]+>', '', intro_match.group(1)).strip()

            # Release date
            release_match = re.search(r'Release date:\s*</td>\s*<td[^>]*>(.+?)</td>', html_content, re.DOTALL)
            if release_match:
                details['release_date'] = re.sub(r'<[^>]+>', '', release_match.group(1)).strip()

            # Last seen
            last_seen_match = re.search(r'Last seen:\s*</td>\s*<td[^>]*>(.+?)</td>', html_content, re.DOTALL)
            if last_seen_match:
                details['last_seen'] = re.sub(r'<[^>]+>', '', last_seen_match.group(1)).strip()

            # Occurrences
            occurrences_match = re.search(r'Occurrences:\s*</td>\s*<td[^>]*>(\d+)</td>', html_content)
            if occurrences_match:
                details['occurrences'] = int(occurrences_match.group(1))

            logger.debug(f"Parsed details for item {item_id}: {details.get('name', 'Unknown')}")
            return details

        except Exception as e:
            logger.error(f"Error parsing item details HTML: {e}")
            return None

    def search_items(self, query: str, filters: Optional[Dict] = None) -> List[Dict]:
        """
        Search items by name or other criteria

        Args:
            query: Search query string
            filters: Optional filters dict (e.g., {'type': 1, 'rarity': 4})

        Returns:
            List of matching items
        """
        if not self.items_cache:
            self.fetch_items_list()

        if not self.items_cache:
            return []

        results = []
        query_lower = query.lower()

        for item in self.items_cache:
            # Name search
            name = item.get('name', '').lower()
            if query_lower in name:
                # Apply filters if provided
                if filters:
                    match = True
                    for key, value in filters.items():
                        if item.get(key) != value:
                            match = False
                            break
                    if match:
                        results.append(item)
                else:
                    results.append(item)

        return results

    def get_item_by_id(self, item_id: int) -> Optional[Dict]:
        """
        Get an item by its ID

        Args:
            item_id: The item ID

        Returns:
            Item dict or None if not found
        """
        if not self.items_cache:
            self.fetch_items_list()

        if not self.items_cache:
            return None

        for item in self.items_cache:
            if item.get('id') == item_id:
                return item

        return None

    def get_items_by_type(self, item_type: int) -> List[Dict]:
        """
        Get all items of a specific type

        Args:
            item_type: Type number (e.g., 1 for Outfit, 2 for Back Bling, etc.)

        Returns:
            List of items matching the type
        """
        if not self.items_cache:
            self.fetch_items_list()

        if not self.items_cache:
            return []

        return [item for item in self.items_cache if item.get('type') == item_type]

    def get_items_by_rarity(self, rarity: int) -> List[Dict]:
        """
        Get all items of a specific rarity

        Args:
            rarity: Rarity number (1=common, 2=uncommon, 3=rare, 4=epic, 5=legendary, etc.)

        Returns:
            List of items matching the rarity
        """
        if not self.items_cache:
            self.fetch_items_list()

        if not self.items_cache:
            return []

        return [item for item in self.items_cache if item.get('r') == rarity]

    def get_items_by_set(self, set_index: int) -> List[Dict]:
        """
        Get all items belonging to a specific set

        Args:
            set_index: Index in the Sets array

        Returns:
            List of items in the set
        """
        if not self.items_cache:
            self.fetch_items_list()

        if not self.items_cache:
            return []

        return [item for item in self.items_cache if item.get('set') == set_index]

    def get_set_name(self, set_index: int) -> Optional[str]:
        """
        Get the name of a set by its index

        Args:
            set_index: Index in the Sets array

        Returns:
            Set name or None if not found
        """
        if not self.sets_cache:
            self.fetch_items_list()

        if not self.sets_cache or set_index < 0 or set_index >= len(self.sets_cache):
            return None

        return self.sets_cache[set_index]

    def clear_cache(self):
        """Clear all cached data"""
        try:
            if ITEMS_CACHE_FILE.exists():
                ITEMS_CACHE_FILE.unlink()
                logger.info("Cleared items cache")

            # Clear details cache
            for cache_file in DETAILS_CACHE_DIR.glob("*.json"):
                cache_file.unlink()
            logger.info("Cleared item details cache")

            self.items_cache = None
            self.sets_cache = None
            self.last_cache_update = None

        except Exception as e:
            logger.error(f"Error clearing cache: {e}")


# Global instance
_cosmetics_service = None


def get_cosmetics_service() -> FortniteCosmetics:
    """Get or create the global cosmetics service instance"""
    global _cosmetics_service
    if _cosmetics_service is None:
        _cosmetics_service = FortniteCosmetics()
    return _cosmetics_service


# Type mapping for reference
ITEM_TYPE_MAP = {
    1: "Outfit",
    2: "Back Bling",
    3: "Pickaxe",
    4: "Glider",
    5: "Aura",
    6: "Emote",
    7: "Wrap",
    9: "Contrail",
    10: "Loading Screen",
    11: "Emoji",
    12: "Spray",
    13: "Banner",
    14: "Bundle",
    15: "Banner",
    16: "Banner Icon",
    17: "Vehicle",
    18: "Decal",
    19: "Wheel",
    20: "Music",
    22: "Instrument",
    25: "Guitar",
    29: "Trail",
    30: "Boost",
    31: "Shoes",
    32: "Pet"
}

RARITY_MAP = {
    1: "Common",
    2: "Uncommon",
    3: "Rare",
    4: "Epic",
    5: "Legendary",
    11: "Mythic"
}
