"""
Unified player position, direction, navigation, and storm detection module for FA11y
Combines functionality from:
- player_position.py: Core position and direction detection
- storm.py: Storm detection on the map
- icon.py: Icon detection and POI navigation
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
from lib.utilities import read_config, get_config_boolean, get_config_float
from lib.object_finder import OBJECT_CONFIGS, find_closest_object
from lib.spatial_audio import SpatialAudio
from lib.mouse import smooth_move_mouse
from lib.custom_poi_handler import update_poi_handler
from lib.background_checks import monitor # Added for map open check

# Initialize speaker
speaker = Auto()

# Initialize spatial audio for POI sound
spatial_poi = SpatialAudio('sounds/poi.ogg')

pyautogui.FAILSAFE = False

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

# Storm detection constants
STORM_MIN_SHAPE_SIZE = 150000
STORM_ROI_START = (621, 182)
STORM_ROI_END = (1342, 964)
STORM_ROI_START_SCALED = tuple(4 * np.array(STORM_ROI_START))
STORM_ROI_END_SCALED = tuple(4 * np.array(STORM_ROI_END))
STORM_TARGET_COLOR = np.array([165, 29, 146]) # BGR format for OpenCV
STORM_COLOR_DISTANCE = 70
STORM_LOWER_BOUND = np.maximum(0, STORM_TARGET_COLOR - STORM_COLOR_DISTANCE)
STORM_UPPER_BOUND = np.minimum(255, STORM_TARGET_COLOR + STORM_COLOR_DISTANCE)
STORM_ROI_SLICE = np.s_[STORM_ROI_START_SCALED[1]:STORM_ROI_END_SCALED[1], STORM_ROI_START_SCALED[0]:STORM_ROI_END_SCALED[0]]


# Icon detection constants
GAME_OBJECTS = [(name.replace('_', ' ').title(), "0", "0") for name in OBJECT_CONFIGS.keys()]
SPECIAL_POIS = [("Safe Zone", "0", "0"), ("Closest", "0", "0")]

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
    try:
        screenshot_rgba = np.array(pyautogui.screenshot(region=(
            ROI_START_ORIG[0],
            ROI_START_ORIG[1],
            ROI_END_ORIG[0] - ROI_START_ORIG[0],
            ROI_END_ORIG[1] - ROI_START_ORIG[1]
        )))
        if screenshot_rgba.shape[2] == 4:
            screenshot = cv2.cvtColor(screenshot_rgba, cv2.COLOR_RGBA2RGB)
        else:
            screenshot = screenshot_rgba # Assuming it's RGB already
    except Exception as e:
        print(f"Error capturing player icon screenshot: {e}")
        return None, None

    screenshot_large = cv2.resize(screenshot, None, fx=SCALE_FACTOR, fy=SCALE_FACTOR, 
                                interpolation=cv2.INTER_LINEAR)
    
    # Extract white pixels
    white_mask = cv2.inRange(screenshot_large, (253, 253, 253), (255, 255, 255)) # Assuming RGB
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
                    
                    # print(f"Player icon located at: ({real_cx}, {real_cy}), facing angle: {angle:.1f}°")
                    return (real_cx, real_cy), angle
    
    # print("Player icon not found")
    return None, None

# ============= MINIMAP DIRECTION DETECTION =============
def find_minimap_icon_direction():
    """Find the player's facing direction from the minimap icon
    
    Returns:
        tuple: (cardinal_direction, angle) or (None, None) if not found
    """
    # Capture the minimap area
    try:
        screenshot_rgba = np.array(pyautogui.screenshot(region=(
            MINIMAP_START[0],
            MINIMAP_START[1],
            MINIMAP_END[0] - MINIMAP_START[0],
            MINIMAP_END[1] - MINIMAP_START[1]
        )))
        if screenshot_rgba.shape[2] == 4:
             screenshot = cv2.cvtColor(screenshot_rgba, cv2.COLOR_RGBA2RGB)
        else:
            screenshot = screenshot_rgba
    except Exception as e:
        print(f"Error capturing minimap screenshot: {e}")
        return None, None

    # Resize the screenshot to match the scale
    screenshot_large = cv2.resize(screenshot, None, fx=SCALE_FACTOR, fy=SCALE_FACTOR,
                                interpolation=cv2.INTER_LINEAR)
    
    # Extract white pixels
    white_mask = cv2.inRange(screenshot_large, (253, 253, 253), (255, 255, 255)) # Assuming RGB
    contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # print("Searching for icon in minimap...")
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
                    # print(f"Found icon facing {cardinal_direction} at {angle:.1f}°")
                    return cardinal_direction, angle
    
    # print("No valid minimap icon found")
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
        int: Quadrant index (0-3) -> 0:TL, 1:TR, 2:BL, 3:BR
    """
    mid_x, mid_y = width // 2, height // 2
    quad = 0
    if x >= mid_x: # Right half
        quad +=1
    if y >= mid_y: # Bottom half
        quad +=2
    return quad


