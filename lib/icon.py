import cv2, numpy as np, pyautogui, ctypes, threading, time, tkinter as tk
from accessible_output2.outputs.auto import Auto
from lib.storm import start_storm_detection

speaker = Auto()

# Constants
min_shape_size, max_shape_size = 1200, 2200
roi_start_orig, roi_end_orig = (590, 190), (1490, 1010)
VK_RIGHT_BRACKET, VK_GRAVE_ACCENT = 0xDD, 0xC0
right_bracket_key_down = grave_accent_key_down = False
selected_poi = None
pois = [("Safe Zone", 0, 0)] + [(line.split(',')[0], int(line.split(',')[1]), int(line.split(',')[2])) for line in open('POI.txt', 'r')]

import threading

def select_poi_tk():
    global selected_poi
    root = tk.Tk()
    root.title("P O I Selector")

    def speak(s):
        speaker.speak(s)

    def delayed_speak(s):
        time.sleep(0.2)
        speak(s)

    def select_poi(poi):
        global selected_poi
        selected_poi = poi
        speak(f"{selected_poi} selected")
        pyautogui.click()
        root.destroy()

    def navigate(event, direction):
        current_index = buttons.index(root.focus_get())
        new_index = max(0, min(current_index + direction, len(buttons) - 1))
        focused_button = buttons[new_index]
        focused_button.focus_set()
        speak(focused_button.cget("text"))

    buttons = []
    for poi, _, _ in pois:
        btn = tk.Button(root, text=poi, command=lambda poi=poi: select_poi(poi))
        btn.pack()
        buttons.append(btn)

    root.bind('<Up>', lambda e: navigate(e, -1))
    root.bind('<Down>', lambda e: navigate(e, 1))
    root.bind('<Return>', lambda e: select_poi(root.focus_get().cget("text")))

    root.attributes('-topmost', True)

    if buttons:
        buttons[0].focus_set()
        threading.Thread(target=delayed_speak, args=(buttons[0].cget("text"),), daemon=True).start()

    root.update_idletasks()
    root.deiconify()
    root.focus_force()
    root.mainloop()

def get_relative_direction(vector, target_bearing):
    adjusted_vector = np.array([vector[0], -vector[1]])
    degree, target_bearing = (np.degrees(np.arctan2(adjusted_vector[1], adjusted_vector[0])) + 360) % 360, (target_bearing + 360) % 360
    relative_bearing = (degree - target_bearing + 360) % 360
    compass_brackets = [22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5]
    compass_labels = ['behind', 'behind and slightly left', 'left', 'behind and slightly right', 'right', 'slightly right', 'in front', 'slightly left']
    return next((compass_labels[i] for i, val in enumerate(compass_brackets) if relative_bearing < val), 'in front')

def calculate_distance(point1, point2):
    return np.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2) * 3.15

def start_icon_detection():
    global right_bracket_key_down, grave_accent_key_down, selected_poi
    while True:
        right_bracket_key_down = check_and_toggle_key(VK_RIGHT_BRACKET, right_bracket_key_down, select_poi_tk)
        grave_accent_key_down = check_and_toggle_key(VK_GRAVE_ACCENT, grave_accent_key_down, lambda: icon_detection_cycle(selected_poi))
        time.sleep(0.01)

def check_and_toggle_key(key, key_down, action):
    current_state = bool(ctypes.windll.user32.GetAsyncKeyState(key))
    if current_state and not key_down: action()
    return current_state

def icon_detection_cycle(selected_poi):
    if not selected_poi:
        speaker.speak("No POI selected. Press the right bracket key.")
        return

    selected_coordinates = next(((x, y) for name, x, y in pois if name == selected_poi), None)
    if selected_poi == "Safe Zone":
        selected_coordinates = start_storm_detection()

    if not selected_coordinates: return

    pyautogui.moveTo(*selected_coordinates, duration=0.01)
    pyautogui.click()
    pyautogui.click(button='right')
    process_screenshot(selected_coordinates)

def process_screenshot(selected_coordinates):
    screenshot = np.array(pyautogui.screenshot())
    screenshot = cv2.resize(screenshot, None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
    roi_color = screenshot[4 * roi_start_orig[1]:4 * roi_end_orig[1], 4 * roi_start_orig[0]:4 * roi_end_orig[0]]
    valid_contours = find_valid_contours(roi_color)
    if valid_contours:
        largest_contour = max(valid_contours, key=cv2.contourArea)
        process_contour(largest_contour, roi_color, selected_coordinates)
    else:
        speaker.speak("Player icon not located.")

def find_valid_contours(roi_color):
    roi_gray = cv2.cvtColor(roi_color, cv2.COLOR_BGR2GRAY)
    _, thresholded = cv2.threshold(roi_gray, 230, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresholded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [cnt for cnt in contours if min_shape_size < cv2.contourArea(cnt) < max_shape_size]

def process_contour(contour, roi_color, selected_coordinates):
    M = cv2.moments(contour)
    center_mass = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
    center_mass_screen = ((center_mass[0] // 4) + roi_start_orig[0], (center_mass[1] // 4) + roi_start_orig[1])
    hull = cv2.convexHull(contour)
    if len(hull) > 2:
        vertices = np.squeeze(hull)
        distances = [np.linalg.norm(v - center_mass) for v in vertices]
        farthest_vertex = vertices[np.argmax(distances)]
        direction_vector = farthest_vertex - np.array(center_mass)
        bearing = (90 - np.degrees(np.arctan2(direction_vector[1], direction_vector[0])) - 180) % 360
        relative_position_vector = np.array(selected_coordinates) - np.array(center_mass_screen)
        relative_position_to_poi = get_relative_direction(relative_position_vector, bearing)
        min_distance = calculate_distance(center_mass_screen, selected_coordinates)
        announce_position(selected_poi, relative_position_to_poi, min_distance)

def announce_position(poi, relative_position_to_poi, distance):
    if distance <= 40:
        speaker.speak(f"At {poi}")
    else:
        speaker.speak(f"{poi} is {relative_position_to_poi} {int(distance)} meters")
