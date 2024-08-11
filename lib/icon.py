import cv2
import time
import keyboard
import numpy as np
import pyautogui
import configparser
from accessible_output2.outputs.auto import Auto
from lib.storm import start_storm_detection
from lib.object_finder import OBJECT_CONFIGS, find_closest_object
import lib.guis.gui as gui
from lib.minimap_direction import find_minimap_icon_direction
from lib.mouse import smooth_move_mouse
from lib.player_location import find_player_icon_location, find_player_icon_location_with_direction

pyautogui.FAILSAFE = False
speaker = Auto()

# Constants
MIN_SHAPE_SIZE, MAX_SHAPE_SIZE = 1300, 2000
ROI_START_ORIG, ROI_END_ORIG = (590, 190), (1490, 1010)

def load_poi_from_file():
    with open('poi.txt', 'r') as file:
        return [tuple(line.strip().split(',')) for line in file]

def find_closest_poi(icon_location, poi_list):
    distances = [(poi, (int(x), int(y)), np.linalg.norm(np.array(icon_location) - np.array([int(x), int(y)])) * 3.25) 
                 for poi, x, y in poi_list]
    return min(distances, key=lambda x: x[2], default=(None, None, float('inf')))[:2]

def load_config():
    config = configparser.ConfigParser()
    config.read('CONFIG.txt')
    try:
        return tuple(config['POI']['selected_poi'].split(', '))
    except (KeyError, configparser.NoSectionError):
        return ('none', '0', '0')

def get_angle_and_direction(vector):
    angle = np.degrees(np.arctan2(-vector[1], vector[0]))
    angle = (450 - angle) % 360  # Adjust to start from North (0 degrees) and increase clockwise
    return angle, get_cardinal_direction(angle)

