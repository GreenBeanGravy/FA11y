import time
import pyautogui
from accessible_output2.outputs.auto import Auto

speaker = Auto()

def check_pixel_color(x, y, target_rgb, tolerance=10):
    pixel_color = pyautogui.pixel(x, y)
    return all(abs(a - b) <= tolerance for a, b in zip(pixel_color, target_rgb))

def smooth_move_and_click(x, y, duration=0.05):
    pyautogui.moveTo(x, y, duration=duration)
    pyautogui.click()

def exit_match():
    if check_pixel_color(1847, 74, (255, 255, 255)) or check_pixel_color(1847, 74, (0, 0, 0)):
        pyautogui.click(1834, 76)
        time.sleep(0.1)
        pyautogui.click(1573, 255)
        time.sleep(0.1)
        pyautogui.click(1579, 924)
    else:
        speaker.speak("Open your quick menu before attempting to leave a match. Press Escape to open your quick menu, and try again.")