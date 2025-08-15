"""
POI selector GUI for FA11y
Provides interface for selecting points of interest for navigation
"""
import os
import logging
import tkinter as tk
from tkinter import ttk, messagebox
import json
import re
import requests
import numpy as np
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Union, Set, Any, Callable

from lib.guis.base_ui import AccessibleUI
from lib.utils.utilities import force_focus_window, read_config, Config, clear_config_cache, save_config
from lib.vision.player_position import ROI_START_ORIG, ROI_END_ORIG, get_quadrant, get_position_in_quadrant
from lib.handlers.custom_poi_handler import load_custom_pois

# Initialize logger
logger = logging.getLogger(__name__)

# Constants
CONFIG_FILE = 'config.txt'
POI_TYPE = Union[Tuple[str, str, str], str]

# Global lock for favorites operations
_favorites_lock = threading.RLock()

class CoordinateSystem:
    """Handles coordinate transformation between world and screen coordinates"""
    def __init__(self, poi_file="pois.txt"):
        self.poi_file = poi_file
        self.REFERENCE_PAIRS = self._load_reference_pairs()
        self.transform_matrix = self._calculate_transformation_matrix()

    def _load_reference_pairs(self) -> dict:
        """
        Load POI reference pairs from the pois.txt file.
        Expected format (one POI per line):
        name|screen_x,screen_y|world_x,world_y
        """
        reference_pairs = {}
        try:
            with open(self.poi_file, 'r') as f:
                for line in f:
                    # Skip empty lines and comments
                    if not line.strip() or line.strip().startswith('#'):
                        continue
                    
                    # Parse the POI data
                    parts = line.strip().split('|')
                    if len(parts) == 3:
                        name = parts[0].strip()
                        screen_x, screen_y = map(int, parts[1].strip().split(','))
                        world_x, world_y = map(float, parts[2].strip().split(','))
                        reference_pairs[(world_x, world_y)] = (screen_x, screen_y)
        except FileNotFoundError:
            print(f"Warning: {self.poi_file} not found. Using empty reference pairs.")
        except Exception as e:
            print(f"Error loading POI data: {e}")
        
        return reference_pairs

    def _calculate_transformation_matrix(self) -> np.ndarray:
        if not self.REFERENCE_PAIRS:
            raise ValueError("No reference pairs available to calculate transformation matrix")
            
        world_coords = np.array([(x, y) for x, y in self.REFERENCE_PAIRS.keys()])
        screen_coords = np.array([coord for coord in self.REFERENCE_PAIRS.values()])
        world_coords_homogeneous = np.column_stack([world_coords, np.ones(len(world_coords))])
        transform_matrix, _, _, _ = np.linalg.lstsq(world_coords_homogeneous, screen_coords, rcond=None)
        return transform_matrix

    def world_to_screen(self, world_x: float, world_y: float) -> Tuple[int, int]:
        world_coord = np.array([world_x, world_y, 1])
        screen_coord = np.dot(world_coord, self.transform_matrix)
        return (int(round(screen_coord[0])), int(round(screen_coord[1])))

class MapData:
    """Map data container"""
    def __init__(self, name, pois):
        self.name = name
        self.pois = pois