def get_position_in_quadrant(x, y, quad_width, quad_height):
    """Get more detailed position within a quadrant
    
    Args:
        x, y: Coordinates to check (relative to quadrant's top-left)
        quad_width, quad_height: Dimensions of the quadrant
        
    Returns:
        str: Position description (e.g., "top-left", "center")
    """
    # This function assumes x,y are relative to the quadrant's origin,
    # but the way it's used in get_player_position_description,
    # x,y are relative to the full map ROI and quad_width/height are half of full.
    # This needs adjustment if x,y are not made relative to the quadrant start.
    # For now, let's assume x,y are already adjusted for the specific quadrant.

    third_x, third_y = quad_width // 3, quad_height // 3
    
    vertical = "top" if y < third_y else "bottom" if y > 2 * third_y else "middle" # Changed "" to "middle"
    horizontal = "left" if x < third_x else "right" if x > 2 * third_x else "center" # Changed "" to "center"
    
    if vertical == "middle" and horizontal == "center":
        return "center"
    elif vertical == "middle":
        return horizontal
    elif horizontal == "center":
        return vertical
    else:
        return f"{vertical}-{horizontal}"

def get_player_position_description(location, poi_name=None, poi_location=None, player_angle=None):
    """Generate a comprehensive description of the player's position
    
    Args:
        location: Player's location coordinates (full screen)
        poi_name: Name of a point of interest (optional)
        poi_location: Location of the POI (full screen) (optional)
        player_angle: Player's facing angle (optional)
        
    Returns:
        str: Description of the player's position
    """
    if location is None:
        return "Player position unknown"
        
    # Make x, y relative to the map ROI's top-left corner
    x_rel_roi = location[0] - ROI_START_ORIG[0]
    y_rel_roi = location[1] - ROI_START_ORIG[1]
    
    roi_width = ROI_END_ORIG[0] - ROI_START_ORIG[0]
    roi_height = ROI_END_ORIG[1] - ROI_START_ORIG[1]
    
    quadrant_idx = get_quadrant(x_rel_roi, y_rel_roi, roi_width, roi_height)
    
    # For position_in_quadrant, x and y need to be relative to the quadrant's start
    quad_width_half = roi_width // 2
    quad_height_half = roi_height // 2
    
    x_in_quad = x_rel_roi % quad_width_half
    y_in_quad = y_rel_roi % quad_height_half
    
    position_in_quadrant_str = get_position_in_quadrant(x_in_quad, y_in_quad, quad_width_half, quad_height_half)
    
    quadrant_names = ["top-left", "top-right", "bottom-left", "bottom-right"]
    base_description = f"Player is in the {position_in_quadrant_str} of the {quadrant_names[quadrant_idx]} quadrant"
    
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
    distance = np.linalg.norm(poi_vector) * 2.65 # Calibration factor for meters
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
    
    if distance is None: # This implies player_location was None in calculate_poi_info
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
            # Check if player is roughly facing the POI
            angle_diff_to_poi = abs((poi_angle - player_angle + 180) % 360 - 180)
            is_facing = angle_diff_to_poi <= 20 # Threshold for "facing"

            if is_facing:
                message = f"Facing {poi_name}, {int(distance)} meters away, "
            else:
                message = f"{poi_name} {int(distance)} meters away {relative_direction}, "

            message += f"{cardinal_direction} at {poi_angle:.0f} degrees. " # Added period for clarity
            message += f"You are facing {player_cardinal} at {player_angle:.0f} degrees." # Changed to "You are facing"
        
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
    with map_manager.sct_lock: # Ensure thread-safe access to mss if it's shared
        with mss() as sct:
            screenshot_rgba = np.array(sct.grab(PPI_CAPTURE_REGION))
    return cv2.cvtColor(screenshot_rgba, cv2.COLOR_BGRA2GRAY) # Convert BGRA from MSS to GRAY

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
        # print("No features found in captured area") # Reduce console spam
        return None
    if map_manager.current_descriptors is None or len(map_manager.current_descriptors) == 0:
        # print("No features loaded for the current map") # Reduce console spam
        return None
    
    matches = map_manager.bf.knnMatch(des1, map_manager.current_descriptors, k=2)
    
    # Filter good matches using ratio test
    good_matches = []
    for match_pair in matches: # Ensure k=2 produced two matches
        if len(match_pair) == 2:
            m, n = match_pair
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
            # print("Could not compute homography") # Reduce spam
            return None
            
        # Check if homography is valid
        if not np.all(np.isfinite(M)):
            # print("Invalid homography matrix (contains inf/nan)") # Reduce spam
            return None
            
        try:
            h, w = captured_area.shape
            pts = np.float32([[0, 0], [0, h-1], [w-1, h-1], [w-1, 0]]).reshape(-1, 1, 2)
            transformed_pts = cv2.perspectiveTransform(pts, M)
            
            # Validate transformed points
            if np.all(np.isfinite(transformed_pts)):
                return transformed_pts
            else:
                # print("Invalid transformed points (contains inf/nan)") # Reduce spam
                return None
                
        except cv2.error as e:
            # print(f"OpenCV error during perspective transform: {e}") # Reduce spam
            return None
    else:
        # print(f"Not enough good matches: {len(good_matches)} < {MIN_MATCHES}") # Reduce spam
        return None

