import os
import sys
import configparser
import threading
import time
import pyautogui
import subprocess
import win32com.client
import requests
import json
import numpy as np
import warnings
from typing import List, Tuple, Optional, Dict, Any, Union

# Suppress pkg_resources deprecation warnings from external libraries
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*", category=UserWarning)

# Check Python version requirement
if sys.version_info < (3, 8):
    print("Error: Python 3.8 or higher is required.")
    input("Press Enter to exit...")
    sys.exit(1)

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import pygame
import win32api
import win32con
import winshell

# Set the command window title
os.system("title FA11y")

# Check Python version and create mock imp if necessary
if sys.version_info >= (3, 12):
    class MockImp:
        __name__ = 'imp'

        @staticmethod
        def is_frozen(arg=None):
            if arg == "__main__":
                return hasattr(sys, "frozen") or '__compiled__' in globals()
            return hasattr(sys, 'frozen') or hasattr(sys, 'importers') or getattr(sys, 'frozen', False)

    sys.modules['imp'] = MockImp()

from accessible_output2.outputs.auto import Auto
from lib.hsr import (
    check_health_shields,
    check_rarity,
)
from lib.mouse import (
    smooth_move_mouse,
    left_mouse_down,
    left_mouse_up,
    right_mouse_down,
    right_mouse_up,
    mouse_scroll,
)

from lib.guis.poi_selector_gui import POIData, launch_poi_selector
from lib.exit_match import exit_match
from lib.height_checker import start_height_checker
from lib.background_checks import monitor
from lib.material_monitor import material_monitor
from lib.resource_monitor import resource_monitor
from lib.gameobject_monitor import gameobject_monitor
from lib.storm_monitor import storm_monitor
from lib.player_position import (
    announce_current_direction as speak_minimap_direction, 
    start_icon_detection, 
    check_for_pixel,
    ROI_START_ORIG,
    ROI_END_ORIG,
    get_quadrant,
    get_position_in_quadrant,
    cleanup_object_detection
)
from lib.hotbar_detection import (
    initialize_hotbar_detection,
    detect_hotbar_item,
    announce_ammo_manually,
)
from lib.inventory_handler import inventory_handler
from lib.utilities import (
    get_config_int,
    get_config_float,
    get_config_value,
    get_config_boolean,
    read_config,
    Config,
    get_default_config_value_string,
    get_gameobject_configs,
    clear_config_cache,
    save_config
)
from lib.input_handler import is_key_pressed, get_pressed_key, is_numlock_on, VK_KEYS
from lib.custom_poi_handler import load_custom_pois

# Initialize pygame mixer and load sounds
pygame.mixer.init()
update_sound = pygame.mixer.Sound("sounds/update.ogg")

# GitHub repository configuration
GITHUB_REPO_URL = "https://raw.githubusercontent.com/GreenBeanGravy/FA11y/main"
VERSION_URL = f"{GITHUB_REPO_URL}/VERSION"
CHANGELOG_URL = f"{GITHUB_REPO_URL}/CHANGELOG.txt"

speaker = Auto()
key_state = {}
action_handlers = {}
config = None
key_bindings = {}
key_listener_thread = None
stop_key_listener = threading.Event()
config_gui_open = threading.Event()
keybinds_enabled = True
poi_data_instance = None

# POI category definitions
POI_CATEGORY_SPECIAL = "special"
POI_CATEGORY_REGULAR = "regular"
POI_CATEGORY_LANDMARK = "landmark"
POI_CATEGORY_FAVORITE = "favorite"
POI_CATEGORY_CUSTOM = "custom"
POI_CATEGORY_GAMEOBJECT = "gameobject"

# Special POI names
SPECIAL_POI_CLOSEST = "closest"
SPECIAL_POI_SAFEZONE = "safe zone"
SPECIAL_POI_CLOSEST_LANDMARK = "closest landmark"
SPECIAL_POI_CLOSEST_GAMEOBJECT = "closest game object"

# Global variable to track current POI category
current_poi_category = POI_CATEGORY_SPECIAL

def handle_movement(action: str, reset_sensitivity: bool) -> None:
    """Handle all movement-related actions."""
    global config
    turn_sensitivity = get_config_int(config, 'TurnSensitivity', 100)
    secondary_turn_sensitivity = get_config_int(config, 'SecondaryTurnSensitivity', 50)
    turn_delay = get_config_float(config, 'TurnDelay', 0.01)
    turn_steps = get_config_int(config, 'TurnSteps', 5)
    recenter_delay = get_config_float(config, 'RecenterDelay', 0.05)
    recenter_steps = get_config_int(config, 'RecenterSteps', 10)
    recenter_step_delay = get_config_float(config, 'RecenterStepDelay', 0) / 1000.0
    recenter_step_speed = get_config_int(config, 'RecenterStepSpeed', 0)
    up_down_sensitivity = turn_sensitivity // 2
    x_move, y_move = 0, 0

    if action in ['turn left', 'turn right', 'secondary turn left', 'secondary turn right', 'look up', 'look down']:
        if 'secondary' in action:
            sensitivity = secondary_turn_sensitivity
        elif action in ['look up', 'look down']:
            sensitivity = up_down_sensitivity
        else:
            sensitivity = turn_sensitivity

        if 'left' in action:
            x_move = -sensitivity
        elif 'right' in action:
            x_move = sensitivity
        elif action == 'look up':
            y_move = -sensitivity
        elif action == 'look down':
            y_move = sensitivity

        smooth_move_mouse(x_move, y_move, turn_delay, turn_steps)
        return

    elif action == 'turn around':
        x_move = get_config_int(config, 'TurnAroundSensitivity', 1158)
        smooth_move_mouse(x_move, 0, turn_delay, turn_steps)
        return
    elif action == 'recenter':
        if reset_sensitivity:
            recenter_move = get_config_int(config, 'ResetRecenterLookDown', 1500)
            down_move = get_config_int(config, 'ResetRecenterLookUp', -580)
        else:
            recenter_move = get_config_int(config, 'RecenterLookDown', 1500)
            down_move = get_config_int(config, 'RecenterLookUp', -820)

        smooth_move_mouse(0, recenter_move, recenter_step_delay, recenter_steps, recenter_step_speed, down_move, recenter_delay)
        speaker.speak("Reset Camera")
        return

    smooth_move_mouse(x_move, y_move, recenter_delay)

