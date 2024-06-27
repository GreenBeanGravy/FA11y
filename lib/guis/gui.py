import tkinter as tk
import threading
import time
import pyautogui
import ctypes
import configparser
from accessible_output2.outputs.auto import Auto
from functools import partial
from lib.object_finder import OBJECT_CONFIGS

speaker = Auto()

# Load POIs once at the start
with open('POI.txt', 'r') as file:
    pois_from_file = [tuple(line.strip().split(',')) for line in file]

# Game objects are now dynamically generated from OBJECT_CONFIGS
game_objects = [(name.replace('_', ' ').title(), "0", "0") for name in OBJECT_CONFIGS.keys()]

VK_RIGHT_BRACKET = 0xDD
current_poi_set = 0

def load_custom_pois():
    try:
        with open('CUSTOM_POI.txt', 'r') as file:
            return [tuple(line.strip().split(',')) for line in file if line.strip()]
    except FileNotFoundError:
        return []

def speak(s):
    speaker.speak(s)

def delayed_speak(s):
    time.sleep(0.2)
    speak(s)

def update_config_file(selected_poi_name):
    custom_pois = load_custom_pois()
    combined_pois = pois_from_file + custom_pois + [("Safe Zone", "0", "0"), ("Closest", "0", "0")] + game_objects

    config = configparser.ConfigParser()
    config.read('CONFIG.txt')
    
    if 'POI' not in config:
        config['POI'] = {}

    poi_entry = next((poi for poi in combined_pois if poi[0].lower() == selected_poi_name.lower()), None)
    if poi_entry:
        config['POI']['selected_poi'] = f'{poi_entry[0]}, {poi_entry[1]}, {poi_entry[2]}'
    else:
        config['POI']['selected_poi'] = 'none, 0, 0'

    with open('CONFIG.txt', 'w') as configfile:
        config.write(configfile)

# Add this at the top of your gui.py file, outside of any function
initial_focus_set = False

def select_poi_tk():
    root = tk.Tk()
    root.title("POI Selector")
    root.attributes('-topmost', True)
    
    buttons_frame = tk.Frame(root)
    buttons_frame.pack()

    def select_poi(poi):
        update_config_file(poi)
        speak(f"{poi} selected")
        pyautogui.click()
        root.destroy()

    def refresh_buttons(forward=True, initial=False):
        global current_poi_set
        if initial:
            current_poi_set = 0
        elif forward:
            current_poi_set = (current_poi_set + 1) % 3
        else:
            current_poi_set = (current_poi_set - 1) % 3
    
        for widget in buttons_frame.winfo_children():
            widget.destroy()
    
        if current_poi_set == 0:
            pois_to_use = [("Safe Zone", "0", "0"), ("Closest", "0", "0")] + pois_from_file
            speak("Game POIs")
        elif current_poi_set == 1:
            pois_to_use = load_custom_pois()
            speak("Custom POIs")
        else:
            pois_to_use = game_objects
            speak("Game Objects")

        if not pois_to_use:
            tk.Label(buttons_frame, text="No POIs available. Please add POIs.").pack()
            speak("No POIs available. Please add POIs.")
            return

        buttons = []
        for poi in pois_to_use:
            poi_name = poi[0] if isinstance(poi, tuple) else poi
            button = tk.Button(buttons_frame, text=poi_name, command=partial(select_poi, poi_name))
            button.pack()
            buttons.append(button)

        if buttons:
            buttons[0].focus_set()
            root.after(100, lambda: delayed_speak(buttons[0]['text']))

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
        speak(buttons[next_index]['text'])

    def on_return(event):
        focused = root.focus_get()
        if isinstance(focused, tk.Button):
            select_poi(focused['text'])

    root.bind('<Tab>', lambda e: refresh_buttons(True))
    root.bind('<Shift-Tab>', lambda e: refresh_buttons(False))
    root.bind('<Up>', navigate)
    root.bind('<Down>', navigate)
    root.bind('<Return>', on_return)

    refresh_buttons(initial=True)

    root.update()
    root.deiconify()
    root.lift()
    root.focus_force()
    root.mainloop()

def create_gui(coordinates):
    root = tk.Tk()
    root.title("POI Name Textbox")
    root.attributes('-topmost', True)

    entry = tk.Entry(root, width=20)
    entry.pack()
    entry.focus_set()

    def on_enter(event):
        poi_name = entry.get()
        if poi_name:
            with open('CUSTOM_POI.txt', 'a') as file:
                file.write(f'{poi_name},{coordinates}\n')
            speak(f"POI {poi_name} added")
        root.destroy()

    def on_up(event):
        content = entry.get()
        speak(content if content else "Text box is empty")

    entry.bind('<Return>', on_enter)
    entry.bind('<Up>', on_up)

    root.update()
    root.deiconify()
    root.lift()
    root.focus_force()
    root.mainloop()

def start_gui_activation():
    right_bracket_key_down = False
    while True:
        right_bracket_key_down = check_and_toggle_key(VK_RIGHT_BRACKET, right_bracket_key_down, select_poi_tk)
        time.sleep(0.01)

def check_and_toggle_key(key, key_down, action):
    current_state = bool(ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000)
    if current_state and not key_down:
        action()
    return current_state

if __name__ == "__main__":
    start_gui_activation()