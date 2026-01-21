"""
Unified player position, direction, navigation detection module for FA11y
"""
import cv2
import numpy as np
import pyautogui
import time
import threading
import os
import math
from typing import Optional, Tuple
from accessible_output2.outputs.auto import Auto
from lib.utilities.utilities import read_config, get_config_boolean, get_config_float, get_config_int
from lib.detection.dynamic_object_finder import optimized_finder, DYNAMIC_OBJECT_CONFIGS
from lib.detection.ppi import find_player_position as ppi_find_player_position
from lib.detection.coordinate_config import get_minimap_coords


def _ensure_dynamic_icon_paths():
    """Ensure dynamic-object template/icon relative paths include 'icons/' when available."""
    try:
        import os
        from lib.detection import dynamic_object_finder as dyn
        cfgs = getattr(dyn, 'DYNAMIC_OBJECT_CONFIGS', {})
        for _name, cfg in (cfgs or {}).items():
            if not isinstance(cfg, dict):
                continue
            for key in ('icon', 'icon_path', 'template', 'template_path', 'icon_file'):
                p = cfg.get(key)
                if isinstance(p, str) and not os.path.isabs(p):
                    if not os.path.exists(p):
                        alt = os.path.join('icons', p)
                        if os.path.exists(alt):
                            cfg[key] = alt
    except Exception as e:
        print(f"[warn] dynamic icon path normalization failed: {e}")

from lib.utilities.spatial_audio import SpatialAudio
from lib.utilities.mouse import smooth_move_mouse
from lib.managers.custom_poi_manager import update_poi_handler
from lib.monitors.background_monitor import monitor

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

# Minimap constants - now loaded dynamically based on current map
# These are set to default (current season) values and updated when needed
def _get_minimap_constants():
    """Get minimap constants based on current map from config."""
    try:
        from lib.utilities.utilities import read_config
        config = read_config()
        current_map = config.get('POI', 'current_map', fallback='main')
        coords = get_minimap_coords(current_map)
        return coords.start, coords.end, coords.min_area, coords.max_area
    except:
        # Fallback to current season defaults if config unavailable
        return (1745, 144), (1776, 174), 650, 1130

# Default values (will be updated when functions are called)
MINIMAP_START, MINIMAP_END, MINIMAP_MIN_AREA, MINIMAP_MAX_AREA = _get_minimap_constants()

# Detection region dimensions
WIDTH, HEIGHT = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]

# Icon detection constants - updated for new systems
DYNAMIC_OBJECTS = [(name.replace('_', ' ').title(), "0", "0") for name in DYNAMIC_OBJECT_CONFIGS.keys()]
SPECIAL_POIS = [("Safe Zone", "0", "0"), ("Closest", "0", "0")]

