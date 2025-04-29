"""
Unified player position, direction, and navigation module for FA11y
Combines functionality from:
- player_location.py: Core position detection functions
- ppi.py: Position detection from minimap
- minimap_direction.py: Direction detection from minimap
- coordinate_utils.py: Coordinate utility functions
"""
import cv2
import numpy as np
import pyautogui
import time
import configparser
import threading
import os
from mss import mss
from accessible_output2.outputs.auto import Auto
from lib.utilities import read_config, get_config_boolean

# Initialize speaker
speaker = Auto()

# ============= CONSTANTS =============
# Core constants for screen regions
ROI_START_ORIG = (524, 84)    # Top-left of detection region
ROI_END_ORIG = (1390, 1010)   # Bottom-right of detection region
SCALE_FACTOR = 4              # Scale factor for image processing
MIN_AREA = 1008               # Minimum player icon area
MAX_AREA = 1386               # Maximum player icon area

# Minimap constants
MINIMAP_START = (1735, 154)   # Minimap top-left coordinates
MINIMAP_END = (1766, 184)     # Minimap bottom-right coordinates
MINIMAP_MIN_AREA = 800        # Minimum minimap icon area
MINIMAP_MAX_AREA = 1100       # Maximum minimap icon area

# PPI (Player Position Information) constants
PPI_CAPTURE_REGION = {"top": 20, "left": 1600, "width": 300, "height": 300}

# Width and height of the detection region
WIDTH, HEIGHT = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]

# ============= CORE DETECTION FUNCTIONS =============
def find_triangle_tip(contour, center_mass):
    """Find the tip of a triangular shape (player direction indicator)
    
    Args:
        contour: OpenCV contour of the player icon
        center_mass: Center of mass of the contour
        
    Returns:
        The coordinates of the triangle tip, or None if not found
    """
    # Get minimum area bounding triangle
    triangle = cv2.minEnclosingTriangle(contour)[1]
    if triangle is None or len(triangle) < 3:
        return None

    # Convert triangle points to integer coordinates
    points = triangle.reshape(-1, 2).astype(np.int32)
    
    # Calculate pairwise distances between all vertices
    distances = np.zeros((3, 3))
    for i in range(3):
        for j in range(3):
            distances[i, j] = np.linalg.norm(points[i] - points[j])
            
    # The tip should be the vertex with largest total distance to other vertices
    total_distances = np.sum(distances, axis=1)
    tip_idx = np.argmax(total_distances)
    
    return points[tip_idx]

def find_player_icon_location():
    """Simplified function that only returns location without direction
    
    Returns:
        tuple: (x, y) coordinates of player icon, or None if not found
    """
    location, _ = find_player_icon_location_with_direction()
    return location