def handle_scroll(action: str) -> None:
    """Handle scroll wheel actions."""
    global config
    scroll_sensitivity = get_config_int(config, 'ScrollSensitivity', 120)
    if action == 'scroll down':
        scroll_sensitivity = -scroll_sensitivity
    mouse_scroll(scroll_sensitivity)

def reload_config() -> None:
    """Reload configuration and update action handlers with thread safety"""
    global config, action_handlers, key_bindings, poi_data_instance, current_poi_category
    
    try:
        # Use thread-safe config reading with cache clearing to ensure fresh read
        clear_config_cache()
        config = read_config(use_cache=False)

        # Initialize POI data if not already done
        if poi_data_instance is None:
            print("Initializing POI data...")
            poi_data_instance = POIData()

        # Initialize or update current_poi_category based on selected POI
        selected_poi_str = config.get('POI', 'selected_poi', fallback='closest, 0, 0')
        selected_poi_parts = selected_poi_str.split(',')
        selected_poi_name = selected_poi_parts[0].strip()
        current_poi_category = get_poi_category(selected_poi_name)

        # Validate keybinds and reset if necessary
        config_updated = False
        temp_key_bindings_from_config = {key.lower(): get_config_value(config, key)[0].lower()
                                         for key in config['Keybinds'] if get_config_value(config, key)[0]}

        validated_key_bindings = {}
        for action, key_str in temp_key_bindings_from_config.items():
            if not key_str: # Allow empty keybinds (disabled)
                validated_key_bindings[action] = key_str
                continue

            key_lower = key_str.lower()
            valid_key = False
            if key_lower in VK_KEYS:
                valid_key = True
            else:
                try:
                    # Check if it's a single character A-Z, 0-9, or other direct ASCII map
                    vk_code = ord(key_str.upper())
                    if 'a' <= key_lower <= 'z' or '0' <= key_lower <= '9':
                         valid_key = True
                    elif key_lower in [',', '.', '/', '\'', ';', '[', ']', '\\', '`', '-','=']: # common punctuation
                        valid_key = True

                except (TypeError, ValueError):
                    valid_key = False
            
            if valid_key:
                validated_key_bindings[action] = key_str
            else:
                speaker.speak(f"Unrecognized key '{key_str}' for action '{action}'. Resetting to default.")
                print(f"Warning: Unrecognized key '{key_str}' for action '{action}'. Resetting to default.")
                
                default_value_string = get_default_config_value_string('Keybinds', action)
                if default_value_string is not None:
                    config['Keybinds'][action] = default_value_string
                    default_key_part = default_value_string.split('"')[0].strip()
                    validated_key_bindings[action] = default_key_part.lower()
                else:
                    config['Keybinds'][action] = f" \"{get_config_value(config, action)[1]}\"" # Keep description
                    validated_key_bindings[action] = ""
                config_updated = True

        if config_updated:
            # Use thread-safe config saving
            success = save_config(config)
            if success:
                print("Configuration updated with default values for invalid keys.")
            else:
                print("Warning: Could not save updated configuration")

        key_bindings = validated_key_bindings

        mouse_keys_enabled = get_config_boolean(config, 'MouseKeys', True)
        reset_sensitivity = get_config_boolean(config, 'ResetSensitivity', False)

        action_handlers.clear()

        action_handlers['start navigation'] = lambda: start_icon_detection(use_ppi=check_for_pixel())

        if mouse_keys_enabled:
            action_handlers.update({
                'fire': left_mouse_down,
                'target': right_mouse_down,
                'turn left': lambda: handle_movement('turn left', reset_sensitivity),
                'turn right': lambda: handle_movement('turn right', reset_sensitivity),
                'secondary turn left': lambda: handle_movement('secondary turn left', reset_sensitivity),
                'secondary turn right': lambda: handle_movement('secondary turn right', reset_sensitivity),
                'look up': lambda: handle_movement('look up', reset_sensitivity),
                'look down': lambda: handle_movement('look down', reset_sensitivity),
                'turn around': lambda: handle_movement('turn around', reset_sensitivity),
                'recenter': lambda: handle_movement('recenter', reset_sensitivity),
                'scroll up': lambda: handle_scroll('scroll up'),
                'scroll down': lambda: handle_scroll('scroll down')
            })

        action_handlers.update({
            'announce direction faced': speak_minimap_direction,
            'check health shields': check_health_shields,
            'check rarity': check_rarity,
            'open p o i selector': open_poi_selector,
            'open gamemode selector': open_gamemode_selector,
            'open configuration menu': open_config_gui,
            'exit match': exit_match,
            'create custom p o i': handle_custom_poi_gui,
            'announce ammo': announce_ammo_manually,
            'toggle keybinds': toggle_keybinds,
            'cycle map': cycle_map,
            'cycle poi': cycle_poi,
            'cycle poi category': cycle_poi_category,
        })

        for i in range(1, 6):
            action_handlers[f'detect hotbar {i}'] = lambda slot=i-1: detect_hotbar_item(slot)
            
    except Exception as e:
        print(f"Error reloading config: {e}")
        speaker.speak("Error reloading configuration")

