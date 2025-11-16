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
import signal
import atexit
import gc
import ctypes
import ctypes.wintypes
import logging
import wx
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

try:
    import PyQt6
    PYQT6_AVAILABLE = True
except ImportError:
    PYQT6_AVAILABLE = False
    print("Warning: PyQt6 not available")

# Import from reorganized lib structure
from lib.detection.hsr import (
    check_health_shields,
    check_rarity,
)
from lib.utilities.mouse import (
    smooth_move_mouse,
    left_mouse_down,
    left_mouse_up,
    right_mouse_down,
    right_mouse_up,
    mouse_scroll,
)

# New imports from reorganized structure
from lib.monitors.height_monitor import start_height_monitor
from lib.monitors.background_monitor import monitor
from lib.monitors.material_monitor import material_monitor
from lib.monitors.resource_monitor import resource_monitor
# from lib.monitors.dynamic_object_monitor import dynamic_object_monitor
from lib.monitors.storm_monitor import storm_monitor

from lib.managers.game_object_manager import game_object_manager
from lib.detection.match_tracker import match_tracker
from lib.managers.social_manager import get_social_manager

from lib.utilities.input import (
    is_key_pressed, get_pressed_key, is_numlock_on, VK_KEYS,
    is_key_combination_pressed, parse_key_combination, get_pressed_key_combination, is_key_combination_pressed_ignore_extra_mods
)

from lib.managers.poi_data_manager import POIData
from lib.detection.exit_match import exit_match
from lib.detection.player_position import (
    announce_current_direction as speak_minimap_direction, 
    start_icon_detection, 
    check_for_pixel,
    ROI_START_ORIG,
    ROI_END_ORIG,
    get_quadrant,
    get_position_in_quadrant,
    cleanup_object_detection,
    find_player_position,
    find_player_icon_location,
    ContinuousPOIPinger,
    handle_poi_selection
)
from lib.managers.hotbar_manager import (
    initialize_hotbar_detection,
    detect_hotbar_item,
    announce_ammo_manually,
)
from lib.managers.inventory_manager import inventory_manager
from lib.utilities.utilities import (
    get_config_int,
    get_config_float,
    get_config_value,
    get_config_boolean,
    read_config,
    Config,
    get_default_config_value_string,
    # get_dynamic_object_configs,
    clear_config_cache,
    save_config,
    calculate_distance,
    get_game_objects_config_order,
    ensure_config_dir,
    migrate_config_files
)
from lib.managers.custom_poi_manager import load_custom_pois

# Ensure config directory exists and migrate old config files
ensure_config_dir()
migrate_config_files()

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
social_gui_open = threading.Event()
locker_gui_open = threading.Event()
gamemode_gui_open = threading.Event()
keybinds_enabled = True
poi_data_instance = None
active_pinger = None
social_manager = None

# Global shutdown flag for instant shutdown
_shutdown_requested = threading.Event()

# Auth expiration flag - set when API returns 401
auth_expired = threading.Event()
auth_expiration_announced = False  # Track if we've already announced it

# POI category definitions
POI_CATEGORY_SPECIAL = "special"
POI_CATEGORY_REGULAR = "regular"
POI_CATEGORY_LANDMARK = "landmark"
POI_CATEGORY_FAVORITE = "favorite"
POI_CATEGORY_CUSTOM = "custom"
POI_CATEGORY_GAMEOBJECT = "gameobject"
# POI_CATEGORY_DYNAMICOBJECT = "dynamicobject"

# Special POI names
SPECIAL_POI_CLOSEST = "closest"
SPECIAL_POI_SAFEZONE = "safe zone"
SPECIAL_POI_CLOSEST_LANDMARK = "closest landmark"

# Global variable to track current POI category
current_poi_category = POI_CATEGORY_SPECIAL

# Initialize logger
logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    """Handle CTRL+C and other termination signals for immediate shutdown."""
    print("\nShutdown requested...")
    _shutdown_requested.set()
    
    # Immediate cleanup of critical resources
    try:
        # Stop all monitoring systems without waiting
        monitor.stop_monitoring()
        material_monitor.stop_monitoring()
        resource_monitor.stop_monitoring()
        # dynamic_object_monitor.stop_monitoring()
        storm_monitor.stop_monitoring()
        match_tracker.stop_monitoring()

        # Stop social manager
        if social_manager:
            social_manager.stop_monitoring()

        # Clean up pygame mixer
        if pygame.mixer.get_init():
            pygame.mixer.quit()
            
        # Set stop event for threads
        stop_key_listener.set()
        
    except:
        pass  # Ignore cleanup errors during shutdown
    
    print("FA11y is closing...")
    # Force immediate exit
    os._exit(0)

def register_shutdown_handlers():
    """Register signal handlers for clean shutdown."""
    signal.signal(signal.SIGINT, signal_handler)   # CTRL+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination request
    
    # Register cleanup function for normal exit
    atexit.register(cleanup_on_exit)

