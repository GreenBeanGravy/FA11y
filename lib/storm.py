import cv2
import numpy as np
import pyautogui
import ctypes
import time

VK_ALT = 0x12
VK_S = 0x53

# Define the minimum purple shape size and the region of interest
min_shape_size = 150000  # Adjust this value as needed
roi_start_orig = (621, 182)  # Top-left corner of the region of interest
roi_end_orig = (1342, 964)  # Bottom-right corner of the region of interest

def start_storm_detection():
    while True:
        # Check if the 'ALT' key is down
        alt_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_ALT) & 0x8000)

        # Check if the 'S' key is down
        s_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_S) & 0x8000)

        # If both the 'ALT' and 'S' keys are pressed
        if alt_key_current_state and s_key_current_state:
            # Move mouse smoothly to the coordinates (1920, 1080) over 0.1 seconds
            pyautogui.moveTo(1900, 1000, duration=0.1, tween=pyautogui.easeInOutQuad)

            # Take a screenshot
            screenshot = pyautogui.screenshot()

            # Convert the screenshot to a numpy array, convert to RGB format, and resize it
            screenshot_np = np.array(screenshot)
            screenshot_np = cv2.cvtColor(screenshot_np, cv2.COLOR_BGR2RGB)
            screenshot_np = cv2.resize(screenshot_np, None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)

            # Adjust the region of interest according to the new size
            roi_start = tuple(4 * np.array(roi_start_orig))
            roi_end = tuple(4 * np.array(roi_end_orig))

            # Crop the screenshot to the region of interest
            roi_color = screenshot_np[roi_start[1]:roi_end[1], roi_start[0]:roi_end[0]]

            # Define the target color and the distance for the range
            target_color = np.array([165, 29, 146])
            distance = 70

            # Define the color range in RGB format
            lower_bound = np.maximum(0, target_color - distance)
            upper_bound = np.minimum(255, target_color + distance)

            # Create a mask that only allows the target color through
            mask = cv2.inRange(roi_color, lower_bound, upper_bound)

            # Invert the mask
            mask = cv2.bitwise_not(mask)

            # Find contours in the inverted masked image. Each contour corresponds to a shape of the non-target color in the original image.
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                # Calculate the area of the contour
                area = cv2.contourArea(contour)

                # If the area of the contour is greater than the minimum size, it's a match
                if area > min_shape_size:
                    # Draw the contour on the image
                    cv2.drawContours(roi_color, [contour], -1, (0, 255, 0), 2)
                
                    # Calculate the center of mass of the contour
                    M = cv2.moments(contour)
                    cX = int(M["m10"] / M["m00"])
                    cY = int(M["m01"] / M["m00"])
                    center_mass = (cX, cY)
                
                    # Draw the center of mass on the image
                    cv2.circle(roi_color, center_mass, 5, (0, 0, 255), -1)
                
                    # Display the area of the contour on the image
                    cv2.putText(roi_color, f"Area: {area}", (cX, cY), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                
                    # Calculate the center of mass on the original screen
                    center_mass_screen = ((center_mass[0] // 4) + roi_start_orig[0], (center_mass[1] // 4) + roi_start_orig[1])
                    print(f"Position in original image: {center_mass_screen}")
                
                    # Move the mouse to the center of mass and left-click
                    pyautogui.moveTo(center_mass_screen[0], center_mass_screen[1], duration=0.1, tween=pyautogui.easeInOutQuad)
                    pyautogui.click()

                    break

        time.sleep(0.01)

if __name__ == "__main__":
    start_storm_detection()