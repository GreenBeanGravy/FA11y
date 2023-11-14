import threading
import os
from lib.icon import start_icon_detection
from lib.hsr import start_health_shield_rarity_detection
from lib.mouse import mouse_movement

def read_config():
    config_file = 'config.txt'
    default_config = 'MouseKeys = false\n'

    # Check if config file exists, create with default settings if it doesn't
    if not os.path.exists(config_file):
        with open(config_file, 'w') as file:
            file.write(default_config)

    with open(config_file, 'r') as file:
        for line in file:
            if 'MouseKeys' in line:
                return line.split('=')[1].strip().lower() == 'true'
    return False  # Default to False if not found or unknown value

def main():
    active_threads = []

    # Start the icon detection function in a separate thread
    icon_thread = threading.Thread(target=start_icon_detection)
    icon_thread.daemon = True
    icon_thread.start()
    active_threads.append("Player Icon")

    # Start the health, shield, and rarity detection function in a separate thread
    hsr_thread = threading.Thread(target=start_health_shield_rarity_detection)
    hsr_thread.daemon = True
    hsr_thread.start()
    active_threads.append("Health/Shield/Rarity detection")

    # Check config and start the mouse movement if enabled
    if read_config():
        mouse_thread = threading.Thread(target=mouse_movement)
        mouse_thread.daemon = True
        mouse_thread.start()
        active_threads.append("Mouse Movement")

    # Formatting the active threads list with 'and' before the last item
    if len(active_threads) > 1:
        active_thread_list = ', '.join(active_threads[:-1]) + ', and ' + active_threads[-1]
    else:
        active_thread_list = active_threads[0]

    print(f"{active_thread_list} are now running in the background. Press Enter in this window to exit.")

    input()  # Wait for user input to exit the program

if __name__ == "__main__":
    main()
