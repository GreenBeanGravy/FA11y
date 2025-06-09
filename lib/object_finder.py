import cv2
import numpy as np
import os
import threading
from typing import Tuple, Optional, Dict, List, NamedTuple
from functools import lru_cache
from mss import mss

class DetectionResult(NamedTuple):
    """Results from object detection"""
    center_x: int
    center_y: int
    confidence: float
    scale: float

class BatchDetectionResult(NamedTuple):
    """Results from batch object detection"""
    object_name: str
    center_x: int
    center_y: int
    confidence: float
    scale: float

class RegionConfig(NamedTuple):
    """Screen region configuration"""
    left: int
    top: int
    width: int
    height: int

FULLSCREEN_REGION = RegionConfig(524, 84, 866, 926)
MINIMAP_REGION = RegionConfig(1580, 0, 400, 400)

MINIMAP_SCALE_FACTOR = 0.5

class FastObjectFinder:
    """Fast object detection with PPI coordinate conversion and batch processing"""
    
    def __init__(self):
        self.icon_cache = {}
        self.thread_local = threading.local()
        
        self.scales = [0.8, 0.9, 1.0]
        self.confidence_threshold = 0.76
        
        self.icons_loaded = False
        self.load_attempted = False
        
        self.load_all_icons()

    def get_mss_instance(self):
        """Get thread-local MSS instance"""
        if not hasattr(self.thread_local, 'mss'):
            self.thread_local.mss = mss()
        return self.thread_local.mss

    @lru_cache(maxsize=128)
    def load_icon(self, icon_path: str) -> Optional[np.ndarray]:
        """Load and cache icon"""
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
        """Load all icons efficiently"""
        if self.icons_loaded or self.load_attempted:
            return
            
        self.load_attempted = True
        icons_folder = 'icons'
        
        if not os.path.exists(icons_folder):
            return
            
        loaded_count = 0
        try:
            for filename in os.listdir(icons_folder):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    object_name = os.path.splitext(filename)[0].lower().replace(' ', '_')
                    icon_path = os.path.join(icons_folder, filename)
                    
                    icon = self.load_icon(icon_path)
                    if icon is not None:
                        self.icon_cache[object_name] = {
                            'template': icon,
                            'path': icon_path
                        }
                        loaded_count += 1
        except Exception:
            pass
        
        if loaded_count > 0:
            self.icons_loaded = True

    def fast_multi_scale_match(self, screen: np.ndarray, template: np.ndarray) -> Optional[DetectionResult]:
        """Fast multi-scale template matching with performance optimizations"""
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
                    scaled_template = cv2.resize(template, (scaled_w, scaled_h), 
                                               interpolation=cv2.INTER_AREA)
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

    def batch_detect_objects(self, screen: np.ndarray, object_names: List[str]) -> List[BatchDetectionResult]:
        """Detect multiple objects in a single screen capture"""
        if screen is None or not object_names:
            return []
            
        results = []
        
        for object_name in object_names:
            if object_name not in self.icon_cache:
                continue
                
            try:
                template = self.icon_cache[object_name]['template']
                detection_result = self.fast_multi_scale_match(screen, template)
                
                if detection_result:
                    batch_result = BatchDetectionResult(
                        object_name=object_name,
                        center_x=detection_result.center_x,
                        center_y=detection_result.center_y,
                        confidence=detection_result.confidence,
                        scale=detection_result.scale
                    )
                    results.append(batch_result)
            except Exception:
                continue
        
        return results

    def capture_region(self, region: RegionConfig) -> Optional[np.ndarray]:
        """Capture a specific screen region with error handling"""
        try:
            sct = self.get_mss_instance()
            if sct is None:
                return None
                
            capture_dict = {
                'left': region.left,
                'top': region.top,
                'width': region.width,
                'height': region.height
            }
            screenshot = np.array(sct.grab(capture_dict))
            
            if screenshot.shape[2] == 4:
                screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
                
            return screenshot
            
        except Exception:
            return None

    def convert_minimap_to_fullmap_coords(self, minimap_coords: Tuple[int, int], 
                                        player_fullmap_pos: Tuple[int, int]) -> Tuple[int, int]:
        """Convert minimap coordinates to full map coordinates"""
        minimap_x, minimap_y = minimap_coords
        player_fullmap_x, player_fullmap_y = player_fullmap_pos
        
        actual_minimap_center_x = 1750
        actual_minimap_center_y = 169
        
        offset_x = minimap_x - actual_minimap_center_x
        offset_y = minimap_y - actual_minimap_center_y
        
        fullmap_x = int(player_fullmap_x + (offset_x * MINIMAP_SCALE_FACTOR))
        fullmap_y = int(player_fullmap_y + (offset_y * MINIMAP_SCALE_FACTOR))
        
        return (fullmap_x, fullmap_y)

    def find_all_objects(self, object_names: List[str], use_ppi: bool = False) -> Dict[str, Tuple[int, int]]:
        """Find multiple objects efficiently with single screen capture"""
        if not object_names or not self.icons_loaded:
            return {}
        
        try:
            if use_ppi:
                from lib.player_position import find_player_position
                
                player_fullmap_pos = find_player_position()
                if player_fullmap_pos is None:
                    return {}
                
                screen = self.capture_region(MINIMAP_REGION)
                if screen is None:
                    return {}
                
                batch_results = self.batch_detect_objects(screen, object_names)
                
                found_objects = {}
                for result in batch_results:
                    minimap_screen_x = result.center_x + MINIMAP_REGION.left
                    minimap_screen_y = result.center_y + MINIMAP_REGION.top
                    
                    fullmap_coords = self.convert_minimap_to_fullmap_coords(
                        (minimap_screen_x, minimap_screen_y), 
                        player_fullmap_pos
                    )
                    
                    found_objects[result.object_name] = fullmap_coords
                
                return found_objects
                
            else:
                screen = self.capture_region(FULLSCREEN_REGION)
                if screen is None:
                    return {}
                
                batch_results = self.batch_detect_objects(screen, object_names)
                
                found_objects = {}
                for result in batch_results:
                    screen_x = result.center_x + FULLSCREEN_REGION.left
                    screen_y = result.center_y + FULLSCREEN_REGION.top
                    
                    found_objects[result.object_name] = (screen_x, screen_y)
                
                return found_objects
        except Exception:
            return {}

    def find_closest_object(self, object_name: str, use_ppi: bool = False) -> Optional[Tuple[int, int]]:
        """Find single object (legacy compatibility)"""
        results = self.find_all_objects([object_name], use_ppi)
        return results.get(object_name)

    def cleanup(self):
        """Clean up resources"""
        if hasattr(self.thread_local, 'mss'):
            try:
                self.thread_local.mss.close()
            except Exception:
                pass

