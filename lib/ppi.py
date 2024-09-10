import cv2
import numpy as np
from mss import mss
import os
from threading import Lock

# Constants
ROI_START_ORIG, ROI_END_ORIG = (590, 190), (1490, 1010)
CAPTURE_REGION = {"top": 10, "left": 1610, "width": 300, "height": 300}
MAP_IMAGE_PATH = "map.jpg"

# Pre-compute constants
WIDTH, HEIGHT = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]
HALF_WIDTH, HALF_HEIGHT = WIDTH // 2, HEIGHT // 2
THIRD_WIDTH, THIRD_HEIGHT = HALF_WIDTH // 3, HALF_HEIGHT // 3

# Pre-compute direction vectors and labels
DIRECTION_VECTORS = np.array([[0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1]])
COMPASS_BRACKETS = np.array([22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5])
COMPASS_LABELS = ['behind', 'behind and to the right', 'to the right', 'in front and to the right', 
                  'in front', 'in front and to the left', 'to the left', 'behind and to the left']
QUADRANT_NAMES = ["top-left", "top-right", "bottom-left", "bottom-right"]

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
    
    good_matches = [m for m, n in matches if m.distance < 0.75 * n.distance]
    
    if len(good_matches) > 10:
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

def get_angle_and_direction(vector):
    angle = np.degrees(np.arctan2(-vector[1], vector[0]))
    angle = (90 - angle) % 360  # Adjust to start from North (0 degrees) and increase clockwise
    return angle, QUADRANT_NAMES[int((angle + 22.5) % 360 // 45)]

def get_relative_direction(player_direction, poi_vector):
    if isinstance(player_direction, str):
        player_vector = DIRECTION_VECTORS[['North', 'Northeast', 'East', 'Southeast', 'South', 'Southwest', 'West', 'Northwest'].index(player_direction)]
    else:
        player_vector = player_direction

    angle = np.degrees(np.arctan2(np.cross(poi_vector, player_vector), np.dot(poi_vector, player_vector)))
    angle = (-angle + 360) % 360  # Reverse the angle and ensure it's between 0 and 360

    return COMPASS_LABELS[np.searchsorted(COMPASS_BRACKETS, angle)]

def get_player_position_description(location, poi_name=None, poi_location=None):
    x, y = np.array(location) - ROI_START_ORIG
    quadrant = (x >= HALF_WIDTH) + 2 * (y >= HALF_HEIGHT)
    
    x_in_quadrant, y_in_quadrant = x % HALF_WIDTH, y % HALF_HEIGHT
    vertical = np.select([y_in_quadrant < THIRD_HEIGHT, y_in_quadrant > 2 * THIRD_HEIGHT], ["top", "bottom"], "")
    horizontal = np.select([x_in_quadrant < THIRD_WIDTH, x_in_quadrant > 2 * THIRD_WIDTH], ["left", "right"], "")
    
    position_in_quadrant = f"{vertical}-{horizontal}" if vertical and horizontal else (vertical or horizontal or "center")
    
    base_description = f"Player is in the {position_in_quadrant} of the {QUADRANT_NAMES[quadrant]} quadrant"
    
    if poi_name and poi_location:
        poi_vector = np.array(poi_location) - np.array(location)
        distance = np.linalg.norm(poi_vector) * 2.65
        angle, cardinal_direction = get_angle_and_direction(poi_vector)
        relative_direction = get_relative_direction([0, -1], poi_vector)  # Assuming player is facing North
        
        poi_description = f"{poi_name} is {relative_direction} {int(distance)} meters, and is {cardinal_direction} at {angle:.0f} degrees"
        return f"{base_description}. {poi_description}"
    
    return base_description

# Initialize the map image
load_map_image(MAP_IMAGE_PATH)