def find_player_position():
    """Find player position using the map
    
    Returns:
        tuple: (x, y) coordinates or None if not found
    """
    # Get current map from config
    config = read_config() # Use utility to read config
    current_map_id = config.get('POI', 'current_map', fallback='main')
    
    # Construct the map filename based on convention (e.g., "map_og.png")
    # If current_map_id is 'main', filename is 'main.png'
    # Otherwise, it's 'map_{current_map_id}.png'
    map_filename_to_load = current_map_id if current_map_id == 'main' else f"map_{current_map_id}"

    if not map_manager.switch_map(map_filename_to_load):
        return None
    
    captured_area = capture_map_screen()
    matched_region = find_best_match(captured_area)
    
    if matched_region is not None:
        center = np.mean(matched_region, axis=0).reshape(-1)
        
        # Scale matched center to original map ROI dimensions
        x = int(center[0] * (WIDTH / map_manager.current_image.shape[1]) + ROI_START_ORIG[0])
        y = int(center[1] * (HEIGHT / map_manager.current_image.shape[0]) + ROI_START_ORIG[1])
        
        return (x, y)
    return None

# ============= STORM DETECTION FUNCTIONS =============
def get_storm_screenshot():
    """Get screenshot for storm detection
    
    Returns:
        numpy.ndarray: Screenshot image (RGB format)
    """
    pyautogui.moveTo(1900, 1000, duration=0.1, tween=pyautogui.easeInOutQuad) # Move mouse out of the way
    screenshot_rgba = np.array(pyautogui.screenshot())
    return cv2.cvtColor(screenshot_rgba, cv2.COLOR_RGBA2RGB) # Convert to RGB

def process_storm_image(screenshot_rgb):
    """Process screenshot for storm detection
    
    Args:
        screenshot_rgb: Screenshot to process (RGB format)
        
    Returns:
        numpy.ndarray: Processed image (BGR for OpenCV processing)
    """
    # OpenCV expects BGR, so convert if it's RGB
    screenshot_bgr = cv2.cvtColor(screenshot_rgb, cv2.COLOR_RGB2BGR)
    return cv2.resize(
        screenshot_bgr, 
        None, 
        fx=4, 
        fy=4, 
        interpolation=cv2.INTER_LINEAR
    )


def detect_storm(roi_color_bgr):
    """Detect storm in the given ROI
    
    Args:
        roi_color_bgr: Region of interest to detect storm in (BGR format)
        
    Returns:
        tuple: Storm center coordinates or None if not found
    """
    mask = cv2.inRange(roi_color_bgr, STORM_LOWER_BOUND, STORM_UPPER_BOUND)
    mask = cv2.bitwise_not(mask) # Invert mask, storm is usually the largest non-purple area
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for contour in contours:
        area = cv2.contourArea(contour)
        if area > STORM_MIN_SHAPE_SIZE:
            return process_storm_contour(roi_color_bgr, contour, area)
    return None

