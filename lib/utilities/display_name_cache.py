"""
Display Name Cache with Persistent Storage
Caches Epic account ID to display name mappings for 3 days
"""
import os
import json
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DisplayNameCache:
    """Persistent cache for Epic account ID to display name mappings"""

    def __init__(self, cache_file: str = "display_name_cache.json", expiry_days: int = 3):
        """
        Initialize display name cache

        Args:
            cache_file: Path to cache file
            expiry_days: Number of days before cache entries expire
        """
        self.cache_file = cache_file
        self.expiry_days = expiry_days
        self.cache: Dict[str, dict] = {}
        self.load_cache()

    def load_cache(self):
        """Load cache from file"""
        if not os.path.exists(self.cache_file):
            logger.info("No display name cache file found, starting fresh")
            return

        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)

            # Filter out expired entries
            now = datetime.now()
            valid_entries = {}

            for account_id, entry in data.items():
                cached_at_str = entry.get('cached_at')
                if cached_at_str:
                    cached_at = datetime.fromisoformat(cached_at_str)
                    age_days = (now - cached_at).days

                    if age_days < self.expiry_days:
                        valid_entries[account_id] = entry
                    else:
                        logger.debug(f"Expired cache entry for {account_id} (age: {age_days} days)")

            self.cache = valid_entries
            logger.info(f"Loaded {len(self.cache)} valid display name cache entries")

        except Exception as e:
            logger.error(f"Error loading display name cache: {e}")
            self.cache = {}

    def save_cache(self):
        """Save cache to file"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
            logger.debug(f"Saved {len(self.cache)} display name cache entries")
        except Exception as e:
            logger.error(f"Error saving display name cache: {e}")

    def get(self, account_id: str) -> Optional[str]:
        """
        Get cached display name for account ID

        Args:
            account_id: Epic account ID

        Returns:
            Display name if cached and valid, None otherwise
        """
        entry = self.cache.get(account_id)
        if entry:
            return entry.get('display_name')
        return None

    def set(self, account_id: str, display_name: str):
        """
        Cache a display name for an account ID

        Args:
            account_id: Epic account ID
            display_name: Display name to cache
        """
        self.cache[account_id] = {
            'display_name': display_name,
            'cached_at': datetime.now().isoformat()
        }

    def set_bulk(self, mappings: Dict[str, str]):
        """
        Cache multiple display names at once

        Args:
            mappings: Dictionary mapping account IDs to display names
        """
        now = datetime.now().isoformat()
        for account_id, display_name in mappings.items():
            self.cache[account_id] = {
                'display_name': display_name,
                'cached_at': now
            }

    def has(self, account_id: str) -> bool:
        """Check if account ID is in cache"""
        return account_id in self.cache

    def clear_expired(self):
        """Remove expired entries from cache"""
        now = datetime.now()
        expired_ids = []

        for account_id, entry in self.cache.items():
            cached_at_str = entry.get('cached_at')
            if cached_at_str:
                cached_at = datetime.fromisoformat(cached_at_str)
                age_days = (now - cached_at).days

                if age_days >= self.expiry_days:
                    expired_ids.append(account_id)

        for account_id in expired_ids:
            del self.cache[account_id]

        if expired_ids:
            logger.info(f"Cleared {len(expired_ids)} expired cache entries")
            self.save_cache()


# Global cache instance
_display_name_cache: Optional[DisplayNameCache] = None


def get_display_name_cache() -> DisplayNameCache:
    """Get or create global display name cache instance"""
    global _display_name_cache
    if _display_name_cache is None:
        _display_name_cache = DisplayNameCache()
    return _display_name_cache