def toggle_keybinds() -> None:
    """Toggle keybinds on/off."""
    global keybinds_enabled
    keybinds_enabled = not keybinds_enabled
    state = 'enabled' if keybinds_enabled else 'disabled'
    speaker.speak(f"FA11y {state}")
    print(f"FA11y has been {state}.")

def key_listener() -> None:
    """Listen for and handle key presses."""
    global key_bindings, key_state, action_handlers, stop_key_listener, config_gui_open, keybinds_enabled, config
    while not stop_key_listener.is_set():
        if not config_gui_open.is_set():
            numlock_on = is_numlock_on()
            if config is None:
                time.sleep(0.1)
                continue

            mouse_keys_enabled = get_config_boolean(config, 'MouseKeys', True)

            for action, key_str in key_bindings.items():
                if not key_str:
                    continue

                key_pressed = is_key_pressed(key_str)
                action_lower = action.lower()

                if action_lower not in action_handlers:
                    continue

                if not keybinds_enabled and action_lower != 'toggle keybinds':
                    continue

                if not mouse_keys_enabled and action_lower in [
                    'fire', 'target', 'turn left', 'turn right',
                    'secondary turn left', 'secondary turn right',
                    'look up', 'look down', 'turn around', 'recenter',
                    'scroll up', 'scroll down'
                ]:
                    continue

                ignore_numlock = get_config_boolean(config, 'IgnoreNumlock', False)
                if action_lower in ['fire', 'target'] and not (ignore_numlock or numlock_on):
                    continue
                
                if key_pressed != key_state.get(key_str, False):
                    key_state[key_str] = key_pressed
                    if key_pressed:
                        action_handler = action_handlers.get(action_lower)
                        if action_handler:
                            try:
                                action_handler()
                            except Exception as e:
                                print(f"Error executing action {action_lower}: {e}")
                    else:
                        if action_lower in ['fire', 'target']:
                            (left_mouse_up if action_lower == 'fire' else right_mouse_up)()
        
        time.sleep(0.001)

def create_desktop_shortcut() -> None:
    """Create a desktop shortcut for FA11y."""
    desktop = winshell.desktop()
    path = os.path.join(desktop, "FA11y.lnk")
    target = os.path.abspath(sys.argv[0])
    wDir = os.path.dirname(target)

    shell = win32com.client.Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(path)
    shortcut.Targetpath = target
    shortcut.WorkingDirectory = wDir
    shortcut.save()

def update_script_config(new_config: configparser.ConfigParser) -> None:
    """Update script configuration and restart key listener with safe operations"""
    global config, key_listener_thread, stop_key_listener
    
    try:
        # Use thread-safe config saving
        clear_config_cache()
        
        # Save the new config
        success = save_config(new_config)
        if not success:
            print("Warning: Could not save updated config")
            speaker.speak("Warning: Could not save configuration")
            return
        
        # Clear cache and reload
        clear_config_cache()
        config = read_config(use_cache=False)
        reload_config()

        # Restart key listener
        if key_listener_thread and key_listener_thread.is_alive():
            stop_key_listener.set()
            key_listener_thread.join()
        
        stop_key_listener.clear()
        key_listener_thread = threading.Thread(target=key_listener, daemon=True)
        key_listener_thread.start()
        
    except Exception as e:
        print(f"Error updating script config: {e}")
        speaker.speak("Error updating configuration")

def open_config_gui() -> None:
    """Open the configuration GUI."""
    config_gui_open.set()
    from lib.guis.config_gui import launch_config_gui
    
    global config
    config_instance = Config()
    config_instance.config = config

    def update_callback(updated_config_parser):
        global config
        config = updated_config_parser
        
        with open('config.txt', 'w') as f:
            config.write(f)
            
        reload_config()
        
        # Notify monitors of config changes
        if gameobject_monitor.running:
            pass
        if storm_monitor.running:
            pass
            
        print("Configuration updated and saved to disk")
    
    launch_config_gui(config_instance, update_callback)
    config_gui_open.clear()

def open_poi_selector() -> None:
    """Open the POI selector GUI with safe config handling"""
    try:
        from lib.guis.poi_selector_gui import launch_poi_selector
        
        global poi_data_instance, current_poi_category, config
        
        if poi_data_instance is None:
            poi_data_instance = POIData()
        
        # Store original state for comparison
        original_config = read_config(use_cache=False)
        original_poi = original_config.get('POI', 'selected_poi', fallback='closest, 0, 0')
        original_map = original_config.get('POI', 'current_map', fallback='main')
        
        # Launch the POI selector GUI
        launch_poi_selector(poi_data_instance)
        
        # Check if configuration changed after GUI closes
        # Use fresh read to ensure we get any changes
        clear_config_cache()
        updated_config = read_config(use_cache=False)
        updated_poi = updated_config.get('POI', 'selected_poi', fallback='closest, 0, 0')
        updated_map = updated_config.get('POI', 'current_map', fallback='main')
        
        # If the configuration changed, update our internal state
        if original_poi != updated_poi or original_map != updated_map:
            # Get the selected POI name
            selected_poi_parts = updated_poi.split(',')
            selected_poi_name = selected_poi_parts[0].strip()
            
            # Update the current_poi_category based on the selected POI
            updated_category = get_poi_category(selected_poi_name)
            current_poi_category = updated_category
            
            print(f"POI selection updated from GUI: {selected_poi_name} (Category: {updated_category})")
            
            # Update our global config reference
            config = updated_config
        else:
            print("No POI configuration changes detected")
            
    except Exception as e:
        print(f"Error opening POI selector: {e}")
        speaker.speak("Error opening POI selector")

