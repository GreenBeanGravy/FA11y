import cv2
import numpy as np
from mss import mss
import os

# Constants from player_location.py
ROI_START_ORIG, ROI_END_ORIG = (590, 190), (1490, 1010)
CAPTURE_REGION = {"top": 10, "left": 1610, "width": 300, "height": 300}
MAP_IMAGE_PATH = "map.jpg"

def load_map_image(path):
    if not os.path.exists(path):
        print(f"Error: Map image not found at {path}")
        return None
    return cv2.imread(path, cv2.IMREAD_GRAYSCALE)

def capture_screen(region):
    with mss() as sct:
        screenshot = np.array(sct.grab(region))
    return cv2.cvtColor(screenshot, cv2.COLOR_RGBA2GRAY)

def find_best_match(captured_area, map_image, sift, bf):
    kp1, des1 = sift.detectAndCompute(captured_area, None)
    kp2, des2 = sift.detectAndCompute(map_image, None)
    
    matches = bf.knnMatch(des1, des2, k=2)
    
    good_matches = [m for m, n in matches if m.distance < 0.75 * n.distance]
    
    if len(good_matches) > 10:
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        
        M, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        h, w = captured_area.shape
        pts = np.float32([[0, 0], [0, h-1], [w-1, h-1], [w-1, 0]]).reshape(-1, 1, 2)
        dst = cv2.perspectiveTransform(pts, M)
        
        return dst
    else:
        return None

def find_player_position():
    map_image = load_map_image(MAP_IMAGE_PATH)
    if map_image is None:
        return None

    sift = cv2.SIFT_create()
    bf = cv2.BFMatcher()
    
    captured_area = capture_screen(CAPTURE_REGION)
    matched_region = find_best_match(captured_area, map_image, sift, bf)
    
    if matched_region is not None:
        center = np.mean(matched_region, axis=0).reshape(-1)
        
        # Convert coordinates to FA11y's coordinate system
        x = int(center[0] * (ROI_END_ORIG[0] - ROI_START_ORIG[0]) / map_image.shape[1] + ROI_START_ORIG[0])
        y = int(center[1] * (ROI_END_ORIG[1] - ROI_START_ORIG[1]) / map_image.shape[0] + ROI_START_ORIG[1])
        
        return (x, y)
    else:
        return None

def get_angle_and_direction(vector):
    angle = np.degrees(np.arctan2(-vector[1], vector[0]))
    angle = (90 - angle) % 360  # Adjust to start from North (0 degrees) and increase clockwise
    return angle, get_cardinal_direction(angle)

def get_cardinal_direction(angle):
    directions = ['North', 'Northeast', 'East', 'Southeast', 'South', 'Southwest', 'West', 'Northwest']
    return directions[int((angle + 22.5) % 360 // 45)]

def get_relative_direction(player_direction, poi_vector):
    if isinstance(player_direction, str):
        # Convert cardinal direction to vector
        direction_to_vector = {
            'North': [0, -1], 'Northeast': [1, -1], 'East': [1, 0], 'Southeast': [1, 1],
            'South': [0, 1], 'Southwest': [-1, 1], 'West': [-1, 0], 'Northwest': [-1, -1]
        }
        player_vector = np.array(direction_to_vector.get(player_direction, [0, -1]))
    else:
        player_vector = player_direction

    angle = np.degrees(np.arctan2(np.cross(poi_vector, player_vector), np.dot(poi_vector, player_vector)))
    angle = (-angle + 360) % 360  # Reverse the angle and ensure it's between 0 and 360

    compass_brackets = [22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5]
    compass_labels = ['behind', 'behind and to the right', 'to the right', 'in front and to the right', 
                      'in front', 'in front and to the left', 'to the left', 'behind and to the left']
    return next((compass_labels[i] for i, val in enumerate(compass_brackets) if angle < val), 'behind')

def get_player_position_description(location, poi_name=None, poi_location=None):
    x, y = location
    x, y = x - ROI_START_ORIG[0], y - ROI_START_ORIG[1]
    width, height = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]
    quadrant = get_quadrant(x, y, width, height)
    position_in_quadrant = get_position_in_quadrant(x, y, width // 2, height // 2)
    
    quadrant_names = ["top-left", "top-right", "bottom-left", "bottom-right"]
    base_description = f"Player is in the {position_in_quadrant} of the {quadrant_names[quadrant]} quadrant"
    
    if poi_name and poi_location:
        poi_vector = np.array(poi_location) - np.array(location)
        distance = np.linalg.norm(poi_vector) * 2.65
        angle, cardinal_direction = get_angle_and_direction(poi_vector)
        relative_direction = get_relative_direction([0, -1], poi_vector)  # Assuming player is facing North
        
        poi_description = f"{poi_name} is {relative_direction} {int(distance)} meters, and is {cardinal_direction} at {angle:.0f} degrees"
        return f"{base_description}. {poi_description}"
    
    return base_description

def get_quadrant(x, y, width, height):
    mid_x, mid_y = width // 2, height // 2
    if x < mid_x:
        return 0 if y < mid_y else 2
    else:
        return 1 if y < mid_y else 3

def get_position_in_quadrant(x, y, quad_width, quad_height):
    third_x, third_y = quad_width // 3, quad_height // 3
    
    vertical = "top" if y < third_y else "bottom" if y > 2 * third_y else ""
    horizontal = "left" if x < third_x else "right" if x > 2 * third_x else ""
    
    if vertical and horizontal:
        return f"{vertical}-{horizontal}"
    elif vertical or horizontal:
        return vertical or horizontal
    else:
        return "center"