"""
POI Data Manager Module

This module handles POI data loading, management, and favorites functionality.
Extracted from the POI selector GUI to maintain functionality after GUI removal.
"""

import os
import logging
import json
import re
import requests
import numpy as np
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from lib.utilities.utilities import read_config

logger = logging.getLogger(__name__)

_favorites_lock = threading.RLock()


class CoordinateSystem:
    """Handles coordinate transformation between world and screen coordinates"""

    def __init__(self, poi_file="pois.txt"):
        """
        Initialize the coordinate system.

        Args:
            poi_file: Path to the POI file containing reference points
        """
        self.poi_file = poi_file
        self.REFERENCE_PAIRS = self._load_reference_pairs()
        self.transform_matrix = self._calculate_transformation_matrix()

    def _load_reference_pairs(self) -> dict:
        """
        Load reference coordinate pairs from POI file.

        Returns:
            Dictionary mapping world coordinates to screen coordinates
        """
        reference_pairs = {}
        try:
            with open(self.poi_file, 'r') as f:
                for line in f:
                    if not line.strip() or line.strip().startswith('#'):
                        continue

                    parts = line.strip().split('|')
                    if len(parts) == 3:
                        name = parts[0].strip()
                        screen_x, screen_y = map(int, parts[1].strip().split(','))
                        world_x, world_y = map(float, parts[2].strip().split(','))
                        reference_pairs[(world_x, world_y)] = (screen_x, screen_y)
        except FileNotFoundError:
            logger.warning(f"POI file {self.poi_file} not found")
        except Exception as e:
            logger.error(f"Error loading POI data: {e}")

        return reference_pairs

    def _calculate_transformation_matrix(self) -> np.ndarray:
        """
        Calculate the transformation matrix from world to screen coordinates.

        Returns:
            Transformation matrix as numpy array
        """
        if not self.REFERENCE_PAIRS:
            return np.array([[1, 0, 0], [0, 1, 0]])

        world_coords = np.array([(x, y) for x, y in self.REFERENCE_PAIRS.keys()])
        screen_coords = np.array([coord for coord in self.REFERENCE_PAIRS.values()])
        world_coords_homogeneous = np.column_stack([world_coords, np.ones(len(world_coords))])
        transform_matrix, _, _, _ = np.linalg.lstsq(world_coords_homogeneous, screen_coords, rcond=None)
        return transform_matrix

    def world_to_screen(self, world_x: float, world_y: float) -> Tuple[int, int]:
        """
        Convert world coordinates to screen coordinates.

        Args:
            world_x: World X coordinate
            world_y: World Y coordinate

        Returns:
            Tuple of (screen_x, screen_y)
        """
        world_coord = np.array([world_x, world_y, 1])
        screen_coord = np.dot(world_coord, self.transform_matrix)
        return (int(round(screen_coord[0])), int(round(screen_coord[1])))


class MapData:
    """Container for map data"""

    def __init__(self, name: str, pois: List[Tuple[str, str, str]] = None):
        """
        Initialize map data.

        Args:
            name: Display name of the map
            pois: List of POI tuples (name, x, y)
        """
        self.name = name
        self.pois = pois if pois is not None else []