def handle_custom_poi_gui(use_ppi=False) -> None:
    """Handle custom POI GUI creation with map-specific support"""
    from lib.guis.custom_poi_gui import launch_custom_poi_creator
    
    global config
    current_map = config.get('POI', 'current_map', fallback='main')
    
    use_ppi = check_for_pixel()
    
    class PlayerDetector:
        def get_player_position(self, use_ppi_flag):
            from lib.player_position import find_player_position as find_map_player_pos, find_player_icon_location
            return find_map_player_pos() if use_ppi_flag else find_player_icon_location()
    
    launch_custom_poi_creator(use_ppi, PlayerDetector(), current_map)

def open_gamemode_selector() -> None:
    """Open the gamemode selector GUI."""
    from lib.guis.gamemode_gui import launch_gamemode_selector
    launch_gamemode_selector()

def get_poi_category(poi_name: str) -> str:
    """
    Determine which category a POI belongs to.
    
    Args:
        poi_name: Name of the POI
        
    Returns:
        str: Category identifier
    """
    global poi_data_instance, config
    
    # Get the current map
    current_map = config.get('POI', 'current_map', fallback='main')
    
    # Check special POIs first
    if poi_name.lower() == SPECIAL_POI_CLOSEST.lower():
        return POI_CATEGORY_SPECIAL
    
    if poi_name.lower() == SPECIAL_POI_SAFEZONE.lower():
        return POI_CATEGORY_SPECIAL
    
    if poi_name.lower() == SPECIAL_POI_CLOSEST_LANDMARK.lower() and current_map == 'main':
        return POI_CATEGORY_SPECIAL
    
    if poi_name.lower() == SPECIAL_POI_CLOSEST_GAMEOBJECT.lower():
        return POI_CATEGORY_SPECIAL
    
    # Check favorites
    favorites_file = 'FAVORITE_POIS.txt'
    if os.path.exists(favorites_file):
        try:
            with open(favorites_file, 'r') as f:
                favorites_data = json.load(f)
                if any(f['name'].lower() == poi_name.lower() for f in favorites_data):
                    return POI_CATEGORY_FAVORITE
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    
    # Check custom POIs
    custom_pois = load_custom_pois(current_map)
    if any(poi[0].lower() == poi_name.lower() for poi in custom_pois):
        return POI_CATEGORY_CUSTOM
    
    # Check game objects
    from lib.object_finder import OBJECT_CONFIGS
    game_objects = [(name.replace('_', ' ').title(), "0", "0") for name in OBJECT_CONFIGS.keys()]
    if any(poi[0].lower() == poi_name.lower() for poi in game_objects):
        return POI_CATEGORY_GAMEOBJECT
    
    # Check landmarks (main map only)
    if current_map == 'main':
        if any(poi[0].lower() == poi_name.lower() for poi in poi_data_instance.landmarks):
            return POI_CATEGORY_LANDMARK
    
    # Default to regular
    return POI_CATEGORY_REGULAR

def get_pois_by_category(category: str) -> List[Tuple[str, str, str]]:
    """
    Get all POIs in a specific category.
    
    Args:
        category: POI category
        
    Returns:
        list: List of POI tuples (name, x, y)
    """
    global poi_data_instance, config
    
    current_map = config.get('POI', 'current_map', fallback='main')
    
    # Special POIs
    if category == POI_CATEGORY_SPECIAL:
        special_pois = [(SPECIAL_POI_CLOSEST, "0", "0"), (SPECIAL_POI_SAFEZONE, "0", "0"), (SPECIAL_POI_CLOSEST_GAMEOBJECT, "0", "0")]
        if current_map == 'main':
            special_pois.append((SPECIAL_POI_CLOSEST_LANDMARK, "0", "0"))
        return special_pois
    
    # Favorites
    if category == POI_CATEGORY_FAVORITE:
        favorites_file = 'FAVORITE_POIS.txt'
        if os.path.exists(favorites_file):
            try:
                with open(favorites_file, 'r') as f:
                    favorites_data = json.load(f)
                    return [(f['name'], f['x'], f['y']) for f in favorites_data]
            except (json.JSONDecodeError, FileNotFoundError):
                return []
        return []
    
    # Custom POIs
    if category == POI_CATEGORY_CUSTOM:
        return load_custom_pois(current_map)
    
    # Game Objects
    if category == POI_CATEGORY_GAMEOBJECT:
        from lib.object_finder import OBJECT_CONFIGS
        return [(name.replace('_', ' ').title(), "0", "0") for name in OBJECT_CONFIGS.keys()]
    
    # Landmarks (main map only)
    if category == POI_CATEGORY_LANDMARK and current_map == 'main':
        return poi_data_instance.landmarks
    
    # Regular POIs
    if category == POI_CATEGORY_REGULAR:
        if current_map == 'main':
            return poi_data_instance.main_pois
        elif current_map in poi_data_instance.maps:
            return poi_data_instance.maps[current_map].pois
    
    return []

