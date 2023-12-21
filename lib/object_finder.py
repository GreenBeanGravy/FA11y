import cv2
import numpy as np
import pyautogui
from accessible_output2.outputs.auto import Auto

def find_image_on_screen(icon_path, screen):
    icon = cv2.imread(icon_path, cv2.IMREAD_UNCHANGED)

    # Convert icons with alpha channel to RGB
    if icon.shape[-1] == 4:
        icon = cv2.cvtColor(icon, cv2.COLOR_BGRA2BGR)

    result = cv2.matchTemplate(screen, icon, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    return max_val, max_loc

def find_the_train():
    screen = pyautogui.screenshot()
    screen = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)
    similarity, location = find_image_on_screen('icons/The Train.png', screen)

    if similarity >= 0.7:
        return location
    else:
        return None

def find_combat_cache():
    screen = pyautogui.screenshot()
    screen = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)
    similarity, location = find_image_on_screen('icons/Combat Cache.png', screen)

    if similarity >= 0.65:
        return location
    else:
        return None

def find_storm_tower():
    screen = pyautogui.screenshot()
    screen = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)
    similarity, location = find_image_on_screen('icons/Storm Tower.png', screen)

    if similarity >= 0.7:
        return location
    else:
        return None
