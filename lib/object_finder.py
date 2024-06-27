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
    print(f"Loading icon from path: {icon_path}")
    icon = cv2.imread(icon_path, cv2.IMREAD_UNCHANGED)
    if icon is None:
        print(f"Failed to load icon from path: {icon_path}")
        return None
    return cv2.cvtColor(icon, cv2.COLOR_BGRA2BGR) if icon.shape[-1] == 4 else icon

def find_all_instances_on_screen(icon: np.ndarray, screen: np.ndarray, threshold: float) -> List[Tuple[int, int]]:
    result = cv2.matchTemplate(screen, icon, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= threshold)
    return list(zip(locations[1], locations[0]))  # x, y coordinates

def find_closest_object(icon_path: str, similarity_threshold: float) -> Optional[Tuple[int, int]]:
    print(f"Attempting to find closest object with icon: {icon_path}")
    screen = cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)
    icon = load_icon(icon_path)
    if icon is None:
        print(f"Icon could not be loaded from path: {icon_path}")
        return None

    instances = find_all_instances_on_screen(icon, screen, similarity_threshold)
    if not instances:
        print(f"No instances of the object found. Similarity threshold: {similarity_threshold}")
        return None

    icon_height, icon_width = icon.shape[:2]
    screen_center = (screen.shape[1] // 2, screen.shape[0] // 2)
    
    closest_instance = min(instances, key=lambda loc: ((loc[0] + icon_width//2 - screen_center[0])**2 + 
                                                       (loc[1] + icon_height//2 - screen_center[1])**2))
    
    center_x = closest_instance[0] + icon_width // 2
    center_y = closest_instance[1] + icon_height // 2
    print(f"Closest object found at center coordinates: ({center_x}, {center_y})")
    return (center_x, center_y)

def load_icon_configs() -> Dict[str, Tuple[str, float]]:
    icon_folder = 'icons'
    object_configs = {}
    
    print(f"Loading icon configurations from folder: {icon_folder}")
    for filename in os.listdir(icon_folder):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            object_name = os.path.splitext(filename)[0].lower().replace(' ', '_')
            icon_path = os.path.join(icon_folder, filename)
            threshold = 0.7
            object_configs[object_name] = (icon_path, threshold)
            print(f"Loaded configuration for object: {object_name}, path: {icon_path}, threshold: {threshold}")
    
    if 'gas_station' not in object_configs:
        print("Warning: Gas Station icon not found in icons folder. Please add it.")
    
    return object_configs

OBJECT_CONFIGS = load_icon_configs()

if __name__ == "__main__":
    print("Available objects:", list(OBJECT_CONFIGS.keys()))
    # You can add test code here if needed
    # For example:
    # for object_name, (icon_path, threshold) in OBJECT_CONFIGS.items():
    #     result = find_closest_object(icon_path, threshold)
    #     print(f"{object_name}: {result}")