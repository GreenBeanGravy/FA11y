from tkinter import ttk
import tkinter as tk
from typing import List, Tuple, Union, Dict
import configparser
import json
import os
from dataclasses import dataclass
import numpy as np
import requests

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

class MapData:
    def __init__(self, name: str):
        self.name = name
        self.pois: List[Tuple[str, str, str]] = []
        self.landmarks: List[Tuple[str, str, str]] = []
        self.load_map_data()

    def load_map_data(self) -> None:
        filename = f'map_{self.name}_pois.txt'
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    for line in f:
                        if line.strip() and not line.startswith('#'):
                            # Split by comma and clean up whitespace
                            parts = [part.strip() for part in line.strip().split(',')]
                            if len(parts) >= 3:  # Ensure we have at least name, x, y
                                name, x, y = parts[:3]
                                poi_type = parts[3].lower() if len(parts) > 3 else 'poi'
                                poi_data = (name, x, y)
                                
                                if poi_type == 'landmark':
                                    self.landmarks.append(poi_data)
                                else:
                                    self.pois.append(poi_data)
            except Exception as e:
                print(f"Error loading map data for {self.name}: {e}")

    def has_pois(self) -> bool:
        return len(self.pois) > 0

    def has_landmarks(self) -> bool:
        return len(self.landmarks) > 0

