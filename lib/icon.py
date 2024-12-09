import cv2
import time
import keyboard
import numpy as np
import pyautogui
import configparser
from typing import List, Tuple, Optional, Union
from accessible_output2.outputs.auto import Auto
from lib.storm import start_storm_detection
from lib.object_finder import OBJECT_CONFIGS, find_closest_object
from lib.guis.poi_selector_gui import POIData
from lib.minimap_direction import find_minimap_icon_direction
from lib.mouse import smooth_move_mouse
from lib.spatial_audio import SpatialAudio
from lib.player_location import (
    find_player_icon_location,
    find_player_icon_location_with_direction,
    get_player_position_description,
    calculate_poi_info,
    generate_poi_message,
    ROI_START_ORIG,
    ROI_END_ORIG,
    SCALE_FACTOR,
    MIN_AREA,
    MAX_AREA
)
from lib.ppi import find_player_position, get_player_position_description
from lib.utilities import get_config_boolean, get_config_float
from lib.custom_poi_handler import update_poi_handler

# Initialize spatial audio for POI sound
spatial_poi = SpatialAudio('sounds/poi.ogg')

pyautogui.FAILSAFE = False
speaker = Auto()

GAME_OBJECTS = [(name.replace('_', ' ').title(), "0", "0") for name in OBJECT_CONFIGS.keys()]
SPECIAL_POIS = [("Safe Zone", "0", "0"), ("Closest", "0", "0")]

def find_closest_poi(icon_location, poi_list):
    """Find closest POI to the player's location."""
    if not icon_location or not poi_list:
        print(f"find_closest_poi: Missing required data - location: {icon_location}, poi count: {len(poi_list) if poi_list else 0}")
        return None, None
    
    print(f"Finding closest POI from {len(poi_list)} POIs")
    print(f"Player location: {icon_location}")
    
    distances = []
    for poi, x, y in poi_list:
        try:
            coord_x = int(float(x))
            coord_y = int(float(y))
            distance = np.linalg.norm(
                np.array(icon_location) - np.array([coord_x, coord_y])
            ) * 3.25  # Scale factor
            distances.append((poi, (coord_x, coord_y), distance))
            print(f"Distance to {poi}: {distance:.2f}")
        except (ValueError, TypeError) as e:
            print(f"Error processing POI {poi}: {e}")
            continue
            
    if not distances:
        print("No valid POIs found")
        return None, None
        
    closest = min(distances, key=lambda x: x[2])
    print(f"Selected closest POI: {closest[0]} at ({closest[1][0]}, {closest[1][1]})")
    return closest[0], closest[1]

def load_config():
    config = configparser.ConfigParser()
    config.read('CONFIG.txt')
    try:
        return tuple(config['POI']['selected_poi'].split(', '))
    except (KeyError, configparser.NoSectionError):
        return ('none', '0', '0')

def load_selected_map():
    """Load the last selected map from config."""
    config = configparser.ConfigParser()
    config.read('CONFIG.txt')
    try:
        return config.get('MAP', 'last_selected_map', fallback='main')
    except (configparser.NoSectionError, configparser.NoOptionError):
        return 'main'

def get_poi_from_map_data(poi_name, map_data):
    """Find POI in map data's POIs and landmarks."""
    # First check POIs
    for poi in map_data.pois:
        if poi[0].lower() == poi_name.lower():
            return poi[0], (int(float(poi[1])), int(float(poi[2])))
            
    # Then check landmarks
    for poi in map_data.landmarks:
        if poi[0].lower() == poi_name.lower():
            return poi[0], (int(float(poi[1])), int(float(poi[2])))
            
    return None

def handle_poi_selection(selected_poi, center_mass_screen, use_ppi=False):
    """
    Handle POI selection and coordinate processing.

    Args:
        selected_poi: String or tuple containing POI name and coordinates
        center_mass_screen: Current player coordinates or None
        use_ppi: Whether to use PPI for position detection

    Returns:
        Tuple (POI name, coordinates) or (None, None) if not found
    """
    print(f"Handling POI selection: {selected_poi}")
    poi_data = POIData()
    
    # Extract POI name from tuple or string
    poi_name = selected_poi[0].lower() if isinstance(selected_poi, tuple) else selected_poi.lower()

    # Handle closest POI selection
    if poi_name == 'closest':
        if center_mass_screen:
            print(f"Finding closest POI from player position: {center_mass_screen}")
            all_pois = [(poi[0], int(float(poi[1])), int(float(poi[2]))) 
                       for poi in poi_data.main_pois]
            return find_closest_poi(center_mass_screen, all_pois)
        else:
            print("Deferring closest POI calculation until player position is available")
            return ("RECALCULATE_CLOSEST", None)
    
    # Handle safe zone detection
    elif poi_name == 'safe zone':
        print("Detecting safe zone")
        return 'Safe Zone', start_storm_detection()
    
    # Handle closest landmark detection
    elif poi_name == 'closest landmark':
        print("Finding closest landmark")
        if center_mass_screen:
            landmarks = [(poi[0], int(float(poi[1])), int(float(poi[2]))) 
                        for poi in poi_data.landmarks]
            return find_closest_poi(center_mass_screen, landmarks)
        return "Closest Landmark", None

    # Handle game objects
    if poi_name in OBJECT_CONFIGS or poi_name.replace(' ', '_') in OBJECT_CONFIGS:
        print(f"Detecting game object: {poi_name}")
        object_name = poi_name if poi_name in OBJECT_CONFIGS else poi_name.replace(' ', '_')
        icon_path, threshold = OBJECT_CONFIGS[object_name]
        result = find_closest_object(icon_path, threshold)
        return (poi_name.title(), result) if result else (poi_name.title(), None)

    # Handle regular POIs
    for poi in poi_data.main_pois:
        if poi[0].lower() == poi_name:
            return poi[0], (int(float(poi[1])), int(float(poi[2])))
    
    for poi in poi_data.landmarks:
        if poi[0].lower() == poi_name:
            return poi[0], (int(float(poi[1])), int(float(poi[2])))
    
    print(f"POI '{selected_poi}' not found")
    return selected_poi, None


