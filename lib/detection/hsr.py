"""
Health / Shield / Rarity (HSR) detection.

Two-path strategy:

1. **Fast path — FA11y-OW companion service**
   If a loopback HTTP service is running at ``http://127.0.0.1:6767/api``
   (the "FA11y-OW" helper, a separate optional project) it gets queried
   first. The service reads Fortnite memory/log signals directly and
   returns exact values, bypassing image analysis.

   The 10 ms timeout below is intentional: if the service isn't up, we
   fall through instantly rather than block the UI. No state is kept
   between calls; every H / shield keypress hits the endpoint fresh.

2. **Fallback — visual bar scan**
   When the service is unreachable (the common case), the functions below
   walk the health/shield bars pixel-by-pixel against the calibrated
   ``health_decreases`` step pattern. This is what ships by default and is
   what the user's F9 settings actually tune.

If you need to re-calibrate: ``python dev_tools/health_calibrator.py``.
"""
from PIL import ImageGrab
from accessible_output2.outputs.auto import Auto
from lib.utilities.utilities import read_config, get_config_boolean
from lib.managers.hotbar_manager import get_last_detected_rarity
from lib.detection.coordinate_config import get_health_shield_coords
import requests

speaker = Auto()

# Optional companion service (FA11y-OW). If not running, requests fail
# instantly and we fall back to the visual bar scan below.
API_BASE_URL = "http://127.0.0.1:6767/api"
API_TIMEOUT = 0.01

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
    Try to get health, shield, and overshield values from the FA11y-OW HTTP API.
    Returns (health, shield, overshield) tuple if successful, or (None, None, None) if API is unavailable.
    """
    try:
        # Get health
        health_response = requests.get(f"{API_BASE_URL}/health", timeout=API_TIMEOUT)
        health_data = health_response.json()
        health = health_data.get('health')
        
        # Get shield and overshield (both in same endpoint)
        shield_response = requests.get(f"{API_BASE_URL}/shield", timeout=API_TIMEOUT)
        shield_data = shield_response.json()
        shield = shield_data.get('shield')
        overshield = shield_data.get('overShield')
        
        # Only return if health and shield are valid numbers
        if health is not None and shield is not None:
            return (health, shield, overshield or 0)
        return (None, None, None)
        
    except (requests.RequestException, requests.Timeout, ValueError, KeyError) as e:
        # API not available, connection failed, or invalid response
        # Silently fall back to visual detection
        return (None, None, None)

def check_health_shields():
    """Check and announce health and shield values using API first, visual fallback."""
    try:
        # Try API first (fast and accurate when FA11y-OW is running)
        health, shield, overshield = get_health_shield_from_api()
        
        if health is not None:
            # Successfully got values from API
            speaker.speak(f'{health} Health')
            
            if shield > 0:
                speaker.speak(f'{shield} Shield')
            else:
                speaker.speak('No Shield')
            
            # Announce overshield if present
            if overshield > 0:
                speaker.speak(f'{overshield} Overshield')
            
            return
        
        # API failed or unavailable, fall back to visual detection
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

def check_rarity():
    """Check and announce the rarity of the last detected item."""
    rarity_str = get_last_detected_rarity()
    speaker.speak(rarity_str)
