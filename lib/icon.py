import cv2
import numpy as np
import pyautogui
import ctypes
import threading
import time
import tkinter as tk
from tkinter import ttk
from accessible_output2.outputs.auto import Auto

speaker = Auto()

# Define the minimum white shape size and the region of interest
min_shape_size = 1500  # The minimum amount of white pixels in a contour in order to be counted
max_shape_size = 3000  # The maximum amount of white pixels in a contour in order to be counted, prevents the next-storm outline from being counted most of the time
roi_start_orig = (621, 182)  # Top-left corner of the map
roi_end_orig = (1342, 964)  # Bottom-right corner of the map

VK_RIGHT_BRACKET = 0xDD
VK_GRAVE_ACCENT = 0xC0
right_bracket_key_down = False
grave_accent_key_down = False

selected_poi = None

icon_detection_active = False

# Method to display a menu and allow the user to select a POI
def select_poi_tk():
    global selected_poi

    def speak(s):
        speaker.speak(s)

    def on_select(poi):
        global selected_poi
        selected_poi = poi
        # Speak the selected POI name immediately
        speak(f"{selected_poi} selected")
        root.destroy()

    def on_navigate(poi_name):
        # Speak the current POI name
        speak(poi_name)

    def navigate(event):
        focused_button = root.focus_get()
        if focused_button:
            index = buttons.index(focused_button)
            if event.keysym == 'Up' and index > 0:
                buttons[index - 1].focus_set()
            elif event.keysym == 'Down' and index < len(buttons) - 1:
                buttons[index + 1].focus_set()

    root = tk.Tk()
    root.title("Select a P O I")

    buttons = []
    for poi, _, _ in pois:  # Only using the first value (name) from each tuple
        btn = tk.Button(root, text=poi, command=lambda poi=poi: on_select(poi))
        btn.bind('<FocusIn>', lambda event, poi=poi: on_navigate(poi))
        btn.pack()
        buttons.append(btn)

    # Bind the Up and Down arrow keys to navigate
    root.bind('<Up>', navigate)
    root.bind('<Down>', navigate)
    root.bind('<Return>', lambda event: on_select(root.focus_get().cget("text")))

    # Give focus to the first button
    if buttons:
        buttons[0].focus_set()

    # Bring the window to the front and give it focus
    root.lift()
    root.attributes('-topmost', True)
    root.after_idle(root.attributes, '-topmost', False)
    root.focus_force()

    root.mainloop()

def get_relative_direction(vector, target_bearing):
    # Adjust for the different coordinate system
    adjusted_vector = np.array([vector[0], -vector[1]])

    # Calculate the angle in degrees from the vector to the positive x axis
    degree = np.degrees(np.arctan2(adjusted_vector[1], adjusted_vector[0]))

    # Normalize the bearing to match our custom compass
    degree = (degree + 360) % 360
    target_bearing = (target_bearing + 360) % 360

    relative_bearing = (degree - target_bearing + 360) % 360

    compass_brackets = [22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5]
    compass_labels = ['behind', 'behind and slightly to the left', 'to the left of', 'behind and slightly to the right', 'to the right of', 'slightly to the right of', 'in front of', 'slightly to the left of']

    for i, val in enumerate(compass_brackets):
        if relative_bearing < val:
            return compass_labels[i]
    
    return 'in front of'

def calculate_distance(point1, point2):
    return np.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2) * 2

# Load Points of Interest (POIs)
pois = []
with open('POI.txt', 'r') as file:
    for line in file.readlines():
        name, x, y = line.strip().split(',')
        pois.append((name, int(x), int(y)))

