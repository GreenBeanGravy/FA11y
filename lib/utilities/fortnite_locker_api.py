"""
Fortnite Locker API Service
Direct API integration for equipping cosmetics via Epic's MCP endpoints
No UI automation needed!
"""
import os
import json
import time
import logging
import requests
from typing import List, Dict, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# MCP endpoints
MCP_BASE = "https://fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api/game/v2/profile"


class FortniteLockerAPI:
    """Service for directly managing Fortnite locker via Epic's API"""

    def __init__(self, auth_instance):
        """
        Initialize the locker API service

        Args:
            auth_instance: EpicAuth instance with valid access token
        """
        self.auth = auth_instance
        self.profile_data = None
        self.owned_items = {}  # GUID -> item data
        self.template_id_map = {}  # template_id -> GUID mapping

    def _get_headers(self) -> Dict[str, str]:
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.auth.access_token}",
            "Content-Type": "application/json"
        }

    def _mcp_operation(self, operation: str, profile_id: str = "athena",
                       body: Optional[Dict] = None) -> Optional[Dict]:
        """
        Execute an MCP operation

        Args:
            operation: Operation name (e.g., "QueryProfile", "SetCosmeticLockerSlot")
            profile_id: Profile ID (default: "athena")
            body: Request body

        Returns:
            Response JSON or None if failed
        """
        if not self.auth.access_token or not self.auth.account_id:
            logger.error("Not authenticated")
            return None

        url = f"{MCP_BASE}/{self.auth.account_id}/client/{operation}"
        params = {"profileId": profile_id}
        body = body or {}

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                params=params,
                json=body,
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"{operation} failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error in {operation}: {e}")
            return None

    def load_profile(self, force_refresh: bool = False) -> bool:
        """
        Load the athena profile (locker)

        Args:
            force_refresh: Force refresh even if already loaded

        Returns:
            True if successful
        """
        if self.profile_data and not force_refresh:
            return True

        logger.info("Loading athena profile...")
        result = self._mcp_operation("QueryProfile", "athena")

        if not result:
            return False

        # Extract profile data
        self.profile_data = result.get("profileChanges", [{}])[0].get("profile", {})
        items = self.profile_data.get("items", {})

        # Build owned items map
        self.owned_items = {}
        self.template_id_map = {}

        for guid, item_data in items.items():
            template_id = item_data.get("templateId", "")
            if template_id:
                self.owned_items[guid] = item_data
                self.template_id_map[template_id] = guid

        logger.info(f"Loaded {len(self.owned_items)} items from profile")
        return True

    def get_owned_template_ids(self) -> List[str]:
        """
        Get list of all owned cosmetic template IDs

        Returns:
            List of template IDs (e.g., ["AthenaCharacter:CID_029_Athena_Commando_F_Halloween", ...])
        """
        if not self.profile_data:
            self.load_profile()

        return list(self.template_id_map.keys())

    def get_owned_cosmetic_ids(self) -> List[str]:
        """
        Get list of owned cosmetic IDs (stripped format for matching)

        Returns:
            List of IDs (e.g., ["CID_029_Athena_Commando_F_Halloween", ...])
        """
        template_ids = self.get_owned_template_ids()
        cosmetic_ids = []

        for template_id in template_ids:
            if ":" in template_id:
                cosmetic_id = template_id.split(":", 1)[1]
                cosmetic_ids.append(cosmetic_id)

        return cosmetic_ids

    def equip_cosmetic(self, template_id: str, category: str = "Character",
                       slot_index: int = 0, locker_guid: Optional[str] = None,
                       variants: Optional[List[Dict]] = None) -> bool:
        """
        Equip a cosmetic item

        Args:
            template_id: Full template ID (e.g., "AthenaCharacter:CID_029_Athena_Commando_F_Halloween")
            category: Category (Character, Backpack, Dance, Pickaxe, Glider, etc.)
            slot_index: Slot index (0 for most items, 0-5 for emotes, 0-6 for wraps)
            locker_guid: Locker item GUID (empty string uses current locker)
            variants: List of variant updates (optional)

        Returns:
            True if successful
        """
        logger.info(f"Equipping {template_id} to {category} slot {slot_index}")

        body = {
            "lockerItem": locker_guid or "",
            "category": category,
            "itemToSlot": template_id,
            "slotIndex": slot_index,
            "variantUpdates": variants or [],
            "optLockerUseCountOverride": 0
        }

        result = self._mcp_operation("SetCosmeticLockerSlot", "athena", body)
        return result is not None

    def equip_multiple_cosmetics(self, loadout: List[Dict],
                                  locker_guid: Optional[str] = None) -> bool:
        """
        Equip multiple cosmetics at once

        Args:
            loadout: List of dicts with keys: category, itemToSlot, slotIndex, variantUpdates
            locker_guid: Locker item GUID (empty string uses current locker)

        Returns:
            True if successful

        Example loadout:
            [
                {
                    "category": "Character",
                    "itemToSlot": "AthenaCharacter:CID_029_Athena_Commando_F_Halloween",
                    "slotIndex": 0,
                    "variantUpdates": []
                },
                {
                    "category": "Backpack",
                    "itemToSlot": "AthenaBackpack:BID_123_BlackKnight",
                    "slotIndex": 0,
                    "variantUpdates": []
                }
            ]
        """
        logger.info(f"Equipping {len(loadout)} cosmetics")

        body = {
            "lockerItem": locker_guid or "",
            "loadoutData": loadout
        }

        result = self._mcp_operation("SetCosmeticLockerSlots", "athena", body)
        return result is not None

    def set_favorite(self, item_guid: str, is_favorite: bool) -> bool:
        """
        Set favorite status for a single item

        Args:
            item_guid: Item GUID from profile
            is_favorite: True to favorite, False to unfavorite

        Returns:
            True if successful
        """
        body = {
            "itemId": item_guid,
            "bFavorite": is_favorite
        }

        result = self._mcp_operation("SetItemFavoriteStatus", "athena", body)
        return result is not None

    def set_favorites_batch(self, items: List[Tuple[str, bool]]) -> bool:
        """
        Set favorite status for multiple items

        Args:
            items: List of (item_guid, is_favorite) tuples

        Returns:
            True if successful
        """
        item_ids = [item[0] for item in items]
        statuses = [item[1] for item in items]

        body = {
            "itemIds": item_ids,
            "itemFavStatus": statuses
        }

        result = self._mcp_operation("SetItemFavoriteStatusBatch", "athena", body)
        return result is not None

    def get_current_loadout(self) -> Dict[str, str]:
        """
        Get currently equipped cosmetics

        Returns:
            Dict mapping category to template_id
        """
        if not self.profile_data:
            self.load_profile()

        loadout = {}
        stats = self.profile_data.get("stats", {}).get("attributes", {})

        # Extract loadout from profile stats
        # The structure varies, but typically stored in favorite_character, favorite_backpack, etc.
        for key, value in stats.items():
            if key.startswith("favorite_"):
                category = key.replace("favorite_", "").title()
                if value:
                    loadout[category] = value

        return loadout

    def build_template_id(self, cosmetic_type: str, cosmetic_id: str) -> str:
        """
        Build full template ID from type and ID

        Args:
            cosmetic_type: Type like "Outfit", "Back Bling", "Pickaxe", etc.
            cosmetic_id: ID like "CID_029_Athena_Commando_F_Halloween"

        Returns:
            Full template ID (e.g., "AthenaCharacter:CID_029_Athena_Commando_F_Halloween")
        """
        type_map = {
            "Outfit": "AthenaCharacter",
            "Back Bling": "AthenaBackpack",
            "Pickaxe": "AthenaPickaxe",
            "Glider": "AthenaGlider",
            "Contrail": "AthenaSkyDiveContrail",
            "Emote": "AthenaDance",
            "Wrap": "AthenaItemWrap",
            "Loading Screen": "AthenaLoadingScreen",
            "Music": "AthenaMusicPack",
            "Pet": "AthenaPetCarrier",
            "Kicks": "AthenaShoes",
            "Car Body": "VehicleCosmetics_Body"
        }

        backend_type = type_map.get(cosmetic_type, cosmetic_type)
        return f"{backend_type}:{cosmetic_id}"

    def extract_cosmetic_id(self, template_id: str) -> str:
        """
        Extract cosmetic ID from template ID

        Args:
            template_id: Full template ID (e.g., "AthenaCharacter:CID_029_Athena_Commando_F_Halloween")

        Returns:
            Cosmetic ID (e.g., "CID_029_Athena_Commando_F_Halloween")
        """
        if ":" in template_id:
            return template_id.split(":", 1)[1]
        return template_id

    def get_category_for_type(self, cosmetic_type: str) -> str:
        """
        Get category name for equipping

        Args:
            cosmetic_type: Type like "Outfit", "Back Bling", etc.

        Returns:
            Category name for API (e.g., "Character", "Backpack")
        """
        category_map = {
            "Outfit": "Character",
            "Back Bling": "Backpack",
            "Pickaxe": "Pickaxe",
            "Glider": "Glider",
            "Contrail": "SkyDiveContrail",
            "Emote": "Dance",
            "Wrap": "ItemWrap",
            "Loading Screen": "LoadingScreen",
            "Music": "MusicPack",
            "Pet": "PetCarrier",
            "Kicks": "Shoes"
        }

        return category_map.get(cosmetic_type, cosmetic_type)


