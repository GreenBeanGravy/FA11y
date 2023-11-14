import cv2, numpy as np, pyautogui, ctypes, time

# Constants and settings
min_shape_size = 150000
roi_start_orig, roi_end_orig = (621, 182), (1342, 964)
roi_start, roi_end = tuple(4 * np.array(roi_start_orig)), tuple(4 * np.array(roi_end_orig))
target_color = np.array([165, 29, 146])
distance = 70
lower_bound, upper_bound = np.maximum(0, target_color - distance), np.minimum(255, target_color + distance)

def get_screenshot():
    # Smooth mouse move and screenshot capture
    pyautogui.moveTo(1900, 1000, duration=0.1, tween=pyautogui.easeInOutQuad)
    return pyautogui.screenshot()

def process_image(screenshot):
    # Convert to numpy array and apply color transformations
    screenshot_np = cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGR2RGB)
    return cv2.resize(screenshot_np, None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)

def detect_storm(roi_color):
    mask = cv2.inRange(roi_color, lower_bound, upper_bound)
    mask = cv2.bitwise_not(mask)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for contour in contours:
        area = cv2.contourArea(contour)
        if area > min_shape_size:
            return process_contour(roi_color, contour, area)
    return None

def process_contour(roi_color, contour, area):
    # Draw contour and calculate center of mass
    cv2.drawContours(roi_color, [contour], -1, (0, 255, 0), 2)
    M, (cX, cY) = cv2.moments(contour), (int(cv2.moments(contour)["m10"] / cv2.moments(contour)["m00"]), int(cv2.moments(contour)["m01"] / cv2.moments(contour)["m00"]))
    center_mass = (cX, cY)

    # Draw center of mass and display area
    cv2.circle(roi_color, center_mass, 5, (0, 0, 255), -1)
    cv2.putText(roi_color, f"Area: {area}", (cX, cY), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
    
    # Translate to original screen coordinates
    center_mass_screen = ((center_mass[0] // 4) + roi_start_orig[0], (center_mass[1] // 4) + roi_start_orig[1])
    print(f"Position in original image: {center_mass_screen}")
    print(f"{center_mass_screen[0]} {center_mass_screen[1]}")

    return center_mass_screen

def start_storm_detection():
    while True:
        screenshot = get_screenshot()
        screenshot_np = process_image(screenshot)
        roi_color = screenshot_np[roi_start[1]:roi_end[1], roi_start[0]:roi_end[0]]
        
        storm_coords = detect_storm(roi_color)
        if storm_coords:
            return storm_coords  # Return the coordinates as soon as they are detected

        time.sleep(0.01)