def process_storm_contour(roi_color_bgr, contour, area):
    """Process storm contour to calculate center of mass
    
    Args:
        roi_color_bgr: ROI image (BGR)
        contour: Storm contour
        area: Contour area
        
    Returns:
        tuple: Storm center coordinates (full screen) or None
    """
    M = cv2.moments(contour)
    if M["m00"] == 0: # Avoid division by zero
        return None
        
    cX = int(M["m10"] / M["m00"]) # Center X within the scaled ROI
    cY = int(M["m01"] / M["m00"]) # Center Y within the scaled ROI
    
    # Translate to original screen coordinates (relative to full screen)
    # cX, cY are coordinates within the *scaled* STORM_ROI_SLICE
    # So, we need to add the start of the *scaled* STORM_ROI, then divide by scale factor
    # and add the start of the *original* STORM_ROI
    
    # This calculation seems off. cX, cY are already in the coordinate system of the `roi_color_bgr`
    # which is `screenshot[STORM_ROI_SLICE]`.
    # So, `cX` and `cY` are relative to the top-left of `STORM_ROI_START_SCALED`.
    
    # Convert cX, cY (from scaled ROI) to full screen coordinates
    center_mass_screen_x = (cX // SCALE_FACTOR) + STORM_ROI_START[0]
    center_mass_screen_y = (cY // SCALE_FACTOR) + STORM_ROI_START[1]
    center_mass_screen = (center_mass_screen_x, center_mass_screen_y)

    # Check if detected storm center is too close to screen center
    screen_width, screen_height = pyautogui.size()
    screen_center_x, screen_center_y = screen_width // 2, screen_height // 2

    if abs(center_mass_screen[0] - screen_center_x) <= 5 and \
       abs(center_mass_screen[1] - screen_center_y) <= 5:
        speaker.speak("No storm detected")
        print("Storm center is too close to screen center, likely no storm.")
        return None 
        
    print(f"Storm position (full screen): {center_mass_screen}")
    return center_mass_screen


def start_storm_detection():
    """Start storm detection
    
    Returns:
        tuple: Storm center coordinates or None if not found
    """
    # This function as a loop is problematic if called synchronously.
    # It should perform one detection attempt.
    screenshot_rgb = get_storm_screenshot()
    processed_image_bgr = process_storm_image(screenshot_rgb)
    roi_color_bgr = processed_image_bgr[STORM_ROI_SLICE] # Apply slice to BGR image
    
    storm_coords = detect_storm(roi_color_bgr)
    return storm_coords


# ============= ICON DETECTION AND POI NAVIGATION FUNCTIONS =============
def find_closest_poi(icon_location, poi_list):
    """Find closest POI to the player
    
    Args:
        icon_location: Player's location
        poi_list: List of POIs to check [(name, x, y), ...]
        
    Returns:
        tuple: (closest_poi_name, poi_location) or (None, None) if not found
    """
    if not icon_location or not poi_list:
        return None, None
    
    distances = []
    for poi_data in poi_list: # poi_data can be (name, x_str, y_str)
        poi_name = poi_data[0]
        try:
            coord_x = int(float(poi_data[1]))
            coord_y = int(float(poi_data[2]))
            distance = np.linalg.norm(
                np.array(icon_location) - np.array([coord_x, coord_y])
            ) * 2.65 # Calibration factor
            distances.append((poi_name, (coord_x, coord_y), distance))
        except (ValueError, TypeError, IndexError):
            print(f"Warning: Could not parse coordinates for POI: {poi_name}")
            continue
            
    if not distances:
        return None, None
        
    closest = min(distances, key=lambda x: x[2]) # No default needed if we check distances list first
    return closest[0], closest[1]


def load_config():
    """Load configuration from file
    
    Returns:
        tuple: (poi_name, x, y) from configuration
    """
    config = read_config()
    selected_poi_str = config.get('POI', 'selected_poi', fallback='none,0,0')
    parts = selected_poi_str.split(',')
    if len(parts) == 3:
        return parts[0].strip(), parts[1].strip(), parts[2].strip()
    return 'none', '0', '0'


def handle_poi_selection(selected_poi_name_from_config: str, center_mass_screen, use_ppi=False):
    """Handle POI selection process
    
    Args:
        selected_poi_name_from_config: Name of selected POI from config
        center_mass_screen: Player's location
        use_ppi: Whether to use PPI for position detection
        
    Returns:
        tuple: (poi_name, poi_location) or (poi_name, None) if not found
    """
    # print(f"Handling POI selection for: {selected_poi_name_from_config}")
    
    from lib.guis.poi_selector_gui import POIData # Import here to avoid circular dependency
    poi_data_manager = POIData() # Get the singleton instance
    
    config = read_config()
    current_map_id = config.get('POI', 'current_map', fallback='main')
    
    # Try custom POI handler first
    custom_result = update_poi_handler(selected_poi_name_from_config, use_ppi)
    if custom_result[0] is not None and custom_result[1] is not None:
        # Ensure coordinates are integers if they are strings
        name, coords = custom_result
        if isinstance(coords[0], str) or isinstance(coords[1], str):
            try:
                coords = (int(float(coords[0])), int(float(coords[1])))
            except ValueError:
                print(f"Error converting custom POI coords for {name}: {coords}")
                return name, None
        return name, coords

    poi_name_lower = selected_poi_name_from_config.lower()

    if poi_name_lower == 'safe zone':
        # print("Detecting safe zone")
        map_was_opened_by_script = False
        if not monitor.map_open:
            pyautogui.press('m')
            time.sleep(0.1) # Increased for reliability
            map_was_opened_by_script = True
            # Add a check here if map actually opened, if possible. For now, assume it did.
            # e.g. by checking a pixel color unique to the open map screen.

        storm_location = start_storm_detection()

        if map_was_opened_by_script:
            # Check if map is still open before trying to close it.
            # This requires `monitor.map_open` to be updated quickly or a direct pixel check.
            # For simplicity, just press escape.
            pyautogui.press('escape')
            time.sleep(0.05)

        return 'Safe Zone', storm_location

    elif poi_name_lower == 'closest':
        # print(f"Finding closest POI in map: {current_map_id}")
        if center_mass_screen:
            pois_to_check = []
            if current_map_id == "main":
                pois_to_check.extend(poi_data_manager.main_pois)
            elif current_map_id in poi_data_manager.maps: # Use the map_id from config
                pois_to_check.extend(poi_data_manager.maps[current_map_id].pois)
            else: # Check if it's a display name that needs to be resolved
                resolved_map_key = None
                for key, map_obj in poi_data_manager.maps.items():
                    if map_obj.name.lower() == current_map_id.lower().replace('_', ' '):
                        resolved_map_key = key
                        break
                if resolved_map_key and resolved_map_key in poi_data_manager.maps:
                     pois_to_check.extend(poi_data_manager.maps[resolved_map_key].pois)

            if not pois_to_check:
                 print(f"No POIs available for map '{current_map_id}' to find closest.")
                 return "Closest", None
            return find_closest_poi(center_mass_screen, pois_to_check)
        else:
            # print("Could not determine player location for finding closest POI")
            return "Closest", None
            
    elif poi_name_lower == 'closest landmark':
        # print("Finding closest landmark (only on main map)")
        if current_map_id == "main":
            if center_mass_screen:
                return find_closest_poi(center_mass_screen, poi_data_manager.landmarks)
            else:
                # print("Could not determine player location for finding closest landmark")
                return "Closest Landmark", None
        else:
            print("Closest Landmark is only available on the main map.")
            speaker.speak("Closest Landmark is only available on the main map.")
            return "Closest Landmark", None
            
    else: # Specific POI name
        # Check current map's POIs first
        pois_to_search = []
        if current_map_id == "main":
            pois_to_search.extend(poi_data_manager.main_pois)
            pois_to_search.extend(poi_data_manager.landmarks)
        elif current_map_id in poi_data_manager.maps:
             pois_to_search.extend(poi_data_manager.maps[current_map_id].pois)
        else: # Resolve display name
            resolved_map_key = None
            for key, map_obj in poi_data_manager.maps.items():
                if map_obj.name.lower() == current_map_id.lower().replace('_', ' '):
                    resolved_map_key = key
                    break
            if resolved_map_key and resolved_map_key in poi_data_manager.maps:
                 pois_to_search.extend(poi_data_manager.maps[resolved_map_key].pois)


        for poi_tuple in pois_to_search:
            if poi_tuple[0].lower() == poi_name_lower:
                try:
                    return poi_tuple[0], (int(float(poi_tuple[1])), int(float(poi_tuple[2])))
                except (ValueError, TypeError):
                    print(f"Error parsing coordinates for {poi_tuple[0]}")
                    return selected_poi_name_from_config, None
        
        # If not found in primary lists, check game objects (these don't have real coords, usually)
        for obj_name_cfg, _, _ in GAME_OBJECTS: # GAME_OBJECTS stores (name, "0", "0")
            if obj_name_cfg.lower() == poi_name_lower:
                # This means it's a game object, find its actual location on screen if applicable
                icon_path_tuple = OBJECT_CONFIGS.get(poi_name_lower.replace(' ', '_'))
                if icon_path_tuple:
                    icon_path, threshold = icon_path_tuple
                    obj_location = find_closest_object(icon_path, threshold)
                    if obj_location:
                        return obj_name_cfg, obj_location
                return obj_name_cfg, None # Game object selected, but may not be findable on screen now

    # print(f"POI '{selected_poi_name_from_config}' not found in map data.")
    return selected_poi_name_from_config, None


def perform_poi_actions(poi_data_tuple, center_mass_screen, speak_info=True, use_ppi=False):
    """Perform actions based on POI selection
    
    Args:
        poi_data_tuple: (poi_name, coordinates) tuple
        center_mass_screen: Player's location
        speak_info: Whether to speak information about POI
        use_ppi: Whether to use PPI for position detection
    """
    poi_name, coordinates = poi_data_tuple
    # print(f"Performing actions for POI: {poi_name}, Coordinates: {coordinates}")

    if coordinates and len(coordinates) == 2:
        x, y = coordinates
        try:
            if center_mass_screen and speak_info: # center_mass_screen is player_location
                process_screenshot((int(x), int(y)), poi_name, center_mass_screen, use_ppi)
            elif not speak_info:
                # print(f"Clicked on {poi_name}. Info will be spoken after auto-turn.")
                pass # Info spoken by speak_auto_turn_result
        except ValueError:
            # print(f"Error: Invalid POI coordinates for {poi_name}: {x}, {y}")
            speaker.speak(f"Error: Invalid POI coordinates for {poi_name}")
    else:
        # This case handles POIs that might not have screen coordinates (like some game objects)
        # or if coordinates were None.
        # If it's a game object without immediate screen coords, auto-turn might not make sense
        # unless find_closest_object gave coords.
        # print(f"POI location for {poi_name} is not set or invalid.")
        if speak_info: # Only speak if we were supposed to.
             speaker.speak(f"{poi_name} location not available for detailed navigation info.")


def process_screenshot(selected_coordinates, poi_name, player_location, use_ppi=False):
    """Process screenshot for POI information
    
    Args:
        selected_coordinates: Coordinates of selected POI
        poi_name: Name of selected POI
        player_location: Player's location
        use_ppi: Whether to use PPI for position detection
    """
    # player_location is already passed, get_player_info was called by caller.
    # We need player_angle.
    _, player_angle = get_player_info(use_ppi) # Re-fetch angle as it might have changed.
                                             # player_location from caller might be slightly stale.
                                             # For consistency, could re-fetch location too or trust caller.
    
    if player_location is not None: # Use the provided player_location
        poi_info = calculate_poi_info(player_location, player_angle, selected_coordinates)
        message = generate_poi_message(poi_name, player_angle, poi_info)
        print(message)
        speaker.speak(message)
    else:
        method = "PPI" if use_ppi else "player icon"
        # print(f"Player location not found using {method}.") # Caller (icon_detection_cycle) handles this.
        # speaker.speak(f"Player location not found using {method}.")


def play_spatial_poi_sound(player_position, player_angle, poi_location):
    """Play spatial POI sound based on relative position
    
    Args:
        player_position: Player's location
        player_angle: Player's facing angle
        poi_location: POI location
    """
    if player_position and poi_location and player_angle is not None:
        # Calculate vector from player to POI
        poi_vector = np.array(poi_location) - np.array(player_position)
        distance = np.linalg.norm(poi_vector) * 2.65 # Calibration factor
        
        # Calculate angle to POI
        poi_angle_rad = np.arctan2(-poi_vector[1], poi_vector[0])
        poi_angle_deg = (90 - np.degrees(poi_angle_rad)) % 360
        
        # Calculate relative angle from player's facing direction
        # Ensure player_angle is also 0-360 with North at 0
        relative_angle = (poi_angle_deg - player_angle + 180) % 360 - 180 # Results in -180 to 180
        
        # Calculate stereo panning based on relative angle
        pan = np.clip(relative_angle / 90, -1, 1) # Pan from -1 (left) to 1 (right)
        left_weight = np.clip((1 - pan) / 2, 0, 1)
        right_weight = np.clip((1 + pan) / 2, 0, 1)
        
        # Get volume settings from config
        config = read_config() # Use utility
        min_volume = get_config_float(config, 'MinimumPOIVolume', 0.05)
        max_volume = get_config_float(config, 'MaximumPOIVolume', 1.0)
        ping_volume_max_distance = get_config_float(config, 'PingVolumeMaxDistance', 100.0) # Use a config value

        # Calculate volume based on distance with new min/max settings
        # Ensure distance_for_volume_calc is not zero to avoid division by zero if ping_volume_max_distance is 0
        distance_for_volume_calc = max(1.0, ping_volume_max_distance) # Avoid division by zero
        
        volume_factor = 1.0 - min(distance / distance_for_volume_calc, 1.0) # Normalized inverse distance
        final_volume = min_volume + (max_volume - min_volume) * volume_factor
        final_volume = np.clip(final_volume, min_volume, max_volume) # Ensure it's within bounds

        # Play the spatial sound
        spatial_poi.play_audio(
            left_weight=left_weight,
            right_weight=right_weight,
            volume=final_volume
        )

def start_icon_detection(use_ppi=False):
    """Start icon detection with universal spatial sound support
    
    Args:
        use_ppi: Whether to use PPI for position detection
    """
    # print("Starting icon detection")
    config = read_config()
    selected_poi_name_from_config = config.get('POI', 'selected_poi', fallback='none,0,0').split(',')[0].strip()
    
    # Load spatial sound configuration
    play_poi_sound_enabled = get_config_boolean(config, 'PlayPOISound', True)
    
    icon_detection_cycle(selected_poi_name_from_config, use_ppi, play_poi_sound_enabled)


def icon_detection_cycle(selected_poi_name, use_ppi, play_poi_sound_enabled=True):
    """Modified icon detection cycle with universal spatial audio support
    
    Args:
        selected_poi_name: Selected POI name (just the name part from config)
        use_ppi: Whether to use PPI for position detection
        play_poi_sound_enabled: Whether to play POI sound
    """
    # print(f"Icon detection cycle started. Selected POI: {selected_poi_name}, Using PPI: {use_ppi}")
    
    if selected_poi_name.lower() == 'none':
        # print("No POI selected.")
        speaker.speak("No POI selected. Please select a POI first.")
        return

    # Get player information
    player_location, player_angle = get_player_info(use_ppi)
    if player_location is None:
        method = "PPI" if use_ppi else "icon detection"
        # print(f"Could not find player position using {method}")
        speaker.speak(f"Could not find player position using {method}")
        # Do not play spatial sound if player location is unknown
        play_poi_sound_enabled = False # Override if player loc unknown

    # Get POI information
    poi_data_tuple = handle_poi_selection(selected_poi_name, player_location, use_ppi)
    # print(f"POI data from handle_poi_selection: {poi_data_tuple}")
    
    poi_name_resolved, poi_coords_resolved = poi_data_tuple

    if poi_coords_resolved is None:
        # print(f"{poi_name_resolved} not located or has no coordinates.")
        speaker.speak(f"{poi_name_resolved} location not available.")
        return

    # Play spatial POI sound if enabled AND player location/angle are known
    if play_poi_sound_enabled and player_location is not None and player_angle is not None:
        play_spatial_poi_sound(player_location, player_angle, poi_coords_resolved)
    elif play_poi_sound_enabled and (player_location is None or player_angle is None):
        # print("Skipping POI sound: Player location or angle unknown.")
        pass


    # Handle clicking for non-PPI mode (map icon interaction)
    if not use_ppi:
        pyautogui.moveTo(poi_coords_resolved[0], poi_coords_resolved[1], duration=0.1) # Added duration
        pyautogui.rightClick(_pause=False)
        time.sleep(0.05) # Small delay after right click
        pyautogui.click(_pause=False) # Left click to confirm ping

    # Perform POI actions (which includes speaking info, but auto-turn might change angle)
    # We will speak the final info AFTER auto-turn. So set speak_info=False here.
    perform_poi_actions(poi_data_tuple, player_location, speak_info=False, use_ppi=use_ppi)
    
    # Handle auto-turning if enabled
    config = read_config()
    auto_turn_enabled = get_config_boolean(config, 'AutoTurn', False)
    auto_turn_success = False # Default to false
    
    if auto_turn_enabled:
        if not use_ppi: # If using map icons, close map before turning
            pyautogui.press('escape')
            time.sleep(0.1)
        if player_location is not None: # Auto-turn requires player location
            auto_turn_success = auto_turn_towards_poi(player_location, poi_coords_resolved, poi_name_resolved)
        else:
            # print("Cannot auto-turn: Player location unknown.")
            speaker.speak("Cannot auto-turn, player location unknown.")
    
    # Get final angle and speak result
    # Re-fetch player angle as it would have changed if auto_turn ran.
    # Player location might also have shifted slightly, but less critical than angle.
    _, latest_player_angle = get_player_info(use_ppi) # Prioritize PPI if it was used, else icon.
                                                    # Or just use find_minimap_icon_direction for angle consistently.
    
    # Consistently use minimap for final direction announcement if available.
    final_direction_source, final_angle_for_speech = find_minimap_icon_direction()
    if final_angle_for_speech is None: # Fallback if minimap fails
        final_angle_for_speech = latest_player_angle if latest_player_angle is not None else player_angle


    speak_auto_turn_result(poi_name_resolved, player_location, final_angle_for_speech, poi_coords_resolved, auto_turn_enabled, auto_turn_success)


def speak_auto_turn_result(poi_name, player_location, player_angle, poi_location, auto_turn_enabled, success):
    """Speak auto-turn result
    
    Args:
        poi_name: Name of selected POI
        player_location: Player's location
        player_angle: Player's facing angle
        poi_location: POI location
        auto_turn_enabled: Whether auto-turn is enabled
        success: Whether auto-turn was successful
    """
    # Ensure poi_location is valid tuple before proceeding
    if not isinstance(poi_location, tuple) or len(poi_location) != 2:
        print(f"Invalid poi_location for {poi_name}: {poi_location}. Cannot generate message.")
        speaker.speak(f"Error with {poi_name} location data.")
        return

    poi_info = calculate_poi_info(player_location, player_angle, poi_location)
    message = generate_poi_message(poi_name, player_angle, poi_info)

    if auto_turn_enabled:
        if success:
            # Message already describes relation, no need to add "Successfully turned"
            pass
        else:
            if player_location is not None: # Only mention failure if turn was attempted
                 message = f"Failed to fully auto-turn towards {poi_name}. {message}"
            # If player_location was None, auto_turn wasn't really attempted. Original message is fine.
    
    print(message)
    speaker.speak(message)


def auto_turn_towards_poi(player_location, poi_location, poi_name):
    """Automatically turn player towards POI
    
    Args:
        player_location: Player's location
        poi_location: POI location
        poi_name: Name of POI
        
    Returns:
        bool: Whether auto-turn was successful
    """
    max_attempts = 20 # Reduced for faster response
    base_turn_sensitivity_factor = 0.8 # Multiplier for turn_sensitivity
    angle_threshold = 10 # Degrees
    
    config = read_config()
    turn_sensitivity = get_config_int(config, 'TurnSensitivity', 75)
    turn_delay = get_config_float(config, 'TurnDelay', 0.01)
    turn_steps = get_config_int(config, 'TurnSteps', 5) # Use config for steps

    for attempts in range(max_attempts):
        current_direction_str, current_angle_deg = find_minimap_icon_direction()
        if current_direction_str is None or current_angle_deg is None:
            # print(f"Unable to determine current direction. Attempt {attempts + 1}/{max_attempts}")
            if attempts < 3 : # Allow a few initial failures
                time.sleep(0.1)
                continue
            else: # Persistent failure
                speaker.speak("Cannot determine direction for auto-turn.")
                return False # Failed to get direction consistently
        
        # Calculate vector from player to POI
        poi_vector = np.array(poi_location) - np.array(player_location)
        # Calculate angle to POI (0 North, clockwise)
        target_poi_angle_deg = (90 - np.degrees(np.arctan2(-poi_vector[1], poi_vector[0]))) % 360
        
        # Calculate angular difference (-180 to 180)
        angle_difference = (target_poi_angle_deg - current_angle_deg + 180) % 360 - 180
        
        # Debug print every few attempts or if close
        # if attempts % 5 == 0 or abs(angle_difference) <= angle_threshold:
            # print(f"Attempt {attempts+1}: Current Angle: {current_angle_deg:.1f}, Target Angle: {target_poi_angle_deg:.1f}, Diff: {angle_difference:.1f}")
        
        if abs(angle_difference) <= angle_threshold:
            # print(f"Successfully turned towards {poi_name}. Current direction: {current_direction_str}")
            return True
        
        # Dynamic turn amount based on difference, scaled by TurnSensitivity
        # Use a fraction of turn_sensitivity for finer control. Maximize at full turn_sensitivity.
        turn_magnitude_mickeys = int(min(abs(angle_difference) / 180.0 * turn_sensitivity * 2.0, turn_sensitivity) * base_turn_sensitivity_factor)
        turn_magnitude_mickeys = max(5, turn_magnitude_mickeys) # Minimum turn to ensure movement

        # Determine turn direction (MICKEYS)
        dx_turn = turn_magnitude_mickeys if angle_difference > 0 else -turn_magnitude_mickeys
        
        smooth_move_mouse(dx_turn, 0, turn_delay, turn_steps)
        time.sleep(0.05 + turn_delay * turn_steps) # Wait for mouse move to complete plus a bit

    # print(f"Failed to turn towards {poi_name} within {angle_threshold} degrees after {max_attempts} attempts.")
    return False


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
    player_location = None
    player_angle = None

    if use_ppi:
        player_location = find_player_position() # This is from map (PPI)
        if player_location is not None:
            _, player_angle = find_minimap_icon_direction() # Angle from minimap is usually more reliable
    else:
        player_location, player_angle = find_player_icon_location_with_direction() # From large map icon
    
    # If angle couldn't be determined by primary method, try minimap as fallback
    if player_angle is None:
        _, player_angle_fallback = find_minimap_icon_direction()
        if player_angle_fallback is not None:
            player_angle = player_angle_fallback
            
    return player_location, player_angle


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

def check_for_pixel():
    """Check if the pixel at a specific location is white or (60, 61, 80)
    This indicates if the full map is open (white pixel) or if PPI can be used (darker pixel on main screen).
    
    Returns:
        bool: True if pixel matches, False otherwise
    """
    try:
        return pyautogui.pixelMatchesColor(1877, 50, (255, 255, 255), tolerance=10) or \
               pyautogui.pixelMatchesColor(1877, 50, (60, 61, 80), tolerance=10)
    except Exception: # Catches errors if screen interaction fails (e.g. on non-Windows)
        return False
