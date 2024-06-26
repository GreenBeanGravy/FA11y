import sys

# Check Python version and create mock imp if necessary
if sys.version_info >= (3, 12):
    class MockImp:
        @staticmethod
        def is_frozen(arg=None):
            if arg == "__main__":
                return hasattr(sys, "frozen") or '__compiled__' in globals()
            return hasattr(sys, 'frozen') or hasattr(sys, 'importers') or getattr(sys, 'frozen', False)

    sys.modules['imp'] = MockImp()
    print("Created mock 'imp' module for compatibility with Python 3.12+.")

import os
import configparser
import threading
import time
import ctypes
import keyboard
import subprocess
from accessible_output2.outputs.auto import Auto
from lib.icon import start_icon_detection, create_custom_poi
from lib.hsr import start_health_shield_rarity_detection
from lib.mouse import smooth_move_mouse, left_mouse_down, left_mouse_up, right_mouse_down, right_mouse_up, mouse_scroll
from lib.guis.gui import start_gui_activation

# Constants
VK_NUMLOCK = 0x90
CONFIG_FILE = 'config.txt'
DEFAULT_CONFIG = """[SETTINGS]
MouseKeys = false
[SCRIPT KEYBINDS]
Locate Player Icon = `
Create Custom POI = \
Fire = lctrl
Target = rctrl
Turn Left = num 1
Turn Slightly Left = 4
Turn Right = num 3
Turn Slightly Right = num 6
Look Up = num 8
Look Down = num 2
Turn Around = num 0
Recenter = num 5
Scroll Up = num 7
Scroll Down = num 9
[POI]
selected_poi = closest, 0, 0"""

VK_KEY_CODES = {
    'lctrl': 0xA2, 'rctrl': 0xA3, 'lshift': 0xA0, 'rshift': 0xA1, 'lalt': 0xA4, 'ralt': 0xA5,
    'num 0': 0x60, 'num 1': 0x61, 'num 2': 0x62, 'num 3': 0x63, 'num 4': 0x64, 'num 5': 0x65,
    'num 6': 0x66, 'num 7': 0x67, 'num 8': 0x68, 'num 9': 0x69
}

speaker = Auto()
key_state = {}
action_handlers = {}

def is_numlock_on():
    return ctypes.windll.user32.GetKeyState(VK_NUMLOCK) & 1 != 0

def handle_movement(action, reset_sensitivity):
    move_distance = 100
    x_move, y_move = 0, 0

    if 'left' in action:
        x_move = -move_distance
    elif 'right' in action:
        x_move = move_distance
    elif 'up' in action:
        y_move = -move_distance
    elif 'down' in action:
        y_move = move_distance

    if 'slightly' in action:
        x_move //= 2
        y_move //= 2

    if action == 'turn around':
        x_move = 1158  # Full 360-degree turn
    elif action == 'recenter':
        smooth_move_mouse(0, 2000, 0.01)
        time.sleep(0.1)
        down_move = -580 if reset_sensitivity else -820
        smooth_move_mouse(0, down_move, 0.01)
        speaker.speak("Reset Camera")
    
    if action != 'recenter':
        smooth_move_mouse(x_move, y_move, 0.01)

def handle_scroll(action):
    scroll_amount = 16 if action == 'scroll up' else -16
    mouse_scroll(scroll_amount)

def is_key_pressed(vk_code):
    return ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000 != 0

def read_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w') as file:
            file.write(DEFAULT_CONFIG)

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return {key.lower(): value.lower() for key, value in config.items('SCRIPT KEYBINDS')}

def key_listener(key_bindings):
    print("Key Listener started")

    while True:
        numlock_on = is_numlock_on()

        for action, key in key_bindings.items():
            vk_code = VK_KEY_CODES.get(key)
            try:
                key_pressed = is_key_pressed(vk_code) if vk_code else keyboard.is_pressed(key)
            except KeyError:
                print(f"Unrecognized key: {key}. Skipping...")
                continue

            action_lower = action.lower()

            if action_lower in ['fire', 'target'] and not numlock_on:
                continue

            if key_pressed != key_state.get(key, False):
                key_state[key] = key_pressed
                if key_pressed:
                    print(f"Detected key press for action: {action}")
                    action_handler = action_handlers.get(action_lower)
                    if action_handler:
                        action_handler()
                        print(f"Action '{action}' activated.")
                else:
                    print(f"{action} button released.")
                    if action_lower in ['fire', 'target']:
                        (left_mouse_up if action_lower == 'fire' else right_mouse_up)()

        time.sleep(0.01)

def main():
    print("Starting..")
    subprocess.call(['python', 'updater.py'])

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    mouse_keys_enabled = config.getboolean('SETTINGS', 'MouseKeys', fallback=False)
    reset_sensitivity = config.getboolean('SETTINGS', 'UsingResetSensitivity', fallback=False)

    global action_handlers
    action_handlers = {
        'locate player icon': start_icon_detection,
        'create custom poi': create_custom_poi
    }

    if mouse_keys_enabled:
        print("Mouse Movement is running in the background!")
        action_handlers.update({
            'fire': left_mouse_down,
            'target': right_mouse_down,
            'turn left': lambda: handle_movement('turn left', False),
            'turn slightly left': lambda: handle_movement('turn slightly left', False),
            'turn right': lambda: handle_movement('turn right', False),
            'turn slightly right': lambda: handle_movement('turn slightly right', False),
            'look up': lambda: handle_movement('look up', False),
            'look down': lambda: handle_movement('look down', False),
            'turn around': lambda: handle_movement('turn around', False),
            'recenter': lambda: handle_movement('recenter', reset_sensitivity),
            'scroll up': lambda: handle_scroll('scroll up'),
            'scroll down': lambda: handle_scroll('scroll down')
        })

    key_bindings = read_config()

    print("Set Key Binds, Starting Key Thread")
    threading.Thread(target=key_listener, args=(key_bindings,), daemon=True).start()
    print("Key Thread Started, Starting GUI Activation..")

    threading.Thread(target=start_gui_activation, daemon=True).start()
    print("GUI Activation started in a separate thread, starting HSR detection..")

    try:
        threading.Thread(target=start_health_shield_rarity_detection, daemon=True).start()
        print("HSR detection started in a separate thread.")
    except Exception as e:
        print("An error occurred while starting HSR detection:", e)

    print("All features are now running in the background. Press Enter in this window to close FA11y!")
    speaker.speak("All features are now running in the background. Press Enter in this window to close FA11y!")
    input()

if __name__ == "__main__":
    main()