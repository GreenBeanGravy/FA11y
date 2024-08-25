import cv2
import numpy as np
import os
import time
from mss import mss
from accessible_output2.outputs.auto import Auto

# Coordinate and slot configurations
SLOT_COORDS = [
    (1514, 931, 1577, 975),  # Slot 1
    (1595, 931, 1658, 975),  # Slot 2
    (1677, 931, 1740, 975),  # Slot 3
    (1759, 931, 1822, 975),  # Slot 4
    (1840, 931, 1903, 975)   # Slot 5
]

SECONDARY_SLOT_COORDS = [(x, y-11, x2, y2-11) for x, y, x2, y2 in SLOT_COORDS]
IMAGES_FOLDER = "images"
CONFIDENCE_THRESHOLD = 0.85

# Coordinates for checking color white (255, 255, 255)
WHITE_CHECK_COORDS = {
    0: [1516, 1537, 1556, 1575],  # SLOT 1 Y915
    1: [1600, 1619, 1638, 1657],  # SLOT 2 Y915
    2: [1681, 1700, 1719, 1738],  # SLOT 3 Y915
    3: [1762, 1781, 1800, 1819],  # SLOT 4 Y915
    4: [1843, 1862, 1881, 1900]   # SLOT 5 Y915
}

# Messages for each coordinate
COORDINATE_MESSAGES = [
    "Scope", "Magazine", "Underbarrel", "Barrel"
]

speaker = Auto()
reference_images = {}

def load_reference_images():
    slot_width, slot_height = SLOT_COORDS[0][2] - SLOT_COORDS[0][0], SLOT_COORDS[0][3] - SLOT_COORDS[0][1]
    for filename in os.listdir(IMAGES_FOLDER):
        if filename.lower().endswith((".png", ".jpg", ".jpeg")):
            img = cv2.imread(os.path.join(IMAGES_FOLDER, filename))
            if img is not None:
                reference_images[os.path.splitext(filename)[0]] = cv2.resize(img, (slot_width, slot_height))

def pixel_based_matching(screenshot, template, threshold=30):
    if screenshot.shape != template.shape:
        return 0
    diff = np.abs(screenshot.astype(np.int32) - template.astype(np.int32))
    matching_pixels = np.sum(np.all(diff <= threshold, axis=2))
    return matching_pixels / (screenshot.shape[0] * screenshot.shape[1])

def detect_hotbar_item(slot_index):
    def check_slot(coord):
        screenshot = cv2.cvtColor(np.array(mss().grab(coord)), cv2.COLOR_RGBA2RGB)
        return max(((name, pixel_based_matching(screenshot, ref_img)) 
                    for name, ref_img in reference_images.items()), 
                   key=lambda x: x[1])

    best_match_name, best_score = check_slot(SLOT_COORDS[slot_index])
    
    if best_score <= CONFIDENCE_THRESHOLD:
        time.sleep(0.05)
        best_match_name, best_score = check_slot(SECONDARY_SLOT_COORDS[slot_index])
    
    if best_score > CONFIDENCE_THRESHOLD:
        # Announce the detected item
        speaker.speak(best_match_name)

        # Wait for 100 ms
        time.sleep(0.1)

        # Check for additional attachments
        attachments = []
        y_coord = 915  # Common Y coordinate for all checks

        for i, x_coord in enumerate(WHITE_CHECK_COORDS[slot_index]):
            # Check if the pixel at the coordinate is white
            screenshot = np.array(mss().grab({'left': x_coord, 'top': y_coord, 'width': 1, 'height': 1}))
            color = screenshot[0, 0, :3]  # Get the RGB values

            if tuple(color) == (255, 255, 255):
                attachments.append(COORDINATE_MESSAGES[i])

        if attachments:
            # Build the attachment message
            if len(attachments) == 1:
                attachment_message = f"with a {attachments[0]}"
            else:
                attachment_message = "with a " + ", ".join(attachments[:-1]) + f", and {attachments[-1]}"

            speaker.speak(attachment_message)

def initialize_hotbar_detection():
    load_reference_images()

def match_template(image, template):
    return pixel_based_matching(image, template)
