import cv2
import numpy as np
import os
import time
from mss import mss
from accessible_output2.outputs.auto import Auto
from threading import Thread, Event
import configparser
from lib.utilities import read_config, get_config_boolean
import zlib
import pickle
from pathlib import Path
from threading import Thread, Event, Lock
from queue import Queue


# Screen coordinates for weapon slots (left, top, right, bottom)
SLOT_COORDS = [
    (1502, 931, 1565, 975),  # Slot 1
    (1583, 931, 1646, 975),  # Slot 2
    (1665, 931, 1728, 975),  # Slot 3
    (1747, 931, 1810, 975),  # Slot 4
    (1828, 931, 1891, 975)   # Slot 5
]

# Secondary slots are slightly above primary slots
SECONDARY_SLOT_COORDS = [(x, y-11, x2, y2-11) for x, y, x2, y2 in SLOT_COORDS]

# Area we use to check the uses/ammo a consumable item has remaining
CONSUMABLE_COUNT_AREA = (1314, 927, 1392, 971)

# Directory configuration
IMAGES_FOLDER = "images"
ATTACHMENTS_FOLDER = "attachments"

# Detection settings
CONFIDENCE_THRESHOLD = 0.82  # Minimum confidence for positive detection
ATTACHMENT_DETECTION_AREA = (1240, 1000, 1410, 1070)  # Area to scan for attachments
AMMO_Y_COORDS = {
    'current': (929, 962),  # Current magazine ammo count position
    'reserve': (936, 962)   # Reserve ammo count position
}

# Pattern for detecting the ammo count divider
DIVIDER_PATTERN = [
    (0, 0), (0, -1), (0, -2), (0, -3),
    (1, -5), (1, -6), (1, -7), (1, -8), (1, -9),
    (2, -10), (2, -11), (2, -12), (2, -13), (2, -14),
    (3, -16), (3, -17), (3, -18), (3, -19)
]

class ImageCache:
    """Handles loading and managing cached weapon images."""
    
    def __init__(self, compression_level: int = 6):
        """
        Initialize the image cache.
        
        Args:
            compression_level (int): zlib compression level (0-9)
        """
        self.compression_level = compression_level
        self.cache = {}
    
    def load_cached_image(self, image_name: str, cache_file: str = "image_cache.pkl") -> np.ndarray:
        """
        Load and decompress an image from the cache.
        
        Args:
            image_name (str): Name of the image to load
            cache_file (str): Path to the cache file
            
        Returns:
            np.ndarray: Decompressed image as numpy array, or None if failed
        """
        try:
            # Load cache if not already loaded
            if not self.cache:
                with open(cache_file, 'rb') as f:
                    self.cache = pickle.load(f)
            
            if image_name in self.cache:
                # Decompress the image data
                compressed_data = self.cache[image_name]['data']
                decompressed_data = zlib.decompress(compressed_data)
                # Convert bytes back to numpy array
                nparr = np.frombuffer(decompressed_data, np.uint8)
                return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return None
        except Exception as e:
            print(f"Error loading {image_name} from cache: {str(e)}")
            return None

# Initialize global variables
speaker = Auto()  # Text-to-speech output
reference_images = {}  # Cached weapon images
attachment_images = {}  # Attachment images
image_cache = ImageCache()  # Image cache manager

# Thread control
current_detection_thread = None
timer_thread = None
stop_event = Event()
timer_stop_event = Event()

# OCR related globals
easyocr_available = False  # Flag for OCR availability
easyocr_ready = Event()  # Event to signal when EasyOCR is ready
easyocr_lock = Lock()  # Lock for thread-safe access to OCR reader
reader = None  # Global OCR reader instance

def initialize_easyocr():
    """Initialize EasyOCR in a background thread."""
    global reader, easyocr_available

    def load_easyocr():
        global reader, easyocr_available
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore')
            try:
                import easyocr
                with easyocr_lock:
                    reader = easyocr.Reader(['en'], recognizer='number')
                    easyocr_available = True
                # print("EasyOCR successfully initialized")
            except Exception as e:
                print(f"EasyOCR initialization failed: {e}")
                easyocr_available = False
            finally:
                easyocr_ready.set()

    # Start loading EasyOCR in background
    Thread(target=load_easyocr, daemon=True).start()
    # print("EasyOCR loading started in background")

initialize_easyocr()

