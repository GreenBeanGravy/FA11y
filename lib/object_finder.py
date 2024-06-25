import cv2
import numpy as np
import pyautogui
from accessible_output2.outputs.auto import Auto
from typing import Tuple, Optional, Dict
from functools import lru_cache
import os

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

def load_icon_configs() -> Dict[str, Tuple[str, float]]:
    icon_folder = 'icons'
    object_configs = {}
    
    for filename in os.listdir(icon_folder):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            object_name = os.path.splitext(filename)[0].lower().replace(' ', '_')
            icon_path = os.path.join(icon_folder, filename)
            # You might want to adjust the threshold based on your needs
            threshold = 0.7
            object_configs[object_name] = (icon_path, threshold)
    
    return object_configs

OBJECT_CONFIGS = load_icon_configs()

if __name__ == "__main__":
    print("Available objects:", list(OBJECT_CONFIGS.keys()))
    # You can add test code here if needed
    # For example:
    # for object_name, (icon_path, threshold) in OBJECT_CONFIGS.items():
    #     result = find_object(icon_path, threshold)
    #     print(f"{object_name}: {result}")