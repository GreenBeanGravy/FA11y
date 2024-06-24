import ctypes
from typing import Tuple, Dict
from accessible_output2.outputs.auto import Auto
import pyautogui

speaker = Auto()

# Constants
VK_H, VK_LBRACKET = 0x48, 0xDB
HEALTH_COLOR, SHIELD_COLOR = (158, 255, 99), (110, 235, 255)
RARITY_COLORS: Dict[str, Tuple[int, int, int]] = {
    'Common': (116, 122, 128), 'Uncommon': (0, 128, 5), 'Rare': (0, 88, 191),
    'Epic': (118, 45, 211), 'Legendary': (191, 79, 0), 'Mythic': (191, 147, 35),
    'Exotic': (118, 191, 255),
}
TOLERANCE, RARITY_TOLERANCE = 70, 30
HEALTH_DECREASES, SHIELD_DECREASES = [4, 3, 3], [3, 4, 3]

def pixel_within_tolerance(pixel_color: Tuple[int, int, int], target_color: Tuple[int, int, int], tol: int) -> bool:
    return all(abs(pc - tc) <= tol for pc, tc in zip(pixel_color, target_color))

def check_value(start_x: int, y: int, decreases: list, color: Tuple[int, int, int], tolerance: int, name: str, no_value_msg: str):
    for i, x in enumerate(range(start_x, start_x - sum(decreases), -1)):
        if pixel_within_tolerance(pyautogui.pixel(x, y), color, tolerance):
            speaker.speak(f'{100 - i} {name},')
            return
    speaker.speak(no_value_msg)

def check_rarity(x: int, y: int) -> bool:
    pixel_color = pyautogui.pixel(x, y)
    for rarity, color in RARITY_COLORS.items():
        if pixel_within_tolerance(pixel_color, color, RARITY_TOLERANCE):
            speaker.speak(rarity)
            return True
    return False

def start_health_shield_rarity_detection():
    h_key_down = lbracket_key_down = False
    get_async_key_state = ctypes.windll.user32.GetAsyncKeyState

    while True:
        h_key_current_state = bool(get_async_key_state(VK_H) & 0x8000)
        if h_key_current_state and not h_key_down:
            check_value(453, 982, HEALTH_DECREASES, HEALTH_COLOR, TOLERANCE, 'Health', 'Cannot find Health Value!')
            check_value(453, 950, SHIELD_DECREASES, SHIELD_COLOR, TOLERANCE, 'Shields', 'No Shields')
        h_key_down = h_key_current_state

        lbracket_key_current_state = bool(get_async_key_state(VK_LBRACKET) & 0x8000)
        if lbracket_key_current_state and not lbracket_key_down:
            if not check_rarity(1205, 777) and not check_rarity(1205, 802):
                speaker.speak('Cannot find rarity.')
        lbracket_key_down = lbracket_key_current_state

if __name__ == "__main__":
    start_health_shield_rarity_detection()