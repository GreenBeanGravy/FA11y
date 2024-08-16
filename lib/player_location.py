import cv2
import numpy as np
import pyautogui

# Constants
MIN_SHAPE_SIZE, MAX_SHAPE_SIZE = 1300, 2000
ROI_START_ORIG, ROI_END_ORIG = (590, 190), (1490, 1010)

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

def get_player_position_description(location):
    x, y = location
    x, y = x - ROI_START_ORIG[0], y - ROI_START_ORIG[1]
    width, height = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]
    quadrant = get_quadrant(x, y, width, height)
    position_in_quadrant = get_position_in_quadrant(x, y, width // 2, height // 2)
    
    quadrant_names = ["top-left", "top-right", "bottom-left", "bottom-right"]
    return f"Player is in the {position_in_quadrant} of the {quadrant_names[quadrant]} quadrant"

def find_player_icon_location():
    print("Finding player icon location")
    screenshot = cv2.resize(np.array(pyautogui.screenshot()), None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
    roi_gray = cv2.cvtColor(screenshot[4 * ROI_START_ORIG[1]:4 * ROI_END_ORIG[1], 4 * ROI_START_ORIG[0]:4 * ROI_END_ORIG[0]], cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(roi_gray, 229, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid_contours = [cnt for cnt in contours if MIN_SHAPE_SIZE < cv2.contourArea(cnt) < MAX_SHAPE_SIZE]
    if valid_contours:
        M = cv2.moments(max(valid_contours, key=cv2.contourArea))
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
    valid_contours = [cnt for cnt in contours if MIN_SHAPE_SIZE < cv2.contourArea(cnt) < MAX_SHAPE_SIZE]
    
    if valid_contours:
        contour = max(valid_contours, key=cv2.contourArea)
        M = cv2.moments(contour)
        center_mass = np.array([int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])])
        
        # Find the point farthest from the center of mass
        hull = cv2.convexHull(contour)
        hull_points = [point[0] for point in hull]
        farthest_point = max(hull_points, key=lambda p: np.linalg.norm(p - center_mass))
        
        # Calculate direction vector
        direction_vector = farthest_point - center_mass
        direction_vector = direction_vector / np.linalg.norm(direction_vector)  # Normalize the vector
        
        # Convert coordinates back to original scale and offset
        center_location = ((center_mass[0] // 4) + ROI_START_ORIG[0], (center_mass[1] // 4) + ROI_START_ORIG[1])
        
        print(f"Player icon located at: {center_location}, facing direction: {direction_vector}")
        return center_location, direction_vector
    
    print("Player icon not found")
    return None

if __name__ == "__main__":
    result = find_player_icon_location_with_direction()
    if result:
        location, direction = result
        print(f"Player location: {location}")
        print(f"Player direction: {direction}")
        print(get_player_position_description(location))
    else:
        print("Failed to find player icon")