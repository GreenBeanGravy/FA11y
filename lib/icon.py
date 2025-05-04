import cv2
import time
import keyboard
import numpy as np
import pyautogui
import configparser
from accessible_output2.outputs.auto import Auto
from lib.storm import start_storm_detection
from lib.object_finder import OBJECT_CONFIGS, find_closest_object
from lib.guis.poi_selector_gui import POIData
from lib.player_position import (
    get_player_info,
    find_minimap_icon_direction,
    calculate_poi_info,
    generate_poi_message,
    get_player_position_description,
    ROI_START_ORIG,
    ROI_END_ORIG
)
from lib.spatial_audio import SpatialAudio
from lib.mouse import smooth_move_mouse
from lib.utilities import get_config_boolean, get_config_float
from lib.custom_poi_handler import update_poi_handler

# Initialize spatial audio for POI sound
spatial_poi = SpatialAudio('sounds/poi.ogg')

pyautogui.FAILSAFE = False
speaker = Auto()

GAME_OBJECTS = [(name.replace('_', ' ').title(), "0", "0") for name in OBJECT_CONFIGS.keys()]
SPECIAL_POIS = [("Safe Zone", "0", "0"), ("Closest", "0", "0")]

def find_closest_poi(icon_location, poi_list):
    if not icon_location or not poi_list:
        return None, None
    
    distances = []
    for poi, x, y in poi_list:
        try:
            coord_x = int(float(x))
            coord_y = int(float(y))
            distance = np.linalg.norm(
                np.array(icon_location) - np.array([coord_x, coord_y])
            ) * 3.25
            distances.append((poi, (coord_x, coord_y), distance))
        except (ValueError, TypeError):
            continue
            
    closest = min(distances, key=lambda x: x[2], default=(None, None, float('inf')))
    return closest[0], closest[1]

def load_config():
    config = configparser.ConfigParser()
    config.read('CONFIG.txt')
    try:
        return tuple(config['POI']['selected_poi'].split(', '))
    except (KeyError, configparser.NoSectionError):
        return ('none', '0', '0')

def handle_poi_selection(selected_poi, center_mass_screen, use_ppi=False):
    print(f"Handling POI selection: {selected_poi}")
    poi_data = POIData()
    
    # Get current map from config
    config = configparser.ConfigParser()
    config.read('CONFIG.txt')
    current_map_value = config.get('POI', 'current_map', fallback='main')
    
    # Convert the config map name to the correct key in poi_data.maps
    current_map = current_map_value
    if current_map != 'main':
        # Try different map name formats
        map_formats = [
            current_map,                    # Direct match
            f"map_{current_map}",           # map_X format
            f"map_{current_map}_pois"       # map_X_pois format
        ]
        
        for format in map_formats:
            if format in poi_data.maps:
                current_map = format
                break
        else:
            # For backward compatibility with space-separated names (like "o g")
            for map_key in poi_data.maps.keys():
                if map_key.startswith('map_') and map_key.endswith('_pois'):
                    # Extract the middle portion and replace underscores with spaces
                    middle = map_key[4:-5].replace('_', ' ')
                    if middle == current_map:
                        current_map = map_key
                        break
            else:
                # If no match found, default to main
                print(f"Warning: Map '{current_map}' not found. Using 'main' instead.")
                current_map = 'main'
    
    if isinstance(selected_poi, tuple) and len(selected_poi) == 1:
        selected_poi = selected_poi[0]
    
    # Handle custom POI selection first
    custom_result = update_poi_handler(
        selected_poi[0] if isinstance(selected_poi, tuple) else selected_poi, 
        use_ppi
    )
    if custom_result[0]:
        return custom_result
    
    poi_name = selected_poi[0].lower() if isinstance(selected_poi, tuple) else selected_poi.lower()
    
    if poi_name == 'safe zone':
        print("Detecting safe zone")
        return 'Safe Zone', start_storm_detection()
    elif poi_name == 'closest':
        print(f"Finding closest POI in {current_map} map")
        if center_mass_screen:
            if current_map == "main":
                pois_to_check = [(poi[0], int(float(poi[1])), int(float(poi[2]))) 
                               for poi in poi_data.main_pois]
            else:
                pois_to_check = [(poi[0], int(float(poi[1])), int(float(poi[2]))) 
                               for poi in poi_data.maps[current_map].pois]
            return find_closest_poi(center_mass_screen, pois_to_check)
        else:
            print("Could not determine player location for finding closest POI")
            return "Closest", None
    else:
        # Check current map's POIs first
        if current_map == "main":
            # Use API data for main map
            for poi in poi_data.main_pois:
                if poi[0].lower() == poi_name:
                    return poi[0], (int(float(poi[1])), int(float(poi[2])))
            
            for poi in poi_data.landmarks:
                if poi[0].lower() == poi_name:
                    return poi[0], (int(float(poi[1])), int(float(poi[2])))
        else:
            # Use direct coordinates for other maps
            for poi in poi_data.maps[current_map].pois:
                if poi[0].lower() == poi_name:
                    return poi[0], (int(float(poi[1])), int(float(poi[2])))
    
    print(f"Error: POI '{selected_poi}' not found in map data")
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
    player_location, player_angle = get_player_info(use_ppi)
    
    if player_location is not None:
        poi_info = calculate_poi_info(player_location, player_angle, selected_coordinates)
        message = generate_poi_message(poi_name, player_angle, poi_info)
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
        
        # Calculate stereo panning based on relative angle
        pan = np.clip(relative_angle / 90, -1, 1)
        left_weight = np.clip((1 - pan) / 2, 0, 1)
        right_weight = np.clip((1 + pan) / 2, 0, 1)
        
        # Get volume settings from config
        config = configparser.ConfigParser()
        config.read('config.txt')
        min_volume = get_config_float(config, 'MinimumPOIVolume', 0.05)
        max_volume = get_config_float(config, 'MaximumPOIVolume', 1.0)
        
        # Calculate volume based on distance with new min/max settings
        volume = max(min_volume, min(max_volume, 1 - (distance / 1000)))
        
        # Play the spatial sound
        spatial_poi.play_audio(
            left_weight=left_weight,
            right_weight=right_weight,
            volume=volume
        )