optimized_finder = FastObjectFinder()

@lru_cache(maxsize=None)
def load_icon(icon_path: str) -> np.ndarray:
    """Legacy compatibility function"""
    return optimized_finder.load_icon(icon_path)

def find_closest_object(icon_path: str, similarity_threshold: float, use_ppi: bool = False) -> Optional[Tuple[int, int]]:
    """Legacy compatibility function with PPI support"""
    object_name = os.path.splitext(os.path.basename(icon_path))[0].lower().replace(' ', '_')
    return optimized_finder.find_closest_object(object_name, use_ppi)

def find_all_instances_on_screen(icon: np.ndarray, screen: np.ndarray, threshold: float) -> List[Tuple[int, int]]:
    """Legacy compatibility function"""
    try:
        result = cv2.matchTemplate(screen, icon, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)
        return list(zip(locations[1], locations[0]))
    except Exception:
        return []

def load_icon_configs() -> Dict[str, Tuple[str, float]]:
    """Load icon configurations"""
    icon_folder = 'icons'
    object_configs = {}

    if not os.path.exists(icon_folder):
        return object_configs

    try:
        for filename in os.listdir(icon_folder):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                object_name = os.path.splitext(filename)[0].lower().replace(' ', '_')
                icon_path = os.path.join(icon_folder, filename)
                threshold = 0.72
                object_configs[object_name] = (icon_path, threshold)
    except Exception:
        pass

    return object_configs

OBJECT_CONFIGS = load_icon_configs()