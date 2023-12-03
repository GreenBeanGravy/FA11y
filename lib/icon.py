import cv2, numpy as np, pyautogui, ctypes, threading, time, win32api, configparser
from accessible_output2.outputs.auto import Auto
from lib.storm import start_storm_detection
import lib.guis.gui as gui

pyautogui.FAILSAFE = False

speaker = Auto()

# Constants
min_shape_size, max_shape_size = 1200, 2200
roi_start_orig, roi_end_orig = (590, 190), (1490, 1010)
VK_GRAVE_ACCENT = 0xC0
VK_SHIFT = 0x10
grave_accent_key_down = False

def load_config():
    config = configparser.ConfigParser()
    config.read('config.txt')
    poi_data = config['POI']['selected_poi']
    return tuple(poi_data.split(', '))

def get_relative_direction(vector, target_bearing):
    adjusted_vector = np.array([vector[0], -vector[1]])
    degree, target_bearing = (np.degrees(np.arctan2(adjusted_vector[1], adjusted_vector[0])) + 360) % 360, (target_bearing + 360) % 360
    relative_bearing = (degree - target_bearing + 360) % 360
    compass_brackets = [22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5]
    compass_labels = ['behind', 'behind and slightly left', 'left', 'behind and slightly right', 'right', 'slightly right', 'in front', 'slightly left']
    return next((compass_labels[i] for i, val in enumerate(compass_brackets) if relative_bearing < val), 'in front')

def calculate_distance(point1, point2):
    return np.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2) * 3.25

def start_icon_detection():
    global grave_accent_key_down
    while True:
        selected_poi = load_config()
        grave_accent_key_down = check_and_toggle_key(VK_GRAVE_ACCENT, grave_accent_key_down, lambda: icon_detection_cycle(selected_poi))
        time.sleep(0.01)

def check_and_toggle_key(key, key_down, action):
    current_state = bool(ctypes.windll.user32.GetAsyncKeyState(key))
    if current_state and not key_down: action()
    return current_state