def sort_pois_by_position(pois: List[Tuple[str, str, str]]) -> List[Tuple[str, str, str]]:
    """
    Sort POIs by their position on the map.
    
    Args:
        pois: List of POI tuples
        
    Returns:
        list: Sorted list of POI tuples
    """
    def poi_sort_key(poi: Tuple[str, str, str]) -> Tuple[int, int, int, int]:
        name, x_str, y_str = poi
        try:
            x = int(float(x_str)) - ROI_START_ORIG[0]
            y = int(float(y_str)) - ROI_START_ORIG[1]
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
    
    if not pois:
        return []
    
    # Don't sort special POIs or game objects
    if pois[0][0].lower() in [SPECIAL_POI_CLOSEST.lower(), SPECIAL_POI_SAFEZONE.lower(), SPECIAL_POI_CLOSEST_LANDMARK.lower(), SPECIAL_POI_CLOSEST_GAMEOBJECT.lower()]:
        return pois
    
    # Don't sort game objects (they have coordinates "0", "0")
    if all(poi[1] == "0" and poi[2] == "0" for poi in pois):
        return sorted(pois, key=lambda x: x[0].lower())
    
    return sorted(pois, key=poi_sort_key)

def get_poi_position_description(poi: Tuple[str, str, str]) -> str:
    """
    Generate a concise description of a POI's position using quadrant format.
    
    Args:
        poi: Tuple containing (name, x, y) coordinates
        
    Returns:
        str: Description in format "position of quadrant"
    """
    try:
        name, x_str, y_str = poi
        x = int(float(x_str))
        y = int(float(y_str))
        
        # Calculate relative position in region of interest
        x_rel = x - ROI_START_ORIG[0]
        y_rel = y - ROI_START_ORIG[1]
        width = ROI_END_ORIG[0] - ROI_START_ORIG[0]
        height = ROI_END_ORIG[1] - ROI_START_ORIG[1]
        
        # Get quadrant (0=top-left, 1=top-right, 2=bottom-left, 3=bottom-right)
        quadrant = get_quadrant(x_rel, y_rel, width, height)
        
        # Get position within quadrant
        quadrant_width = width // 2
        quadrant_height = height // 2
        x_in_quad = x_rel % quadrant_width
        y_in_quad = y_rel % quadrant_height
        
        position = get_position_in_quadrant(x_in_quad, y_in_quad, quadrant_width, quadrant_height)
        
        # Map quadrant index to name
        quadrant_names = ["top left", "top right", "bottom left", "bottom right"]
        quadrant_name = quadrant_names[quadrant]
        
        # Return concise description
        if position == "center":
            return f"center of {quadrant_name} quadrant"
        else:
            return f"{position} of {quadrant_name} quadrant"
    except (ValueError, TypeError, IndexError):
        return "position unknown"

def get_poi_categories(include_empty: bool = False) -> List[str]:
    """
    Get available POI categories for the current map.
    
    Args:
        include_empty: Whether to include empty categories
        
    Returns:
        list: Available category identifiers
    """
    global config
    
    categories = [POI_CATEGORY_SPECIAL, POI_CATEGORY_REGULAR]
    current_map = config.get('POI', 'current_map', fallback='main')
    
    # Add landmarks for main map
    if current_map == 'main':
        categories.append(POI_CATEGORY_LANDMARK)
    
    # Add game objects if any exist
    game_objects = get_pois_by_category(POI_CATEGORY_GAMEOBJECT)
    if include_empty or game_objects:
        categories.append(POI_CATEGORY_GAMEOBJECT)
    
    # Add favorites if any exist
    favorites = get_pois_by_category(POI_CATEGORY_FAVORITE)
    if include_empty or favorites:
        categories.append(POI_CATEGORY_FAVORITE)
    
    # Add custom POIs if any exist
    custom_pois = get_pois_by_category(POI_CATEGORY_CUSTOM)
    if include_empty or custom_pois:
        categories.append(POI_CATEGORY_CUSTOM)
    
    return categories

def find_closest_game_object(player_location: Tuple[int, int]) -> Optional[Tuple[str, Tuple[int, int]]]:
    """
    Find the closest game object to the player using object detection.
    
    Args:
        player_location: Player's current position (x, y)
        
    Returns:
        Tuple of (object_name, (x, y)) or None if no objects found
    """
    try:
        from lib.object_finder import optimized_finder, OBJECT_CONFIGS
        
        if not player_location or not OBJECT_CONFIGS:
            return None
        
        # Get all object names
        object_names = list(OBJECT_CONFIGS.keys())
        
        # Try to find objects using PPI first, then fallback to fullscreen
        use_ppi = check_for_pixel()
        found_objects = optimized_finder.find_all_objects(object_names, use_ppi)
        
        if not found_objects:
            # Fallback to non-PPI if PPI didn't find anything
            found_objects = optimized_finder.find_all_objects(object_names, False)
        
        if not found_objects:
            return None
        
        # Calculate distances and find closest
        closest_object = None
        min_distance = float('inf')
        
        for obj_name, obj_coords in found_objects.items():
            distance = np.linalg.norm(
                np.array(player_location) - np.array(obj_coords)
            )
            
            if distance < min_distance:
                min_distance = distance
                # Convert internal name to display name
                display_name = obj_name.replace('_', ' ').title()
                closest_object = (display_name, obj_coords)
        
        return closest_object
        
    except Exception as e:
        print(f"Error finding closest game object: {e}")
        return None