def find_player_icon_location_with_direction():
    """Find both player location and direction using improved detection method
    
    Returns:
        tuple: ((x, y), angle) of player icon and direction, or (None, None) if not found
    """
    # Capture and upscale screenshot
    screenshot = np.array(pyautogui.screenshot(region=(
        ROI_START_ORIG[0],
        ROI_START_ORIG[1],
        ROI_END_ORIG[0] - ROI_START_ORIG[0],
        ROI_END_ORIG[1] - ROI_START_ORIG[1]
    )))
    
    screenshot_large = cv2.resize(screenshot, None, fx=SCALE_FACTOR, fy=SCALE_FACTOR, 
                                interpolation=cv2.INTER_LINEAR)
    
    # Extract white pixels
    white_mask = cv2.inRange(screenshot_large, (253, 253, 253), (255, 255, 255))
    contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for contour in contours:
        area = cv2.contourArea(contour)
        if MIN_AREA < area < MAX_AREA:
            M = cv2.moments(contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                center_mass = np.array([cx, cy])
                
                # Find tip using triangle method
                tip_point = find_triangle_tip(contour, center_mass)
                if tip_point is not None:
                    # Calculate angle using the tip
                    direction_vector = tip_point - center_mass
                    angle = np.degrees(np.arctan2(-direction_vector[1], direction_vector[0]))
                    angle = (90 - angle) % 360
                    
                    # Convert coordinates back to original scale and add ROI offset
                    real_cx = cx // SCALE_FACTOR + ROI_START_ORIG[0]
                    real_cy = cy // SCALE_FACTOR + ROI_START_ORIG[1]
                    
                    print(f"Player icon located at: ({real_cx}, {real_cy}), facing angle: {angle:.1f}°")
                    return (real_cx, real_cy), angle
    
    print("Player icon not found")
    return None, None

# ============= MINIMAP DIRECTION DETECTION =============
def find_minimap_icon_direction():
    """Find the player's facing direction from the minimap icon
    
    Returns:
        tuple: (cardinal_direction, angle) or (None, None) if not found
    """
    # Capture the minimap area
    screenshot = np.array(pyautogui.screenshot(region=(
        MINIMAP_START[0],
        MINIMAP_START[1],
        MINIMAP_END[0] - MINIMAP_START[0],
        MINIMAP_END[1] - MINIMAP_START[1]
    )))
    
    # Resize the screenshot to match the scale
    screenshot_large = cv2.resize(screenshot, None, fx=SCALE_FACTOR, fy=SCALE_FACTOR,
                                interpolation=cv2.INTER_LINEAR)
    
    # Extract white pixels
    white_mask = cv2.inRange(screenshot_large, (253, 253, 253), (255, 255, 255))
    contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    print("Searching for icon in minimap...")
    for contour in contours:
        area = cv2.contourArea(contour)
        if MINIMAP_MIN_AREA < area < MINIMAP_MAX_AREA:
            M = cv2.moments(contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                center_mass = np.array([cx, cy])
                
                # Find tip using triangle method
                tip_point = find_triangle_tip(contour, center_mass)
                if tip_point is not None:
                    # Calculate angle using the tip
                    direction_vector = tip_point - center_mass
                    angle = np.degrees(np.arctan2(-direction_vector[1], direction_vector[0]))
                    angle = (90 - angle) % 360
                    
                    cardinal_direction = get_cardinal_direction(angle)
                    print(f"Found icon facing {cardinal_direction} at {angle:.1f}°")
                    return cardinal_direction, angle
    
    print("No valid minimap icon found")
    return None, None

def speak_minimap_direction():
    """Announce the player's current direction using the minimap icon"""
    direction, angle = find_minimap_icon_direction()
    if direction and angle is not None:
        message = f"Facing {direction} at {angle:.0f} degrees"
        print(message)
        speaker.speak(message)
    else:
        message = "Unable to determine direction from minimap"
        print(message)
        speaker.speak(message)

# ============= ANGLE AND DIRECTION UTILITIES =============
def get_angle_and_direction(vector):
    """Convert a vector to angle and cardinal direction
    
    Args:
        vector: 2D vector [x, y]
        
    Returns:
        tuple: (angle, cardinal_direction)
    """
    angle = np.degrees(np.arctan2(-vector[1], vector[0]))
    angle = (90 - angle) % 360  # Adjust to start from North (0 degrees) and increase clockwise
    return angle, get_cardinal_direction(angle)

def get_cardinal_direction(angle):
    """Convert angle to cardinal direction
    
    Args:
        angle: Angle in degrees (0-360)
        
    Returns:
        str: Cardinal direction (North, Northeast, etc.)
    """
    directions = ['North', 'Northeast', 'East', 'Southeast', 'South', 'Southwest', 'West', 'Northwest']
    return directions[int((angle + 22.5) % 360 // 45)]

def get_relative_direction(player_angle, poi_angle):
    """Get the relative direction from player to POI
    
    Args:
        player_angle: Player's facing angle in degrees
        poi_angle: Angle to POI in degrees
        
    Returns:
        str: Relative direction description
    """
    if player_angle is None:
        return "unknown direction"
    
    angle_diff = (poi_angle - player_angle + 360) % 360
    
    if angle_diff < 22.5 or angle_diff >= 337.5:
        return "in front"
    elif 22.5 <= angle_diff < 67.5:
        return "in front and to the right"
    elif 67.5 <= angle_diff < 112.5:
        return "to the right"
    elif 112.5 <= angle_diff < 157.5:
        return "behind and to the right"
    elif 157.5 <= angle_diff < 202.5:
        return "behind"
    elif 202.5 <= angle_diff < 247.5:
        return "behind and to the left"
    elif 247.5 <= angle_diff < 292.5:
        return "to the left"
    else:  # 292.5 <= angle_diff < 337.5
        return "in front and to the left"

# ============= POSITION DESCRIPTION FUNCTIONS =============
def get_quadrant(x, y, width, height):
    """Determine which quadrant a point is in
    
    Args:
        x, y: Coordinates to check
        width, height: Dimensions of the area
        
    Returns:
        int: Quadrant index (0-3)
    """
    mid_x, mid_y = width // 2, height // 2
    return (1 if x >= mid_x else 0) + (2 if y >= mid_y else 0)

def get_position_in_quadrant(x, y, quad_width, quad_height):
    """Get more detailed position within a quadrant
    
    Args:
        x, y: Coordinates to check
        quad_width, quad_height: Dimensions of the quadrant
        
    Returns:
        str: Position description (e.g., "top-left", "center")
    """
    third_x, third_y = quad_width // 3, quad_height // 3
    
    vertical = "top" if y < third_y else "bottom" if y > 2 * third_y else ""
    horizontal = "left" if x < third_x else "right" if x > 2 * third_x else ""
    
    if vertical and horizontal:
        return f"{vertical}-{horizontal}"
    elif vertical or horizontal:
        return vertical or horizontal
    else:
        return "center"

def get_player_position_description(location, poi_name=None, poi_location=None, player_angle=None):
    """Generate a comprehensive description of the player's position
    
    Args:
        location: Player's location coordinates
        poi_name: Name of a point of interest (optional)
        poi_location: Location of the POI (optional)
        player_angle: Player's facing angle (optional)
        
    Returns:
        str: Description of the player's position
    """
    if location is None:
        return "Player position unknown"
        
    x, y = location
    x, y = x - ROI_START_ORIG[0], y - ROI_START_ORIG[1]
    width, height = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]
    quadrant = get_quadrant(x, y, width, height)
    position_in_quadrant = get_position_in_quadrant(x, y, width // 2, height // 2)
    
    quadrant_names = ["top-left", "top-right", "bottom-left", "bottom-right"]
    base_description = f"Player is in the {position_in_quadrant} of the {quadrant_names[quadrant]} quadrant"
    
    if poi_name and poi_location and player_angle is not None:
        poi_info = calculate_poi_info(location, player_angle, poi_location)
        poi_description = generate_poi_message(poi_name, player_angle, poi_info)
        return f"{base_description}. {poi_description}"
    
    return base_description

def calculate_poi_info(player_location, player_angle, poi_location):
    """Calculate information about a POI relative to the player
    
    Args:
        player_location: Player's location coordinates
        player_angle: Player's facing angle
        poi_location: POI location coordinates
        
    Returns:
        tuple: (distance, poi_angle, cardinal_direction, relative_direction)
    """
    if player_location is None:
        return None, None, None, "unknown"
    
    poi_vector = np.array(poi_location) - np.array(player_location)
    distance = np.linalg.norm(poi_vector) * 2.65
    poi_angle, cardinal_direction = get_angle_and_direction(poi_vector)
    
    relative_direction = get_relative_direction(player_angle, poi_angle) if player_angle is not None else "unknown"
    
    return distance, poi_angle, cardinal_direction, relative_direction

def generate_poi_message(poi_name, player_angle, poi_info):
    """Generate a message describing a POI's position relative to the player
    
    Args:
        poi_name: Name of the POI
        player_angle: Player's facing angle
        poi_info: Tuple of (distance, poi_angle, cardinal_direction, relative_direction)
        
    Returns:
        str: Message describing the POI relative to the player
    """
    config = read_config()
    simplify = get_config_boolean(config, 'SimplifySpeechOutput', False)
    
    distance, poi_angle, cardinal_direction, relative_direction = poi_info
    
    if distance is None:
        return f"Pinged {poi_name}, player position unknown."

    if simplify:
        if player_angle is None:
            return f"{poi_name} {int(distance)} meters {cardinal_direction}"
        else:
            return f"{poi_name} {int(distance)} meters {relative_direction} at {poi_angle:.0f} degrees"
    else:
        if player_angle is None:
            message = f"{poi_name} is {int(distance)} meters away"
            if cardinal_direction:
                message += f", {cardinal_direction}"
            if poi_angle is not None:
                message += f" at {poi_angle:.0f} degrees"
            message += ". Player direction not found."
        else:
            player_cardinal = get_cardinal_direction(player_angle)
            is_facing = abs((poi_angle - player_angle + 180) % 360 - 180) <= 20

            if is_facing:
                message = f"Facing {poi_name} {int(distance)} meters away, "
            else:
                message = f"{poi_name} {int(distance)} meters away {relative_direction}, "

            message += f"{cardinal_direction} at {poi_angle:.0f} degrees, "
            message += f"facing {player_cardinal} at {player_angle:.0f} degrees"
        
        return message

# ============= PPI (MAP POSITION DETECTION) =============
class MapManager:
    """Manages map data and matching for position detection"""
    
    def __init__(self):
        self.current_map = None
        self.current_image = None
        self.current_keypoints = None
        self.current_descriptors = None
        
        # Initialize SIFT feature detector
        self.sift = cv2.SIFT_create()
        self.bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
        self.sct_lock = threading.Lock()
    
    def switch_map(self, map_name: str) -> bool:
        """Switch to a different map
        
        Args:
            map_name: Name of the map to switch to
            
        Returns:
            bool: True if successful, False otherwise
        """
        if self.current_map == map_name:
            return True
        
        map_file = f"maps/{map_name}.png"
        if not os.path.exists(map_file):
            print(f"Error: Map file {map_file} not found")
            return False
        
        self.current_map = map_name
        self.current_image = cv2.imread(map_file, cv2.IMREAD_GRAYSCALE)
        self.current_keypoints, self.current_descriptors = self.sift.detectAndCompute(
            self.current_image, None
        )
        return True

# Initialize the map manager
map_manager = MapManager()

def capture_map_screen():
    """Capture the map area of the screen
    
    Returns:
        np.ndarray: Screenshot of the map area
    """
    with map_manager.sct_lock:
        with mss() as sct:
            screenshot = np.array(sct.grab(PPI_CAPTURE_REGION))
    return cv2.cvtColor(screenshot, cv2.COLOR_RGBA2GRAY)

def find_best_match(captured_area):
    """Find the best match between captured area and current map
    
    Args:
        captured_area: Screenshot to match against the map
        
    Returns:
        np.ndarray: Transformed points or None if no match found
    """
    kp1, des1 = map_manager.sift.detectAndCompute(captured_area, None)
    
    # Check if features were found in the captured area
    if des1 is None or len(des1) == 0:
        print("No features found in captured area")
        return None
    
    matches = map_manager.bf.knnMatch(des1, map_manager.current_descriptors, k=2)
    
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
    """Find player position using the map
    
    Returns:
        tuple: (x, y) coordinates or None if not found
    """
    # Get current map from config
    config = configparser.ConfigParser()
    config.read('config.txt')
    current_map = config.get('POI', 'current_map', fallback='main')
    
    # Switch map if needed
    if not map_manager.switch_map(current_map):
        return None
    
    captured_area = capture_map_screen()
    matched_region = find_best_match(captured_area)
    
    if matched_region is not None:
        center = np.mean(matched_region, axis=0).reshape(-1)
        
        x = int(center[0] * WIDTH / map_manager.current_image.shape[1] + ROI_START_ORIG[0])
        y = int(center[1] * HEIGHT / map_manager.current_image.shape[0] + ROI_START_ORIG[1])
        
        return (x, y)
    return None

# ============= PUBLIC API FUNCTIONS =============
def get_current_coordinates():
    """Get the player's current coordinates
    
    Returns:
        tuple: (x, y) coordinates or None if not found
    """
    return find_player_icon_location()

def get_current_position_and_direction():
    """Get the player's current position and direction
    
    Returns:
        tuple: ((x, y), angle) or (None, None) if not found
    """
    return find_player_icon_location_with_direction()

def get_current_position_from_map():
    """Get the player's current position using the map
    
    Returns:
        tuple: (x, y) coordinates or None if not found
    """
    return find_player_position()

def get_current_direction():
    """Get the player's current direction from the minimap
    
    Returns:
        tuple: (cardinal_direction, angle) or (None, None) if not found
    """
    return find_minimap_icon_direction()

def announce_current_direction():
    """Announce the player's current direction"""
    speak_minimap_direction()

def describe_player_position(poi_name=None, poi_location=None):
    """Describe the player's current position
    
    Args:
        poi_name: Name of a POI (optional)
        poi_location: Location of the POI (optional)
        
    Returns:
        str: Description of the player's position
    """
    location, angle = get_current_position_and_direction()
    return get_player_position_description(location, poi_name, poi_location, angle)

# ============= DETECTION METHOD SELECTION FUNCTIONS =============
def get_player_info(use_ppi=False):
    """Get player location and angle using either PPI or normal icon detection
    
    Args:
        use_ppi: Whether to use PPI (map matching) or direct icon detection
        
    Returns:
        tuple: ((x, y), angle) or (None, None) if not found
    """
    if use_ppi:
        player_location = find_player_position()
        if player_location is None:
            return None, None
        _, player_angle = find_minimap_icon_direction()
        return player_location, player_angle
    else:
        return find_player_icon_location_with_direction()

def get_position_with_fallback():
    """Get player position using all available methods with fallback
    
    Returns:
        tuple: (x, y) coordinates or None if not found
    """
    # Try direct icon detection first
    position = find_player_icon_location()
    
    # If that fails, try map-based detection
    if position is None:
        position = find_player_position()
        
    return position