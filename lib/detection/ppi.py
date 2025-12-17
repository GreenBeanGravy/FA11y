"""
Player Position Interface (PPI) module for FA11y
Handles map-based position detection using computer vision.
"""
import cv2
import numpy as np
import os
from mss import mss
from typing import Optional, Tuple
from lib.utilities.utilities import read_config

# Check if OpenCL is available and enable it. OpenCV's T-API will handle the rest.
use_gpu = cv2.ocl.haveOpenCL()
if use_gpu:
    cv2.ocl.setUseOpenCL(True)
    # Corrected, safe print statement
    # print("OpenCL-compatible GPU found. Enabling GPU acceleration.")
# else:
    # print("No OpenCL-compatible GPU found. Using CPU for PPI.")

# PPI constants - Current/Default
PPI_CAPTURE_REGION = {"top": 33, "left": 1637, "width": 250, "height": 250}

# Core constants for screen regions (imported from player_position for consistency)
ROI_START_ORIG = (524, 84)
ROI_END_ORIG = (1390, 1010)

# Legacy PPI constants (for "o g" map)
PPI_CAPTURE_REGION_LEGACY = {"top": 20, "left": 1600, "width": 300, "height": 300}
ROI_START_ORIG_LEGACY = (524, 84)
ROI_END_ORIG_LEGACY = (1390, 1010)

# Detection region dimensions
WIDTH, HEIGHT = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]

def get_ppi_coordinates(map_name: str) -> dict:
    """Get appropriate PPI capture region based on map name"""
    if map_name == "o g":
        return PPI_CAPTURE_REGION_LEGACY
    return PPI_CAPTURE_REGION