def cleanup_on_exit():
    """Cleanup function called on normal exit."""
    try:
        if pygame.mixer.get_init():
            pygame.mixer.quit()
    except:
        pass

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

        # Initialize POI data if not already done and ensure data is loaded
        if poi_data_instance is None:
            poi_data_instance = POIData()
        
        # Ensure POI data is loaded for the current map
        current_map = config.get('POI', 'current_map', fallback='main')
        if current_map == 'main':
            poi_data_instance._ensure_api_data_loaded()
        else:
            poi_data_instance._ensure_map_data_loaded(current_map)

        # Initialize or update current_poi_category based on selected POI
        selected_poi_str = config.get('POI', 'selected_poi', fallback='closest, 0, 0')
        selected_poi_parts = selected_poi_str.split(',')
        selected_poi_name = selected_poi_parts[0].strip()
        current_poi_category = get_poi_category(selected_poi_name)

        # Validate keybinds and reset if necessary - now supports modifier keys
        config_updated = False
        temp_key_bindings_from_config = {key.lower(): get_config_value(config, key)[0].lower()
                                         for key in config['Keybinds'] if get_config_value(config, key)[0]}

        validated_key_bindings = {}
        for action, key_str in temp_key_bindings_from_config.items():
            if not key_str: # Allow empty keybinds (disabled)
                validated_key_bindings[action] = key_str
                continue

            if is_valid_key_or_combination(key_str):
                validated_key_bindings[action] = key_str
            else:
                speaker.speak(f"Unrecognized key combination '{key_str}' for action '{action}'. Resetting to default.")
                print(f"Warning: Unrecognized key combination '{key_str}' for action '{action}'. Resetting to default.")
                
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
            'open gamemode selector': open_gamemode_selector,
            'open locker selector': open_locker_selector,
            'open locker viewer': open_locker_viewer,
            'open configuration menu': open_config_gui,
            'exit match': exit_match,
            'create custom p o i': handle_custom_poi_gui,
            'announce ammo': announce_ammo_manually,
            'toggle keybinds': toggle_keybinds,
            'toggle continuous ping': toggle_continuous_ping,
            'mark bad game object': mark_last_reached_object_as_bad,
            'cycle map': lambda: cycle_map("forwards"),
            'cycle map backwards': lambda: cycle_map("backwards"),
            'cycle poi': lambda: cycle_poi("forwards"),
            'cycle poi backwards': lambda: cycle_poi("backwards"),
            'cycle poi category': lambda: cycle_poi_category("forwards"),
            'cycle poi category backwards': lambda: cycle_poi_category("backwards"),
            'get match stats': get_match_stats,
            'check hotspots': check_hotspots,
            'open visited objects': open_visited_objects,
            'open social menu': open_social_menu,
            'open authentication': open_authentication,
            'accept notification': accept_notification,
            'decline notification': decline_notification,
        })

        for i in range(1, 6):
            action_handlers[f'detect hotbar {i}'] = lambda slot=i-1: detect_hotbar_item(slot)
            
    except Exception as e:
        print(f"Error reloading config: {e}")
        speaker.speak("Error reloading configuration")

def is_valid_key_or_combination(key_combo: str) -> bool:
    """Check if a key combination is valid"""
    if not key_combo:
        return False
    
    from lib.utilities.input import validate_key_combination
    return validate_key_combination(key_combo)