def perform_poi_actions(poi_data, center_mass_screen, speak_info=True, use_ppi=False):
    poi_name, coordinates = poi_data
    print(f"Performing actions for POI: {poi_name}, Coordinates: {coordinates}")

    if coordinates and len(coordinates) == 2:
        x, y = coordinates
        try:
            if center_mass_screen and speak_info:
                process_screenshot((int(x), int(y)), poi_name, center_mass_screen, use_ppi)
            elif not speak_info:
                print(f"Clicked on {poi_name}. Info will be spoken after auto-turn.")
        except ValueError:
            print(f"Error: Invalid POI coordinates for {poi_name}: {x}, {y}")
            speaker.speak(f"Error: Invalid POI coordinates for {poi_name}")
    else:
        print(f"Error: Invalid POI location for {poi_name}")
        speaker.speak(f"Error: Invalid POI location for {poi_name}")

def process_screenshot(selected_coordinates, poi_name, center_mass_screen, use_ppi=False):
    if use_ppi:
        location = find_player_position()
        _, angle = find_minimap_icon_direction()
    else:
        location, angle = find_player_icon_location_with_direction()
    
    if location is not None:
        poi_info = calculate_poi_info(location, angle, selected_coordinates)
        message = generate_poi_message(poi_name, angle, poi_info)
        print(message)
        speaker.speak(message)
    else:
        method = "PPI" if use_ppi else "player icon"
        print(f"Player location not found using {method}.")
        speaker.speak(f"Player location not found using {method}.")

def play_spatial_poi_sound(player_position, player_angle, poi_location):
    """Play spatial POI sound based on relative position."""
    if player_position and poi_location and player_angle is not None:
        # Calculate vector from player to POI
        poi_vector = np.array(poi_location) - np.array(player_position)
        distance = np.linalg.norm(poi_vector) * 2.65
        
        # Calculate angle to POI
        poi_angle = np.degrees(np.arctan2(-poi_vector[1], poi_vector[0]))
        poi_angle = (90 - poi_angle) % 360
        
        # Calculate relative angle from player's facing direction
        relative_angle = (poi_angle - player_angle + 180) % 360 - 180
        
        # Calculate left/right weights based on relative angle
        pan = np.clip(relative_angle / 90, -1, 1)
        left_weight = np.clip((1 - pan) / 2, 0, 1)
        right_weight = np.clip((1 + pan) / 2, 0, 1)
        
        # Get volume settings from config
        config = configparser.ConfigParser()
        config.read('config.txt')
        min_volume = get_config_float(config, 'MinimumPOIVolume', 0.05)
        max_volume = get_config_float(config, 'MaximumPOIVolume', 1.0)
        
        # Calculate volume based on distance
        volume = max(min_volume, min(max_volume, 1 - (distance / 1000)))
        
        # Play the spatial sound
        spatial_poi.play_audio(
            left_weight=left_weight,
            right_weight=right_weight,
            volume=volume
        )

def get_player_info(use_ppi):
    """Get player location and angle using either PPI or normal icon detection."""
    if use_ppi:
        player_location = find_player_position()
        if player_location is None:
            return None, None
        _, player_angle = find_minimap_icon_direction()
        return player_location, player_angle
    else:
        return find_player_icon_location_with_direction()

def start_icon_detection(use_ppi=False):
    """Start icon detection with universal spatial sound support."""
    print("Starting icon detection")
    config = configparser.ConfigParser()
    config.read('config.txt')
    
    # Parse the stored POI data properly
    stored_poi = config['POI']['selected_poi'].strip() if 'POI' in config else 'none'
    if stored_poi.lower() != 'none':
        # Split the stored POI string into components
        parts = [part.strip() for part in stored_poi.split(',')]
        if len(parts) == 3:
            # Reconstruct as tuple with proper types
            selected_poi = (parts[0], parts[1], parts[2])
        else:
            selected_poi = stored_poi
    else:
        selected_poi = 'none'
    
    print(f"Read from config: {selected_poi}")
    
    icon_detection_cycle(selected_poi, use_ppi)

