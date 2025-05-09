import threading
import time
import queue
import pyautogui
from mss import mss
import numpy as np
import os
import pickle
import difflib
import cv2
from accessible_output2.outputs.auto import Auto
from lib.utilities import read_config
from lib.input_handler import is_key_pressed
from lib.background_checks import monitor

class InventoryHandler:
    def __init__(self):
        self.speaker = Auto()
        
        # State tracking
        self.current_section = "bottom"  # "bottom", "ammo", or "materials"
        self.current_slot = 0
        self.dragging = False
        self.last_announced_item = None
        self.last_announcement_time = 0
        self.announcement_cooldown = 0.5
        self.last_focused_item = None
        self.navigation_timestamp = 0
        self.ocr_timers = {}
        
        # Threading
        self.monitoring_thread = None
        self.movement_thread = None
        self.stop_monitoring = threading.Event()
        self.movement_queue = queue.Queue()
        self.state_lock = threading.Lock()
        
        # OCR setup
        self.ocr_available = False
        self.ocr_ready = threading.Event()
        self.ocr_lock = threading.Lock()
        self.reader = None
        
        # Mouse movement parameters
        self.MOVEMENT_DURATION = 0.04
        self.MOVEMENT_STEPS = 8
        
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
        
        # Ammo slots with pixel check coordinates (no arrows)
        self.ammo_slots = [
            ("Light Ammo", (1260, 470)),
            ("Medium Ammo", (1340, 470)),
            ("Heavy Ammo", (1420, 470)),
            ("Shells", (1510, 470)),
            ("Rockets", (1580, 470))
        ]
        
        # Material slots with pixel check coordinates
        self.material_slots = [
            ("Wood", (1260, 380)),
            ("Stone", (1340, 380)),
            ("Metal", (1420, 380))
        ]
        
        # OCR regions for count detection
        self.count_regions = {
            # Materials
            "Wood": (1215, 375, 1300, 410),
            "Stone": (1295, 375, 1380, 410),
            "Metal": (1375, 375, 1460, 410),
            
            # Ammo
            "Light Ammo": (1215, 475, 1300, 510),
            "Medium Ammo": (1295, 475, 1380, 510),
            "Heavy Ammo": (1375, 475, 1460, 510),
            "Shells": (1455, 475, 1540, 510),
            "Rockets": (1535, 475, 1620, 510)
        }
        
        # Item name cache for bottom slots
        self.item_names = []
        self.slot_name_cache = {}
        self.load_item_names()
        
        # Rarity colors
        self.rarity_colors = {
            'Common': (116, 122, 128), 
            'Uncommon': (0, 128, 5), 
            'Rare': (0, 88, 191),
            'Epic': (118, 45, 211), 
            'Legendary': (191, 79, 0), 
            'Mythic': (191, 147, 35),
            'Exotic': (118, 191, 255)
        }
        self.rarity_tolerance = 15
        
        # OCR text corrections
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
        
        # Start OCR initialization in background
        self.initialize_ocr()
        
        # Start threads
        self.start_monitoring()
        self.start_movement_handler()

    def load_item_names(self):
        """Load item names from the cache file"""
        try:
            images_folder = "images"
            cache_file = os.path.join(images_folder, "image_cache.pkl")
            
            if os.path.exists(cache_file):
                with open(cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                
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
        except Exception:
            pass

    def initialize_ocr(self):
        """Initialize OCR engine in a background thread"""
        def load_ocr():
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore')
                try:
                    import easyocr
                    with self.ocr_lock:
                        self.reader = easyocr.Reader(['en'])
                        self.ocr_available = True
                except Exception:
                    self.ocr_available = False
                finally:
                    self.ocr_ready.set()

        threading.Thread(target=load_ocr, daemon=True).start()

    def start_monitoring(self):
        """Start the inventory monitoring thread"""
        if self.monitoring_thread is None or not self.monitoring_thread.is_alive():
            self.stop_monitoring.clear()
            self.monitoring_thread = threading.Thread(target=self.monitor_inventory, daemon=True)
            self.monitoring_thread.start()

    def start_movement_handler(self):
        """Start the movement handling thread"""
        self.movement_thread = threading.Thread(target=self.handle_movement_queue, daemon=True)
        self.movement_thread.start()

    def stop(self):
        """Stop all threads and cleanup"""
        self.stop_monitoring.set()
        if self.dragging:
            pyautogui.mouseUp(button='left', _pause=False)
        
        self.cancel_all_ocr_timers()
        
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=1.0)
        if self.movement_thread:
            self.movement_thread.join(timeout=1.0)

    def cancel_all_ocr_timers(self):
        """Cancel all pending OCR timers"""
        for timer_key, timer in list(self.ocr_timers.items()):
            if timer and timer.is_alive():
                timer.cancel()
        self.ocr_timers.clear()

    def handle_movement_queue(self):
        """Process movement requests from the queue"""
        while not self.stop_monitoring.is_set():
            try:
                x, y = self.movement_queue.get(timeout=0.01)
                self._execute_movement(x, y)
                self.movement_queue.task_done()
            except queue.Empty:
                pass
            except Exception:
                pass

    def _execute_movement(self, target_x, target_y):
        """Execute a smooth mouse movement to the target coordinates"""
        start_x, start_y = pyautogui.position()
        
        # Optimize if already close to target
        if abs(start_x - target_x) < 5 and abs(start_y - target_y) < 5:
            pyautogui.moveTo(target_x, target_y, _pause=False)
            return

        def ease_out_cubic(t):
            """Cubic easing function for smooth movement"""
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

    def smooth_move_to(self, x, y):
        """Queue a smooth movement request"""
        self.movement_queue.put((x, y))

    def check_pixel_color(self, x, y, target_color, tolerance=2):
        """Check if pixel at location matches target color within tolerance"""
        try:
            pixel_color = pyautogui.pixel(x, y)
            if isinstance(target_color, tuple) and len(target_color) == 3:
                return all(abs(a - b) <= tolerance for a, b in zip(pixel_color, target_color))
            return pixel_color == target_color
        except Exception:
            return False

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

    def monitor_inventory(self):
        """Main inventory monitoring loop"""
        prev_inventory_state = False
        
        while not self.stop_monitoring.is_set():
            try:
                current_inventory_state = monitor.inventory_open
                
                # Handle inventory state change
                if current_inventory_state != prev_inventory_state:
                    if current_inventory_state:
                        # Inventory just opened
                        with self.state_lock:
                            self.slot_name_cache.clear()
                            self.current_section = "bottom"
                            self.current_slot = 0
                            self.last_focused_item = None
                            self.cancel_all_ocr_timers()
                                
                        self.navigate_to_slot(0)
                    elif self.dragging:
                        # Release mouse if inventory closed while dragging
                        pyautogui.mouseUp(button='left', _pause=False)
                        self.dragging = False
                
                # Handle input for open inventory
                if current_inventory_state:
                    self.handle_keyboard_input()
                
                prev_inventory_state = current_inventory_state
                time.sleep(0.0005)
                
            except Exception:
                time.sleep(0.05)

    def handle_keyboard_input(self):
        """Handle keyboard input for inventory navigation"""
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

    def handle_horizontal_navigation(self, direction):
        """Handle left/right navigation within the current section"""
        if not monitor.inventory_open:
            return
        
        with self.state_lock:
            # Get slot count based on current section
            if self.current_section == "bottom":
                max_slots = len(self.bottom_slots)
            elif self.current_section == "ammo":
                max_slots = len(self.ammo_slots)
            elif self.current_section == "materials":
                max_slots = len(self.material_slots)
            else:
                return
            
            # Update current slot with wrapping
            if direction == 'left':
                self.current_slot = (self.current_slot - 1) % max_slots
            else:  # right
                self.current_slot = (self.current_slot + 1) % max_slots
            
            slot_idx = self.current_slot
        
        # Navigate to the new slot
        self.navigate_to_slot(slot_idx)

    def handle_vertical_navigation(self, direction):
        """Handle up/down navigation between sections"""
        if not monitor.inventory_open:
            return
        
        sections = ["materials", "ammo", "bottom"]
        
        with self.state_lock:
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
            self.last_focused_item = None
        
        # Announce section name and navigate to first slot
        self.speaker.speak(new_section.capitalize())
        self.navigate_to_slot(0)

    def handle_space(self):
        """Toggle drag state for hotbar items"""
        if not monitor.inventory_open or self.current_section != "bottom":
            return
        
        self.dragging = not self.dragging
        if self.dragging:
            pyautogui.mouseDown(button='left', _pause=False)
            self.speaker.speak("Dragging")
        else:
            pyautogui.mouseUp(button='left', _pause=False)
            self.speaker.speak("Released")

    def navigate_to_slot(self, slot_index):
        """Navigate to a specific slot in the current section"""
        # Generate a new timestamp for this navigation action
        new_timestamp = time.time()
        
        with self.state_lock:
            section = self.current_section
            self.navigation_timestamp = new_timestamp
            self.cancel_all_ocr_timers()
        
        # Use delay to prevent immediate re-announcement
        announce_delay = 0.01
        
        if section == "bottom":
            # Navigate to bottom slots (hotbar)
            if 0 <= slot_index < len(self.bottom_slots):
                coords = self.bottom_slots[slot_index]
                self.smooth_move_to(coords[0], coords[1])
                time.sleep(announce_delay)
                self.speaker.speak(f"Slot {slot_index + 1}")
                
                # Schedule OCR for hotbar item
                timer_key = f"bottom_{slot_index}"
                timer = threading.Timer(
                    0.15, 
                    self.perform_ocr_for_hotbar_with_timestamp_check, 
                    args=[slot_index, new_timestamp, timer_key]
                )
                timer.daemon = True
                self.ocr_timers[timer_key] = timer
                timer.start()
                
        elif section == "ammo":
            # Navigate to ammo slots
            if 0 <= slot_index < len(self.ammo_slots):
                item_name, coords = self.ammo_slots[slot_index]
                self.smooth_move_to(coords[0], coords[1])
                time.sleep(announce_delay)
                self.speaker.speak(item_name)
                
                # Schedule OCR for ammo count
                timer_key = f"ammo_{item_name}"
                timer = threading.Timer(
                    0.15, 
                    self.announce_item_count_with_timestamp_check, 
                    args=[item_name, new_timestamp, timer_key]
                )
                timer.daemon = True
                self.ocr_timers[timer_key] = timer
                timer.start()
                
        elif section == "materials":
            # Navigate to material slots
            if 0 <= slot_index < len(self.material_slots):
                item_name, coords = self.material_slots[slot_index]
                self.smooth_move_to(coords[0], coords[1])
                time.sleep(announce_delay)
                self.speaker.speak(item_name)
                
                # Schedule OCR for material count
                timer_key = f"material_{item_name}"
                timer = threading.Timer(
                    0.15, 
                    self.announce_item_count_with_timestamp_check, 
                    args=[item_name, new_timestamp, timer_key]
                )
                timer.daemon = True
                self.ocr_timers[timer_key] = timer
                timer.start()

    def perform_ocr_for_hotbar_with_timestamp_check(self, slot_index, timestamp, timer_key):
        """Perform OCR for hotbar with navigation timestamp check"""
        # Remove this timer from the tracking dictionary
        self.ocr_timers.pop(timer_key, None)
        
        # Check if this OCR operation is still valid based on timestamp
        with self.state_lock:
            if timestamp != self.navigation_timestamp:
                return
        
        # Only proceed if OCR is available
        if not self.ocr_ready.is_set() or not self.ocr_available:
            return
            
        # Actual OCR implementation
        self.perform_ocr_for_hotbar(slot_index)

    def announce_item_count_with_timestamp_check(self, item_name, timestamp, timer_key):
        """Announce item count with navigation timestamp check"""
        # Remove this timer from the tracking dictionary
        self.ocr_timers.pop(timer_key, None)
        
        # Check if this OCR operation is still valid based on timestamp
        with self.state_lock:
            if timestamp != self.navigation_timestamp:
                return
        
        # Only proceed if OCR is available
        if not self.ocr_ready.is_set() or not self.ocr_available:
            return
            
        # Actual OCR implementation
        self.announce_item_count(item_name)

    def announce_item_count(self, item_name):
        """Detect and announce item count"""
        count = self.detect_item_count(item_name)
        if count is not None:
            self.speaker.speak(f"{count}")

    def perform_ocr_for_hotbar(self, slot_index):
        """Perform OCR for a hotbar slot to identify the item"""
        # Check if already OCRed (but always check rarity)
        cached_name = self.slot_name_cache.get(slot_index)
        if cached_name:
            self.check_rarity_and_announce(cached_name, slot_index)
            return
            
        # Define the OCR area for item name
        ocr_area = {
            'left': 1195, 
            'top': 610, 
            'width': 561, 
            'height': 100
        }
        
        try:
            # Use a new MSS instance for this thread
            with mss() as sct:
                # Capture screenshot for OCR
                screenshot = np.array(sct.grab(ocr_area))
                
                # Process image for OCR
                if screenshot.shape[2] == 4:
                    screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
                
                # Convert to grayscale and threshold
                gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
                _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
                
                # Perform OCR
                with self.ocr_lock:
                    results = self.reader.readtext(binary, detail=0)
                
                if results:
                    # Combine detected text
                    ocr_text = ' '.join(results).lower()
                    
                    # Match to known item
                    matched_item = self.find_closest_match(ocr_text)
                    
                    # Cache the item name
                    self.slot_name_cache[slot_index] = matched_item
                    
                    # Check rarity and announce
                    self.check_rarity_and_announce(matched_item, slot_index)
        except Exception:
            pass

    def find_closest_match(self, ocr_text):
        """Find the closest matching item to OCR text"""
        if not self.item_names or not ocr_text:
            return ocr_text
        
        # Apply common OCR corrections
        for misread, correction in self.ocr_corrections.items():
            if misread in ocr_text:
                ocr_text = ocr_text.replace(misread, correction)
        
        best_match = None
        highest_ratio = 0
        best_clean_name = None
        
        # Find best matching item name
        for full_name, clean_name in self.item_names:
            ratio = difflib.SequenceMatcher(None, ocr_text, clean_name.lower()).ratio()
            
            if ratio > highest_ratio and ratio > 0.4:
                highest_ratio = ratio
                best_match = full_name
                best_clean_name = clean_name
        
        return best_clean_name if best_clean_name else ocr_text

    def check_rarity_and_announce(self, item_name, slot_index):
        """Check item rarity and announce full item name"""
        # Check for rarity by examining pixels
        rarity = self.detect_rarity()
        
        # Combine rarity with item name
        full_item_name = f"{rarity} {item_name}" if rarity else item_name
        
        # Announce if not recently announced
        if self.should_announce(full_item_name):
            self.speaker.speak(full_item_name)

    def detect_rarity(self):
        """Detect item rarity based on pixel colors"""
        try:
            # Check common rarity indicator locations
            check_locations = [(1210, 684), (1210, 657)]
            
            for x, y in check_locations:
                if self.check_pixel_color(x, y, (255, 255, 255)):
                    # Check pixel 5 to the left for rarity color
                    rarity_pixel_x = x - 5
                    rarity_pixel_color = pyautogui.pixel(rarity_pixel_x, y)
                    
                    # Compare with known rarity colors
                    for rarity, color in self.rarity_colors.items():
                        if all(abs(a - b) <= self.rarity_tolerance for a, b in zip(rarity_pixel_color, color)):
                            return rarity
            
            return ""
        except Exception:
            return ""

    def should_announce(self, item_name):
        """Check if item should be announced based on cooldown"""
        current_time = time.time()
        
        # Don't repeat announcements too quickly
        if item_name == self.last_announced_item:
            if current_time - self.last_announcement_time < self.announcement_cooldown:
                return False
        
        # Update announcement tracking
        self.last_announced_item = item_name
        self.last_announcement_time = current_time
        return True

    def detect_item_count(self, item_name):
        """Detect item count using OCR"""
        if not self.ocr_available or not self.ocr_ready.is_set():
            return None
            
        if item_name not in self.count_regions:
            return None
            
        ocr_region = self.count_regions[item_name]
        
        try:
            # Create a new MSS instance for this thread
            with mss() as sct:
                # Capture count region
                screenshot = np.array(sct.grab({
                    'left': ocr_region[0],
                    'top': ocr_region[1],
                    'width': ocr_region[2] - ocr_region[0],
                    'height': ocr_region[3] - ocr_region[1]
                }))
                
                # Convert to BGR if needed
                if screenshot.shape[2] == 4:
                    screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
                
                # Create grayscale version
                gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
                
                # Apply multiple techniques and try OCR on each
                ocr_approaches = [
                    # Extract bright text with HSV color filtering
                    lambda: self._extract_bright_text(screenshot),
                    
                    # High contrast binary threshold
                    lambda: cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)[1],
                    
                    # Low contrast binary threshold
                    lambda: cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]
                ]
                
                # Try each approach until we get a valid count
                for approach_fn in ocr_approaches:
                    processed = approach_fn()
                    
                    # Apply scaling for better OCR
                    processed = cv2.resize(processed, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
                    
                    # Run OCR
                    with self.ocr_lock:
                        results = self.reader.readtext(processed, detail=0, 
                                                    allowlist='0123456789',
                                                    paragraph=False,
                                                    height_ths=1.2)
                    
                    if results:
                        # Join all detected digits
                        count_text = ''.join(results)
                        # Remove any non-digit characters
                        count_text = ''.join(c for c in count_text if c.isdigit())
                        
                        if count_text:
                            try:
                                return int(count_text)
                            except ValueError:
                                pass
        
        except Exception:
            pass
            
        return None
        
    def _extract_bright_text(self, image):
        """Extract bright text (white/yellow) using HSV color filtering"""
        # Convert to HSV
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Define range for bright colors (white/yellow text)
        lower_white = np.array([0, 0, 180])
        upper_white = np.array([180, 80, 255])
        mask_white = cv2.inRange(hsv, lower_white, upper_white)
        
        lower_yellow = np.array([20, 100, 100])
        upper_yellow = np.array([40, 255, 255])
        mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)
        
        # Combine masks
        mask = cv2.bitwise_or(mask_white, mask_yellow)
        
        # Apply mask
        extracted = cv2.bitwise_and(image, image, mask=mask)
        
        # Convert to grayscale
        return cv2.cvtColor(extracted, cv2.COLOR_BGR2GRAY)

# Create a single instance
inventory_handler = InventoryHandler()