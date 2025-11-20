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

    def __init__(self, epic_auth_instance):
        """
        Initialize with an EpicAuth instance

        Args:
            epic_auth_instance: Instance of EpicAuth for authentication
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
                logger.debug("Created reusable cloudscraper instance")
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
                logger.debug(f"Using cached response for {url} (age: {age:.1f}s)")
                return cached_html
            else:
                # Cache expired, remove it
                del self._response_cache[url]

        # Rate limiting - wait 0.5 seconds between requests (optimized from 1s)
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
                logger.debug(f"Cached response for {url}")

            return html

        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def get_discovery_token(self, branch: str = "++Fortnite+Release-38.11") -> Optional[str]:
        """
        Get discovery token for v2 API access

        This token is required for Discovery Service v2 endpoints.
        It's version-specific and should be cached per session.

        Args:
            branch: Fortnite branch/version (e.g., "++Fortnite+Release-38.11")

        Returns:
            Base64-encoded discovery token or None if failed
        """
        # Check cache first
        if branch in self._discovery_token_cache:
            logger.debug(f"Using cached discovery token for {branch}")
            return self._discovery_token_cache[branch]

        try:
            url = f"{self.DISCOVERY_TOKEN_URL}/{branch}"
            logger.debug(f"Getting discovery token: GET {url}")

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
                    logger.info(f"Successfully obtained discovery token for {branch}")
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

        Args:
            island_data: Raw island data from API

        Returns:
            DiscoveryIsland object or None if parsing fails
        """
        try:
            # Handle both Discovery API (linkCode) and Data API (code) formats
            link_code = island_data.get("linkCode") or island_data.get("code", "")
            if not link_code:
                return None

            # Extract title (display name)
            # Data API uses "title", Discovery API might use "title" or linkCode as fallback
            title = island_data.get("title", link_code)

            # Extract creator name
            # Data API uses "creatorCode", Discovery API uses "creatorName"
            creator_name = island_data.get("creatorName") or island_data.get("creatorCode")

            # Extract description
            description = island_data.get("description")

            # Extract image URL
            image_url = island_data.get("imageUrl")

            # Extract tags (Data API)
            tags = island_data.get("tags", [])

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

        Args:
            surface_name: Name of the surface to query
            branch: Fortnite branch/version for token retrieval

        Returns:
            Surface data with panels and islands
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
            logger.debug(f"Discovery surface request: POST {url}?appId=Fortnite")
            logger.debug(f"Payload: {payload}")

            # Use BOTH Authorization and X-Epic-Access-Token headers
            # Authorization for account auth, X-Epic-Access-Token for discovery access
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
            logger.debug(f"Found {len(panels)} panels in surface data")

            for panel in panels:
                # Each panel has a firstPage with results
                first_page = panel.get("firstPage", {})
                results = first_page.get("results", [])
                logger.debug(f"Panel has {len(results)} results")

                for result in results:
                    # Skip panel references (they start with "ref_" or "reference_")
                    link_code = result.get("linkCode", "")
                    if link_code.startswith(("ref_", "reference_")):
                        logger.debug(f"Skipping panel reference: {link_code}")
                        continue

                    # Parse the island data
                    island = self._parse_island_data(result)
                    if island:
                        islands.append(island)
                        logger.debug(f"Parsed island: {island.title} ({island.link_code})")

            logger.info(f"Extracted {len(islands)} islands from surface")
            return islands

        except Exception as e:
            logger.error(f"Error extracting islands from surface: {e}")
            return []

    def get_all_islands(self, limit: int = 100) -> List[DiscoveryIsland]:
        """
        Get all available islands from the public Fortnite Data API

        Args:
            limit: Maximum number of islands to return (default 100)

        Returns:
            List of DiscoveryIsland objects
        """
        try:
            # Use the public Data API (no authentication required!)
            url = f"{self.DATA_API_BASE}/islands"

            logger.debug(f"Get all islands request (Data API): GET {url}")

            # Data API doesn't require authentication
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "FA11y/1.0"
            }

            # Get islands (up to limit)
            response = requests.get(
                url,
                headers=headers,
                params={"size": limit},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                all_islands = data.get("data", [])

                # Parse all islands
                islands = []
                for island_data in all_islands:
                    island = self._parse_island_data(island_data)
                    if island:
                        islands.append(island)

                logger.info(f"Retrieved {len(islands)} islands from Data API")
                return islands
            else:
                logger.error(f"Failed to get islands (Data API): {response.status_code}")
                logger.error(f"Response body: {response.text}")
                return []

        except Exception as e:
            logger.error(f"Error getting all islands: {e}")
            return []

    def scrape_fortnite_gg(self, search_query: str = "", limit: int = 50) -> List[DiscoveryIsland]:
        """
        Scrape island data from fortnite.gg

        Args:
            search_query: Optional search query (e.g., "among us", "zone wars")
            limit: Maximum number of islands to return (default 50)

        Returns:
            List of DiscoveryIsland objects scraped from fortnite.gg
        """
        islands = []

        try:
            # Build URL
            base_url = "https://fortnite.gg/creative"
            params = {}
            if search_query:
                params["search"] = search_query

            # Build query string
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            url = f"{base_url}?{query_string}" if query_string else base_url

            logger.debug(f"Scraping fortnite.gg: {url}")

            # Add browser-like headers to avoid bot detection
            # Don't manually set Accept-Encoding - let requests/cloudscraper handle compression
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://fortnite.gg/",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Cache-Control": "max-age=0"
            }

            # Use optimized cached fetch
            html = self._fetch_url_cached(url, headers)
            if not html:
                return []

            # Debug: log first 500 chars to see what we got
            logger.debug(f"Response preview: {html[:500]}")

            # Parse HTML using regex (simple and robust for this structure)
            # Pattern: <a class='island' href='/island?code=XXXX-XXXX-XXXX'>
            # Note: Browse pages have SVG element before player count
            island_pattern = re.compile(
                r"<a class='island' href='/island\?code=([\d-]+)'>.*?"
                r"<img src='([^']+)'[^>]*alt='([^']+)'.*?"
                r"<div class='players'[^>]*>.*?</svg>\s*(\d+)\s*</div>.*?"
                r"<h3 class='island-title'>([^<]+)</h3>",
                re.DOTALL
            )

            matches = island_pattern.findall(html)

            for match in matches[:limit]:
                code, image_url, alt_text, players, title = match

                # Clean up title (remove extra whitespace)
                title = title.strip()

                # Parse player count
                try:
                    player_count = int(players.strip())
                except:
                    player_count = -1

                # Create DiscoveryIsland object
                island = DiscoveryIsland(
                    link_code=code,
                    title=title,
                    creator_name=None,  # Not easily available in the list view
                    description=None,
                    global_ccu=player_count,
                    image_url=image_url if image_url and not image_url.endswith('_s.jpeg') else image_url.replace('_s.jpeg', '.jpeg') if image_url else None
                )

                islands.append(island)
                logger.debug(f"Scraped island: {title} ({code}) - {player_count} players")

            logger.info(f"Scraped {len(islands)} islands from fortnite.gg")
            return islands

        except Exception as e:
            logger.error(f"Error scraping fortnite.gg: {e}")
            return []

    def _fetch_and_parse_creator_page(self, creator_name: str, page_num: int) -> List[DiscoveryIsland]:
        """
        Fetch and parse a single creator page

        Args:
            creator_name: Creator name
            page_num: Page number to fetch

        Returns:
            List of DiscoveryIsland objects from this page
        """
        islands = []

        # Build URL for creator page
        url = f"https://fortnite.gg/creator?name={creator_name}"
        if page_num > 1:
            url += f"&page={page_num}"

        logger.debug(f"Scraping creator page: {url}")

        # Add browser-like headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://fortnite.gg/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Cache-Control": "max-age=0"
        }

        # Use optimized cached fetch
        html = self._fetch_url_cached(url, headers)
        if not html:
            return []

        # Creator pages use a different HTML structure than browse pages
        # Pattern: <a href="/island?code=CODE" class="island byepic">
        # Note: Uses DOUBLE quotes, has "byepic" class, nested divs
        # Player count is AFTER the SVG element and may have "K" suffix (e.g., "218.4K")
        island_pattern = re.compile(
            r'<a href=["\']?/island\?code=([^"\'>&\s]+)["\']?[^>]*class=["\'][^"\']*island[^"\']*["\'][^>]*>.*?'
            r'<img src=["\']([^"\']+)["\'][^>]*alt=["\']([^"\']+)["\'].*?'
            r'<div class=["\']players["\'][^>]*>.*?</svg>\s*([\d.]+K?)\s*</div>',
            re.DOTALL | re.IGNORECASE
        )

        matches = island_pattern.findall(html)
        logger.debug(f"Pattern matched {len(matches)} islands on page {page_num}")

        for match in matches:
            # Match groups: code, image_url, title (from alt), players
            code, image_url, title, players = match

            # Clean up title and code
            title = title.strip()
            code = code.strip()

            # Parse player count (handle "K" suffix: "218.4K" = 218400)
            try:
                players_str = players.strip()
                if 'K' in players_str.upper():
                    # Remove K and convert (218.4K -> 218.4 * 1000 = 218400)
                    player_count = int(float(players_str.upper().replace('K', '')) * 1000)
                else:
                    player_count = int(float(players_str))
            except:
                player_count = -1

            # Create DiscoveryIsland object
            island = DiscoveryIsland(
                link_code=code,
                title=title,
                creator_name=creator_name,
                description=None,
                global_ccu=player_count,
                image_url=image_url if image_url and not image_url.endswith('_s.jpeg') else image_url.replace('_s.jpeg', '.jpeg') if image_url else None
            )

            islands.append(island)
            logger.debug(f"Scraped creator island: {title} ({code}) - {player_count} players")

        return islands

    def scrape_creator_maps(self, creator_name: str, limit: int = 50, start_page: int = 1) -> List[DiscoveryIsland]:
        """
        Scrape maps from a specific creator's page on fortnite.gg

        Optimized with parallel page fetching for better performance.

        Args:
            creator_name: Creator name (e.g., "epic")
            limit: Maximum islands to return (default 50)
            start_page: Starting page number (default 1)

        Returns:
            List of DiscoveryIsland objects from the creator
        """
        islands = []

        try:
            # Determine how many pages to fetch (typically 24 islands per page)
            islands_per_page = 24
            max_pages = max(1, (limit + islands_per_page - 1) // islands_per_page)

            # Optimization: Fetch multiple pages in parallel (limit to 3 concurrent requests)
            # This significantly speeds up multi-page fetching while being respectful to the server
            max_workers = min(3, max_pages)

            if max_pages == 1:
                # Single page - no need for parallel fetching
                page_islands = self._fetch_and_parse_creator_page(creator_name, start_page)
                islands.extend(page_islands[:limit])
            else:
                # Multi-page - use parallel fetching
                page_nums = list(range(start_page, start_page + max_pages))

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # Submit all page fetch tasks
                    future_to_page = {
                        executor.submit(self._fetch_and_parse_creator_page, creator_name, page_num): page_num
                        for page_num in page_nums
                    }

                    # Collect results as they complete
                    for future in as_completed(future_to_page):
                        page_num = future_to_page[future]
                        try:
                            page_islands = future.result()
                            if page_islands:
                                islands.extend(page_islands)
                                logger.info(f"Fetched {len(page_islands)} islands from page {page_num}")
                            else:
                                logger.debug(f"No islands found on page {page_num}")
                        except Exception as e:
                            logger.error(f"Error fetching page {page_num}: {e}")

                # Sort by player count (descending) to maintain consistent ordering
                islands.sort(key=lambda x: x.global_ccu, reverse=True)

                # Trim to limit
                islands = islands[:limit]

            logger.info(f"Total scraped {len(islands)} islands for creator '{creator_name}'")
            return islands

        except Exception as e:
            logger.error(f"Error scraping creator maps: {e}")
            return islands  # Return what we got so far

    def search_islands(self, query: str, order_by: str = "globalCCU", page: int = 0) -> List[DiscoveryIsland]:
        """
        Search for islands/gamemodes using the public Fortnite Data API

        Args:
            query: Search query (filters by title or creator)
            order_by: Sort key (not used by Data API, kept for compatibility)
            page: Page number (not used, returns first 100 results)

        Returns:
            List of DiscoveryIsland objects matching the query
        """
        try:
            # Use the public Data API (no authentication required!)
            url = f"{self.DATA_API_BASE}/islands"

            logger.debug(f"Island search request (Data API): GET {url}")

            # Data API doesn't require authentication
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "FA11y/1.0"
            }

            # Get first batch of islands (up to 100)
            response = requests.get(
                url,
                headers=headers,
                params={"size": 100},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                all_islands = data.get("data", [])

                # Filter by query (search title and creator)
                query_lower = query.lower().strip()
                islands = []

                for island_data in all_islands:
                    title = island_data.get("title", "").lower()
                    creator = island_data.get("creatorCode", "").lower()
                    code = island_data.get("code", "").lower()

                    # Match if query is in title, creator, or code
                    if query_lower in title or query_lower in creator or query_lower in code:
                        island = self._parse_island_data(island_data)
                        if island:
                            islands.append(island)

                logger.info(f"Found {len(islands)} islands matching '{query}'")
                return islands
            else:
                logger.error(f"Failed to search islands (Data API): {response.status_code}")
                logger.error(f"Response body: {response.text}")
                return []

        except Exception as e:
            logger.error(f"Error searching islands: {e}")
            return []

    def get_island_by_code(self, code: str) -> Optional[DiscoveryIsland]:
        """
        Get island metadata by island code using the public Fortnite Data API

        Args:
            code: Island code (e.g., "1234-1234-1234")

        Returns:
            DiscoveryIsland object or None if not found
        """
        try:
            url = f"{self.DATA_API_BASE}/islands/{code}"

            logger.debug(f"Island lookup request (Data API): GET {url}")

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
                island = self._parse_island_data(island_data)

                if island:
                    logger.info(f"Found island: {island.title} ({island.link_code})")
                    return island
                else:
                    logger.warning(f"Failed to parse island data for code: {code}")
                    return None
            elif response.status_code == 404:
                logger.warning(f"Island not found: {code}")
                return None
            else:
                logger.error(f"Failed to get island by code: {response.status_code}")
                logger.error(f"Response body: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error getting island by code: {e}")
            return None

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
