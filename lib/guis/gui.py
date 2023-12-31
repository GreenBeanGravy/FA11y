import tkinter as tk
import threading
import time
import pyautogui
import ctypes
from accessible_output2.outputs.auto import Auto

# Speaker for accessibility
speaker = Auto()

# Read POIs from POI.txt
pois_from_file = [(line.split(',')[0].strip(), int(line.split(',')[1]), int(line.split(',')[2])) for line in open('POI.txt', 'r')]
game_objects = [("Combat Cache", 0, 0), ("Storm Tower", 0, 0), ("The Train", 0, 0), ("Reboot", 0, 0)]

# Constants
VK_RIGHT_BRACKET = 0xDD

# Start on the Game POIs menu
current_poi_set = 0

def select_poi_tk():
    global selected_poi

    root = tk.Tk()
    root.title("P O I Selector")

    buttons_frame = tk.Frame(root)
    buttons_frame.pack()

    def speak(s):
        speaker.speak(s)

    def delayed_speak(s):
        time.sleep(0.2)
        speak(s)

    def select_poi(poi):
        global selected_poi
        selected_poi = poi
        speak(f"{selected_poi} selected")
        # Assuming update_config_file is a function you have
        update_config_file(selected_poi)  
        pyautogui.click()
        root.destroy()

    def load_custom_pois():
        try:
            with open('CUSTOM_POI.txt', 'r') as file:
                return [(line.split(',')[0].strip(), int(line.split(',')[1]), int(line.split(',')[2])) for line in file if line.strip()]
        except FileNotFoundError:
            return

    def refresh_buttons(forward=True, initial=False):
        global current_poi_set
        if initial:
            current_poi_set = 0  # Start with Game POIs
        elif forward:
            current_poi_set = (current_poi_set + 1) % 3  # Forward
        else:
            current_poi_set = (current_poi_set - 1) % 3  # Backward
    
        for widget in buttons_frame.winfo_children():
            widget.destroy()
    
        if current_poi_set == 0:
            pois_to_use = [("Safe Zone", 0, 0), ("Closest", 0, 0)] + pois_from_file
            speaker.speak("Game POIs")
        elif current_poi_set == 1:
            pois_to_use = load_custom_pois()
            speaker.speak("Custom POIs")
        else:
            pois_to_use = game_objects
            speaker.speak("Game Objects")

        if not pois_to_use:
            no_poi_label = tk.Label(buttons_frame, text="No POIs available. Please add POIs.")
            no_poi_label.pack()
            speak("No POIs available. Please add POIs.")
            return

        for poi, _, _ in pois_to_use:
            btn = tk.Button(buttons_frame, text=poi, command=lambda poi=poi: select_poi(poi))
            btn.pack()

        if buttons_frame.winfo_children():
            first_button = buttons_frame.winfo_children()[0]
            first_button.focus_set()
            # Delayed speak to announce the first button on the list
            threading.Thread(target=delayed_speak, args=(first_button.cget("text"),), daemon=True).start()

    def navigate(event, direction):
        buttons = [widget for widget in buttons_frame.winfo_children() if isinstance(widget, tk.Button)]
        if not buttons:
            return

        current_index = buttons.index(root.focus_get())
        new_index = max(0, min(current_index + direction, len(buttons) - 1))
        focused_button = buttons[new_index]
        focused_button.focus_set()
        speak(focused_button.cget("text"))

    root.bind('<Tab>', lambda e: refresh_buttons(forward=True))
    root.bind('<Shift-Tab>', lambda e: refresh_buttons(forward=False))
    root.bind('<Up>', lambda e: navigate(e, -1))
    root.bind('<Down>', lambda e: navigate(e, 1))
    root.bind('<Return>', lambda e: select_poi(root.focus_get().cget("text")))

    root.update_idletasks()
    root.deiconify()
    root.lift()
    root.attributes('-topmost', True)
    root.after_idle(root.attributes, '-topmost', False)
    root.focus_force()

    root.update_idletasks()
    root.deiconify()
    root.lift()
    root.attributes('-topmost', True)
    root.after_idle(root.attributes, '-topmost', False)
    root.focus_force()

    refresh_buttons(initial=True)  # Load with Game POIs initially

    root.mainloop()

def create_gui(coordinates):
    root = tk.Tk()
    root.title("P O I Name Textbox")

    def speak(s):
        speaker.speak(s)

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
        if content:
            speak(content)
        else:
            speak("Text box is empty")

    entry.bind('<Return>', on_enter)
    entry.bind('<Up>', on_up)

    root.update_idletasks()
    root.deiconify()
    root.lift()
    root.attributes('-topmost', True)
    root.after_idle(root.attributes, '-topmost', False)
    root.focus_force()
    root.mainloop()

def update_config_file(selected_poi_name):
    # Load custom POIs
    custom_pois = []
    try:
        with open('CUSTOM_POI.txt', 'r') as file:
            custom_pois = [(line.split(',')[0].strip(), line.split(',')[1].strip(), line.split(',')[2].strip()) for line in file if line.strip()]
    except FileNotFoundError:
        pass

    # Combine regular (from POI.txt) and custom POIs
    combined_pois = pois_from_file + custom_pois

    # Update the CONFIG.txt file
    with open('CONFIG.txt', 'r') as file:
        lines = file.readlines()

    with open('CONFIG.txt', 'w') as file:
        for line in lines:
            if line.strip().startswith('selected_poi'):
                if selected_poi_name in [poi[0] for poi in game_objects + [("Safe Zone", 0, 0), ("Closest", 0, 0)]]:  # Include 'Closest P O I' in the check
                    file.write(f'selected_poi = {selected_poi_name.lower()}, 0, 0\n')  # Use lower case for 'closest'
                else:
                    # Find the selected POI in the combined list
                    poi_entry = next((poi for poi in combined_pois if poi[0] == selected_poi_name), None)
                    if poi_entry:
                        # Write the actual coordinates for non-game objects
                        file.write(f'selected_poi = {poi_entry[0]}, {poi_entry[1]}, {poi_entry[2]}\n')
            else:
                file.write(line)

def check_and_toggle_key(key, key_down, action):
    current_state = bool(ctypes.windll.user32.GetAsyncKeyState(key))
    if current_state and not key_down: action()
    return current_state

def start_gui_activation():
    right_bracket_key_down = False
    while True:
        right_bracket_key_down = check_and_toggle_key(VK_RIGHT_BRACKET, right_bracket_key_down, select_poi_tk)
        time.sleep(0.01)
