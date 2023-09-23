import threading
from lib.icon import start_icon_detection
from lib.hsr import start_health_shield_rarity_detection
from lib.mouse import mouse_movement

def main():
    # Start the icon detection function in a separate thread
    icon_thread = threading.Thread(target=start_icon_detection)
    icon_thread.daemon = True
    icon_thread.start()

    # Start the health, shield, and rarity detection function in a separate thread
    hsr_thread = threading.Thread(target=start_health_shield_rarity_detection)
    hsr_thread.daemon = True
    hsr_thread.start()

    # Start the mouse movement in a seperate thread
    mouse_thread = threading.Thread(target=mouse_movement)
    mouse_thread.daemon = True
    mouse_thread.start()

    print("Mouse Movement, Player Icon, storm, and health/shield/rarity detection are now running in the background. Press any key followed by Enter in this window to exit.")

    input()  # Wait for user input to exit the program

if __name__ == "__main__":
    main()