def icon_detection_cycle(selected_poi, use_ppi):
    """
    Main cycle for POI detection and navigation.

    Args:
        selected_poi: POI to navigate to
        use_ppi: Whether to use PPI for position detection
    """
    print(f"Icon detection cycle started. Selected POI: {selected_poi}, Using PPI: {use_ppi}")
    
    # Get player position first
    if use_ppi:
        player_location = find_player_position()
        player_angle = None
        if player_location is None:
            print("Could not find player position using PPI")
            speaker.speak("Could not find player position using PPI")
            return
    else:
        player_info = find_player_icon_location_with_direction()
        if player_info is None:
            print("Could not find player icon or determine direction")
            speaker.speak("Could not find player icon")
            return
        player_location, player_angle = player_info

    print(f"Found player at position: {player_location}")

    # Get POI information with player position
    poi_data = handle_poi_selection(selected_poi, player_location, use_ppi)
    print(f"Initial POI data: {poi_data}")

    # Handle closest POI recalculation if needed
    if poi_data[0] == "RECALCULATE_CLOSEST":
        print("Recalculating closest POI with player position")
        poi_data = handle_poi_selection(("Closest", "0", "0"), player_location, use_ppi)
        print(f"Recalculated POI data: {poi_data}")

    # Check if POI was found
    if poi_data[1] is None:
        print(f"{poi_data[0]} not located.")
        speaker.speak(f"{poi_data[0]} not located.")
        return

    # Handle clicking for non-PPI mode
    if not use_ppi:
        pyautogui.moveTo(poi_data[1][0], poi_data[1][1])
        pyautogui.rightClick()
        pyautogui.click()

    # Get final angle if needed
    if player_angle is None:
        _, player_angle = find_minimap_icon_direction()

    # Play spatial POI sound if enabled and have required data
    config = configparser.ConfigParser()
    config.read('CONFIG.txt')
    play_sound = get_config_boolean(config, 'PlayPOISound', True)
    if play_sound and player_angle is not None and player_location is not None:
        play_spatial_poi_sound(player_location, player_angle, poi_data[1])

    # Perform POI actions
    perform_poi_actions(poi_data, player_location, speak_info=False)
    
    # Handle auto-turning
    auto_turn_enabled = get_config_boolean(config, 'AutoTurn', False)
    
    if auto_turn_enabled:
        if not use_ppi:
            pyautogui.press('escape')
            time.sleep(0.1)
        success = auto_turn_towards_poi(player_location, poi_data[1], poi_data[0])
    else:
        success = False

    # Get final angle and announce result
    _, latest_angle = find_minimap_icon_direction()
    if latest_angle is None:
        print("Unable to determine final player direction. Using initial direction.")
        latest_angle = player_angle

    speak_auto_turn_result(poi_data[0], player_location, latest_angle, poi_data[1], auto_turn_enabled, success)

def speak_auto_turn_result(poi_name, player_location, player_angle, poi_location, auto_turn_enabled, success):
    poi_info = calculate_poi_info(player_location, player_angle, poi_location)
    message = generate_poi_message(poi_name, player_angle, poi_info)

    print(message)
    speaker.speak(message)

def auto_turn_towards_poi(player_location, poi_location, poi_name):
    max_attempts = 30
    base_turn_speed, max_turn_speed = 200, 500
    angle_threshold = 5
    sensitivity = 1.0
    min_sensitivity = 0.6
    consecutive_failures = 0

    for attempts in range(max_attempts):
        current_direction, current_angle = find_minimap_icon_direction()
        if current_direction is None or current_angle is None:
            consecutive_failures += 1
            
            if attempts < 3 and consecutive_failures == 3:
                print("Failed to determine direction for the first three consecutive attempts. Stopping AutoTurn.")
                return False
            
            time.sleep(0.1)
            continue
        
        consecutive_failures = 0
        
        if player_location:
            poi_vector = np.array(poi_location) - np.array(player_location)
            poi_angle = (450 - np.degrees(np.arctan2(-poi_vector[1], poi_vector[0]))) % 360
        else:
            poi_angle = 0
        
        angle_difference = (poi_angle - current_angle + 180) % 360 - 180
        
        if attempts % 5 == 0 or abs(angle_difference) <= angle_threshold:
            print(f"Current angle: {current_angle:.2f}, POI angle: {poi_angle:.2f}, Difference: {angle_difference:.2f}")
        
        if abs(angle_difference) <= angle_threshold:
            print(f"Successfully turned towards {poi_name}. Current direction: {current_direction}")
            return True
        
        turn_speed = min(base_turn_speed + (abs(angle_difference) * 2), max_turn_speed)
        turn_amount = min(abs(angle_difference), 90)
        turn_direction = 1 if angle_difference > 0 else -1
        
        smooth_move_mouse(int(turn_amount * turn_direction * (turn_speed / 100)), 0, 0.01)
        time.sleep(0.05)

    print(f"Failed to turn towards {poi_name} after maximum attempts.")
    return False