# Performance tracking for optimized player position updates
class PlayerPositionTracker:
    """Optimized player position tracker"""
    
    def __init__(self):
        self.last_position = None
        self.last_angle = None
        self.monitoring = False
        self.monitor_thread = None
        self.stop_event = threading.Event()
    
    def get_cached_position(self) -> Optional[Tuple[int, int]]:
        """Get last cached position"""
        return self.last_position
    
    def get_cached_angle(self) -> Optional[float]:
        """Get last cached angle"""
        return self.last_angle
    
    def get_position_and_angle(self, force_update: bool = False) -> Tuple[Optional[Tuple[int, int]], Optional[float]]:
        """Get current position and angle using PPI when minimap is visible"""
        try:
            position = None
            angle = None
            
            # Always try PPI regardless of map check
            position = ppi_find_player_position()
            if position is not None:
                self.last_position = position
                # Get angle from minimap
                _, angle = find_minimap_icon_direction()
            
            if angle is not None:
                self.last_angle = angle
        
        except Exception as e:
            print(f"Error updating player position: {e}")
        
        return self.last_position, self.last_angle
    
    def start_monitoring(self):
        """Start background position monitoring for better performance"""
        if not self.monitoring:
            self.monitoring = True
            self.stop_event.clear()
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop background monitoring"""
        self.monitoring = False
        self.stop_event.set()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        while not self.stop_event.is_set():
            try:
                # Update position in background
                self.get_position_and_angle()
                
                # Get update interval from config
                config = read_config()
                new_interval = get_config_float(config, 'PositionUpdateInterval', 0.5)
                
                # Sleep for the configured interval
                self.stop_event.wait(timeout=new_interval)
                
            except Exception as e:
                print(f"Error in position monitor loop: {e}")
                time.sleep(1.0)

# Global position tracker
position_tracker = PlayerPositionTracker()

def check_for_minimap():
    """Check if minimap is present (map not open) by checking white pixel"""
    try:
        pixel_color = pyautogui.pixel(1883, 49)
        r, g, b = pixel_color
        return (250 <= r <= 255) and (250 <= g <= 255) and (250 <= b <= 255)
    except Exception:
        return False

def check_for_full_map():
    """Check if full map is open by checking yellow pixel"""
    try:
        pixel_color = pyautogui.pixel(66, 66)
        r, g, b = pixel_color
        return (232 <= r <= 262) and (240 <= g <= 270) and (11 <= b <= 41)
    except Exception:
        return False

def handle_closed_map_ppi(poi_name, poi_coords):
    """Handle PPI when map is closed - close map, get position, reopen map"""
    try:
        # Close map
        pyautogui.press('m')
        time.sleep(0.1)
        
        # Wait until we can get player position via PPI
        max_attempts = 1
        player_position = None
        
        for attempt in range(max_attempts):
            # Always try PPI
            player_position = ppi_find_player_position()
            if player_position is not None:
                break
            time.sleep(0.1)
        
        # Reopen map
        pyautogui.press('m')
        time.sleep(0.1)
        
        # Announce the POI
        speaker.speak(f"pinging {poi_name}")
        
        return player_position
        
    except Exception as e:
        print(f"Error handling closed map PPI: {e}")
        return None

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
        # Get current map coordinates
        config = read_config()
        current_map = config.get('POI', 'current_map', fallback='main')
        coords = get_minimap_coords(current_map)
        
        screenshot_rgba = np.array(pyautogui.screenshot(region=(
            coords.start[0],
            coords.start[1],
            coords.end[0] - coords.start[0],
            coords.end[1] - coords.start[1]
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
    
    white_mask = cv2.inRange(screenshot_large, (226, 226, 226), (255, 255, 255))
    contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for contour in contours:
        area = cv2.contourArea(contour)
        if coords.min_area < area < coords.max_area:
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
        poi_description = generate_poi_message(poi_name, player_angle, poi_info, location)
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

def should_use_gameobject_positioning(poi_name: str, config) -> bool:
    """Check if game object positioning should be used for this POI"""
    try:
        # Get the threshold from config
        max_instances_threshold = get_config_int(config, 'MaxInstancesForGameObjectPositioning', 20)
        
        # Check if this looks like a game object (has ID in name)
        import re
        match = re.search(r'(\w+)(\d+)$', poi_name)
        if not match:
            return False
        
        obj_type, obj_id = match.groups()
        
        # Get current map
        current_map = config.get('POI', 'current_map', fallback='main')
        
        # Check instance count for this object type
        from lib.managers.game_object_manager import game_object_manager
        instance_count = game_object_manager.get_object_instance_count(current_map, obj_type)
        
        return instance_count <= max_instances_threshold
        
    except Exception as e:
        print(f"Error checking game object positioning: {e}")
        return False


def get_gameobject_positioning_info(poi_name: str, poi_coordinates: Tuple[float, float], distance: float, config) -> Optional[str]:
    """Get game object positioning information similar to GUI speech"""
    try:
        # Extract object type and ID from POI name
        import re
        match = re.search(r'(\w+)(\d+)$', poi_name)
        if not match:
            return None
        
        obj_type, obj_id = match.groups()
        current_map = config.get('POI', 'current_map', fallback='main')
        
        # Try to import POI data to find closest POI for reference
        try:
            from lib.managers.poi_data_manager import POIData
            poi_data = POIData()
            
            # Get POIs for current map
            if current_map == 'main':
                poi_data._ensure_api_data_loaded()
                pois = poi_data.main_pois
            elif current_map in poi_data.maps:
                poi_data._ensure_map_data_loaded(current_map)
                pois = poi_data.maps[current_map].pois
            else:
                pois = []
        except Exception as e:
            print(f"Could not load POI data: {e}")
            pois = []
        
        if not pois:
            return f"{obj_type} {obj_id} is {int(distance)} meters away"
        
        # Find closest POI
        closest_poi = None
        min_distance = float('inf')
        closest_poi_coords = None
        
        for poi_name_ref, poi_x_str, poi_y_str in pois:
            try:
                poi_coords = (float(poi_x_str), float(poi_y_str))
                from lib.utilities.utilities import calculate_distance
                distance_to_poi = calculate_distance(poi_coordinates, poi_coords)
                
                if distance_to_poi < min_distance:
                    min_distance = distance_to_poi
                    closest_poi = poi_name_ref
                    closest_poi_coords = poi_coords
                    
            except (ValueError, TypeError):
                continue
        
        if closest_poi and min_distance < 1000:
            # Calculate direction from POI to object
            poi_x, poi_y = closest_poi_coords
            dx = poi_coordinates[0] - poi_x
            dy = poi_coordinates[1] - poi_y
            
            # Determine direction
            angle = np.arctan2(dy, dx) * 180 / np.pi
            angle = (angle + 360) % 360
            
            # Convert to 8-direction compass
            if angle < 22.5 or angle >= 337.5:
                direction = "east"
            elif angle < 67.5:
                direction = "southeast"
            elif angle < 112.5:
                direction = "south"
            elif angle < 157.5:
                direction = "southwest"
            elif angle < 202.5:
                direction = "west"
            elif angle < 247.5:
                direction = "northwest"
            elif angle < 292.5:
                direction = "north"
            else:
                direction = "northeast"
            
            return f"{obj_type} {obj_id} is {int(distance)} meters away, {min_distance:.0f} meters {direction} of {closest_poi}"
        else:
            return f"{obj_type} {obj_id} is {int(distance)} meters away"
            
    except Exception as e:
        print(f"Error in game object positioning: {e}")
        return None

def generate_poi_message(poi_name, player_angle, poi_info, player_location=None):
    """Generate a message describing a POI's position relative to the player"""
    config = read_config()
    simplify = get_config_boolean(config, 'SimplifySpeechOutput', False)
    
    distance, poi_angle, cardinal_direction, relative_direction = poi_info
    
    if distance is None:
        return f"Pinged {poi_name}, player position unknown."

    # Check if this is a game object with limited instances for game object positioning info
    gameobject_positioning = should_use_gameobject_positioning(poi_name, config)
    
    if gameobject_positioning and player_location and poi_angle is not None:
        # Calculate POI coordinates from player position, distance, and angle
        try:
            # Convert angle to radians and calculate POI position
            angle_rad = math.radians(poi_angle)
            # Distance is in meters, but we need pixels - divide by 2.65 scale factor
            distance_pixels = distance / 2.65
            
            poi_x = player_location[0] + distance_pixels * math.cos(angle_rad)
            poi_y = player_location[1] - distance_pixels * math.sin(angle_rad)  # Negative because screen Y increases downward
            poi_coords = (poi_x, poi_y)
            
            gameobject_info = get_gameobject_positioning_info(poi_name, poi_coords, distance, config)
            if gameobject_info:
                return gameobject_info
        except Exception as e:
            print(f"Error calculating game object positioning: {e}")

    # Use original logic for other cases
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

