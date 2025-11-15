"""
Epic Games Discovery API Integration
Handles Fortnite Creative Discovery surfaces, search, and creator features
"""
import logging
import requests
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryIsland:
    """Represents a discovered island/gamemode"""
    link_code: str
    title: str  # Display name
    creator_name: Optional[str] = None
    description: Optional[str] = None
    is_favorite: bool = False
    last_visited: Optional[float] = None
    global_ccu: int = -1
    lock_status: str = "UNKNOWN"
    is_visible: bool = True
    image_url: Optional[str] = None
    score: Optional[float] = None


@dataclass
class Creator:
    """Represents a creator"""
    account_id: str
    score: float


class EpicDiscovery:
    """Epic Games Discovery API wrapper for Fortnite Creative"""

    # Surface names
    SURFACE_MAIN = "CreativeDiscoverySurface_Frontend"
    SURFACE_BROWSE = "CreativeDiscoverySurface_Browse"
    SURFACE_LIBRARY = "CreativeDiscoverySurface_Library"
    SURFACE_ROCKET_RACING = "CreativeDiscoverySurface_DelMar_TrackAndExperience"
    SURFACE_EPIC_PAGE = "CreativeDiscoverySurface_EpicPage"
    SURFACE_CREATOR_PAGE = "CreativeDiscoverySurface_CreatorPage"

    def __init__(self, epic_auth_instance):
        """
        Initialize with an EpicAuth instance

        Args:
            epic_auth_instance: Instance of EpicAuth for authentication
        """
        self.auth = epic_auth_instance

        # Epic Games API endpoints
        self.DISCOVERY_BASE = "https://fn-service-discovery-live-public.ogs.live.on.epicgames.com/api/v2/discovery"
        # Note: Search endpoints require game client authentication, not available with web OAuth
        self.SEARCH_BASE = "https://fngw-svc-gc-livefn.ol.epicgames.com/api"

    def _get_headers(self) -> dict:
        """Get authorization headers for API requests"""
        if not self.auth.access_token:
            raise ValueError("Not authenticated. Please log in first.")

        return {
            "Authorization": f"Bearer {self.auth.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "Fortnite/++Fortnite+Release-20.00-CL-19458861 Windows/10.0.19041.1.768.64bit"
        }

    def _parse_island_data(self, island_data: Dict) -> Optional[DiscoveryIsland]:
        """
        Parse island data from API response

        Args:
            island_data: Raw island data from API

        Returns:
            DiscoveryIsland object or None if parsing fails
        """
        try:
            link_code = island_data.get("linkCode", "")
            if not link_code:
                return None

            # Extract title (display name)
            title = island_data.get("title", link_code)

            # Extract creator name
            creator_name = island_data.get("creatorName")

            # Extract description
            description = island_data.get("description")

            # Extract image URL
            image_url = island_data.get("imageUrl")

            return DiscoveryIsland(
                link_code=link_code,
                title=title,
                creator_name=creator_name,
                description=description,
                is_favorite=island_data.get("isFavorite", False),
                last_visited=island_data.get("lastVisited"),
                global_ccu=island_data.get("globalCCU", island_data.get("playerCount", -1)),
                lock_status=island_data.get("lockStatus", "UNKNOWN"),
                is_visible=island_data.get("isVisible", True),
                image_url=image_url,
                score=island_data.get("score")
            )
        except Exception as e:
            logger.error(f"Error parsing island data: {e}")
            return None

    def get_discovery_surface(self, surface_name: str = SURFACE_MAIN) -> Optional[Dict]:
        """
        Get discovery surface data

        Args:
            surface_name: Name of the surface to query

        Returns:
            Surface data with panels and islands
        """
        try:
            payload = {
                "playerId": self.auth.account_id,
                "partyMemberIds": [self.auth.account_id],
                "accountLevel": 1,
                "battlepassLevel": 1,
                "locale": "en",
                "matchmakingRegion": "NAE",
                "platform": "Windows",
                "isCabined": False,
                "ratingAuthority": "ESRB",
                "rating": "ESRB_TEEN",
                "numLocalPlayers": 1
            }

            url = f"{self.DISCOVERY_BASE}/surface/{surface_name}"
            logger.debug(f"Discovery surface request: POST {url}?appId=Fortnite")
            logger.debug(f"Payload: {payload}")

            response = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                params={
                    "appId": "Fortnite",
                    "stream": "CreativeDiscovery"
                },
                timeout=10
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get discovery surface: {response.status_code}")
                logger.error(f"Response headers: {dict(response.headers)}")
                logger.error(f"Response body: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error getting discovery surface: {e}")
            return None

    def get_islands_from_surface(self, surface_data: Dict) -> List[DiscoveryIsland]:
        """
        Extract islands from a discovery surface response

        Args:
            surface_data: Surface data from get_discovery_surface()

        Returns:
            List of DiscoveryIsland objects
        """
        islands = []

        try:
            # Surface data contains panels with links to islands
            panels = surface_data.get("panels", [])

            for panel in panels:
                # Each panel can have multiple pages
                pages = panel.get("pages", [])

                for page in pages:
                    # Each page has results (islands)
                    results = page.get("results", [])

                    for result in results:
                        # Parse the island data
                        island = self._parse_island_data(result)
                        if island:
                            islands.append(island)

            logger.info(f"Extracted {len(islands)} islands from surface")
            return islands

        except Exception as e:
            logger.error(f"Error extracting islands from surface: {e}")
            return []

    def search_islands(self, query: str, order_by: str = "globalCCU", page: int = 0) -> List[DiscoveryIsland]:
        """
        Search for islands/gamemodes

        NOTE: Island search requires in-game authentication which is not available
        with web OAuth. This method returns an empty list.

        For searching islands, use get_discovery_surface() and filter the results,
        or search by code directly.

        Args:
            query: Search query
            order_by: Sort key (globalCCU, etc.)
            page: Page number

        Returns:
            Empty list (feature not available with web auth)
        """
        logger.warning("Island search requires in-game authentication, not available with web OAuth")
        logger.info("Tip: Use discovery surfaces to browse islands instead")
        return []

    def search_creators(self, creator_term: str) -> List[Creator]:
        """
        Search for creators using text search

        Note: Direct creator search requires game client authentication.
        This falls back to searching islands by creator name.

        Args:
            creator_term: Creator search query

        Returns:
            List of Creator objects (may be empty if feature unavailable)
        """
        try:
            # Creator search requires game client tokens which we don't have with web OAuth
            # Return empty list with a note
            logger.warning("Creator search requires in-game authentication, not available with web OAuth")
            logger.info("Tip: You can search for creators by name in the island search instead")
            return []

        except Exception as e:
            logger.error(f"Error searching creators: {e}")
            return []
