"""
Hybrid Fortnite Cosmetics Service
Combines Fortnite-API.com and Fortnite.gg to handle missing items
"""
import logging
from typing import List, Dict, Optional
from lib.utilities.fortnite_cosmetics import get_cosmetics_service, ITEM_TYPE_MAP, RARITY_MAP

logger = logging.getLogger(__name__)


class HybridCosmeticsService:
    """
    Hybrid service that uses both Fortnite-API.com and Fortnite.gg

    Strategy:
    1. Use Fortnite-API.com as primary source (has proper CIDs)
    2. Use Fortnite.gg to fill in missing items
    3. Extract CID patterns from owned items for better matching
    """

    def __init__(self, fortnite_api_data: List[Dict], auth_instance=None):
        """
        Initialize hybrid service

        Args:
            fortnite_api_data: Data from Fortnite-API.com
            auth_instance: EpicAuth instance (optional, for owned items)
        """
        self.fortnite_api_data = fortnite_api_data
        self.auth = auth_instance
        self.fortnite_gg = get_cosmetics_service()

        # Build lookup maps
        self.cid_to_cosmetic = {}  # CID -> cosmetic data
        self.name_to_cosmetic = {}  # name.lower() -> cosmetic data

        for cosmetic in fortnite_api_data:
            cid = cosmetic.get('id', '').lower()
            name = cosmetic.get('name', '').lower()

            if cid:
                self.cid_to_cosmetic[cid] = cosmetic
            if name:
                self.name_to_cosmetic[name] = cosmetic

    def get_cosmetic_by_cid(self, cid: str) -> Optional[Dict]:
        """
        Get cosmetic by CID, trying both sources

        Args:
            cid: Cosmetic ID (e.g., "CID_035_Athena_Commando_M_Medieval")

        Returns:
            Cosmetic dict or None
        """
        # Try Fortnite-API.com first
        cosmetic = self.cid_to_cosmetic.get(cid.lower())
        if cosmetic:
            return cosmetic

        # Try to match from Fortnite.gg by name patterns
        # Extract name pattern from CID if possible
        logger.warning(f"CID {cid} not found in Fortnite-API.com, searching Fortnite.gg...")

        return self._create_placeholder_from_cid(cid)

    def get_cosmetic_by_name(self, name: str) -> Optional[Dict]:
        """
        Get cosmetic by name, trying both sources

        Args:
            name: Cosmetic name

        Returns:
            Cosmetic dict or None
        """
        # Try Fortnite-API.com first
        cosmetic = self.name_to_cosmetic.get(name.lower())
        if cosmetic:
            return cosmetic

        # Try Fortnite.gg
        logger.info(f"'{name}' not found in Fortnite-API.com, searching Fortnite.gg...")
        gg_results = self.fortnite_gg.search_items(name)

        if gg_results:
            # Convert Fortnite.gg item to our format
            return self._convert_from_fortnite_gg(gg_results[0])

        return None

    def enrich_with_fortnite_gg(self, cosmetic: Dict) -> Dict:
        """
        Enrich cosmetic data with Fortnite.gg details

        Args:
            cosmetic: Cosmetic dict from Fortnite-API.com

        Returns:
            Enhanced cosmetic dict
        """
        name = cosmetic.get('name', '')
        if not name:
            return cosmetic

        # Search Fortnite.gg
        gg_results = self.fortnite_gg.search_items(name)
        if not gg_results:
            return cosmetic

        # Get the first match (should be exact if name matches)
        gg_item = gg_results[0]

        # Fetch detailed info
        details = self.fortnite_gg.fetch_item_details(gg_item['id'])

        if details:
            # Add Fortnite.gg data to cosmetic
            cosmetic['fortnite_gg'] = {
                'id': gg_item['id'],
                'character_id': details.get('character_id'),
                'set_name': details.get('set_name'),
                'last_seen': details.get('last_seen'),
                'release_date': details.get('release_date'),
                'occurrences': details.get('occurrences'),
                'source': details.get('source')
            }

        return cosmetic

    def fill_missing_items(self, owned_cids: List[str]) -> List[Dict]:
        """
        Create entries for owned items missing from Fortnite-API.com
        Uses Fortnite.gg to get better data than generic placeholders

        Args:
            owned_cids: List of owned cosmetic IDs

        Returns:
            List of cosmetic dicts for missing items
        """
        existing_cids = set(self.cid_to_cosmetic.keys())
        missing_cids = [cid for cid in owned_cids if cid.lower() not in existing_cids]

        if not missing_cids:
            return []

        logger.info(f"Found {len(missing_cids)} owned items missing from Fortnite-API.com")

        # Load Fortnite.gg data if not already loaded
        if not self.fortnite_gg.items_cache:
            self.fortnite_gg.fetch_items_list()

        missing_items = []

        for cid in missing_cids:
            # Try to create better entry using CID patterns and Fortnite.gg
            cosmetic = self._create_enhanced_placeholder(cid)
            if cosmetic:
                missing_items.append(cosmetic)

        return missing_items

    def _create_enhanced_placeholder(self, cid: str) -> Dict:
        """
        Create enhanced placeholder using CID patterns and Fortnite.gg data

        Args:
            cid: Cosmetic ID

        Returns:
            Cosmetic dict
        """
        # Parse CID to extract type
        cosmetic_type = self._extract_type_from_cid(cid)

        # Try to find similar items in Fortnite.gg
        # Look for items with matching type
        matching_items = None
        if self.fortnite_gg.items_cache:
            type_num = self._get_fortnite_gg_type_num(cosmetic_type)
            if type_num:
                matching_items = [item for item in self.fortnite_gg.items_cache
                                if item.get('type') == type_num]

        # Create enhanced placeholder
        placeholder = {
            "id": cid,
            "name": self._beautify_cid_name(cid),
            "description": f"Owned cosmetic (CID: {cid})",
            "type": cosmetic_type,
            "rarity": "common",
            "rarity_value": 0,
            "introduction_chapter": "?",
            "introduction_season": "?",
            "image_url": "",
            "favorite": False,
            "missing_from_api": True  # Flag to identify these
        }

        # Try to get more info from Fortnite.gg by searching the beautified name
        name_search = self._beautify_cid_name(cid)
        gg_results = self.fortnite_gg.search_items(name_search)

        if gg_results:
            # Found a potential match
            gg_item = gg_results[0]
            details = self.fortnite_gg.fetch_item_details(gg_item['id'])

            if details:
                # Update placeholder with Fortnite.gg data
                placeholder['name'] = gg_item.get('name', placeholder['name'])
                placeholder['description'] = details.get('description', placeholder['description'])

                # Map Fortnite.gg rarity to our format
                gg_rarity = gg_item.get('r', 1)
                placeholder['rarity'] = RARITY_MAP.get(gg_rarity, 'common').lower()
                placeholder['rarity_value'] = gg_rarity

                # Add season info if available
                if gg_item.get('season'):
                    placeholder['introduction_season'] = str(gg_item['season'])

                # Add Fortnite.gg metadata
                placeholder['fortnite_gg'] = {
                    'id': gg_item['id'],
                    'character_id': details.get('character_id'),
                    'set_name': details.get('set_name'),
                    'last_seen': details.get('last_seen'),
                    'release_date': details.get('release_date'),
                    'occurrences': details.get('occurrences')
                }

                logger.info(f"Enhanced placeholder for {cid} with Fortnite.gg data: {placeholder['name']}")

        return placeholder

    def _create_placeholder_from_cid(self, cid: str) -> Dict:
        """Create basic placeholder from CID"""
        cosmetic_type = self._extract_type_from_cid(cid)

        return {
            "id": cid,
            "name": self._beautify_cid_name(cid),
            "description": f"Item not in database (CID: {cid})",
            "type": cosmetic_type,
            "rarity": "common",
            "rarity_value": 0,
            "introduction_chapter": "?",
            "introduction_season": "?",
            "image_url": "",
            "favorite": False,
            "missing_from_api": True
        }

    def _convert_from_fortnite_gg(self, gg_item: Dict) -> Dict:
        """
        Convert Fortnite.gg item to our format

        Args:
            gg_item: Item from Fortnite.gg

        Returns:
            Cosmetic dict in our format
        """
        # Get type info
        type_num = gg_item.get('type', 1)
        type_info = ITEM_TYPE_MAP.get(type_num, "Unknown")

        # Get rarity
        rarity_num = gg_item.get('r', 1)
        rarity = RARITY_MAP.get(rarity_num, 'Common').lower()

        # Fetch details for more info
        details = self.fortnite_gg.fetch_item_details(gg_item['id'])
        character_id = details.get('character_id', '') if details else ''

        # Try to construct a CID from the character_id
        # This is a best-guess approach
        cid = self._guess_cid_from_character_id(character_id, type_num)

        cosmetic = {
            "id": cid,
            "name": gg_item.get('name', 'Unknown'),
            "description": details.get('description', '') if details else '',
            "type": self._map_gg_type_to_backend(type_num),
            "rarity": rarity,
            "rarity_value": rarity_num,
            "introduction_chapter": "?",
            "introduction_season": str(gg_item.get('season', '?')),
            "image_url": "",
            "favorite": False,
            "from_fortnite_gg": True,
            "fortnite_gg": {
                'id': gg_item['id'],
                'character_id': character_id,
                'set_name': details.get('set_name', '') if details else '',
                'last_seen': details.get('last_seen', '') if details else '',
                'release_date': details.get('release_date', '') if details else ''
            }
        }

        return cosmetic

    def _extract_type_from_cid(self, cid: str) -> str:
        """
        Extract cosmetic type from CID pattern

        Args:
            cid: Cosmetic ID

        Returns:
            Backend type (e.g., "AthenaCharacter")
        """
        cid_upper = cid.upper()

        if cid_upper.startswith('CID_'):
            return 'AthenaCharacter'
        elif cid_upper.startswith('BID_'):
            return 'AthenaBackpack'
        elif cid_upper.startswith('PICKAXE_ID_') or cid_upper.startswith('PID_'):
            return 'AthenaPickaxe'
        elif cid_upper.startswith('GLIDER_ID_') or cid_upper.startswith('GLID_'):
            return 'AthenaGlider'
        elif cid_upper.startswith('EID_'):
            return 'AthenaDance'
        elif cid_upper.startswith('WRAP_'):
            return 'AthenaItemWrap'
        elif cid_upper.startswith('TRAILS_ID_'):
            return 'AthenaSkyDiveContrail'
        elif cid_upper.startswith('MUSICPACK_'):
            return 'AthenaMusicPack'
        elif cid_upper.startswith('LOADINGSCREEN_'):
            return 'AthenaLoadingScreen'
        elif cid_upper.startswith('PETCARRIER_'):
            return 'AthenaPetCarrier'
        else:
            return 'Unknown'

    def _beautify_cid_name(self, cid: str) -> str:
        """
        Convert CID to readable name

        Args:
            cid: Cosmetic ID

        Returns:
            Readable name
        """
        # Remove prefix and convert to title case
        import re

        # Remove common prefixes
        name = re.sub(r'^(CID|BID|EID|PICKAXE_ID|GLIDER_ID|WRAP|TRAILS_ID|MUSICPACK|LOADINGSCREEN|PETCARRIER)_', '', cid, flags=re.IGNORECASE)

        # Remove _Athena_* patterns
        name = re.sub(r'_Athena_\w+', '', name, flags=re.IGNORECASE)

        # Replace underscores with spaces
        name = name.replace('_', ' ')

        # Title case
        name = name.title()

        return name or cid

    def _get_fortnite_gg_type_num(self, backend_type: str) -> Optional[int]:
        """Map backend type to Fortnite.gg type number"""
        from lib.utilities.fortnite_locker_api import FORTNITE_GG_TYPE_MAP

        for type_num, info in FORTNITE_GG_TYPE_MAP.items():
            if info['backend'] == backend_type:
                return type_num
        return None

    def _map_gg_type_to_backend(self, type_num: int) -> str:
        """Map Fortnite.gg type number to backend type"""
        from lib.utilities.fortnite_locker_api import FORTNITE_GG_TYPE_MAP

        info = FORTNITE_GG_TYPE_MAP.get(type_num, {})
        return info.get('backend', 'Unknown')

    def _guess_cid_from_character_id(self, character_id: str, type_num: int) -> str:
        """
        Try to guess CID from Character_ID

        This is a best-effort approach and may not always be accurate

        Args:
            character_id: Character ID from Fortnite.gg (e.g., "Character_BugBandit")
            type_num: Fortnite.gg type number

        Returns:
            Guessed CID
        """
        if not character_id:
            return f"UNKNOWN_{type_num}"

        # Remove "Character_" prefix if present
        base_name = character_id.replace('Character_', '').replace('character_', '')

        # Get type prefix
        type_prefixes = {
            1: 'CID',      # Outfit
            2: 'BID',      # Back Bling
            3: 'Pickaxe_ID',  # Pickaxe
            4: 'Glider_ID',   # Glider
            6: 'EID',      # Emote
            7: 'Wrap',     # Wrap
            9: 'Trails_ID', # Contrail
            10: 'LoadingScreen',  # Loading Screen
            20: 'MusicPack',  # Music
            31: 'Shoes',   # Kicks
            32: 'PetCarrier'  # Pet
        }

        prefix = type_prefixes.get(type_num, 'UNKNOWN')

        # Construct a likely CID
        # Note: This is a GUESS and may not be the actual CID
        return f"{prefix}_{base_name}"


def get_hybrid_cosmetics_service(fortnite_api_data: List[Dict], auth_instance=None) -> HybridCosmeticsService:
    """Get a new HybridCosmeticsService instance"""
    return HybridCosmeticsService(fortnite_api_data, auth_instance)
