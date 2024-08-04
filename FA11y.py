import sys
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import ctypes
import configparser
import threading
import time
import win32api
import win32con
import keyboard
import subprocess
import winshell
import pyautogui
from win32com.client import Dispatch
import pygame
import requests

if sys.platform.startswith('win'):
    ctypes.windll.kernel32.SetConsoleTitleW("FA11y")
elif sys.platform.startswith('linux') or sys.platform.startswith('darwin'):
    sys.stdout.write("\x1b]2;FA11y\x07")
    sys.stdout.flush()

# Check Python version and create mock imp if necessary
if sys.version_info >= (3, 12):
    class MockImp:
        __name__ = 'imp'
        
        @staticmethod
        def is_frozen(arg=None):
            if arg == "__main__":
                return hasattr(sys, "frozen") or '__compiled__' in globals()
            return hasattr(sys, 'frozen') or hasattr(sys, 'importers') or getattr(sys, 'frozen', False)

    sys.modules['imp'] = MockImp()

from accessible_output2.outputs.auto import Auto
from lib.icon import start_icon_detection, create_custom_poi
from lib.hsr import start_health_shield_rarity_detection, check_health_shields, check_rarity
from lib.mouse import smooth_move_mouse, left_mouse_down, left_mouse_up, right_mouse_down, right_mouse_up, mouse_scroll
from lib.guis.gui import select_poi_tk, select_gamemode_tk, create_gui
from lib.height_checker import start_height_checker
from lib.minimap_direction import speak_minimap_direction
from lib.guis.config_gui import create_config_gui
from lib.exit_match import exit_match
from lib.hotbar_detection import initialize_hotbar_detection, detect_hotbar_item

# Initialize pygame mixer
pygame.mixer.init()

# Load the update sound
update_sound = pygame.mixer.Sound("sounds/update.ogg")

# GitHub repository details
REPO_OWNER = "GreenBeanGravy"
REPO_NAME = "FA11y"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/main"

# Constants
CONFIG_FILE = 'config.txt'
DEFAULT_CONFIG = """[SETTINGS]
MouseKeys = true
UsingResetSensitivity = false
EnableAutoUpdates = true
CreateDesktopShortcut = true
AutoTurn = true
TurnSensitivity = 100
SecondaryTurnSensitivity = 50
TurnAroundSensitivity = 1158
ScrollAmount = 120
RecenterDelay = 0.01
TurnDelay = 0.01
TurnSteps = 5
RecenterSteps = 20
RecenterStepDelay = 1
RecenterStepSpeed = 0
RecenterVerticalMove = 1500
RecenterVerticalMoveBack = -820
SecondaryRecenterVerticalMove = 1500
SecondaryRecenterVerticalMoveBack = -580

[THREADS]
EnableIconDetection = true
EnableCustomPOI = true
EnableGUIActivation = true
EnableHeightChecker = true
EnableHSRDetection = true
EnableHotbarDetection = true

[SCRIPT KEYBINDS]
Locate Player Icon = grave
Create Custom POI = backslash
Fire = lctrl
Target = rctrl
Turn Left = num 1
Turn Right = num 3
SecondaryTurn Left = num 4
SecondaryTurn Right = num 6
Look Up = num 8
Look Down = num 2
Turn Around = num 0
Recenter = num 5
Scroll Up = num 7
Scroll Down = num 9
Speak Minimap Direction = semicolon
Check Health Shields = h
Check Rarity = bracketleft
Select POI = bracketright
Select Gamemode = apostrophe
Open Configuration = f9
Exit Match = f12
Detect Hotbar 1 = 1
Detect Hotbar 2 = 2
Detect Hotbar 3 = 3
Detect Hotbar 4 = 4
Detect Hotbar 5 = 5

[POI]
selected_poi = closest, 0, 0"""

