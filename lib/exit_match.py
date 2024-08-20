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
    if check_pixel_color(1315, 640, (14, 24, 52)):
        time.sleep(0.1)  # Wait 100ms
        smooth_move_and_click(1320, 1010)
        smooth_move_and_click(1500, 1025)
        time.sleep(0.25)  # Wait 250ms
        pyautogui.click()  # Click again at the same position
    else:
        speaker.speak("You are not in your quick menu!")