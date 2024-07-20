import cv2
import numpy as np
import os
from mss import mss
from accessible_output2.outputs.auto import Auto

# Constants
SLOT_COORDS = [
    (1514, 931, 1577, 975),  # Slot 1
    (1595, 931, 1658, 975),  # Slot 2
    (1677, 931, 1740, 975),  # Slot 3
    (1759, 931, 1822, 975),  # Slot 4
    (1840, 931, 1903, 975)   # Slot 5
]
IMAGES_FOLDER = "images"  # Folder containing reference weapon images
CONFIDENCE_THRESHOLD = 0.75  # Minimum confidence to consider a match valid

speaker = Auto()
reference_images = {}

def load_reference_images(folder):
    global reference_images
    for filename in os.listdir(folder):
        if filename.endswith((".png", ".jpg", ".jpeg")):
            img = cv2.imread(os.path.join(folder, filename))
            img = cv2.resize(img, (SLOT_COORDS[0][2] - SLOT_COORDS[0][0], SLOT_COORDS[0][3] - SLOT_COORDS[0][1]))
            name = os.path.splitext(filename)[0]
            reference_images[name] = img

def match_template(image, template):
    result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return max_val

def detect_hotbar_item(slot_index):
    with mss() as sct:
        coord = SLOT_COORDS[slot_index]
        screenshot = np.array(sct.grab(coord))
        screenshot_rgb = cv2.cvtColor(screenshot, cv2.COLOR_RGBA2RGB)
    
    best_match = None
    best_score = -1
    for name, ref_img in reference_images.items():
        score = match_template(screenshot_rgb, ref_img)
        if score > best_score:
            best_score = score
            best_match = name
    
    if best_score > CONFIDENCE_THRESHOLD:
        speaker.speak(best_match)

def initialize_hotbar_detection():
    load_reference_images(IMAGES_FOLDER)
    print("Hotbar detection initialized")