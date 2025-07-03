"""
Unified player position, direction, navigation detection module for FA11y
"""
import cv2
import numpy as np
import pyautogui
import time
import threading
import os
from mss import mss
from typing import Optional, Tuple
from accessible_output2.outputs.auto import Auto
from lib.utilities import read_config, get_config_boolean, get_config_float
from lib.object_finder import optimized_finder, OBJECT_CONFIGS
from lib.spatial_audio import SpatialAudio
from lib.mouse import smooth_move_mouse
from lib.custom_poi_handler import update_poi_handler
from lib.background_checks import monitor

# Initialize speaker
speaker = Auto()

# Initialize spatial audio for POI sound
spatial_poi = SpatialAudio('sounds/poi.ogg')

pyautogui.FAILSAFE = False

# Core constants for screen regions
ROI_START_ORIG = (524, 84)
ROI_END_ORIG = (1390, 1010)
SCALE_FACTOR = 4
MIN_AREA = 1008
MAX_AREA = 1386

# Minimap constants
MINIMAP_START = (1735, 154)
MINIMAP_END = (1766, 184)
MINIMAP_MIN_AREA = 800
MINIMAP_MAX_AREA = 1100

# PPI constants
PPI_CAPTURE_REGION = {"top": 20, "left": 1600, "width": 300, "height": 300}

# Detection region dimensions
WIDTH, HEIGHT = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]

# Icon detection constants
GAME_OBJECTS = [(name.replace('_', ' ').title(), "0", "0") for name in OBJECT_CONFIGS.keys()]
SPECIAL_POIS = [("Safe Zone", "0", "0"), ("Closest", "0", "0"), ("Closest Game Object", "0", "0")]

def find_triangle_tip(contour, center_mass):
    """Find the tip of a triangular shape (player direction indicator)"""
    triangle = cv2.minEnclosingTriangle(contour)[1]
    if triangle is None or len(triangle) < 3:
        return None

    points = triangle.reshape(-1, 2).astype(np.int32)
    
    distances = np.zeros((3, 3))
    for i in range(3):
        for j in range(3):
            distances[i, j] = np.linalg.norm(points[i] - points[j])
            
    total_distances = np.sum(distances, axis=1)
    tip_idx = np.argmax(total_distances)
    
    return points[tip_idx]

def find_player_icon_location():
    """Return player location without direction"""
    location, _ = find_player_icon_location_with_direction()
    return location

def find_player_icon_location_with_direction():
    """Find both player location and direction"""
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
            screenshot = screenshot_rgba
    except Exception as e:
        print(f"Player icon capture error: {e}")
        return None, None

    screenshot_large = cv2.resize(screenshot, None, fx=SCALE_FACTOR, fy=SCALE_FACTOR, 
                                interpolation=cv2.INTER_LINEAR)
    
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
                
                tip_point = find_triangle_tip(contour, center_mass)
                if tip_point is not None:
                    direction_vector = tip_point - center_mass
                    angle = np.degrees(np.arctan2(-direction_vector[1], direction_vector[0]))
                    angle = (90 - angle) % 360
                    
                    real_cx = cx // SCALE_FACTOR + ROI_START_ORIG[0]
                    real_cy = cy // SCALE_FACTOR + ROI_START_ORIG[1]
                    
                    return (real_cx, real_cy), angle
    
    return None, None

