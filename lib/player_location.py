import cv2
import numpy as np
import pyautogui

# Constants
MIN_SHAPE_SIZE, MAX_SHAPE_SIZE = 1300, 2000
ROI_START_ORIG, ROI_END_ORIG = (590, 190), (1490, 1010)

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