def find_player_position():
    """Find player position using the map (wrapper for PPI module) with automatic map check"""
    # Always try PPI
    return ppi_find_player_position()

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

def find_closest_dynamic_object(player_location: Tuple[int, int], use_ppi: bool = False) -> Optional[Tuple[str, Tuple[int, int]]]:
    """
    Find the closest dynamic object to the player using object detection.
    
    Args:
        player_location: Player's current position (x, y)
        use_ppi: Whether to use PPI for detection
        
    Returns:
        Tuple of (object_name, (x, y)) or None if no objects found
    """
    try:
        if not player_location or not DYNAMIC_OBJECT_CONFIGS:
            return None
        
        # Get all object names
        object_names = list(DYNAMIC_OBJECT_CONFIGS.keys())
        
        # Try to find objects
        found_objects = optimized_finder.find_all_dynamic_objects(object_names, use_ppi)
        
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
        print(f"Error finding closest dynamic object: {e}")
        return None

def find_closest_game_object(player_location: Tuple[int, int]) -> Optional[Tuple[str, Tuple[int, int]]]:
    """
    Find the closest game object to the player using the new game objects system.
    
    Args:
        player_location: Player's current position (x, y)
        
    Returns:
        Tuple of (object_name, (x, y)) or None if no objects found
    """
    try:
        from lib.managers.game_object_manager import game_object_manager
        from lib.utilities.utilities import calculate_distance
        
        if not player_location:
            return None
        
        config = read_config()
        current_map = config.get('POI', 'current_map', fallback='main')
        
        # Find all objects within a reasonable radius
        nearby_objects = game_object_manager.find_all_objects_within_radius(
            current_map, player_location, 1000.0  # 1000 meter radius
        )
        
        if not nearby_objects:
            return None
        
        # Find the closest object across all types
        closest_object = None
        min_distance = float('inf')
        
        for obj_type, objects in nearby_objects.items():
            for obj_name, coords, distance in objects:
                if distance < min_distance:
                    min_distance = distance
                    closest_object = (obj_name, coords)
        
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

