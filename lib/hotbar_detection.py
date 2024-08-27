import cv2
import numpy as np
import os
import time
from mss import mss
from accessible_output2.outputs.auto import Auto
from threading import Thread, Event
import configparser
from lib.utilities import get_config_boolean

# Constants
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
ATTACHMENT_DETECTION_AREA = (1240, 1000, 1410, 1070)
AMMO_Y_COORDS = {
    'current': (929, 962),
    'reserve': (936, 962)
}

# Divider pattern
DIVIDER_PATTERN = [
    (0, 0), (0, -1), (0, -2), (0, -3),
    (1, -5), (1, -6), (1, -7), (1, -8), (1, -9),
    (2, -10), (2, -11), (2, -12), (2, -13), (2, -14),
    (3, -16), (3, -17), (3, -18), (3, -19)
]

speaker = Auto()
reference_images = {}
attachment_images = {}
easyocr_available = False

try:
    import easyocr
    reader = easyocr.Reader(['en'], recognizer='number')
    easyocr_available = True
except ImportError:
    print("EasyOCR not available. OCR functions will be skipped.")

current_detection_thread = None
timer_thread = None
stop_event = Event()
timer_stop_event = Event()

def load_images(folder, is_attachment=False):
    images = {}
    for filename in os.listdir(folder):
        if filename.lower().endswith((".png", ".jpg", ".jpeg")):
            img = cv2.imread(os.path.join(folder, filename))
            if img is not None:
                name = os.path.splitext(filename)[0]
                if is_attachment:
                    _, img = cv2.threshold(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 254, 255, cv2.THRESH_BINARY)
                images[name] = img
    return images

def load_reference_images():
    global reference_images
    slot_width, slot_height = SLOT_COORDS[0][2] - SLOT_COORDS[0][0], SLOT_COORDS[0][3] - SLOT_COORDS[0][1]
    reference_images = load_images(IMAGES_FOLDER)
    for name, img in reference_images.items():
        reference_images[name] = cv2.resize(img, (slot_width, slot_height))

def load_attachment_images():
    global attachment_images
    for attachment_type in ["Scope", "Magazine", "Underbarrel", "Barrel"]:
        folder_path = os.path.join(ATTACHMENTS_FOLDER, attachment_type)
        attachment_images[attachment_type] = load_images(folder_path, is_attachment=True)

def pixel_based_matching(screenshot, template, threshold=30):
    if screenshot.shape != template.shape:
        return 0
    diff = np.abs(screenshot.astype(np.int32) - template.astype(np.int32))
    matching_pixels = np.sum(np.all(diff <= threshold, axis=2))
    return matching_pixels / (screenshot.shape[0] * screenshot.shape[1])

def timer_thread_function(delay, function, *args):
    time.sleep(delay)
    if not timer_stop_event.is_set():
        function(*args)

def detect_hotbar_item(slot_index):
    global current_detection_thread, timer_thread, stop_event, timer_stop_event
    
    if current_detection_thread and current_detection_thread.is_alive():
        stop_event.set()
    
    if timer_thread and timer_thread.is_alive():
        timer_stop_event.set()
        timer_thread.join()
    
    stop_event.clear()
    timer_stop_event.clear()
    
    current_detection_thread = Thread(target=detect_hotbar_item_thread, args=(slot_index,))
    current_detection_thread.start()

def check_slot(coord):
    with mss() as sct:
        screenshot = cv2.cvtColor(np.array(sct.grab(coord)), cv2.COLOR_RGBA2RGB)
    return max(((name, pixel_based_matching(screenshot, ref_img)) 
                for name, ref_img in reference_images.items()), 
               key=lambda x: x[1])

def detect_hotbar_item_thread(slot_index):
    global timer_thread
    config = configparser.ConfigParser()
    config.read('config.txt')
    announce_attachments_enabled = get_config_boolean(config, 'SETTINGS', 'AnnounceWeaponAttachments', True)
    announce_ammo_enabled = get_config_boolean(config, 'SETTINGS', 'AnnounceAmmo', True)

    best_match_name, best_score = check_slot(SLOT_COORDS[slot_index])
    
    if best_score <= CONFIDENCE_THRESHOLD:
        timer_thread = Thread(target=timer_thread_function, args=(0.05, check_secondary_slot, slot_index))
        timer_thread.start()
        return
    
    if best_score > CONFIDENCE_THRESHOLD and not stop_event.is_set():
        speaker.speak(best_match_name)
        
        if easyocr_available and announce_ammo_enabled:
            timer_thread = Thread(target=timer_thread_function, args=(0.1, announce_ammo))
            timer_thread.start()
        
        if announce_attachments_enabled:
            timer_thread = Thread(target=timer_thread_function, args=(0.4, announce_attachments))
            timer_thread.start()

def check_secondary_slot(slot_index):
    if stop_event.is_set():
        return
    best_match_name, best_score = check_slot(SECONDARY_SLOT_COORDS[slot_index])
    if best_score > CONFIDENCE_THRESHOLD:
        speaker.speak(best_match_name)
        config = configparser.ConfigParser()
        config.read('config.txt')
        announce_ammo_enabled = get_config_boolean(config, 'SETTINGS', 'AnnounceAmmo', True)
        if easyocr_available and announce_ammo_enabled:
            timer_thread = Thread(target=timer_thread_function, args=(0.1, announce_ammo))
            timer_thread.start()