def load_images(folder, is_attachment=False):
    """
    Load images from a folder (used for attachments only).
    
    Args:
        folder (str): Path to the images folder
        is_attachment (bool): Whether loading attachment images
        
    Returns:
        dict: Dictionary of loaded images
    """
    images = {}
    for filename in os.listdir(folder):
        if filename.lower().endswith((".png", ".jpg", ".jpeg")):
            img = cv2.imread(os.path.join(folder, filename))
            if img is not None:
                name = os.path.splitext(filename)[0]
                if is_attachment:
                    # Convert attachment images to binary for better matching
                    _, img = cv2.threshold(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 254, 255, cv2.THRESH_BINARY)
                images[name] = img
    return images

def load_reference_images():
    """
    Load weapon images from the cache file and resize them to slot dimensions.
    """
    global reference_images
    slot_width = SLOT_COORDS[0][2] - SLOT_COORDS[0][0]
    slot_height = SLOT_COORDS[0][3] - SLOT_COORDS[0][1]
    
    cache_file = os.path.join(IMAGES_FOLDER, "image_cache.pkl")
    if not os.path.exists(cache_file):
        raise FileNotFoundError(f"Cache file not found at {cache_file}")
    
    # Load all images from cache
    with open(cache_file, 'rb') as f:
        cached_data = pickle.load(f)
    
    for image_name in cached_data.keys():
        # Strip the file extension from the image name
        name_without_ext = os.path.splitext(image_name)[0]
        img = image_cache.load_cached_image(image_name, cache_file)
        if img is not None:
            reference_images[name_without_ext] = cv2.resize(img, (slot_width, slot_height))

def load_attachment_images():
    """Load all attachment images from their respective folders."""
    global attachment_images
    for attachment_type in ["Scope", "Magazine", "Underbarrel", "Barrel"]:
        folder_path = os.path.join(ATTACHMENTS_FOLDER, attachment_type)
        attachment_images[attachment_type] = load_images(folder_path, is_attachment=True)

def pixel_based_matching(screenshot, template, threshold=30):
    """
    Compare screenshot with template using pixel-based matching.
    
    Args:
        screenshot (np.ndarray): Screenshot to compare
        template (np.ndarray): Template to match against
        threshold (int): Maximum allowed difference per pixel
        
    Returns:
        float: Matching confidence score (0-1)
    """
    if screenshot.shape != template.shape:
        return 0
    diff = np.abs(screenshot.astype(np.int32) - template.astype(np.int32))
    matching_pixels = np.sum(np.all(diff <= threshold, axis=2))
    return matching_pixels / (screenshot.shape[0] * screenshot.shape[1])

def timer_thread_function(delay, function, *args):
    """
    Execute a function after a delay unless stopped.
    
    Args:
        delay (float): Delay in seconds
        function (callable): Function to execute
        *args: Arguments to pass to the function
    """
    time.sleep(delay)
    if not timer_stop_event.is_set():
        function(*args)

def check_slot(coord):
    """
    Check a slot for weapon matches.
    
    Args:
        coord (tuple): Screen coordinates to check (left, top, right, bottom)
        
    Returns:
        tuple: (weapon_name, confidence_score)
    """
    with mss() as sct:
        screenshot = cv2.cvtColor(np.array(sct.grab(coord)), cv2.COLOR_RGBA2RGB)
    return max(((name, pixel_based_matching(screenshot, ref_img)) 
                for name, ref_img in reference_images.items()), 
               key=lambda x: x[1])

def detect_hotbar_item(slot_index):
    """
    Main function to detect weapon in a hotbar slot.
    
    Args:
        slot_index (int): Index of the slot to check (0-4)
    """
    global current_detection_thread, timer_thread, stop_event, timer_stop_event
    
    # Stop any ongoing detection
    if current_detection_thread and current_detection_thread.is_alive():
        stop_event.set()
    
    if timer_thread and timer_thread.is_alive():
        timer_stop_event.set()
        timer_thread.join()
    
    # Reset stop events
    stop_event.clear()
    timer_stop_event.clear()
    
    # Start new detection thread
    current_detection_thread = Thread(target=detect_hotbar_item_thread, args=(slot_index,))
    current_detection_thread.start()