def get_roi_coordinates(map_name: str) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Get appropriate ROI start/end coordinates based on map name"""
    if map_name == "o g":
        return ROI_START_ORIG_LEGACY, ROI_END_ORIG_LEGACY
    return ROI_START_ORIG, ROI_END_ORIG

class MapManager:
    """Manages map data and matching for position detection - optimized for per-map loading"""
    
    def __init__(self):
        self.current_map = None
        self.current_image_dims = None # Store dimensions for calculations
        self.current_keypoints = None
        self.current_descriptors = None
        
        # SIFT and BFMatcher objects are the same, the T-API handles where they run
        self.sift = cv2.SIFT_create()
        self.bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
        
        # Cache to prevent repeated prints when loading the same map
        self.map_load_cache = {}
        self.last_map_printed = None
    
    def switch_map(self, map_name: str) -> bool:
        """Switch to a different map with optimized loading and reduced spam"""
        if self.current_map == map_name:
            return True
        
        # Check cache first
        if map_name in self.map_load_cache:
            cache_entry = self.map_load_cache[map_name]
            self.current_map = map_name
            self.current_image_dims = cache_entry['dims']
            self.current_keypoints = cache_entry['keypoints']
            self.current_descriptors = cache_entry['descriptors']
            return True
        
        map_file = f"maps/{map_name}.png"
        if not os.path.exists(map_file):
            if self.last_map_printed != map_name:  # Reduce spam
                print(f"Map file not found: {map_file}")
                self.last_map_printed = map_name
            return False
        
        self.current_map = map_name
        cpu_image = cv2.imread(map_file, cv2.IMREAD_GRAYSCALE)
        self.current_image_dims = cpu_image.shape
        
        # Convert the numpy array to a UMat. This tells OpenCV it can be used on the GPU.
        umat_image = cv2.UMat(cpu_image)
        
        self.current_keypoints, self.current_descriptors = self.sift.detectAndCompute(
            umat_image, None
        )
        
        # Cache the loaded map
        self.map_load_cache[map_name] = {
            'dims': self.current_image_dims,
            'keypoints': self.current_keypoints,
            'descriptors': self.current_descriptors
        }
        
        return True

# Global map manager instance
map_manager = MapManager()

def capture_map_screen(map_name: str = "main"):
    """Capture the map area of the screen using appropriate coordinates for the map"""
    capture_region = get_ppi_coordinates(map_name)
    with mss() as sct:
        screenshot_rgba = np.array(sct.grab(capture_region))
    return cv2.cvtColor(screenshot_rgba, cv2.COLOR_BGRA2GRAY)

def find_best_match(captured_area):
    """Find the best match between captured area and current map"""
    # Convert captured area to UMat to enable GPU processing
    umat_captured_area = cv2.UMat(captured_area)
    
    kp1, des1 = map_manager.sift.detectAndCompute(umat_captured_area, None)
    
    if des1 is None or map_manager.current_descriptors is None:
        return None
    
    # The knnMatch function will automatically use the GPU if descriptors are UMat objects
    matches = map_manager.bf.knnMatch(des1, map_manager.current_descriptors, k=2)
    
    good_matches = []
    for match_pair in matches:
        if len(match_pair) == 2:
            m, n = match_pair
            if m.distance < 0.75 * n.distance:
                good_matches.append(m)
    
    MIN_MATCHES = 25
    if len(good_matches) > MIN_MATCHES:
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([map_manager.current_keypoints[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        
        M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        
        if M is None or not np.all(np.isfinite(M)):
            return None
            
        try:
            h, w = captured_area.shape
            pts = np.float32([[0, 0], [0, h-1], [w-1, h-1], [w-1, 0]]).reshape(-1, 1, 2)
            transformed_pts = cv2.perspectiveTransform(pts, M)
            
            if np.all(np.isfinite(transformed_pts)):
                return transformed_pts
            else:
                return None
                
        except cv2.error:
            return None
    else:
        return None

def find_player_position() -> Optional[Tuple[int, int]]:
    """Find player position using the map"""
    config = read_config()
    current_map_id = config.get('POI', 'current_map', fallback='main')

    # Extract actual map name for file loading
    if current_map_id == 'main':
        map_filename_to_load = 'main'
    else:
        if current_map_id.startswith("map_") and "_pois" in current_map_id:
            map_name_parts = current_map_id.split("_pois")
            base_name = map_name_parts[0]
            if base_name.startswith("map_"):
                base_name = base_name[4:]
            map_filename_to_load = base_name
        else:
            map_filename_to_load = current_map_id

    if not map_manager.switch_map(map_filename_to_load):
        return None

    # Get appropriate coordinates based on map name
    roi_start, roi_end = get_roi_coordinates(map_filename_to_load)
    roi_width = roi_end[0] - roi_start[0]
    roi_height = roi_end[1] - roi_start[1]

    captured_area = capture_map_screen(map_filename_to_load)
    matched_region = find_best_match(captured_area)

    if matched_region is not None:
        center = np.mean(matched_region, axis=0).reshape(-1)

        map_h, map_w = map_manager.current_image_dims
        x = int(center[0] * (roi_width / map_w) + roi_start[0])
        y = int(center[1] * (roi_height / map_h) + roi_start[1])

        return (x, y)
    return None

def get_ppi_status() -> dict:
    """Get current PPI system status for debugging"""
    # Descriptors can be UMat, get() retrieves them as numpy arrays to count
    desc = map_manager.current_descriptors
    desc_count = 0
    if desc is not None:
        # Check if the descriptor object is a UMat before calling .get()
        if isinstance(desc, cv2.UMat):
            desc_count = desc.get().shape[0]
        else: # It's a numpy array on CPU
            desc_count = desc.shape[0]

    return {
        'current_map': map_manager.current_map,
        'map_loaded': map_manager.current_image_dims is not None,
        'using_gpu_acceleration': use_gpu,
        'keypoints_count': len(map_manager.current_keypoints) if map_manager.current_keypoints else 0,
        'descriptors_count': desc_count,
        'cached_maps': list(map_manager.map_load_cache.keys())
    }

def cleanup_ppi():
    """Clean up PPI resources"""
    global map_manager
    if map_manager:
        map_manager.map_load_cache.clear()
        map_manager.current_map = None
        map_manager.current_image_dims = None
        map_manager.current_keypoints = None
        map_manager.current_descriptors = None