def announce_ammo():
    if stop_event.is_set() or not easyocr_available:
        return
    with mss() as sct:
        current_ammo, reserve_ammo = detect_ammo(sct)
    if current_ammo is not None or reserve_ammo is not None:
        speaker.speak(f"with {current_ammo or 0} ammo in the mag and {reserve_ammo or 0} in reserves")
    else:
        print("OCR failed to detect any ammo values.")

def announce_ammo_manually():
    sct = mss()
    current_ammo, reserve_ammo = detect_ammo(sct)
    if current_ammo is not None or reserve_ammo is not None:
        speaker.speak(f"You have {current_ammo or 0} ammo in the mag and {reserve_ammo or 0} in reserves")
    else:
        speaker.speak("No ammo")

def announce_attachments():
    if stop_event.is_set():
        return
    with mss() as sct:
        detected_attachments = detect_attachments(sct)
    if detected_attachments:
        attachment_list = [f"a {detected_attachments[at_type]}" for at_type in ["Scope", "Magazine", "Underbarrel", "Barrel"] if at_type in detected_attachments]
        if attachment_list:
            attachment_message = "with " + ", ".join(attachment_list[:-1])
            if len(attachment_list) > 1:
                attachment_message += f", and {attachment_list[-1]}"
            else:
                attachment_message += attachment_list[-1]
            speaker.speak(attachment_message)

def is_white(pixel):
    return np.all(pixel[:3] == [255, 255, 255])

def detect_divider(screenshot):
    height, width = screenshot.shape[:2]
    for x in range(width - 3):
        y = 57  # 957 on screen, adjusted for the screenshot's top at 900
        
        if all(0 <= x + dx < width and 0 <= y + dy < height and 
               is_white(screenshot[y + dy, x + dx]) for dx, dy in DIVIDER_PATTERN):
            
            surrounding_coords = [
                (dx, dy) for dx in range(-1, 5) for dy in range(-20, 1)
                if (dx, dy) not in DIVIDER_PATTERN
            ]
            
            if all(0 <= x + dx < width and 0 <= y + dy < height and 
                   not is_white(screenshot[y + dy, x + dx]) for dx, dy in surrounding_coords):
                return x, y
    
    return None

def detect_ammo(sct):
    if not easyocr_available:
        return None, None
    
    screenshot = np.array(sct.grab({'left': 1200, 'top': 900, 'width': 800, 'height': 200}))
    screenshot = cv2.cvtColor(screenshot, cv2.COLOR_RGBA2BGR)
    
    divider_pos = detect_divider(screenshot)
    
    if divider_pos:
        divider_x, _ = divider_pos
        
        current_ammo_area = {'left': divider_x + 1200 - 75, 'top': AMMO_Y_COORDS['current'][0], 
                             'width': 75, 'height': AMMO_Y_COORDS['current'][1] - AMMO_Y_COORDS['current'][0]}
        reserve_ammo_area = {'left': divider_x + 1200 + 7, 'top': AMMO_Y_COORDS['reserve'][0], 
                             'width': 40, 'height': AMMO_Y_COORDS['reserve'][1] - AMMO_Y_COORDS['reserve'][0]}
        
        current_ammo_screenshot = np.array(sct.grab(current_ammo_area))
        reserve_ammo_screenshot = np.array(sct.grab(reserve_ammo_area))
        
        current_ammo = detect_ammo_count(current_ammo_screenshot)
        reserve_ammo = detect_ammo_count(reserve_ammo_screenshot)
        
        return current_ammo, reserve_ammo
    else:
        print("Failed to detect ammo divider.")
        return None, None

def detect_ammo_count(ammo_screenshot):
    if not easyocr_available:
        return None
    
    gray = cv2.cvtColor(ammo_screenshot, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY)
    if np.mean(binary) > 127:
        binary = cv2.bitwise_not(binary)
    binary = cv2.resize(binary, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    
    results = reader.readtext(binary, allowlist='0123456789', paragraph=False, min_size=10, text_threshold=0.5)
    
    if results:
        ammo_text = results[0][1]
        return int(ammo_text) if ammo_text.isdigit() else None
    return None

def detect_attachments(sct):
    screenshot = np.array(sct.grab({'left': ATTACHMENT_DETECTION_AREA[0], 'top': ATTACHMENT_DETECTION_AREA[1], 
                                    'width': ATTACHMENT_DETECTION_AREA[2] - ATTACHMENT_DETECTION_AREA[0], 
                                    'height': ATTACHMENT_DETECTION_AREA[3] - ATTACHMENT_DETECTION_AREA[1]}))
    
    _, binary_screenshot = cv2.threshold(cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY), 254, 255, cv2.THRESH_BINARY)
    
    detected_attachments = {}
    
    for attachment_type in ["Scope", "Magazine", "Underbarrel", "Barrel"]:
        best_match, best_score = max(
            ((name, cv2.matchTemplate(binary_screenshot, template, cv2.TM_CCOEFF_NORMED).max())
             for name, template in attachment_images[attachment_type].items()),
            key=lambda x: x[1]
        )
        
        if best_score > CONFIDENCE_THRESHOLD:
            detected_attachments[attachment_type] = best_match
    
    return detected_attachments

def initialize_hotbar_detection():
    load_reference_images()
    load_attachment_images()