from tkinter import ttk
import tkinter as tk
from typing import List, Tuple, Union, Dict
import configparser
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple
import requests
import numpy as np

from lib.guis.AccessibleUIBackend import AccessibleUIBackend
from lib.object_finder import OBJECT_CONFIGS
from lib.player_location import ROI_START_ORIG, ROI_END_ORIG, get_quadrant, get_position_in_quadrant
from lib.utilities import force_focus_window
import pyautogui

CONFIG_FILE = 'CONFIG.txt'
POI_TYPE = Union[Tuple[str, str, str], str]

@dataclass
class FavoritePOI:
    name: str
    x: str
    y: str
    source_tab: str

class FavoritesManager:
    def __init__(self, filename: str = "fav_pois.txt"):
        self.filename = filename
        self.favorites: List[FavoritePOI] = []
        self.load_favorites()

    def load_favorites(self) -> None:
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    data = json.load(f)
                    self.favorites = [FavoritePOI(**poi) for poi in data]
            except json.JSONDecodeError:
                print("Error loading favorites file. Starting with empty favorites.")
                self.favorites = []
        else:
            self.favorites = []

    def save_favorites(self) -> None:
        with open(self.filename, 'w') as f:
            json.dump([vars(poi) for poi in self.favorites], f, indent=2)

    def toggle_favorite(self, poi: Tuple[str, str, str], source_tab: str) -> bool:
        name, x, y = poi
        existing = next((f for f in self.favorites if f.name == name), None)
        
        if existing:
            self.favorites.remove(existing)
            self.save_favorites()
            return False
        else:
            new_fav = FavoritePOI(name=name, x=x, y=y, source_tab=source_tab)
            self.favorites.append(new_fav)
            self.save_favorites()
            return True

    def is_favorite(self, poi_name: str) -> bool:
        return any(f.name == poi_name for f in self.favorites)

    def get_favorites_as_tuples(self) -> List[Tuple[str, str, str]]:
        return [(f.name, f.x, f.y) for f in self.favorites]

    def get_source_tab(self, poi_name: str) -> str:
        fav = next((f for f in self.favorites if f.name == poi_name), None)
        return fav.source_tab if fav else None

class CoordinateSystem:
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

@dataclass
class MapData:
    name: str
    pois: List[Tuple[str, str, str]]
    image_file: str

class POIData:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(POIData, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not POIData._initialized:
            self.maps: Dict[str, MapData] = {}
            self.current_map = "main"  # Default map
            self.main_pois: List[Tuple[str, str, str]] = []  # Keep these attributes
            self.landmarks: List[Tuple[str, str, str]] = []  # Keep these attributes
            self.coordinate_system = CoordinateSystem()
            self._load_all_maps()
            self._fetch_and_process_pois()  # For main map
            POIData._initialized = True
            
    def _load_all_maps(self):
        # Load main map first
        self.maps["main"] = MapData("Main Map", [], "maps/main.png")
        
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
                            pois=pois,
                            image_file=f"maps/{map_name}.png"
                        )

    def _load_map_pois(self, filename: str) -> List[Tuple[str, str, str]]:
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
        try:
            #print("Fetching POI data from API...")
            response = requests.get('https://fortnite-api.com/v1/map', params={'language': 'en'})
            response.raise_for_status()
            
            # Print raw response for debugging
            #print("\nRAW API Response:")
            #print(json.dumps(response.json(), indent=2))
            #print("\nProcessing data...")
            
            self.api_data = response.json().get('data', {}).get('pois', [])

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
            self.main_pois = []
            self.landmarks = []

# Constants
GAME_OBJECTS = [(name.replace('_', ' ').title(), "0", "0") for name in OBJECT_CONFIGS.keys()]
SPECIAL_POIS = [("Safe Zone", "0", "0"), ("Closest", "0", "0")]
CLOSEST_LANDMARK = ("Closest Landmark", "0", "0")

