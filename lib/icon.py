import cv2
import numpy as np
import pyautogui
import configparser
from accessible_output2.outputs.auto import Auto
from lib.storm import start_storm_detection
from lib.object_finder import find_the_train, find_combat_cache, find_storm_tower, find_reboot
import lib.guis.gui as gui

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
    config.read('config.txt')
    return tuple(config['POI']['selected_poi'].split(', '))

def get_relative_direction(front_vector, poi_vector):
    compass_brackets = [22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5]
    compass_labels = ['in front', 'slightly right', 'right', 'behind and slightly right', 'behind', 'behind and slightly left', 'left', 'slightly left']
    relative_angle = (np.degrees(np.arctan2(poi_vector[1], poi_vector[0])) - np.degrees(np.arctan2(front_vector[1], front_vector[0])) + 360) % 360
    return next((compass_labels[i] for i, val in enumerate(compass_brackets) if relative_angle < val), 'in front')

def start_icon_detection():
    icon_detection_cycle(load_config(), False)

def create_custom_poi():
    icon_detection_cycle(load_config(), True)

def icon_detection_cycle(selected_poi, is_create_custom_poi):
    center_mass_screen = find_player_icon_location()
    if not center_mass_screen:
        speaker.speak("Player icon not located.")
        return

    if is_create_custom_poi:
        gui.create_gui(f"{center_mass_screen[0]},{center_mass_screen[1]}")
    else:
        if selected_poi[0].lower() == 'none':
            speaker.speak("No POI selected. Please select a POI first.")
            return

        poi_data = handle_poi_selection(selected_poi, center_mass_screen)
        if poi_data[1]:  # Check if coordinates are not None
            perform_poi_actions(poi_data, selected_poi)
        else:
            speaker.speak(f"{poi_data[0]} not located.")

def find_player_icon_location():
    screenshot = cv2.resize(np.array(pyautogui.screenshot()), None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
    roi_gray = cv2.cvtColor(screenshot[4 * ROI_START_ORIG[1]:4 * ROI_END_ORIG[1], 4 * ROI_START_ORIG[0]:4 * ROI_END_ORIG[0]], cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(roi_gray, 229, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid_contours = [cnt for cnt in contours if MIN_SHAPE_SIZE < cv2.contourArea(cnt) < MAX_SHAPE_SIZE]
    if valid_contours:
        M = cv2.moments(max(valid_contours, key=cv2.contourArea))
        return ((int(M["m10"] / M["m00"]) // 4) + ROI_START_ORIG[0], (int(M["m01"] / M["m00"]) // 4) + ROI_START_ORIG[1])
    return None

def handle_poi_selection(selected_poi, center_mass_screen):
    special_poi_handlers = {
        'the train': find_the_train,
        'combat cache': find_combat_cache,
        'storm tower': find_storm_tower,
        'reboot': find_reboot,
        'safe zone': start_storm_detection,
        'closest': lambda: find_closest_poi(center_mass_screen, load_poi_from_file()) if center_mass_screen else (None, None)
    }
    
    poi_name = selected_poi[0].lower()
    if poi_name in special_poi_handlers:
        result = special_poi_handlers[poi_name]()
        if poi_name == 'closest':
            return result  # This now returns (poi_name, coordinates) directly
        else:
            return poi_name, result
    else:
        try:
            return poi_name, (int(selected_poi[1]), int(selected_poi[2]))
        except ValueError:
            print(f"Error: Invalid POI coordinates for {poi_name}: {selected_poi[1]}, {selected_poi[2]}")
            return poi_name, None

def perform_poi_actions(poi_data, selected_poi):
    if isinstance(poi_data, tuple) and len(poi_data) == 2:
        poi_name, coordinates = poi_data
    else:
        poi_name, coordinates = selected_poi[0], poi_data

    if coordinates and len(coordinates) == 2:
        x, y = coordinates
        try:
            pyautogui.moveTo(int(x), int(y), duration=0.01)
            pyautogui.click()
            pyautogui.click(button='right')
            process_screenshot((int(x), int(y)), poi_name)
        except ValueError:
            print(f"Error: Invalid POI coordinates for {poi_name}: {x}, {y}")
            speaker.speak(f"Error: Invalid POI coordinates for {poi_name}")
    else:
        print(f"Error: Invalid POI location for {poi_name}")
        speaker.speak(f"Error: Invalid POI location for {poi_name}")

def process_screenshot(selected_coordinates, poi_name):
    screenshot = cv2.resize(np.array(pyautogui.screenshot()), None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
    roi_color = screenshot[4 * ROI_START_ORIG[1]:4 * ROI_END_ORIG[1], 4 * ROI_START_ORIG[0]:4 * ROI_END_ORIG[0]]
    roi_gray = cv2.cvtColor(roi_color, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(roi_gray, 229, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid_contours = [cnt for cnt in contours if MIN_SHAPE_SIZE < cv2.contourArea(cnt) < MAX_SHAPE_SIZE]
    
    if valid_contours:
        contour = max(valid_contours, key=cv2.contourArea)
        M = cv2.moments(contour)
        center_mass_screen = ((int(M["m10"] / M["m00"]) // 4) + ROI_START_ORIG[0], (int(M["m01"] / M["m00"]) // 4) + ROI_START_ORIG[1])
        
        hull = cv2.convexHull(contour)
        if len(hull) > 2:
            vertices = np.squeeze(hull)
            center_mass = np.array([M["m10"] / M["m00"], M["m01"] / M["m00"]])
            farthest_vertex = vertices[np.argmax(np.linalg.norm(vertices - center_mass, axis=1))]
            direction_vector = farthest_vertex - center_mass
            
            relative_position = get_relative_direction(direction_vector, np.array(selected_coordinates) - center_mass_screen)
            distance = np.linalg.norm(np.array(center_mass_screen) - np.array(selected_coordinates)) * 2.65
            
            message = f"At {poi_name}" if distance <= 40 else f"{poi_name} is {relative_position} {int(distance)} meters"
            speaker.speak(message)
    else:
        speaker.speak("Player icon not located.")

if __name__ == "__main__":
    # Add any standalone testing or execution code here
    pass