def start_icon_detection(use_ppi=False):
    """Start icon detection with universal spatial sound support."""
    print("Starting icon detection")
    config = configparser.ConfigParser()
    config.read('config.txt')
    selected_poi = config.get('POI', 'selected_poi', fallback='none, 0, 0').split(', ')[0]
    
    # Load spatial sound configuration
    play_poi_sound = get_config_boolean(config, 'PlayPOISound', True)
    
    icon_detection_cycle(selected_poi, use_ppi, play_poi_sound)

def icon_detection_cycle(selected_poi, use_ppi, play_poi_sound=True):
    """Modified icon detection cycle with universal spatial audio support."""
    print(f"Icon detection cycle started. Selected POI: {selected_poi}, Using PPI: {use_ppi}")
    
    if selected_poi.lower() == 'none':
        print("No POI selected.")
        speaker.speak("No POI selected. Please select a POI first.")
        return

    # Get player information
    player_location, player_angle = get_player_info(use_ppi)
    if player_location is None:
        method = "PPI" if use_ppi else "icon detection"
        print(f"Could not find player position using {method}")
        speaker.speak(f"Could not find player position using {method}")
        # Proceed without player location

    # Get POI information
    poi_data = handle_poi_selection(selected_poi, player_location, use_ppi)
    print(f"POI data: {poi_data}")
    
    if poi_data[1] is None:
        print(f"{poi_data[0]} not located.")
        speaker.speak(f"{poi_data[0]} not located.")
        return

    # Play spatial POI sound if enabled
    if play_poi_sound:
        if player_angle is not None and player_location is not None:
            play_spatial_poi_sound(player_location, player_angle, poi_data[1])

    # Handle clicking for non-PPI mode
    if not use_ppi:
        pyautogui.moveTo(poi_data[1][0], poi_data[1][1])
        pyautogui.rightClick()
        pyautogui.click()

    # Perform POI actions
    perform_poi_actions(poi_data, player_location, speak_info=False, use_ppi=use_ppi)
    
    # Handle auto-turning if enabled
    config = configparser.ConfigParser()
    config.read('CONFIG.txt')
    auto_turn_enabled = get_config_boolean(config, 'AutoTurn', False)
    
    if auto_turn_enabled:
        if not use_ppi:
            pyautogui.press('escape')
            time.sleep(0.1)
        success = auto_turn_towards_poi(player_location, poi_data[1], poi_data[0])
    else:
        success = False

    # Get final angle and speak result
    _, latest_angle = find_minimap_icon_direction()
    if latest_angle is None:
        print("Unable to determine final player direction. Using initial direction.")
        latest_angle = player_angle

    speak_auto_turn_result(poi_data[0], player_location, latest_angle, poi_data[1], auto_turn_enabled, success)

def speak_auto_turn_result(poi_name, player_location, player_angle, poi_location, auto_turn_enabled, success):
    poi_info = calculate_poi_info(player_location, player_angle, poi_location)
    message = generate_poi_message(poi_name, player_angle, poi_info)

    if auto_turn_enabled and success:
        message = f"{message}"

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
            print(f"Unable to determine current direction. Attempt {attempts + 1}/{max_attempts}")
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