def cycle_poi_category() -> None:
    """Cycle between POI categories with safe config handling"""
    global config, poi_data_instance, current_poi_category
    
    try:
        # Always re-read the config to ensure we have the latest state
        clear_config_cache()
        config = read_config(use_cache=False)
        
        # Check if shift is being held for reverse cycling
        reverse = is_key_pressed('lshift') or is_key_pressed('rshift')
        
        # Validate POI data is initialized
        if poi_data_instance is None:
            print("POI data not initialized")
            speaker.speak("POI data not initialized")
            return
        
        # Get all available categories
        categories = get_poi_categories()
        if not categories:
            speaker.speak("No POI categories available")
            return
        
        # Find current category index
        try:
            current_index = categories.index(current_poi_category)
        except ValueError:
            # If current category not found, default to first category
            current_index = 0
        
        # Calculate new index with wrapping
        if reverse:
            new_index = (current_index - 1) % len(categories)
        else:
            new_index = (current_index + 1) % len(categories)
        
        # Get new category
        new_category = categories[new_index]
        
        # Update global category tracker
        current_poi_category = new_category
        
        # Get POIs in the new category
        category_pois = get_pois_by_category(new_category)
        
        # Sort POIs by position
        sorted_pois = sort_pois_by_position(category_pois)
        
        # If category has POIs, select the first one
        if sorted_pois:
            first_poi = sorted_pois[0]
            
            # Use thread-safe config operations
            config_adapter = Config()
            config_adapter.set_poi(first_poi[0], first_poi[1], first_poi[2])
            success = config_adapter.save()
            
            if success:
                # Update our global config reference
                clear_config_cache()
                config = read_config(use_cache=False)
                
                # Get category display name
                category_display_names = {
                    POI_CATEGORY_SPECIAL: "Special",
                    POI_CATEGORY_REGULAR: "Regular",
                    POI_CATEGORY_LANDMARK: "Landmark",
                    POI_CATEGORY_FAVORITE: "Favorite",
                    POI_CATEGORY_CUSTOM: "Custom",
                    POI_CATEGORY_GAMEOBJECT: "Game Object"
                }
                display_name = category_display_names.get(new_category, new_category.title())
                
                # Get position description if not a special POI or game object
                position_desc = ""
                if (first_poi[0].lower() not in [SPECIAL_POI_CLOSEST.lower(), SPECIAL_POI_SAFEZONE.lower(), 
                                                SPECIAL_POI_CLOSEST_LANDMARK.lower(), SPECIAL_POI_CLOSEST_GAMEOBJECT.lower()] 
                    and first_poi[1] != "0" and first_poi[2] != "0"):
                    position_desc = get_poi_position_description(first_poi)
                    if position_desc:
                        position_desc = f", {position_desc}"
                
                # Announce selection
                speaker.speak(f"{display_name} POIs: {first_poi[0]}{position_desc}")
                print(f"Selected {first_poi[0]} from {display_name} POIs")
            else:
                speaker.speak("Error saving POI selection")
        else:
            speaker.speak(f"No POIs available in the selected category")
            print(f"No POIs available in the selected category")
            
    except Exception as e:
        print(f"Error cycling POI category: {e}")
        speaker.speak("Error cycling POI categories")

def cycle_poi() -> None:
    """Cycle through POIs in the current category with safe config handling"""
    global config, poi_data_instance, current_poi_category
    
    try:
        # Always re-read the config to ensure we have the latest state
        clear_config_cache()
        config = read_config(use_cache=False)
        
        # Check if shift is being held for reverse cycling
        reverse = is_key_pressed('lshift') or is_key_pressed('rshift')
        
        if poi_data_instance is None:
            print("POI data not initialized")
            speaker.speak("POI data not initialized")
            return
        
        # Get POIs in the current category
        category_pois = get_pois_by_category(current_poi_category)
        
        # If no POIs in the category, notify user
        if not category_pois:
            speaker.speak("No POIs available in the current category")
            return
        
        # Sort POIs by position
        sorted_pois = sort_pois_by_position(category_pois)
        
        # Get current selected POI directly from config
        selected_poi_str = config.get('POI', 'selected_poi', fallback='closest, 0, 0')
        selected_poi_parts = selected_poi_str.split(',')
        selected_poi_name = selected_poi_parts[0].strip()
        
        # Find index of current POI
        current_index = -1
        for i, poi in enumerate(sorted_pois):
            if poi[0].lower() == selected_poi_name.lower():
                current_index = i
                break
        
        # If not found, default to first POI
        if current_index == -1:
            current_index = 0
        
        # Calculate new index with wrapping
        if reverse:
            new_index = (current_index - 1) % len(sorted_pois)
        else:
            new_index = (current_index + 1) % len(sorted_pois)
        
        # Get new POI
        new_poi = sorted_pois[new_index]
        
        # Use thread-safe config operations
        config_adapter = Config()
        config_adapter.set_poi(new_poi[0], new_poi[1], new_poi[2])
        success = config_adapter.save()
        
        if success:
            # Update our global config reference
            clear_config_cache()
            config = read_config(use_cache=False)
            
            # Get position description if not a special POI or game object
            position_desc = ""
            if (new_poi[0].lower() not in [SPECIAL_POI_CLOSEST.lower(), SPECIAL_POI_SAFEZONE.lower(), 
                                          SPECIAL_POI_CLOSEST_LANDMARK.lower(), SPECIAL_POI_CLOSEST_GAMEOBJECT.lower()] 
                and new_poi[1] != "0" and new_poi[2] != "0"):
                position_desc = get_poi_position_description(new_poi)
                if position_desc:
                    position_desc = f", {position_desc}"
            
            # Announce selection
            speaker.speak(f"{new_poi[0]}{position_desc}")
            print(f"{new_poi[0]} selected")
        else:
            speaker.speak("Error saving POI selection")
            
    except Exception as e:
        print(f"Error cycling POI: {e}")
        speaker.speak("Error cycling POIs")

