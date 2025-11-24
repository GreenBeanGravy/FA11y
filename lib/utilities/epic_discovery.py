"""
Epic Games Discovery API Integration
Handles Fortnite Creative Discovery surfaces, search, and creator features
"""
import logging
import requests
import re
import time
from html.parser import HTMLParser
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False

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

    def __init__(self, epic_auth_instance=None):
        """
        Initialize Discovery API

        Args:
            epic_auth_instance: Instance of EpicAuth for authentication (optional for public features)
        """
        self.auth = epic_auth_instance

        # Epic Games API endpoints
        self.DISCOVERY_BASE = "https://fn-service-discovery-live-public.ogs.live.on.epicgames.com/api/v2/discovery"
        self.DISCOVERY_TOKEN_URL = "https://fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api/discovery/accessToken"
        # Note: Search endpoints require game client authentication, not available with web OAuth
        self.SEARCH_BASE = "https://fngw-svc-gc-livefn.ol.epicgames.com/api"
        # Public Fortnite Data API (no authentication required!)
        self.DATA_API_BASE = "https://api.fortnite.com/ecosystem/v1"

        # Cache for discovery token (version-specific)
        self._discovery_token_cache = {}  # {branch: token}

        # Optimization: Reusable scraper instance (avoids recreation overhead)
        self._scraper = None
        if HAS_CLOUDSCRAPER:
            try:
                self._scraper = cloudscraper.create_scraper(
                    browser={
                        'browser': 'chrome',
                        'platform': 'windows',
                        'desktop': True
                    }
                )
                pass  # Scraper created successfully
            except Exception as e:
                logger.warning(f"Failed to create cloudscraper: {e}")

        # Optimization: Response cache {url: (html, timestamp)}
        # Cache responses for 30 seconds to avoid duplicate requests
        self._response_cache: Dict[str, Tuple[str, float]] = {}
        self._cache_ttl = 30.0  # seconds

    def _get_headers(self) -> dict:
        """Get authorization headers for API requests"""
        if not self.auth.access_token:
            raise ValueError("Not authenticated. Please log in first.")

        return {
            "Authorization": f"Bearer {self.auth.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "Fortnite/++Fortnite+Release-20.00-CL-19458861 Windows/10.0.19041.1.768.64bit"
        }

    def _fetch_url_cached(self, url: str, headers: Dict[str, str], use_cache: bool = True) -> Optional[str]:
        """
        Fetch URL with caching support

        Args:
            url: URL to fetch
            headers: HTTP headers
            use_cache: Whether to use cache (default True)

        Returns:
            HTML response or None if failed
        """
        # Check cache first
        if use_cache and url in self._response_cache:
            cached_html, cached_time = self._response_cache[url]
            age = time.time() - cached_time
            if age < self._cache_ttl:
                return cached_html
            else:
                # Cache expired, remove it
                del self._response_cache[url]

        # Rate limiting - wait 0.5 seconds between requests
        time.sleep(0.5)

        # Fetch using reusable scraper if available
        try:
            if self._scraper:
                response = self._scraper.get(url, headers=headers, timeout=15, allow_redirects=True)
            elif HAS_CLOUDSCRAPER:
                # Fallback: create temporary scraper
                scraper = cloudscraper.create_scraper(
                    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
                )
                response = scraper.get(url, headers=headers, timeout=15, allow_redirects=True)
            else:
                # Final fallback: regular requests
                logger.warning("cloudscraper not available, using regular requests (may be blocked)")
                session = requests.Session()
                response = session.get(url, headers=headers, timeout=15, allow_redirects=True)

            if response.status_code != 200:
                logger.error(f"Failed to fetch {url}: {response.status_code}")
                if "cloudflare" in response.text.lower() or "cf-ray" in response.headers:
                    logger.warning("Cloudflare protection detected")
                return None

            html = response.text

            # Cache the response
            if use_cache:
                self._response_cache[url] = (html, time.time())

            return html

        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def get_discovery_token(self, branch: str = "++Fortnite+Release-38.11") -> Optional[str]:
        """
        Get discovery token for v2 API access
        """
        # Check cache first
        if branch in self._discovery_token_cache:
            return self._discovery_token_cache[branch]

        try:
            url = f"{self.DISCOVERY_TOKEN_URL}/{branch}"

            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                token = data.get("token")

                if token:
                    # Cache the token
                    self._discovery_token_cache[branch] = token
                    return token
                else:
                    logger.error("Discovery token not found in response")
                    return None
            else:
                logger.error(f"Failed to get discovery token: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error getting discovery token: {e}")
            return None

    def _parse_island_data(self, island_data: Dict) -> Optional[DiscoveryIsland]:
        """
        Parse island data from API response (supports both Discovery and Data API formats)
        """
        try:
            # Handle both Discovery API (linkCode) and Data API (code) formats
            link_code = island_data.get("linkCode") or island_data.get("code", "")
            if not link_code:
                return None

            # Extract title (display name)
            title = island_data.get("title", link_code)

            # Extract creator name
            creator_name = island_data.get("creatorName") or island_data.get("creatorCode")

            # Extract description
            description = island_data.get("description")

            # Extract image URL
            image_url = island_data.get("imageUrl")

            return DiscoveryIsland(
                link_code=link_code,
                title=title,
                creator_name=creator_name,
                description=description or (f"Category: {island_data.get('category', 'Unknown')}" if island_data.get('category') else None),
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

    def get_discovery_surface(self, surface_name: str = SURFACE_MAIN, branch: str = "++Fortnite+Release-38.11") -> Optional[Dict]:
        """
        Get discovery surface data using Discovery v2 API
        """
        try:
            # Get discovery token first
            discovery_token = self.get_discovery_token(branch)
            if not discovery_token:
                logger.error("Failed to obtain discovery token, cannot query surface")
                return None

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
            
            headers = {
                "Authorization": f"Bearer {self.auth.access_token}",
                "X-Epic-Access-Token": discovery_token,
                "Content-Type": "application/json",
                "User-Agent": "Fortnite/++Fortnite+Release-20.00-CL-19458861 Windows/10.0.19041.1.768.64bit"
            }

            response = requests.post(
                url,
                headers=headers,
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
                return None

        except Exception as e:
            logger.error(f"Error getting discovery surface: {e}")
            return None

    def get_islands_from_surface(self, surface_data: Dict) -> List[DiscoveryIsland]:
        """
        Extract islands from a discovery surface response
        """
        islands = []

        try:
            panels = surface_data.get("panels", [])
            for panel in panels:
                first_page = panel.get("firstPage", {})
                results = first_page.get("results", [])

                for result in results:
                    link_code = result.get("linkCode", "")
                    if link_code.startswith(("ref_", "reference_")):
                        continue

                    island = self._parse_island_data(result)
                    if island:
                        islands.append(island)

            return islands

        except Exception as e:
            logger.error(f"Error extracting islands from surface: {e}")
            return []

    def get_all_islands(self, limit: int = 100) -> List[DiscoveryIsland]:
        """
        Get all available islands from the public Fortnite Data API
        """
        try:
            url = f"{self.DATA_API_BASE}/islands"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "FA11y/1.0"
            }

            response = requests.get(
                url,
                headers=headers,
                params={"size": limit},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                all_islands = data.get("data", [])

                islands = []
                for island_data in all_islands:
                    island = self._parse_island_data(island_data)
                    if island:
                        islands.append(island)

                return islands
            else:
                logger.error(f"Failed to get islands (Data API): {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Error getting all islands: {e}")
            return []

    def _parse_fortnite_gg_html(self, html: str, default_creator: Optional[str] = None) -> List[DiscoveryIsland]:
        """
        Robust parser for fortnite.gg HTML content.
        Handles different attribute orders and HTML structures found in browse, search, and creator pages.
        """
        islands = []
        
        # Regex to find the main anchor tag block for an island.
        # Matches <a ... href='/island?code=CODE' ...> ... </a>
        # Handles attributes in any order.
        # Captures: 1. Full opening tag (to check class), 2. Code, 3. Inner HTML
        island_block_pattern = re.compile(
            r"(<a[^>]+href=['\"]/island\?code=([^'\"]+)['\"][^>]*>)(.*?)</a>",
            re.DOTALL | re.IGNORECASE
        )

        # Regexes for inner content
        img_pattern = re.compile(r"<img[^>]+src=['\"]([^'\"]+)['\"]", re.IGNORECASE)
        title_pattern = re.compile(r"<h3[^>]*class=['\"]island-title['\"][^>]*>([^<]+)</h3>", re.IGNORECASE)
        # Fallback title from alt tag if h3 is missing
        alt_title_pattern = re.compile(r"alt=['\"]([^'\"]+)['\"]", re.IGNORECASE)
        
        # CCU Pattern: Handles "245.6K", "1M", "36" inside the players div
        ccu_pattern = re.compile(r"<div[^>]*class=['\"]players['\"][^>]*>.*?</svg>\s*([\d.,]+[KMB]?)\s*</div>", re.DOTALL | re.IGNORECASE)

        matches = island_block_pattern.findall(html)

        for opening_tag, code, inner_html in matches:
            try:
                # 1. Determine Creator
                # If the anchor tag has class 'byepic', it's an Epic Games map
                current_creator = None
                if "byepic" in opening_tag.lower():
                    current_creator = "Epic Games"
                elif default_creator:
                    # Only set creator if explicitly provided (e.g. creator page)
                    # For search results, default_creator is None, so current_creator remains None
                    current_creator = default_creator
                
                # 2. Extract Title
                title_match = title_pattern.search(inner_html)
                if title_match:
                    title = title_match.group(1).strip()
                else:
                    # Fallback to alt tag
                    alt_match = alt_title_pattern.search(inner_html)
                    title = alt_match.group(1).strip() if alt_match else code

                # 3. Extract Image
                img_match = img_pattern.search(inner_html)
                image_url = img_match.group(1) if img_match else None
                if image_url:
                    # Fix resolution if needed
                    if image_url.endswith('_s.jpeg'):
                        pass # Keep small if that's what we got
                    else:
                        image_url = image_url.replace('_s.jpeg', '.jpeg')

                # 4. Extract CCU (Player Count)
                ccu_match = ccu_pattern.search(inner_html)
                player_count = -1
                if ccu_match:
                    raw_ccu = ccu_match.group(1).upper().replace(',', '')
                    try:
                        if 'K' in raw_ccu:
                            player_count = int(float(raw_ccu.replace('K', '')) * 1000)
                        elif 'M' in raw_ccu:
                            player_count = int(float(raw_ccu.replace('M', '')) * 1000000)
                        else:
                            player_count = int(float(raw_ccu))
                    except ValueError:
                        player_count = -1

                # Create Island Object
                island = DiscoveryIsland(
                    link_code=code,
                    title=title,
                    creator_name=current_creator,
                    description=None,
                    global_ccu=player_count,
                    image_url=image_url
                )
                islands.append(island)

            except Exception as e:
                logger.warning(f"Failed to parse an island block: {e}")
                continue

        return islands

    def scrape_fortnite_gg(self, search_query: str = "", limit: int = 50) -> List[DiscoveryIsland]:
        """
        Scrape island data from fortnite.gg
        Handles Browse, Search, and Playlist codes.
        """
        try:
            # Build URL
            base_url = "https://fortnite.gg/creative"
            params = {}
            if search_query:
                params["search"] = search_query

            # Build query string
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            url = f"{base_url}?{query_string}" if query_string else base_url


            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "Referer": "https://fortnite.gg/",
            }

            html = self._fetch_url_cached(url, headers)
            if not html:
                return []

            # Use the unified parser
            # Pass None as default_creator so search results don't get a fake creator name
            islands = self._parse_fortnite_gg_html(html, default_creator=None)
            
            # Limit results
            islands = islands[:limit]

            return islands

        except Exception as e:
            logger.error(f"Error scraping fortnite.gg: {e}")
            return []

    def scrape_creator_maps(self, creator_name: str, limit: int = 50, start_page: int = 1) -> List[DiscoveryIsland]:
        """
        Scrape maps from a specific creator's page on fortnite.gg
        """
        islands = []

        try:
            # Determine how many pages to fetch (typically 24 islands per page)
            islands_per_page = 24
            max_pages = max(1, (limit + islands_per_page - 1) // islands_per_page)
            max_workers = min(3, max_pages)

            if max_pages == 1:
                page_islands = self._fetch_and_parse_creator_page(creator_name, start_page)
                islands.extend(page_islands[:limit])
            else:
                page_nums = list(range(start_page, start_page + max_pages))
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_page = {
                        executor.submit(self._fetch_and_parse_creator_page, creator_name, page_num): page_num
                        for page_num in page_nums
                    }

                    for future in as_completed(future_to_page):
                        page_num = future_to_page[future]
                        try:
                            page_islands = future.result()
                            if page_islands:
                                islands.extend(page_islands)
                        except Exception as e:
                            logger.error(f"Error fetching page {page_num}: {e}")

                # Sort by player count (descending)
                islands.sort(key=lambda x: x.global_ccu, reverse=True)
                islands = islands[:limit]

            return islands

        except Exception as e:
            logger.error(f"Error scraping creator maps: {e}")
            return islands

    def _fetch_and_parse_creator_page(self, creator_name: str, page_num: int) -> List[DiscoveryIsland]:
        """
        Fetch and parse a single creator page
        """
        url = f"https://fortnite.gg/creator?name={creator_name}"
        if page_num > 1:
            url += f"&page={page_num}"


        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://fortnite.gg/",
        }

        html = self._fetch_url_cached(url, headers)
        if not html:
            return []

        # Use the unified parser, passing the known creator name
        return self._parse_fortnite_gg_html(html, default_creator=creator_name)

    def search_islands(self, query: str, order_by: str = "globalCCU", page: int = 0) -> List[DiscoveryIsland]:
        """
        Search for islands/gamemodes using the public Fortnite Data API
        """
        try:
            url = f"{self.DATA_API_BASE}/islands"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "FA11y/1.0"
            }

            response = requests.get(
                url,
                headers=headers,
                params={"size": 100},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                all_islands = data.get("data", [])

                query_lower = query.lower().strip()
                islands = []

                for island_data in all_islands:
                    title = island_data.get("title", "").lower()
                    creator = island_data.get("creatorCode", "").lower()
                    code = island_data.get("code", "").lower()

                    if query_lower in title or query_lower in creator or query_lower in code:
                        island = self._parse_island_data(island_data)
                        if island:
                            islands.append(island)

                return islands
            else:
                logger.error(f"Failed to search islands (Data API): {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Error searching islands: {e}")
            return []

    def get_island_by_code(self, code: str) -> Optional[DiscoveryIsland]:
        """
        Get island metadata by island code using the public Fortnite Data API
        """
        try:
            url = f"{self.DATA_API_BASE}/islands/{code}"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "FA11y/1.0"
            }

            response = requests.get(
                url,
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                island_data = response.json()
                return self._parse_island_data(island_data)
            elif response.status_code == 404:
                logger.warning(f"Island not found: {code}")
                return None
            else:
                logger.error(f"Failed to get island by code: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error getting island by code: {e}")
            return None

    def search_creators(self, creator_term: str) -> List[Creator]:
        """
        Search for creators using text search
        """
        try:
            logger.warning("Creator search requires in-game authentication, not available with web OAuth")
            return []
        except Exception as e:
            logger.error(f"Error searching creators: {e}")
            return []
