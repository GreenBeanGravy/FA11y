import threading
import time
from PIL import ImageGrab
import numpy as np
from accessible_output2.outputs.auto import Auto

speaker = Auto()

def check_pixel_color(x, y, target_color):
    screenshot = ImageGrab.grab(bbox=(x, y, x+1, y+1))
    return screenshot.getpixel((0, 0)) == target_color

def interpolate_height(pixel_y):
    # Define the known points
    y1, h1 = 47, 750
    y2, h2 = 173, 325
    y3, h3 = 299, 0

    # Check which range the pixel_y falls into
    if y1 <= pixel_y <= y2:
        # Interpolate between (y1, h1) and (y2, h2)
        return h1 + (pixel_y - y1) * (h2 - h1) / (y2 - y1)
    elif y2 < pixel_y <= y3:
        # Interpolate between (y2, h2) and (y3, h3)
        return h2 + (pixel_y - y2) * (h3 - h2) / (y3 - y2)
    else:
        # Outside the known range
        return None

def check_height():
    target_color = (255, 255, 255)  # White
    check_points = [(1576, 329), (1586, 329), (1596, 329), (1599, 33)]
    height_x = 1583
    min_y, max_y = 47, 299  # Updated to match the new range
    
    while True:
        if all(check_pixel_color(x, y, target_color) for x, y in check_points):
            screenshot = ImageGrab.grab(bbox=(height_x, min_y, height_x+1, max_y+1))
            img_array = np.array(screenshot)
            white_pixels = np.where(np.all(img_array == target_color, axis=1))[0]
            
            if white_pixels.size > 0:
                pixel_y = min_y + white_pixels[0]
                meters = interpolate_height(pixel_y)
                if meters is not None:
                    print(f"Height detected: {meters:.2f} meters")
                    speaker.speak(f"{meters:.0f} meters high")
                else:
                    print("Height indicator outside expected range")
            else:
                print("No height indicator detected")
        
        time.sleep(2.5)

def start_height_checker():
    thread = threading.Thread(target=check_height, daemon=True)
    thread.start()
