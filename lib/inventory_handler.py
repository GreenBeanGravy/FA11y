import threading
import time
import queue
import pyautogui
from mss import mss
import numpy as np
import os
import pickle
import difflib
from accessible_output2.outputs.auto import Auto
from lib.utilities import read_config
from lib.input_handler import is_key_pressed, VK_KEYS
from lib.background_checks import monitor

class InventoryHandler:
    def __init__(self):
        self.speaker = Auto()
        self.current_slot = 0
        self.current_section = "bottom"  # "bottom", "ammo", or "resources"
        self.dragging = False
        self.monitoring_thread = None
        self.movement_thread = None
        self.stop_monitoring = threading.Event()
        self.movement_queue = queue.Queue()
        self.sct = None  # Will be initialized in the monitor thread
        
        # Item change detection
        self.last_detected_type = None
        self.last_check_time = 0
        self.last_navigation_time = 0
        
        # OCR detection
        self.ocr_cooldown = 0.5  # Increased cooldown to prevent multiple triggers
        self.ocr_lock = threading.Lock()  # Lock to prevent concurrent OCR
        self.easyocr_available = False
        self.easyocr_ready = threading.Event()
        self.easyocr_lock = threading.Lock()
        self.reader = None
        self.ocr_thread = None
        self.last_announced_item = None
        self.last_announcement_time = 0
        self.announcement_cooldown = 1.0  # 1 second cooldown between announcements
        
        # Rarity colors
        self.rarity_colors = {
            'Common': (116, 122, 128), 
            'Uncommon': (0, 128, 5), 
            'Rare': (0, 88, 191),
            'Epic': (118, 45, 211), 
            'Legendary': (191, 79, 0), 
            'Mythic': (191, 147, 35),
            'Exotic': (118, 191, 255),
        }
        self.rarity_tolerance = 15  # Increased tolerance for better matching
        
        # Item names cache - only cache names, not rarity
        self.item_names = []
        self.slot_name_cache = {}  # Cache only names, not rarity
        self.load_item_names()
        
        # Initialize OCR in background
        self.initialize_easyocr()
        
        # Mouse movement parameters
        self.MOVEMENT_DURATION = 0.07
        self.MOVEMENT_STEPS = 15
        
        # Key state tracking
        self.key_states = {
            'left': False,
            'right': False,
            'space': False,
            'up': False,
            'down': False
        }
        
        # Bottom section slots (hotbar)
        self.bottom_slots = [
            (1265, 820),  # Slot 1
            (1396, 820),  # Slot 2
            (1528, 820),  # Slot 3
            (1664, 820),  # Slot 4
            (1794, 820)   # Slot 5
        ]
        
        # Ammo section slots
        self.ammo_slots = [
            (1259, 467),  # Arrows
            (1339, 467),  # Heavy Bullets
            (1420, 467),  # Light Bullets
            (1500, 467),  # Medium Bullets
            (1577, 467),  # Rockets
            (1659, 467)   # Shells
        ]

        # Fixed positions for sections
        self.section_positions = {
            "resources": (1196, 375),
            "ammo": (1196, 468),
            "bottom": None  # Uses slot positions
        }

        # Detection patterns
        self.ammo_detection = {
            "Arrows": [
                (1286, 654), (1292, 642), (1294, 655), (1290, 652), (1374, 645),
                (1371, 641), (1366, 646), (1372, 651), (1365, 654)
            ],
            "Heavy Bullets": [
                (1286, 654), (1289, 643), (1291, 650), (1297, 641), (1293, 655),
                (1446, 645), (1443, 641), (1438, 646), (1445, 651), (1436, 653)
            ],
            "Light Bullets": [
                (1289, 642), (1285, 655), (1292, 655), (1435, 644), (1432, 641),
                (1427, 646), (1434, 651), (1425, 653)
            ],
            "Medium Bullets": [
                (1286, 655), (1291, 642), (1293, 652), (1301, 642), (1299, 656),
                (1464, 644), (1461, 641), (1456, 646), (1463, 651), (1454, 653)
            ],
            "Rockets": [
                (1286, 655), (1292, 641), (1296, 644), (1293, 655), (1290, 650),
                (1379, 645), (1376, 641), (1370, 646), (1378, 651), (1369, 653)
            ],
            "Shells": [
                (1296, 644), (1293, 641), (1288, 646), (1295, 651), (1286, 653),
                (1358, 644), (1356, 641), (1349, 646), (1357, 651), (1348, 653)
            ]
        }

        self.resource_detection = {
            "Wood": [
                (1206, 643), (1205, 655), (1214, 643), (1215, 656),
                (1221, 642), (1256, 642), (1264, 649), (1254, 656)
            ],
            "Stone": [
                (1214, 644), (1211, 640), (1206, 646), (1213, 651),
                (1203, 653), (1268, 643), (1262, 649), (1265, 655),
                (1266, 649), (1262, 642), (1259, 655)
            ],
            "Metal": [
                (1203, 654), (1208, 642), (1211, 653), (1219, 642),
                (1217, 656), (1265, 642), (1262, 655), (1269, 654)
            ]
        }
        
        # Common OCR misreads dictionary
        self.ocr_corrections = {
            "bust an": "burst ar",
            "bust a": "burst ar",
            "bunt ar": "burst ar",
            "bust ap": "burst smg",
            "burst arp": "burst smg",
            "bust sag": "burst smg",
            "ares": "ares'",
            "modular": "warforged",
            "wapforged": "warforged",
            "assaut": "assault",
            "assaul": "assault",
            "at": "ar"
        }
        
        # Start threads
        self.start_monitoring()
        self.start_movement_handler()

    def load_item_names(self):
        """Load item names from the cache file used by hotbar.py"""
        try:
            images_folder = "images"
            cache_file = os.path.join(images_folder, "image_cache.pkl")
            
            if os.path.exists(cache_file):
                with open(cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                
                # Extract name without extensions and strip rarity prefixes
                rarity_prefixes = ["Common ", "Uncommon ", "Rare ", "Epic ", "Legendary ", "Mythic ", "Exotic "]
                for image_name in cache_data.keys():
                    name_without_ext = os.path.splitext(image_name)[0]
                    
                    # Store both the full name and clean name (without rarity prefix)
                    clean_name = name_without_ext
                    for prefix in rarity_prefixes:
                        if name_without_ext.startswith(prefix):
                            clean_name = name_without_ext[len(prefix):]
                            break
                    
                    self.item_names.append((name_without_ext, clean_name))
                
                print(f"Loaded {len(self.item_names)} item names from cache")
            else:
                print(f"Cache file not found at {cache_file}")
        except Exception as e:
            print(f"Error loading item names: {e}")

    def find_closest_match(self, ocr_text):
        """Find the closest matching item name to the OCR text"""
        if not self.item_names or not ocr_text:
            return ocr_text
            
        # Clean OCR text
        ocr_text = ocr_text.lower()
        
        # Apply common OCR corrections
        for misread, correction in self.ocr_corrections.items():
            if misread in ocr_text:
                ocr_text = ocr_text.replace(misread, correction)
        
        best_match = None
        highest_ratio = 0
        best_clean_name = None
        
        # Find best matching clean name (without rarity prefix)
        for full_name, clean_name in self.item_names:
            # Calculate similarity ratios against the clean name
            ratio = difflib.SequenceMatcher(None, ocr_text, clean_name.lower()).ratio()
            
            if ratio > highest_ratio and ratio > 0.4:  # Lower threshold to catch more matches
                highest_ratio = ratio
                best_match = full_name
                best_clean_name = clean_name
        
        if best_clean_name:
            print(f"Matched OCR: '{ocr_text}' to '{best_clean_name}' (from '{best_match}') with ratio {highest_ratio:.2f}")
            return best_clean_name  # Return the clean name without rarity
        
        return ocr_text

    def detect_rarity(self, x, y):
        """Detect item rarity based on a single point with increased tolerance."""
        try:
            # Check pixel 5 to the left of the white pixel
            rarity_pixel_x = x - 5
            rarity_pixel_color = pyautogui.pixel(rarity_pixel_x, y)
            
            # Compare with known rarity colors
            for rarity, color in self.rarity_colors.items():
                # Check if within tolerance
                if all(abs(a - b) <= self.rarity_tolerance for a, b in zip(rarity_pixel_color, color)):
                    return rarity
            
            return ""  # No matching rarity found
        except Exception as e:
            print(f"Error detecting rarity: {e}")
            return ""

    def initialize_easyocr(self):
        """Initialize EasyOCR in a background thread."""
        def load_easyocr():
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore')
                try:
                    import easyocr
                    with self.easyocr_lock:
                        self.reader = easyocr.Reader(['en'])
                        self.easyocr_available = True
                except Exception as e:
                    print(f"EasyOCR initialization failed: {e}")
                    self.easyocr_available = False
                finally:
                    self.easyocr_ready.set()

        threading.Thread(target=load_easyocr, daemon=True).start()

    def smooth_move_to(self, x, y):
        """Queue a smooth movement request"""
        self.movement_queue.put((x, y))

    def handle_movement_queue(self):
        """Handle movement requests in a separate thread"""
        while not self.stop_monitoring.is_set():
            try:
                x, y = self.movement_queue.get(timeout=0.01)
                self._execute_movement(x, y)
                self.movement_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in movement handler: {e}")

    def _execute_movement(self, target_x, target_y):
        """Execute the actual movement - runs in movement thread"""
        start_x, start_y = pyautogui.position()
        
        # Optimize if we're already close to target
        if abs(start_x - target_x) < 5 and abs(start_y - target_y) < 5:
            pyautogui.moveTo(target_x, target_y, _pause=False)
            return

        def ease_out_cubic(t):
            """Cubic easing - faster acceleration, smooth deceleration"""
            return 1 - pow(1 - t, 3)

        for step in range(self.MOVEMENT_STEPS + 1):
            if self.stop_monitoring.is_set():
                break
                
            t = step / self.MOVEMENT_STEPS
            eased_t = ease_out_cubic(t)
            
            current_x = int(start_x + (target_x - start_x) * eased_t)
            current_y = int(start_y + (target_y - start_y) * eased_t)
            
            pyautogui.moveTo(current_x, current_y, _pause=False)
            time.sleep(self.MOVEMENT_DURATION / self.MOVEMENT_STEPS)

    def check_pixel_color(self, x, y, target_color):
        """Check if the pixel at the given location matches the target color."""
        try:
            pixel_color = pyautogui.pixel(x, y)
            return pixel_color == target_color
        except Exception as e:
            print(f"Error checking pixel color: {e}")
            return False

    def perform_ocr_for_slot(self, slot_index):
        """Perform OCR for a specific slot."""
        if not self.easyocr_available or not self.easyocr_ready.is_set():
            return
            
        # Use a lock to prevent concurrent OCR operations
        if not self.ocr_lock.acquire(blocking=False):
            return
            
        try:
            # Define the OCR area based on known UI layout
            ocr_area = {
                'left': 1195, 
                'top': 610, 
                'width': 561, 
                'height': 100
            }
            
            # Check if we've already OCRed this slot name (but always check rarity)
            cached_name = self.slot_name_cache.get(slot_index)
            
            # If we have the name cached, skip OCR and just check rarity
            if cached_name:
                self.check_rarity_and_announce(cached_name, slot_index)
            else:
                # Start OCR in separate thread
                self.ocr_thread = threading.Thread(
                    target=self.ocr_worker, 
                    args=(ocr_area, slot_index),
                    daemon=True
                )
                self.ocr_thread.start()
            
        finally:
            self.ocr_lock.release()
    
    def check_rarity_and_announce(self, item_name, slot_index):
        """Check rarity and announce the full item name."""
        # Check for rarity by checking the white pixel positions
        rarity = ""
        rarity_check_locations = [(1210, 684), (1210, 657)]
        for x, y in rarity_check_locations:
            if self.check_pixel_color(x, y, (255, 255, 255)):
                rarity = self.detect_rarity(x, y)
                if rarity:
                    break
        
        # Combine rarity with item name
        full_item_name = f"{rarity} {item_name}" if rarity else item_name
        
        # Check if we should announce this item
        if self.should_announce(full_item_name):
            self.speaker.speak(full_item_name)
            print(f"Slot {slot_index+1}: {full_item_name}")
    
    def ocr_worker(self, ocr_area, slot_index):
        """Worker thread for OCR processing."""
        try:
            with mss() as sct:
                screenshot = np.array(sct.grab(ocr_area))
            
            # Process the image for better OCR results
            import cv2
            if screenshot.shape[2] == 4:  # BGRA format
                screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
                
            # Convert to grayscale
            gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
            
            # Apply thresholding to isolate text
            _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
            
            # Perform OCR
            with self.easyocr_lock:
                results = self.reader.readtext(binary, detail=0)
            
            if results:
                # Combine all detected text and convert to lowercase
                ocr_text = ' '.join(results).lower()
                
                # Find the closest match in known item names
                matched_item = self.find_closest_match(ocr_text)
                
                # Cache only the item name
                self.slot_name_cache[slot_index] = matched_item
                
                # Get fresh rarity and announce
                self.check_rarity_and_announce(matched_item, slot_index)
                
        except Exception as e:
            print(f"Error in OCR worker: {e}")
    
    def should_announce(self, item_name):
        """Check if we should announce this item based on cooldown."""
        current_time = time.time()
        
        # Don't repeat the same announcement
        if item_name == self.last_announced_item:
            if current_time - self.last_announcement_time < self.announcement_cooldown:
                return False
        
        # Update tracking state
        self.last_announced_item = item_name
        self.last_announcement_time = current_time
        return True

    def detect_item_type(self):
        """Detect the type of item in the current slot based on pixel colors"""
        if self.current_section == "ammo":
            patterns = self.ammo_detection
            default = "Empty Ammo Slot"
            # Region for ammo detection
            capture_region = {
                'left': 1280,
                'top': 640,
                'width': 200,
                'height': 50
            }
        elif self.current_section == "resources":
            patterns = self.resource_detection
            default = "Empty Resource Slot"
            # Region for resource detection
            capture_region = {
                'left': 1200,
                'top': 640,
                'width': 100,
                'height': 50
            }
        else:
            return None

        try:
            screenshot = np.array(self.sct.grab(capture_region))
            
            for item_type, pixels in patterns.items():
                all_match = True
                for x, y in pixels:
                    # Adjust coordinates to be relative to the screenshot
                    rel_x = x - capture_region['left']
                    rel_y = y - capture_region['top']
                    pixel = screenshot[rel_y, rel_x][:3]
                    if not np.array_equal(pixel, [255, 255, 255]):
                        all_match = False
                        break
                if all_match:
                    return item_type
            
            return default
            
        except Exception as e:
            print(f"Error in item detection: {e}")
            return "Detection Error"

    def navigate_to_slot(self, slot_index):
        """Move to a specific inventory slot"""
        self.last_navigation_time = time.time()
        
        if self.current_section == "bottom":
            slots = self.bottom_slots
            self.smooth_move_to(slots[slot_index][0], slots[slot_index][1])
            self.speaker.speak(f"Slot {slot_index + 1}")
            
            # After a small delay, perform OCR for the slot
            threading.Timer(0.2, self.perform_ocr_for_slot, args=[slot_index]).start()
        else:  # ammo or resources section
            time.sleep(0.01)  # Wait for UI to update
            item_type = self.detect_item_type()
            self.speaker.speak(item_type)
            # Update last known type and reset check timer
            self.last_detected_type = item_type
            self.last_check_time = time.time()

    def handle_vertical_navigation(self, direction):
        """Handle up/down navigation between sections with wrapping"""
        if not monitor.inventory_open:
            return
            
        sections = ["resources", "ammo", "bottom"]
        current_index = sections.index(self.current_section)
        
        if direction == 'up':
            new_index = (current_index - 1) % len(sections)
        else:  # down
            new_index = (current_index + 1) % len(sections)
            
        new_section = sections[new_index]
        self.current_section = new_section
        self.current_slot = 0
        
        # Clear name cache when changing sections
        self.slot_name_cache.clear()
        
        # Announce section name and initial item
        if new_section == "bottom":
            self.speaker.speak("Hotbar")
            self.navigate_to_slot(0)
        else:
            # Move to fixed section position and announce
            position = self.section_positions[new_section]
            self.smooth_move_to(position[0], position[1])
            section_name = new_section.capitalize()
            self.speaker.speak(section_name)
            
            # Wait and detect initial item
            time.sleep(0.01)
            item_type = self.detect_item_type()
            self.speaker.speak(item_type)
            
            # Initialize tracking
            self.last_detected_type = item_type
            self.last_check_time = time.time()
            self.last_navigation_time = time.time()

    def handle_horizontal_navigation(self, direction):
        """Handle left/right navigation within a section"""
        if not monitor.inventory_open:
            return
            
        if self.current_section == "bottom":
            max_slots = len(self.bottom_slots)
        elif self.current_section == "ammo":
            max_slots = len(self.ammo_slots)
        else:  # resources
            max_slots = len(self.resource_detection)
            
        if direction == 'left':
            self.current_slot = (self.current_slot - 1) % max_slots
        else:  # right
            self.current_slot = (self.current_slot + 1) % max_slots
            
        self.navigate_to_slot(self.current_slot)

    def handle_space(self):
        """Toggle drag state - only works in bottom section"""
        if not monitor.inventory_open or self.current_section != "bottom":
            return
        self.dragging = not self.dragging
        if self.dragging:
            pyautogui.mouseDown(button='left', _pause=False)
            self.speaker.speak("Dragging")
        else:
            pyautogui.mouseUp(button='left', _pause=False)
            self.speaker.speak("Released")

    def check_key_press(self, key):
        """Check for a single key press without repeat"""
        key_pressed = is_key_pressed(key)
        was_pressed = self.key_states[key]
        
        if key_pressed and not was_pressed:
            self.key_states[key] = True
            return True
        elif not key_pressed and was_pressed:
            self.key_states[key] = False
        
        return False

    def check_item_changes(self):
        """Check for changes in item type"""
        if self.current_section not in ["ammo", "resources"]:
            return None
            
        current_time = time.time()
        
        # Don't check for changes if we recently navigated
        if current_time - self.last_navigation_time < 0.5:
            return None
            
        # Only check every 0.5 seconds
        if current_time - self.last_check_time < 0.5:
            return None
            
        self.last_check_time = current_time
        current_type = self.detect_item_type()
        
        if self.last_detected_type is not None and current_type != self.last_detected_type:
            self.last_detected_type = current_type
            return current_type
            
        self.last_detected_type = current_type
        return None

    def monitor_inventory(self):
        """Monitor inventory state and handle key presses"""
        prev_inventory_state = False
        
        # Initialize MSS in the monitoring thread
        self.sct = mss()
        
        while not self.stop_monitoring.is_set():
            try:
                current_inventory_state = monitor.inventory_open
                
                # Handle inventory state change
                if current_inventory_state != prev_inventory_state:
                    if current_inventory_state:
                        # Clear slot cache when opening inventory
                        self.slot_name_cache.clear()
                        self.current_section = "bottom"
                        self.current_slot = 0
                        self.last_detected_type = None
                        self.last_announced_item = None
                        self.navigate_to_slot(0)
                    elif self.dragging:
                        pyautogui.mouseUp(button='left', _pause=False)
                        self.dragging = False
                
                # Handle input based on current state
                if current_inventory_state:
                    # Regular inventory navigation
                    if self.current_section in ["ammo", "resources"]:
                        changed_type = self.check_item_changes()
                        if changed_type:
                            self.speaker.speak(changed_type)
                    
                    if self.check_key_press('left'):
                        self.handle_horizontal_navigation('left')
                    elif self.check_key_press('right'):
                        self.handle_horizontal_navigation('right')
                    elif self.check_key_press('up'):
                        self.handle_vertical_navigation('up')
                    elif self.check_key_press('down'):
                        self.handle_vertical_navigation('down')
                    elif self.check_key_press('space'):
                        self.handle_space()
                
                prev_inventory_state = current_inventory_state
                time.sleep(0.001)
                
            except Exception as e:
                print(f"Error in inventory monitor: {e}")
                time.sleep(0.1)

    def start_movement_handler(self):
        """Start the movement handling thread"""
        self.movement_thread = threading.Thread(target=self.handle_movement_queue, daemon=True)
        self.movement_thread.start()

    def start_monitoring(self):
        """Start the inventory monitoring thread"""
        if self.monitoring_thread is None or not self.monitoring_thread.is_alive():
            self.stop_monitoring.clear()
            self.monitoring_thread = threading.Thread(target=self.monitor_inventory, daemon=True)
            self.monitoring_thread.start()

    def stop(self):
        """Stop all threads and cleanup"""
        self.stop_monitoring.set()
        if self.dragging:
            pyautogui.mouseUp(button='left', _pause=False)
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=1.0)
        if self.movement_thread:
            self.movement_thread.join(timeout=1.0)
        if self.sct:
            self.sct.close()

# Create a single instance
inventory_handler = InventoryHandler()