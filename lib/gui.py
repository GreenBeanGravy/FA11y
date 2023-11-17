import tkinter as tk
import threading
import time
import pyautogui
import ctypes
from accessible_output2.outputs.auto import Auto

# Speaker for accessibility
speaker = Auto()

# Read POIs from POI.txt and keep 'Safe Zone' at the top
pois = [("Safe Zone", 0, 0)] + [(line.split(',')[0].strip(), int(line.split(',')[1]), int(line.split(',')[2])) for line in open('POI.txt', 'r')]

# Constants
VK_RIGHT_BRACKET = 0xDD

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
        update_config_file(selected_poi)
        pyautogui.click()
        root.destroy()

    buttons = []
    for poi, _, _ in pois:
        btn = tk.Button(root, text=poi, command=lambda poi=poi: select_poi(poi))
        btn.pack()
        buttons.append(btn)

    def navigate(event, direction):
        current_index = buttons.index(root.focus_get())
        new_index = max(0, min(current_index + direction, len(buttons) - 1))
        focused_button = buttons[new_index]
        focused_button.focus_set()
        speak(focused_button.cget("text"))

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

def update_config_file(selected_poi_name):
    poi_entry = next((poi for poi in pois if poi[0] == selected_poi_name), None)
    if not poi_entry:
        return

    with open('CONFIG.txt', 'r') as file:
        lines = file.readlines()

    with open('CONFIG.txt', 'w') as file:
        for line in lines:
            if line.strip().startswith('selected_poi'):
                if selected_poi_name == "Safe Zone":
                    file.write('selected_poi = Safe Zone, 0, 0\n')
                else:
                    file.write(f'selected_poi = {selected_poi_name}, {poi_entry[1]}, {poi_entry[2]}\n')
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
