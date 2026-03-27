import time
import traceback
from PIL import ImageGrab
from accessible_output2.outputs.auto import Auto
from lib.utilities.mouse import instant_click, pixel

speaker = Auto()

def _log(msg):
    """Log to console and speak via accessible output for debugging."""
    print(f"[exit_match] {msg}")
    speaker.speak(f"{msg}")

def check_pixel_color(x, y, target_rgb, tolerance=10):
    pixel_color = pixel(x, y)
    _log(f"check_pixel_color({x}, {y}) => {pixel_color}, target={target_rgb}, tol={tolerance}")
    return all(abs(a - b) <= tolerance for a, b in zip(pixel_color, target_rgb))

def exit_match():
    """Exit match - mirrors original: pyautogui.click(x,y) + sleep(0.1) between each."""
    _log("exit_match() called")
    try:
        white_check = check_pixel_color(1847, 74, (255, 255, 255))
        black_check = check_pixel_color(1847, 74, (0, 0, 0))
        _log(f"Pixel checks: white={white_check}, black={black_check}")

        if white_check or black_check:
            _log("Quick menu detected, starting leave sequence...")
            instant_click(1834, 76)
            time.sleep(0.1)
            instant_click(1573, 255)
            time.sleep(0.1)
            instant_click(1579, 924)
            _log("Leave sequence complete")
        else:
            _log("Quick menu NOT detected")
            speaker.speak("Open your quick menu before attempting to leave a match. Press Escape to open your quick menu, and try again.")
    except Exception as e:
        _log(f"ERROR in exit_match: {e}")
        _log(traceback.format_exc())
