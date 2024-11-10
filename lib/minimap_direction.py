import cv2
import numpy as np
import pyautogui
from accessible_output2.outputs.auto import Auto
from lib.player_location import (
    find_triangle_tip,
    get_cardinal_direction,
    SCALE_FACTOR
)

speaker = Auto()

MINIMAP_START = (1736, 165)
MINIMAP_END = (1761, 192)
MIN_AREA = 800
MAX_AREA = 1100

def find_minimap_icon_direction():
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
                    
                    cardinal_direction = get_cardinal_direction(angle)
                    print(f"Found icon facing {cardinal_direction} at {angle:.1f}°")
                    return cardinal_direction, angle
    
    print("No valid minimap icon found")
    return None, None

def speak_minimap_direction():
    direction, angle = find_minimap_icon_direction()
    if direction and angle is not None:
        message = f"Facing {direction} at {angle:.0f} degrees"
        print(message)
        speaker.speak(message)
    else:
        message = "Unable to determine direction from minimap"
        print(message)
        speaker.speak(message)