VK_NUMPAD = {
    'num 0': win32con.VK_NUMPAD0,
    'num 1': win32con.VK_NUMPAD1,
    'num 2': win32con.VK_NUMPAD2,
    'num 3': win32con.VK_NUMPAD3,
    'num 4': win32con.VK_NUMPAD4,
    'num 5': win32con.VK_NUMPAD5,
    'num 6': win32con.VK_NUMPAD6,
    'num 7': win32con.VK_NUMPAD7,
    'num 8': win32con.VK_NUMPAD8,
    'num 9': win32con.VK_NUMPAD9,
    'num period': win32con.VK_DECIMAL,
    'num .': win32con.VK_DECIMAL,
    'num +': win32con.VK_ADD,
    'num -': win32con.VK_SUBTRACT,
    'num *': win32con.VK_MULTIPLY,
    'num /': win32con.VK_DIVIDE,
}

# Define other special keys
SPECIAL_KEYS = {
    'lctrl': win32con.VK_LCONTROL,
    'rctrl': win32con.VK_RCONTROL,
    'lshift': win32con.VK_LSHIFT,
    'rshift': win32con.VK_RSHIFT,
    'lalt': win32con.VK_LMENU,
    'ralt': win32con.VK_RMENU,
    'f1': win32con.VK_F1,
    'f2': win32con.VK_F2,
    'f3': win32con.VK_F3,
    'f4': win32con.VK_F4,
    'f5': win32con.VK_F5,
    'f6': win32con.VK_F6,
    'f7': win32con.VK_F7,
    'f8': win32con.VK_F8,
    'f9': win32con.VK_F9,
    'f10': win32con.VK_F10,
    'f11': win32con.VK_F11,
    'f12': win32con.VK_F12,
    'tab': win32con.VK_TAB,
    'capslock': win32con.VK_CAPITAL,
    'space': win32con.VK_SPACE,
    'backspace': win32con.VK_BACK,
    'enter': win32con.VK_RETURN,
    'esc': win32con.VK_ESCAPE,
    'insert': win32con.VK_INSERT,
    'delete': win32con.VK_DELETE,
    'home': win32con.VK_HOME,
    'end': win32con.VK_END,
    'pageup': win32con.VK_PRIOR,
    'pagedown': win32con.VK_NEXT,
    'up': win32con.VK_UP,
    'down': win32con.VK_DOWN,
    'left': win32con.VK_LEFT,
    'right': win32con.VK_RIGHT,
    'printscreen': win32con.VK_PRINT,
    'scrolllock': win32con.VK_SCROLL,
    'pause': win32con.VK_PAUSE,
    'numlock': win32con.VK_NUMLOCK,
    'bracketleft': 0xDB,    # '['
    'bracketright': 0xDD,   # ']'
    'apostrophe': 0xDE,     # '''
    'grave': 0xC0,          # '`'
    'backslash': 0xDC,      # '\'
    'semicolon': 0xBA,      # ';'
    'period': 0xBE,         # '.'
}

speaker = Auto()
key_state = {}
action_handlers = {}
config = None
key_bindings = {}
key_listener_thread = None
stop_key_listener = threading.Event()
config_gui_open = threading.Event()

def is_numlock_on():
    return win32api.GetKeyState(win32con.VK_NUMLOCK) & 1 != 0

def is_key_pressed(key):
    key_lower = key.lower()
    if key_lower in VK_NUMPAD:
        return win32api.GetAsyncKeyState(VK_NUMPAD[key_lower]) & 0x8000 != 0
    elif key_lower in SPECIAL_KEYS:
        return win32api.GetAsyncKeyState(SPECIAL_KEYS[key_lower]) & 0x8000 != 0
    else:
        try:
            vk_code = ord(key.upper())
            return win32api.GetAsyncKeyState(vk_code) & 0x8000 != 0
        except:
            print(f"Unrecognized key: {key}. Skipping...")
            return False

