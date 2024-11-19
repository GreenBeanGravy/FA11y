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
from lib.minimap_direction import find_minimap_icon_direction
from lib.mouse import smooth_move_mouse
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
from lib.utilities import get_config_boolean

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

def handle_poi_selection(selected_poi, center_mass_screen):
    print(f"Handling POI selection: {selected_poi}")
    poi_data = POIData()
    
    if isinstance(selected_poi, tuple) and len(selected_poi) == 1:
        selected_poi = selected_poi[0]
    
    if isinstance(selected_poi, str):
        parts = selected_poi.split(',')
        if len(parts) == 3 and parts[0].lower() == 'position':
            try:
                x, y = int(parts[1]), int(parts[2])
                return 'Custom Position', (x, y)
            except ValueError:
                print(f"Error: Invalid custom position coordinates: {parts[1]}, {parts[2]}")
                return 'Custom Position', None
    
    poi_name = selected_poi[0].lower() if isinstance(selected_poi, tuple) else selected_poi.lower()
    
    if poi_name == 'safe zone':
        print("Detecting safe zone")
        return 'Safe Zone', start_storm_detection()
    elif poi_name == 'closest':
        print("Finding closest main POI")
        if center_mass_screen is None:
            center_mass_screen = find_player_icon_location()
        if center_mass_screen:
            main_pois = [(poi[0], int(float(poi[1])), int(float(poi[2]))) 
                        for poi in poi_data.main_pois]
            return find_closest_poi(center_mass_screen, main_pois)
        else:
            print("Could not determine player location for finding closest POI")
            return "Closest", None
    elif poi_name == 'closest landmark':
        print("Finding closest landmark")
        if center_mass_screen is None:
            center_mass_screen = find_player_icon_location()
        if center_mass_screen:
            landmarks = [(poi[0], int(float(poi[1])), int(float(poi[2]))) 
                        for poi in poi_data.landmarks]
            return find_closest_poi(center_mass_screen, landmarks)
        else:
            print("Could not determine player location for finding closest landmark")
            return "Closest Landmark", None
    else:
        if poi_name in OBJECT_CONFIGS or poi_name.replace(' ', '_') in OBJECT_CONFIGS:
            print(f"Detecting game object: {poi_name}")
            object_name = poi_name if poi_name in OBJECT_CONFIGS else poi_name.replace(' ', '_')
            icon_path, threshold = OBJECT_CONFIGS[object_name]
            result = find_closest_object(icon_path, threshold)
            if result:
                print(f"Game object {poi_name} found at: {result}")
                return poi_name, result
            else:
                print(f"Game object {poi_name} not found on screen")
                return poi_name, None
        else:
            for poi in poi_data.main_pois:
                if poi[0].lower() == poi_name:
                    return poi[0], (int(float(poi[1])), int(float(poi[2])))
            
            for poi in poi_data.landmarks:
                if poi[0].lower() == poi_name:
                    return poi[0], (int(float(poi[1])), int(float(poi[2])))
            
            print(f"Error: POI '{selected_poi}' not found in API data")
            return selected_poi, None

def perform_poi_actions(poi_data, center_mass_screen, speak_info=True):
    poi_name, coordinates = poi_data
    print(f"Performing actions for POI: {poi_name}, Coordinates: {coordinates}")

    if coordinates and len(coordinates) == 2:
        x, y = coordinates
        try:
            if center_mass_screen and speak_info:
                process_screenshot((int(x), int(y)), poi_name, center_mass_screen)
            elif not speak_info:
                print(f"Clicked on {poi_name}. Info will be spoken after auto-turn.")
        except ValueError:
            print(f"Error: Invalid POI coordinates for {poi_name}: {x}, {y}")
            speaker.speak(f"Error: Invalid POI coordinates for {poi_name}")
    else:
        print(f"Error: Invalid POI location for {poi_name}")
        speaker.speak(f"Error: Invalid POI location for {poi_name}")

def process_screenshot(selected_coordinates, poi_name, center_mass_screen):
    location, angle = find_player_icon_location_with_direction()
    if location is not None:
        poi_info = calculate_poi_info(location, angle, selected_coordinates)
        message = generate_poi_message(poi_name, angle, poi_info)
        print(message)
        speaker.speak(message)
    else:
        print("Player icon not located in screenshot processing.")
        speaker.speak("Player icon not located.")

def start_icon_detection(use_ppi=False):
    print("Starting icon detection")
    config = load_config()
    selected_poi = config[0] if isinstance(config, tuple) else config
    icon_detection_cycle(selected_poi, use_ppi)

def icon_detection_cycle(selected_poi, use_ppi):
    print(f"Icon detection cycle started. Selected POI: {selected_poi}")
    
    if selected_poi.lower() == 'none':
        print("No POI selected.")
        speaker.speak("No POI selected. Please select a POI first.")
        return

    config = configparser.ConfigParser()
    config.read('CONFIG.txt')
    auto_turn_enabled = get_config_boolean(config, 'AutoTurn', False)
    if use_ppi:
        player_location = find_player_position()
        if player_location is None:
            print("Could not find player position using PPI")
            speaker.speak("Could not find player position using PPI")
            return
        player_angle = None
    else:
        player_info = find_player_icon_location_with_direction()
        if player_info is None:
            print("Could not find player icon or determine direction")
            player_location, player_angle = None, None
        else:
            player_location, player_angle = player_info

    poi_data = handle_poi_selection(selected_poi, player_location)
    print(f"POI data: {poi_data}")
    
    if poi_data[1] is None:
        print(f"{poi_data[0]} not located.")
        speaker.speak(f"{poi_data[0]} not located.")
        return

    if not use_ppi:
        pyautogui.moveTo(poi_data[1][0], poi_data[1][1])
        pyautogui.rightClick()
        pyautogui.click()

    if player_angle is None:
        _, player_angle = find_minimap_icon_direction()
        if player_angle is None:
            print("Could not determine player direction from minimap")

    perform_poi_actions(poi_data, player_location, speak_info=False)
    
    if auto_turn_enabled:
        if not use_ppi:
            pyautogui.press('escape')
            time.sleep(0.1)
        success = auto_turn_towards_poi(player_location, poi_data[1], poi_data[0])
    else:
        success = False

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