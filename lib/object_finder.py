import cv2
import numpy as np
import pyautogui
from accessible_output2.outputs.auto import Auto
from typing import Tuple, Optional, Dict
from functools import lru_cache

speaker = Auto()

@lru_cache(maxsize=None)
def load_icon(icon_path: str) -> np.ndarray:
    icon = cv2.imread(icon_path, cv2.IMREAD_UNCHANGED)
    return cv2.cvtColor(icon, cv2.COLOR_BGRA2BGR) if icon.shape[-1] == 4 else icon

def find_image_on_screen(icon: np.ndarray, screen: np.ndarray) -> Tuple[float, Tuple[int, int]]:
    result = cv2.matchTemplate(screen, icon, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    return max_val, max_loc

def find_object(icon_path: str, similarity_threshold: float) -> Optional[Tuple[int, int]]:
    screen = cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)
    icon = load_icon(icon_path)
    similarity, location = find_image_on_screen(icon, screen)
    return location if similarity >= similarity_threshold else None

OBJECT_CONFIGS: Dict[str, Tuple[str, float]] = {
    'the_train': ('icons/The Train.png', 0.7),
    'combat_cache': ('icons/Combat Cache.png', 0.65),
    'storm_tower': ('icons/Storm Tower.png', 0.7),
    'reboot': ('icons/Reboot.png', 0.7)
}

def create_finder_function(object_name: str) -> callable:
    icon_path, threshold = OBJECT_CONFIGS[object_name]
    return lambda: find_object(icon_path, threshold)

find_the_train = create_finder_function('the_train')
find_combat_cache = create_finder_function('combat_cache')
find_storm_tower = create_finder_function('storm_tower')
find_reboot = create_finder_function('reboot')

if __name__ == "__main__":
    # Add any test code here if needed
    pass