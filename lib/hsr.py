from PIL import ImageGrab
from accessible_output2.outputs.auto import Auto
import cv2
import numpy as np
import os
import pickle
import re
from lib.utilities import read_config, get_config_boolean
from mss import mss

speaker = Auto()

# Health and shields detection constants
health_color, shield_color = (158, 255, 99), (110, 235, 255)
health_decreases, shield_decreases = [4, 3, 3], [3, 4, 3]
tolerance = 70

# Rarity detection
last_detected_rarity = None  # For the check_rarity keybind
initialized = False
rarity_mapping = {}  # Cache for filename to rarity mapping

# Screen coordinates for weapon slots (same as in hotbar_detection.py)
SLOT_COORDS = [
    (1502, 931, 1565, 975),  # Slot 1
    (1583, 931, 1646, 975),  # Slot 2
    (1665, 931, 1728, 975),  # Slot 3
    (1747, 931, 1810, 975),  # Slot 4
    (1828, 931, 1891, 975)   # Slot 5
]

def initialize_rarity_mapping():
    """Initialize the rarity mapping from image cache filenames"""
    global rarity_mapping, initialized
    
    if initialized:
        return
    
    cache_file = os.path.join('images', 'image_cache.pkl')
    if not os.path.exists(cache_file):
        print(f"Cache file not found at {cache_file}")
        return
    
    # Load the cache data
    try:
        with open(cache_file, 'rb') as f:
            cached_data = pickle.load(f)
            
        # Extract rarity from filenames
        rarity_pattern = re.compile(r'^(Common|Uncommon|Rare|Epic|Legendary|Mythic|Exotic)_', re.IGNORECASE)
        
        for image_name in cached_data.keys():
            name_without_ext = os.path.splitext(image_name)[0]
            match = rarity_pattern.search(name_without_ext)
            
            if match:
                rarity = match.group(1).capitalize()
                rarity_mapping[name_without_ext] = rarity
                
        initialized = True
        print(f"Initialized rarity mapping with {len(rarity_mapping)} entries")
    except Exception as e:
        print(f"Error initializing rarity mapping: {e}")

def pixel_within_tolerance(pixel_color, target_color, tol):
    return all(abs(pc - tc) <= tol for pc, tc in zip(pixel_color, target_color))

def check_value(pixels, start_x, y, decreases, color, tolerance, name, no_value_msg):
    x = start_x
    for i in range(100, 0, -1):
        if pixel_within_tolerance(pixels[x, y], color, tolerance):
            speaker.speak(f'{i} {name}')
            return
        x -= decreases[i % len(decreases)]
    speaker.speak(no_value_msg)

def check_health_shields():
    """Announce player's current health and shield values"""
    screenshot = ImageGrab.grab(bbox=(0, 0, 1920, 1080))
    pixels = screenshot.load()
    check_value(pixels, 423, 1024, health_decreases, health_color, tolerance, 'Health', 'Cannot find Health Value!')
    check_value(pixels, 423, 984, shield_decreases, shield_color, tolerance, 'Shields', 'No Shields')

def pixel_based_matching(screenshot, template, threshold=30):
    """
    Compare screenshot with template using pixel-based matching.
    Same as in hotbar_detection.py for consistency.
    """
    if screenshot.shape != template.shape:
        return 0
    diff = np.abs(screenshot.astype(np.int32) - template.astype(np.int32))
    matching_pixels = np.sum(np.all(diff <= threshold, axis=2))
    return matching_pixels / (screenshot.shape[0] * screenshot.shape[1])

def load_cached_image(image_name, cache_file, compression_level=6):
    """
    Load and decompress an image from the cache.
    Simplified version of the functionality in ImageCache.
    """
    try:
        with open(cache_file, 'rb') as f:
            cache = pickle.load(f)
        
        if image_name in cache:
            import zlib
            compressed_data = cache[image_name]['data']
            decompressed_data = zlib.decompress(compressed_data)
            nparr = np.frombuffer(decompressed_data, np.uint8)
            return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return None
    except Exception as e:
        print(f"Error loading {image_name} from cache: {str(e)}")
        return None