def get_match_stats() -> None:
    """Announce current match statistics"""
    try:
        stats = match_tracker.get_current_match_stats()
        if not stats:
            speaker.speak("No active match data available")
            return
        
        duration_minutes = int(stats['duration'] // 60)
        duration_seconds = int(stats['duration'] % 60)
        
        message = f"Match active for {duration_minutes} minutes {duration_seconds} seconds. "
        message += f"Total visits: {stats['total_visits']}. "
        
        if stats['visited_object_types']:
            message += "Visited: " + ", ".join(stats['visited_object_types'])
        
        speaker.speak(message)
        print(f"Match Stats: {stats}")
        
    except Exception as e:
        print(f"Error getting match stats: {e}")
        speaker.speak("Error getting match statistics")

def mark_last_reached_object_as_bad() -> None:
    """Mark the last reached game object as bad and remove it from the map"""
    try:
        # Get current match stats to find last reached object
        stats = match_tracker.get_current_match_stats()
        if not stats or not stats.get('visited_object_types'):
            speaker.speak("No game objects have been reached yet")
            return
        
        # Find the most recently visited object across all types
        last_visited = None
        latest_time = 0
        last_visited_type = None
        
        for obj_type in stats['visited_object_types']:
            visited_objects = match_tracker.get_visited_objects_of_type(obj_type)
            for visited_obj in visited_objects:
                if visited_obj.visit_time > latest_time:
                    latest_time = visited_obj.visit_time
                    last_visited = visited_obj
                    last_visited_type = obj_type
        
        if not last_visited:
            speaker.speak("No game objects have been reached yet")
            return
        
        # Get current map and file paths
        config = read_config()
        current_map = config.get('POI', 'current_map', fallback='main')
        
        if current_map == 'main':
            source_file = os.path.join('maps', 'map_main_gameobjects.txt')
            bad_file = os.path.join('maps', 'map_main_badgameobject.txt')
        else:
            safe_map = current_map.strip().lower().replace(' ', '_')
            import re
            safe_map = re.sub(r'[^a-z0-9_]+', '', safe_map)
            source_file = os.path.join('maps', f'map_{safe_map}_gameobjects.txt')
            bad_file = os.path.join('maps', f'map_{safe_map}_badgameobject.txt')
        
        if not os.path.exists(source_file):
            speaker.speak(f"Game objects file not found for {current_map} map")
            return
        
        # Convert screen coordinates back to image coordinates for matching
        from lib.managers.game_object_manager import MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, SCREEN_BOUNDS_X1, SCREEN_BOUNDS_Y1, SCREEN_BOUNDS_X2, SCREEN_BOUNDS_Y2
        
        screen_width = SCREEN_BOUNDS_X2 - SCREEN_BOUNDS_X1
        screen_height = SCREEN_BOUNDS_Y2 - SCREEN_BOUNDS_Y1
        screen_x = last_visited.coordinates[0] - SCREEN_BOUNDS_X1
        screen_y = last_visited.coordinates[1] - SCREEN_BOUNDS_Y1
        image_x = (screen_x / screen_width) * MAP_IMAGE_WIDTH
        image_y = (screen_y / screen_height) * MAP_IMAGE_HEIGHT
        
        # Find and remove matching line from source file
        line_removed = None
        updated_lines = []
        
        with open(source_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith('#'):
                updated_lines.append(line)
                continue
            
            try:
                parts = line_stripped.split(',')
                if len(parts) == 3:
                    obj_type = parts[0].strip()
                    file_x = float(parts[1].strip())
                    file_y = float(parts[2].strip())
                    
                    # Check if this matches our target (within tolerance)
                    if (obj_type == last_visited_type and 
                        abs(file_x - image_x) <= 5 and 
                        abs(file_y - image_y) <= 5):
                        line_removed = line_stripped
                        continue  # Skip this line (remove it)
                
                updated_lines.append(line)
            except (ValueError, IndexError):
                updated_lines.append(line)
        
        if not line_removed:
            speaker.speak("Could not find matching game object in file")
            return
        
        # Write updated source file
        with open(source_file, 'w', encoding='utf-8') as f:
            f.writelines(updated_lines)
        
        # Add to bad objects file
        os.makedirs('maps', exist_ok=True)
        bad_lines = []
        
        if os.path.exists(bad_file):
            with open(bad_file, 'r', encoding='utf-8') as f:
                bad_lines = f.readlines()
        
        # Add header if file is empty
        if not bad_lines:
            bad_lines = [f"# Bad game objects for {current_map} map\n",
                        "# Format: ObjectType,X,Y (coordinates relative to map image)\n",
                        "#\n"]
        
        # Remove trailing empty lines and add the bad object
        while bad_lines and not bad_lines[-1].strip():
            bad_lines.pop()
        bad_lines.append(line_removed + '\n')
        
        with open(bad_file, 'w', encoding='utf-8') as f:
            f.writelines(bad_lines)
        
        # Refresh game object data and remove from match tracking
        game_object_manager.reload_map_data(current_map)
        
        if last_visited_type in match_tracker.current_match.visited_objects:
            visited_list = match_tracker.current_match.visited_objects[last_visited_type]
            match_tracker.current_match.visited_objects[last_visited_type] = [
                obj for obj in visited_list if obj.coordinates != last_visited.coordinates
            ]
            if not match_tracker.current_match.visited_objects[last_visited_type]:
                del match_tracker.current_match.visited_objects[last_visited_type]
        
        speaker.speak(f"Marked {last_visited_type} as bad and removed from map")
        
    except Exception as e:
        print(f"Error marking object as bad: {e}")
        speaker.speak("Error marking last reached object as bad")

# Auth expiration handling
def handle_auth_expiration():
    """Handle authentication expiration - announce once and set flag"""
    global auth_expiration_announced
    auth_expired.set()
    if not auth_expiration_announced:
        speaker.speak("Authentication expired. Press ALT+A to re-authenticate.")
        logger.warning("Epic Games authentication expired")
        auth_expiration_announced = True

def open_authentication():
    """Open Epic Games authentication dialog for re-authentication (ALT+A)"""
    global social_manager, auth_expired, auth_expiration_announced

    try:
        from lib.utilities.epic_auth import get_epic_auth_instance
        from lib.guis.epic_login_dialog import LoginDialog
        import wx

        speaker.speak("Opening authentication dialog")

        epic_auth = get_epic_auth_instance()

        # Create wx app if needed
        app = wx.GetApp()
        if app is None:
            app = wx.App(False)

        # Show login dialog
        login_dialog = LoginDialog(None, epic_auth)
        result = login_dialog.ShowModal()
        authenticated = login_dialog.authenticated
        login_dialog.Destroy()

        if authenticated:
            # Clear auth expiration flags
            auth_expired.clear()
            auth_expiration_announced = False

            # Refresh auth instance
            epic_auth = get_epic_auth_instance()

            # Reinitialize social manager if it exists
            if social_manager:
                social_manager.stop_monitoring()
                from lib.managers.social_manager import get_social_manager
                social_manager = get_social_manager(epic_auth)
                social_manager.start_monitoring()

            speaker.speak(f"Authentication successful for {epic_auth.display_name}")
            logger.info(f"Re-authenticated as {epic_auth.display_name}")
        else:
            speaker.speak("Authentication cancelled")

    except Exception as e:
        logger.error(f"Error opening authentication dialog: {e}")
        speaker.speak("Error opening authentication dialog")

# Social manager wrapper functions
def open_social_menu():
    """Open social menu GUI"""
    global social_manager, social_gui_open
    if not social_manager:
        speaker.speak("Social features not enabled")
        return

    # Check if social GUI is already open
    if social_gui_open.is_set():
        speaker.speak("Social menu is already open")
        return

    # Wait for initial data to load (with timeout)
    if not social_manager.initial_data_loaded.is_set():
        speaker.speak("Loading social data")
        if not social_manager.wait_for_initial_data(timeout=10):
            speaker.speak("Timeout waiting for social data, opening anyway")

    try:
        from lib.guis.social_gui import show_social_gui
        social_gui_open.set()
        try:
            show_social_gui(social_manager)
        finally:
            social_gui_open.clear()
    except Exception as e:
        logger.error(f"Error opening social menu: {e}")
        speaker.speak("Error opening social menu")
        social_gui_open.clear()

def accept_notification():
    """Accept pending notification (Alt+Y)"""
    global social_manager
    if social_manager:
        social_manager.accept_notification()
    else:
        logger.debug("Social manager not initialized")

def decline_notification():
    """Decline pending notification (Alt+D)"""
    global social_manager
    if social_manager:
        social_manager.decline_notification()
    else:
        logger.debug("Social manager not initialized")

def check_hotspots() -> None:
    """Check for hotspot POIs on the map"""
    try:
        # Import here to avoid circular imports
        from lib.monitors.background_monitor import monitor
        
        # Define the pixel coordinates to check
        hotspot_pixels = [
            (683, 303), (955, 311), (1210, 245), (782, 405), (904, 417),
            (1031, 461), (654, 511), (555, 618), (725, 641), (894, 625),
            (1078, 639), (1232, 607), (585, 894), (957, 846), (1190, 876),
            (764, 830), (1265, 776)
        ]
        
        hotspot_coordinates = []
        
        # Check each pixel
        for x, y in hotspot_pixels:
            try:
                pixel_color = pyautogui.pixel(x, y)
                r, g, b = pixel_color
                
                # Check if pixel is NOT white (250-255) and NOT black (0-5)
                is_white = (250 <= r <= 255) and (250 <= g <= 255) and (250 <= b <= 255)
                is_black = (0 <= r <= 5) and (0 <= g <= 5) and (0 <= b <= 5)
                
                if not is_white and not is_black:
                    hotspot_coordinates.append((x, y))
                    
            except Exception as e:
                print(f"Error checking pixel at {x},{y}: {e}")
                continue
        
        if not hotspot_coordinates:
            speaker.speak("No hotspots detected")
            return
        
        if len(hotspot_coordinates) > 2:
            speaker.speak(f"Error: {len(hotspot_coordinates)} hotspots detected, expected maximum 2")
            return
        
        # Find closest POIs to the hotspot coordinates
        hotspot_pois = []
        
        global poi_data_instance
        if poi_data_instance is None:
            poi_data_instance = POIData()
        
        current_map = config.get('POI', 'current_map', fallback='main')
        
        # Get POIs for current map
        if current_map == 'main':
            # Ensure data is loaded
            poi_data_instance._ensure_api_data_loaded()
            available_pois = poi_data_instance.main_pois
        elif current_map in poi_data_instance.maps:
            poi_data_instance._ensure_map_data_loaded(current_map)
            available_pois = poi_data_instance.maps[current_map].pois
        else:
            speaker.speak("No POI data available for current map")
            return
        
        for hotspot_x, hotspot_y in hotspot_coordinates:
            closest_poi = None
            min_distance = float('inf')
            
            for poi_name, poi_x_str, poi_y_str in available_pois:
                try:
                    poi_x = int(float(poi_x_str))
                    poi_y = int(float(poi_y_str))
                    
                    # Calculate distance
                    distance = ((hotspot_x - poi_x) ** 2 + (hotspot_y - poi_y) ** 2) ** 0.5
                    
                    if distance < min_distance:
                        min_distance = distance
                        closest_poi = poi_name
                        
                except (ValueError, TypeError):
                    continue
            
            if closest_poi:
                hotspot_pois.append(closest_poi)
        
        # Announce the results
        if len(hotspot_pois) == 1:
            speaker.speak(f"{hotspot_pois[0]} is a hot spot")
        elif len(hotspot_pois) == 2:
            speaker.speak(f"{hotspot_pois[0]} and {hotspot_pois[1]} are hot spots")
        else:
            speaker.speak("No POIs found near hotspots")
            
    except Exception as e:
        print(f"Error checking hotspots: {e}")
        speaker.speak("Error checking hotspots")

def open_visited_objects() -> None:
    """Open the visited objects manager GUI"""
    try:
        from lib.guis.visited_objects_gui import launch_visited_objects_gui
        launch_visited_objects_gui()
    except Exception as e:
        print(f"Error opening visited objects GUI: {e}")
        speaker.speak("Error opening visited objects manager")

def toggle_keybinds() -> None:
    """Toggle keybinds on/off."""
    global keybinds_enabled
    keybinds_enabled = not keybinds_enabled
    state = 'enabled' if keybinds_enabled else 'disabled'
    speaker.speak(f"FA11y {state}")
    print(f"FA11y has been {state}.")

def toggle_continuous_ping() -> None:
    """Toggle continuous pinging for the selected POI."""
    global active_pinger, config
    if active_pinger:
        active_pinger.stop()
        active_pinger = None
        speaker.speak("Continuous ping disabled.")
        return

    config = read_config()
    selected_poi_str = config.get('POI', 'selected_poi', fallback='none,0,0')
    parts = selected_poi_str.split(',')
    if len(parts) < 3 or parts[0].strip().lower() == 'none':
        speaker.speak("No POI selected.")
        return

    poi_name = parts[0].strip()
    player_pos = find_player_position()
    if not player_pos:
        speaker.speak("Cannot start ping, player position unknown.")
        return

    poi_data = handle_poi_selection(poi_name, player_pos)
    if not poi_data or not poi_data[1]:
        speaker.speak(f"Location for {poi_name} not found.")
        return

    poi_coords = (int(float(poi_data[1][0])), int(float(poi_data[1][1])))
    
    active_pinger = ContinuousPOIPinger(poi_coords)
    active_pinger.start()
    speaker.speak(f"Continuous ping enabled for {poi_name}.")

def key_listener() -> None:
    """Listen for and handle key presses with modifier key support and fast shutdown response."""
    global key_bindings, key_state, action_handlers, stop_key_listener, config_gui_open, keybinds_enabled, config
    
    # Define the set of actions that should ignore extra modifiers
    mouse_key_actions = {
        'fire', 'target', 'turn left', 'turn right',
        'secondary turn left', 'secondary turn right',
        'look up', 'look down', 'turn around', 'recenter',
        'scroll up', 'scroll down'
    }

    # Helper to check if any FA11y GUI has focus
    def any_fa11y_gui_focused():
        """Check if any FA11y GUI window is currently focused"""
        try:
            import ctypes
            # Get foreground window title
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return False

            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            window_title = buff.value

            # Check if it's one of our GUIs
            fa11y_gui_titles = [
                "Social Menu",
                "Locker",
                "Gamemode Selector",
                "Configuration",
                "Custom POI Creator",
                "Visited Objects Manager",
                "Epic Games Login"
            ]

            return any(title in window_title for title in fa11y_gui_titles)
        except:
            return False

    while not stop_key_listener.is_set() and not _shutdown_requested.is_set():
        # Quick exit check at start of loop
        if _shutdown_requested.is_set():
            break

        # Skip keybind processing if any FA11y GUI has focus (allows typing in text fields)
        if not any_fa11y_gui_focused():
            numlock_on = is_numlock_on()
            if config is None:
                time.sleep(0.1)
                continue

            mouse_keys_enabled = get_config_boolean(config, 'MouseKeys', True)

            for action, key_combo in key_bindings.items():
                if not key_combo:
                    continue

                # Quick exit check in inner loop
                if _shutdown_requested.is_set():
                    return

                action_lower = action.lower()

                if action_lower not in action_handlers:
                    continue

                if not keybinds_enabled and action_lower != 'toggle keybinds':
                    continue

                if not mouse_keys_enabled and action_lower in mouse_key_actions:
                    continue

                ignore_numlock = get_config_boolean(config, 'IgnoreNumlock', False)
                if action_lower in ['fire', 'target'] and not (ignore_numlock or numlock_on):
                    continue
                
                # *** MODIFIED LOGIC STARTS HERE ***
                key_pressed = False
                if action_lower in mouse_key_actions:
                    # For movement, use the lenient check that ignores extra modifiers
                    key_pressed = is_key_combination_pressed_ignore_extra_mods(key_combo)
                else:
                    # For all other actions, use the strict, exact-match check
                    key_pressed = is_key_combination_pressed(key_combo)

                key_state_key = key_combo
                
                if key_pressed != key_state.get(key_state_key, False):
                    key_state[key_state_key] = key_pressed
                    if key_pressed:
                        action_handler = action_handlers.get(action_lower)
                        if action_handler:
                            try:
                                action_handler()
                            except Exception as e:
                                print(f"Error executing action {action_lower}: {e}")
                    else:
                        # Handle key release for fire/target actions
                        if action_lower in ['fire', 'target']:
                            # Parse the combination to get the main key
                            modifiers, main_key = parse_key_combination(key_combo)
                            if main_key in ['lctrl', 'rctrl']:  # Only for ctrl keys
                                (left_mouse_up if action_lower == 'fire' else right_mouse_up)()
        
        # Reduced sleep time for faster shutdown response
        time.sleep(0.005)

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
    try:
        from lib.guis.config_gui import launch_config_gui
        
        global config
        config_instance = Config()
        config_instance.config = config

        def update_callback(updated_config_parser):
            global config
            config = updated_config_parser
            
            with open('config/config.txt', 'w') as f:
                config.write(f)
                
            reload_config()
            
            # Notify monitors of config changes
            if storm_monitor.running:
                storm_monitor.stop_monitoring()
                storm_monitor.start_monitoring()
                
            print("Configuration updated and saved to disk")
        
        launch_config_gui(config_instance, update_callback)
        
    except Exception as e:
        print(f"Error opening config GUI: {e}")
        speaker.speak("Error opening configuration GUI")

# POI selector GUI has been removed - use virtual POI selector with cycle_poi() instead

def handle_custom_poi_gui(use_ppi=False) -> None:
    """Handle custom POI GUI creation with map-specific support"""
    try:
        from lib.guis.custom_poi_gui import launch_custom_poi_creator
        
        global config
        current_map = config.get('POI', 'current_map', fallback='main')
        
        use_ppi = check_for_pixel()
        
        class PlayerDetector:
            def get_player_position(self, use_ppi_flag):
                from lib.detection.player_position import find_player_position as find_map_player_pos, find_player_icon_location
                return find_map_player_pos() if use_ppi_flag else find_player_icon_location()
        
        launch_custom_poi_creator(use_ppi, PlayerDetector(), current_map)
        
    except Exception as e:
        print(f"Error opening custom POI GUI: {e}")
        speaker.speak("Error opening custom POI creator")

def open_gamemode_selector() -> None:
    """Open the gamemode selector GUI with Epic auth for advanced features."""
    global gamemode_gui_open

    # Check if gamemode GUI is already open
    if gamemode_gui_open.is_set():
        speaker.speak("Gamemode selector is already open")
        return

    try:
        from lib.guis.gamemode_gui import launch_gamemode_selector
        from lib.utilities.epic_auth import get_epic_auth_instance

        # Get Epic auth instance for advanced discovery features
        epic_auth = None
        try:
            epic_auth = get_epic_auth_instance()
        except Exception as e:
            logger.debug(f"Epic auth not available for gamemode selector: {e}")

        gamemode_gui_open.set()
        try:
            launch_gamemode_selector(epic_auth=epic_auth)
        finally:
            gamemode_gui_open.clear()

    except Exception as e:
        print(f"Error opening gamemode selector: {e}")
        speaker.speak("Error opening gamemode selector")
        gamemode_gui_open.clear()

def open_locker_selector() -> None:
    """Open the unified locker GUI for browsing and equipping cosmetics."""
    global active_pinger, locker_gui_open

    # Check if locker GUI is already open
    if locker_gui_open.is_set():
        speaker.speak("Locker is already open")
        return

    if active_pinger:
        active_pinger.stop()
        active_pinger = None
        speaker.speak("Continuous ping disabled.")
    try:
        from lib.guis.locker_gui import launch_locker_gui
        locker_gui_open.set()
        try:
            launch_locker_gui()
        finally:
            locker_gui_open.clear()

    except Exception as e:
        print(f"Error opening locker: {e}")
        speaker.speak("Error opening locker")
        locker_gui_open.clear()

def open_locker_viewer() -> None:
    """Open the unified locker GUI for browsing and equipping cosmetics."""
    global active_pinger, locker_gui_open

    # Check if locker GUI is already open
    if locker_gui_open.is_set():
        speaker.speak("Locker is already open")
        return

    if active_pinger:
        active_pinger.stop()
        active_pinger = None
        speaker.speak("Continuous ping disabled.")
    try:
        from lib.guis.locker_gui import launch_locker_gui
        locker_gui_open.set()
        try:
            launch_locker_gui()
        finally:
            locker_gui_open.clear()

    except Exception as e:
        print(f"Error opening locker: {e}")
        speaker.speak("Error opening locker")
        locker_gui_open.clear()

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

    n = (poi_name or '').strip().lower()
    if n.startswith('closest '):
        try:
            types = {t.lower() for t in game_object_manager.get_available_object_types(current_map)}
            if n.replace('closest ', '', 1).strip() in types:
                return POI_CATEGORY_GAMEOBJECT
        except Exception:
            pass
    
    # Check special POIs first
    if poi_name.lower() == SPECIAL_POI_CLOSEST.lower():
        return POI_CATEGORY_SPECIAL
    
    if poi_name.lower() == SPECIAL_POI_SAFEZONE.lower():
        return POI_CATEGORY_SPECIAL
    
    if poi_name.lower() == SPECIAL_POI_CLOSEST_LANDMARK.lower() and current_map == 'main':
        return POI_CATEGORY_SPECIAL
    
    # Check favorites
    favorites_file = 'config/FAVORITE_POIS.txt'
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
    game_object_types = game_object_manager.get_available_object_types(current_map)
    for obj_type in game_object_types:
        objects = game_object_manager.get_objects_of_type(current_map, obj_type)
        if any(obj[0].lower() == poi_name.lower() for obj in objects):
            return POI_CATEGORY_GAMEOBJECT
    
    # Check dynamic objects
    # dynamic_objects = get_dynamic_objects()
    # if any(poi[0].lower() == poi_name.lower() for poi in dynamic_objects):
    #     return POI_CATEGORY_DYNAMICOBJECT
    
    # Check landmarks (main map only)
    if current_map == 'main':
        if poi_data_instance is None:
            poi_data_instance = POIData()
        poi_data_instance._ensure_api_data_loaded()
        if any(poi[0].lower() == poi_name.lower() for poi in poi_data_instance.landmarks):
            return POI_CATEGORY_LANDMARK
    
    # Default to regular
    return POI_CATEGORY_REGULAR

'''
def get_dynamic_objects() -> List[Tuple[str, str, str]]:
    """Get dynamic objects from icons folder"""
    dynamic_objects = []
    icons_folder = 'icons'
    
    if os.path.exists(icons_folder):
        try:
            for filename in os.listdir(icons_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    object_name = os.path.splitext(filename)[0]
                    display_name = object_name.replace('_', ' ').title()
                    dynamic_objects.append((display_name, "0", "0"))
        except Exception as e:
            print(f"Error loading dynamic objects: {e}")
    
    return sorted(dynamic_objects, key=lambda x: x[0])
'''

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
        special_pois = [(SPECIAL_POI_CLOSEST, "0", "0"), (SPECIAL_POI_SAFEZONE, "0", "0")]
        if current_map == 'main':
            special_pois.append((SPECIAL_POI_CLOSEST_LANDMARK, "0", "0"))
        return special_pois
    
    # Favorites
    if category == POI_CATEGORY_FAVORITE:
        favorites_file = 'config/FAVORITE_POIS.txt'
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
    
    # Game Objects (from new game objects system) - sorted alphabetically
    if category == POI_CATEGORY_GAMEOBJECT:
        # Get all available object types for current map
        available_types = game_object_manager.get_available_object_types(current_map)
        
        # Sort types alphabetically
        ordered_types = sorted(available_types)
        
        return [(f"Closest {t}", "0", "0") for t in ordered_types]
    
    # Landmarks (main map only)
    if category == POI_CATEGORY_LANDMARK and current_map == 'main':
        if poi_data_instance is None:
            poi_data_instance = POIData()
        poi_data_instance._ensure_api_data_loaded()
        return poi_data_instance.landmarks
    
    # Regular POIs
    if category == POI_CATEGORY_REGULAR:
        if poi_data_instance is None:
            poi_data_instance = POIData()
            
        if current_map == 'main':
            poi_data_instance._ensure_api_data_loaded()
            return poi_data_instance.main_pois
        elif current_map in poi_data_instance.maps:
            poi_data_instance._ensure_map_data_loaded(current_map)
            return poi_data_instance.maps[current_map].pois
    
    return []

def get_display_poi_name(poi_name: str) -> str:
    """
    Get display-friendly POI name by removing 'Closest ' prefix from game objects only
    
    Args:
        poi_name: Original POI name
        
    Returns:
        str: Clean POI name for display/speech
    """
    # Only strip "Closest " from game objects, not from other POI types
    poi_category = get_poi_category(poi_name)
    if poi_category == POI_CATEGORY_GAMEOBJECT and poi_name.startswith("Closest "):
        return poi_name[8:]  # Remove "Closest " (8 characters)
    return poi_name

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
    if pois[0][0].lower() in [SPECIAL_POI_CLOSEST.lower(), SPECIAL_POI_SAFEZONE.lower(), SPECIAL_POI_CLOSEST_LANDMARK.lower()]:
        return pois
    
    # Don't sort game objects (they have coordinates "0", "0") - they are already ordered by config
    if all(poi[1] == "0" and poi[2] == "0" for poi in pois):
        return pois  # Keep the config-based ordering for game objects
    
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
    
    # Add dynamic objects if any exist
    # dynamic_objects = get_pois_by_category(POI_CATEGORY_DYNAMICOBJECT)
    # if include_empty or dynamic_objects:
    #     categories.append(POI_CATEGORY_DYNAMICOBJECT)
    
    # Add favorites if any exist
    favorites = get_pois_by_category(POI_CATEGORY_FAVORITE)
    if include_empty or favorites:
        categories.append(POI_CATEGORY_FAVORITE)
    
    # Add custom POIs if any exist
    custom_pois = get_pois_by_category(POI_CATEGORY_CUSTOM)
    if include_empty or custom_pois:
        categories.append(POI_CATEGORY_CUSTOM)
    
    return categories

def cycle_poi_category(direction: str = "forwards") -> None:
    """Cycle between POI categories with safe config handling"""
    global config, poi_data_instance, current_poi_category, active_pinger
    if active_pinger:
        active_pinger.stop()
        active_pinger = None
        speaker.speak("Continuous ping disabled.")
    
    try:
        # Always re-read the config to ensure we have the latest state
        clear_config_cache()
        config = read_config(use_cache=False)
        
        # Validate POI data is initialized
        if poi_data_instance is None:
            poi_data_instance = POIData()
        
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
        if direction == "backwards":
            new_index = (current_index - 1) % len(categories)
        else:  # forwards
            new_index = (current_index + 1) % len(categories)
        
        # Get new category
        new_category = categories[new_index]
        
        # Update global category tracker
        current_poi_category = new_category
        
        # Get POIs in the new category
        category_pois = get_pois_by_category(new_category)
        
        # Sort POIs by position (preserves config order for game objects)
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
                    POI_CATEGORY_GAMEOBJECT: "Game Object",
                    # POI_CATEGORY_DYNAMICOBJECT: "Dynamic Object"
                }
                display_name = category_display_names.get(new_category, new_category.title())
                
                # Get position description if not a special POI or game object
                position_desc = ""
                if (first_poi[0].lower() not in [SPECIAL_POI_CLOSEST.lower(), SPECIAL_POI_SAFEZONE.lower(), 
                                                SPECIAL_POI_CLOSEST_LANDMARK.lower()] 
                    and first_poi[1] != "0" and first_poi[2] != "0"):
                    position_desc = get_poi_position_description(first_poi)
                    if position_desc:
                        position_desc = f", {position_desc}"
                
                # Announce selection
                display_poi_name = get_display_poi_name(first_poi[0])
                speaker.speak(f"{display_name} POIs: {display_poi_name}{position_desc}")
            else:
                speaker.speak("Error saving POI selection")
        else:
            speaker.speak(f"No POIs available in the selected category")
            
    except Exception as e:
        print(f"Error cycling POI category: {e}")
        speaker.speak("Error cycling POI categories")

def cycle_poi(direction: str = "forwards") -> None:
    """Cycle through POIs in the current category with safe config handling"""
    global config, poi_data_instance, current_poi_category, active_pinger
    if active_pinger:
        active_pinger.stop()
        active_pinger = None
        speaker.speak("Continuous ping disabled.")
    
    try:
        # Always re-read the config to ensure we have the latest state
        clear_config_cache()
        config = read_config(use_cache=False)
        
        if poi_data_instance is None:
            poi_data_instance = POIData()
        
        # Get POIs in the current category
        category_pois = get_pois_by_category(current_poi_category)
        
        # If no POIs in the category, notify user
        if not category_pois:
            speaker.speak("No POIs available in the current category")
            return
        
        # Sort POIs by position (preserves config order for game objects)
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
        if direction == "backwards":
            new_index = (current_index - 1) % len(sorted_pois)
        else:  # forwards
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
                                          SPECIAL_POI_CLOSEST_LANDMARK.lower()] 
                and new_poi[1] != "0" and new_poi[2] != "0"):
                position_desc = get_poi_position_description(new_poi)
                if position_desc:
                    position_desc = f", {position_desc}"
            
            # Announce selection
            display_poi_name = get_display_poi_name(new_poi[0])
            speaker.speak(f"{display_poi_name}{position_desc}")
        else:
            speaker.speak("Error saving POI selection")
            
    except Exception as e:
        print(f"Error cycling POI: {e}")
        speaker.speak("Error cycling POIs")