def icon_detection_cycle(selected_poi):
    # Handling when SHIFT is pressed for custom GUI creation
    if win32api.GetAsyncKeyState(VK_SHIFT) < 0:
        screenshot = np.array(pyautogui.screenshot())
        screenshot = cv2.resize(screenshot, None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
        roi_color = screenshot[4 * roi_start_orig[1]:4 * roi_end_orig[1], 4 * roi_start_orig[0]:4 * roi_end_orig[0]]

        roi_gray = cv2.cvtColor(roi_color, cv2.COLOR_BGR2GRAY)
        _, binary_image = cv2.threshold(roi_gray, 229, 255, cv2.THRESH_BINARY)
        valid_contours = find_valid_contours(binary_image)

        if valid_contours:
            largest_contour = max(valid_contours, key=cv2.contourArea)
            center_mass_screen = process_contour(largest_contour, roi_color, None, None)  # Passing None as these are not used in this scenario
            gui.create_gui(f"{center_mass_screen[0]},{center_mass_screen[1]}")
        else:
            speaker.speak("Player icon not located.")
        return

    # Rest of the function for normal operation
    if selected_poi[0].lower() == 'none':
        speaker.speak("No POI selected. Please update the config file.")
        return

    # Special handling for 'Storm' POI
    if selected_poi[0].lower() == 'safe zone':
        selected_coordinates = start_storm_detection()
    else:
        selected_coordinates = (int(selected_poi[1]), int(selected_poi[2]))

    if not selected_coordinates:
        return

    pyautogui.moveTo(*selected_coordinates, duration=0.01)
    pyautogui.click()
    pyautogui.click(button='right')
    process_screenshot(selected_coordinates, selected_poi)

def process_screenshot(selected_coordinates, selected_poi):
    screenshot = np.array(pyautogui.screenshot())
    screenshot = cv2.resize(screenshot, None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
    roi_color = screenshot[4 * roi_start_orig[1]:4 * roi_end_orig[1], 4 * roi_start_orig[0]:4 * roi_end_orig[0]]

    # Convert the ROI to grayscale
    roi_gray = cv2.cvtColor(roi_color, cv2.COLOR_BGR2GRAY)

    # Set a binary threshold to keep only pure white and pure black
    _, binary_image = cv2.threshold(roi_gray, 229, 255, cv2.THRESH_BINARY)

    # Remove the comment below to check if the conversion to black-and-white is functioning
    # cv2.imwrite('output.png', binary_image)

    valid_contours = find_valid_contours(binary_image)  # Updated to use binary_image
    if valid_contours:
        largest_contour = max(valid_contours, key=cv2.contourArea)
        process_contour(largest_contour, roi_color, selected_coordinates, selected_poi)
    else:
        speaker.speak("Player icon not located.")

def find_valid_contours(binary_image):  # Updated to use binary_image
    # Find contours in the binary image
    contours, _ = cv2.findContours(binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Filter contours based on the area size
    return [cnt for cnt in contours if min_shape_size < cv2.contourArea(cnt) < max_shape_size]

def process_contour(contour, roi_color, selected_coordinates, selected_poi):
    M = cv2.moments(contour)
    center_mass = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
    center_mass_screen = ((center_mass[0] // 4) + roi_start_orig[0], (center_mass[1] // 4) + roi_start_orig[1])
    hull = cv2.convexHull(contour)


    if selected_coordinates is not None:
        if len(hull) > 2:
            vertices = np.squeeze(hull)
            distances = [np.linalg.norm(v - center_mass) for v in vertices]
            farthest_vertex = vertices[np.argmax(distances)]
            direction_vector = farthest_vertex - np.array(center_mass)
    
            # Corrected calculation for the bearing of the contour
            direction_degree = (450 - np.degrees(np.arctan2(direction_vector[1], direction_vector[0]))) % 360
    
            # Corrected calculation for the bearing from the contour to the POI
            dx = selected_coordinates[0] - center_mass_screen[0]
            dy = selected_coordinates[1] - center_mass_screen[1]
            poi_degree = (450 - np.degrees(np.arctan2(dy, dx))) % 360
    
            relative_position_vector = np.array(selected_coordinates) - np.array(center_mass_screen)
            relative_position_to_poi = get_relative_direction(relative_position_vector, direction_degree)
            min_distance = calculate_distance(center_mass_screen, selected_coordinates)
            announce_position(selected_poi, relative_position_to_poi, min_distance)
    
            # Drawing the contour
            cv2.drawContours(roi_color, [contour], -1, (0, 255, 0), 3)
    
            # Drawing the center of mass
            cv2.circle(roi_color, center_mass, 5, (255, 0, 0), -1)
    
            # Drawing the farthest vertex
            cv2.circle(roi_color, tuple(farthest_vertex), 5, (0, 0, 255), -1)
    
            # Drawing a line from the center to the farthest vertex
            cv2.line(roi_color, center_mass, tuple(farthest_vertex), (255, 255, 0), 2)
    
            # Marking the selected POI and drawing a line from vertex to POI
            selected_poi_screen = (int(selected_coordinates[0]), int(selected_coordinates[1]))
            cv2.circle(roi_color, selected_poi_screen, 5, (0, 255, 255), -1)
            cv2.line(roi_color, tuple(farthest_vertex), selected_poi_screen, (0, 255, 255), 2)
        
            # Displaying degrees as text
            cv2.putText(roi_color, f"Contour Direction: {direction_degree:.2f} degrees", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(roi_color, f"POI Direction: {poi_degree:.2f} degrees", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
            # Remove the comment below to enable debug screenshots
            # cv2.imwrite('debug.png', roi_color)

    return center_mass_screen
    
def announce_position(selected_poi, relative_position_to_poi, distance):
    poi_name = selected_poi[0]
    if distance <= 40:
        speaker.speak(f"At {poi_name}")
    else:
        speaker.speak(f"{poi_name} is {relative_position_to_poi} {int(distance)} meters")
