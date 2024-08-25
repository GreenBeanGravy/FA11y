import os
import sys

# Set the command window title
os.system("title FA11y")
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
from lib.icon import start_icon_detection
from lib.hsr import start_health_shield_rarity_detection, check_health_shields, check_rarity
from lib.mouse import smooth_move_mouse, left_mouse_down, left_mouse_up, right_mouse_down, right_mouse_up, mouse_scroll
from lib.guis.gui import select_poi_tk
from lib.guis.gamemode_selector import select_gamemode_tk
from lib.guis.coordinate_utils import speak_current_coordinates, get_current_coordinates
from lib.guis.custom_poi_creator import create_custom_poi_gui
from lib.height_checker import start_height_checker
from lib.minimap_direction import speak_minimap_direction
from lib.guis.config_gui import create_config_gui
from lib.exit_match import exit_match
from lib.hotbar_detection import initialize_hotbar_detection, detect_hotbar_item
from lib.ppi import find_player_position, get_player_position_description

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
AnnounceWeaponAttachments = true
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
RecenterStepDelay = 2
RecenterStepSpeed = 0
RecenterVerticalMove = 1500
RecenterVerticalMoveBack = -820
SecondaryRecenterVerticalMove = 1500
SecondaryRecenterVerticalMoveBack = -580

[SCRIPT KEYBINDS]
Locate Player Icon = grave
Get Current Coordinates = c
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
Create Custom POI = backslash
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

# Combine VK_NUMPAD and SPECIAL_KEYS into a single dictionary
VK_KEYS = {
    **{f'num {i}': getattr(win32con, f'VK_NUMPAD{i}') for i in range(10)},
    'num period': win32con.VK_DECIMAL,
    'num .': win32con.VK_DECIMAL,
    'num +': win32con.VK_ADD,
    'num -': win32con.VK_SUBTRACT,
    'num *': win32con.VK_MULTIPLY,
    'num /': win32con.VK_DIVIDE,
    'lctrl': win32con.VK_LCONTROL,
    'rctrl': win32con.VK_RCONTROL,
    'lshift': win32con.VK_LSHIFT,
    'rshift': win32con.VK_RSHIFT,
    'lalt': win32con.VK_LMENU,
    'ralt': win32con.VK_RMENU,
    **{f'f{i}': getattr(win32con, f'VK_F{i}') for i in range(1, 13)},
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
    'bracketleft': 0xDB,
    'bracketright': 0xDD,
    'apostrophe': 0xDE,
    'grave': 0xC0,
    'backslash': 0xDC,
    'semicolon': 0xBA,
    'period': 0xBE,
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
    if key_lower in VK_KEYS:
        return win32api.GetAsyncKeyState(VK_KEYS[key_lower]) & 0x8000 != 0
    else:
        try:
            vk_code = ord(key.upper())
            return win32api.GetAsyncKeyState(vk_code) & 0x8000 != 0
        except:
            print(f"Unrecognized key: {key}. Skipping...")
            return False

def check_white_pixel():
    return pyautogui.pixelMatchesColor(1908, 14, (255, 255, 255))

def handle_movement(action, reset_sensitivity):
    global config
    turn_sensitivity = config.getint('SETTINGS', 'TurnSensitivity', fallback=100)
    secondary_turn_sensitivity = config.getint('SETTINGS', 'SecondaryTurnSensitivity', fallback=50)
    turn_delay = config.getfloat('SETTINGS', 'TurnDelay', fallback=0.01)
    turn_steps = config.getint('SETTINGS', 'TurnSteps', fallback=5)
    recenter_delay = config.getfloat('SETTINGS', 'RecenterDelay', fallback=0.05)
    recenter_steps = config.getint('SETTINGS', 'RecenterSteps', fallback=10)
    recenter_step_delay = config.getfloat('SETTINGS', 'RecenterStepDelay', fallback=0) / 1000
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
    default_config.optionxform = str
    default_config.read_string(DEFAULT_CONFIG)
    
    updated = False
    
    for section in default_config.sections():
        if not config.has_section(section):
            config.add_section(section)
            updated = True
        
        new_section = {}
        existing_keys = {k.lower(): (k, config[section][k]) for k in config[section]}
        
        for key, default_value in default_config.items(section):
            lower_key = key.lower()
            if lower_key in existing_keys:
                original_key, value = existing_keys[lower_key]
                if original_key != key:
                    updated = True
                new_section[key] = value
            else:
                new_section[key] = default_value
                updated = True
        
        config[section] = new_section
    
    # Always rewrite the config file to ensure order is maintained
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)
    
    if updated:
        print(f"Updated config file: {CONFIG_FILE}")
    
    return config

def read_config():
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    
    if not os.path.exists(CONFIG_FILE):
        config.read_string(DEFAULT_CONFIG)
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
        print(f"Created new config file: {CONFIG_FILE}")
    else:
        config.read(CONFIG_FILE)
        config = update_config(config)
    
    return config