def cycle_map(direction: str = "forwards"):
    """Cycle to the next/previous map with safe config handling"""
    global config, poi_data_instance, current_poi_category, active_pinger
    if active_pinger:
        active_pinger.stop()
        active_pinger = None
        speaker.speak("Continuous ping disabled.")
    
    try:
        # Always re-read the config to ensure we have the latest state
        clear_config_cache()
        config = read_config(use_cache=False)
        
        if poi_data_instance is None:
            poi_data_instance = POIData()

        # Get the current map from config
        current_map = config.get('POI', 'current_map', fallback='main')
        
        # Get a sorted list of all available maps
        all_maps = sorted(poi_data_instance.maps.keys())
        
        # Find the index of the current map
        try:
            current_index = all_maps.index(current_map)
        except ValueError:
            current_index = 0
        
        # Calculate the new index with wrapping
        if direction == "backwards":
            new_index = (current_index - 1) % len(all_maps)
        else:  # forwards
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
    """Periodically check for updates with shutdown awareness."""
    update_notified = False

    while not _shutdown_requested.is_set():
        # Check for shutdown request every second during the 6-second wait
        for _ in range(60):  # 6 seconds = 60 * 0.1 second checks
            if _shutdown_requested.is_set():
                return
            time.sleep(0.1)
        
        # Only check for updates if not shutting down
        if _shutdown_requested.is_set():
            return

        local_version = None
        if os.path.exists('VERSION'):
            with open('VERSION', 'r') as f:
                local_version = f.read().strip()

        remote_version = get_version()

        if not local_version:
            pass  # Reduce spam
        elif not remote_version:
            pass  # Reduce spam
        else:
            try:
                local_v = parse_version(local_version)
                remote_v = parse_version(remote_version)
                if local_v != remote_v:
                    if not update_notified and not _shutdown_requested.is_set():
                        update_sound.play()
                        speaker.speak("An update is available for FA11y! Restart FA11y to update!")
                        print("An update is available for FA11y! Restart FA11y to update!")
                        update_notified = True
                else:
                    update_notified = False
            except ValueError:
                pass  # Reduce spam

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