def extract_rarity_from_filename(filename):
    """Extract rarity from a filename"""
    rarity_pattern = re.compile(r'^(Common|Uncommon|Rare|Epic|Legendary|Mythic|Exotic)_', re.IGNORECASE)
    match = rarity_pattern.search(filename)
    
    if match:
        return match.group(1).capitalize()
    return None

def detect_slot_rarity(slot_index, store_only=False):
    """
    Detect rarity of item in a specific slot.
    
    Args:
        slot_index: Index of the slot to check (0-4)
        store_only: If True, only store the rarity without speaking it
        
    Returns:
        The detected rarity or None if not found
    """
    global last_detected_rarity, rarity_mapping
    
    # Initialize mapping if not already done
    if not initialized:
        initialize_rarity_mapping()
    
    # Get slot screenshot - exact same area as hotbar detection
    with mss() as sct:
        screenshot = cv2.cvtColor(np.array(sct.grab(SLOT_COORDS[slot_index])), cv2.COLOR_RGBA2RGB)
    
    # Use the same cache file and matching logic as hotbar detection
    cache_file = os.path.join('images', 'image_cache.pkl')
    if not os.path.exists(cache_file):
        print(f"Cache file not found at {cache_file}")
        return None
    
    best_match_name = None
    best_score = 0
    
    try:
        # Open cache file
        with open(cache_file, 'rb') as f:
            cached_data = pickle.load(f)
            
        # Find best match
        slot_width = SLOT_COORDS[0][2] - SLOT_COORDS[0][0]
        slot_height = SLOT_COORDS[0][3] - SLOT_COORDS[0][1]
        
        for image_name in cached_data.keys():
            name_without_ext = os.path.splitext(image_name)[0]
            img = load_cached_image(image_name, cache_file)
            
            if img is not None:
                ref_img = cv2.resize(img, (slot_width, slot_height))
                score = pixel_based_matching(screenshot, ref_img)
                
                if score > best_score:
                    best_score = score
                    best_match_name = name_without_ext
        
        # Check if we found a match with reasonable confidence
        confidence_threshold = 0.75  # Slightly lower than hotbar detection to catch more items
        
        if best_score >= confidence_threshold and best_match_name is not None:
            # Get rarity from the filename or mapping
            if best_match_name in rarity_mapping:
                rarity = rarity_mapping[best_match_name]
            else:
                rarity = extract_rarity_from_filename(best_match_name)
                if rarity:
                    rarity_mapping[best_match_name] = rarity
            
            if rarity:
                # Store the rarity
                last_detected_rarity = rarity
                
                # Only speak if requested (not store_only)
                if not store_only:
                    speaker.speak(rarity)
                
                return rarity
            
    except Exception as e:
        print(f"Error checking rarity from cache: {e}")
    
    return None

def process_hotbar_result(slot_index, item_name, confidence):
    """
    Process the result of hotbar detection and store rarity if item was found
    
    Args:
        slot_index: The hotbar slot index (0-4)
        item_name: The detected item name (or None if not detected)
        confidence: The confidence score
        
    Returns:
        bool: True if an item was detected, False otherwise
    """
    global last_detected_rarity
    
    # Initialize mapping if not already done
    if not initialized:
        initialize_rarity_mapping()
    
    if item_name:
        # Item was detected successfully
        print(f"Item detected in slot {slot_index+1}: {item_name} (confidence: {confidence:.2f})")
        
        # Extract rarity from the item name if possible
        if item_name in rarity_mapping:
            rarity = rarity_mapping[item_name]
        else:
            rarity = extract_rarity_from_filename(item_name)
            if rarity:
                rarity_mapping[item_name] = rarity
        
        # Store the rarity without speaking it
        if rarity:
            last_detected_rarity = rarity
            print(f"Stored rarity from item name: {rarity}")
        
        return True
    else:
        # No item detected
        print(f"No item detected in slot {slot_index+1}")
        return False

def check_rarity():
    """
    Keybind handler for check_rarity.
    Announces the last detected rarity.
    """
    global last_detected_rarity
    
    if last_detected_rarity:
        speaker.speak(last_detected_rarity)
    else:
        speaker.speak("No rarity detected yet")