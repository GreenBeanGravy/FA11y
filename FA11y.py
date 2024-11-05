import os
import sys
import configparser
import threading
import time
import pyautogui
import subprocess
import win32com.client

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import pygame
import requests
import win32api
import win32con
import winshell

# Set the command window title
os.system("title FA11y")

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
from lib.hsr import (
    check_health_shields,
    check_rarity,
)
from lib.mouse import (
    smooth_move_mouse,
    left_mouse_down,
    left_mouse_up,
    right_mouse_down,
    right_mouse_up,
    mouse_scroll,
)
# Updated imports for the new GUI implementations
from lib.guis.poi_selector_gui import POIData, select_poi_tk
from lib.guis.gamemode_selector_gui import select_gamemode_tk
from lib.guis.custom_poi_gui import create_custom_poi_gui
from lib.guis.config_gui import create_config_gui
from lib.height_checker import start_height_checker
from lib.minimap_direction import speak_minimap_direction, find_minimap_icon_direction
from lib.exit_match import exit_match
from lib.hotbar_detection import (
    initialize_hotbar_detection,
    detect_hotbar_item,
    announce_ammo_manually,
)
from lib.utilities import (
    get_config_int,
    get_config_float,
    get_config_value,
    get_config_boolean,
    read_config,
)
from lib.pathfinder import toggle_pathfinding
from lib.input_handler import is_key_pressed, get_pressed_key, is_numlock_on, VK_KEYS

# Initialize pygame mixer
pygame.mixer.init()

# Load the update sound
update_sound = pygame.mixer.Sound("sounds/update.ogg")

# GitHub repository details
REPO_OWNER = "GreenBeanGravy"
REPO_NAME = "FA11y"
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/main"

speaker = Auto()
key_state = {}
action_handlers = {}
config = None
key_bindings = {}
key_listener_thread = None
stop_key_listener = threading.Event()
config_gui_open = threading.Event()
keybinds_enabled = True
poi_data_instance = None

def handle_movement(action: str, reset_sensitivity: bool) -> None:
    """Handle all movement-related actions."""
    global config
    turn_sensitivity = get_config_int(config, 'SETTINGS', 'TurnSensitivity', 100)
    secondary_turn_sensitivity = get_config_int(config, 'SETTINGS', 'SecondaryTurnSensitivity', 50)
    up_down_sensitivity = turn_sensitivity // 2
    turn_delay = get_config_float(config, 'SETTINGS', 'TurnDelay', 0.01)
    turn_steps = get_config_int(config, 'SETTINGS', 'TurnSteps', 5)
    recenter_delay = get_config_float(config, 'SETTINGS', 'RecenterDelay', 0.05)
    recenter_steps = get_config_int(config, 'SETTINGS', 'RecenterSteps', 10)
    recenter_step_delay = get_config_float(config, 'SETTINGS', 'RecenterStepDelay', 0) / 1000
    recenter_step_speed = get_config_int(config, 'SETTINGS', 'RecenterStepSpeed', 0)
    x_move, y_move = 0, 0

    if action in ['turn left', 'turn right', 'secondary turn left', 'secondary turn right', 'look up', 'look down']:
        if 'secondary' in action:
            sensitivity = secondary_turn_sensitivity
        elif action in ['look up', 'look down']:
            sensitivity = up_down_sensitivity
        else:
            sensitivity = turn_sensitivity

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
        x_move = get_config_int(config, 'SETTINGS', 'TurnAroundSensitivity', 1158)
        smooth_move_mouse(x_move, 0, turn_delay, turn_steps)
        return  # Add return here to prevent the second movement

    elif action == 'recenter':
        if reset_sensitivity:
            recenter_move = get_config_int(config, 'SETTINGS', 'ResetRecenterLookDown', 1500)
            down_move = get_config_int(config, 'SETTINGS', 'ResetRecenterLookUp', -580)
        else:
            recenter_move = get_config_int(config, 'SETTINGS', 'RecenterLookDown', 1500)
            down_move = get_config_int(config, 'SETTINGS', 'RecenterLookUp', -820)

        smooth_move_mouse(0, recenter_move, recenter_step_delay, recenter_steps, recenter_step_speed, down_move, recenter_delay)
        speaker.speak("Reset Camera")
        return  # Add return here to be explicit

    # This line should now only execute if none of the above conditions are met
    smooth_move_mouse(x_move, y_move, recenter_delay)

