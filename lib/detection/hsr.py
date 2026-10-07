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

_READ_ERROR = "error"


def read_value_visual(pixels, start_x, y, decreases, color, tolerance):
    """The value 1 to 100 shown by a health or shield bar, None when the bar is empty, or _READ_ERROR."""
    x = start_x
    for i in range(100, 0, -1):
        try:
            if pixel_within_tolerance(pixels[x, y], color, tolerance):
                return i
        except IndexError:
            return _READ_ERROR

        if decreases:
            x -= decreases[i % len(decreases)]
        else:
            x -= 1
    return None


def health_shield_text(health, shield, short):
    """What to say for the two readings. Short speech says only the numbers: "100, 50"."""
    if health == _READ_ERROR:
        return "Error reading Health bar."
    if health is None:
        return "Cannot find Health Value!"
    if shield == _READ_ERROR:
        return f"{health}, error reading shield" if short else f"{health} Health. Error reading Shield bar."
    if short:
        return f"{health}, {shield or 0}"
    return f"{health} Health, {shield} Shield" if shield is not None else f"{health} Health, No Shield"


def check_health_shields():
    """Check and announce health and shield values."""
    try:
        from lib.app.speech import is_simple
        # Get map-specific coordinates and settings
        config = read_config()
        current_map = config.get('POI', 'current_map', fallback='main')
        coords = get_health_shield_coords(current_map)

        screenshot = ImageGrab.grab(bbox=(0, 0, 1920, 1080))
        pixels = screenshot.load()

        # Use map-specific coordinates, colors, tolerance, and decrease patterns
        health = read_value_visual(pixels, coords.health_x, coords.health_y, coords.health_decreases,
                                   coords.health_color, coords.tolerance)
        shield = read_value_visual(pixels, coords.shield_x, coords.shield_y, coords.shield_decreases,
                                   coords.shield_color, coords.tolerance)
        speaker.speak(health_shield_text(health, shield, is_simple()))

    except Exception as e:
        print(f"Error in check_health_shields: {e}")
        speaker.speak("Error checking health and shields.")
