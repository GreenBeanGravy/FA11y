import time
import sys
import os
import pyautogui

if sys.version_info >= (3, 12):
    class MockImp:
        __name__ = 'imp'
        
        @staticmethod
        def is_frozen(arg=None):
            if arg == "__main__":
                return hasattr(sys, "frozen") or '__compiled__' in globals()
            return hasattr(sys, 'frozen') or hasattr(sys, 'importers') or getattr(sys, 'frozen', False)

    sys.modules['imp'] = MockImp()

from accessible_output2.outputs.auto import Auto

# Initialize speaker
speaker = Auto()

def check_pixel_color(x, y, target_rgb, tolerance=10):
    pixel_color = pyautogui.pixel(x, y)
    return all(abs(a - b) <= tolerance for a, b in zip(pixel_color, target_rgb))

def smooth_move_and_click(x, y, duration=0.05):
    pyautogui.moveTo(x, y, duration=duration)
    pyautogui.click()

def send_friend_request(player_name):
    # Check initial pixel color at 1315, 640
    if not check_pixel_color(1315, 640, (14, 24, 52)):
        # Press Escape if the check fails
        pyautogui.press('esc')

    # Perform the sequence of actions for sending a friend request
    smooth_move_and_click(1320, 290)  # Left click on 1320, 290
    time.sleep(0.1)  # Wait for 100ms
    smooth_move_and_click(1880, 150)  # Left click on 1880, 150
    time.sleep(0.05)  # Wait for 50ms
    smooth_move_and_click(1630, 150)  # Left click on 1630, 150
    time.sleep(0.05)  # Wait for 50ms

    # Type in the player name
    pyautogui.write(player_name)
    time.sleep(0.05)  # Wait for 50ms
    pyautogui.press('enter')  # Press Enter
    time.sleep(2)  # Wait for 2000ms

    # Check the pixel color at 1415, 280
    if check_pixel_color(1415, 280, (0, 95, 160)):
        smooth_move_and_click(1415, 280)  # Left click at 1415, 280
        time.sleep(0.5)  # Wait for 500ms
        smooth_move_and_click(1650, 380)  # Left click at 1650, 380
        time.sleep(0.25)  # Wait for 250ms
        pyautogui.press('esc')  # Press Escape
        speaker.speak(f"Sent friend request to {player_name}")
    else:
        speaker.speak("This player is already on your friends list, or was not found.")
        print("This player is already on your friends list, or was not found.")
