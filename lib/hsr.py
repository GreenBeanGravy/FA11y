from PIL import ImageGrab
from accessible_output2.outputs.auto import Auto
from lib.utilities import read_config, get_config_boolean
from lib.hotbar_detection import get_last_detected_rarity

speaker = Auto()

# Simplified HSR - using the new rarity detection from hotbar_detection
health_color, shield_color = (158, 255, 99), (110, 235, 255)
tolerance = 70
health_decreases, shield_decreases = [4, 3, 3], [3, 4, 3]

def pixel_within_tolerance(pixel_color, target_color, tol):
    return all(abs(pc - tc) <= tol for pc, tc in zip(pixel_color, target_color))

def check_value(pixels, start_x, y, decreases, color, tolerance, name, no_value_msg):
    x = start_x
    for i in range(100, 0, -1):
        if pixel_within_tolerance(pixels[x, y], color, tolerance):
            speaker.speak(f'{i} {name}')
            return
        x -= decreases[i % len(decreases)]
    speaker.speak(no_value_msg)

def check_health_shields():
    screenshot = ImageGrab.grab(bbox=(0, 0, 1920, 1080))
    pixels = screenshot.load()
    check_value(pixels, 423, 1024, health_decreases, health_color, tolerance, 'Health', 'Cannot find Health Value!')
    check_value(pixels, 423, 984, shield_decreases, shield_color, tolerance, 'Shields', 'No Shields')

def check_rarity():
    """Check and announce the rarity of the last detected item."""
    rarity = get_last_detected_rarity()
    speaker.speak(rarity)