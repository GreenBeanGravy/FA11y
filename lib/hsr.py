import ctypes, pyautogui
from accessible_output2.outputs.auto import Auto
import time

speaker = Auto()

VK_H, VK_LBRACKET = 0x48, 0xDB
health_color, shield_color = (158, 255, 99), (110, 235, 255)
rarity_colors = {
    'Common': (116, 122, 128), 'Uncommon': (0, 128, 5), 'Rare': (0, 88, 191),
    'Epic': (118, 45, 211), 'Legendary': (191, 79, 0), 'Mythic': (191, 147, 35),
    'Exotic': (118, 191, 255),
}
tolerance, rarity_tolerance = 70, 30
h_key_down, lbracket_key_down, f_key_down = False, False, False
health_decreases, shield_decreases = [4, 3, 3], [3, 4, 3]

def pixel_within_tolerance(pixel_color, target_color, tol):
    return all(abs(pc - tc) <= tol for pc, tc in zip(pixel_color, target_color))

def check_value(start_x, y, decreases, color, tolerance, name, no_value_msg):
    x = start_x
    for i in range(100, 0, -1):
        if pixel_within_tolerance(pyautogui.pixel(x, y), color, tolerance):
            speaker.speak(f'{i} {name},')
            return
        x -= decreases[i % len(decreases)]
    speaker.speak(no_value_msg)

def start_health_shield_rarity_detection():
    global h_key_down, lbracket_key_down
    while True:
        h_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_H))
        if h_key_current_state and not h_key_down:
            check_value(453, 982, health_decreases, health_color, tolerance, 'Health', 'Cannot find Health Value!')
            check_value(453, 950, shield_decreases, shield_color, tolerance, 'Shields', 'No Shields')

        h_key_down = h_key_current_state
        lbracket_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_LBRACKET))
        if lbracket_key_current_state and not lbracket_key_down:
            pixel_color = pyautogui.pixel(1205, 650)
            for rarity, color in rarity_colors.items():
                if pixel_within_tolerance(pixel_color, color, rarity_tolerance):
                    speaker.speak(rarity)
                    break
            else:
                speaker.speak('No Rarity Found.')
        
        lbracket_key_down = lbracket_key_current_state
