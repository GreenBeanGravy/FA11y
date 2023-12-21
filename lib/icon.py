import cv2, numpy as np, pyautogui, ctypes, threading, time, win32api, configparser, keyboard
from accessible_output2.outputs.auto import Auto
from lib.storm import start_storm_detection
from lib.object_finder import find_the_train, find_combat_cache, find_storm_tower
import lib.guis.gui as gui
from pynput.keyboard import Controller, Key

pyautogui.FAILSAFE = False
speaker = Auto()
keyboard_controller = Controller()

# Constants
min_shape_size, max_shape_size = 1300, 2000
roi_start_orig, roi_end_orig = (590, 190), (1490, 1010)

def load_poi_from_file():
    with open('poi.txt', 'r') as file:
        return [(data[0], int(data[1]), int(data[2])) for data in (line.strip().split(',') for line in file)]

def find_closest_poi(icon_location, poi_list):
    closest_poi = min(((poi, (x, y), calculate_distance(icon_location, (x, y))) for poi, x, y in poi_list), key=lambda x: x[2], default=(None, None, float('inf')))
    return closest_poi[:2]  # Return POI name and coordinates

def load_config():
    config = configparser.ConfigParser()
    config.read('config.txt')
    return tuple(config['POI']['selected_poi'].split(', '))

def get_relative_direction(front_vector, poi_vector):
    compass_brackets = [22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5]
    compass_labels = ['in front', 'slightly right', 'right', 'behind and slightly right', 'behind', 'behind and slightly left', 'left', 'slightly left']
    relative_angle = (np.degrees(np.arctan2(poi_vector[1], poi_vector[0])) - np.degrees(np.arctan2(front_vector[1], front_vector[0])) + 360) % 360
    return next((compass_labels[i] for i, val in enumerate(compass_brackets) if relative_angle < val), 'in front')

def calculate_distance(point1, point2):
    return np.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2) * 3.25

def check_pixel_color(x, y, color=(247, 255, 26), tolerance=10):
    screenshot = np.array(pyautogui.screenshot())
    pixel_color = screenshot[y, x]
    return all(abs(pixel_color[i] - color[i]) <= tolerance for i in range(3))

def press_key(key):
    keyboard.press(key)
    time.sleep(0.1)
    keyboard.release(key)

def click_mouse(x, y, duration=0.05):
    pyautogui.moveTo(x, y, duration=duration)
    pyautogui.click()

def start_icon_detection():
    selected_poi = load_config()
    icon_detection_cycle(selected_poi, False)

def create_custom_poi():
    selected_poi = load_config()
    icon_detection_cycle(selected_poi, True)

def icon_detection_cycle(selected_poi, is_create_custom_poi):
    center_mass_screen = find_player_icon_location()
    if not center_mass_screen:
        return

    # Handle custom POI creation or normal icon detection
    if is_create_custom_poi:
        gui.create_gui(f"{center_mass_screen[0]},{center_mass_screen[1]}")
    else:
        if selected_poi[0].lower() == 'none':
            speaker.speak("No POI selected. Please select a POI first.")
            return

        result = handle_poi_selection(selected_poi, center_mass_screen)
        if result is not None:
            poi_name, poi_location = result
            if poi_location:
                perform_poi_actions(poi_location, (poi_name, selected_poi[1], selected_poi[2]))
            else:
                speaker.speak(f"{poi_name} not located.")