class POIData:
    """
    POI data manager with background loading.

    This class manages POI data from multiple sources:
    - Fortnite API for main map POIs
    - Local pois.txt file as fallback
    - Custom map POI files
    - Game objects

    Implements singleton pattern to prevent duplicate loading.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(POIData, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize POI data manager with background loading."""
        if not POIData._initialized:
            self.main_pois = []
            self.landmarks = []
            self.maps = {}
            self.current_map = 'main'
            self.coordinate_system = None
            self._api_loaded = False
            self._loading_lock = threading.Lock()
            self._loading_thread = None

            # Immediately discover maps (fast)
            self._discover_available_maps()

            # Start background loading for API data (slow)
            self._start_background_loading()

            POIData._initialized = True

    def _start_background_loading(self):
        """Start loading API data in background thread."""
        if self._loading_thread is None or not self._loading_thread.is_alive():
            self._loading_thread = threading.Thread(
                target=self._background_load_api_data,
                daemon=True
            )
            self._loading_thread.start()

    def _background_load_api_data(self):
        """Load API data in background."""
        try:
            with self._loading_lock:
                if not self._api_loaded:
                    if self.coordinate_system is None:
                        self.coordinate_system = CoordinateSystem()

                    if self.coordinate_system.REFERENCE_PAIRS:
                        self._fetch_and_process_pois()
                    else:
                        self._load_local_pois()

                    self._api_loaded = True
        except Exception as e:
            logger.error(f"Error in background loading: {e}")
            self._load_local_pois()
            self._api_loaded = True

    def _discover_available_maps(self):
        """Discover available maps without loading their data."""
        self.maps["main"] = MapData("Main Map", [])

        maps_dir = "maps"
        if os.path.exists(maps_dir):
            for filename in os.listdir(maps_dir):
                if filename.startswith("map_") and filename.endswith("_pois.txt"):
                    map_name = filename[4:-9]
                    if map_name != "main":
                        display_name = map_name.replace('_', ' ')
                        self.maps[map_name] = MapData(
                            name=display_name.title(),
                            pois=[]
                        )

    def _load_map_pois(self, filename: str) -> List[Tuple[str, str, str]]:
        """
        Load POIs from a map file.

        Args:
            filename: Path to the map POI file

        Returns:
            List of POI tuples (name, x, y)
        """
        pois = []
        try:
            with open(filename, 'r') as f:
                for line in f.readlines():
                    parts = line.strip().split(',')
                    if len(parts) >= 3:
                        name = parts[0].strip()
                        x = parts[1].strip()
                        y = parts[2].strip()
                        pois.append((name, x, y))
        except Exception as e:
            logger.error(f"Error loading POIs from {filename}: {e}")
        return pois

    def _ensure_api_data_loaded(self, timeout=0.1):
        """
        Ensure API data is loaded (non-blocking).

        Args:
            timeout: Maximum time to wait (not used, returns immediately)

        Returns:
            True if data is loaded, False if still loading
        """
        if self._api_loaded:
            return True

        # If loading thread is still running, don't wait
        if self._loading_thread and self._loading_thread.is_alive():
            return False

        # If thread finished but flag not set, trigger load
        if not self._api_loaded:
            self._start_background_loading()

        return self._api_loaded

    def _ensure_map_data_loaded(self, map_name: str):
        """
        Ensure specific map data is loaded.

        Args:
            map_name: Name of the map to load
        """
        if map_name == "main":
            self._ensure_api_data_loaded()
        elif map_name in self.maps and not self.maps[map_name].pois:
            maps_dir = "maps"
            filename = os.path.join(maps_dir, f"map_{map_name}_pois.txt")
            if os.path.exists(filename):
                self.maps[map_name].pois = self._load_map_pois(filename)

    def _fetch_and_process_pois(self) -> None:
        """Fetch POIs from Fortnite API and process them."""
        try:
            response = requests.get(
                'https://fortnite-api.com/v1/map',
                params={'language': 'en'},
                timeout=10
            )
            response.raise_for_status()

            self.api_data = response.json().get('data', {}).get('pois', [])

            self.main_pois = []
            self.landmarks = []

            for poi in self.api_data:
                name = poi['name']
                world_x = float(poi['location']['x'])
                world_y = float(poi['location']['y'])
                screen_x, screen_y = self.coordinate_system.world_to_screen(world_x, world_y)

                if re.match(r'Athena\.Location\.POI\.Generic\.(?:EE\.)?\d+', poi['id']):
                    self.main_pois.append((name, str(screen_x), str(screen_y)))
                elif re.match(r'Athena\.Location\.UnNamedPOI\.(Landmark|GasStation)\.\d+', poi['id']):
                    self.landmarks.append((name, str(screen_x), str(screen_y)))

            self.maps["main"].pois = self.main_pois

        except requests.RequestException as e:
            logger.error(f"Error fetching POIs from API: {e}")
            self._load_local_pois()

    def _load_local_pois(self):
        """Load POIs from local pois.txt file."""
        try:
            with open('pois.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split('|')
                    if len(parts) == 3:
                        name = parts[0]
                        coords = parts[1].split(',')
                        if len(coords) == 2:
                            x, y = coords[0], coords[1]
                            self.main_pois.append((name, x, y))

            self.maps["main"].pois = self.main_pois

        except FileNotFoundError:
            logger.warning("Local pois.txt file not found")
        except Exception as e:
            logger.error(f"Error loading main POIs from file: {e}")

    def get_current_map(self) -> str:
        """
        Get the current map from config.

        Returns:
            Current map name
        """
        try:
            config = read_config()
            return config.get('POI', 'current_map', fallback='main')
        except Exception as e:
            logger.error(f"Error getting current map: {e}")
            return 'main'

    def get_map_names(self) -> List[str]:
        """
        Get list of available map names.

        Returns:
            List of map names
        """
        return list(self.maps.keys())

    def get_map_data(self, map_name: str) -> Optional[MapData]:
        """
        Get data for a specific map.

        Args:
            map_name: Name of the map

        Returns:
            MapData object or None if map not found
        """
        if map_name in self.maps:
            self._ensure_map_data_loaded(map_name)
            return self.maps[map_name]
        return None

    def wait_for_loading(self, timeout: float = 5.0) -> bool:
        """
        Wait for API data to finish loading.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if loading completed, False if timed out
        """
        if self._loading_thread:
            self._loading_thread.join(timeout=timeout)
        return self._api_loaded


@dataclass
class FavoritePOI:
    """Favorite POI data container"""
    name: str
    x: str
    y: str
    source_tab: str


class FavoritesManager:
    """
    Manages favorite POIs with thread-safe operations.

    Favorites are stored in JSON format in FAVORITE_POIS.txt
    """

    def __init__(self, filename: str = "FAVORITE_POIS.txt"):
        """
        Initialize favorites manager.

        Args:
            filename: Path to favorites file
        """
        self.filename = filename
        self.favorites: List[FavoritePOI] = []
        self._load_lock = threading.RLock()
        self.load_favorites()

    def _safe_write_favorites(self, data: List[dict], max_retries: int = 3) -> bool:
        """
        Safely write favorites to file with backup and retry logic.

        Args:
            data: List of favorite POI dictionaries
            max_retries: Maximum number of write attempts

        Returns:
            True if write succeeded, False otherwise
        """
        for attempt in range(max_retries):
            try:
                backup_file = f"{self.filename}.backup"
                if os.path.exists(self.filename):
                    try:
                        with open(self.filename, 'r') as f:
                            backup_content = f.read()
                        with open(backup_file, 'w') as f:
                            f.write(backup_content)
                    except Exception as e:
                        logger.warning(f"Could not create backup: {e}")

                with open(self.filename, 'w') as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())

                if os.path.exists(backup_file):
                    try:
                        os.remove(backup_file)
                    except:
                        pass

                return True

            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed to write favorites: {e}")
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))
                    backup_file = f"{self.filename}.backup"
                    if os.path.exists(backup_file):
                        try:
                            with open(backup_file, 'r') as f:
                                backup_content = f.read()
                            with open(self.filename, 'w') as f:
                                f.write(backup_content)
                        except:
                            pass
                else:
                    return False

        return False

    def load_favorites(self) -> None:
        """Load favorites from file."""
        with _favorites_lock:
            if os.path.exists(self.filename):
                try:
                    with open(self.filename, 'r') as f:
                        data = json.load(f)
                        self.favorites = [FavoritePOI(**poi) for poi in data]
                except json.JSONDecodeError:
                    logger.error("Error loading favorites file. Starting with empty favorites.")
                    self.favorites = []
                except Exception as e:
                    logger.error(f"Error loading favorites: {e}")
                    self.favorites = []
            else:
                self.favorites = []

    def save_favorites(self) -> bool:
        """
        Save favorites to file.

        Returns:
            True if save succeeded, False otherwise
        """
        with _favorites_lock:
            try:
                data = [vars(poi) for poi in self.favorites]
                return self._safe_write_favorites(data)
            except Exception as e:
                logger.error(f"Error saving favorites: {e}")
                return False

    def toggle_favorite(self, poi: Tuple[str, str, str], source_tab: str) -> bool:
        """
        Toggle a POI as favorite (add if not present, remove if present).

        Args:
            poi: POI tuple (name, x, y)
            source_tab: Source tab/category of the POI

        Returns:
            True if POI was added to favorites, False if removed
        """
        with _favorites_lock:
            name, x, y = poi
            existing = next((f for f in self.favorites if f.name == name), None)

            if existing:
                self.favorites.remove(existing)
                success = self.save_favorites()
                if not success:
                    self.favorites.append(existing)
                    logger.error(f"Failed to save favorites after removing {name}")
                    return False
                return False
            else:
                new_fav = FavoritePOI(name=name, x=x, y=y, source_tab=source_tab)
                self.favorites.append(new_fav)
                success = self.save_favorites()
                if not success:
                    self.favorites.remove(new_fav)
                    logger.error(f"Failed to save favorites after adding {name}")
                    return False
                return True

    def is_favorite(self, poi_name: str) -> bool:
        """
        Check if a POI is in favorites.

        Args:
            poi_name: Name of the POI

        Returns:
            True if POI is a favorite, False otherwise
        """
        with _favorites_lock:
            return any(f.name == poi_name for f in self.favorites)

    def get_favorites_as_tuples(self) -> List[Tuple[str, str, str]]:
        """
        Get all favorites as tuples.

        Returns:
            List of POI tuples (name, x, y)
        """
        with _favorites_lock:
            return [(f.name, f.x, f.y) for f in self.favorites]

    def get_source_tab(self, poi_name: str) -> Optional[str]:
        """
        Get the source tab of a favorite POI.

        Args:
            poi_name: Name of the POI

        Returns:
            Source tab name or None if not found
        """
        with _favorites_lock:
            fav = next((f for f in self.favorites if f.name == poi_name), None)
            return fav.source_tab if fav else None

    def remove_all_favorites(self) -> bool:
        """
        Remove all favorites.

        Returns:
            True if removal succeeded, False otherwise
        """
        with _favorites_lock:
            old_favorites = self.favorites.copy()
            self.favorites = []
            success = self.save_favorites()
            if not success:
                self.favorites = old_favorites
                logger.error("Failed to save favorites after removing all")
                return False
            return True


# Global instances for easy access
_poi_data_instance = None
_favorites_manager_instance = None


def get_poi_data() -> POIData:
    """
    Get the global POI data instance (singleton).

    Returns:
        POIData instance
    """
    global _poi_data_instance
    if _poi_data_instance is None:
        _poi_data_instance = POIData()
    return _poi_data_instance


def get_favorites_manager() -> FavoritesManager:
    """
    Get the global favorites manager instance (singleton).

    Returns:
        FavoritesManager instance
    """
    global _favorites_manager_instance
    if _favorites_manager_instance is None:
        _favorites_manager_instance = FavoritesManager()
    return _favorites_manager_instance