def find_minimap_icon_direction():
    """Find the player's facing direction from the minimap icon"""
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
        print(f"Minimap capture error: {e}")
        return None, None

    screenshot_large = cv2.resize(screenshot, None, fx=SCALE_FACTOR, fy=SCALE_FACTOR,
                                interpolation=cv2.INTER_LINEAR)
    
    white_mask = cv2.inRange(screenshot_large, (253, 253, 253), (255, 255, 255))
    contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for contour in contours:
        area = cv2.contourArea(contour)
        if MINIMAP_MIN_AREA < area < MINIMAP_MAX_AREA:
            M = cv2.moments(contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                center_mass = np.array([cx, cy])
                
                tip_point = find_triangle_tip(contour, center_mass)
                if tip_point is not None:
                    direction_vector = tip_point - center_mass
                    angle = np.degrees(np.arctan2(-direction_vector[1], direction_vector[0]))
                    angle = (90 - angle) % 360
                    
                    cardinal_direction = get_cardinal_direction(angle)
                    return cardinal_direction, angle
    
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

def get_angle_and_direction(vector):
    """Convert a vector to angle and cardinal direction"""
    angle = np.degrees(np.arctan2(-vector[1], vector[0]))
    angle = (90 - angle) % 360
    return angle, get_cardinal_direction(angle)

def get_cardinal_direction(angle):
    """Convert angle to cardinal direction"""
    directions = ['North', 'Northeast', 'East', 'Southeast', 'South', 'Southwest', 'West', 'Northwest']
    return directions[int((angle + 22.5) % 360 // 45)]

def get_relative_direction(player_angle, poi_angle):
    """Get the relative direction from player to POI"""
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
    else:
        return "in front and to the left"

def get_quadrant(x, y, width, height):
    """Determine which quadrant a point is in"""
    mid_x, mid_y = width // 2, height // 2
    quad = 0
    if x >= mid_x:
        quad +=1
    if y >= mid_y:
        quad +=2
    return quad

def get_position_in_quadrant(x, y, quad_width, quad_height):
    """Get more detailed position within a quadrant"""
    third_x, third_y = quad_width // 3, quad_height // 3
    
    vertical = "top" if y < third_y else "bottom" if y > 2 * third_y else "middle"
    horizontal = "left" if x < third_x else "right" if x > 2 * third_x else "center"
    
    if vertical == "middle" and horizontal == "center":
        return "center"
    elif vertical == "middle":
        return horizontal
    elif horizontal == "center":
        return vertical
    else:
        return f"{vertical}-{horizontal}"

def get_player_position_description(location, poi_name=None, poi_location=None, player_angle=None):
    """Generate a comprehensive description of the player's position"""
    if location is None:
        return "Player position unknown"
        
    x_rel_roi = location[0] - ROI_START_ORIG[0]
    y_rel_roi = location[1] - ROI_START_ORIG[1]
    
    roi_width = ROI_END_ORIG[0] - ROI_START_ORIG[0]
    roi_height = ROI_END_ORIG[1] - ROI_START_ORIG[1]
    
    quadrant_idx = get_quadrant(x_rel_roi, y_rel_roi, roi_width, roi_height)
    
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
    """Calculate information about a POI relative to the player"""
    if player_location is None:
        return None, None, None, "unknown"
    
    poi_vector = np.array(poi_location) - np.array(player_location)
    distance = np.linalg.norm(poi_vector) * 2.65
    poi_angle, cardinal_direction = get_angle_and_direction(poi_vector)
    
    relative_direction = get_relative_direction(player_angle, poi_angle) if player_angle is not None else "unknown"
    
    return distance, poi_angle, cardinal_direction, relative_direction

def generate_poi_message(poi_name, player_angle, poi_info):
    """Generate a message describing a POI's position relative to the player"""
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
            angle_diff_to_poi = abs((poi_angle - player_angle + 180) % 360 - 180)
            is_facing = angle_diff_to_poi <= 20

            if is_facing:
                message = f"Facing {poi_name}, {int(distance)} meters away, "
            else:
                message = f"{poi_name} {int(distance)} meters away {relative_direction}, "

            message += f"{cardinal_direction} at {poi_angle:.0f} degrees. "
            message += f"You are facing {player_cardinal} at {player_angle:.0f} degrees."
        
        return message

class MapManager:
    """Manages map data and matching for position detection"""
    
    def __init__(self):
        self.current_map = None
        self.current_image = None
        self.current_keypoints = None
        self.current_descriptors = None
        
        self.sift = cv2.SIFT_create()
        self.bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
        self.sct_lock = threading.Lock()
        
        # Add caching to reduce map loading prints
        self.map_load_cache = {}
    
    def switch_map(self, map_name: str) -> bool:
        """Switch to a different map with caching"""
        if self.current_map == map_name:
            return True
        
        # Check cache first
        if map_name in self.map_load_cache:
            cache_entry = self.map_load_cache[map_name]
            self.current_map = map_name
            self.current_image = cache_entry['image']
            self.current_keypoints = cache_entry['keypoints']
            self.current_descriptors = cache_entry['descriptors']
            return True
        
        map_file = f"maps/{map_name}.png"
        if not os.path.exists(map_file):
            print(f"Map file not found: {map_file}")
            return False
        
        self.current_map = map_name
        self.current_image = cv2.imread(map_file, cv2.IMREAD_GRAYSCALE)
        self.current_keypoints, self.current_descriptors = self.sift.detectAndCompute(
            self.current_image, None
        )
        
        # Cache the loaded map
        self.map_load_cache[map_name] = {
            'image': self.current_image,
            'keypoints': self.current_keypoints,
            'descriptors': self.current_descriptors
        }
        
        return True

map_manager = MapManager()

def capture_map_screen():
    """Capture the map area of the screen"""
    with map_manager.sct_lock:
        with mss() as sct:
            screenshot_rgba = np.array(sct.grab(PPI_CAPTURE_REGION))
    return cv2.cvtColor(screenshot_rgba, cv2.COLOR_BGRA2GRAY)

def find_best_match(captured_area):
    """Find the best match between captured area and current map"""
    kp1, des1 = map_manager.sift.detectAndCompute(captured_area, None)
    
    if des1 is None or len(des1) == 0:
        return None
    if map_manager.current_descriptors is None or len(map_manager.current_descriptors) == 0:
        return None
    
    matches = map_manager.bf.knnMatch(des1, map_manager.current_descriptors, k=2)
    
    good_matches = []
    for match_pair in matches:
        if len(match_pair) == 2:
            m, n = match_pair
            if m.distance < 0.75 * n.distance:
                good_matches.append(m)
    
    MIN_MATCHES = 10
    if len(good_matches) > MIN_MATCHES:
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([map_manager.current_keypoints[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        
        M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        
        if M is None:
            return None
            
        if not np.all(np.isfinite(M)):
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

def find_player_position():
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
    
    captured_area = capture_map_screen()
    matched_region = find_best_match(captured_area)
    
    if matched_region is not None:
        center = np.mean(matched_region, axis=0).reshape(-1)
        
        x = int(center[0] * (WIDTH / map_manager.current_image.shape[1]) + ROI_START_ORIG[0])
        y = int(center[1] * (HEIGHT / map_manager.current_image.shape[0]) + ROI_START_ORIG[1])
        
        return (x, y)
    return None

def find_closest_poi(icon_location, poi_list):
    """Find closest POI to the player"""
    if not icon_location or not poi_list:
        return None, None
    
    distances = []
    for poi_data in poi_list:
        poi_name = poi_data[0]
        try:
            coord_x = int(float(poi_data[1]))
            coord_y = int(float(poi_data[2]))
            distance = np.linalg.norm(
                np.array(icon_location) - np.array([coord_x, coord_y])
            ) * 2.65
            distances.append((poi_name, (coord_x, coord_y), distance))
        except (ValueError, TypeError, IndexError):
            continue
            
    if not distances:
        return None, None
        
    closest = min(distances, key=lambda x: x[2])
    return closest[0], closest[1]

def find_closest_game_object(player_location: Tuple[int, int], use_ppi: bool = False) -> Optional[Tuple[str, Tuple[int, int]]]:
    """
    Find the closest game object to the player using object detection.
    
    Args:
        player_location: Player's current position (x, y)
        use_ppi: Whether to use PPI for detection
        
    Returns:
        Tuple of (object_name, (x, y)) or None if no objects found
    """
    try:
        if not player_location or not OBJECT_CONFIGS:
            return None
        
        # Get all object names
        object_names = list(OBJECT_CONFIGS.keys())
        
        # Try to find objects
        found_objects = optimized_finder.find_all_objects(object_names, use_ppi)
        
        if not found_objects:
            return None
        
        # Calculate distances and find closest
        closest_object = None
        min_distance = float('inf')
        
        for obj_name, obj_coords in found_objects.items():
            distance = np.linalg.norm(
                np.array(player_location) - np.array(obj_coords)
            )
            
            if distance < min_distance:
                min_distance = distance
                # Convert internal name to display name
                display_name = obj_name.replace('_', ' ').title()
                closest_object = (display_name, obj_coords)
        
        return closest_object
        
    except Exception as e:
        print(f"Error finding closest game object: {e}")
        return None

def load_config():
    """Load configuration from file"""
    config = read_config()
    selected_poi_str = config.get('POI', 'selected_poi', fallback='none,0,0')
    parts = selected_poi_str.split(',')
    if len(parts) == 3:
        return parts[0].strip(), parts[1].strip(), parts[2].strip()
    return 'none', '0', '0'

def find_game_object_with_fallback(object_name: str, use_ppi: bool = False) -> Optional[Tuple[int, int]]:
    """Find game object with fallback between PPI and fullscreen detection"""
    object_key = object_name.lower().replace(' ', '_')
    
    result = optimized_finder.find_closest_object(object_key, use_ppi)
    
    if result is None and use_ppi:
        result = optimized_finder.find_closest_object(object_key, False)
        
    return result

def handle_poi_selection(selected_poi_name_from_config, center_mass_screen, use_ppi=False):
    """Handle POI selection process with improved object detection"""
    from lib.guis.poi_selector_gui import POIData
    poi_data_manager = POIData()
    
    config = read_config()
    current_map_id = config.get('POI', 'current_map', fallback='main')
    
    # Try custom POI handler first
    custom_result = update_poi_handler(selected_poi_name_from_config, use_ppi)
    if custom_result[0] is not None and custom_result[1] is not None:
        name, coords = custom_result
        if isinstance(coords[0], str) or isinstance(coords[1], str):
            try:
                coords = (int(float(coords[0])), int(float(coords[1])))
            except ValueError:
                return name, None
        return name, coords

    poi_name_lower = selected_poi_name_from_config.lower()

    if poi_name_lower == 'safe zone':
        # Use new storm monitor system
        from lib.storm_monitor import storm_monitor
        storm_location = storm_monitor.get_current_storm_location()
        return 'Safe Zone', storm_location

    elif poi_name_lower == 'closest':
        if center_mass_screen:
            pois_to_check = []
            if current_map_id == "main":
                pois_to_check.extend(poi_data_manager.main_pois)
            elif current_map_id in poi_data_manager.maps:
                pois_to_check.extend(poi_data_manager.maps[current_map_id].pois)
            else:
                resolved_map_key = None
                for key, map_obj in poi_data_manager.maps.items():
                    if map_obj.name.lower() == current_map_id.lower().replace('_', ' '):
                        resolved_map_key = key
                        break
                if resolved_map_key and resolved_map_key in poi_data_manager.maps:
                     pois_to_check.extend(poi_data_manager.maps[resolved_map_key].pois)

            if not pois_to_check:
                 return "Closest", None
            return find_closest_poi(center_mass_screen, pois_to_check)
        else:
            return "Closest", None
            
    elif poi_name_lower == 'closest landmark':
        if current_map_id == "main":
            if center_mass_screen:
                return find_closest_poi(center_mass_screen, poi_data_manager.landmarks)
            else:
                return "Closest Landmark", None
        else:
            speaker.speak("Closest Landmark is only available on the main map.")
            return "Closest Landmark", None

    elif poi_name_lower == 'closest game object':
        if center_mass_screen:
            closest_obj = find_closest_game_object(center_mass_screen, use_ppi)
            if closest_obj:
                return closest_obj
            else:
                return "Closest Game Object", None
        else:
            return "Closest Game Object", None
            
    else:
        # Check current map's POIs first
        pois_to_search = []
        if current_map_id == "main":
            pois_to_search.extend(poi_data_manager.main_pois)
            pois_to_search.extend(poi_data_manager.landmarks)
        elif current_map_id in poi_data_manager.maps:
             pois_to_search.extend(poi_data_manager.maps[current_map_id].pois)
        else:
            resolved_map_key = None
            for key, map_obj in poi_data_manager.maps.items():
                if map_obj.name.lower() == current_map_id.lower().replace('_', ' '):
                    resolved_map_key = key
                    break
            if resolved_map_key and resolved_map_key in poi_data_manager.maps:
                 pois_to_search.extend(poi_data_manager.maps[resolved_map_key].pois)

        # Search in regular POIs first
        for poi_tuple in pois_to_search:
            if poi_tuple[0].lower() == poi_name_lower:
                try:
                    return poi_tuple[0], (int(float(poi_tuple[1])), int(float(poi_tuple[2])))
                except (ValueError, TypeError):
                    return selected_poi_name_from_config, None
        
        # Check if it's a game object using improved detection
        object_key = poi_name_lower.replace(' ', '_')
        if object_key in OBJECT_CONFIGS or any(obj_name.lower() == poi_name_lower for obj_name, _, _ in GAME_OBJECTS):
            obj_location = optimized_finder.find_closest_object(object_key, use_ppi)
            
            if obj_location:
                proper_name = selected_poi_name_from_config
                for obj_name_cfg, _, _ in GAME_OBJECTS:
                    if obj_name_cfg.lower() == poi_name_lower:
                        proper_name = obj_name_cfg
                        break
                
                return proper_name, obj_location
            else:
                return selected_poi_name_from_config, None

    return selected_poi_name_from_config, None

def perform_poi_actions(poi_data_tuple, center_mass_screen, speak_info=True, use_ppi=False):
    """Perform actions based on POI selection"""
    poi_name, coordinates = poi_data_tuple

    if coordinates and len(coordinates) == 2:
        x, y = coordinates
        try:
            if center_mass_screen and speak_info:
                process_screenshot((int(x), int(y)), poi_name, center_mass_screen, use_ppi)
            elif not speak_info:
                pass
        except ValueError:
            speaker.speak(f"Error: Invalid POI coordinates for {poi_name}")
    else:
        if speak_info:
             speaker.speak(f"{poi_name} location not available for detailed navigation info.")

def process_screenshot(selected_coordinates, poi_name, player_location, use_ppi=False):
    """Process screenshot for POI information"""
    _, player_angle = get_player_info(use_ppi)
                                             
    if player_location is not None:
        poi_info = calculate_poi_info(player_location, player_angle, selected_coordinates)
        message = generate_poi_message(poi_name, player_angle, poi_info)
        print(message)
        speaker.speak(message)

# Initialize a global reference to track the active sound updater
active_sound_updater = None

def play_spatial_poi_sound(player_location, player_angle, poi_location):
    """Play POI sound with real-time spatial audio updates as player turns."""
    global config, active_sound_updater
    
    if active_sound_updater:
        active_sound_updater.stop()
        active_sound_updater = None
    
    if not player_location or not poi_location or player_angle is None:
        return None
    
    config = read_config()
    play_poi_sound_enabled = get_config_boolean(config, 'PlayPOISound', True)
    if not play_poi_sound_enabled or not os.path.exists('sounds/poi.ogg'):
        return None
    
    # Get volume configuration
    master_volume, poi_volume = SpatialAudio.get_volume_from_config(config, 'POIVolume', 'MasterVolume', 1.0)
    spatial_poi.set_master_volume(master_volume)
    spatial_poi.set_individual_volume(poi_volume)
    
    # Calculate distance and relative angle using universal calculation
    distance, relative_angle = SpatialAudio.calculate_distance_and_angle(
        player_location, player_angle, poi_location
    )
    
    # Get volume configuration for distance falloff
    min_volume = get_config_float(config, 'MinimumPOIVolume', 0.05)
    max_volume = get_config_float(config, 'MaximumPOIVolume', 1.0)
    ping_volume_max_distance = get_config_float(config, 'PingVolumeMaxDistance', 100.0)
    
    # Calculate volume based on distance
    distance_for_volume_calc = max(1.0, ping_volume_max_distance)
    volume_factor = 1.0 - min(distance / distance_for_volume_calc, 1.0)
    final_volume = min_volume + (max_volume - min_volume) * volume_factor
    final_volume = np.clip(final_volume, min_volume, max_volume)
    
    # Start playing the sound with new spatial parameters
    spatial_poi.play_audio(
        distance=distance,
        relative_angle=relative_angle,
        volume=final_volume
    )
    
    # Create a new sound updater and store globally
    active_sound_updater = POISoundUpdater(player_location, poi_location, final_volume)
    return active_sound_updater

class POISoundUpdater:
    """Handles real-time updates for POI spatial sound as player turns."""
    
    def __init__(self, player_location, poi_location, volume):
        """Initialize with fixed positions and volume."""
        self.player_location = player_location
        self.poi_location = poi_location
        self.volume = volume
        self.stop_event = threading.Event()
        self.update_thread = None
        self.start_updates()
    
    def start_updates(self):
        """Start the thread that updates panning based on player rotation."""
        self.update_thread = threading.Thread(target=self._update_loop)
        self.update_thread.daemon = True
        self.update_thread.start()
    
    def _update_loop(self):
        """Continuously update panning based on player's current angle."""
        update_interval = 0.1
        
        while not self.stop_event.is_set() and spatial_poi.is_playing:
            try:
                _, current_player_angle = find_minimap_icon_direction()
                
                if current_player_angle is not None:
                    # Use universal spatial positioning
                    distance, relative_angle = SpatialAudio.calculate_distance_and_angle(
                        self.player_location, current_player_angle, self.poi_location
                    )
                    
                    spatial_poi.update_spatial_position(distance, relative_angle, self.volume)
            
            except Exception:
                pass
            
            time.sleep(update_interval)
    
    def stop(self):
        """Stop the update thread."""
        self.stop_event.set()
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=0.5)

def start_icon_detection(use_ppi=False):
    """Start icon detection with universal spatial sound support"""
    config = read_config()
    selected_poi_name_from_config = config.get('POI', 'selected_poi', fallback='none,0,0').split(',')[0].strip()
    
    play_poi_sound_enabled = get_config_boolean(config, 'PlayPOISound', True)
    
    icon_detection_cycle(selected_poi_name_from_config, use_ppi, play_poi_sound_enabled)

def icon_detection_cycle(selected_poi_name, use_ppi, play_poi_sound_enabled=True):
    """Modified icon detection cycle with improved object detection and real-time spatial audio updates."""
    if selected_poi_name.lower() == 'none':
        speaker.speak("No POI selected. Please select a POI first.")
        return

    player_location, player_angle = get_player_info(use_ppi)
    if player_location is None:
        method = "PPI" if use_ppi else "icon detection"
        speaker.speak(f"Could not find player position using {method}")
        play_poi_sound_enabled = False

    poi_data_tuple = handle_poi_selection(selected_poi_name, player_location, use_ppi)
    
    poi_name_resolved, poi_coords_resolved = poi_data_tuple

    if poi_coords_resolved is None:
        speaker.speak(f"{poi_name_resolved} location not available.")
        return

    # Play spatial sound if enabled
    if play_poi_sound_enabled and player_location is not None and player_angle is not None:
        play_spatial_poi_sound(player_location, player_angle, poi_coords_resolved)

    # Handle game object interaction differently for PPI vs fullscreen
    is_game_object = any(obj_name.lower() == selected_poi_name.lower() for obj_name, _, _ in GAME_OBJECTS)
    
    if not use_ppi and not is_game_object:
        pyautogui.moveTo(poi_coords_resolved[0], poi_coords_resolved[1], duration=0.1)
        pyautogui.rightClick(_pause=False)
        time.sleep(0.05)
        pyautogui.click(_pause=False)
    elif not use_ppi and is_game_object:
        pyautogui.moveTo(poi_coords_resolved[0], poi_coords_resolved[1], duration=0.1)

    perform_poi_actions(poi_data_tuple, player_location, speak_info=False, use_ppi=use_ppi)
    
    config = read_config()
    auto_turn_enabled = get_config_boolean(config, 'AutoTurn', False)
    auto_turn_success = False
    
    if auto_turn_enabled:
        if not use_ppi:
            pyautogui.press('escape')
            time.sleep(0.1)
        if player_location is not None:
            auto_turn_success = auto_turn_towards_poi(player_location, poi_coords_resolved, poi_name_resolved)
        else:
            speaker.speak("Cannot auto-turn, player location unknown.")
    
    _, latest_player_angle = get_player_info(use_ppi)
                                                    
    final_direction_source, final_angle_for_speech = find_minimap_icon_direction()
    if final_angle_for_speech is None:
        final_angle_for_speech = latest_player_angle if latest_player_angle is not None else player_angle

    speak_auto_turn_result(poi_name_resolved, player_location, final_angle_for_speech, poi_coords_resolved, auto_turn_enabled, auto_turn_success)

def speak_auto_turn_result(poi_name, player_location, player_angle, poi_location, auto_turn_enabled, success):
    """Speak auto-turn result"""
    if not isinstance(poi_location, tuple) or len(poi_location) != 2:
        speaker.speak(f"Error with {poi_name} location data.")
        return

    poi_info = calculate_poi_info(player_location, player_angle, poi_location)
    message = generate_poi_message(poi_name, player_angle, poi_info)

    if auto_turn_enabled:
        if success:
            pass
        else:
            if player_location is not None:
                 message = f"Failed to fully auto-turn towards {poi_name}. {message}"
    
    print(message)
    speaker.speak(message)

def auto_turn_towards_poi(player_location, poi_location, poi_name):
    """Automatically turn player towards POI"""
    max_attempts = 20
    base_turn_sensitivity_factor = 0.8
    angle_threshold = 10
    
    config = read_config()
    turn_sensitivity = get_config_int(config, 'TurnSensitivity', 75)
    turn_delay = get_config_float(config, 'TurnDelay', 0.01)
    turn_steps = get_config_int(config, 'TurnSteps', 5)

    for attempts in range(max_attempts):
        current_direction_str, current_angle_deg = find_minimap_icon_direction()
        if current_direction_str is None or current_angle_deg is None:
            if attempts < 3:
                time.sleep(0.1)
                continue
            else:
                speaker.speak("Cannot determine direction for auto-turn.")
                return False
        
        poi_vector = np.array(poi_location) - np.array(player_location)
        target_poi_angle_deg = (90 - np.degrees(np.arctan2(-poi_vector[1], poi_vector[0]))) % 360
        
        angle_difference = (target_poi_angle_deg - current_angle_deg + 180) % 360 - 180
        
        if abs(angle_difference) <= angle_threshold:
            return True
        
        turn_magnitude_mickeys = int(min(abs(angle_difference) / 180.0 * turn_sensitivity * 2.0, turn_sensitivity) * base_turn_sensitivity_factor)
        turn_magnitude_mickeys = max(5, turn_magnitude_mickeys)

        dx_turn = turn_magnitude_mickeys if angle_difference > 0 else -turn_magnitude_mickeys
        
        smooth_move_mouse(dx_turn, 0, turn_delay, turn_steps)
        time.sleep(0.05 + turn_delay * turn_steps)

    return False

def get_current_coordinates():
    """Get the player's current coordinates"""
    return find_player_icon_location()

def get_current_position_and_direction():
    """Get the player's current position and direction"""
    return find_player_icon_location_with_direction()

def get_current_position_from_map():
    """Get the player's current position using the map"""
    return find_player_position()

def get_current_direction():
    """Get the player's current direction from the minimap"""
    return find_minimap_icon_direction()

def announce_current_direction():
    """Announce the player's current direction"""
    speak_minimap_direction()

def describe_player_position(poi_name=None, poi_location=None):
    """Describe the player's current position"""
    location, angle = get_current_position_and_direction()
    return get_player_position_description(location, poi_name, poi_location, angle)

def get_player_info(use_ppi=False):
    """Get player location and angle using either PPI or normal icon detection"""
    player_location = None
    player_angle = None

    if use_ppi:
        player_location = find_player_position()
        if player_location is not None:
            _, player_angle = find_minimap_icon_direction()
    else:
        player_location, player_angle = find_player_icon_location_with_direction()
    
    if player_angle is None:
        _, player_angle_fallback = find_minimap_icon_direction()
        if player_angle_fallback is not None:
            player_angle = player_angle_fallback
            
    return player_location, player_angle

def get_position_with_fallback():
    """Get player position using all available methods with fallback"""
    position = find_player_icon_location()
    
    if position is None:
        position = find_player_position()
        
    return position

def check_for_pixel():
    """Check if the pixel at a specific location is white or (60, 61, 80)"""
    try:
        return pyautogui.pixelMatchesColor(1877, 50, (255, 255, 255), tolerance=10) or \
               pyautogui.pixelMatchesColor(1877, 50, (60, 61, 80), tolerance=10)
    except Exception:
        return False

def get_config_int(config, key, fallback=None):
    """Get an integer from config"""
    from lib.utilities import get_config_int as util_get_config_int
    return util_get_config_int(config, key, fallback)

def cleanup_object_detection():
    """Clean up object detection resources"""
    optimized_finder.cleanup()