def handle_movement(action, reset_sensitivity):
    global config
    turn_sensitivity = config.getint('SETTINGS', 'TurnSensitivity', fallback=100)
    secondary_turn_sensitivity = config.getint('SETTINGS', 'SecondaryTurnSensitivity', fallback=50)
    turn_delay = config.getfloat('SETTINGS', 'TurnDelay', fallback=0.01)
    turn_steps = config.getint('SETTINGS', 'TurnSteps', fallback=5)
    recenter_delay = config.getfloat('SETTINGS', 'RecenterDelay', fallback=0.05)
    recenter_steps = config.getint('SETTINGS', 'RecenterSteps', fallback=10)
    recenter_step_delay = config.getfloat('SETTINGS', 'RecenterStepDelay', fallback=0) / 1000  # Convert ms to seconds
    recenter_step_speed = config.getint('SETTINGS', 'RecenterStepSpeed', fallback=150)
    x_move, y_move = 0, 0

    if action in ['turn left', 'turn right', 'secondaryturn left', 'secondaryturn right', 'look up', 'look down']:
        sensitivity = secondary_turn_sensitivity if 'secondary' in action else turn_sensitivity
        if 'left' in action:
            x_move = -sensitivity
        elif 'right' in action:
            x_move = sensitivity
        elif action == 'look up':
            y_move = -sensitivity
        elif action == 'look down':
            y_move = sensitivity
        
        smooth_move_mouse(x_move, y_move, turn_delay, turn_steps)
        return
    elif action == 'turn around':
        x_move = config.getint('SETTINGS', 'TurnAroundSensitivity', fallback=1158)
        smooth_move_mouse(x_move, 0, turn_delay, turn_steps)
        return
    elif action == 'recenter':
        if reset_sensitivity:
            recenter_move = config.getint('SETTINGS', 'SecondaryRecenterVerticalMove', fallback=1500)
            down_move = config.getint('SETTINGS', 'SecondaryRecenterVerticalMoveBack', fallback=-580)
        else:
            recenter_move = config.getint('SETTINGS', 'RecenterVerticalMove', fallback=1500)
            down_move = config.getint('SETTINGS', 'RecenterVerticalMoveBack', fallback=-820)
        
        # Perform recentering movements
        smooth_move_mouse(0, recenter_move, recenter_step_delay, recenter_steps, recenter_step_speed, down_move, recenter_delay)
        speaker.speak("Reset Camera")
        return

    smooth_move_mouse(x_move, y_move, recenter_delay)

def normalize_key(key):
    key_mapping = {
        '`': 'grave',
        '\\': 'backslash',
        ';': 'semicolon',
        '[': 'bracketleft',
        ']': 'bracketright',
        "'": 'apostrophe',
        '.': 'period',
    }
    return key_mapping.get(key, key)

def handle_scroll(action):
    global config
    scroll_amount = config.getint('SETTINGS', 'ScrollAmount', fallback=120)
    if action == 'scroll down':
        scroll_amount = -scroll_amount
    mouse_scroll(scroll_amount)

def update_config(config):
    default_config = configparser.ConfigParser(interpolation=None)
    default_config.optionxform = str  # Preserve case of keys
    default_config.read_string(DEFAULT_CONFIG)
    
    updated = False
    
    for section in default_config.sections():
        if not config.has_section(section):
            config.add_section(section)
            updated = True
        
        # Get all keys in the current section (case-insensitive)
        existing_keys = {k.lower(): k for k in config[section]}
        
        for key, value in default_config.items(section):
            lower_key = key.lower()
            
            if lower_key in existing_keys:
                # If the key exists (case-insensitive), but the case doesn't match
                if existing_keys[lower_key] != key:
                    current_value = config[section][existing_keys[lower_key]]
                    config.remove_option(section, existing_keys[lower_key])
                    config.set(section, key, current_value)
                    updated = True
            else:
                # If the key doesn't exist at all, add it
                config.set(section, key, value)
                updated = True
    
    # Remove any keys that exist in the config but not in the default config
    for section in config.sections():
        if section in default_config.sections():
            for key in list(config[section].keys()):
                if key not in default_config[section]:
                    config.remove_option(section, key)
                    updated = True
    
    if updated:
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
        print(f"Updated config file with correct casing and removed obsolete entries: {CONFIG_FILE}")