# Category to type mapping for Fortnite.gg data
FORTNITE_GG_TYPE_MAP = {
    1: {"name": "Outfit", "category": "Character", "backend": "AthenaCharacter"},
    2: {"name": "Back Bling", "category": "Backpack", "backend": "AthenaBackpack"},
    3: {"name": "Pickaxe", "category": "Pickaxe", "backend": "AthenaPickaxe"},
    4: {"name": "Glider", "category": "Glider", "backend": "AthenaGlider"},
    5: {"name": "Aura", "category": "Aura", "backend": "AthenaAura"},
    6: {"name": "Emote", "category": "Dance", "backend": "AthenaDance"},
    7: {"name": "Wrap", "category": "ItemWrap", "backend": "AthenaItemWrap"},
    9: {"name": "Contrail", "category": "SkyDiveContrail", "backend": "AthenaSkyDiveContrail"},
    10: {"name": "Loading Screen", "category": "LoadingScreen", "backend": "AthenaLoadingScreen"},
    20: {"name": "Music", "category": "MusicPack", "backend": "AthenaMusicPack"},
    31: {"name": "Kicks", "category": "Shoes", "backend": "AthenaShoes"},
    32: {"name": "Pet", "category": "PetCarrier", "backend": "AthenaPetCarrier"}
}


def get_locker_api(auth_instance) -> FortniteLockerAPI:
    """Get a new FortniteLockerAPI instance"""
    return FortniteLockerAPI(auth_instance)
