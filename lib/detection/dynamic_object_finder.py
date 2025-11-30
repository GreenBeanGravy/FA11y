import cv2
import numpy as np
import os
import threading
from typing import Tuple, Optional, Dict, List, NamedTuple
from functools import lru_cache
from mss import mss

# Centralized minimap region and scale (should match utilities.py)
MINIMAP_REGION = {
    'left': 1637,
    'top': 33,
    'width': 250,
    'height': 250
}
MINIMAP_SCALE_FACTOR = 0.5

# For legacy/compat
class DetectionResult(NamedTuple):
    center_x: int
    center_y: int
    confidence: float
    scale: float

class BatchDetectionResult(NamedTuple):
    dynamic_object_name: str
    center_x: int
    center_y: int
    confidence: float
    scale: float

class FastDynamicObjectFinder:
    """Fast dynamic object detection with PPI coordinate conversion and batch processing"""
    def __init__(self):
        self.icon_cache = {}
        self.thread_local = threading.local()
        self.scales = [0.8, 0.9, 1.0]
        self.confidence_threshold = 0.76
        self.icons_loaded = False
        self.load_attempted = False
        self.load_all_icons()

    def get_mss_instance(self):
        if not hasattr(self.thread_local, 'mss'):
            self.thread_local.mss = mss()
        return self.thread_local.mss

    @lru_cache(maxsize=128)
    def load_icon(self, icon_path: str) -> Optional[np.ndarray]:
        if not os.path.exists(icon_path):
            return None
        try:
            icon = cv2.imread(icon_path, cv2.IMREAD_COLOR)
            if icon is None:
                return None
            if icon.shape[-1] == 4:
                icon = cv2.cvtColor(icon, cv2.COLOR_BGRA2BGR)
            return icon
        except Exception:
            return None

    def load_all_icons(self):
        if self.icons_loaded or self.load_attempted:
            return
        self.load_attempted = True
        icons_folder = 'icons'  # Fixed: Changed from 'dynamic_icons' to 'icons'
        if not os.path.exists(icons_folder):
            return
        loaded_count = 0
        try:
            for filename in os.listdir(icons_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    dynamic_object_name = os.path.splitext(filename)[0].lower().replace(' ', '_')
                    icon_path = os.path.join(icons_folder, filename)
                    icon = self.load_icon(icon_path)
                    if icon is not None:
                        self.icon_cache[dynamic_object_name] = {
                            'template': icon,
                            'path': icon_path
                        }
                        loaded_count += 1
        except Exception:
            pass
        if loaded_count > 0:
            self.icons_loaded = True

    def fast_multi_scale_match(self, screen: np.ndarray, template: np.ndarray) -> Optional[DetectionResult]:
        if screen is None or template is None:
            return None
        best_confidence = 0
        best_result = None
        template_h, template_w = template.shape[:2]
        screen_h, screen_w = screen.shape[:2]
        for scale in self.scales:
            scaled_h, scaled_w = int(template_h * scale), int(template_w * scale)
            if scaled_h > screen_h or scaled_w > screen_w:
                continue
            try:
                if scale != 1.0:
                    scaled_template = cv2.resize(template, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
                else:
                    scaled_template = template
                result = cv2.matchTemplate(screen, scaled_template, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                if max_val > best_confidence:
                    best_confidence = max_val
                    center_x = max_loc[0] + scaled_w // 2
                    center_y = max_loc[1] + scaled_h // 2
                    best_result = DetectionResult(
                        center_x=center_x,
                        center_y=center_y,
                        confidence=max_val,
                        scale=scale
                    )
            except (cv2.error, Exception):
                continue
        if best_result and best_result.confidence >= self.confidence_threshold:
            return best_result
        return None

    def batch_detect_dynamic_objects(self, screen: np.ndarray, dynamic_object_names: List[str]) -> List[BatchDetectionResult]:
        if screen is None or not dynamic_object_names:
            return []
        results = []
        for dynamic_object_name in dynamic_object_names:
            if dynamic_object_name not in self.icon_cache:
                continue
            try:
                template = self.icon_cache[dynamic_object_name]['template']
                detection_result = self.fast_multi_scale_match(screen, template)
                if detection_result:
                    batch_result = BatchDetectionResult(
                        dynamic_object_name=dynamic_object_name,
                        center_x=detection_result.center_x,
                        center_y=detection_result.center_y,
                        confidence=detection_result.confidence,
                        scale=detection_result.scale
                    )
                    results.append(batch_result)
            except Exception:
                continue
        return results

    def capture_region(self, region: Dict) -> Optional[np.ndarray]:
        try:
            sct = self.get_mss_instance()
            if sct is None:
                return None
            capture_dict = {
                'left': region['left'],
                'top': region['top'],
                'width': region['width'],
                'height': region['height']
            }
            screenshot = np.array(sct.grab(capture_dict))
            if screenshot.shape[2] == 4:
                screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
            return screenshot
        except Exception:
            return None

    def convert_minimap_to_fullmap_coords(self, minimap_coords: Tuple[int, int],
                                          player_fullmap_pos: Tuple[int, int]) -> Tuple[int, int]:
        minimap_x, minimap_y = minimap_coords
        player_fullmap_x, player_fullmap_y = player_fullmap_pos
        minimap_center_x = MINIMAP_REGION['left'] + MINIMAP_REGION['width'] // 2
        minimap_center_y = MINIMAP_REGION['top'] + MINIMAP_REGION['height'] // 2
        offset_x = minimap_x - minimap_center_x
        offset_y = minimap_y - minimap_center_y
        fullmap_x = int(player_fullmap_x + (offset_x * MINIMAP_SCALE_FACTOR))
        fullmap_y = int(player_fullmap_y + (offset_y * MINIMAP_SCALE_FACTOR))
        return (fullmap_x, fullmap_y)

    def find_all_dynamic_objects(self, dynamic_object_names: List[str], use_ppi: bool = False) -> Dict[str, Tuple[int, int]]:
        if not dynamic_object_names or not self.icons_loaded:
            return {}
        try:
            if use_ppi:
                from lib.detection.player_position import find_player_position
                player_fullmap_pos = find_player_position()
                if player_fullmap_pos is None:
                    return {}
                screen = self.capture_region(MINIMAP_REGION)
                if screen is None:
                    return {}
                batch_results = self.batch_detect_dynamic_objects(screen, dynamic_object_names)
                found_dynamic_objects = {}
                for result in batch_results:
                    minimap_screen_x = result.center_x + MINIMAP_REGION['left']
                    minimap_screen_y = result.center_y + MINIMAP_REGION['top']
                    fullmap_coords = self.convert_minimap_to_fullmap_coords(
                        (minimap_screen_x, minimap_screen_y),
                        player_fullmap_pos
                    )
                    found_dynamic_objects[result.dynamic_object_name] = fullmap_coords
                return found_dynamic_objects
            else:
                # For fullscreen searching, capture entire screen
                import pyautogui
                screenshot_rgba = np.array(pyautogui.screenshot())
                if screenshot_rgba.shape[2] == 4:
                    screenshot = cv2.cvtColor(screenshot_rgba, cv2.COLOR_RGBA2BGR)
                else:
                    screenshot = screenshot_rgba
                
                batch_results = self.batch_detect_dynamic_objects(screenshot, dynamic_object_names)
                found_dynamic_objects = {}
                for result in batch_results:
                    found_dynamic_objects[result.dynamic_object_name] = (result.center_x, result.center_y)
                return found_dynamic_objects
        except Exception:
            return {}

    def find_dynamic_objects_on_minimap_screen(self, dynamic_object_names: List[str]) -> Dict[str, Tuple[int, int]]:
        """Detects dynamic objects on the minimap and returns their screen coordinates."""
        if not dynamic_object_names or not self.icons_loaded:
            return {}
        try:
            screen = self.capture_region(MINIMAP_REGION)
            if screen is None:
                return {}
            batch_results = self.batch_detect_dynamic_objects(screen, dynamic_object_names)
            found_dynamic_objects = {}
            for result in batch_results:
                minimap_screen_x = result.center_x + MINIMAP_REGION['left']
                minimap_screen_y = result.center_y + MINIMAP_REGION['top']
                found_dynamic_objects[result.dynamic_object_name] = (minimap_screen_x, minimap_screen_y)
            return found_dynamic_objects
        except Exception:
            return {}

    def find_closest_dynamic_object(self, dynamic_object_name: str, use_ppi: bool = False) -> Optional[Tuple[int, int]]:
        results = self.find_all_dynamic_objects([dynamic_object_name], use_ppi)
        return results.get(dynamic_object_name)

    def cleanup(self):
        if hasattr(self.thread_local, 'mss'):
            try:
                self.thread_local.mss.close()
            except Exception:
                pass

optimized_finder = FastDynamicObjectFinder()

def load_dynamic_object_configs() -> Dict[str, Tuple[str, float]]:
    """Load dynamic object configurations"""
    icon_folder = 'icons'  # Fixed: Changed from 'dynamic_icons' to 'icons'
    dynamic_object_configs = {}
    if not os.path.exists(icon_folder):
        return dynamic_object_configs
    try:
        for filename in os.listdir(icon_folder):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                dynamic_object_name = os.path.splitext(filename)[0].lower().replace(' ', '_')
                icon_path = os.path.join(icon_folder, filename)
                threshold = 0.72
                dynamic_object_configs[dynamic_object_name] = (icon_path, threshold)
    except Exception:
        pass
    return dynamic_object_configs

DYNAMIC_OBJECT_CONFIGS = load_dynamic_object_configs()