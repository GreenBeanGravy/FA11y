import cv2
import numpy as np
import os
import time
from mss import mss
from accessible_output2.outputs.auto import Auto
import easyocr
from threading import Thread, Event
import configparser
from lib.utilities import get_config_int, get_config_float, get_config_value, get_config_boolean

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
ATTACHMENTS_FOLDER = "attachments"
CONFIDENCE_THRESHOLD = 0.80

AMMO_RESERVE_COORDS = [
    ((1527, 966), (1559, 983)),  # Slot 1
    ((1605, 966), (1642, 983)),  # Slot 2
    ((1686, 966), (1723, 983)),  # Slot 3
    ((1770, 966), (1804, 983)),  # Slot 4
    ((1850, 966), (1887, 983))   # Slot 5
]

ATTACHMENT_DETECTION_AREA = (1240, 1000, 1410, 1070)

DIVIDER_CHECK_COORDS = (1294, 936, 1335, 959)
AMMO_Y_COORDS = {
    'current': (929, 962),
    'reserve': (936, 962)
}

speaker = Auto()
reference_images = {}
attachment_images = {}
reader = easyocr.Reader(['en'], recognizer='number')

current_detection_thread = None
stop_event = Event()

def load_reference_images():
    slot_width, slot_height = SLOT_COORDS[0][2] - SLOT_COORDS[0][0], SLOT_COORDS[0][3] - SLOT_COORDS[0][1]
    for filename in os.listdir(IMAGES_FOLDER):
        if filename.lower().endswith((".png", ".jpg", ".jpeg")):
            img = cv2.imread(os.path.join(IMAGES_FOLDER, filename))
            if img is not None:
                reference_images[os.path.splitext(filename)[0]] = cv2.resize(img, (slot_width, slot_height))

def load_attachment_images():
    for attachment_type in ["Scope", "Magazine", "Underbarrel", "Barrel"]:
        attachment_images[attachment_type] = {}
        folder_path = os.path.join(ATTACHMENTS_FOLDER, attachment_type)
        for filename in os.listdir(folder_path):
            if filename.lower().endswith((".png", ".jpg", ".jpeg")):
                img = cv2.imread(os.path.join(folder_path, filename))
                if img is not None:
                    _, binary_img = cv2.threshold(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 254, 255, cv2.THRESH_BINARY)
                    attachment_images[attachment_type][os.path.splitext(filename)[0]] = binary_img

def pixel_based_matching(screenshot, template, threshold=30):
    if screenshot.shape != template.shape:
        return 0
    diff = np.abs(screenshot.astype(np.int32) - template.astype(np.int32))
    matching_pixels = np.sum(np.all(diff <= threshold, axis=2))
    return matching_pixels / (screenshot.shape[0] * screenshot.shape[1])

def detect_hotbar_item(slot_index):
    global current_detection_thread, stop_event
    
    if current_detection_thread and current_detection_thread.is_alive():
        stop_event.set()
        current_detection_thread.join()
    
    stop_event.clear()
    
    current_detection_thread = Thread(target=detect_hotbar_item_thread, args=(slot_index,))
    current_detection_thread.start()

def detect_hotbar_item_thread(slot_index):
    sct = mss()  # Create a new mss instance for this thread

    # Load configuration
    config = configparser.ConfigParser()
    config.read('config.txt')
    announce_attachments = get_config_boolean(config, 'SETTINGS', 'AnnounceWeaponAttachments', True)

    def check_slot(coord):
        screenshot = cv2.cvtColor(np.array(sct.grab(coord)), cv2.COLOR_RGBA2RGB)
        return max(((name, pixel_based_matching(screenshot, ref_img)) 
                    for name, ref_img in reference_images.items()), 
                   key=lambda x: x[1])

    best_match_name, best_score = check_slot(SLOT_COORDS[slot_index])
    
    if best_score <= CONFIDENCE_THRESHOLD:
        time.sleep(0.05)
        best_match_name, best_score = check_slot(SECONDARY_SLOT_COORDS[slot_index])
    
    if best_score > CONFIDENCE_THRESHOLD and not stop_event.is_set():
        speaker.speak(best_match_name)
        time.sleep(0.05)
        
        # Announce ammo
        if not stop_event.is_set():
            current_ammo, reserve_ammo = detect_ammo(sct)
            if current_ammo is not None or reserve_ammo is not None:
                current_ammo = current_ammo or 0
                reserve_ammo = reserve_ammo or 0
                speaker.speak(f"with {current_ammo} ammo in the mag and {reserve_ammo} in reserves")
            else:
                print("OCR failed to detect any ammo values.")
        
        # Wait for 0.3 seconds before announcing attachments
        time.sleep(0.3)
        
        # Then announce attachments
        if announce_attachments and not stop_event.is_set():
            detected_attachments = detect_attachments(sct)
            
            if detected_attachments:
                attachment_message = "with "
                attachment_list = []
                for attachment_type in ["Scope", "Magazine", "Underbarrel", "Barrel"]:
                    if attachment_type in detected_attachments:
                        attachment_list.append(f"a {detected_attachments[attachment_type]}")
                
                if len(attachment_list) > 0:
                    attachment_message += ", ".join(attachment_list[:-1])
                    if len(attachment_list) > 1:
                        attachment_message += f", and {attachment_list[-1]}"
                    else:
                        attachment_message += attachment_list[-1]
                    speaker.speak(attachment_message)