def cycle_map():
    """Cycle to the next/previous map with safe config handling"""
    global config, poi_data_instance, current_poi_category
    
    try:
        # Always re-read the config to ensure we have the latest state
        clear_config_cache()
        config = read_config(use_cache=False)
        
        # Check if shift is being held for reverse cycling
        reverse = is_key_pressed('lshift') or is_key_pressed('rshift')
        
        if poi_data_instance is None:
            print("POI data not initialized")
            speaker.speak("POI data not initialized")
            return

        # Get the current map from config
        current_map = config.get('POI', 'current_map', fallback='main')
        
        # Get a sorted list of all available maps (without duplicating 'main')
        all_maps = sorted(poi_data_instance.maps.keys())
        
        # Find the index of the current map
        try:
            current_index = all_maps.index(current_map)
        except ValueError:
            current_index = 0
        
        # Calculate the new index with wrapping
        if reverse:
            new_index = (current_index - 1) % len(all_maps)
        else:
            new_index = (current_index + 1) % len(all_maps)
        
        # Get the new map name
        new_map = all_maps[new_index]
        
        # Remember current category - don't change it when switching maps
        previous_category = current_poi_category
        
        # Try to get POIs in the current category for the new map
        # Temporarily update the config to check POIs
        temp_config = config
        temp_config.set('POI', 'current_map', new_map)
        category_pois = get_pois_by_category(previous_category)
        
        # If no POIs in the current category on the new map, fall back to special category
        if not category_pois:
            current_poi_category = POI_CATEGORY_SPECIAL
            category_pois = get_pois_by_category(POI_CATEGORY_SPECIAL)
        
        # Reset selected POI to first one in the category
        if category_pois:
            sorted_pois = sort_pois_by_position(category_pois)
            first_poi = sorted_pois[0]
            selected_poi_value = f"{first_poi[0]}, {first_poi[1]}, {first_poi[2]}"
        else:
            # If no POIs found at all, reset to closest
            selected_poi_value = "closest, 0, 0"
        
        # Use thread-safe config operations
        config_adapter = Config()
        config_adapter.set_current_map(new_map)
        config_adapter.set_poi(*selected_poi_value.split(', '))
        success = config_adapter.save()
        
        if success:
            # Update our global config reference
            clear_config_cache()
            config = read_config(use_cache=False)
            
            # Get display name for announcement
            try:
                display_name = poi_data_instance.maps[new_map].name
            except (KeyError, AttributeError):
                display_name = new_map.replace('_', ' ').title()
                
            speaker.speak(f"{display_name} map selected")
            print(f"{new_map} selected")
        else:
            speaker.speak("Error saving map selection")
            
    except Exception as e:
        print(f"Error cycling map: {e}")
        speaker.speak("Error cycling maps")

def handle_update_with_changelog() -> None:
    """Handle update notification with changelog display option."""
    local_changelog_path = 'CHANGELOG.txt'
    
    local_changelog_exists = os.path.exists(local_changelog_path)
    
    remote_changelog = None
    try:
        response = requests.get(CHANGELOG_URL, timeout=10)
        response.raise_for_status()
        remote_changelog = response.text
    except requests.RequestException as e:
        print(f"Failed to fetch remote changelog: {e}")
        speaker.speak("FA11y has been updated! Closing in 5 seconds...")
        print("FA11y has been updated! Closing in 5 seconds...")
        time.sleep(5)
        return
    
    changelog_updated = True
    if local_changelog_exists:
        try:
            with open(local_changelog_path, 'r', encoding='utf-8') as f:
                local_changelog = f.read()
            changelog_updated = remote_changelog != local_changelog
        except Exception as e:
            print(f"Error reading local changelog: {e}")
    
    try:
        with open(local_changelog_path, 'w', encoding='utf-8') as f:
            f.write(remote_changelog)
    except Exception as e:
        print(f"Error saving changelog: {e}")
    
    if changelog_updated:
        speaker.speak("FA11y has been updated! Open changelog? Press Y for yes, or any other key for no.")
        print("FA11y has been updated! Open changelog? (Y/N)")
        
        try:
            import msvcrt
            key = msvcrt.getch().decode('utf-8', errors='ignore').lower()
            
            if key == 'y':
                try:
                    if sys.platform == 'win32':
                        os.startfile(local_changelog_path)
                    elif sys.platform == 'darwin':
                        subprocess.call(['open', local_changelog_path])
                    else:
                        subprocess.call(['xdg-open', local_changelog_path])
                except Exception as e:
                    print(f"Failed to open changelog: {e}")
                    speaker.speak("Failed to open changelog. Closing in 5 seconds...")
                    print("Failed to open changelog. Closing in 5 seconds...")
                    time.sleep(5)
                    return
            else:
                speaker.speak("Closing in 5 seconds...")
                print("Closing in 5 seconds...")
        except:
            print("Press Y and Enter to open changelog, or just Enter to close")
            response = input().strip().lower()
            if response == 'y':
                try:
                    if sys.platform == 'win32':
                        os.startfile(local_changelog_path)
                    elif sys.platform == 'darwin':
                        subprocess.call(['open', local_changelog_path])
                    else:
                        subprocess.call(['xdg-open', local_changelog_path])
                except Exception as e:
                    print(f"Failed to open changelog: {e}")
            
        time.sleep(5)
    else:
        speaker.speak("FA11y has been updated! Closing in 5 seconds...")
        print("FA11y has been updated! Closing in 5 seconds...")
        time.sleep(5)

