import time
from accessible_output2.outputs.auto import Auto
from lib.mouse import move_and_click, left_click

speaker = Auto()

def check_pixel_color(x, y, target_rgb, tolerance=10):
    """Check if pixel at coordinates matches target color within tolerance"""
    import pyautogui
    pixel_color = pyautogui.pixel(x, y)
    return all(abs(a - b) <= tolerance for a, b in zip(pixel_color, target_rgb))

def exit_match():
    """Exit the current match if the quick menu is open"""
    if check_pixel_color(1315, 640, (14, 24, 52)):
        time.sleep(0.1)  # Wait 100ms
        move_and_click(1320, 1010, duration=0.05)
        move_and_click(1500, 1025, duration=0.05)
        time.sleep(0.25)  # Wait 250ms
        left_click()  # Click again at the same position
    else:
        speaker.speak("Open your quick menu before attempting to leave a match. Press Escape to open your quick menu, and try again.")