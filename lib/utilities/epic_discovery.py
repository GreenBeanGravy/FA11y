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
    is_favorite: bool
    last_visited: Optional[float]
    global_ccu: int
    lock_status: str
    is_visible: bool
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
                params={"appId": "Fortnite"},
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

    def search_islands(self, query: str, order_by: str = "globalCCU", page: int = 0) -> List[DiscoveryIsland]:
        """
        Search for islands/gamemodes

        Args:
            query: Search query
            order_by: Sort key (globalCCU, etc.)
            page: Page number

        Returns:
            List of DiscoveryIsland objects
        """
        try:
            payload = {
                "namespace": "fortnite",
                "context": [],
                "locale": "en-US-POSIX",
                "search": query,
                "orderBy": order_by,
                "ratingAuthority": "",
                "rating": "",
                "page": page
            }

            url = f"{self.SEARCH_BASE}/island-search/v1/search/{self.auth.account_id}"
            logger.debug(f"Island search request: POST {url}")
            logger.debug(f"Payload: {payload}")

            response = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])

                islands = []
                for result in results:
                    island = DiscoveryIsland(
                        link_code=result.get("linkCode", ""),
                        is_favorite=result.get("isFavorite", False),
                        last_visited=result.get("lastVisited"),
                        global_ccu=result.get("globalCCU", -1),
                        lock_status=result.get("lockStatus", "UNKNOWN"),
                        is_visible=result.get("isVisible", True),
                        score=result.get("score")
                    )
                    islands.append(island)

                logger.info(f"Found {len(islands)} islands matching '{query}'")
                return islands
            else:
                logger.error(f"Failed to search islands: {response.status_code}")
                logger.error(f"Response headers: {dict(response.headers)}")
                logger.error(f"Response body: {response.text}")
                return []

        except Exception as e:
            logger.error(f"Error searching islands: {e}")
            return []

    def search_creators(self, creator_term: str) -> List[Creator]:
        """
        Search for creators

        Args:
            creator_term: Creator search query

        Returns:
            List of Creator objects
        """
        try:
            payload = {
                "creatorTerm": creator_term
            }

            url = f"{self.SEARCH_BASE}/creator-search/v1/search/{self.auth.account_id}"
            logger.debug(f"Creator search request: POST {url}")
            logger.debug(f"Payload: {payload}")

            response = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])

                creators = []
                for result in results:
                    creator = Creator(
                        account_id=result.get("accountId", ""),
                        score=result.get("score", 0.0)
                    )
                    creators.append(creator)

                logger.info(f"Found {len(creators)} creators matching '{creator_term}'")
                return creators
            else:
                logger.error(f"Failed to search creators: {response.status_code}")
                logger.error(f"Response headers: {dict(response.headers)}")
                logger.error(f"Response body: {response.text}")
                return []

        except Exception as e:
            logger.error(f"Error searching creators: {e}")
            return []
