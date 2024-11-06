from lib.guis.AccessibleUIBackend import AccessibleUIBackend
import pyautogui
import configparser
from typing import List, Tuple, Union, Dict
from lib.object_finder import OBJECT_CONFIGS
from lib.player_location import ROI_START_ORIG, ROI_END_ORIG, get_quadrant, get_position_in_quadrant
from lib.utilities import force_focus_window
import requests
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
from dataclasses import dataclass

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
    def __init__(self):
        self.REFERENCE_PAIRS = {
            (-75056, -87856): (631, 874),    # THE RIG
            (114368, 113456): (1397, 139),   # THE YACHT
            (61312, -22656): (900, 330),     # PLEASANT PARK
            (35136, -74992): (677, 440),     # SWEATY SANDS
            (-88320, 25856): (1063, 911),    # MISTY MEADOWS
            (-29696, -36096): (833, 688),    # WEEPING WOODS
            (-48384, 53184): (1167, 769),    # LAZY LAKE
            (-65536, -47680): (788, 826),    # SLURPY SWAMP
            (82880, 96064): (1333, 267),     # STEAMY STACKS
            (13568, 113920): (1397, 522)     # DIRTY DOCKS
        }
        self.transform_matrix = self._calculate_transformation_matrix()

    def _calculate_transformation_matrix(self) -> np.ndarray:
        world_coords = np.array([(x, y) for x, y in self.REFERENCE_PAIRS.keys()])
        screen_coords = np.array([coord for coord in self.REFERENCE_PAIRS.values()])
        world_coords_homogeneous = np.column_stack([world_coords, np.ones(len(world_coords))])
        transform_matrix, _, _, _ = np.linalg.lstsq(world_coords_homogeneous, screen_coords, rcond=None)
        return transform_matrix

    def world_to_screen(self, world_x: float, world_y: float) -> Tuple[int, int]:
        world_coord = np.array([world_x, world_y, 1])
        screen_coord = np.dot(world_coord, self.transform_matrix)
        return (int(round(screen_coord[0])), int(round(screen_coord[1])))

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
            self.api_data = None
            self.coordinate_system = CoordinateSystem()
            self._fetch_and_process_pois()
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

GAME_OBJECTS = [(name.replace('_', ' ').title(), "0", "0") for name in OBJECT_CONFIGS.keys()]
SPECIAL_POIS = [("Safe Zone", "0", "0"), ("Closest", "0", "0")]

def update_config_file(selected_poi_name: str, poi_data: POIData) -> None:
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    if 'POI' not in config:
        config['POI'] = {}

    # Handle "Closest Landmark" specifically
    if selected_poi_name.lower() == "closest landmark":
        config['POI']['selected_poi'] = "Closest Landmark, 0, 0"
    else:
        poi_entry = next(
            (poi for poi in poi_data.main_pois if poi[0].lower() == selected_poi_name.lower()),
            next(
                (poi for poi in poi_data.landmarks if poi[0].lower() == selected_poi_name.lower()),
                next(
                    (poi for poi in SPECIAL_POIS + GAME_OBJECTS 
                     if poi[0].lower() == selected_poi_name.lower()),
                    None
                )
            )
        )

        config['POI']['selected_poi'] = (
            f'{poi_entry[0]}, {poi_entry[1]}, {poi_entry[2]}'
            if poi_entry else 'none, 0, 0'
        )

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