def handle_scroll(action: str) -> None:
    """Handle scroll wheel actions."""
    global config
    scroll_sensitivity = get_config_int(config, 'SETTINGS', 'ScrollSensitivity', 120)
    if action == 'scroll down':
        scroll_sensitivity = -scroll_sensitivity
    mouse_scroll(scroll_sensitivity)

def reload_config() -> None:
    """Reload configuration and update action handlers."""
    global config, action_handlers, key_bindings, poi_data_instance
    config = read_config()

    # Initialize POI data if not already done
    if poi_data_instance is None:
        print("Initializing POI data...")
        poi_data_instance = POIData()

    key_bindings = {key.lower(): get_config_value(config, 'SCRIPT KEYBINDS', key)[0].lower()
                    for key in config['SCRIPT KEYBINDS'] if get_config_value(config, 'SCRIPT KEYBINDS', key)[0]}

    mouse_keys_enabled = get_config_boolean(config, 'SETTINGS', 'MouseKeys', True)
    reset_sensitivity = get_config_boolean(config, 'SETTINGS', 'ResetSensitivity', False)

    action_handlers.clear()

    action_handlers['start navigation'] = lambda: start_icon_detection(use_ppi=check_white_pixel())

    if mouse_keys_enabled:
        action_handlers.update({
            'fire': left_mouse_down,
            'target': right_mouse_down,
            'turn left': lambda: handle_movement('turn left', reset_sensitivity),
            'turn right': lambda: handle_movement('turn right', reset_sensitivity),
            'secondary turn left': lambda: handle_movement('secondary turn left', reset_sensitivity),
            'secondary turn right': lambda: handle_movement('secondary turn right', reset_sensitivity),
            'look up': lambda: handle_movement('look up', reset_sensitivity),
            'look down': lambda: handle_movement('look down', reset_sensitivity),
            'turn around': lambda: handle_movement('turn around', reset_sensitivity),
            'recenter': lambda: handle_movement('recenter', reset_sensitivity),
            'scroll up': lambda: handle_scroll('scroll up'),
            'scroll down': lambda: handle_scroll('scroll down')
        })

    action_handlers.update({
        'announce direction faced': speak_minimap_direction,
        'check health shields': check_health_shields,
        'check rarity': check_rarity,
        'open p o i selector': lambda: select_poi_tk(poi_data_instance),
        'open gamemode selector': select_gamemode_tk,
        'open configuration menu': open_config_gui,
        'exit match': exit_match,
        'create custom p o i': create_custom_poi_gui,
        'announce ammo': announce_ammo_manually,
        'toggle pathfinding': toggle_pathfinding,
        'toggle keybinds': toggle_keybinds
    })

    for i in range(1, 6):
        action_handlers[f'detect hotbar {i}'] = lambda slot=i-1: detect_hotbar_item(slot)

def toggle_keybinds() -> None:
    """Toggle keybinds on/off."""
    global keybinds_enabled
    keybinds_enabled = not keybinds_enabled
    state = 'enabled' if keybinds_enabled else 'disabled'
    speaker.speak(f"FA11y {state}")
    print(f"FA11y has been {state}.")

def key_listener() -> None:
    """Listen for and handle key presses."""
    global key_bindings, key_state, action_handlers, stop_key_listener, config_gui_open, keybinds_enabled
    while not stop_key_listener.is_set():
        if not config_gui_open.is_set():
            numlock_on = is_numlock_on()
            mouse_keys_enabled = get_config_boolean(config, 'SETTINGS', 'MouseKeys', True)

            for action, key in key_bindings.items():
                if not key:
                    continue

                key_pressed = is_key_pressed(key)
                action_lower = action.lower()

                if action_lower not in action_handlers:
                    continue

                if not keybinds_enabled and action_lower != 'toggle keybinds':
                    continue

                if not mouse_keys_enabled and action_lower in [
                    'fire', 'target', 'turn left', 'turn right',
                    'secondary turn left', 'secondary turn right',
                    'look up', 'look down', 'turn around', 'recenter',
                    'scroll up', 'scroll down'
                ]:
                    continue

                if action_lower in ['fire', 'target'] and not numlock_on:
                    continue

                if key_pressed != key_state.get(key, False):
                    key_state[key] = key_pressed
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