def detect_hotbar_item_thread(slot_index):
    """
    Thread function for hotbar item detection.
    
    Args:
        slot_index (int): Index of the slot to check (0-4)
    """
    global timer_thread
    
    # Load configuration
    config = configparser.ConfigParser()
    config.read('config.txt')
    announce_attachments_enabled = get_config_boolean(config, 'AnnounceWeaponAttachments', True)
    announce_ammo_enabled = get_config_boolean(config, 'AnnounceAmmo', True)

    # Check primary slot
    best_match_name, best_score = check_slot(SLOT_COORDS[slot_index])
    
    if best_score <= CONFIDENCE_THRESHOLD:
        # If no match in primary slot, check secondary slot
        timer_thread = Thread(target=timer_thread_function, args=(0.05, check_secondary_slot, slot_index))
        timer_thread.start()
        return
    
    if best_score > CONFIDENCE_THRESHOLD and not stop_event.is_set():
        # Announce weapon name
        speaker.speak(best_match_name)
        
        # Announce ammo if enabled
        if easyocr_available and announce_ammo_enabled:
            timer_thread = Thread(target=timer_thread_function, args=(0.1, announce_ammo))
            timer_thread.start()
        
        # Announce attachments if enabled
        if announce_attachments_enabled:
            timer_thread = Thread(target=timer_thread_function, args=(0.4, announce_attachments))
            timer_thread.start()

def check_secondary_slot(slot_index):
    """Check the secondary weapon slot if primary slot check fails."""
    if stop_event.is_set():
        return
    best_match_name, best_score = check_slot(SECONDARY_SLOT_COORDS[slot_index])
    if best_score > CONFIDENCE_THRESHOLD:
        speaker.speak(best_match_name)
        config = configparser.ConfigParser()
        config.read('config.txt')
        announce_ammo_enabled = get_config_boolean(config, 'AnnounceAmmo', True)
        if easyocr_available and announce_ammo_enabled:
            timer_thread = Thread(target=timer_thread_function, args=(0.1, announce_ammo))
            timer_thread.start()

def announce_ammo():
    """Announce current and reserve ammo counts or consumable counts with simplified speech if enabled."""
    if stop_event.is_set() or not easyocr_available:
        return
        
    config = read_config()
    simplify = get_config_boolean(config, 'SimplifySpeechOutput', False)
    
    with mss() as sct:
        current_ammo, reserve_ammo, consumable_count = detect_ammo(sct)
    
    if consumable_count is not None:
        if simplify:
            speaker.speak(f"{consumable_count}")
        else:
            speaker.speak(f"{consumable_count} uses left")
    elif current_ammo is not None or reserve_ammo is not None:
        if simplify:
            speaker.speak(f"{current_ammo or 0} mag {reserve_ammo or 0} reserves")
        else:
            speaker.speak(f"with {current_ammo or 0} ammo in the mag and {reserve_ammo or 0} in reserves")
    else:
        print("OCR failed to detect any values.")

def announce_ammo_manually():
    """Manually announce ammo counts or consumable counts with simplified speech if enabled."""
    config = read_config()
    simplify = get_config_boolean(config, 'SimplifySpeechOutput', False)
    
    sct = mss()
    current_ammo, reserve_ammo, consumable_count = detect_ammo(sct)
    
    if consumable_count is not None:
        if simplify:
            speaker.speak(f"{consumable_count} uses")
        else:
            speaker.speak(f"You have {consumable_count} uses left")
    elif current_ammo is not None or reserve_ammo is not None:
        if simplify:
            speaker.speak(f"{current_ammo or 0} mag {reserve_ammo or 0} reserves")
        else:
            speaker.speak(f"You have {current_ammo or 0} ammo in the mag and {reserve_ammo or 0} in reserves")
    else:
        speaker.speak("No ammo")

def announce_attachments():
    """Announce detected weapon attachments."""
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
    """Check if a pixel is white (used for divider detection)."""
    return np.all(pixel[:3] == [255, 255, 255])