def validate_epic_auth(epic_auth) -> bool:
    """
    Validate Epic auth token with a test API request

    Args:
        epic_auth: EpicAuth instance to validate

    Returns:
        True if token is valid, False otherwise
    """
    if not epic_auth or not epic_auth.access_token:
        return False

    try:
        import requests
        # Make a lightweight API request to test the token
        response = requests.get(
            f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{epic_auth.account_id}",
            headers={'Authorization': f'Bearer {epic_auth.access_token}'},
            timeout=5
        )

        if response.status_code == 401:
            logger.info("Epic auth token expired (401 response)")
            return False
        elif response.status_code == 200:
            logger.info("Epic auth token validated successfully")
            return True
        else:
            logger.warning(f"Unexpected status during auth validation: {response.status_code}")
            # For other errors, assume token might still be valid
            return True

    except Exception as e:
        logger.warning(f"Error validating Epic auth token: {e}")
        # If we can't validate, assume valid to avoid blocking
        return True

def main() -> None:
    """Main entry point for FA11y with instant shutdown capability."""
    global config, action_handlers, key_bindings, key_listener_thread, stop_key_listener, social_manager
    try:
        print("Starting FA11y...")
        
        # Register shutdown handlers early
        register_shutdown_handlers()

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

        # Start key listener thread as daemon
        stop_key_listener.clear()
        key_listener_thread = threading.Thread(target=key_listener, daemon=True)
        key_listener_thread.start()

        # Start update checker thread as daemon
        update_thread = threading.Thread(target=check_for_updates, daemon=True)
        update_thread.start()

        # Start auxiliary systems - all as daemon threads
        threading.Thread(target=start_height_monitor, daemon=True).start()
        
        # Start monitoring systems
        monitor.start_monitoring()
        material_monitor.start_monitoring()
        resource_monitor.start_monitoring()
        # dynamic_object_monitor.start_monitoring()
        storm_monitor.start_monitoring()

        # Start new game object system
        match_tracker.start_monitoring()

        # Auto-start a new match
        match_tracker._start_new_match()

        # Initialize hotbar detection
        initialize_hotbar_detection()

        # Initialize Epic authentication and social features
        try:
            from lib.utilities.epic_auth import get_epic_auth_instance
            from lib.guis.epic_login_dialog import LoginDialog

            epic_auth = get_epic_auth_instance()

            # Validate auth token (checks if exists and if valid via API request)
            if not validate_epic_auth(epic_auth):
                print("Epic Games authentication required for social features")
                speaker.speak("Epic Games authentication required. Opening login dialog.")

                # Show login dialog
                app = wx.App()
                login_dialog = LoginDialog(None, epic_auth)
                login_dialog.ShowModal()
                authenticated = login_dialog.authenticated
                login_dialog.Destroy()
                app.Destroy()

                if not authenticated:
                    print("Social features disabled: Authentication cancelled")
                    speaker.speak("Social features disabled")
                    epic_auth = None
                else:
                    # Refresh auth instance after login
                    epic_auth = get_epic_auth_instance()

            # Start social manager and other Epic auth-dependent features
            if epic_auth and epic_auth.access_token:
                social_manager = get_social_manager(epic_auth)
                social_manager.start_monitoring()
                print(f"Social features enabled for {epic_auth.display_name}")
                speaker.speak(f"Social features enabled for {epic_auth.display_name}")
            else:
                print("Social features disabled: Not authenticated")

        except Exception as e:
            print(f"Social features disabled: {e}")
            logger.warning(f"Failed to initialize social features: {e}")

        '''
        # Print available dynamic objects for reference (reduced spam)
        dynamic_objects = get_dynamic_object_configs()
        if dynamic_objects:
            print(f"Dynamic object monitoring configured for {len(dynamic_objects)} object types")
            '''

        # Print game objects info (reduced spam)
        config = read_config()
        current_map = config.get('POI', 'current_map', fallback='main')
        game_object_types = game_object_manager.get_available_object_types(current_map)
        if game_object_types:
            print(f"Game objects available on {current_map} map: {len(game_object_types)} types")

        # Notify user and wait for input with immediate response capability
        speaker.speak("FA11y is now running in the background. Press Enter in this window to stop FA11y.")
        print("FA11y is now running in the background. Press Enter in this window to stop FA11y.")
        
        # Use a loop to check for shutdown request while waiting for Enter key
        if sys.platform == 'win32':
            # Windows - use msvcrt for non-blocking input, but only respond to Enter
            import msvcrt
            while not _shutdown_requested.is_set():
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    # Only exit on Enter key (carriage return)
                    if key == b'\r' or key == b'\n':
                        break
                    # Ignore all other keys (including Escape)
                time.sleep(0.1)
        else:
            input()

    except KeyboardInterrupt:
        # Handle CTRL+C gracefully
        _shutdown_requested.set()
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        speaker.speak(f"An error occurred: {str(e)}")
    finally:
        # Set shutdown flag
        _shutdown_requested.set()
        
        # Minimal cleanup - no waiting for threads since they're daemon threads
        stop_key_listener.set()
        
        # Quick resource cleanup
        try:
            # Stop monitoring systems without waiting
            monitor.stop_monitoring()
            material_monitor.stop_monitoring()
            resource_monitor.stop_monitoring()
            # dynamic_object_monitor.stop_monitoring()
            storm_monitor.stop_monitoring()
            match_tracker.stop_monitoring()

            # Stop social manager
            if social_manager:
                social_manager.stop_monitoring()

            # Clean up object detection resources
            cleanup_object_detection()
            
            # Clean up pygame mixer
            if pygame.mixer.get_init():
                pygame.mixer.quit()
        except:
            pass  # Ignore cleanup errors during shutdown

        print("FA11y is closing...")
        # Use os._exit for immediate termination
        os._exit(0)

if __name__ == "__main__":
    main()