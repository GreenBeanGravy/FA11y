import threading
import time
from PIL import ImageGrab
import numpy as np
from accessible_output2.outputs.auto import Auto

speaker = Auto()

def check_pixel_color(x, y, target_color):
    screenshot = ImageGrab.grab(bbox=(x, y, x+1, y+1))
    return screenshot.getpixel((0, 0)) == target_color

def check_height():
    target_color = (255, 255, 255)  # White
    check_points = [(1586, 309), (1597, 309), (1608, 309), (1609, 11)]
    height_x = 1587
    min_y, max_y = 35, 305
    min_meter, max_meter = 0, 770
    
    while True:
        if all(check_pixel_color(x, y, target_color) for x, y in check_points):
            screenshot = ImageGrab.grab(bbox=(height_x, min_y, height_x+1, max_y+1))
            img_array = np.array(screenshot)
            white_pixels = np.where(np.all(img_array == target_color, axis=1))[0]
            
            if white_pixels.size > 0:
                pixel_y = min_y + white_pixels[0]
                meters = max_meter - (pixel_y - min_y) * (max_meter - min_meter) / (max_y - min_y)
                print(f"Height detected: {meters:.2f} meters")
                speaker.speak(f"{meters:.0f} meters high")
            else:
                print("No height indicator detected")
        
        time.sleep(2.5)

def start_height_checker():
    thread = threading.Thread(target=check_height, daemon=True)
    thread.start()

if __name__ == "__main__":
    start_height_checker()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Height checker stopped.")