def find_dynamic_object_with_fallback(object_name: str, use_ppi: bool = False) -> Optional[Tuple[int, int]]:
    """Find dynamic object with fallback between PPI and fullscreen detection"""
    _ensure_dynamic_icon_paths()
    object_key = object_name.lower().replace(' ', '_')
    result = optimized_finder.find_closest_dynamic_object(object_key, use_ppi)
    if result is None and use_ppi:
        result = optimized_finder.find_closest_dynamic_object(object_key, False)
    return result

def handle_poi_selection(selected_poi_name_from_config, center_mass_screen, use_ppi=False):
    """Handle POI selection process with improved object detection and new game objects system"""
    from lib.managers.poi_data_manager import POIData
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
        from lib.monitors.storm_monitor import storm_monitor
        storm_location = storm_monitor.get_current_storm_location()
        return 'Safe Zone', storm_location
    elif poi_name_lower.startswith('closest '):
        # Virtual: Closest <Type> (static game object types)
        type_guess = poi_name_lower.replace('closest ', '', 1).strip()
        try:
            from lib.managers.game_object_manager import game_object_manager
            from lib.detection.match_tracker import match_tracker
            
            config = read_config()
            current_map_id = config.get('POI', 'current_map', fallback='main')
            available = {t.lower(): t for t in game_object_manager.get_available_object_types(current_map_id)}
            
            if center_mass_screen and type_guess in available:
                actual_type = available[type_guess]
                
                # Get visited coordinates for this type to exclude them
                visited_coords = match_tracker.get_visited_coordinates_for_type(actual_type)
                
                # Find nearest unvisited object
                nearest = game_object_manager.find_nearest_unvisited_object_of_type(
                    current_map_id, actual_type, center_mass_screen, visited_coords
                )
                
                if nearest:
                    obj_name, (x, y), distance = nearest
                    return obj_name, (int(x), int(y))
                else:
                    # All objects of this type have been visited
                    return f"Closest {actual_type}", None
                    
        except Exception as e:
            print(f"Closest <Type> resolution failed: {e}")
    elif poi_name_lower == 'closest':
        if center_mass_screen:
            pois_to_check = []
            if current_map_id == "main":
                # Ensure API data is loaded for main map
                poi_data_manager._ensure_api_data_loaded()
                pois_to_check.extend(poi_data_manager.main_pois)
            elif current_map_id in poi_data_manager.maps:
                poi_data_manager._ensure_map_data_loaded(current_map_id)
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
                # Ensure API data is loaded for landmarks
                poi_data_manager._ensure_api_data_loaded()
                return find_closest_poi(center_mass_screen, poi_data_manager.landmarks)
            else:
                return "Closest Landmark", None
        else:
            speaker.speak("Closest Landmark is only available on the main map.")
            return "Closest Landmark", None
    
    # Handle specific game objects by name
    try:
        from lib.managers.game_object_manager import game_object_manager
        
        # Get all game objects for the current map
        game_objects_map = game_object_manager.get_game_objects_for_map(current_map_id)
        
        # Search through all object types for a matching name
        for obj_type, objects in game_objects_map.items():
            for obj_name, x_str, y_str in objects:
                if obj_name.lower() == selected_poi_name_from_config.lower():
                    try:
                        x, y = int(float(x_str)), int(float(y_str))
                        return obj_name, (x, y)
                    except (ValueError, TypeError):
                        continue
    except Exception as e:
        print(f"Error searching game objects: {e}")
    
    # If not found anywhere, return as-is with None coordinates
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
        message = generate_poi_message(poi_name, player_angle, poi_info, player_location)
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

