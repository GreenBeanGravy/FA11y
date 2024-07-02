import cv2
import numpy as np
import pyautogui
import configparser
from accessible_output2.outputs.auto import Auto
from lib.storm import start_storm_detection
from lib.object_finder import OBJECT_CONFIGS, find_closest_object
import lib.guis.gui as gui
from lib.mouse import smooth_move_mouse

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

def get_relative_direction(front_vector, poi_vector):
    compass_brackets = [22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5]
    compass_labels = ['in front', 'slightly right', 'right', 'behind and slightly right', 'behind', 'behind and slightly left', 'left', 'slightly left']
    relative_angle = (np.degrees(np.arctan2(poi_vector[1], poi_vector[0])) - np.degrees(np.arctan2(front_vector[1], front_vector[0])) + 360) % 360
    return next((compass_labels[i] for i, val in enumerate(compass_brackets) if relative_angle < val), 'in front')

def start_icon_detection():
    print("Starting icon detection")
    icon_detection_cycle(load_config(), False)

def create_custom_poi():
    print("Creating custom POI")
    icon_detection_cycle(load_config(), True)

def icon_detection_cycle(selected_poi, is_create_custom_poi):
    print(f"Icon detection cycle started. Selected POI: {selected_poi}, Create custom POI: {is_create_custom_poi}")
    center_mass_screen = find_player_icon_location()
    
    if is_create_custom_poi:
        if center_mass_screen:
            print(f"Creating custom POI at {center_mass_screen}")
            gui.create_gui(f"{center_mass_screen[0]},{center_mass_screen[1]}")
        else:
            print("Player icon not located. Cannot create custom POI.")
            speaker.speak("Player icon not located. Cannot create custom POI.")
    else:
        if selected_poi[0].lower() == 'none':
            print("No POI selected.")
            speaker.speak("No POI selected. Please select a POI first.")
            return

        poi_data = handle_poi_selection(selected_poi, center_mass_screen)
        print(f"POI data: {poi_data}")
        if poi_data[1]:  # Check if coordinates are not None
            perform_poi_actions(poi_data, center_mass_screen)
        else:
            print(f"{poi_data[0]} not located.")
            speaker.speak(f"{poi_data[0]} not located.")

def find_player_icon_location():
    print("Finding player icon location")
    screenshot = cv2.resize(np.array(pyautogui.screenshot()), None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
    roi_gray = cv2.cvtColor(screenshot[4 * ROI_START_ORIG[1]:4 * ROI_END_ORIG[1], 4 * ROI_START_ORIG[0]:4 * ROI_END_ORIG[0]], cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(roi_gray, 229, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid_contours = [cnt for cnt in contours if MIN_SHAPE_SIZE < cv2.contourArea(cnt) < MAX_SHAPE_SIZE]
    if valid_contours:
        M = cv2.moments(max(valid_contours, key=cv2.contourArea))
        location = ((int(M["m10"] / M["m00"]) // 4) + ROI_START_ORIG[0], (int(M["m01"] / M["m00"]) // 4) + ROI_START_ORIG[1])
        print(f"Player icon located at: {location}")
        return location
    print("Player icon not found")
    return None

def perform_poi_actions(poi_data, center_mass_screen):
    poi_name, coordinates = poi_data
    print(f"Performing actions for POI: {poi_name}, Coordinates: {coordinates}")

    if coordinates and len(coordinates) == 2:
        x, y = coordinates
        try:
            print(f"Moving mouse to: ({x}, {y})")
            pyautogui.moveTo(int(x), int(y))  # Use instant movement
            pyautogui.click()
            pyautogui.click(button='right')
            
            if center_mass_screen:
                process_screenshot((int(x), int(y)), poi_name, center_mass_screen)
            else:
                print("Player icon not located. Cannot provide relative position information.")
                speaker.speak(f"Clicked on {poi_name}. Player icon not located.")
        except ValueError:
            print(f"Error: Invalid POI coordinates for {poi_name}: {x}, {y}")
            speaker.speak(f"Error: Invalid POI coordinates for {poi_name}")
    else:
        print(f"Error: Invalid POI location for {poi_name}")
        speaker.speak(f"Error: Invalid POI location for {poi_name}")

def handle_poi_selection(selected_poi, center_mass_screen):
    print(f"Handling POI selection: {selected_poi}")
    poi_name = selected_poi[0].lower()
    
    if poi_name == 'safe zone':
        print("Detecting safe zone")
        return 'Safe Zone', start_storm_detection()
    elif poi_name == 'closest':
        print("Finding closest POI")
        return find_closest_poi(center_mass_screen, load_poi_from_file()) if center_mass_screen else (None, None)
    elif poi_name in OBJECT_CONFIGS or poi_name.replace(' ', '_') in OBJECT_CONFIGS:
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
        try:
            coordinates = (int(selected_poi[1]), int(selected_poi[2]))
            if coordinates == (0, 0):
                print(f"Warning: Static coordinates (0, 0) detected for {poi_name}. This might be a placeholder.")
            print(f"Using static POI coordinates: {coordinates}")
            return poi_name, coordinates
        except ValueError:
            print(f"Error: Invalid POI coordinates for {poi_name}: {selected_poi[1]}, {selected_poi[2]}")
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
            
            relative_position = get_relative_direction(direction_vector, np.array(selected_coordinates) - center_mass_screen)
            distance = np.linalg.norm(np.array(center_mass_screen) - np.array(selected_coordinates)) * 2.65
            
            message = f"At {poi_name}" if distance <= 40 else f"{poi_name} is {relative_position} {int(distance)} meters"
            print(message)
            speaker.speak(message)
    else:
        print("Player icon not located in screenshot processing.")
        speaker.speak("Player icon not located.")

if __name__ == "__main__":
    print("Available objects:", list(OBJECT_CONFIGS.keys()))
