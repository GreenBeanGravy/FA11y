import cv2
import numpy as np
from mss import mss
import os
import configparser
from threading import Lock
from lib.player_location import (
    ROI_START_ORIG,
    ROI_END_ORIG,
    get_angle_and_direction,
    get_relative_direction,
    get_player_position_description
)

# Constants
CAPTURE_REGION = {"top": 20, "left": 1600, "width": 300, "height": 300}

# Pre-compute constants
WIDTH, HEIGHT = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]

# Initialize objects
sift = cv2.SIFT_create()
bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
sct_lock = Lock()

class MapManager:
    def __init__(self):
        self.current_map = None
        self.current_image = None
        self.current_keypoints = None
        self.current_descriptors = None
    
    def switch_map(self, map_name: str) -> bool:
        if self.current_map == map_name:
            return True
        
        map_file = f"maps/{map_name}.png"
        if not os.path.exists(map_file):
            print(f"Error: Map file {map_file} not found")
            return False
        
        self.current_map = map_name
        self.current_image = cv2.imread(map_file, cv2.IMREAD_GRAYSCALE)
        self.current_keypoints, self.current_descriptors = sift.detectAndCompute(
            self.current_image, None
        )
        return True
    
map_manager = MapManager()

def capture_screen():
    with sct_lock:
        with mss() as sct:
            screenshot = np.array(sct.grab(CAPTURE_REGION))
    return cv2.cvtColor(screenshot, cv2.COLOR_RGBA2GRAY)

def find_best_match(captured_area):
    kp1, des1 = sift.detectAndCompute(captured_area, None)
    
    # Check if features were found in the captured area
    if des1 is None or len(des1) == 0:
        print("No features found in captured area")
        return None
    
    matches = bf.knnMatch(des1, map_manager.current_descriptors, k=2)
    
    # Filter good matches using ratio test
    good_matches = []
    for m, n in matches:
        if m.distance < 0.75 * n.distance:
            good_matches.append(m)
    
    # Need minimum number of matches for reliable homography
    MIN_MATCHES = 10
    if len(good_matches) > MIN_MATCHES:
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([map_manager.current_keypoints[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        
        # Calculate homography
        M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        
        # Check if homography was found
        if M is None:
            print("Could not compute homography")
            return None
            
        # Check if homography is valid
        if not np.all(np.isfinite(M)):
            print("Invalid homography matrix (contains inf/nan)")
            return None
            
        try:
            h, w = captured_area.shape
            pts = np.float32([[0, 0], [0, h-1], [w-1, h-1], [w-1, 0]]).reshape(-1, 1, 2)
            transformed_pts = cv2.perspectiveTransform(pts, M)
            
            # Validate transformed points
            if np.all(np.isfinite(transformed_pts)):
                return transformed_pts
            else:
                print("Invalid transformed points (contains inf/nan)")
                return None
                
        except cv2.error as e:
            print(f"OpenCV error during perspective transform: {e}")
            return None
    else:
        print(f"Not enough good matches: {len(good_matches)} < {MIN_MATCHES}")
        return None

def find_player_position():
    # Get current map from config
    config = configparser.ConfigParser()
    config.read('config.txt')
    current_map = config.get('POI', 'current_map', fallback='main')
    
    # Switch map if needed
    if not map_manager.switch_map(current_map):
        return None
    
    captured_area = capture_screen()
    matched_region = find_best_match(captured_area)
    
    if matched_region is not None:
        center = np.mean(matched_region, axis=0).reshape(-1)
        
        x = int(center[0] * WIDTH / map_manager.current_image.shape[1] + ROI_START_ORIG[0])
        y = int(center[1] * HEIGHT / map_manager.current_image.shape[0] + ROI_START_ORIG[1])
        
        return (x, y)
    return None
