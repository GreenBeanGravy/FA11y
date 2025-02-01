from PIL import ImageGrab
from accessible_output2.outputs.auto import Auto
from lib.utilities import read_config, get_config_boolean

speaker = Auto()

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

def check_rarity():
    screenshot = ImageGrab.grab(bbox=(0, 0, 1920, 1080))
    pixels = screenshot.load()
    for coords in [(1205, 657), (1205, 802)]:
        pixel_color = pixels[coords]
        for rarity, color in rarity_colors.items():
            if pixel_within_tolerance(pixel_color, color, rarity_tolerance):
                speaker.speak(rarity)
                return
    speaker.speak('Cannot find rarity.')

def check_health_shields():
    screenshot = ImageGrab.grab(bbox=(0, 0, 1920, 1080))
    pixels = screenshot.load()
    check_value(pixels, 423, 1024, health_decreases, health_color, tolerance, 'Health', 'Cannot find Health Value!')
    check_value(pixels, 423, 984, shield_decreases, shield_color, tolerance, 'Shields', 'No Shields')
