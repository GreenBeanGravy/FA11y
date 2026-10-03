"""
Health / Shield (HSR) detection.

Walks the health/shield bars pixel-by-pixel against the calibrated
``health_decreases`` step pattern. The F9 settings tune this.

If you need to re-calibrate: ``python dev_tools/health_calibrator.py``.
"""
from PIL import ImageGrab
from accessible_output2.outputs.auto import Auto
from lib.utilities.utilities import read_config, get_config_boolean
from lib.detection.coordinate_config import get_health_shield_coords

speaker = Auto()

# Visual detection settings
health_color, shield_color = (247, 255, 26), (213, 255, 232)
tolerance = 30

# Full calibrated decrease pattern (100 HP -> 1 HP)
health_decreases = [3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 3, 4, 4, 3, 4, 3, 3, 3, 4, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 3]
shield_decreases = health_decreases

def pixel_within_tolerance(pixel_color, target_color, tol):
    return all(abs(pc - tc) <= tol for pc, tc in zip(pixel_color, target_color))

def check_value_visual(pixels, start_x, y, decreases, color, tolerance, name, no_value_msg):
    """Visual fallback method for checking health/shield bars."""
    x = start_x
    for i in range(100, 0, -1):
        try:
            if pixel_within_tolerance(pixels[x, y], color, tolerance):
                speaker.speak(f'{i} {name}')
                return
        except IndexError:
            speaker.speak(f"Error reading {name} bar.")
            return
        
        if decreases:
            x -= decreases[i % len(decreases)]
        else:
            x -= 1

    speaker.speak(no_value_msg)

def check_health_shields():
    """Check and announce health and shield values."""
    try:
        # Get map-specific coordinates and settings
        config = read_config()
        current_map = config.get('POI', 'current_map', fallback='main')
        coords = get_health_shield_coords(current_map)
        
        screenshot = ImageGrab.grab(bbox=(0, 0, 1920, 1080))
        pixels = screenshot.load()
        
        # Use map-specific coordinates, colors, tolerance, and decrease patterns
        check_value_visual(
            pixels, coords.health_x, coords.health_y, coords.health_decreases,
            coords.health_color, coords.tolerance, 'Health', 'Cannot find Health Value!'
        )
        check_value_visual(
            pixels, coords.shield_x, coords.shield_y, coords.shield_decreases,
            coords.shield_color, coords.tolerance, 'Shield', 'No Shield'
        )
        
    except Exception as e:
        print(f"Error in check_health_shields: {e}")
        speaker.speak("Error checking health and shields.")
