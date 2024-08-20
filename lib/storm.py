import cv2
import numpy as np
import pyautogui
import time

# Constants and settings
MIN_SHAPE_SIZE = 150000
ROI_START_ORIG, ROI_END_ORIG = (621, 182), (1342, 964)
ROI_START, ROI_END = tuple(4 * np.array(ROI_START_ORIG)), tuple(4 * np.array(ROI_END_ORIG))
TARGET_COLOR = np.array([165, 29, 146])
DISTANCE = 70
LOWER_BOUND, UPPER_BOUND = np.maximum(0, TARGET_COLOR - DISTANCE), np.minimum(255, TARGET_COLOR + DISTANCE)

# Precompute the ROI slice
ROI_SLICE = np.s_[ROI_START[1]:ROI_END[1], ROI_START[0]:ROI_END[0]]

def get_screenshot():
    pyautogui.moveTo(1900, 1000, duration=0.1, tween=pyautogui.easeInOutQuad)
    return np.array(pyautogui.screenshot())

def process_image(screenshot):
    return cv2.resize(cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB), None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)

def detect_storm(roi_color):
    mask = cv2.inRange(roi_color, LOWER_BOUND, UPPER_BOUND)
    mask = cv2.bitwise_not(mask)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for contour in contours:
        area = cv2.contourArea(contour)
        if area > MIN_SHAPE_SIZE:
            return process_contour(roi_color, contour, area)
    return None

def process_contour(roi_color, contour, area):
    M = cv2.moments(contour)
    cX, cY = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
    center_mass = (cX, cY)
    
    # Draw contour and center of mass (for visualization purposes)
    cv2.drawContours(roi_color, [contour], -1, (0, 255, 0), 2)
    cv2.circle(roi_color, center_mass, 5, (0, 0, 255), -1)
    cv2.putText(roi_color, f"Area: {area}", (cX, cY), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
    
    # Translate to original screen coordinates
    center_mass_screen = ((cX // 4) + ROI_START_ORIG[0], (cY // 4) + ROI_START_ORIG[1])
    print(f"Position in original image: {center_mass_screen}")
    print(f"{center_mass_screen[0]} {center_mass_screen[1]}")
    return center_mass_screen

def start_storm_detection():
    while True:
        screenshot = get_screenshot()
        roi_color = process_image(screenshot)[ROI_SLICE]
        
        storm_coords = detect_storm(roi_color)
        if storm_coords:
            return storm_coords  # Return the coordinates as soon as they are detected
        time.sleep(0.01)