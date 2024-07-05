import ctypes
from PIL import ImageGrab
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
health_decreases, shield_decreases = [4, 3, 3], [3, 4, 3]

def pixel_within_tolerance(pixel_color, target_color, tol):
    return all(abs(pc - tc) <= tol for pc, tc in zip(pixel_color, target_color))

def check_value(pixels, start_x, y, decreases, color, tolerance, name, no_value_msg):
    x = start_x
    for i in range(100, 0, -1):
        if pixel_within_tolerance(pixels[x, y], color, tolerance):
            speaker.speak(f'{i} {name}')
            return
        x -= decreases[i % len(decreases)]
    speaker.speak(no_value_msg)

def check_rarity(pixels):
    for coords in [(1205, 777), (1205, 802)]:
        pixel_color = pixels[coords]
        for rarity, color in rarity_colors.items():
            if pixel_within_tolerance(pixel_color, color, rarity_tolerance):
                speaker.speak(rarity)
                return
    speaker.speak('Cannot find rarity.')

def start_health_shield_rarity_detection():
    h_key_down = lbracket_key_down = False
    while True:
        h_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_H) & 0x8000)
        lbracket_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_LBRACKET) & 0x8000)

        if h_key_current_state != h_key_down or lbracket_key_current_state != lbracket_key_down:
            screenshot = ImageGrab.grab(bbox=(0, 0, 1920, 1080))
            pixels = screenshot.load()

            if h_key_current_state and not h_key_down:
                check_value(pixels, 453, 982, health_decreases, health_color, tolerance, 'Health', 'Cannot find Health Value!')
                check_value(pixels, 453, 950, shield_decreases, shield_color, tolerance, 'Shields', 'No Shields')

            if lbracket_key_current_state and not lbracket_key_down:
                check_rarity(pixels)

        h_key_down = h_key_current_state
        lbracket_key_down = lbracket_key_current_state

        time.sleep(0.01)  # Small delay to reduce CPU usage

if __name__ == "__main__":
    start_health_shield_rarity_detection()