def create_desktop_shortcut() -> None:
    """Create a desktop shortcut for FA11y."""
    desktop = winshell.desktop()
    path = os.path.join(desktop, "FA11y.lnk")
    target = os.path.abspath(sys.argv[0])
    wDir = os.path.dirname(target)

    shell = win32com.client.Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(path)
    shortcut.Targetpath = target
    shortcut.WorkingDirectory = wDir
    shortcut.save()

def update_script_config(new_config: configparser.ConfigParser) -> None:
    """Update script configuration and restart key listener."""
    global config, key_listener_thread, stop_key_listener
    config = new_config
    reload_config()

    stop_key_listener.set()
    stop_key_listener.clear()
    key_listener_thread = threading.Thread(target=key_listener, daemon=True)
    key_listener_thread.start()

def open_config_gui() -> None:
    """Open the configuration GUI."""
    config_gui_open.set()
    create_config_gui(update_script_config)
    config_gui_open.clear()

def run_updater() -> bool:
    """Run the updater script."""
    result = subprocess.run([sys.executable, 'updater.py', '--run-by-fa11y'], capture_output=True, text=True)
    return result.returncode == 1

def get_version(repo: str) -> str:
    """Get version from GitHub repository."""
    url = f"https://raw.githubusercontent.com/{repo}/main/VERSION"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException as e:
        print(f"Failed to fetch VERSION file: {e}")
        return None

def parse_version(version: str) -> tuple:
    """Parse version string into tuple."""
    return tuple(map(int, version.split('.')))

def check_for_updates() -> None:
    """Periodically check for updates."""
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
                if local_v != repo_v:
                    if not update_notified:
                        update_sound.play()
                        speaker.speak("An update is available for FA11y! Restart FA11y to update!")
                        print("An update is available for FA11y! Restart FA11y to update!")
                        update_notified = True
                else:
                    update_notified = False
            except ValueError:
                print("Invalid version format. Treating as update required.")

        time.sleep(30)

def get_legendary_username() -> str:
    """Get username from Legendary launcher."""
    try:
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

def check_white_pixel():
    """Check if the pixel at a specific location is white."""
    return pyautogui.pixelMatchesColor(1879, 62, (255, 255, 255))

def main() -> None:
    """Main entry point for FA11y."""
    global config, action_handlers, key_bindings, key_listener_thread, stop_key_listener
    try:
        print("Starting FA11y...")

        # Check and welcome user
        local_username = get_legendary_username()
        if local_username:
            print(f"Welcome back {local_username}!")
            speaker.speak(f"Welcome back {local_username}!")
        else:
            print("You are not logged into Legendary.")
            speaker.speak("You are not logged into Legendary.")

        # Initialize configuration
        config = read_config()

        # Check for updates if enabled
        if get_config_boolean(config, 'SETTINGS', 'AutoUpdates', True):
            if run_updater():
                sys.exit(0)

        # Create desktop shortcut if enabled
        if get_config_boolean(config, 'SETTINGS', 'CreateDesktopShortcut', True):
            create_desktop_shortcut()

        # Initialize core systems
        reload_config()

        # Start key listener thread
        stop_key_listener.clear()
        key_listener_thread = threading.Thread(target=key_listener, daemon=True)
        key_listener_thread.start()

        # Start update checker thread
        update_thread = threading.Thread(target=check_for_updates, daemon=True)
        update_thread.start()

        # Start auxiliary systems
        threading.Thread(target=start_height_checker, daemon=True).start()

        # Initialize hotbar detection
        initialize_hotbar_detection()

        # Notify user that FA11y is running
        speaker.speak("FA11y is now running in the background. Press Enter in this window to stop FA11y.")
        print("FA11y is now running in the background. Press Enter in this window to stop FA11y.")
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
