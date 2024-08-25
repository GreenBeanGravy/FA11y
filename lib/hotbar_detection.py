import cv2
import numpy as np
import os
import time
from mss import mss
from accessible_output2.outputs.auto import Auto
import easyocr
from threading import Thread, Event, Lock
from queue import Queue, Empty
import configparser

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
CONFIDENCE_THRESHOLD = 0.80
sct_lock = Lock()

ATTACHMENT_COORDS = {
    0: [1516, 1537, 1556, 1575],  # SLOT 1 Y915
    1: [1600, 1619, 1638, 1657],  # SLOT 2 Y915
    2: [1681, 1700, 1719, 1738],  # SLOT 3 Y915
    3: [1762, 1781, 1800, 1819],  # SLOT 4 Y915
    4: [1843, 1862, 1881, 1900]   # SLOT 5 Y915
}

ATTACHMENTS = [
    "Scope", "Magazine", "Underbarrel", "Barrel"
]

AMMO_RESERVE_COORDS = [
    ((1527, 966), (1559, 983)),  # Slot 1
    ((1605, 966), (1642, 983)),  # Slot 2
    ((1686, 966), (1723, 983)),  # Slot 3
    ((1770, 966), (1804, 983)),  # Slot 4
    ((1850, 966), (1887, 983))   # Slot 5
]

speaker = Auto()
reference_images = {}
reader = easyocr.Reader(['en'])
sct = mss()

current_detection_thread = None
stop_event = Event()
speech_queue = Queue()

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

def speak_thread():
    while True:
        try:
            message = speech_queue.get(timeout=0.1)
            speaker.speak(message)
            speech_queue.task_done()
        except Empty:
            continue

def detect_hotbar_item(slot_index):
    global current_detection_thread, stop_event
    
    if current_detection_thread and current_detection_thread.is_alive():
        stop_event.set()
        current_detection_thread.join()
    
    stop_event.clear()
    
    current_detection_thread = Thread(target=detect_hotbar_item_thread, args=(slot_index,))
    current_detection_thread.start()

def detect_hotbar_item_thread(slot_index):
    with sct_lock:
        sct = mss()  # Create a new mss instance for this thread

    # Load configuration
    config = configparser.ConfigParser()
    config.read('config.txt')
    announce_attachments = config.getboolean('SETTINGS', 'AnnounceWeaponAttachments', fallback=True)

    def check_slot(coord):
        with sct_lock:
            screenshot = cv2.cvtColor(np.array(sct.grab(coord)), cv2.COLOR_RGBA2RGB)
        return max(((name, pixel_based_matching(screenshot, ref_img)) 
                    for name, ref_img in reference_images.items()), 
                   key=lambda x: x[1])

    best_match_name, best_score = check_slot(SLOT_COORDS[slot_index])
    
    if best_score <= CONFIDENCE_THRESHOLD:
        time.sleep(0.05)  # Reinstated delay
        best_match_name, best_score = check_slot(SECONDARY_SLOT_COORDS[slot_index])
    
    if best_score > CONFIDENCE_THRESHOLD and not stop_event.is_set():
        speech_queue.put(best_match_name)
        
        if announce_attachments:
            time.sleep(0.05)
            
            detected_attachments = []
            y_coord = 915
            for i, x_coord in enumerate(ATTACHMENT_COORDS[slot_index]):
                with sct_lock:
                    screenshot = np.array(sct.grab({'left': x_coord, 'top': y_coord, 'width': 1, 'height': 1}))
                color = screenshot[0, 0, :3]
                if tuple(color) == (255, 255, 255):
                    detected_attachments.append(ATTACHMENTS[i])
            
            if detected_attachments and not stop_event.is_set():
                if len(detected_attachments) == 1:
                    attachment_message = f"with a {detected_attachments[0]}"
                else:
                    attachment_message = "with a " + ", ".join(detected_attachments[:-1]) + f", and {detected_attachments[-1]}"
                speech_queue.put(attachment_message)
        
        time.sleep(0.05)
        
        if not stop_event.is_set():
            ammo_coords = AMMO_RESERVE_COORDS[slot_index]
            with sct_lock:
                ammo_screenshot = np.array(sct.grab({'left': ammo_coords[0][0], 'top': ammo_coords[0][1], 
                                                    'width': ammo_coords[1][0] - ammo_coords[0][0], 
                                                    'height': ammo_coords[1][1] - ammo_coords[0][1]}))
            
            gray = cv2.cvtColor(ammo_screenshot, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            
            results = reader.readtext(binary)
            if results and not stop_event.is_set():
                ammo_text = results[0][1]
                speech_queue.put(f"with {ammo_text} ammo in reserves")

def initialize_hotbar_detection():
    load_reference_images()
    speech_thread = Thread(target=speak_thread, daemon=True)
    speech_thread.start()