def detect_ammo(sct):
    divider_screenshot = np.array(sct.grab({'left': DIVIDER_CHECK_COORDS[0], 'top': DIVIDER_CHECK_COORDS[1], 
                                            'width': DIVIDER_CHECK_COORDS[2] - DIVIDER_CHECK_COORDS[0], 
                                            'height': DIVIDER_CHECK_COORDS[3] - DIVIDER_CHECK_COORDS[1]}))
    
    divider_template_path = os.path.join(ATTACHMENTS_FOLDER, "divider.png")
    if not os.path.exists(divider_template_path):
        print(f"Error: Divider template not found at {divider_template_path}")
        return None, None
    divider_template = cv2.imread(divider_template_path, 0)
    if divider_template is None:
        print(f"Error: Failed to read divider template from {divider_template_path}")
        return None, None
    gray_screenshot = cv2.cvtColor(divider_screenshot, cv2.COLOR_BGR2GRAY)
    
    # Apply threshold to make divider more distinct
    _, binary_screenshot = cv2.threshold(gray_screenshot, 255, 255, cv2.THRESH_BINARY)
    
    result = cv2.matchTemplate(binary_screenshot, divider_template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    
    if max_val > CONFIDENCE_THRESHOLD:
        divider_x = DIVIDER_CHECK_COORDS[0] + max_loc[0]
        
        current_ammo_area = {'left': divider_x - 75, 'top': AMMO_Y_COORDS['current'][0], 
                             'width': 75, 'height': AMMO_Y_COORDS['current'][1] - AMMO_Y_COORDS['current'][0]}
        reserve_ammo_area = {'left': divider_x + 7, 'top': AMMO_Y_COORDS['reserve'][0], 
                             'width': 50, 'height': AMMO_Y_COORDS['reserve'][1] - AMMO_Y_COORDS['reserve'][0]}
        
        current_ammo_screenshot = np.array(sct.grab(current_ammo_area))
        reserve_ammo_screenshot = np.array(sct.grab(reserve_ammo_area))
        
        current_ammo = detect_ammo_count(current_ammo_screenshot)
        reserve_ammo = detect_ammo_count(reserve_ammo_screenshot)
        
        return current_ammo, reserve_ammo
    else:
        print(f"Failed to detect ammo divider. Confidence: {max_val}")
        return None, None

def detect_ammo_count(ammo_screenshot):
    # Convert to grayscale
    gray = cv2.cvtColor(ammo_screenshot, cv2.COLOR_BGR2GRAY)
    
    # Apply threshold to isolate white pixels (220-255)
    _, binary = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY)
    
    # Invert the image if it's mostly white (assuming dark text on light background)
    if np.mean(binary) > 127:
        binary = cv2.bitwise_not(binary)
    
    # Resize for better OCR performance
    binary = cv2.resize(binary, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    
    results = reader.readtext(binary, 
                              allowlist='0123456789',
                              paragraph=False,
                              min_size=10,
                              text_threshold=0.5)
    
    if results:
        ammo_text = results[0][1]
        if ammo_text.isdigit():
            return int(ammo_text)
    
    return None

def detect_attachments(sct):
    screenshot = np.array(sct.grab({'left': ATTACHMENT_DETECTION_AREA[0], 'top': ATTACHMENT_DETECTION_AREA[1], 
                                    'width': ATTACHMENT_DETECTION_AREA[2] - ATTACHMENT_DETECTION_AREA[0], 
                                    'height': ATTACHMENT_DETECTION_AREA[3] - ATTACHMENT_DETECTION_AREA[1]}))
    
    # Convert screenshot to binary image (only pure white pixels)
    _, binary_screenshot = cv2.threshold(cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY), 254, 255, cv2.THRESH_BINARY)
    
    detected_attachments = {}
    attachment_order = ["Scope", "Magazine", "Underbarrel", "Barrel"]
    
    for attachment_type in attachment_order:
        best_match = None
        best_score = 0
        
        for name, template in attachment_images[attachment_type].items():
            result = cv2.matchTemplate(binary_screenshot, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            
            if max_val > best_score:
                best_score = max_val
                best_match = name
        
        if best_match and best_score > CONFIDENCE_THRESHOLD:
            detected_attachments[attachment_type] = best_match
    
    return detected_attachments

def initialize_hotbar_detection():
    load_reference_images()
    load_attachment_images()
