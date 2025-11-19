<<<<<<< HEAD
from PIL import ImageGrab
from accessible_output2.outputs.auto import Auto
from lib.utilities.utilities import read_config, get_config_boolean # Not strictly needed now but good practice
from lib.managers.hotbar_manager import get_last_detected_rarity

speaker = Auto()

# Simplified HSR - using the new rarity detection from hotbar_detection
health_color, shield_color = (158, 255, 99), (110, 235, 255)
tolerance = 70
health_decreases, shield_decreases = [4, 3, 3], [3, 4, 3] # These seem specific to a pixel-bar reading logic

def pixel_within_tolerance(pixel_color, target_color, tol):
    return all(abs(pc - tc) <= tol for pc, tc in zip(pixel_color, target_color))

def check_value(pixels, start_x, y, decreases, color, tolerance, name, no_value_msg):
    # This function reads health/shield bars pixel by pixel.
    # It's not directly related to rarity, so it can remain as is.
    x = start_x
    for i in range(100, 0, -1): # Assumes 100 points max
        try:
            if pixel_within_tolerance(pixels[x, y], color, tolerance):
                speaker.speak(f'{i} {name}')
                return
        except IndexError: # If x goes out of bounds
            speaker.speak(f"Error reading {name} bar.")
            return
        
        # This decreasing logic seems specific to how the bar is drawn
        # Ensure decreases has enough elements or use modulo correctly
        if decreases: # Check if decreases is not empty
            x -= decreases[i % len(decreases)] 
        else: # Fallback if decreases is empty, though it shouldn't be
            x -= 1 

    speaker.speak(no_value_msg)

def check_health_shields():
    try:
        screenshot = ImageGrab.grab(bbox=(0, 0, 1920, 1080))
        pixels = screenshot.load()
        check_value(pixels, 423, 1024, health_decreases, health_color, tolerance, 'Health', 'Cannot find Health Value!')
        check_value(pixels, 423, 984, shield_decreases, shield_color, tolerance, 'Shields', 'No Shields')
    except Exception as e:
        print(f"Error in check_health_shields: {e}")
        speaker.speak("Error checking health and shields.")


def check_rarity():
    """Check and announce the rarity of the last detected item."""
    rarity_str = get_last_detected_rarity() # This will return "Unknown" if None or not found
=======
from PIL import ImageGrab
from accessible_output2.outputs.auto import Auto
from lib.utilities.utilities import read_config, get_config_boolean # Not strictly needed now but good practice
from lib.managers.hotbar_manager import get_last_detected_rarity

speaker = Auto()

# Simplified HSR - using the new rarity detection from hotbar_detection
health_color, shield_color = (158, 255, 99), (110, 235, 255)
tolerance = 70
health_decreases, shield_decreases = [4, 3, 3], [3, 4, 3] # These seem specific to a pixel-bar reading logic

def pixel_within_tolerance(pixel_color, target_color, tol):
    return all(abs(pc - tc) <= tol for pc, tc in zip(pixel_color, target_color))

def check_value(pixels, start_x, y, decreases, color, tolerance, name, no_value_msg):
    # This function reads health/shield bars pixel by pixel.
    # It's not directly related to rarity, so it can remain as is.
    x = start_x
    for i in range(100, 0, -1): # Assumes 100 points max
        try:
            if pixel_within_tolerance(pixels[x, y], color, tolerance):
                speaker.speak(f'{i} {name}')
                return
        except IndexError: # If x goes out of bounds
            speaker.speak(f"Error reading {name} bar.")
            return
        
        # This decreasing logic seems specific to how the bar is drawn
        # Ensure decreases has enough elements or use modulo correctly
        if decreases: # Check if decreases is not empty
            x -= decreases[i % len(decreases)] 
        else: # Fallback if decreases is empty, though it shouldn't be
            x -= 1 

    speaker.speak(no_value_msg)

def check_health_shields():
    try:
        screenshot = ImageGrab.grab(bbox=(0, 0, 1920, 1080))
        pixels = screenshot.load()
        check_value(pixels, 423, 1024, health_decreases, health_color, tolerance, 'Health', 'Cannot find Health Value!')
        check_value(pixels, 423, 984, shield_decreases, shield_color, tolerance, 'Shields', 'No Shields')
    except Exception as e:
        print(f"Error in check_health_shields: {e}")
        speaker.speak("Error checking health and shields.")


def check_rarity():
    """Check and announce the rarity of the last detected item."""
    rarity_str = get_last_detected_rarity() # This will return "Unknown" if None or not found
>>>>>>> 7c21c23a460e8f25bc96524c200b22c8b26c9b15
    speaker.speak(rarity_str)