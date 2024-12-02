import cv2
import numpy as np
import pyautogui

# Constants
ROI_START_ORIG, ROI_END_ORIG = (524, 84), (1390, 1010)
SCALE_FACTOR = 4
MIN_AREA = 1008
MAX_AREA = 1386

def get_angle_and_direction(vector):
    angle = np.degrees(np.arctan2(-vector[1], vector[0]))
    angle = (90 - angle) % 360  # Adjust to start from North (0 degrees) and increase clockwise
    return angle, get_cardinal_direction(angle)

def get_cardinal_direction(angle):
    directions = ['North', 'Northeast', 'East', 'Southeast', 'South', 'Southwest', 'West', 'Northwest']
    return directions[int((angle + 22.5) % 360 // 45)]

def calculate_poi_info(player_location, player_angle, poi_location):
    if player_location is None:
        return None, None, None, "unknown"
    
    poi_vector = np.array(poi_location) - np.array(player_location)
    distance = np.linalg.norm(poi_vector) * 2.65
    poi_angle, cardinal_direction = get_angle_and_direction(poi_vector)
    
    relative_direction = get_relative_direction(player_angle, poi_angle) if player_angle is not None else "unknown"
    
    return distance, poi_angle, cardinal_direction, relative_direction

def get_relative_direction(player_angle, poi_angle):
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

def generate_poi_message(poi_name, player_angle, poi_info):
    distance, poi_angle, cardinal_direction, relative_direction = poi_info
    
    if distance is None:
        return f"Pinged {poi_name}, player position unknown."

    if player_angle is None:
        message = f"{poi_name} is {int(distance)} meters away"
        if cardinal_direction:
            message += f", {cardinal_direction}"
        if poi_angle is not None:
            message += f" at {poi_angle:.0f} degrees"
        message += ". Player direction not found."
    else:
        player_cardinal = get_cardinal_direction(player_angle)
        
        # Check if the player is roughly facing the POI (within 20 degrees)
        is_facing = abs((poi_angle - player_angle + 180) % 360 - 180) <= 20

        if is_facing:
            message = f"Facing {poi_name} at {int(distance)} meters away, "
        else:
            message = f"{poi_name} is {relative_direction} {int(distance)} meters away, "

        message += f"{cardinal_direction} at {poi_angle:.0f} degrees, "
        message += f"facing {player_cardinal} at {player_angle:.0f} degrees"
    
    return message

def get_quadrant(x, y, width, height):
    mid_x, mid_y = width // 2, height // 2
    return (1 if x >= mid_x else 0) + (2 if y >= mid_y else 0)

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

def get_player_position_description(location, poi_name=None, poi_location=None, player_angle=None):
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

def find_triangle_tip(contour, center_mass):
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
    """Simple version that only returns location without direction"""
    location, _ = find_player_icon_location_with_direction()
    return location

def find_player_icon_location_with_direction():
    """Find both player location and direction using improved detection method"""
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