import cv2
import numpy as np
import pyautogui
from accessible_output2.outputs.auto import Auto
from typing import Tuple, Optional, Dict, List
from functools import lru_cache
import os

speaker = Auto()

@lru_cache(maxsize=None)
def load_icon(icon_path: str) -> np.ndarray:
    icon = cv2.imread(icon_path, cv2.IMREAD_UNCHANGED)
    return cv2.cvtColor(icon, cv2.COLOR_BGRA2BGR) if icon.shape[-1] == 4 else icon

def find_all_instances(icon: np.ndarray, screen: np.ndarray, threshold: float) -> List[Tuple[int, int]]:
    result = cv2.matchTemplate(screen, icon, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= threshold)
    return list(zip(*locations[::-1]))  # Reverse to get (x, y) format

def find_closest_instance(instances: List[Tuple[int, int]], player_position: Tuple[int, int]) -> Optional[Tuple[int, int]]:
    if not instances:
        return None
    return min(instances, key=lambda pos: np.linalg.norm(np.array(pos) - np.array(player_position)))

def find_object(icon_path: str, similarity_threshold: float, player_position: Optional[Tuple[int, int]] = None) -> Optional[Tuple[int, int]]:
    screen = cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)
    icon = load_icon(icon_path)
    instances = find_all_instances(icon, screen, similarity_threshold)
    
    if player_position:
        return find_closest_instance(instances, player_position)
    elif instances:
        return instances[0]  # Return the first instance if player position is not provided
    else:
        return None

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
    # player_pos = (800, 600)  # Example player position
    # for object_name, (icon_path, threshold) in OBJECT_CONFIGS.items():
    #     result = find_object(icon_path, threshold, player_pos)
    #     print(f"{object_name}: {result}")