def start_icon_detection():
    global right_bracket_key_down, grave_accent_key_down
    global selected_poi  # Make sure selected_poi is globally defined

    while True:
        # Capture the "]" key press to open Tkinter window for POI selection
        right_bracket_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_RIGHT_BRACKET))
        if right_bracket_key_current_state and not right_bracket_key_down:
            select_poi_tk()
        right_bracket_key_down = right_bracket_key_current_state

        # Find the coordinates of the selected_poi
        selected_coordinates = None
        for name, x, y in pois:
            if name == selected_poi:
                selected_coordinates = (x, y)
                break

        # Capture the grave accent key press to invoke icon detection once
        grave_accent_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_GRAVE_ACCENT))
        if grave_accent_key_current_state and not grave_accent_key_down:
            print("Starting icon detection for one cycle.")

            # Check if a POI has been selected
            if selected_poi is None:
                print("No POI has been selected. Please select a POI first by pressing the right bracket key.")
                speaker.speak("No P O I has been selected. Please select a P O I first by pressing the right bracket key.")

            pyautogui.moveTo(1900, 1000, duration=0.1, tween=pyautogui.easeInOutQuad)
            screenshot = pyautogui.screenshot()
            screenshot_np = np.array(screenshot)
            screenshot_np = cv2.resize(screenshot_np, None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
            roi_start = tuple(4 * np.array(roi_start_orig))
            roi_end = tuple(4 * np.array(roi_end_orig))
            roi_color = screenshot_np[roi_start[1]:roi_end[1], roi_start[0]:roi_end[0]]
            roi_gray = cv2.cvtColor(roi_color, cv2.COLOR_BGR2GRAY)
            _, thresholded = cv2.threshold(roi_gray, 230, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(thresholded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            valid_contours = [cnt for cnt in contours if min_shape_size < cv2.contourArea(cnt) < max_shape_size]
            if valid_contours:
                largest_contour = max(valid_contours, key=cv2.contourArea)
                area = cv2.contourArea(largest_contour)  # Bring back the 'area' variable
                print(f"{area}")
                M = cv2.moments(largest_contour)
                cX = int(M["m10"] / M["m00"])
                cY = int(M["m01"] / M["m00"])
                center_mass = (cX, cY)
                center_mass_screen = ((center_mass[0] // 4) + roi_start_orig[0], (center_mass[1] // 4) + roi_start_orig[1])
                hull = cv2.convexHull(largest_contour)
    
                if len(hull) > 2:
                    vertices = np.squeeze(hull)
                    distances = [np.linalg.norm(vertices[i] - center_mass) for i in range(len(vertices))]
                    farthest_vertex_index = np.argmax(distances)
                    farthest_vertex = vertices[farthest_vertex_index]
                    direction_vector = farthest_vertex - np.array(center_mass)
                    bearing = 90 - np.degrees(np.arctan2(direction_vector[1], direction_vector[0]))
                    adjusted_bearing = (bearing - 180) % 360
    
                    if selected_coordinates:
                        relative_position_vector = np.array(selected_coordinates) - np.array(center_mass_screen)
                        relative_position_to_poi = get_relative_direction(relative_position_vector, bearing)
                        min_distance = calculate_distance(center_mass_screen, selected_coordinates)
                        
                        if min_distance <= 50:
                            print(f"You are at {selected_poi}")
                            speaker.speak(f"You are at {selected_poi}")
                        else:
                            print(f"{selected_poi} is {relative_position_to_poi} you at a distance of {int(min_distance)} meters")
                            speaker.speak(f"{selected_poi} is {relative_position_to_poi} you at a distance of {int(min_distance)} meters")

                # Draw the contour on the cropped region of interest
                cv2.drawContours(roi_color, [largest_contour], -1, (0, 255, 0), 2)
                
                # Draw the center of mass
                cv2.circle(roi_color, center_mass, 10, (255, 0, 0), -1)
                
                # cv2.imwrite('image.jpg', roi_color)
                # You can remove the comment above to make the output image save, useful for debugging
    
            else:
                print("Could not locate the player icon")
                speaker.speak(f"Could not locate the player icon")
            
            print("Icon detection cycle completed.")

        grave_accent_key_down = grave_accent_key_current_state
    
        time.sleep(0.01)