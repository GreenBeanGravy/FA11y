import tkinter as tk
import time
import pyautogui
from pyautogui import typewrite
import configparser
import os
from accessible_output2.outputs.auto import Auto
from functools import partial
from lib.object_finder import OBJECT_CONFIGS

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

GAMEMODES_FOLDER = "GAMEMODES"

def load_gamemodes():
    gamemodes = []
    if not os.path.exists(GAMEMODES_FOLDER):
        print(f"'{GAMEMODES_FOLDER}' folder not found. Creating it.")
        os.makedirs(GAMEMODES_FOLDER)
        return gamemodes

    for filename in os.listdir(GAMEMODES_FOLDER):
        if filename.endswith(".txt"):
            try:
                with open(os.path.join(GAMEMODES_FOLDER, filename), 'r') as file:
                    lines = file.readlines()
                    if len(lines) >= 2:
                        gamemode_name = filename[:-4]  # Remove .txt extension
                        gamemode_text = lines[0].strip()
                        team_sizes = lines[1].strip().split(',')
                        gamemodes.append((gamemode_name, gamemode_text, team_sizes))
            except Exception as e:
                print(f"Error reading {filename}: {str(e)}")
    return gamemodes

def smooth_move_and_click(x, y, duration=0.2):
    pyautogui.moveTo(x, y, duration=duration)
    pyautogui.click()

def select_gamemode(gamemode):
    # Click on game mode selection
    smooth_move_and_click(172, 67)
    time.sleep(0.5)

    # Click at 900, 200
    smooth_move_and_click(900, 200)
    time.sleep(0.1)  # Wait 100ms before clearing the field

    # Clear the field using backspace - improved method
    pyautogui.typewrite('\b' * 50, interval=0.01)

    # Type the new gamemode
    pyautogui.write(gamemode[1])
    pyautogui.press('enter')

    # Wait for white pixel with a 5-second timeout
    start_time = time.time()
    while not pyautogui.pixelMatchesColor(84, 328, (255, 255, 255)):
        if time.time() - start_time > 5:
            speaker.speak("Timed out waiting for game mode to load.")
            return False
        time.sleep(0.1)
    time.sleep(0.1)

    # Click on game mode
    smooth_move_and_click(300, 515)
    time.sleep(0.7)

    # Click on play button
    smooth_move_and_click(285, 910)
    time.sleep(0.5)

    # Press 'B' twice
    pyautogui.press('b')
    time.sleep(0.05)
    pyautogui.press('b')

    speaker.speak(f"{gamemode[0]} selected")
    return True

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

def select_poi_tk():
    root = tk.Tk()
    root.title("P O I Selector")
    root.attributes('-topmost', True)
    
    buttons_frame = tk.Frame(root)
    buttons_frame.pack()

    def select_poi(poi):
        update_config_file(poi)
        speak(f"{poi} selected")
        smooth_move_and_click(pyautogui.position()[0], pyautogui.position()[1])
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
            speak("Game P O Is")
        elif current_poi_set == 1:
            pois_to_use = load_custom_pois()
            speak("Custom P O Is")
        else:
            pois_to_use = game_objects
            speak("Game Objects")

        if not pois_to_use:
            tk.Label(buttons_frame, text="No custom POIs available. Go make some!").pack()
            speak("No custom P O Is available. Go make some!")
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

    def on_escape(event):
        speak("Closing P O I selector")
        root.destroy()

    root.bind('<Tab>', lambda e: refresh_buttons(True))
    root.bind('<Shift-Tab>', lambda e: refresh_buttons(False))
    root.bind('<Up>', navigate)
    root.bind('<Down>', navigate)
    root.bind('<Return>', on_return)
    root.bind('<Escape>', on_escape)

    refresh_buttons(initial=True)

    root.update()
    root.deiconify()
    root.lift()
    root.focus_force()
    root.mainloop()

def select_gamemode_tk():
    gamemodes = load_gamemodes()

    if not gamemodes:
        speak("No game modes available. Please add game mode files to the GAMEMODES folder.")
        return

    root = tk.Tk()
    root.title("Gamemode Selector")
    root.attributes('-topmost', True)
    
    buttons_frame = tk.Frame(root)
    buttons_frame.pack()

    def select_gamemode_action(gamemode):
        root.destroy()
        if select_gamemode(gamemode):
            return
        speak("Failed to select gamemode. Please try again.")

    buttons = []
    for gamemode in gamemodes:
        button = tk.Button(buttons_frame, text=gamemode[0], command=partial(select_gamemode_action, gamemode))
        button.pack()
        buttons.append(button)

    def navigate(event):
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
            select_gamemode_action(gamemodes[buttons.index(focused)])

    def on_escape(event):
        speak("Closing gamemode selector")
        root.destroy()

    root.bind('<Up>', navigate)
    root.bind('<Down>', navigate)
    root.bind('<Return>', on_return)
    root.bind('<Escape>', on_escape)

    if buttons:
        buttons[0].focus_set()
        root.after(100, lambda: delayed_speak(buttons[0]['text']))

    root.update()
    root.deiconify()
    root.lift()
    root.focus_force()
    root.mainloop()

def create_gui(coordinates):
    root = tk.Tk()
    root.title("Enter custom P O I name")
    root.attributes('-topmost', True)

    def speak_element(text):
        # Add spaces between P, O, and I when speaking
        spoken_text = text.replace("POI", "P O I")
        speaker.speak(spoken_text)

    speak_element("Enter custom P O I name")

    label = tk.Label(root, text="Enter POI Name:")
    label.pack(pady=5)
    speak_element("Enter P O I Name")

    name_entry = tk.Entry(root)
    name_entry.pack(pady=5)

    def on_key_press(event):
        if event.char:
            speak_element(event.char)

    name_entry.bind('<KeyPress>', on_key_press)

    def save_poi():
        poi_name = name_entry.get().strip()
        if poi_name:
            with open('CUSTOM_POI.txt', 'a') as file:
                file.write(f"{poi_name},{coordinates[0]},{coordinates[1]}\n")
            speak_element(f"Custom P O I {poi_name} saved")
            root.destroy()
            # Perform a smooth move and click to refocus on the Fortnite window
            smooth_move_and_click(pyautogui.position()[0], pyautogui.position()[1])
        else:
            speak_element("Please enter a name for the P O I")

    def on_enter(event):
        save_poi()

    def on_up_arrow(event):
        content = name_entry.get()
        speak_element(content if content else "Text box is empty")

    def on_tab(event):
        focused = root.focus_get()
        if focused == name_entry:
            save_button.focus_set()
            speak_element("Save P O I button")
        else:
            name_entry.focus_set()
            speak_element("P O I Name entry field")
        return "break"  # Prevents default tab behavior

    save_button = tk.Button(root, text="Save POI", command=save_poi)
    save_button.pack(pady=10)

    root.bind('<Return>', on_enter)
    root.bind('<Up>', on_up_arrow)
    root.bind('<Tab>', on_tab)

    def on_escape(event):
        speak_element("Cancelling Custom P O I creation")
        root.destroy()

    root.bind('<Escape>', on_escape)

    root.geometry("300x150")

    # Ensure window comes into focus
    def focus_window():
        root.deiconify()  # Ensure the window is not minimized
        root.focus_force()  # Force focus on the window
        root.lift()  # Raise the window to the top
        name_entry.focus_set()  # Set focus to the entry field
        speak_element("P O I Name entry field")

    # Use after() to call focus_window after the window has been created
    root.after(100, focus_window)

    root.mainloop()

# Expose the necessary functions
__all__ = ['select_poi_tk', 'select_gamemode_tk', 'create_gui']
