import cv2
import numpy as np
import pyautogui
from accessible_output2.outputs.auto import Auto

speaker = Auto()

# Constants
MINIMAP_START = (1685, 83)
MINIMAP_END = (1838, 236)
MIN_SHAPE_SIZE, MAX_SHAPE_SIZE = 1170, 1800
COLOR_THRESHOLD = 50 # All colors under this RGB color value are outlawed
MAX_OUTLAWED_PIXELS = 100  # Maximum number of outlawed pixels allowed within a contour

def get_cardinal_direction(angle):
    directions = ['North', 'Northeast', 'East', 'Southeast', 'South', 'Southwest', 'West', 'Northwest']
    index = int((angle + 22.5) % 360 // 45)
    return directions[index]

def count_pixels(mask, contour):
    # Create a blank mask
    temp_mask = np.zeros(mask.shape, dtype=np.uint8)
    # Draw the contour on the mask
    cv2.drawContours(temp_mask, [contour], 0, 255, -1)
    # Count white and colored pixels within the contour
    white_pixels = cv2.countNonZero(cv2.bitwise_and(mask, temp_mask))
    colored_pixels = cv2.countNonZero(cv2.bitwise_and(cv2.bitwise_not(mask), temp_mask))
    return white_pixels, colored_pixels

def find_minimap_icon_direction(sensitivity=1.0):
    # Capture the minimap area
    screenshot = np.array(pyautogui.screenshot(region=(MINIMAP_START[0], MINIMAP_START[1], 
                                                       MINIMAP_END[0] - MINIMAP_START[0], 
                                                       MINIMAP_END[1] - MINIMAP_START[1])))
    
    # Resize the screenshot to match the scale of the original detection
    screenshot = cv2.resize(screenshot, None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
    
    # Convert to grayscale
    gray = cv2.cvtColor(screenshot, cv2.COLOR_RGB2GRAY)
    
    # Threshold to get the white icon
    _, binary = cv2.threshold(gray, int(229 * sensitivity), 255, cv2.THRESH_BINARY)
    
    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Filter contours by size and color
    valid_contours = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if MIN_SHAPE_SIZE < area < MAX_SHAPE_SIZE:
            white_pixels, colored_pixels = count_pixels(binary, cnt)
            if colored_pixels <= MAX_OUTLAWED_PIXELS:
                valid_contours.append((cnt, white_pixels, colored_pixels))
    
    valid_contours.sort(key=lambda x: x[1], reverse=True)  # Sort by white pixel count
    
    print("Top 5 detected contours:")
    for i, (cnt, white_pixels, colored_pixels) in enumerate(valid_contours[:5], 1):
        print(f"Contour {i}: White pixels: {white_pixels}, Colored pixels: {colored_pixels}")
    
    if valid_contours:
        # Get the largest valid contour (should be the player icon)
        contour = valid_contours[0][0]
        
        # Get the moments and center of mass
        M = cv2.moments(contour)
        center_mass = np.array([M["m10"] / M["m00"], M["m01"] / M["m00"]])
        
        # Get the convex hull and find the farthest point
        hull = cv2.convexHull(contour)
        if len(hull) > 2:
            vertices = np.squeeze(hull)
            farthest_vertex = vertices[np.argmax(np.linalg.norm(vertices - center_mass, axis=1))]
            
            # Calculate the direction vector
            direction_vector = farthest_vertex - center_mass
            
            # Calculate the angle in degrees
            angle = np.degrees(np.arctan2(-direction_vector[1], direction_vector[0]))
            
            # Adjust angle to start from North (0 degrees) and increase clockwise
            angle = (450 - angle) % 360
            
            # Get the cardinal direction
            cardinal_direction = get_cardinal_direction(angle)
            
            return cardinal_direction, angle
    
    return None, None

def speak_minimap_direction():
    direction, angle = find_minimap_icon_direction()
    if direction and angle is not None:
        message = f"Facing {direction}, {angle:.0f} degrees"
        print(message)
        speaker.speak(message)
    else:
        message = "Unable to determine direction from minimap"
        print(message)
        speaker.speak(message)
