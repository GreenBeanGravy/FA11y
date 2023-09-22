import ctypes
import pyautogui
from accessible_output2.outputs.auto import Auto
import time

speaker = Auto()

VK_H = 0x48
VK_LBRACKET = 0xDB

# Define the RGB colors to look for
health_color = (158, 255, 99)
shield_color = (110, 235, 255)
rarity_colors = {
    'Common': (116, 122, 128),
    'Uncommon': (0, 128, 5),
    'Rare': (0, 88, 191),
    'Epic': (118, 45, 211),
    'Legendary': (191, 79, 0),
    'Mythic': (191, 147, 35),
    'Exotic': (118, 191, 255),
}

# Define the tolerance for the color match
tolerance = 70
rarity_tolerance = 30  # Separate tolerance for the rarity check

# Variables to track the state of the keys
h_key_down = False
lbracket_key_down = False
f_key_down = False

# Define the pattern of decreases
health_decreases = [4, 3, 3]
shield_decreases = [3, 4, 3]

def check_inventory_open():
    # Check if the inventory is open by verifying a specific pixel's color.
    x, y = 1616, 1034
    pixel_color = pyautogui.pixel(x, y)
    white_color = (255, 255, 255)
    if not all(abs(pc - tc) <= 10 for pc, tc in zip(pixel_color, white_color)):
        speaker.speak("You do not have your inventory open. Please make sure your inventory is open to check rarity.")
        return False
    return True

def start_health_shield_rarity_detection():
    while True:
        # Check if the "H" key is down
        h_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_H))
    
        # If the "H" key was just pressed
        if h_key_current_state and not h_key_down:
            # Check health value
            x = 453
            found = False
            for i in range(100, 0, -1):  # Loop from 100 to 1
                y = 982
                pixel_color = pyautogui.pixel(x, y)
                
                # Check if the pixel color is within the tolerance of the target color
                if all(abs(pc - tc) <= tolerance for pc, tc in zip(pixel_color, health_color)):
                    speaker.speak(f'{i} Health,')  # Speak the health value
                    found = True
                    break
                
                # Decrease x according to the pattern
                x -= health_decreases[i % len(health_decreases)]
            
            if not found:
                speaker.speak('Cannot find Health Value! Make sure your game is running in 1920x1080 or increase your Tolerance value.')
    
            # Check shield value
            x = 453
            found = False
            for i in range(100, 0, -1):  # Loop from 100 to 1
                y = 950
                pixel_color = pyautogui.pixel(x, y)
                
                # Check if the pixel color is within the tolerance of the target color
                if all(abs(pc - tc) <= tolerance for pc, tc in zip(pixel_color, shield_color)):
                    speaker.speak(f'{i} Shields')  # Speak the shield value
                    found = True
                    break
                
                # Decrease x according to the pattern
                x -= shield_decreases[i % len(shield_decreases)]
            
            if not found:
                speaker.speak('No Shields')
    
        h_key_down = h_key_current_state
    
        # Check if the "[" key is down
        lbracket_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_LBRACKET))
    
        # If the "[" key was just pressed
        if lbracket_key_current_state and not lbracket_key_down:
            # First, check if the inventory is open
            if not check_inventory_open():
                lbracket_key_down = lbracket_key_current_state
                continue  # Skip the rest of the loop iteration
            # Check rarity
            x, y = 1214, 987
            pixel_color = pyautogui.pixel(x, y)
            found = False
            for rarity, color in rarity_colors.items():
                # Check if the pixel color is within the rarity tolerance of the target color
                if all(abs(pc - tc) <= rarity_tolerance for pc, tc in zip(pixel_color, color)):
                    speaker.speak(rarity)  # Speak the rarity
                    found = True
                    break
        
            if not found:
                speaker.speak('No Rarity Found. Please select a weapon or adjust your Tolerance value.')
        
        lbracket_key_down = lbracket_key_current_state