def get_cardinal_direction(angle):
    directions = ['North', 'Northeast', 'East', 'Southeast', 'South', 'Southwest', 'West', 'Northwest']
    return directions[int((angle + 22.5) % 360 // 45)]

def get_relative_direction(player_direction, poi_vector):
    if isinstance(player_direction, str):
        # Convert cardinal direction to vector
        direction_to_vector = {
            'North': [0, -1], 'Northeast': [1, -1], 'East': [1, 0], 'Southeast': [1, 1],
            'South': [0, 1], 'Southwest': [-1, 1], 'West': [-1, 0], 'Northwest': [-1, -1]
        }
        player_vector = np.array(direction_to_vector.get(player_direction, [0, -1]))
    else:
        player_vector = player_direction

    angle = np.degrees(np.arctan2(np.cross(player_vector, poi_vector), np.dot(player_vector, poi_vector)))
    angle = (angle + 360) % 360  # Ensure angle is between 0 and 360

    compass_brackets = [22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5]
    compass_labels = ['in front', 'to the right', 'to the right', 'behind and to the right', 
                      'behind', 'behind and to the left', 'to the left', 'to the left']
    return next((compass_labels[i] for i, val in enumerate(compass_brackets) if angle < val), 'in front')

def start_icon_detection():
    print("Starting icon detection")
    icon_detection_cycle(load_config())

def icon_detection_cycle(selected_poi):
    print(f"Icon detection cycle started. Selected POI: {selected_poi}")
    player_info = find_player_icon_location_with_direction()
    
    if player_info is None:
        print("Unable to determine player location and direction.")
        speaker.speak("Unable to determine player location and direction.")
        return

    center_mass_screen, initial_player_direction = player_info

    if selected_poi[0].lower() == 'none':
        print("No POI selected.")
        speaker.speak("No POI selected. Please select a POI first.")
        return

    poi_data = handle_poi_selection(selected_poi, center_mass_screen)
    print(f"POI data: {poi_data}")
    if poi_data[1]:  # Check if coordinates are not None
        config = configparser.ConfigParser()
        config.read('CONFIG.txt')
        auto_turn_enabled = config.getboolean('SETTINGS', 'AutoTurn', fallback=False)
        
        perform_poi_actions(poi_data, center_mass_screen, speak_info=False)
        
        if auto_turn_enabled and center_mass_screen:
            time.sleep(0.1)
            keyboard.press_and_release('esc')
            time.sleep(0.1)
            _, success = auto_turn_towards_poi(center_mass_screen, poi_data[1], poi_data[0])
        else:
            success = False

        # Get the latest player direction right before announcing
        latest_direction, latest_angle = find_minimap_icon_direction()
        if latest_direction is None:
            print("Unable to determine final player direction. Using initial direction.")
            # Calculate the angle from the initial direction vector
            latest_angle = np.degrees(np.arctan2(-initial_player_direction[1], initial_player_direction[0]))
            latest_angle = (450 - latest_angle) % 360

        speak_auto_turn_result(poi_data[0], center_mass_screen, latest_angle, poi_data[1], auto_turn_enabled, success)
    else:
        print(f"{poi_data[0]} not located.")
        speaker.speak(f"{poi_data[0]} not located.")

def speak_auto_turn_result(poi_name, player_location, player_angle, poi_location, auto_turn_enabled, success):
    poi_vector = np.array(poi_location) - np.array(player_location)
    distance = np.linalg.norm(poi_vector) * 2.65
    angle, cardinal_direction = get_angle_and_direction(poi_vector)

    if player_angle is not None:
        player_cardinal = get_cardinal_direction(player_angle)
        player_direction = np.array([np.cos(np.radians(player_angle)), -np.sin(np.radians(player_angle))])
    else:
        player_cardinal = "Unknown"
        player_direction = np.array([0, -1])  # Default to North if angle is unknown
    
    relative_direction = get_relative_direction(player_direction, poi_vector)

    if not auto_turn_enabled or not success:
        message = f"{poi_name} is {relative_direction} {int(distance)} meters, and is {cardinal_direction} at {angle:.0f} degrees"
    else:
        message = f"Facing {poi_name} at {int(distance)} meters away, {poi_name} is {cardinal_direction} at {angle:.0f} degrees"

    if player_angle is not None:
        message += f", facing {player_cardinal} at {player_angle:.0f} degrees"
    else:
        message += f", facing direction unknown"

    print(message)
    speaker.speak(message)

def auto_turn_towards_poi(player_location, poi_location, poi_name):
    max_attempts = 30
    base_turn_speed, max_turn_speed = 200, 500
    angle_threshold = 5
    sensitivity = 1.0
    min_sensitivity = 0.6

    for attempts in range(max_attempts):
        current_direction, current_angle = find_minimap_icon_direction(sensitivity)
        if current_direction is None:
            print(f"Unable to determine current direction. Sensitivity: {sensitivity:.2f}, Attempt {attempts + 1}/{max_attempts}")
            sensitivity = max(sensitivity - 0.05, min_sensitivity)
            time.sleep(0.1)
            continue
        
        poi_vector = np.array(poi_location) - np.array(player_location)
        poi_angle = (450 - np.degrees(np.arctan2(-poi_vector[1], poi_vector[0]))) % 360
        
        angle_difference = (poi_angle - current_angle + 180) % 360 - 180
        
        if attempts % 5 == 0 or abs(angle_difference) <= angle_threshold:
            print(f"Current angle: {current_angle:.2f}, POI angle: {poi_angle:.2f}, Difference: {angle_difference:.2f}")
        
        if abs(angle_difference) <= angle_threshold:
            print(f"Successfully turned towards {poi_name}. Current direction: {current_direction}")
            return np.array([np.cos(np.radians(current_angle)), -np.sin(np.radians(current_angle))]), True
        
        turn_speed = min(base_turn_speed + (abs(angle_difference) * 2), max_turn_speed)
        turn_amount = min(abs(angle_difference), 90)
        turn_direction = 1 if angle_difference > 0 else -1
        
        smooth_move_mouse(int(turn_amount * turn_direction * (turn_speed / 100)), 0, 0.01)
        time.sleep(0.05)
        
        sensitivity = min(sensitivity + 0.05, 1.0) if abs(angle_difference) < 45 else sensitivity

    print(f"Failed to turn towards {poi_name} after maximum attempts.")
    return np.array([np.cos(np.radians(current_angle)), -np.sin(np.radians(current_angle))]), False

def perform_poi_actions(poi_data, center_mass_screen, speak_info=True):
    poi_name, coordinates = poi_data
    print(f"Performing actions for POI: {poi_name}, Coordinates: {coordinates}")

    if coordinates and len(coordinates) == 2:
        x, y = coordinates
        try:
            print(f"Moving mouse to: ({x}, {y})")
            pyautogui.moveTo(int(x), int(y))  # Use instant movement
            pyautogui.click()
            pyautogui.click(button='right')
            
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

def handle_poi_selection(selected_poi, center_mass_screen):
    print(f"Handling POI selection: {selected_poi}")
    
    if isinstance(selected_poi, tuple) and len(selected_poi) == 1:
        selected_poi = selected_poi[0]  # Unpack the tuple if it's a single-element tuple
    
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
        print("Finding closest POI")
        return find_closest_poi(center_mass_screen, load_poi_from_file()) if center_mass_screen else (None, None)
    else:
        # Check if it's a game object
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
            # Handle as static POI
            try:
                if isinstance(selected_poi, tuple) and len(selected_poi) >= 3:
                    coordinates = (int(selected_poi[1]), int(selected_poi[2]))
                else:
                    raise ValueError("Invalid POI format")
                
                if coordinates == (0, 0):
                    print(f"Warning: Static coordinates (0, 0) detected for {poi_name}. This might be a placeholder.")
                print(f"Using static POI coordinates: {coordinates}")
                return poi_name, coordinates
            except (ValueError, IndexError):
                print(f"Error: Invalid POI coordinates for {poi_name}: {selected_poi}")
                return poi_name, None

def process_screenshot(selected_coordinates, poi_name, center_mass_screen):
    print(f"Processing screenshot for POI: {poi_name}, Coordinates: {selected_coordinates}")
    screenshot = cv2.resize(np.array(pyautogui.screenshot()), None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
    roi_color = screenshot[4 * ROI_START_ORIG[1]:4 * ROI_END_ORIG[1], 4 * ROI_START_ORIG[0]:4 * ROI_END_ORIG[0]]
    roi_gray = cv2.cvtColor(roi_color, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(roi_gray, 229, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid_contours = [cnt for cnt in contours if MIN_SHAPE_SIZE < cv2.contourArea(cnt) < MAX_SHAPE_SIZE]
    
    if valid_contours:
        contour = max(valid_contours, key=cv2.contourArea)
        M = cv2.moments(contour)
        center_mass = np.array([M["m10"] / M["m00"], M["m01"] / M["m00"]])
        
        hull = cv2.convexHull(contour)
        if len(hull) > 2:
            vertices = np.squeeze(hull)
            farthest_vertex = vertices[np.argmax(np.linalg.norm(vertices - center_mass, axis=1))]
            direction_vector = farthest_vertex - center_mass
            
            player_angle, cardinal_direction = get_angle_and_direction(direction_vector)
            relative_direction, relative_angle = get_relative_direction(direction_vector, np.array(selected_coordinates) - center_mass_screen)
            distance = np.linalg.norm(np.array(center_mass_screen) - np.array(selected_coordinates)) * 2.65
            
            print(f"Player facing: {cardinal_direction} ({player_angle:.2f} degrees)")
            print(f"POI relative direction: {relative_direction} ({relative_angle:.2f} degrees)")
            
            message = f"At {poi_name}" if distance <= 40 else f"{poi_name} is {relative_direction} {int(distance)} meters"
            print(message)
            speaker.speak(message)
    else:
        print("Player icon not located in screenshot processing.")
        speaker.speak("Player icon not located.")

if __name__ == "__main__":
    print("Available objects:", list(OBJECT_CONFIGS.keys()))
