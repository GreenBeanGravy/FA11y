import cv2
import numpy as np
import os
import time
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
SECONDARY_SLOT_COORDS = [
    (1514, 920, 1577, 964),  # Slot 1
    (1595, 920, 1658, 964),  # Slot 2
    (1677, 920, 1740, 964),  # Slot 3
    (1759, 920, 1822, 964),  # Slot 4
    (1840, 920, 1903, 964)   # Slot 5
]
IMAGES_FOLDER = "images"  # Folder containing reference weapon images
CONFIDENCE_THRESHOLD = 0.75  # Minimum confidence to consider a match valid

speaker = Auto()
reference_images = {}

def load_reference_images(folder):
    """Loads and resizes reference images to the slot dimensions."""
    slot_width = SLOT_COORDS[0][2] - SLOT_COORDS[0][0]
    slot_height = SLOT_COORDS[0][3] - SLOT_COORDS[0][1]
    
    for filename in os.listdir(folder):
        if filename.lower().endswith((".png", ".jpg", ".jpeg")):
            img = cv2.imread(os.path.join(folder, filename))
            if img is not None:
                img_resized = cv2.resize(img, (slot_width, slot_height))
                reference_images[os.path.splitext(filename)[0]] = img_resized

def match_template(image, template):
    """Matches the template within the given image using normalized cross-correlation."""
    result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    return cv2.minMaxLoc(result)[1]  # Return only the maximum value

def detect_hotbar_item(slot_index):
    """Detects the item in the specified hotbar slot."""
    def check_slot(coord):
        with mss() as sct:
            screenshot = np.array(sct.grab(coord))
            screenshot_rgb = cv2.cvtColor(screenshot, cv2.COLOR_RGBA2RGB)
        
        best_match_name = None
        best_score = -1
        for name, ref_img in reference_images.items():
            score = match_template(screenshot_rgb, ref_img)
            if score > best_score:
                best_score = score
                best_match_name = name
        return best_match_name, best_score

    # Primary coordinates check
    best_match_name, best_score = check_slot(SLOT_COORDS[slot_index])
    
    # If no item found with primary coordinates, wait 0.1 seconds and check secondary coordinates
    if best_score <= CONFIDENCE_THRESHOLD:
        time.sleep(0.05)
        best_match_name, best_score = check_slot(SECONDARY_SLOT_COORDS[slot_index])
    
    # Speak the detected item if a match was found with high confidence
    if best_score > CONFIDENCE_THRESHOLD:
        speaker.speak(best_match_name)

def initialize_hotbar_detection():
    """Initializes the hotbar detection by loading reference images."""
    load_reference_images(IMAGES_FOLDER)