class ContinuousPOIPinger:
    """Handles continuous pinging for a POI with variable interval."""
    def __init__(self, poi_location: Tuple[int, int]):
        self.poi_location = poi_location
        self.stop_event = threading.Event()
        self.thread = None
        self.config = read_config()
        self.min_interval = get_config_float(self.config, 'ContinuousPingMinInterval', 0.5)
        self.max_interval = get_config_float(self.config, 'ContinuousPingMaxInterval', 2.0)
        self.distance_exponent = get_config_float(self.config, 'ContinuousPingDistanceExponent', 1.5)
        self.max_distance_for_interval = get_config_float(self.config, 'PingVolumeMaxDistance', 1000.0)

    def start(self):
        if not self.thread or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._audio_loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def _audio_loop(self):
        while not self.stop_event.is_set():
            player_pos = find_player_position()
            _, player_angle = find_minimap_icon_direction()

            if player_pos and player_angle is not None:
                distance, _ = SpatialAudio.calculate_distance_and_angle(player_pos, player_angle, self.poi_location)
                
                # Play sound
                play_spatial_poi_sound(player_pos, player_angle, self.poi_location)
                
                # Calculate next interval
                distance_ratio = min(distance / self.max_distance_for_interval, 1.0)
                interval_range = self.max_interval - self.min_interval
                # Inverted relationship: closer means smaller ratio, faster interval
                current_interval = self.min_interval + (interval_range * (distance_ratio ** self.distance_exponent))
                
                sleep_time = max(self.min_interval, min(current_interval, self.max_interval))
                
                if self.stop_event.wait(timeout=sleep_time):
                    break
            else:
                # If player position is not available, wait a bit before retrying
                if self.stop_event.wait(timeout=self.max_interval):
                    break

def start_icon_detection(use_ppi=False):
    """Start icon detection with manual trigger handling"""
    config = read_config()
    selected_poi_str = config.get('POI', 'selected_poi', fallback='none,0,0')
    selected_poi_parts = selected_poi_str.split(',')
    selected_poi_name_from_config = selected_poi_parts[0].strip()
    
    play_poi_sound_enabled = get_config_boolean(config, 'PlayPOISound', True)
    
    # Start background position monitoring for better performance
    position_tracker.start_monitoring()
    
    # Check pixel conditions
    minimap_present = check_for_minimap()
    full_map_open = check_for_full_map()
    
    if minimap_present:
        # Minimap present, map not open - just use PPI
        icon_detection_cycle(selected_poi_name_from_config, use_ppi=True, play_poi_sound_enabled=play_poi_sound_enabled)
    elif full_map_open:
        # Full map is open - do M key sequence then use original behavior
        handle_closed_map_ppi(selected_poi_name_from_config, None)
        icon_detection_cycle(selected_poi_name_from_config, use_ppi=False, play_poi_sound_enabled=play_poi_sound_enabled)
    else:
        # Neither condition met - just use PPI
        icon_detection_cycle(selected_poi_name_from_config, use_ppi=True, play_poi_sound_enabled=play_poi_sound_enabled)