def read_config():
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str  # Preserve case of keys
    
    if not os.path.exists(CONFIG_FILE):
        config.read_string(DEFAULT_CONFIG)
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
        print(f"Created new config file: {CONFIG_FILE}")
    else:
        config.read(CONFIG_FILE)
        update_config(config)
    
    return config

def key_listener():
    global key_bindings, key_state, action_handlers, stop_key_listener, config_gui_open
    while not stop_key_listener.is_set():
        if not config_gui_open.is_set():
            numlock_on = is_numlock_on()

            for action, key in key_bindings.items():
                if not key:  # Skip if the keybind is empty
                    continue
                
                normalized_key = normalize_key(key)
                key_pressed = is_key_pressed(normalized_key)
                action_lower = action.lower()

                # Skip actions that don't have handlers
                if action_lower not in action_handlers:
                    continue

                if action_lower in ['fire', 'target'] and not numlock_on:
                    continue

                if key_pressed != key_state.get(normalized_key, False):
                    key_state[normalized_key] = key_pressed
                    if key_pressed:
                        print(f"Detected key press for action: {action_lower}")
                        action_handler = action_handlers.get(action_lower)
                        if action_handler:
                            action_handler()
                            print(f"Action '{action_lower}' activated.")
                    else:
                        print(f"{action_lower} button released.")
                        if action_lower in ['fire', 'target']:
                            (left_mouse_up if action_lower == 'fire' else right_mouse_up)()

        time.sleep(0.001)

def create_desktop_shortcut():
    desktop = winshell.desktop()
    path = os.path.join(desktop, "FA11y.lnk")
    target = os.path.abspath(sys.argv[0])
    wDir = os.path.dirname(target)
    
    shell = Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(path)
    shortcut.Targetpath = target
    shortcut.WorkingDirectory = wDir
    shortcut.save()

def reload_config():
    global config, action_handlers, key_bindings
    config = read_config()
    
    # Update key bindings
    key_bindings = {key.lower(): value.lower() for key, value in config.items('SCRIPT KEYBINDS') if value}  # Only include non-empty keybinds
    
    # Update action handlers based on new config
    mouse_keys_enabled = config.getboolean('SETTINGS', 'MouseKeys', fallback=True)
    reset_sensitivity = config.getboolean('SETTINGS', 'UsingResetSensitivity', fallback=False)
    
    action_handlers.clear()  # Clear existing handlers
    
    if config.getboolean('THREADS', 'EnableIconDetection', fallback=True):
        action_handlers['locate player icon'] = start_icon_detection
    if config.getboolean('THREADS', 'EnableCustomPOI', fallback=True):
        action_handlers['create custom poi'] = lambda: create_gui(pyautogui.position())

    if mouse_keys_enabled:
        action_handlers.update({
            'fire': left_mouse_down,
            'target': right_mouse_down,
            'turn left': lambda: handle_movement('turn left', reset_sensitivity),
            'turn right': lambda: handle_movement('turn right', reset_sensitivity),
            'secondaryturn left': lambda: handle_movement('secondaryturn left', reset_sensitivity),
            'secondaryturn right': lambda: handle_movement('secondaryturn right', reset_sensitivity),
            'look up': lambda: handle_movement('look up', reset_sensitivity),
            'look down': lambda: handle_movement('look down', reset_sensitivity),
            'turn around': lambda: handle_movement('turn around', reset_sensitivity),
            'recenter': lambda: handle_movement('recenter', reset_sensitivity),
            'scroll up': lambda: handle_scroll('scroll up'),
            'scroll down': lambda: handle_scroll('scroll down')
        })
    
    action_handlers['speak minimap direction'] = speak_minimap_direction
    action_handlers['check health shields'] = check_health_shields
    action_handlers['check rarity'] = check_rarity
    action_handlers['select poi'] = select_poi_tk
    action_handlers['select gamemode'] = select_gamemode_tk
    action_handlers['open configuration'] = open_config_gui
    action_handlers['exit match'] = exit_match
    
    # Add hotbar detection handlers
    if config.getboolean('THREADS', 'EnableHotbarDetection', fallback=True):
        for i in range(1, 6):
            action_handlers[f'detect hotbar {i}'] = lambda slot=i-1: detect_hotbar_item(slot)
    
    print("Configuration reloaded")
    speaker.speak("Configuration updated")

