"""
Test script to check pixel at (84, 335) using both methods
Run this while you have the search results visible to verify the pixel color
"""
import pyautogui
from lib.managers.screenshot_manager import capture_coordinates, screenshot_manager

print("Testing pixel at position (84, 335)...")
print("=" * 60)

# Method 1: PyAutoGUI
try:
    pyautogui_color = pyautogui.pixel(84, 335)
    print(f"PyAutoGUI pixel(84, 335): {pyautogui_color}")
except Exception as e:
    print(f"PyAutoGUI error: {e}")

# Method 2: FA11y capture_coordinates (1x1 region)
try:
    pixel = capture_coordinates(84, 335, 1, 1, 'rgb')
    if pixel is not None and pixel.shape[0] > 0 and pixel.shape[1] > 0:
        fa11y_color = tuple(pixel[0, 0])
        print(f"FA11y capture_coordinates(84, 335, 1, 1): {fa11y_color}")
    else:
        print("FA11y capture_coordinates: Failed")
except Exception as e:
    print(f"FA11y error: {e}")

# Method 3: FA11y full screen (like dev tool does)
try:
    full_screen = screenshot_manager.capture_full_screen('rgb')
    if full_screen is not None:
        # Note: numpy arrays are indexed [y, x] not [x, y]
        dev_tool_color = tuple(full_screen[335, 84])
        print(f"FA11y full_screen[335, 84] (dev tool method): {dev_tool_color}")
    else:
        print("FA11y full_screen: Failed")
except Exception as e:
    print(f"FA11y full_screen error: {e}")

print("=" * 60)
print("\nRun this script with the search results visible on screen")
print("to see what the pixel actually is at (84, 335)")