def select_poi_tk(existing_poi_data: POIData = None) -> None:
    ui = AccessibleUIBackend("POI Selector")
    current_poi_set = [0]
    
    poi_data = existing_poi_data or POIData()
    favorites_manager = FavoritesManager()

    def show_remove_all_confirmation():
        confirmation = tk.messagebox.askyesno(
            "Removal Comfirmation",
            "Are you sure you want to remove all favorites?",
            parent=ui.root
        )
        if confirmation:
            favorites_manager.favorites = []
            favorites_manager.save_favorites()
            # Update the favorites tab content
            poi_sets[3] = ("Favorites", favorites_manager.get_favorites_as_tuples())
            if current_poi_set[0] == 3:  # If we're in the favorites tab
                set_poi_buttons(3)
            ui.speak("All favorites removed")
        else:
            ui.speak("Operation cancelled")


    # Add "Closest Landmark" to landmarks list
    CLOSEST_LANDMARK = ("Closest Landmark", "0", "0")

    poi_sets = [
        ("Main P O I's", SPECIAL_POIS + sorted(poi_data.main_pois, key=poi_sort_key)),
        ("Landmarks", [CLOSEST_LANDMARK] + sorted(poi_data.landmarks, key=poi_sort_key)),
        ("Game Objects", GAME_OBJECTS),
        ("Favorites", favorites_manager.get_favorites_as_tuples())
    ]

    def select_poi(poi: str) -> None:
        # Special handling for Closest Landmark
        if poi == "Closest Landmark":
            update_config_file(poi, poi_data)
            ui.speak("Closest Landmark selected")
            pyautogui.click()
            ui.root.destroy()
            return
    
        # Regular handling for other POIs
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
        pyautogui.click()
        ui.root.destroy()

    def should_speak_position(poi_set_index: int, poi: Tuple[str, str, str]) -> bool:
        if poi_set_index == 2:  # Game Objects
            return False
        if poi in SPECIAL_POIS or poi == CLOSEST_LANDMARK:
            return False
        return True

    def toggle_favorite(poi: Tuple[str, str, str], source_tab: str) -> None:
        is_added = favorites_manager.toggle_favorite(poi, source_tab)
        action = "added to" if is_added else "removed from"
        ui.speak(f"{poi[0]} {action} favorites")
        
        # Update the favorites tab content
        poi_sets[3] = ("Favorites", favorites_manager.get_favorites_as_tuples())
        if current_poi_set[0] == 3:  # If we're in the favorites tab
            set_poi_buttons(3)

    def create_poi_button(frame: ttk.Frame, poi: Union[Tuple[str, str, str], str], 
                         row: int, col: int, set_index: int) -> ttk.Button:
        button_text = poi[0] if isinstance(poi, tuple) else poi
        speech_text = f"{poi[0]}, {get_poi_position_description(poi)}" if should_speak_position(set_index, poi) else button_text
        
        button = ttk.Button(frame, text=button_text, command=lambda p=button_text: select_poi(p))
        button.grid(row=row, column=col, padx=2, pady=2, sticky='nsew')
        
        # Add favorite indicator if POI is favorited
        if isinstance(poi, tuple) and favorites_manager.is_favorite(poi[0]):
            button.configure(text=f"⭐ {button_text}")
        
        def on_focus(event, text=speech_text):
            ui.speak(text)
        button.bind('<FocusIn>', on_focus)
        
        return button

    def set_poi_buttons(index: int) -> None:
        ui.widgets["P O I's"] = []
        for widget in ui.tabs["P O I's"].winfo_children():
            widget.destroy()

        current_poi_set[0] = index
        set_name, pois_to_use = poi_sets[index]
        ui.speak(set_name)

        if not pois_to_use:
            ui.add_button(
                "P O I's",
                "No POIs available",
                lambda: None,
                custom_speech="No POIs available"
            )
            ui.speak("No P O Is available")
        else:
            frame = ttk.Frame(ui.tabs["P O I's"])
            frame.pack(expand=True, fill='both')

            if index in [1, 3]:  # Landmarks or Favorites
                buttons_per_row = 10
                for i, poi in enumerate(pois_to_use):
                    button = create_poi_button(frame, poi, i // buttons_per_row, i % buttons_per_row, index)
                    frame.grid_columnconfigure(i % buttons_per_row, weight=1)
                    ui.widgets["P O I's"].append(button)
            else:  # Main POIs and Game Objects
                for i, poi in enumerate(pois_to_use):
                    button_text = poi[0] if isinstance(poi, tuple) else poi
                    speech_text = f"{poi[0]}, {get_poi_position_description(poi)}" if should_speak_position(index, poi) else button_text
                    
                    if isinstance(poi, tuple) and favorites_manager.is_favorite(poi[0]):
                        button_text = f"⭐ {button_text}"
                    
                    ui.add_button(
                        "P O I's",
                        button_text,
                        lambda p=poi[0]: select_poi(p),
                        custom_speech=speech_text
                    )

            if isinstance(pois_to_use[0], tuple):
                if should_speak_position(index, pois_to_use[0]):
                    ui.speak(f"{pois_to_use[0][0]}, {get_poi_position_description(pois_to_use[0])}")
                else:
                    ui.speak(pois_to_use[0][0])
            else:
                ui.speak(pois_to_use[0])

    def cycle_poi_set(event) -> str:
        next_index = (
            current_poi_set[0] + (1 if not event.state & 0x1 else -1)
        ) % len(poi_sets)
        set_poi_buttons(next_index)
        return "break"

    def handle_favorite_key(event) -> None:
        focused = ui.root.focus_get()
        if isinstance(focused, ttk.Button):
            try:
                poi_text = focused['text'].replace('⭐ ', '')  # Remove star if present
                current_set = poi_sets[current_poi_set[0]]
                
                # Find the corresponding POI tuple
                poi = next((p for p in current_set[1] if isinstance(p, tuple) and p[0] == poi_text), None)
                if poi:
                    # Pass the tab name (current_set[0]) instead of the index
                    is_added = favorites_manager.toggle_favorite(poi, current_set[0])
                    # Update the star on the current button
                    focused.configure(text=f"⭐ {poi_text}" if is_added else poi_text)
                    # Update favorites tab content
                    poi_sets[3] = ("Favorites", favorites_manager.get_favorites_as_tuples())
                    
                    # If we're in the favorites tab, refresh it immediately
                    if current_poi_set[0] == 3:
                        set_poi_buttons(3)
                    
                    # Speak the action
                    action = "added to" if is_added else "removed from"
                    ui.speak(f"{poi_text} {action} favorites")
                    
            except tk.TclError:
                pass

    def handle_remove_all_favorites(event):
        if current_poi_set[0] == 3:  # Only in favorites tab
            show_remove_all_confirmation()
        return "break"

    ui.add_tab("P O I's")
    
    # Bind keyboard shortcuts
    ui.root.bind('<Tab>', cycle_poi_set)
    ui.root.bind('<Shift-Tab>', cycle_poi_set)
    ui.root.bind('f', handle_favorite_key)
    ui.root.bind('r', handle_remove_all_favorites)

    def initial_setup() -> None:
        force_focus_window(ui.root, "")
        # Use after() to ensure the window is fully loaded before setting POI buttons
        ui.root.after(100, lambda: set_poi_buttons(0))

    ui.root.after(100, initial_setup)
    ui.run()