def select_poi_tk(existing_poi_data: POIData = None) -> None:
    """Create and display the POI selector GUI."""
    ui = AccessibleUIBackend("POI Selector")
    poi_data = existing_poi_data or POIData()
    
    # Load last used map from config
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    current_map = config.get('POI', 'current_map', fallback='main')
    
    # Convert clean map name back to file format if needed
    if current_map != 'main' and current_map + '_' in poi_data.maps:
        current_map = current_map + '_'
    
    if current_map not in poi_data.maps:
        current_map = 'main'
    
    current_map_ref = [current_map]  # Mutable reference

    def get_current_poi_sets():
        if current_map_ref[0] == "main":
            return [
                ("Main P O I's", SPECIAL_POIS + sorted(poi_data.main_pois, key=poi_sort_key)),
                ("Landmarks", [CLOSEST_LANDMARK] + sorted(poi_data.landmarks, key=poi_sort_key)),
                ("Game Objects", GAME_OBJECTS),
                ("Custom P O I's", load_custom_pois()),
                ("Favorites", favorites_manager.get_favorites_as_tuples())
            ]
        else:
            current_map_name = poi_data.maps[current_map_ref[0]].name
            return [
                (f"{current_map_name} P O I's", SPECIAL_POIS + sorted(poi_data.maps[current_map_ref[0]].pois, key=poi_sort_key)),
                ("Favorites", favorites_manager.get_favorites_as_tuples())
            ]        
    def switch_map(event=None):
        maps = list(poi_data.maps.keys())
        current_idx = maps.index(current_map_ref[0])
        next_idx = (current_idx + (1 if not event.state & 0x1 else -1)) % len(maps)
        current_map_ref[0] = maps[next_idx]
        poi_sets.clear()
        poi_sets.extend(get_current_poi_sets())
        set_poi_buttons(0)  # Reset to first tab when switching maps
        ui.speak(f"Switched to {poi_data.maps[current_map_ref[0]].name}")
        return "break"
    
    # Add map switching bindings
    ui.root.bind('<Control-Tab>', switch_map)
    ui.root.bind('<Control-Shift-Tab>', switch_map)
    
    ui.add_tab("P O I's")
    
    # Initialize state
    current_poi_set = [0]  # Using list for mutable reference
    favorites_manager = FavoritesManager()

    # Load custom POIs
    def load_custom_pois() -> List[Tuple[str, str, str]]:
        custom_pois = []
        if os.path.exists('CUSTOM_POI.txt'):
            try:
                with open('CUSTOM_POI.txt', 'r', encoding='utf-8') as f:
                    for line in f:
                        parts = line.strip().split(',')
                        if len(parts) == 3:
                            name, x, y = parts
                            custom_pois.append((name, x, y))
            except Exception as e:
                print(f"Error loading custom POIs: {e}")
        return sorted(custom_pois, key=poi_sort_key)

    # Initialize poi_sets
    poi_sets = get_current_poi_sets()    # Helper functions
    def should_speak_position(poi_set_index: int, poi: Tuple[str, str, str]) -> bool:
        """Determine if position should be spoken for a POI."""
        if poi_set_index == 2:  # Game Objects
            return False
        if poi in SPECIAL_POIS or poi == CLOSEST_LANDMARK:
            return False
        return True

    def create_poi_button(frame: ttk.Frame, poi: Union[Tuple[str, str, str], str], 
                         row: int, col: int, set_index: int) -> ttk.Button:
        """Create a POI button with appropriate text and speech."""
        button_text = poi[0] if isinstance(poi, tuple) else poi
        speech_text = f"{poi[0]}, {get_poi_position_description(poi)}" if should_speak_position(set_index, poi) else button_text
        
        button = ttk.Button(frame, text=button_text, command=lambda p=button_text: select_poi(p))
        button.grid(row=row, column=col, padx=2, pady=2, sticky='nsew')
        
        if isinstance(poi, tuple) and favorites_manager.is_favorite(poi[0]):
            button.configure(text=f"⭐ {button_text}")
        
        button.custom_speech = speech_text
        return button

    # Button grid creation
    def create_button_grid(frame: ttk.Frame, pois: List[POI_TYPE], set_index: int) -> None:
        """Create a grid of POI buttons."""
        buttons_per_row = 10
        for i, poi in enumerate(pois):
            button = create_poi_button(frame, poi, i // buttons_per_row, i % buttons_per_row, set_index)
            frame.grid_columnconfigure(i % buttons_per_row, weight=1)
            ui.widgets["P O I's"].append(button)

    # POI set handling
    def set_poi_buttons(index: int) -> None:
        """Update the display with buttons for the selected POI set."""
        ui.widgets["P O I's"].clear()
        for widget in ui.tabs["P O I's"].winfo_children():
            widget.destroy()

        current_poi_set[0] = index
        set_name, pois_to_use = poi_sets[index]
        ui.speak(set_name)

        if not pois_to_use:
            no_poi_message = "No custom POIs set" if index == 3 else "No POIs available"
            button = ttk.Button(ui.tabs["P O I's"], 
                              text=no_poi_message,
                              command=lambda: None)
            button.pack(fill='x', padx=5, pady=5)
            button.custom_speech = no_poi_message
            ui.widgets["P O I's"].append(button)
            ui.speak(no_poi_message)
            return

        frame = ttk.Frame(ui.tabs["P O I's"])
        frame.pack(expand=True, fill='both')

        if index in [1, 3, 4]:  # Landmarks, Custom POIs, or Favorites
            create_button_grid(frame, pois_to_use, index)
        else:  # Main POIs and Game Objects
            for poi in pois_to_use:
                button_text = poi[0] if isinstance(poi, tuple) else poi
                speech_text = f"{poi[0]}, {get_poi_position_description(poi)}" if should_speak_position(index, poi) else button_text
                
                if isinstance(poi, tuple) and favorites_manager.is_favorite(poi[0]):
                    button_text = f"⭐ {button_text}"
                
                button = ttk.Button(ui.tabs["P O I's"],
                                  text=button_text,
                                  command=lambda p=poi[0]: select_poi(p))
                button.pack(fill='x', padx=5, pady=5)
                button.custom_speech = speech_text
                ui.widgets["P O I's"].append(button)

        # Announce first POI
        if isinstance(pois_to_use[0], tuple):
            if should_speak_position(index, pois_to_use[0]):
                ui.speak(f"{pois_to_use[0][0]}, {get_poi_position_description(pois_to_use[0])}")
            else:
                ui.speak(pois_to_use[0][0])
        else:
            ui.speak(pois_to_use[0])

    # POI selection handling
    def select_poi(poi: str) -> None:
        """Handle POI selection and update configuration."""
        # Update the current map in POIData
        poi_data.current_map = current_map_ref[0]
    
        if poi == "Closest Landmark":
            update_config_file(poi, poi_data)
            ui.speak("Closest Landmark selected")
            ui.save_and_close()
            return
    
        source_tab = favorites_manager.get_source_tab(poi)
        if source_tab:
            for set_name, pois in poi_sets:
                if set_name == source_tab:
                    for original_poi in pois:
                        if isinstance(original_poi, tuple) and original_poi[0] == poi:
                            update_config_file(poi, poi_data)
                            break
        else:
            update_config_file(poi, poi_data)
    
        ui.speak(f"{poi} selected")
        ui.save_and_close()

    # Favorites handling
    def handle_favorite_key(event) -> None:
        """Handle pressing the favorite key for a POI."""
        focused = ui.root.focus_get()
        if isinstance(focused, ttk.Button):
            try:
                poi_text = focused['text'].replace('⭐ ', '')
                current_set = poi_sets[current_poi_set[0]]
                
                poi = next((p for p in current_set[1] if isinstance(p, tuple) and p[0] == poi_text), None)
                if poi:
                    is_added = favorites_manager.toggle_favorite(poi, current_set[0])
                    focused.configure(text=f"⭐ {poi_text}" if is_added else poi_text)
                    poi_sets[4] = ("Favorites", favorites_manager.get_favorites_as_tuples())  # Updated index to 4
                    
                    if current_poi_set[0] == 4:  # Updated index to 4
                        set_poi_buttons(4)  # Updated index to 4
                    
                    action = "added to" if is_added else "removed from"
                    ui.speak(f"{poi_text} {action} favorites")
                    
            except tk.TclError:
                pass

    def show_remove_all_confirmation() -> None:
        """Show confirmation dialog for removing all favorites."""
        confirmation = tk.messagebox.askyesno(
            "Remove All Favorites",
            "Are you sure you want to remove all favorites?",
            parent=ui.root
        )
        if confirmation:
            favorites_manager.favorites = []
            favorites_manager.save_favorites()
            poi_sets[4] = ("Favorites", favorites_manager.get_favorites_as_tuples())  # Updated index to 4
            if current_poi_set[0] == 4:  # Updated index to 4
                set_poi_buttons(4)  # Updated index to 4
            ui.speak("All favorites removed")
        else:
            ui.speak("Operation cancelled")

    def handle_remove_all_favorites(event) -> str:
        """Handle the remove all favorites key press."""
        if current_poi_set[0] == 4:  # Updated index to 4
            show_remove_all_confirmation()
        return "break"

    # Navigation handling
    def cycle_poi_set(event) -> str:
        """Handle cycling between POI sets."""
        next_index = (
            current_poi_set[0] + (1 if not event.state & 0x1 else -1)
        ) % len(poi_sets)
        set_poi_buttons(next_index)
        return "break"

    # Window initialization
    def initialize_window() -> None:
        """Set up window properties and bindings."""
        ui.root.resizable(False, False)
        ui.root.protocol("WM_DELETE_WINDOW", ui.save_and_close)
        
        # Bind keyboard shortcuts
        ui.root.bind('<Tab>', cycle_poi_set)
        ui.root.bind('<Shift-Tab>', cycle_poi_set)
        ui.root.bind('f', handle_favorite_key)
        ui.root.bind('r', handle_remove_all_favorites)

    # Focus handling
    def focus_first_widget() -> None:
        """Focus the first widget and announce its state."""
        if ui.widgets["P O I's"]:
            first_widget = ui.widgets["P O I's"][0]
            first_widget.focus_set()
            widget_info = ui.get_widget_info(first_widget)
            if widget_info:
                ui.speak(widget_info)

    # Create interface
    initialize_window()
    set_poi_buttons(0)  # Initialize with first POI set

    # Initialize focus
    ui.root.after(100, lambda: force_focus_window(
        ui.root,
        "",
        focus_first_widget
    ))

    # Start the UI
    ui.run()

def update_config_file(selected_poi_name: str, poi_data: POIData) -> None:
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    
    if 'POI' not in config:
        config['POI'] = {}
    
    # Save current map with clean name in config
    current_map = poi_data.current_map
    config['POI']['current_map'] = current_map.replace('_', '')
    
    # Use original map name (with underscore) for accessing map data
    if selected_poi_name.lower() == "closest landmark":
        config['POI']['selected_poi'] = "Closest Landmark, 0, 0"
    else:
        # Check current map's POIs first
        if current_map == "main":
            poi_list = poi_data.main_pois + poi_data.landmarks
        else:
            # Use the original map name with underscore
            poi_list = poi_data.maps[current_map].pois
            
        poi_entry = next(
            (poi for poi in poi_list if poi[0].lower() == selected_poi_name.lower()),
            None
        )
        
        # If not found, check custom POIs
        if not poi_entry and os.path.exists('CUSTOM_POI.txt'):
            try:
                with open('CUSTOM_POI.txt', 'r', encoding='utf-8') as f:
                    for line in f:
                        parts = line.strip().split(',')
                        if len(parts) == 3 and parts[0].lower() == selected_poi_name.lower():
                            poi_entry = tuple(parts)
                            break
            except Exception as e:
                print(f"Error reading custom POIs: {e}")

        # If still not found, check special POIs
        if not poi_entry:
            poi_entry = next(
                (poi for poi in SPECIAL_POIS + GAME_OBJECTS 
                 if poi[0].lower() == selected_poi_name.lower()),
                None
            )

        config['POI']['selected_poi'] = (
            f'{poi_entry[0]}, {poi_entry[1]}, {poi_entry[2]}'
            if poi_entry else 'none, 0, 0'
        )

    with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
        config.write(configfile)

    print(f"Updated config file with POI: {config['POI']['selected_poi']} on map: {config['POI']['current_map']}")

def poi_sort_key(poi: Tuple[str, str, str]) -> Tuple[int, int, int, int]:
    """Generate a sort key for POI ordering.
    
    Args:
        poi: Tuple containing (name, x, y) coordinates
    
    Returns:
        Tuple of sort values for consistent ordering
    """
    name, x, y = poi
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

def get_poi_position_description(poi: Tuple[str, str, str]) -> str:
    """Generate a description of a POI's position.
    
    Args:
        poi: Tuple containing (name, x, y) coordinates
    
    Returns:
        String describing the POI's position
    """
    name, x, y = poi
    x = int(float(x)) - ROI_START_ORIG[0]
    y = int(float(y)) - ROI_START_ORIG[1]
    width, height = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]
    
    quadrant = get_quadrant(x, y, width, height)
    position = get_position_in_quadrant(x, y, width // 2, height // 2)
    
    quadrant_names = ["top-left", "top-right", "bottom-left", "bottom-right"]
    return f"in the {position} of the {quadrant_names[quadrant]} quadrant"