def find_player_icon_location():
    screenshot = cv2.resize(np.array(pyautogui.screenshot()), None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
    roi_gray = cv2.cvtColor(screenshot[4 * roi_start_orig[1]:4 * roi_end_orig[1], 4 * roi_start_orig[0]:4 * roi_end_orig[0]], cv2.COLOR_BGR2GRAY)
    valid_contours = find_valid_contours(cv2.threshold(roi_gray, 229, 255, cv2.THRESH_BINARY)[1])
    return process_contour(max(valid_contours, key=cv2.contourArea), roi_gray, None, None) if valid_contours else None

def handle_poi_selection(selected_poi, center_mass_screen):
    special_poi_handlers = {
        'the train': lambda: (selected_poi[0], find_the_train()),
        'combat cache': lambda: (selected_poi[0], find_combat_cache()),
        'storm tower': lambda: (selected_poi[0], find_storm_tower()),
        'safe zone': lambda: (selected_poi[0], start_storm_detection()),
        'closest': lambda: find_closest_poi(center_mass_screen, load_poi_from_file()) if center_mass_screen else (None, None)
    }
    result = special_poi_handlers.get(selected_poi[0].lower(), lambda: (selected_poi[0], (int(selected_poi[1]), int(selected_poi[2]))))()
    return result

def perform_poi_actions(poi_location, selected_poi):
    if len(poi_location) == 2:
        x, y = poi_location
        pyautogui.moveTo(x, y, duration=0.01)
        pyautogui.click()
        pyautogui.click(button='right')
        process_screenshot(poi_location, selected_poi)
    else:
        # Handle the error or log a message if poi_location does not have 2 elements
        print("Error: poi_location does not have exactly two elements.")

def find_valid_contours(binary_image):
    return [cnt for cnt in cv2.findContours(binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0] if min_shape_size < cv2.contourArea(cnt) < max_shape_size]

def process_contour(contour, roi_color, selected_coordinates, selected_poi):
    M = cv2.moments(contour)
    contour_area = cv2.contourArea(contour)
    print(f"Contour Area (Number of pixels inside the contour): {contour_area}")

    center_mass_screen = ((int(M["m10"] / M["m00"]) // 4) + roi_start_orig[0], (int(M["m01"] / M["m00"]) // 4) + roi_start_orig[1])
    if selected_coordinates:
        process_drawing_and_announce(contour, roi_color, center_mass_screen, selected_coordinates, selected_poi, M)
    return center_mass_screen

def process_drawing_and_announce(contour, roi_color, center_mass_screen, selected_coordinates, selected_poi, M):
    hull = cv2.convexHull(contour)
    if len(hull) > 2:
        vertices, center_mass = np.squeeze(hull), np.array([M["m10"] / M["m00"], M["m01"] / M["m00"]])
        farthest_vertex = vertices[np.argmax([np.linalg.norm(v - center_mass) for v in vertices])]
        direction_vector = farthest_vertex - center_mass
        draw_contour_elements(roi_color, contour, center_mass, farthest_vertex, selected_coordinates)
        announce_position(selected_poi, get_relative_direction(direction_vector, np.array(selected_coordinates) - center_mass_screen), calculate_distance(center_mass_screen, selected_coordinates))
        # Uncomment the line below to enable debug screenshots
        #save_screenshot_with_contour(roi_color)  # Save the screenshot with the contour

def save_screenshot_with_contour(roi_color):
    cv2.imwrite('debug.png', roi_color)

def draw_contour_elements(roi_color, contour, center_mass, farthest_vertex, selected_poi_screen):
    cv2.drawContours(roi_color, [contour], -1, (0, 255, 0), 3)
    cv2.circle(roi_color, tuple(map(int, center_mass)), 5, (255, 0, 0), -1)
    cv2.circle(roi_color, tuple(map(int, farthest_vertex)), 5, (0, 0, 255), -1)
    cv2.line(roi_color, tuple(map(int, center_mass)), tuple(map(int, farthest_vertex)), (255, 255, 0), 2)
    cv2.circle(roi_color, tuple(map(int, selected_poi_screen)), 5, (0, 255, 255), -1)
    cv2.line(roi_color, tuple(map(int, farthest_vertex)), tuple(map(int, selected_poi_screen)), (0, 255, 255), 2)

def announce_position(selected_poi, relative_position_to_poi, distance):
    speaker.speak(f"At {selected_poi[0]}" if distance <= 40 else f"{selected_poi[0]} is {relative_position_to_poi} {int(distance)} meters")

def process_screenshot(selected_coordinates, selected_poi):
    roi_color = cv2.resize(np.array(pyautogui.screenshot()), None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)[4 * roi_start_orig[1]:4 * roi_end_orig[1], 4 * roi_start_orig[0]:4 * roi_end_orig[0]]
    valid_contours = find_valid_contours(cv2.threshold(cv2.cvtColor(roi_color, cv2.COLOR_BGR2GRAY), 229, 255, cv2.THRESH_BINARY)[1])
    if valid_contours:
        process_contour(max(valid_contours, key=cv2.contourArea), roi_color, selected_coordinates, selected_poi)
    else:
        speaker.speak("Player icon not located.")
