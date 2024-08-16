import tkinter as tk
import time
import pyautogui
import configparser
from accessible_output2.outputs.auto import Auto
from functools import partial
from lib.object_finder import OBJECT_CONFIGS
from lib.player_location import ROI_START_ORIG, ROI_END_ORIG
from lib.utilities import force_focus_window
from lib.player_location import get_quadrant, get_position_in_quadrant

speaker = Auto()

# Load POIs once at the start
try:
    with open('POI.txt', 'r') as file:
        pois_from_file = [tuple(line.strip().split(',')) for line in file]
except FileNotFoundError:
    print("POI.txt not found. Creating an empty file.")
    open('POI.txt', 'w').close()
    pois_from_file = []

# Game objects are now dynamically generated from OBJECT_CONFIGS
game_objects = [(name.replace('_', ' ').title(), "0", "0") for name in OBJECT_CONFIGS.keys()]

current_poi_set = 0

def load_custom_pois():
    try:
        with open('CUSTOM_POI.txt', 'r') as file:
            return [tuple(line.strip().split(',')) for line in file if line.strip()]
    except FileNotFoundError:
        print("CUSTOM_POI.txt not found. Creating an empty file.")
        open('CUSTOM_POI.txt', 'w').close()
        return []

def speak(s):
    speaker.speak(s)

def delayed_speak(s):
    time.sleep(0.2)
    speak(s)

def update_config_file(selected_poi_name):
    config = configparser.ConfigParser()
    config.read('CONFIG.txt')
    
    if 'POI' not in config:
        config['POI'] = {}

    if selected_poi_name.startswith("Position,"):
        config['POI']['selected_poi'] = selected_poi_name
    else:
        # Check in pois_from_file
        poi_entry = next((poi for poi in pois_from_file if poi[0].lower() == selected_poi_name.lower()), None)
        
        # If not found, check in custom POIs
        if not poi_entry:
            custom_pois = load_custom_pois()
            poi_entry = next((poi for poi in custom_pois if poi[0].lower() == selected_poi_name.lower()), None)
        
        # If still not found, check in game objects and special POIs
        if not poi_entry:
            combined_pois = [("Safe Zone", "0", "0"), ("Closest", "0", "0")] + game_objects
            poi_entry = next((poi for poi in combined_pois if poi[0].lower() == selected_poi_name.lower()), None)
        
        if poi_entry:
            config['POI']['selected_poi'] = f'{poi_entry[0]}, {poi_entry[1]}, {poi_entry[2]}'
        else:
            config['POI']['selected_poi'] = 'none, 0, 0'

    with open('CONFIG.txt', 'w') as configfile:
        config.write(configfile)

def input_custom_coordinates(root):
    def create_coordinate_window(coordinate, min_value, max_value, callback):
        coord_window = tk.Toplevel(root)
        coord_window.title(f"{coordinate.upper()} Coordinate")
        coord_window.attributes('-topmost', True)

        entry = tk.Entry(coord_window)
        entry.pack(pady=10)
        entry.focus_set()

        speak(f"{coordinate.upper()} coordinate. Input field, blank. Enter a value between {min_value} and {max_value}")

        def on_enter(event):
            try:
                value = int(entry.get())
                if min_value <= value <= max_value:
                    coord_window.destroy()
                    callback(value)
                else:
                    speak(f"Invalid input. Please enter a value between {min_value} and {max_value}")
            except ValueError:
                speak("Invalid input. Please enter a number")

        def on_up_arrow(event):
            speak(entry.get() or "Blank")

        def on_escape(event):
            speak(f"Cancelling {coordinate} coordinate input")
            coord_window.destroy()
            root.destroy()

        entry.bind('<Return>', on_enter)
        entry.bind('<Up>', on_up_arrow)
        entry.bind('<Escape>', on_escape)

    def get_y_coordinate(x_value):
        def set_coordinates(y_value):
            # Transform coordinates to match the player icon search area
            transformed_x = x_value + ROI_START_ORIG[0]
            transformed_y = y_value + ROI_START_ORIG[1]
            
            update_config_file(f"Position,{transformed_x},{transformed_y}")
            speak(f"Custom position set to {x_value}, {y_value} in the visible area")
            pyautogui.click()
            root.destroy()

        create_coordinate_window('Input Y', 0, 820, set_coordinates)

    create_coordinate_window('Input X', 0, 900, get_y_coordinate)

