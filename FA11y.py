import os, configparser, threading, time, ctypes, keyboard
from accessible_output2.outputs.auto import Auto
from lib.icon import start_icon_detection, create_custom_poi
from lib.hsr import start_health_shield_rarity_detection
from lib.mouse import smooth_move_mouse, left_mouse_down, left_mouse_up, right_mouse_down, right_mouse_up, mouse_scroll
from lib.guis.gui import start_gui_activation

speaker = Auto()

# Constants
VK_NUMLOCK = 0x90
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
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

# Virtual-Key Codes for the modifier keys, numpad keys and regular number keys
VK_KEY_CODES = {
    'lctrl': 0xA2,
    'rctrl': 0xA3,
    'lshift': 0xA0,
    'rshift': 0xA1,
    'lalt': 0xA4,
    'ralt': 0xA5,
    'num 0': 0x60,
    'num 1': 0x61,
    'num 2': 0x62,
    'num 3': 0x63,
    'num 4': 0x64,
    'num 5': 0x65,
    'num 6': 0x66,
    'num 7': 0x67,
    'num 8': 0x68,
    'num 9': 0x69
}

# Global state
key_state = {}

# Function to handle movement-related actions
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

    # Special handling for "Turn Around" and "Recenter"
    if action == 'turn around':
        x_move = 1158  # Full 360-degree turn
    elif action == 'recenter':
        smooth_move_mouse(0, 2000, 0.01)
        time.sleep(0.1)
        down_move = -580 if reset_sensitivity else -820
        smooth_move_mouse(0, down_move, 0.01)
        speaker.speak("Reset Camera")

    if action not in ['recenter']:  # Exclude 'recenter' from smooth movement
        smooth_move_mouse(x_move, y_move, 0.01)

# Function to handle scroll actions
def handle_scroll(action):
    scroll_amount = 3
    if action == 'scroll up':
        mouse_scroll(scroll_amount)
    elif action == 'scroll down':
        mouse_scroll(-scroll_amount)

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
    global key_state

    print("Key Listener started")

    while True:
        for action, key in key_bindings.items():
            vk_code = VK_KEY_CODES.get(key, None)
            try:
                key_pressed = is_key_pressed(vk_code) if vk_code else keyboard.is_pressed(key)
            except KeyError:
                print(f"Unrecognized key: {key}. Skipping...")
                continue

            action_lower = action.lower()

            if key_pressed and not key_state.get(key, False):
                key_state[key] = True
                print(f"Detected key press for action: {action}")

                action_handler = action_handlers.get(action_lower)
                if action_handler:
                    action_handler()
                    print(f"Action '{action}' activated.")

            elif not key_pressed and key_state.get(key, False):
                key_state[key] = False
                print(f"{action} button released.")
                if action_lower in ['fire', 'target']:
                    handle_key_release(action_lower)

        time.sleep(0.01)

def handle_key_release(action):
    if action == 'fire':
        left_mouse_up()
    elif action == 'target':
        right_mouse_up()

def main():
    print("Starting..")
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    mouse_keys_enabled = config.getboolean('SETTINGS', 'MouseKeys', fallback=False)
    reset_sensitivity = config.getboolean('SETTINGS', 'UsingResetSensitivity', fallback=False)

    global action_handlers
    action_handlers = {
        'locate player icon': start_icon_detection,
        'create custom poi': create_custom_poi
    }

    # Add mouse-related actions if MouseKeys is enabled
    if mouse_keys_enabled:
        print("Mouse Movement is running in the background!")
        mouse_related_actions = {
            'fire': left_mouse_down,
            'target': right_mouse_down,
            'turn left': lambda: handle_movement('turn left'),
            'turn slightly left': lambda: handle_movement('turn slightly left'),
            'turn right': lambda: handle_movement('turn right'),
            'turn slightly right': lambda: handle_movement('turn slightly right'),
            'look up': lambda: handle_movement('look up'),
            'look down': lambda: handle_movement('look down'),
            'turn around': lambda: handle_movement('turn around'),
            'recenter': lambda: handle_movement('recenter', reset_sensitivity),
            'scroll up': lambda: handle_scroll('scroll up'),
            'scroll down': lambda: handle_scroll('scroll down')
        }
        action_handlers.update(mouse_related_actions)

    key_bindings = read_config()

    print("Set Key Binds, Starting Key Thread")
    key_thread = threading.Thread(target=key_listener, args=(key_bindings,))
    key_thread.daemon = True
    key_thread.start()
    print("Key Thread Started, Starting GUI Activation..")

    gui_thread = threading.Thread(target=start_gui_activation)
    gui_thread.daemon = True
    gui_thread.start()
    print("GUI Activation started in a separate thread, starting HSR detection..")

    try:
        hsr_thread = threading.Thread(target=start_health_shield_rarity_detection)
        hsr_thread.daemon = True
        hsr_thread.start()
        print("HSR detection started in a separate thread.")
    except Exception as e:
        print("An error occurred while starting HSR detection:", e)

    print("All features are now running in the background. Press Enter in this window to exit.")
    input()

if __name__ == "__main__":
    main()