def icon_detection_cycle(selected_poi_name, use_ppi, play_poi_sound_enabled=True):
    """Icon detection cycle that uses either PPI or original mouse behavior"""
    if selected_poi_name.lower() == 'none':
        speaker.speak("No POI selected. Please select a POI first.")
        return

    # Get player info based on method
    if use_ppi:
        # Use PPI method
        player_location, player_angle = get_player_info_ppi()
        if player_location is None:
            speaker.speak("Could not find player position using PPI")
            play_poi_sound_enabled = False
    else:
        # Use original icon detection method
        player_location, player_angle = find_player_icon_location_with_direction()
        if player_location is None:
            speaker.speak("Could not find player position using icon detection")
            play_poi_sound_enabled = False

    poi_data_tuple = handle_poi_selection(selected_poi_name, player_location, use_ppi)
    
    poi_name_resolved, poi_coords_resolved = poi_data_tuple
    # Fallback: if resolution failed, try using saved coordinates from config
    if poi_coords_resolved is None:
        try:
            cfg = read_config()
            sel_str = cfg.get('POI', 'selected_poi', fallback='none,0,0')
            parts = [p.strip() for p in sel_str.split(',')]
            if len(parts) >= 3 and parts[0].strip().lower() == poi_name_resolved.lower():
                x_fb = int(float(parts[1]))
                y_fb = int(float(parts[2]))
                poi_coords_resolved = (x_fb, y_fb)
        except Exception:
            pass

    if poi_coords_resolved is None:
        speaker.speak(f"{poi_name_resolved} location not available.")
        return

    # Play spatial sound if enabled
    if play_poi_sound_enabled and player_location is not None and player_angle is not None:
        play_spatial_poi_sound(player_location, player_angle, poi_coords_resolved)

    # Handle mouse actions based on method
    if not use_ppi:
        # Use original mouse behavior
        is_dynamic_object = any(obj_name.lower() == selected_poi_name.lower() for obj_name, _, _ in DYNAMIC_OBJECTS)
        
        if not is_dynamic_object:
            pyautogui.moveTo(poi_coords_resolved[0], poi_coords_resolved[1], duration=0.1)
            pyautogui.rightClick(_pause=False)
            time.sleep(0.05)
            pyautogui.click(_pause=False)
        elif is_dynamic_object:
            pyautogui.moveTo(poi_coords_resolved[0], poi_coords_resolved[1], duration=0.1)

    # Perform POI actions
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
    
    # Get final angle for speech
    if use_ppi:
        _, latest_player_angle = get_player_info_ppi()
    else:
        _, latest_player_angle = find_player_icon_location_with_direction()
                                                    
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
    message = generate_poi_message(poi_name, player_angle, poi_info, player_location)

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

def get_player_info_ppi():
    """Get player location and angle using PPI method"""
    # Try to use cached position first for performance
    cached_pos, cached_angle = position_tracker.get_position_and_angle(force_update=True)
    
    if cached_pos is not None and cached_angle is not None:
        return cached_pos, cached_angle
    
    # Use PPI for position detection
    player_location = None
    player_angle = None

    # Always try PPI regardless of map check
    player_location = ppi_find_player_position()
    if player_location is not None:
        _, player_angle = find_minimap_icon_direction()
    
    # Always try to get angle from minimap if we don't have it
    if player_angle is None:
        _, player_angle_fallback = find_minimap_icon_direction()
        if player_angle_fallback is not None:
            player_angle = player_angle_fallback
            
    return player_location, player_angle

def get_player_info(use_ppi=False, manual_trigger=False):
    """Get player location and angle - wrapper for compatibility"""
    if use_ppi:
        return get_player_info_ppi()
    else:
        return find_player_icon_location_with_direction()

def get_position_with_fallback():
    """Get player position using all available methods with fallback"""
    # Try cached position first
    cached_pos = position_tracker.get_cached_position()
    if cached_pos is not None:
        return cached_pos
    
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

def cleanup_object_detection():
    """Clean up object detection resources"""
    # Stop position tracker
    position_tracker.stop_monitoring()
    
    # Cleanup dynamic object detection
    optimized_finder.cleanup()
    
    # Cleanup PPI resources
    from lib.detection.ppi import cleanup_ppi
    cleanup_ppi()