def detect_divider(screenshot):
    """
    Detect the ammo count divider in the screenshot.
    
    Args:
        screenshot (np.ndarray): Screenshot to analyze
        
    Returns:
        tuple: (x, y) coordinates of divider if found, None otherwise
    """
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
    """
    Detect current and reserve ammo counts or consumable count.
    
    Args:
        sct (mss.mss): Screenshot context
        
    Returns:
        tuple: (current_ammo, reserve_ammo, consumable_count)
    """
    if not easyocr_available:
        return None, None, None
    
    screenshot = np.array(sct.grab({'left': 1200, 'top': 900, 'width': 800, 'height': 200}))
    screenshot = cv2.cvtColor(screenshot, cv2.COLOR_RGBA2BGR)
    
    divider_pos = detect_divider(screenshot)
    
    if divider_pos:
        # Regular ammo detection logic
        divider_x, _ = divider_pos
        
        current_ammo_area = {'left': divider_x + 1200 - 75, 'top': AMMO_Y_COORDS['current'][0], 
                             'width': 75, 'height': AMMO_Y_COORDS['current'][1] - AMMO_Y_COORDS['current'][0]}
        reserve_ammo_area = {'left': divider_x + 1200 + 7, 'top': AMMO_Y_COORDS['reserve'][0], 
                             'width': 40, 'height': AMMO_Y_COORDS['reserve'][1] - AMMO_Y_COORDS['reserve'][0]}
        
        current_ammo_screenshot = np.array(sct.grab(current_ammo_area))
        reserve_ammo_screenshot = np.array(sct.grab(reserve_ammo_area))
        
        current_ammo = detect_ammo_count(current_ammo_screenshot)
        reserve_ammo = detect_ammo_count(reserve_ammo_screenshot)
        
        return current_ammo, reserve_ammo, None
    else:
        # Try to detect consumable count
        consumable_area = {'left': CONSUMABLE_COUNT_AREA[0], 'top': CONSUMABLE_COUNT_AREA[1],
                          'width': CONSUMABLE_COUNT_AREA[2] - CONSUMABLE_COUNT_AREA[0],
                          'height': CONSUMABLE_COUNT_AREA[3] - CONSUMABLE_COUNT_AREA[1]}
        
        consumable_screenshot = np.array(sct.grab(consumable_area))
        consumable_count = detect_consumable_count(consumable_screenshot)
        
        if consumable_count is not None:
            return None, None, consumable_count
        
        print("Failed to detect ammo divider or consumable count.")
        return None, None, None

def detect_consumable_count(consumable_screenshot):
    """
    Detect consumable item count from a screenshot using OCR.
    
    Args:
        consumable_screenshot (np.ndarray): Screenshot of consumable count area
        
    Returns:
        int: Detected consumable count or None if detection fails
    """
    global reader, easyocr_available
    
    # Wait for a short time for EasyOCR to be ready
    if not easyocr_ready.wait(timeout=0.1):  # 100ms timeout
        return None
        
    if not easyocr_available:
        return None

    try:
        gray = cv2.cvtColor(consumable_screenshot, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY)
        if np.mean(binary) > 127:
            binary = cv2.bitwise_not(binary)
        binary = cv2.resize(binary, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        
        with easyocr_lock:
            results = reader.readtext(binary, allowlist='0123456789', paragraph=False, min_size=10, text_threshold=0.5)
        
        if results:
            count_text = results[0][1]
            count = int(count_text) if count_text.isdigit() else None
            return count if count and count <= 999 else None
    except Exception as e:
        print(f"Error in consumable count detection: {e}")
    return None

def detect_ammo_count(ammo_screenshot):
    """
    Detect ammo count from a screenshot using OCR.
    
    Args:
        ammo_screenshot (np.ndarray): Screenshot of ammo count area
        
    Returns:
        int: Detected ammo count or None if detection fails
    """
    global reader, easyocr_available
    
    # Wait for a short time for EasyOCR to be ready
    if not easyocr_ready.wait(timeout=0.1):  # 100ms timeout
        return None
        
    if not easyocr_available:
        return None

    try:
        gray = cv2.cvtColor(ammo_screenshot, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY)
        if np.mean(binary) > 127:
            binary = cv2.bitwise_not(binary)
        binary = cv2.resize(binary, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        
        with easyocr_lock:
            results = reader.readtext(binary, allowlist='0123456789', paragraph=False, min_size=10, text_threshold=0.5)
        
        if results:
            ammo_text = results[0][1]
            return int(ammo_text) if ammo_text.isdigit() else None
    except Exception as e:
        print(f"Error in ammo detection: {e}")
    return None

def detect_attachments(sct):
    """
    Detect weapon attachments from a screenshot.
    
    Args:
        sct (mss.mss): Screenshot context
        
    Returns:
        dict: Dictionary of detected attachments by type
    """
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
    """
    Initialize the hotbar detection system.
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        load_reference_images()
        load_attachment_images()
        return True
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Please ensure the image cache file exists in the images folder.")
        return False
    except Exception as e:
        print(f"Error initializing hotbar detection: {e}")
        return False