def run_updater() -> bool:
    """Run the updater script."""
    result = subprocess.run([sys.executable, 'updater.py', '--run-by-fa11y'], capture_output=True, text=True)
    update_performed = result.returncode == 1
    
    if update_performed:
        handle_update_with_changelog()
        
    return update_performed

def get_version() -> str:
    """Get version from GitHub repository."""
    try:
        response = requests.get(VERSION_URL, timeout=10)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException as e:
        print(f"Failed to fetch version from GitHub: {e}")
        return None

def parse_version(version: str) -> tuple:
    """Parse version string into tuple."""
    return tuple(map(int, version.split('.')))

def check_for_updates() -> None:
    """Periodically check for updates."""
    update_notified = False

    while True:
        local_version = None
        if os.path.exists('VERSION'):
            with open('VERSION', 'r') as f:
                local_version = f.read().strip()

        remote_version = get_version()

        if not local_version:
            print("No local version found. Update may be required.")
        elif not remote_version:
            print("Failed to fetch remote version. Skipping version check.")
        else:
            try:
                local_v = parse_version(local_version)
                remote_v = parse_version(remote_version)
                if local_v != remote_v:
                    if not update_notified:
                        update_sound.play()
                        speaker.speak("An update is available for FA11y! Restart FA11y to update!")
                        print("An update is available for FA11y! Restart FA11y to update!")
                        update_notified = True
                else:
                    update_notified = False
            except ValueError:
                print("Invalid version format. Treating as update required.")

        time.sleep(6)

def get_legendary_username() -> str:
    """Get username from Legendary launcher."""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)

        result = subprocess.run(["legendary", "status"], capture_output=True, text=True)
        if result.returncode == 0:
            output = result.stdout
            for line in output.splitlines():
                if "Epic account:" in line:
                    username = line.split("Epic account:")[1].strip()
                    if username and username != "<not logged in>":
                        return username
        return None
    except Exception as e:
        print(f"Failed to run 'legendary status': {str(e)}")
        return None

def main() -> None:
    """Main entry point for FA11y."""
    global config, action_handlers, key_bindings, key_listener_thread, stop_key_listener
    try:
        print("Starting FA11y...")

        # Check and welcome user
        local_username = get_legendary_username()
        if local_username:
            print(f"Welcome back {local_username}!")
            speaker.speak(f"Welcome back {local_username}!")
        else:
            print("You are not logged into Legendary.")
            speaker.speak("You are not logged into Legendary.")

        # Check for updates if enabled
        temp_config_for_update_check = read_config()
        if get_config_boolean(temp_config_for_update_check, 'AutoUpdates', True):
            if run_updater():
                sys.exit(0)

        # Create desktop shortcut if enabled
        temp_config_for_shortcut_check = read_config()
        if get_config_boolean(temp_config_for_shortcut_check, 'CreateDesktopShortcut', True):
            create_desktop_shortcut()

        # Initialize core systems
        reload_config()

        # Start key listener thread
        stop_key_listener.clear()
        key_listener_thread = threading.Thread(target=key_listener, daemon=True)
        key_listener_thread.start()

        # Start update checker thread
        update_thread = threading.Thread(target=check_for_updates, daemon=True)
        update_thread.start()

        # Start auxiliary systems
        threading.Thread(target=start_height_checker, daemon=True).start()
        monitor.start_monitoring()
        material_monitor.start_monitoring()
        resource_monitor.start_monitoring()
        gameobject_monitor.start_monitoring()
        storm_monitor.start_monitoring()

        # Initialize hotbar detection
        initialize_hotbar_detection()

        # Print available game objects for reference
        gameobjects = get_gameobject_configs()
        if gameobjects:
            print(f"Game object monitoring configured for {len(gameobjects)} object types:")
            for obj_name in sorted(gameobjects.keys()):
                display_name = obj_name.replace('_', ' ').title()
                config_key = f"Monitor{obj_name.replace('_', '').title()}"
                ping_key = f"{obj_name.replace('_', '').title()}PingInterval"
                print(f"  - {display_name} (Toggle: {config_key}, Interval: {ping_key})")

        # Print storm monitoring info
        print("Storm monitoring configured:")
        print("  - Monitor storm on minimap with spatial audio pings")
        print("  - Config options: MonitorStorm (toggle), StormVolume, StormPingInterval")

        # Notify user that FA11y is running
        speaker.speak("FA11y is now running in the background. Press Enter in this window to stop FA11y.")
        print("FA11y is now running in the background. Press Enter in this window to stop FA11y.")
        input()

    except Exception as e:
        print(f"An error occurred: {str(e)}")
        speaker.speak(f"An error occurred: {str(e)}")
    finally:
        # Clean up operations
        stop_key_listener.set()
        if key_listener_thread is not None:
            key_listener_thread.join(timeout=1.0)

        monitor.stop_monitoring()
        material_monitor.stop_monitoring()
        resource_monitor.stop_monitoring()
        gameobject_monitor.stop_monitoring()
        storm_monitor.stop_monitoring()
        
        # Clean up object detection resources
        cleanup_object_detection()

        # Clean up any remaining tkinter variables
        if 'tk' in sys.modules:
            try:
                import tkinter as tk
                if tk._default_root:
                    for widget in tk._default_root.winfo_children():
                        widget.destroy()
                    tk._default_root.destroy()
                    tk._default_root = None
            except Exception:
                pass

        print("FA11y is closing...")
        sys.exit(0)

if __name__ == "__main__":
    main()