class POIData:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(POIData, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not POIData._initialized:
            self.main_pois: List[Tuple[str, str, str]] = []
            self.landmarks: List[Tuple[str, str, str]] = []
            self.maps_info: Dict[str, MapData] = {'main': None}
            self.coordinate_system = CoordinateSystem()
            self._fetch_and_process_pois()
            self._load_additional_maps()
            POIData._initialized = True

    def _fetch_and_process_pois(self) -> None:
        try:
            print("Fetching POI data from API...")
            response = requests.get('https://fortnite-api.com/v1/map', params={'language': 'en'})
            response.raise_for_status()
            self.api_data = response.json().get('data', {}).get('pois', [])

            for poi in self.api_data:
                name = poi['name']
                world_x = float(poi['location']['x'])
                world_y = float(poi['location']['y'])
                screen_x, screen_y = self.coordinate_system.world_to_screen(world_x, world_y)
                
                if name.isupper():
                    self.main_pois.append((name, str(screen_x), str(screen_y)))
                else:
                    self.landmarks.append((name, str(screen_x), str(screen_y)))

            print(f"Successfully processed {len(self.main_pois)} main POIs and {len(self.landmarks)} landmarks")

        except requests.RequestException as e:
            print(f"Error fetching POIs from API: {e}")
            self.main_pois = []
            self.landmarks = []

    def _load_additional_maps(self) -> None:
        for filename in os.listdir():
            if filename.startswith('map_') and filename.endswith('_pois.txt'):
                map_name = filename[4:-9]  # Extract name between 'map_' and '_pois.txt'
                if map_name != 'main':
                    self.maps_info[map_name] = MapData(map_name)

class CoordinateSystem:
    def __init__(self, poi_file="pois.txt"):
        self.poi_file = poi_file
        self.REFERENCE_PAIRS = self._load_reference_pairs()
        self.transform_matrix = self._calculate_transformation_matrix()

    def _load_reference_pairs(self) -> dict:
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

def select_poi_tk(existing_poi_data: POIData = None) -> None:
    ui = AccessibleUIBackend("POI Selector")
    ui.add_tab("P O I's")
    
    current_poi_set = [0]
    poi_data = existing_poi_data or POIData()
    favorites_manager = FavoritesManager()

    # Initialize current_map with last selected map if valid
    config = configparser.ConfigParser()
    config.read('CONFIG.txt')
    last_map = config.get('MAP', 'last_selected_map', fallback='main')
    current_map = [last_map if last_map in poi_data.maps_info and last_map != 'None' else 'main']

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

    def get_current_map_poi_sets():
        if current_map[0] == 'main':
            return [
                ("Main P O I's", SPECIAL_POIS + sorted(poi_data.main_pois, key=poi_sort_key)),
                ("Landmarks", [CLOSEST_LANDMARK] + sorted(poi_data.landmarks, key=poi_sort_key)),
                ("Game Objects", GAME_OBJECTS),
                ("Custom P O I's", load_custom_pois()),
                ("Favorites", favorites_manager.get_favorites_as_tuples())
            ]
        else:
            map_data = poi_data.maps_info[current_map[0]]
            poi_sets = []
            
            # Include Safe Zone and Closest for all maps
            special_pois = [("Safe Zone", "0", "0"), ("Closest", "0", "0")]
            
            # Only add tabs for categories that have content
            if map_data.has_pois():
                poi_sets.append((f"{current_map[0].title()} P O I's", special_pois + sorted(map_data.pois, key=poi_sort_key)))
            if map_data.has_landmarks():
                poi_sets.append((f"{current_map[0].title()} Landmarks", [CLOSEST_LANDMARK] + sorted(map_data.landmarks, key=poi_sort_key)))
                
            custom_pois = load_custom_pois()
            if custom_pois:
                poi_sets.append(("Custom P O I's", custom_pois))
                
            favorites = favorites_manager.get_favorites_as_tuples()
            if favorites:
                poi_sets.append(("Favorites", favorites))
                
            return poi_sets if poi_sets else [("No POIs Available", [])]

    def switch_map(direction: int) -> None:
        maps = list(poi_data.maps_info.keys())
        current_index = maps.index(current_map[0])
        new_index = (current_index + direction) % len(maps)
        current_map[0] = maps[new_index]
        current_poi_set[0] = 0  # Reset to first POI set when switching maps
        rebuild_interface()

    def rebuild_interface() -> None:
        for widget in ui.tabs["P O I's"].winfo_children():
            widget.destroy()
        ui.widgets["P O I's"].clear()
        set_poi_buttons(0)
        ui.speak(f"Switched to {current_map[0]} map")

    def should_speak_position(poi_set_index: int, poi: Tuple[str, str, str]) -> bool:
        if poi_set_index == 2 and current_map[0] == 'main':  # Game Objects
            return False
        if poi in SPECIAL_POIS or poi == CLOSEST_LANDMARK:
            return False
        return True

    def create_poi_button(frame: ttk.Frame, poi: Union[Tuple[str, str, str], str], 
                         row: int, col: int, set_index: int) -> ttk.Button:
        button_text = poi[0] if isinstance(poi, tuple) else poi
        speech_text = f"{poi[0]}, {get_poi_position_description(poi)}" if should_speak_position(set_index, poi) else button_text
        
        button = ttk.Button(frame, text=button_text, command=lambda p=button_text: select_poi(p))
        button.grid(row=row, column=col, padx=2, pady=2, sticky='nsew')
        
        if isinstance(poi, tuple) and favorites_manager.is_favorite(poi[0]):
            button.configure(text=f"⭐ {button_text}")
        
        button.custom_speech = speech_text
        return button

    def create_button_grid(frame: ttk.Frame, pois: List[POI_TYPE], set_index: int) -> None:
        buttons_per_row = 10
        for i, poi in enumerate(pois):
            button = create_poi_button(frame, poi, i // buttons_per_row, i % buttons_per_row, set_index)
            frame.grid_columnconfigure(i % buttons_per_row, weight=1)
            ui.widgets["P O I's"].append(button)

    def set_poi_buttons(index: int) -> None:
        ui.widgets["P O I's"].clear()
        for widget in ui.tabs["P O I's"].winfo_children():
            widget.destroy()

        current_poi_set[0] = index
        poi_sets = get_current_map_poi_sets()
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

        if index in [1, 3, 4] and current_map[0] == 'main':  # Landmarks, Custom POIs, or Favorites
            create_button_grid(frame, pois_to_use, index)
        else:
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

    def select_poi(poi: str) -> None:
        if poi == "Closest Landmark":
            update_config_file(poi, poi_data)
            ui.speak("Closest Landmark selected")
            pyautogui.click()
            ui.root.destroy()
            return
        
        source_tab = favorites_manager.get_source_tab(poi)
        if source_tab:
            for set_name, pois in get_current_map_poi_sets():
                if set_name == source_tab:
                    for original_poi in pois:
                        if isinstance(original_poi, tuple) and original_poi[0] == poi:
                            update_config_file(poi, poi_data, current_map[0])
                            break
        else:
            update_config_file(poi, poi_data, current_map[0])
        
        ui.speak(f"{poi} selected")
        pyautogui.click()
        ui.root.destroy()

    def handle_favorite_key(event) -> None:
        focused = ui.root.focus_get()
        if isinstance(focused, ttk.Button):
            try:
                poi_text = focused['text'].replace('⭐ ', '')
                current_set = get_current_map_poi_sets()[current_poi_set[0]]
                
                poi = next((p for p in current_set[1] if isinstance(p, tuple) and p[0] == poi_text), None)
                if poi:
                    is_added = favorites_manager.toggle_favorite(poi, current_set[0])
                    focused.configure(text=f"⭐ {poi_text}" if is_added else poi_text)
                    poi_sets = get_current_map_poi_sets()
                    
                    if current_poi_set[0] == len(poi_sets) - 1:  # Favorites tab
                        set_poi_buttons(current_poi_set[0])
                    
                    action = "added to" if is_added else "removed from"
                    ui.speak(f"{poi_text} {action} favorites")
                    
            except tk.TclError:
                pass

    def show_remove_all_confirmation() -> None:
        confirmation = tk.messagebox.askyesno(
            "Remove All Favorites",
            "Are you sure you want to remove all favorites?",
            parent=ui.root
        )
        if confirmation:
            favorites_manager.favorites = []
            favorites_manager.save_favorites()
            poi_sets = get_current_map_poi_sets()
            if current_poi_set[0] == len(poi_sets) - 1:  # Favorites tab
                set_poi_buttons(current_poi_set[0])
            ui.speak("All favorites removed")
        else:
            ui.speak("Operation cancelled")

    def handle_remove_all_favorites(event) -> str:
        poi_sets = get_current_map_poi_sets()
        if current_poi_set[0] == len(poi_sets) - 1:  # Favorites tab
            show_remove_all_confirmation()
        return "break"

    def handle_map_switch(event) -> str:
        direction = 1 if not event.state & 0x1 else -1  # Check if Shift is pressed
        switch_map(direction)
        return "break"

    def cycle_poi_set(event) -> str:
        next_index = (
            current_poi_set[0] + (1 if not event.state & 0x1 else -1)
        ) % len(get_current_map_poi_sets())
        set_poi_buttons(next_index)
        return "break"

    def initialize_window() -> None:
        ui.root.resizable(False, False)
        ui.root.protocol("WM_DELETE_WINDOW", ui.save_and_close)
        
        # Bind keyboard shortcuts
        ui.root.bind('<Tab>', cycle_poi_set)
        ui.root.bind('<Shift-Tab>', cycle_poi_set)
        ui.root.bind('f', handle_favorite_key)
        ui.root.bind('r', handle_remove_all_favorites)
        ui.root.bind('<Control-Tab>', handle_map_switch)
        ui.root.bind('<Control-Shift-Tab>', handle_map_switch)

    def focus_first_widget() -> None:
        if ui.widgets["P O I's"]:
            first_widget = ui.widgets["P O I's"][0]
            first_widget.focus_set()
            widget_info = ui.get_widget_info(first_widget)
            if widget_info:
                ui.speak(widget_info)

    # Initialize interface
    initialize_window()
    set_poi_buttons(0)

    # Initialize focus
    ui.root.after(100, lambda: force_focus_window(
        ui.root,
        "",
        focus_first_widget
    ))

    # Start the UI
    ui.run()

def update_config_file(selected_poi_name: str, poi_data: POIData, map_name: str = 'main') -> None:
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    if 'POI' not in config:
        config['POI'] = {}
    if 'MAP' not in config:
        config['MAP'] = {}

    # Handle special POIs without changing the map
    special_pois = {
        'closest landmark': ('Closest Landmark', '0', '0'),
        'closest': ('Closest', '0', '0'),
        'safe zone': ('Safe Zone', '0', '0')
    }
    
    name = selected_poi_name.lower()
    if name in special_pois:
        config['POI']['selected_poi'] = f"{special_pois[name][0]}, {special_pois[name][1]}, {special_pois[name][2]}"
        # Don't update map for special POIs
        with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
        return

    # Handle game objects
    game_object_names = [obj[0].lower() for obj in GAME_OBJECTS]
    if name in game_object_names:
        # Find original case from GAME_OBJECTS
        original_name = next(obj[0] for obj in GAME_OBJECTS if obj[0].lower() == name)
        config['POI']['selected_poi'] = f"{original_name}, 0, 0"
        # Don't update map for game objects
        with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
        return

    # Ensure map_name is valid, but don't reset to 'main' automatically
    if map_name is None:
        print(f"No map specified for POI {selected_poi_name}. Using previous map if available.")
        map_name = config.get('MAP', 'last_selected_map', fallback='main')

    # Check for direct coordinate format
    parts = [p.strip() for p in selected_poi_name.split(',')]
    if len(parts) == 3:
        try:
            name = parts[0]
            x = int(float(parts[1]))
            y = int(float(parts[2]))
            config['POI']['selected_poi'] = f"{name}, {x}, {y}"
            if map_name:  # Only update map if we have a valid one
                config['MAP']['last_selected_map'] = map_name
            with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                config.write(configfile)
            return
        except ValueError:
            pass

    # Check custom POIs
    if os.path.exists('CUSTOM_POI.txt'):
        with open('CUSTOM_POI.txt', 'r', encoding='utf-8') as f:
            for line in f:
                c_parts = line.strip().split(',')
                if len(c_parts) == 3 and c_parts[0].strip().lower() == name:
                    try:
                        cx, cy = int(float(c_parts[1])), int(float(c_parts[2]))
                        config['POI']['selected_poi'] = f"{c_parts[0].strip()}, {cx}, {cy}"
                        # Custom POIs maintain current map
                        if map_name:
                            config['MAP']['last_selected_map'] = map_name
                        with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                            config.write(configfile)
                        return
                    except ValueError:
                        pass

    # Try to find POI in specified map first
    if map_name and map_name != 'main':
        map_data = poi_data.maps_info.get(map_name)
        if map_data:
            # Check POIs
            for poi in map_data.pois:
                if poi[0].lower() == name:
                    x, y = int(float(poi[1])), int(float(poi[2]))
                    config['POI']['selected_poi'] = f"{poi[0]}, {x}, {y}"
                    config['MAP']['last_selected_map'] = map_name
                    with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                        config.write(configfile)
                    return
            # Check landmarks
            for poi in map_data.landmarks:
                if poi[0].lower() == name:
                    x, y = int(float(poi[1])), int(float(poi[2]))
                    config['POI']['selected_poi'] = f"{poi[0]}, {x}, {y}"
                    config['MAP']['last_selected_map'] = map_name
                    with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                        config.write(configfile)
                    return

    # If not found in specified map or map is main, check main map POIs
    for poi in poi_data.main_pois:
        if poi[0].lower() == name:
            x, y = int(float(poi[1])), int(float(poi[2]))
            config['POI']['selected_poi'] = f"{poi[0]}, {x}, {y}"
            config['MAP']['last_selected_map'] = 'main'
            with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                config.write(configfile)
            return
    
    for poi in poi_data.landmarks:
        if poi[0].lower() == name:
            x, y = int(float(poi[1])), int(float(poi[2]))
            config['POI']['selected_poi'] = f"{poi[0]}, {x}, {y}"
            config['MAP']['last_selected_map'] = 'main'
            with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                config.write(configfile)
            return

    # If POI not found anywhere, set to none but preserve the map
    config['POI']['selected_poi'] = 'none, 0, 0'
    # Don't change the map if POI isn't found
    with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
        config.write(configfile)

def poi_sort_key(poi: Tuple[str, str, str]) -> Tuple[int, int, int, int]:
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
    name, x, y = poi
    x = int(float(x)) - ROI_START_ORIG[0]
    y = int(float(y)) - ROI_START_ORIG[1]
    width, height = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]
    
    quadrant = get_quadrant(x, y, width, height)
    position = get_position_in_quadrant(x, y, width // 2, height // 2)
    
    quadrant_names = ["top-left", "top-right", "bottom-left", "bottom-right"]
    return f"in the {position} of the {quadrant_names[quadrant]} quadrant"

# Constants
GAME_OBJECTS = [(name.replace('_', ' ').title(), "0", "0") for name in OBJECT_CONFIGS.keys()]
SPECIAL_POIS = [("Safe Zone", "0", "0"), ("Closest", "0", "0")]
CLOSEST_LANDMARK = ("Closest Landmark", "0", "0")