def poi_sort_key(poi):
    name, x, y = poi
    x, y = int(x) - ROI_START_ORIG[0], int(y) - ROI_START_ORIG[1]
    width, height = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]
    quadrant = get_quadrant(x, y, width, height)
    position_in_quadrant = get_position_in_quadrant(x, y, width // 2, height // 2)
    
    # Create a numeric value for position_in_quadrant
    position_value = {
        "top-left": 0, "top": 1, "top-right": 2,
        "left": 3, "center": 4, "right": 5,
        "bottom-left": 6, "bottom": 7, "bottom-right": 8
    }.get(position_in_quadrant, 9)  # Default to 9 if not found
    
    return (quadrant, position_value, y, x)

def get_poi_position_description(poi):
    name, x, y = poi
    x, y = int(x) - ROI_START_ORIG[0], int(y) - ROI_START_ORIG[1]
    width, height = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]
    quadrant = get_quadrant(x, y, width, height)
    position_in_quadrant = get_position_in_quadrant(x, y, width // 2, height // 2)
    
    quadrant_names = ["top-left", "top-right", "bottom-left", "bottom-right"]
    return f"{name}, in the {position_in_quadrant} of the {quadrant_names[quadrant]} quadrant"

def select_poi_tk():
    root = tk.Tk()
    root.title("POI Selector")
    root.attributes('-topmost', True)
    
    buttons_frame = tk.Frame(root)
    buttons_frame.pack()

    def select_poi(poi):
        if poi == "Custom Coordinates":
            input_custom_coordinates(root)
        else:
            update_config_file(poi)
            speak(f"{poi} selected")
            pyautogui.click()
            root.destroy()

    def refresh_buttons(forward=True, initial=False):
        global current_poi_set
        if initial:
            current_poi_set = 0
        elif forward:
            current_poi_set = (current_poi_set + 1) % 4
        else:
            current_poi_set = (current_poi_set - 1) % 4
    
        for widget in buttons_frame.winfo_children():
            widget.destroy()
    
        if current_poi_set == 0:
            fixed_pois = [("Safe Zone", "0", "0"), ("Closest", "0", "0")]
            sorted_pois = sorted(pois_from_file, key=poi_sort_key)
            pois_to_use = fixed_pois + sorted_pois
            speak("Game P O Is")
        elif current_poi_set == 1:
            custom_pois = load_custom_pois()
            if custom_pois:
                pois_to_use = sorted(custom_pois, key=poi_sort_key)
                speak("Custom P O Is")
            else:
                tk.Label(buttons_frame, text="No custom POIs available. Go make some!").pack()
                speak("No custom P O Is available. Go make some!")
                pois_to_use = []
        elif current_poi_set == 2:
            pois_to_use = game_objects
            speak("Game Objects")
        else:
            pois_to_use = [("Custom Coordinates", "0", "0")]
            speak("Custom Coordinates")

        buttons = []
        for poi in pois_to_use:
            poi_name = poi[0] if isinstance(poi, tuple) else poi
            button = tk.Button(buttons_frame, text=poi_name, command=partial(select_poi, poi_name))
            button.pack()
            buttons.append(button)

        if buttons:
            buttons[0].focus_set()
            root.after(100, lambda: delayed_speak(get_poi_position_description(pois_to_use[0]) if isinstance(pois_to_use[0], tuple) else pois_to_use[0]))

    def navigate(event):
        buttons = [w for w in buttons_frame.winfo_children() if isinstance(w, tk.Button)]
        if not buttons:
            return
        focused = root.focus_get()
        if focused in buttons:
            current = buttons.index(focused)
            next_index = (current + (1 if event.keysym == 'Down' else -1)) % len(buttons)
        else:
            next_index = 0
        buttons[next_index].focus_set()
        
        if current_poi_set in [0, 1]:  # For Game POIs and Custom POIs
            poi = next((poi for poi in pois_from_file + load_custom_pois() if poi[0] == buttons[next_index]['text']), None)
            if poi:
                speak(get_poi_position_description(poi))
            else:
                speak(buttons[next_index]['text'])
        else:
            speak(buttons[next_index]['text'])

    def on_return(event):
        focused = root.focus_get()
        if isinstance(focused, tk.Button):
            select_poi(focused['text'])

    def on_escape(event):
        speak("Closing P O I selector")
        root.destroy()

    def on_close():
        root.destroy()
        # Explicitly delete any Tkinter variables if they exist
        for var in root.children.values():
            if isinstance(var, tk.Variable):
                var.set(None)
                del var

    root.bind('<Tab>', lambda e: refresh_buttons(True))
    root.bind('<Shift-Tab>', lambda e: refresh_buttons(False))
    root.bind('<Up>', navigate)
    root.bind('<Down>', navigate)
    root.bind('<Return>', on_return)
    root.bind('<Escape>', on_escape)
    root.protocol("WM_DELETE_WINDOW", on_close)

    refresh_buttons(initial=True)

    def focus_first_button():
        buttons = [w for w in buttons_frame.winfo_children() if isinstance(w, tk.Button)]
        if buttons:
            buttons[0].focus_set()
            poi = next((poi for poi in pois_from_file + load_custom_pois() if poi[0] == buttons[0]['text']), None)
            if poi:
                speak(get_poi_position_description(poi))
            else:
                speak(buttons[0]['text'])
        else:
            speak("No POIs available")

    root.after(100, lambda: force_focus_window(root, None, focus_first_button))

    root.mainloop()

if __name__ == "__main__":
    select_poi_tk()