def key_listener():
    global key_bindings, key_state, action_handlers, stop_key_listener, config_gui_open
    while not stop_key_listener.is_set():
        if not config_gui_open.is_set():
            numlock_on = is_numlock_on()
            mouse_keys_enabled = config.getboolean('SETTINGS', 'MouseKeys', fallback=True)

            for action, key in key_bindings.items():
                if not key:
                    continue
                
                normalized_key = normalize_key(key)
                key_pressed = is_key_pressed(normalized_key)
                action_lower = action.lower()

                if action_lower not in action_handlers:
                    continue

                if not mouse_keys_enabled and action_lower in ['fire', 'target', 'turn left', 'turn right', 'secondaryturn left', 'secondaryturn right', 'look up', 'look down', 'turn around', 'recenter', 'scroll up', 'scroll down']:
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
    
    key_bindings = {key.lower(): value.lower() for key, value in config.items('SCRIPT KEYBINDS') if value}
    
    mouse_keys_enabled = config.getboolean('SETTINGS', 'MouseKeys', fallback=True)
    reset_sensitivity = config.getboolean('SETTINGS', 'UsingResetSensitivity', fallback=False)
    
    action_handlers.clear()
    
    action_handlers['locate player icon'] = lambda: start_icon_detection(use_ppi=check_white_pixel())

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
    
    action_handlers.update({
        'speak minimap direction': speak_minimap_direction,
        'check health shields': check_health_shields,
        'check rarity': check_rarity,
        'select poi': select_poi_tk,
        'select gamemode': select_gamemode_tk,
        'open configuration': open_config_gui,
        'exit match': exit_match,
        'get current coordinates': speak_current_coordinates,
        'create custom poi': create_custom_poi_gui
    })
    
    for i in range(1, 6):
        action_handlers[f'detect hotbar {i}'] = lambda slot=i-1: detect_hotbar_item(slot)

def update_script_config(new_config):
    global config, key_listener_thread, stop_key_listener
    config = new_config
    reload_config()
    
    stop_key_listener.set()
    
    stop_key_listener.clear()
    key_listener_thread = threading.Thread(target=key_listener, daemon=True)
    key_listener_thread.start()

def open_config_gui():
    config_gui_open.set()
    create_config_gui(update_script_config)
    config_gui_open.clear()

def run_updater():
    result = subprocess.run([sys.executable, 'updater.py', '--run-by-fa11y'], capture_output=True, text=True)
    return result.returncode == 1

def get_version(repo):
    url = f"https://raw.githubusercontent.com/{repo}/main/VERSION"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException as e:
        print(f"Failed to fetch VERSION file: {e}")
        return None

def parse_version(version):
    return tuple(map(int, version.split('.')))

def check_for_updates():
    repo = "GreenBeanGravy/FA11y"
    update_notified = False
    
    while True:
        local_version = None
        if os.path.exists('VERSION'):
            with open('VERSION', 'r') as f:
                local_version = f.read().strip()
        
        repo_version = get_version(repo)
        
        if not local_version:
            print("No local version found. Update may be required.")
        elif not repo_version:
            print("Failed to fetch repository version. Skipping version check.")
        else:
            try:
                local_v = parse_version(local_version)
                repo_v = parse_version(repo_version)
                if local_v != repo_v:  # Update if local version is not equal to repo version
                    if not update_notified:
                        update_sound.play()
                        speaker.speak("An update is available for FA11y! Restart FA11y to update!")
                        print("An update is available for FA11y! Restart FA11y to update!")
                        update_notified = True
                else:
                    update_notified = False  # Reset the flag if versions match
            except ValueError:
                print("Invalid version format. Treating as update required.")
        
        time.sleep(30)

def get_legendary_username():
    try:
        # Change the working directory to the script's directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)
        
        result = subprocess.run(["legendary", "status"], capture_output=True, text=True)
        if result.returncode == 0:
            output = result.stdout
            for line in output.splitlines():
                if "Epic account:" in line:
                    username = line.split("Epic account:")[1].strip()
                    if username and username != "<not logged in>":
                        return username
        return None
    except Exception as e:
        print(f"Failed to run 'legendary status': {str(e)}")
        return None

def main():
    global config, action_handlers, key_bindings, key_listener_thread, stop_key_listener
    try:
        print("Starting FA11y...")

        # Get the players username from legendary
        LOCAL_USERNAME = get_legendary_username()
        if LOCAL_USERNAME:
            print(f"Welcome back {LOCAL_USERNAME}!")
            speaker.speak(f"Welcome back {LOCAL_USERNAME}!")
        else:
            print("You are not logged into Legendary.")
            speaker.speak("You are not logged into Legendary.")
        
        config = read_config()

        if config.getboolean('SETTINGS', 'EnableAutoUpdates', fallback=True):
            if run_updater():
                sys.exit(0)

        if config.getboolean('SETTINGS', 'CreateDesktopShortcut', fallback=True):
            create_desktop_shortcut()

        reload_config()
        
        stop_key_listener.clear()
        key_listener_thread = threading.Thread(target=key_listener, daemon=True)
        key_listener_thread.start()

        update_thread = threading.Thread(target=check_for_updates, daemon=True)
        update_thread.start()

        threading.Thread(target=start_height_checker, daemon=True).start()

        threading.Thread(target=start_health_shield_rarity_detection, daemon=True).start()

        initialize_hotbar_detection()

        speaker.speak("FA11y has started! Press Enter in this window to stop FA11y.")
        print("FA11y is now running. Press Enter in this window to stop FA11y.")
        input()
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        speaker.speak(f"An error occurred: {str(e)}")
    finally:
        stop_key_listener.set()
        print("FA11y is closing...")
        sys.exit(0)

if __name__ == "__main__":
    main()
