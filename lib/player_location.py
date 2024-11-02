import cv2
import numpy as np
import pyautogui

# Constants
MIN_SHAPE_SIZE, MAX_SHAPE_SIZE = 1300, 2000
ROI_START_ORIG, ROI_END_ORIG = (584, 84), (1490, 1010)
COLOR_THRESHOLD = 50  # All colors under this RGB color value are outlawed
MAX_OUTLAWED_PIXELS = 100  # Maximum number of outlawed pixels allowed within a contour

def get_angle_and_direction(vector):
    angle = np.degrees(np.arctan2(-vector[1], vector[0]))
    angle = (90 - angle) % 360  # Adjust to start from North (0 degrees) and increase clockwise
    return angle, get_cardinal_direction(angle)

def get_cardinal_direction(angle):
    directions = ['North', 'Northeast', 'East', 'Southeast', 'South', 'Southwest', 'West', 'Northwest']
    return directions[int((angle + 22.5) % 360 // 45)]

def calculate_poi_info(player_location, player_angle, poi_location):
    if player_location is None:
        distance = None
        poi_angle = None
        cardinal_direction = None
        relative_direction = "unknown"
    else:
        poi_vector = np.array(poi_location) - np.array(player_location)
        distance = np.linalg.norm(poi_vector) * 2.65
        poi_angle, cardinal_direction = get_angle_and_direction(poi_vector)
        
        if player_angle is not None:
            relative_direction = get_relative_direction(player_angle, poi_angle)
        else:
            relative_direction = "unknown"
    
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

def get_player_position_description(location, poi_name=None, poi_location=None, player_angle=None):
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

def count_pixels(mask, contour):
    temp_mask = np.zeros(mask.shape, dtype=np.uint8)
    cv2.drawContours(temp_mask, [contour], 0, 255, -1)
    white_pixels = cv2.countNonZero(cv2.bitwise_and(mask, temp_mask))
    black_pixels = cv2.countNonZero(cv2.bitwise_and(cv2.bitwise_not(mask), temp_mask))
    return white_pixels, black_pixels

def find_player_icon_location():
    print("Finding player icon location")
    screenshot = cv2.resize(np.array(pyautogui.screenshot()), None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
    roi_color = screenshot[4 * ROI_START_ORIG[1]:4 * ROI_END_ORIG[1], 4 * ROI_START_ORIG[0]:4 * ROI_END_ORIG[0]]
    roi_gray = cv2.cvtColor(roi_color, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(roi_gray, 229, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    valid_contours = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if MIN_SHAPE_SIZE < area < MAX_SHAPE_SIZE:
            white_pixels, black_pixels = count_pixels(binary, cnt)
            if black_pixels <= MAX_OUTLAWED_PIXELS:
                valid_contours.append((cnt, white_pixels, black_pixels))
    
    valid_contours.sort(key=lambda x: x[1], reverse=True)  # Sort by white pixel count
    
    print("Top 5 detected contours:")
    for i, (cnt, white_pixels, black_pixels) in enumerate(valid_contours[:5], 1):
        print(f"Contour {i}: White pixels: {white_pixels}, Black pixels: {black_pixels}")
    
    if valid_contours:
        best_contour = valid_contours[0][0]
        M = cv2.moments(best_contour)
        location = ((int(M["m10"] / M["m00"]) // 4) + ROI_START_ORIG[0], (int(M["m01"] / M["m00"]) // 4) + ROI_START_ORIG[1])
        print(f"Player icon located at: {location}")
        return location
    print("Player icon not found")
    return None

def find_player_icon_location_with_direction():
    print("Finding player icon location and direction")
    screenshot = cv2.resize(np.array(pyautogui.screenshot()), None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
    roi_color = screenshot[4 * ROI_START_ORIG[1]:4 * ROI_END_ORIG[1], 4 * ROI_START_ORIG[0]:4 * ROI_END_ORIG[0]]
    roi_gray = cv2.cvtColor(roi_color, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(roi_gray, 229, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    valid_contours = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if MIN_SHAPE_SIZE < area < MAX_SHAPE_SIZE:
            white_pixels, black_pixels = count_pixels(binary, cnt)
            if black_pixels <= MAX_OUTLAWED_PIXELS:
                valid_contours.append((cnt, white_pixels, black_pixels))
    
    valid_contours.sort(key=lambda x: x[1], reverse=True)  # Sort by white pixel count
    
    print("Top 5 detected contours:")
    for i, (cnt, white_pixels, black_pixels) in enumerate(valid_contours[:5], 1):
        print(f"Contour {i}: White pixels: {white_pixels}, Black pixels: {black_pixels}")
    
    if valid_contours:
        best_contour = valid_contours[0][0]
        M = cv2.moments(best_contour)
        center_mass = np.array([int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])])
        
        hull = cv2.convexHull(best_contour)
        hull_points = [point[0] for point in hull]
        farthest_point = max(hull_points, key=lambda p: np.linalg.norm(p - center_mass))
        
        direction_vector = farthest_point - center_mass
        player_angle, _ = get_angle_and_direction(direction_vector)
        
        center_location = ((center_mass[0] // 4) + ROI_START_ORIG[0], (center_mass[1] // 4) + ROI_START_ORIG[1])
        
        print(f"Player icon located at: {center_location}, facing angle: {player_angle}")
        return center_location, player_angle
    
    print("Player icon not found")
    return None