class POIData:
    """
    POI data manager that combines local files and API data
    """
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(POIData, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize with data from FA11y's expected locations"""
        if not POIData._initialized:
            self.main_pois = []
            self.landmarks = []
            self.maps = {}
            self.current_map = 'main'
            self.coordinate_system = CoordinateSystem()
            
            self._load_all_maps()
            self._fetch_and_process_pois()  # Load from API
            POIData._initialized = True
    
    def _load_all_maps(self):
        """Load all map configurations"""
        # Initialize main map
        self.maps["main"] = MapData("Main Map", [])
        
        # Find all map POI files in maps directory
        maps_dir = "maps"
        if os.path.exists(maps_dir):
            for filename in os.listdir(maps_dir):
                if filename.startswith("map_") and filename.endswith("_pois.txt"):
                    map_name = filename[4:-9]  # Remove 'map_' and '_pois.txt'
                    if map_name != "main":
                        pois = self._load_map_pois(os.path.join(maps_dir, filename))
                        display_name = map_name.replace('_', ' ')
                        self.maps[map_name] = MapData(
                            name=display_name.title(),
                            pois=pois
                        )
    
    def _load_map_pois(self, filename: str) -> List[Tuple[str, str, str]]:
        """Load POIs from a map-specific file"""
        pois = []
        try:
            with open(filename, 'r') as f:
                for line in f.readlines():
                    name, x, y = line.strip().split(',')
                    pois.append((name.strip(), x.strip(), y.strip()))
        except Exception as e:
            print(f"Error loading POIs from {filename}: {e}")
        return pois
    
    def _fetch_and_process_pois(self) -> None:
        """Fetch POIs from the Fortnite API and process them"""
        try:
            print("Fetching POI data from API...")
            response = requests.get('https://fortnite-api.com/v1/map', params={'language': 'en'})
            response.raise_for_status()
            
            self.api_data = response.json().get('data', {}).get('pois', [])

            # Clear existing POIs to avoid duplicates
            self.main_pois = []
            self.landmarks = []

            for poi in self.api_data:
                name = poi['name']
                world_x = float(poi['location']['x'])
                world_y = float(poi['location']['y'])
                screen_x, screen_y = self.coordinate_system.world_to_screen(world_x, world_y)
                
                # Filter main POIs (including both patterns)
                if re.match(r'Athena\.Location\.POI\.Generic\.(?:EE\.)?\d+', poi['id']):
                    self.main_pois.append((name, str(screen_x), str(screen_y)))
                # Filter landmarks (including gas stations)
                elif re.match(r'Athena\.Location\.UnNamedPOI\.(Landmark|GasStation)\.\d+', poi['id']):
                    self.landmarks.append((name, str(screen_x), str(screen_y)))

            # Also store main POIs in the maps dictionary
            self.maps["main"].pois = self.main_pois

            print(f"Successfully processed {len(self.main_pois)} main POIs and {len(self.landmarks)} landmarks")

        except requests.RequestException as e:
            print(f"Error fetching POIs from API: {e}")
            # Fallback to local files if API request fails
            self._load_local_pois()
    
    def _load_local_pois(self):
        """Fallback method to load POIs from local files if API fails"""
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
        except FileNotFoundError:
            print("pois.txt not found for fallback")
        except Exception as e:
            print(f"Error loading main POIs from file: {e}")
    
    def get_current_map(self):
        """Get current map from config"""
        try:
            config = read_config()
            return config.get('POI', 'current_map', fallback='main')
        except Exception as e:
            print(f"Error getting current map: {e}")
            return 'main'

@dataclass
class FavoritePOI:
    """Favorite POI data container"""
    name: str
    x: str
    y: str
    source_tab: str

class FavoritesManager:
    """Manages favorite POIs with thread-safe operations"""
    
    def __init__(self, filename: str = "FAVORITE_POIS.txt"):
        """Initialize the favorites manager
        
        Args:
            filename: Path to favorites file
        """
        self.filename = filename
        self.favorites: List[FavoritePOI] = []
        self._load_lock = threading.RLock()
        self.load_favorites()

    def _safe_write_favorites(self, data: List[dict], max_retries: int = 3) -> bool:
        """Safely write favorites to file with retry logic"""
        for attempt in range(max_retries):
            try:
                # Create backup
                backup_file = f"{self.filename}.backup"
                if os.path.exists(self.filename):
                    try:
                        with open(self.filename, 'r') as f:
                            backup_content = f.read()
                        with open(backup_file, 'w') as f:
                            f.write(backup_content)
                    except Exception as e:
                        logger.warning(f"Could not create backup: {e}")
                
                # Write new data
                with open(self.filename, 'w') as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Remove backup on success
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
                    # Try to restore from backup
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
        """Load favorites from file with thread safety"""
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
        """Save favorites to file with thread safety"""
        with _favorites_lock:
            try:
                data = [vars(poi) for poi in self.favorites]
                return self._safe_write_favorites(data)
            except Exception as e:
                logger.error(f"Error saving favorites: {e}")
                return False

    def toggle_favorite(self, poi: Tuple[str, str, str], source_tab: str) -> bool:
        """Toggle favorite status for a POI with thread safety
        
        Args:
            poi: POI data tuple (name, x, y)
            source_tab: Source tab name
            
        Returns:
            bool: True if added, False if removed
        """
        with _favorites_lock:
            name, x, y = poi
            existing = next((f for f in self.favorites if f.name == name), None)
            
            if existing:
                self.favorites.remove(existing)
                success = self.save_favorites()
                if not success:
                    # Rollback on failure
                    self.favorites.append(existing)
                    logger.error(f"Failed to save favorites after removing {name}")
                    return False
                return False
            else:
                new_fav = FavoritePOI(name=name, x=x, y=y, source_tab=source_tab)
                self.favorites.append(new_fav)
                success = self.save_favorites()
                if not success:
                    # Rollback on failure
                    self.favorites.remove(new_fav)
                    logger.error(f"Failed to save favorites after adding {name}")
                    return False
                return True

    def is_favorite(self, poi_name: str) -> bool:
        """Check if a POI is a favorite with thread safety
        
        Args:
            poi_name: POI name
            
        Returns:
            bool: True if favorite, False otherwise
        """
        with _favorites_lock:
            return any(f.name == poi_name for f in self.favorites)

    def get_favorites_as_tuples(self) -> List[Tuple[str, str, str]]:
        """Get favorites as tuples with thread safety
        
        Returns:
            list: List of POI tuples (name, x, y)
        """
        with _favorites_lock:
            return [(f.name, f.x, f.y) for f in self.favorites]

    def get_source_tab(self, poi_name: str) -> Optional[str]:
        """Get source tab for a favorite POI with thread safety
        
        Args:
            poi_name: POI name
            
        Returns:
            str or None: Source tab name or None if not found
        """
        with _favorites_lock:
            fav = next((f for f in self.favorites if f.name == poi_name), None)
            return fav.source_tab if fav else None
        
    def remove_all_favorites(self) -> bool:
        """Remove all favorites with thread safety"""
        with _favorites_lock:
            old_favorites = self.favorites.copy()
            self.favorites = []
            success = self.save_favorites()
            if not success:
                # Rollback on failure
                self.favorites = old_favorites
                logger.error("Failed to save favorites after removing all")
                return False
            return True

class POIGUI(AccessibleUI):
    """POI selector GUI with safe config handling"""
    
    def __init__(self, poi_data, config_file: str = CONFIG_FILE):
        """Initialize the POI selector GUI
        
        Args:
            poi_data: POI data manager
            config_file: Path to config file
        """
        super().__init__(title="POI Selector")
        
        self.poi_data = poi_data
        self.config_file = config_file
        
        # Use the current map already determined by poi_data
        config = read_config()
        self.current_map = config.get('POI', 'current_map', fallback='main')
        
        # Create mutable reference for current map and POI set
        self.current_map_ref = [self.current_map]
        self.current_poi_set = [0]
        
        # Initialize favorites manager
        self.favorites_manager = FavoritesManager()
        
        # Store original config state for rollback if needed
        self.original_config_state = {
            'selected_poi': config.get('POI', 'selected_poi', fallback='closest, 0, 0'),
            'current_map': config.get('POI', 'current_map', fallback='main')
        }
        
        # Track if config has been modified
        self.config_modified = False
        
        # Setup UI components
        self.setup()
    
    def setup(self) -> None:
        """Set up the POI selector GUI"""
        # Add POI tab
        self.add_tab("P O I's")
        
        # Set up key bindings
        self.setup_poi_bindings()
        
        # Get POI sets to display
        self.poi_sets = self.get_poi_sets()
        
        # Create POI buttons for first set
        self.set_poi_buttons(0)
        
        # Window initialization
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        
        # Initialize focus
        self.root.after(100, lambda: force_focus_window(
            self.root,
            "",
            self.focus_first_widget
        ))
    
    def setup_poi_bindings(self) -> None:
        """Set up key bindings for POI GUI"""
        # Add map switching bindings
        self.root.bind('<Control-Tab>', self.switch_map)
        self.root.bind('<Control-Shift-Tab>', self.switch_map)
        
        # POI navigation bindings
        self.root.bind('<Tab>', self.cycle_poi_set)
        self.root.bind('<Shift-Tab>', self.cycle_poi_set)
        
        # Favorite management bindings
        self.root.bind('f', self.handle_favorite_key)
        self.root.bind('r', self.handle_remove_all_favorites)
    
    def get_poi_sets(self) -> List[Tuple[str, List[POI_TYPE]]]:
        """Get POI sets to display based on current map
        
        Returns:
            list: List of (category_name, poi_list) tuples
        """
        from lib.vision.object_finder import OBJECT_CONFIGS
        
        # Constants
        GAME_OBJECTS = [(name.replace('_', ' ').title(), "0", "0") for name in OBJECT_CONFIGS.keys()]
        SPECIAL_POIS = [("Safe Zone", "0", "0"), ("Closest", "0", "0"), ("Closest Game Object", "0", "0")]
        CLOSEST_LANDMARK = ("Closest Landmark", "0", "0")
        
        # Get map-specific custom POIs using the current map
        custom_pois = load_custom_pois(self.current_map_ref[0])
        
        if self.current_map_ref[0] == "main":
            return [
                ("Main P O I's", SPECIAL_POIS + sorted(self.poi_data.main_pois, key=self.poi_sort_key)),
                ("Landmarks", [CLOSEST_LANDMARK] + sorted(self.poi_data.landmarks, key=self.poi_sort_key)),
                ("Game Objects", GAME_OBJECTS),
                ("Custom P O I's", sorted(custom_pois, key=self.poi_sort_key)),
                ("Favorites", self.favorites_manager.get_favorites_as_tuples())
            ]
        else:
            # For other maps, show their specific custom POIs
            current_map_name = self.poi_data.maps[self.current_map_ref[0]].name
            return [
                (f"{current_map_name} P O I's", SPECIAL_POIS + sorted(self.poi_data.maps[self.current_map_ref[0]].pois, key=self.poi_sort_key)),
                ("Game Objects", GAME_OBJECTS),
                ("Custom P O I's", sorted(custom_pois, key=self.poi_sort_key)),
                ("Favorites", self.favorites_manager.get_favorites_as_tuples())
            ]
    
    def switch_map(self, event) -> str:
        """Handle tab switching with map change
        
        Args:
            event: Key event
            
        Returns:
            str: "break" to prevent default handling
        """
        maps = list(self.poi_data.maps.keys())
        current_idx = maps.index(self.current_map_ref[0])
        next_idx = (current_idx + (1 if not event.state & 0x1 else -1)) % len(maps)
        self.current_map_ref[0] = maps[next_idx]
        
        # Update POI sets for new map
        self.poi_sets = self.get_poi_sets()
        
        # Reset to first tab when switching maps
        self.set_poi_buttons(0)
        
        # Announce map change
        self.speak(f"Switched to {self.poi_data.maps[self.current_map_ref[0]].name}")
        return "break"
    
    def should_speak_position(self, poi_set_index: int, poi: Tuple[str, str, str]) -> bool:
        """Determine if position should be spoken for a POI
        
        Args:
            poi_set_index: Index of the POI set
            poi: POI data tuple
            
        Returns:
            bool: True if position should be spoken, False otherwise
        """
        # Don't speak positions for game objects
        if self.current_map_ref[0] == "main":
            game_objects_index = 2
        else:
            game_objects_index = 1
        
        if poi_set_index == game_objects_index:
            return False
        
        # Don't speak positions for special POIs
        SPECIAL_POIS = [("Safe Zone", "0", "0"), ("Closest", "0", "0"), ("Closest Game Object", "0", "0")]
        CLOSEST_LANDMARK = ("Closest Landmark", "0", "0")
        
        if poi in SPECIAL_POIS or poi == CLOSEST_LANDMARK:
            return False
            
        return True
    
    def create_poi_button(self, frame: ttk.Frame, poi: Union[Tuple[str, str, str], str], 
                         row: int, col: int, set_index: int) -> ttk.Button:
        """Create a POI button with appropriate text and speech
        
        Args:
            frame: Parent frame
            poi: POI data
            row: Grid row
            col: Grid column
            set_index: POI set index
            
        Returns:
            ttk.Button: Created button
        """
        button_text = poi[0] if isinstance(poi, tuple) else poi
        
        # Determine speech text based on POI type
        if self.should_speak_position(set_index, poi):
            speech_text = f"{poi[0]}, {self.get_poi_position_description(poi)}"
        else:
            speech_text = button_text
        
        # Create the button
        button = ttk.Button(frame, text=button_text, command=lambda p=button_text: self.select_poi(p))
        button.grid(row=row, column=col, padx=2, pady=2, sticky='nsew')
        
        # Add star to favorites
        if isinstance(poi, tuple) and self.favorites_manager.is_favorite(poi[0]):
            button.configure(text=f"⭐ {button_text}")
        
        # Set custom speech
        button.custom_speech = speech_text
        return button
    
    def set_poi_buttons(self, index: int) -> None:
        """Update the display with buttons for the selected POI set
        
        Args:
            index: POI set index
        """
        # Clear existing widgets
        self.widgets["P O I's"].clear()
        for widget in self.tabs["P O I's"].winfo_children():
            widget.destroy()

        # Update current set index
        self.current_poi_set[0] = index
        set_name, pois_to_use = self.poi_sets[index]
        
        # Announce set name
        self.speak(set_name)

        # Handle empty POI set
        if not pois_to_use:
            no_poi_message = f"No {set_name.lower()} available"
            button = ttk.Button(self.tabs["P O I's"], 
                              text=no_poi_message,
                              command=lambda: None)
            button.pack(fill='x', padx=5, pady=5)
            button.custom_speech = no_poi_message
            self.widgets["P O I's"].append(button)
            self.speak(no_poi_message)
            return

        # Create appropriate layout based on POI set type
        frame = ttk.Frame(self.tabs["P O I's"])
        frame.pack(expand=True, fill='both')

        # Determine which layout to use
        using_grid_layout = False
        
        # For main map, use grid layout for landmarks, custom POIs, and favorites
        if self.current_map_ref[0] == "main":
            using_grid_layout = index in [1, 3, 4]
        # For other maps, use grid layout for custom POIs and favorites
        else:
            using_grid_layout = index in [2, 3]

        if using_grid_layout:
            # Create grid layout for these types
            buttons_per_row = 10
            for i, poi in enumerate(pois_to_use):
                button = self.create_poi_button(frame, poi, i // buttons_per_row, i % buttons_per_row, index)
                frame.grid_columnconfigure(i % buttons_per_row, weight=1)
                self.widgets["P O I's"].append(button)
        else:  # Main POIs and Game Objects - use vertical list layout
            for poi in pois_to_use:
                button_text = poi[0] if isinstance(poi, tuple) else poi
                
                # Determine speech text based on POI type
                speech_text = f"{poi[0]}, {self.get_poi_position_description(poi)}" if self.should_speak_position(index, poi) else button_text
                
                # Add star for favorites
                if isinstance(poi, tuple) and self.favorites_manager.is_favorite(poi[0]):
                    button_text = f"⭐ {button_text}"
                
                # Create button
                button = ttk.Button(self.tabs["P O I's"],
                                  text=button_text,
                                  command=lambda p=poi[0]: self.select_poi(p))
                button.pack(fill='x', padx=5, pady=5)
                button.custom_speech = speech_text
                self.widgets["P O I's"].append(button)

        # Announce first POI if available
        if isinstance(pois_to_use[0], tuple):
            if self.should_speak_position(index, pois_to_use[0]):
                self.speak(f"{pois_to_use[0][0]}, {self.get_poi_position_description(pois_to_use[0])}")
            else:
                self.speak(pois_to_use[0][0])
        else:
            self.speak(pois_to_use[0])
    
    def select_poi(self, poi: str) -> None:
        """Handle POI selection and update configuration safely
        
        Args:
            poi: POI name
        """
        try:
            # Update the current map in POIData
            self.poi_data.current_map = self.current_map_ref[0]
        
            # Handle special POIs first
            if poi.lower() in ["closest", "safe zone", "closest landmark", "closest game object"]:
                special_poi_map = {
                    "closest": "Closest",
                    "closest landmark": "Closest Landmark",
                    "safe zone": "Safe Zone",
                    "closest game object": "Closest Game Object"
                }
                actual_name = special_poi_map.get(poi.lower(), poi)
                
                success = self.safe_update_config(actual_name, "0", "0")
                if success:
                    self.speak(f"{actual_name} selected")
                    self.close()
                else:
                    self.speak("Error updating configuration")
                return
        
            # Handle selecting a favorite POI
            source_tab = self.favorites_manager.get_source_tab(poi)
            if source_tab:
                for set_name, pois in self.poi_sets:
                    if set_name == source_tab:
                        for original_poi in pois:
                            if isinstance(original_poi, tuple) and original_poi[0] == poi:
                                success = self.safe_update_config_from_poi_data(poi)
                                if success:
                                    self.speak(f"{poi} selected")
                                    self.close()
                                else:
                                    self.speak("Error updating configuration")
                                return
            else:
                success = self.safe_update_config_from_poi_data(poi)
                if success:
                    self.speak(f"{poi} selected")
                    self.close()
                else:
                    self.speak("Error updating configuration")
                    
        except Exception as e:
            logger.error(f"Error in POI selection: {e}")
            self.speak("Error selecting POI")
    
    def safe_update_config(self, poi_name: str, x: str, y: str) -> bool:
        """Safely update config with POI selection
        
        Args:
            poi_name: POI name
            x: X coordinate
            y: Y coordinate
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Use thread-safe config operations
            config_adapter = Config()
            config_adapter.set_poi(poi_name, x, y)
            config_adapter.set_current_map(self.current_map_ref[0])
            
            success = config_adapter.save()
            if success:
                self.config_modified = True
                return True
            else:
                logger.error("Failed to save config")
                return False
                
        except Exception as e:
            logger.error(f"Error updating config: {e}")
            return False
    
    def safe_update_config_from_poi_data(self, selected_poi_name: str) -> bool:
        """Safely update configuration file with selected POI from data
        
        Args:
            selected_poi_name: Selected POI name
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Updating configuration for POI: {selected_poi_name}")
            
            current_map = self.current_map_ref[0]
            
            # Check current map's POIs
            if current_map == "main":
                poi_list = self.poi_data.main_pois + self.poi_data.landmarks
            else:
                poi_list = self.poi_data.maps[current_map].pois
                
            poi_entry = next(
                (poi for poi in poi_list if poi[0].lower() == selected_poi_name.lower()),
                None
            )
            
            # Check custom POIs if not found in main list
            if not poi_entry:
                # Use map-specific custom POI loading
                custom_pois = load_custom_pois(current_map)
                poi_entry = next(
                    (poi for poi in custom_pois if poi[0].lower() == selected_poi_name.lower()),
                    None
                )
        
            # Check game objects if still not found
            if not poi_entry:
                from lib.vision.object_finder import OBJECT_CONFIGS
                GAME_OBJECTS = [(name.replace('_', ' ').title(), "0", "0") for name in OBJECT_CONFIGS.keys()]
                
                poi_entry = next(
                    (poi for poi in GAME_OBJECTS 
                     if poi[0].lower() == selected_poi_name.lower()),
                    None
                )
        
            # Save the POI entry
            if poi_entry:
                return self.safe_update_config(poi_entry[0], poi_entry[1], poi_entry[2])
            else:
                return self.safe_update_config("none", "0", "0")
                
        except Exception as e:
            logger.error(f"Error updating configuration: {e}")
            return False
    
    def handle_favorite_key(self, event) -> None:
        """Handle pressing the favorite key for a POI with safe operations
        
        Args:
            event: Key event
        """
        try:
            focused = self.root.focus_get()
            if isinstance(focused, ttk.Button):
                try:
                    poi_text = focused['text'].replace('⭐ ', '')
                    current_set = self.poi_sets[self.current_poi_set[0]]
                    
                    poi = next((p for p in current_set[1] if isinstance(p, tuple) and p[0] == poi_text), None)
                    if poi:
                        # Toggle favorite status with thread safety
                        is_added = self.favorites_manager.toggle_favorite(poi, current_set[0])
                        
                        if is_added is not None:  # None indicates operation failed
                            # Update button text
                            focused.configure(text=f"⭐ {poi_text}" if is_added else poi_text)
                            
                            # Update favorites list index based on current map
                            if self.current_map_ref[0] == "main":
                                favorites_index = 4
                            else:
                                favorites_index = 3
                            self.poi_sets[favorites_index] = ("Favorites", self.favorites_manager.get_favorites_as_tuples())
                            
                            # Refresh favorites tab if currently viewing it
                            if self.current_poi_set[0] == favorites_index:
                                self.set_poi_buttons(favorites_index)
                            
                            # Announce action
                            action = "added to" if is_added else "removed from"
                            self.speak(f"{poi_text} {action} favorites")
                        else:
                            self.speak(f"Failed to update favorites for {poi_text}")
                        
                except tk.TclError:
                    pass
                except Exception as e:
                    logger.error(f"Error handling favorite key: {e}")
                    self.speak("Error updating favorites")
        except Exception as e:
            logger.error(f"Error in handle_favorite_key: {e}")
    
    def handle_remove_all_favorites(self, event) -> str:
        """Handle the remove all favorites key press with safe operations
        
        Args:
            event: Key event
            
        Returns:
            str: "break" to prevent default handling
        """
        try:
            # Determine favorites index based on current map
            if self.current_map_ref[0] == "main":
                favorites_index = 4
            else:
                favorites_index = 3
            
            if self.current_poi_set[0] == favorites_index:  # Only when in favorites tab
                self.show_remove_all_confirmation()
        except Exception as e:
            logger.error(f"Error in handle_remove_all_favorites: {e}")
        return "break"
    
    def show_remove_all_confirmation(self) -> None:
        """Show confirmation dialog for removing all favorites with safe operations"""
        try:
            confirmation = messagebox.askyesno(
                "Remove All Favorites",
                "Are you sure you want to remove all favorites?",
                parent=self.root
            )
            if confirmation:
                success = self.favorites_manager.remove_all_favorites()
                
                if success:
                    # Update favorites list index based on current map
                    if self.current_map_ref[0] == "main":
                        favorites_index = 4
                    else:
                        favorites_index = 3
                    self.poi_sets[favorites_index] = ("Favorites", [])
                    
                    # Refresh favorites tab if currently viewing it
                    if self.current_poi_set[0] == favorites_index:
                        self.set_poi_buttons(favorites_index)
                        
                    self.speak("All favorites removed")
                else:
                    self.speak("Failed to remove all favorites")
            else:
                self.speak("Operation cancelled")
        except Exception as e:
            logger.error(f"Error in show_remove_all_confirmation: {e}")
            self.speak("Error removing favorites")
    
    def cycle_poi_set(self, event) -> str:
        """Handle cycling between POI sets
        
        Args:
            event: Key event
            
        Returns:
            str: "break" to prevent default handling
        """
        try:
            next_index = (
                self.current_poi_set[0] + (1 if not event.state & 0x1 else -1)
            ) % len(self.poi_sets)
            self.set_poi_buttons(next_index)
        except Exception as e:
            logger.error(f"Error cycling POI set: {e}")
        return "break"
    
    def focus_first_widget(self) -> None:
        """Focus the first widget and announce its state"""
        try:
            if self.widgets["P O I's"]:
                first_widget = self.widgets["P O I's"][0]
                first_widget.focus_set()
                widget_info = self.get_widget_info(first_widget)
                if widget_info:
                    self.speak(widget_info)
        except Exception as e:
            logger.error(f"Error focusing first widget: {e}")
    
    def poi_sort_key(self, poi: Tuple[str, str, str]) -> Tuple[int, int, int, int]:
        """Generate a sort key for POI ordering
        
        Args:
            poi: Tuple containing (name, x, y) coordinates
        
        Returns:
            tuple: Sort key for consistent ordering
        """
        name, x, y = poi
        try:
            x = int(float(x)) - ROI_START_ORIG[0]
            y = int(float(y)) - ROI_START_ORIG[1]
            width, height = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]
            
            quadrant = get_quadrant(x, y, width, height)
            position = get_position_in_quadrant(x, y, width // 2, height // 2)
            
            position_values = {
                "top-left": 0, "top": 1, "top-right": 2,
                "left": 3, "center": 4, "right": 5,
                "bottom-left": 6, "bottom": 7, "bottom-right": 8
            }
            
            return (quadrant, position_values.get(position, 9), y, x)
        except (ValueError, TypeError):
            # If coordinates can't be parsed, sort alphabetically by name
            return (9, 9, 9, 9)
    
    def get_poi_position_description(self, poi: Tuple[str, str, str]) -> str:
        """Generate a description of a POI's position
        
        Args:
            poi: Tuple containing (name, x, y) coordinates
        
        Returns:
            str: Description of the POI's position
        """
        try:
            name, x, y = poi
            x = int(float(x)) - ROI_START_ORIG[0]
            y = int(float(y)) - ROI_START_ORIG[1]
            width, height = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]
            
            quadrant = get_quadrant(x, y, width, height)
            position = get_position_in_quadrant(x, y, width // 2, height // 2)
            
            quadrant_names = ["top-left", "top-right", "bottom-left", "bottom-right"]
            return f"in the {position} of the {quadrant_names[quadrant]} quadrant"
        except (ValueError, TypeError):
            return "position unknown"
    
    def close(self) -> None:
        """Close the GUI safely"""
        try:
            # Clear config cache to ensure fresh reads elsewhere
            clear_config_cache()
            super().close()
        except Exception as e:
            logger.error(f"Error closing POI GUI: {e}")


def launch_poi_selector(poi_data = None) -> None:
    """Launch the POI selector GUI with safe error handling
    
    Args:
        poi_data: POI data manager (optional)
    """
    try:
        # Initialize POI data if not provided
        if poi_data is None:
            poi_data = POIData()
            
        gui = POIGUI(poi_data)
        gui.run()
    except Exception as e:
        logger.error(f"Error launching POI selector GUI: {e}")