def update_script_config(new_config):
    global config, key_listener_thread, stop_key_listener
    config = new_config
    reload_config()
    
    # Signal the current key listener to stop
    stop_key_listener.set()
    
    # Start a new key listener thread with new bindings
    stop_key_listener.clear()
    key_listener_thread = threading.Thread(target=key_listener, daemon=True)
    key_listener_thread.start()

def open_config_gui():
    config_gui_open.set()
    create_config_gui(update_script_config)
    config_gui_open.clear()

def run_updater():
    result = subprocess.run([sys.executable, 'updater.py', '--run-by-fa11y'], capture_output=True, text=True)
    return result.returncode == 1  # Return True if updates were applied

def check_for_updates():
    last_commit_sha = None
    
    while True:
        try:
            response = requests.get(API_URL)
            if response.status_code == 200:
                current_commit = response.json()['sha']
                
                if last_commit_sha is not None and current_commit != last_commit_sha:
                    # New commit detected
                    update_sound.play()
                    speaker.speak("An update is available for FA11y! Restart FA11y to update!")
                
                last_commit_sha = current_commit
            
            else:
                print(f"Failed to fetch commits. Status code: {response.status_code}")
        
        except Exception as e:
            print(f"Error checking for updates: {str(e)}")
        
        # Wait for 120 seconds before checking again
        time.sleep(120)

def main():
    global config, action_handlers, key_bindings, key_listener_thread, stop_key_listener
    try:
        print("Starting FA11y...")
        
        config = read_config()

        if config.getboolean('SETTINGS', 'EnableAutoUpdates', fallback=True):
            if run_updater():
                sys.exit(0)  # Exit the script

        if config.getboolean('SETTINGS', 'CreateDesktopShortcut', fallback=True):
            create_desktop_shortcut()

        reload_config()
        
        stop_key_listener.clear()
        key_listener_thread = threading.Thread(target=key_listener, daemon=True)
        key_listener_thread.start()

        # Start the update checker thread
        update_thread = threading.Thread(target=check_for_updates, daemon=True)
        update_thread.start()

        if config.getboolean('THREADS', 'EnableHeightChecker', fallback=True):
            threading.Thread(target=start_height_checker, daemon=True).start()

        if config.getboolean('THREADS', 'EnableHSRDetection', fallback=True):
            try:
                threading.Thread(target=start_health_shield_rarity_detection, daemon=True).start()
            except Exception as e:
                print("An error occurred while starting HSR detection:", e)

        if config.getboolean('THREADS', 'EnableHotbarDetection', fallback=True):
            try:
                initialize_hotbar_detection()
            except Exception as e:
                print("An error occurred while initializing hotbar detection:", e)

        speaker.speak("FA11y has started! Press Enter in this window to stop FA11y.")
        print("FA11y is now running. Press Enter in this window to stop FA11y.")
        input()
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        speaker.speak(f"An error occurred: {str(e)}")
    finally:
        stop_key_listener.set()  # Ensure the key listener thread stops
        print("FA11y is closing...")
        sys.exit(0)  # Ensure the script exits

if __name__ == "__main__":
    main()
