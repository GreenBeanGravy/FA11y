"""
POI selector GUI for FA11y
Provides interface for selecting points of interest for navigation
"""
import os
import logging
import tkinter as tk
from tkinter import ttk, messagebox
import configparser
import json
import re
import requests
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Union, Set, Any, Callable

from lib.guis.base_ui import AccessibleUI
from lib.utilities import force_focus_window
from lib.player_location import ROI_START_ORIG, ROI_END_ORIG, get_quadrant, get_position_in_quadrant

# Initialize logger
logger = logging.getLogger(__name__)

# Constants
CONFIG_FILE = 'config.txt'
POI_TYPE = Union[Tuple[str, str, str], str]

class MapData:
    """Map data container"""
    def __init__(self, name, pois):
        self.name = name
        self.pois = pois

class POIData:
    """
    Adapter class to provide POI data in the format expected by the new UI.
    This bridges the gap between FA11y's POI handling and what the new UI expects.
    """
    def __init__(self):
        """Initialize with data from FA11y's expected locations"""
        self.main_pois = []
        self.landmarks = []
        self.maps = {}
        self.current_map = 'main'
        
        self.load_pois()
    
    def load_pois(self):
        """Load POIs from files"""
        # Load main POIs from pois.txt
        self.load_main_pois()
        
        # Load map-specific POIs
        self.load_map_pois()
        
        # Add main map to the maps dictionary
        self.maps['main'] = MapData('Main Map', self.main_pois)
    
    def load_main_pois(self):
        """Load main POIs from pois.txt"""
        try:
            with open('pois.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split('|')
                    if len(parts) == 3:
                        name = parts[0]
                        coords = parts[1].split(',')
                        game_coords = parts[2].split(',')
                        if len(coords) == 2 and len(game_coords) == 2:
                            # Convert coordinates
                            x, y = coords[0], coords[1]
                            self.main_pois.append((name, x, y))
        except FileNotFoundError:
            print("pois.txt not found")
        except Exception as e:
            print(f"Error loading main POIs: {e}")
    
    def load_map_pois(self):
        """Load map-specific POIs"""
        try:
            import os
            maps_dir = 'maps'
            if os.path.exists(maps_dir):
                for filename in os.listdir(maps_dir):
                    if filename.endswith('.txt') and filename.startswith('map_'):
                        # Keep the original filename as the key (without .txt)
                        map_key = filename[:-4]  # Remove .txt suffix
                        
                        # Create a display name by removing 'map_' and '_pois', and formatting
                        display_name = map_key[4:].replace('_pois', '')
                        display_name = display_name.replace('_', ' ').title()
                        
                        map_pois = []
                        
                        with open(os.path.join(maps_dir, filename), 'r', encoding='utf-8') as f:
                            for line in f:
                                parts = line.strip().split(',')
                                if len(parts) == 3:
                                    name, x, y = parts[0], parts[1], parts[2]
                                    map_pois.append((name, x, y))
                        
                        # Create map data object
                        self.maps[map_key] = MapData(display_name, map_pois)
        except Exception as e:
            print(f"Error loading map POIs: {e}")
    
    def get_current_map(self):
        """Get current map from config"""
        try:
            import configparser
            config = configparser.ConfigParser()
            config.read('config.txt')
            map_value = config.get('POI', 'current_map', fallback='main')
            
            # If it's not 'main', check if it matches any map key
            if map_value != 'main':
                # First try with direct match
                if map_value in self.maps:
                    self.current_map = map_value
                # Then try with map_X format
                elif f"map_{map_value}" in self.maps:
                    self.current_map = f"map_{map_value}"
                # Finally, try with map_X_pois format
                elif f"map_{map_value}_pois" in self.maps:
                    self.current_map = f"map_{map_value}_pois"
                # For backward compatibility with space-separated names (like "o g")
                else:
                    for map_key in self.maps.keys():
                        if map_key.startswith('map_') and map_key.endswith('_pois'):
                            # Extract the middle portion and replace underscores with spaces
                            middle = map_key[4:-5].replace('_', ' ')
                            if middle == map_value:
                                self.current_map = map_key
                                break
        except Exception as e:
            print(f"Error getting current map: {e}")
    
    def get_map_names(self):
        """Get list of available map names"""
        return list(self.maps.keys())

@dataclass
class FavoritePOI:
    """Favorite POI data container"""
    name: str
    x: str
    y: str
    source_tab: str

class FavoritesManager:
    """Manages favorite POIs"""
    
    def __init__(self, filename: str = "fav_pois.txt"):
        """Initialize the favorites manager
        
        Args:
            filename: Path to favorites file
        """
        self.filename = filename
        self.favorites: List[FavoritePOI] = []
        self.load_favorites()

    def load_favorites(self) -> None:
        """Load favorites from file"""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    data = json.load(f)
                    self.favorites = [FavoritePOI(**poi) for poi in data]
            except json.JSONDecodeError:
                logger.error("Error loading favorites file. Starting with empty favorites.")
                self.favorites = []
        else:
            self.favorites = []

    def save_favorites(self) -> None:
        """Save favorites to file"""
        with open(self.filename, 'w') as f:
            json.dump([vars(poi) for poi in self.favorites], f, indent=2)

    def toggle_favorite(self, poi: Tuple[str, str, str], source_tab: str) -> bool:
        """Toggle favorite status for a POI
        
        Args:
            poi: POI data tuple (name, x, y)
            source_tab: Source tab name
            
        Returns:
            bool: True if added, False if removed
        """
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
        """Check if a POI is a favorite
        
        Args:
            poi_name: POI name
            
        Returns:
            bool: True if favorite, False otherwise
        """
        return any(f.name == poi_name for f in self.favorites)

    def get_favorites_as_tuples(self) -> List[Tuple[str, str, str]]:
        """Get favorites as tuples
        
        Returns:
            list: List of POI tuples (name, x, y)
        """
        return [(f.name, f.x, f.y) for f in self.favorites]

    def get_source_tab(self, poi_name: str) -> Optional[str]:
        """Get source tab for a favorite POI
        
        Args:
            poi_name: POI name
            
        Returns:
            str or None: Source tab name or None if not found
        """
        fav = next((f for f in self.favorites if f.name == poi_name), None)
        return fav.source_tab if fav else None
        
    def remove_all_favorites(self) -> None:
        """Remove all favorites"""
        self.favorites = []
        self.save_favorites()

class POIGUI(AccessibleUI):
    """POI selector GUI"""
    
    def __init__(self, poi_data, config_file: str = CONFIG_FILE):
        """Initialize the POI selector GUI
        
        Args:
            poi_data: POI data manager
            config_file: Path to config file
        """
        super().__init__(title="POI Selector")
        
        self.poi_data = poi_data
        self.config_file = config_file
        
        # Load current map from config
        config = configparser.ConfigParser()
        config.read(CONFIG_FILE)
        self.current_map = config.get('POI', 'current_map', fallback='main')
        
        # Convert clean map name back to file format if needed
        if self.current_map != 'main' and f"{self.current_map}_" in self.poi_data.maps:
            self.current_map = f"{self.current_map}_"
        
        if self.current_map not in self.poi_data.maps:
            self.current_map = 'main'
        
        # Create mutable reference for current map and POI set
        self.current_map_ref = [self.current_map]
        self.current_poi_set = [0]
        
        # Initialize favorites manager
        self.favorites_manager = FavoritesManager()
        
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
        from lib.object_finder import OBJECT_CONFIGS
        
        # Constants
        GAME_OBJECTS = [(name.replace('_', ' ').title(), "0", "0") for name in OBJECT_CONFIGS.keys()]
        SPECIAL_POIS = [("Safe Zone", "0", "0"), ("Closest", "0", "0")]
        CLOSEST_LANDMARK = ("Closest Landmark", "0", "0")
        
        if self.current_map_ref[0] == "main":
            return [
                ("Main P O I's", SPECIAL_POIS + sorted(self.poi_data.main_pois, key=self.poi_sort_key)),
                ("Landmarks", [CLOSEST_LANDMARK] + sorted(self.poi_data.landmarks, key=self.poi_sort_key)),
                ("Game Objects", GAME_OBJECTS),
                ("Custom P O I's", self.load_custom_pois()),
                ("Favorites", self.favorites_manager.get_favorites_as_tuples())
            ]
        else:
            current_map_name = self.poi_data.maps[self.current_map_ref[0]].name
            return [
                (f"{current_map_name} P O I's", SPECIAL_POIS + sorted(self.poi_data.maps[self.current_map_ref[0]].pois, key=self.poi_sort_key)),
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
    
    def load_custom_pois(self) -> List[Tuple[str, str, str]]:
        """Load custom POIs from file
        
        Returns:
            list: List of POI tuples (name, x, y)
        """
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
                logger.error(f"Error loading custom POIs: {e}")
        return sorted(custom_pois, key=self.poi_sort_key)
    
    def should_speak_position(self, poi_set_index: int, poi: Tuple[str, str, str]) -> bool:
        """Determine if position should be spoken for a POI
        
        Args:
            poi_set_index: Index of the POI set
            poi: POI data tuple
            
        Returns:
            bool: True if position should be spoken, False otherwise
        """
        # Don't speak positions for game objects
        if poi_set_index == 2:
            return False
        
        # Don't speak positions for special POIs
        SPECIAL_POIS = [("Safe Zone", "0", "0"), ("Closest", "0", "0")]
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
            no_poi_message = "No custom POIs set" if index == 3 else "No POIs available"
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

        if index in [1, 3, 4]:  # Landmarks, Custom POIs, or Favorites
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
        """Handle POI selection and update configuration
        
        Args:
            poi: POI name
        """
        # Update the current map in POIData
        self.poi_data.current_map = self.current_map_ref[0]
    
        # Handle special POIs first
        if poi.lower() in ["closest", "safe zone", "closest landmark"]:
            special_poi_map = {
                "closest": "Closest",
                "closest landmark": "Closest Landmark",
                "safe zone": "Safe Zone"
            }
            actual_name = special_poi_map.get(poi.lower(), poi)
            
            config = configparser.ConfigParser()
            config.read(self.config_file)
            if 'POI' not in config.sections():
                config.add_section('POI')
            config.set('POI', 'selected_poi', f"{actual_name}, 0, 0")
            config.set('POI', 'current_map', self.current_map_ref[0].replace('_', ''))
            with open(self.config_file, 'w') as f:
                config.write(f)
            
            self.speak(f"{actual_name} selected")
            self.close()
            return
    
        # Handle selecting a favorite POI
        source_tab = self.favorites_manager.get_source_tab(poi)
        if source_tab:
            for set_name, pois in self.poi_sets:
                if set_name == source_tab:
                    for original_poi in pois:
                        if isinstance(original_poi, tuple) and original_poi[0] == poi:
                            self.update_config_file(poi)
                            break
        else:
            self.update_config_file(poi)
    
        self.speak(f"{poi} selected")
        self.close()
    
    def handle_favorite_key(self, event) -> None:
        """Handle pressing the favorite key for a POI
        
        Args:
            event: Key event
        """
        focused = self.root.focus_get()
        if isinstance(focused, ttk.Button):
            try:
                poi_text = focused['text'].replace('⭐ ', '')
                current_set = self.poi_sets[self.current_poi_set[0]]
                
                poi = next((p for p in current_set[1] if isinstance(p, tuple) and p[0] == poi_text), None)
                if poi:
                    # Toggle favorite status
                    is_added = self.favorites_manager.toggle_favorite(poi, current_set[0])
                    
                    # Update button text
                    focused.configure(text=f"⭐ {poi_text}" if is_added else poi_text)
                    
                    # Update favorites list
                    self.poi_sets[4] = ("Favorites", self.favorites_manager.get_favorites_as_tuples())
                    
                    # Refresh favorites tab if currently viewing it
                    if self.current_poi_set[0] == 4:
                        self.set_poi_buttons(4)
                    
                    # Announce action
                    action = "added to" if is_added else "removed from"
                    self.speak(f"{poi_text} {action} favorites")
                    
            except tk.TclError:
                pass
    
    def handle_remove_all_favorites(self, event) -> str:
        """Handle the remove all favorites key press
        
        Args:
            event: Key event
            
        Returns:
            str: "break" to prevent default handling
        """
        if self.current_poi_set[0] == 4:  # Only when in favorites tab
            self.show_remove_all_confirmation()
        return "break"
    
    def show_remove_all_confirmation(self) -> None:
        """Show confirmation dialog for removing all favorites"""
        confirmation = messagebox.askyesno(
            "Remove All Favorites",
            "Are you sure you want to remove all favorites?",
            parent=self.root
        )
        if confirmation:
            self.favorites_manager.remove_all_favorites()
            self.poi_sets[4] = ("Favorites", [])
            
            # Refresh favorites tab if currently viewing it
            if self.current_poi_set[0] == 4:
                self.set_poi_buttons(4)
                
            self.speak("All favorites removed")
        else:
            self.speak("Operation cancelled")
    
    def cycle_poi_set(self, event) -> str:
        """Handle cycling between POI sets
        
        Args:
            event: Key event
            
        Returns:
            str: "break" to prevent default handling
        """
        next_index = (
            self.current_poi_set[0] + (1 if not event.state & 0x1 else -1)
        ) % len(self.poi_sets)
        self.set_poi_buttons(next_index)
        return "break"
    
    def focus_first_widget(self) -> None:
        """Focus the first widget and announce its state"""
        if self.widgets["P O I's"]:
            first_widget = self.widgets["P O I's"][0]
            first_widget.focus_set()
            widget_info = self.get_widget_info(first_widget)
            if widget_info:
                self.speak(widget_info)
    
    def update_config_file(self, selected_poi_name: str) -> None:
        """Update configuration file with selected POI
        
        Args:
            selected_poi_name: Selected POI name
        """
        try:
            config = configparser.ConfigParser()
            config.read(self.config_file)
            
            logger.info(f"Updating configuration for POI: {selected_poi_name}")
            
            # Ensure POI section exists
            if 'POI' not in config.sections():
                config.add_section('POI')
                
            # Update current map in config with the correct format
            current_map = self.current_map_ref[0]
            
            # Store the map identifier in a format that can be correctly resolved later
            if current_map == 'main':
                config.set('POI', 'current_map', 'main')
            elif current_map.startswith('map_') and current_map.endswith('_pois'):
                # Extract the middle part, preserving underscores
                map_id = current_map[4:-5]
                config.set('POI', 'current_map', map_id)
            else:
                # Fallback if the format is unexpected
                config.set('POI', 'current_map', current_map)
            
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
            if not poi_entry and os.path.exists('CUSTOM_POI.txt'):
                try:
                    with open('CUSTOM_POI.txt', 'r', encoding='utf-8') as f:
                        for line in f:
                            parts = line.strip().split(',')
                            if len(parts) == 3 and parts[0].lower() == selected_poi_name.lower():
                                poi_entry = tuple(parts)
                                break
                except Exception as e:
                    logger.error(f"Error reading custom POIs: {e}")
    
            # Check game objects if still not found
            if not poi_entry:
                from lib.object_finder import OBJECT_CONFIGS
                GAME_OBJECTS = [(name.replace('_', ' ').title(), "0", "0") for name in OBJECT_CONFIGS.keys()]
                
                poi_entry = next(
                    (poi for poi in GAME_OBJECTS 
                     if poi[0].lower() == selected_poi_name.lower()),
                    None
                )
    
            # Save the POI entry
            if poi_entry:
                config.set('POI', 'selected_poi', f"{poi_entry[0]}, {poi_entry[1]}, {poi_entry[2]}")
            else:
                config.set('POI', 'selected_poi', "none, 0, 0")
                
            with open(self.config_file, 'w') as f:
                config.write(f)
                
        except Exception as e:
            logger.error(f"Error updating configuration: {e}")
            self.speak("Error updating configuration")
        
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


def launch_poi_selector(poi_data) -> None:
    """Launch the POI selector GUI
    
    Args:
        poi_data: POI data manager
    """
    try:
        gui = POIGUI(poi_data)
        gui.run()
    except Exception as e:
        logger.error(f"Error launching POI selector GUI: {e}")
