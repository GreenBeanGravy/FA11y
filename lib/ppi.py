import cv2
import numpy as np
from mss import mss
import os
from threading import Lock
from lib.player_location import (
    ROI_START_ORIG,
    ROI_END_ORIG,
    get_angle_and_direction,
    get_relative_direction,
    get_player_position_description
)

# Constants
CAPTURE_REGION = {"top": 10, "left": 1610, "width": 300, "height": 300}
MAP_IMAGE_PATH = "map.jpg"

# Pre-compute constants
WIDTH, HEIGHT = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]

# Initialize objects
sift = cv2.SIFT_create()
bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
sct_lock = Lock()
map_image = None
map_keypoints = None
map_descriptors = None

def load_map_image(path):
    global map_image, map_keypoints, map_descriptors
    if not os.path.exists(path):
        print(f"Error: Map image not found at {path}")
        return None
    map_image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    map_keypoints, map_descriptors = sift.detectAndCompute(map_image, None)
    return map_image

def capture_screen():
    with sct_lock:
        with mss() as sct:
            screenshot = np.array(sct.grab(CAPTURE_REGION))
    return cv2.cvtColor(screenshot, cv2.COLOR_RGBA2GRAY)

def find_best_match(captured_area):
    kp1, des1 = sift.detectAndCompute(captured_area, None)
    
    matches = bf.knnMatch(des1, map_descriptors, k=2)
    
    good_matches = [m for m, n in matches if m.distance < 0.85 * n.distance]
    
    if len(good_matches) > 20:
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([map_keypoints[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        
        M, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        h, w = captured_area.shape
        pts = np.float32([[0, 0], [0, h-1], [w-1, h-1], [w-1, 0]]).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, M)
    else:
        return None

def find_player_position():
    global map_image
    if map_image is None:
        map_image = load_map_image(MAP_IMAGE_PATH)
        if map_image is None:
            return None

    captured_area = capture_screen()
    matched_region = find_best_match(captured_area)
    
    if matched_region is not None:
        center = np.mean(matched_region, axis=0).reshape(-1)
        
        # Convert coordinates to FA11y's coordinate system
        x = int(center[0] * WIDTH / map_image.shape[1] + ROI_START_ORIG[0])
        y = int(center[1] * HEIGHT / map_image.shape[0] + ROI_START_ORIG[1])
        
        return (x, y)
    else:
        return None

# Initialize the map image
load_map_image(MAP_IMAGE_PATH)
