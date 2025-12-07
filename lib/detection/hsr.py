from PIL import ImageGrab
from accessible_output2.outputs.auto import Auto
from lib.utilities.utilities import read_config, get_config_boolean
from lib.managers.hotbar_manager import get_last_detected_rarity
import requests  # Add this import

speaker = Auto()

# API Configuration
API_BASE_URL = "http://localhost:6767/api"
API_TIMEOUT = 0.5  # 500ms timeout - fast fail if FA11y-OW isn't running

# Visual detection fallback settings
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

def get_health_shield_from_api():
    """
    Try to get health and shield values from the FA11y-OW HTTP API.
    Returns (health, shield) tuple if successful, or (None, None) if API is unavailable.
    """
    try:
        # Try to get health
        health_response = requests.get(f"{API_BASE_URL}/health", timeout=API_TIMEOUT)
        health_data = health_response.json()
        health = health_data.get('health')
        
        # Try to get shield
        shield_response = requests.get(f"{API_BASE_URL}/shield", timeout=API_TIMEOUT)
        shield_data = shield_response.json()
        shield = shield_data.get('shield')
        
        # Only return if both are valid numbers
        if health is not None and shield is not None:
            return (health, shield)
        return (None, None)
        
    except (requests.RequestException, requests.Timeout, ValueError, KeyError) as e:
        # API not available, connection failed, or invalid response
        # Silently fall back to visual detection
        return (None, None)

def check_health_shields():
    """Check and announce health and shield values using API first, visual fallback."""
    try:
        # Try API first (fast and accurate when FA11y-OW is running)
        health, shield = get_health_shield_from_api()
        
        if health is not None and shield is not None:
            # Successfully got values from API
            speaker.speak(f'{health} Health')
            if shield > 0:
                speaker.speak(f'{shield} Shields')
            else:
                speaker.speak('No Shields')
            return
        
        # API failed or unavailable, fall back to visual detection
        screenshot = ImageGrab.grab(bbox=(0, 0, 1920, 1080))
        pixels = screenshot.load()
        check_value_visual(pixels, 408, 1000, health_decreases, health_color, tolerance, 'Health', 'Cannot find Health Value!')
        check_value_visual(pixels, 408, 970, shield_decreases, shield_color, tolerance, 'Shields', 'No Shields')
        
    except Exception as e:
        print(f"Error in check_health_shields: {e}")
        speaker.speak("Error checking health and shields.")

def check_rarity():
    """Check and announce the rarity of the last detected item."""
    rarity_str = get_last_detected_rarity()
    speaker.speak(rarity_str)
