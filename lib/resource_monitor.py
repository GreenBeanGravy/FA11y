import cv2
import numpy as np
from mss import mss
import os
from threading import Thread, Event, Lock
from accessible_output2.outputs.auto import Auto
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List

# Screen monitoring configuration
SCAN_REGION = {
    'left': 1465,
    'top': 583,
    'width': 110,
    'height': 223
}

OCR_OFFSET = {
    'width': 75,
    'height': 50
}

@dataclass
class ResourceState:
    name: str
    position: Tuple[int, int]
    count: Optional[int] = None
    last_seen: float = 0.0
    confidence: float = 0.0
    last_position_change: float = 0.0
    position_history: List[Tuple[int, int]] = None
    last_count: Optional[int] = None
    announced_values: Dict[int, float] = None  # Track values and when they were announced
    last_global_announcement: float = 0.0      # Track any announcement for this resource

    def __post_init__(self):
        if self.position_history is None:
            self.position_history = []
        if self.announced_values is None:
            self.announced_values = {}
        self.position_history.append(self.position)
        while len(self.position_history) > 3:
            self.position_history.pop(0)
            
    def can_announce(self, new_count: int, current_time: float) -> bool:
        """Check if we should announce this count."""
        # Check for rapid repeat announcements of same value
        last_specific_announcement = self.announced_values.get(new_count, 0)
        if current_time - last_specific_announcement < 1.0:  # 1 second cooldown for same value
            return False
            
        # Check for any recent announcements from this resource
        if current_time - self.last_global_announcement < 0.3:  # 300ms global cooldown per resource
            return False
            
        return True

class ResourceMonitor:
    def __init__(self):
        self.speaker = Auto()
        self.running = False
        self.stop_event = Event()
        self.thread = None
        self.lock = Lock()
        self.active_resources: Dict[str, ResourceState] = {}
        self.resource_templates = {}
        self.easyocr_available = False
        self.easyocr_ready = Event()
        self.easyocr_lock = Lock()
        self.reader = None
        self.position_change_cooldown = 0.2  # 200ms cooldown for position changes
        self.initialize_easyocr()
        self.load_resource_templates()
        self.last_positions = {}  # Track last known positions of resources

    def initialize_easyocr(self):
        def load_easyocr():
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore')
                try:
                    import easyocr
                    with self.easyocr_lock:
                        self.reader = easyocr.Reader(['en'], recognizer='number')
                        self.easyocr_available = True
                except:
                    self.easyocr_available = False
                finally:
                    self.easyocr_ready.set()
        Thread(target=load_easyocr, daemon=True).start()

    def load_resource_templates(self):
        templates = {}
        mats_folder = Path("mats")
        materials = ['wood', 'stone', 'metal']
        ammo_folder = Path("ammo")
        ammo_types = ['light_bullets', 'heavy_bullets', 'medium_bullets', 'shells', 'rockets']
        
        for folder, resources in [(mats_folder, materials), (ammo_folder, ammo_types)]:
            for resource in resources:
                template_path = folder / f"{resource}.png"
                if template_path.exists():
                    img = cv2.imread(str(template_path))
                    if img is not None:
                        h, w = img.shape[:2]
                        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                        edges = cv2.Canny(gray, 100, 200)
                        templates[resource] = {
                            'edges': edges,
                            'width': w,
                            'height': h
                        }
        self.resource_templates = templates

    def is_list_stable(self, current_time: float) -> bool:
        """Check if enough time has passed since the last list modification."""
        for resource in self.active_resources.values():
            if current_time - resource.last_position_change < 0.15:  # 150ms stability window
                return False
        return True

    def is_valid_position_change(self, name: str, new_position: Tuple[int, int], current_time: float) -> bool:
        """Validate if a position change is reasonable."""
        if name not in self.active_resources:
            return True

        resource = self.active_resources[name]
        old_position = resource.position

        # Check if enough time has passed since last position change
        if current_time - resource.last_position_change < self.position_change_cooldown:
            return False

        # Calculate movement distance
        distance = np.sqrt((new_position[0] - old_position[0])**2 + 
                         (new_position[1] - old_position[1])**2)

        # Check if movement is within reasonable bounds (e.g., max 50 pixels)
        if distance > 50:
            return False

        # Verify the new position isn't too close to other active resources
        min_distance_between_items = 20
        for other_name, other_resource in self.active_resources.items():
            if other_name != name:
                other_pos = other_resource.position
                other_distance = np.sqrt((new_position[0] - other_pos[0])**2 + 
                                       (new_position[1] - other_pos[1])**2)
                if other_distance < min_distance_between_items:
                    return False

        return True

    def detect_resource(self, screenshot):
        if screenshot.shape[2] == 4:
            screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
        
        gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        detections = []
        threshold = 0.45
        
        for name, template_data in self.resource_templates.items():
            edges_template = template_data['edges']
            result = cv2.matchTemplate(edges, edges_template, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= threshold)
            
            current_time = time.time()
            for pt in zip(*locations[::-1]):
                confidence = result[pt[1], pt[0]]
                
                # Validate position change
                if not self.is_valid_position_change(name, pt, current_time):
                    continue
                
                if name in self.active_resources:
                    old_pos = self.active_resources[name].position
                    distance = np.sqrt((pt[0] - old_pos[0])**2 + (pt[1] - old_pos[1])**2)
                    if distance < 20:
                        self.active_resources[name].last_seen = current_time
                        self.active_resources[name].confidence = confidence
                        self.active_resources[name].position = pt
                        continue
                
                detections.append((name, pt, confidence))
        
        return detections

    def detect_count(self, screenshot, position: Tuple[int, int], name: str, current_time: float) -> Optional[int]:
        """Enhanced count detection with position validation."""
        if not self.easyocr_available or not self.easyocr_ready.is_set():
            return None

        try:
            if screenshot.shape[2] == 4:
                screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)

            # Color mask for specific BGR range
            lower_bound = np.array([255, 226, 182], dtype=np.uint8)
            upper_bound = np.array([255, 255, 255], dtype=np.uint8)
            color_mask = cv2.inRange(screenshot, lower_bound, upper_bound)
            filtered = cv2.bitwise_and(screenshot, screenshot, mask=color_mask)
            
            gray = cv2.cvtColor(filtered, cv2.COLOR_BGR2GRAY)
            _, gray = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
            gray = cv2.resize(gray, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_LINEAR)
            
            with self.easyocr_lock:
                results = self.reader.readtext(gray,
                                            allowlist='0123456789',
                                            paragraph=False,
                                            min_size=10,
                                            text_threshold=0.4,
                                            width_ths=0.8)
            
            if results:
                count_text = results[0][1]
                if count_text.isdigit():
                    count = int(count_text)
                    if count <= 999:
                        # Validate the count change
                        if name in self.active_resources:
                            old_count = self.active_resources[name].count
                            if old_count is not None:
                                # If count changes too drastically, ignore it
                                if abs(count - old_count) > 100:  # Adjust threshold as needed
                                    return None
                        return count
        except:
            pass
        return None

    def monitor_loop(self):
        with mss() as sct:
            while not self.stop_event.is_set():
                try:
                    screenshot = np.array(sct.grab(SCAN_REGION))
                    current_time = time.time()
                    
                    # Only process if the list is stable
                    if not self.is_list_stable(current_time):
                        time.sleep(0.1)
                        continue
                        
                    detections = self.detect_resource(screenshot)
                    list_modified = False
                    
                    with self.lock:
                        # Process new detections
                        for name, position, confidence in detections:
                            if name not in self.active_resources:
                                template_data = self.resource_templates[name]
                                icon_width = template_data['width']
                                icon_height = template_data['height']
                                
                                ocr_area = {
                                    'left': SCAN_REGION['left'] + position[0] + icon_width + 5,
                                    'top': SCAN_REGION['top'] + position[1] + (icon_height // 2) - (OCR_OFFSET['height'] // 2),
                                    'width': OCR_OFFSET['width'],
                                    'height': OCR_OFFSET['height']
                                }
                                
                                count_screenshot = np.array(sct.grab(ocr_area))
                                count = self.detect_count(count_screenshot, position, name, current_time)
                                
                                if count is not None:
                                    resource = ResourceState(
                                        name=name,
                                        position=position,
                                        count=count,
                                        last_seen=current_time,
                                        confidence=confidence,
                                        last_position_change=current_time,
                                        last_global_announcement=0.0  # Allow first announcement
                                    )
                                    
                                    if resource.can_announce(count, current_time):
                                        self.speaker.speak(f"plus {count} {name.replace('_', ' ')}")
                                        resource.announced_values[count] = current_time
                                        resource.last_global_announcement = current_time
                                        
                                    self.active_resources[name] = resource
                        
                        # Update existing resources
                        resources_to_remove = []
                        for name, state in self.active_resources.items():
                            if current_time - state.last_seen > 2.0:
                                resources_to_remove.append(name)
                                list_modified = True
                                continue
                                
                            template_data = self.resource_templates[name]
                            icon_width = template_data['width']
                            icon_height = template_data['height']
                            
                            ocr_area = {
                                'left': SCAN_REGION['left'] + state.position[0] + icon_width + 5,
                                'top': SCAN_REGION['top'] + state.position[1] + (icon_height // 2) - (OCR_OFFSET['height'] // 2),
                                'width': OCR_OFFSET['width'],
                                'height': OCR_OFFSET['height']
                            }
                            
                            count_screenshot = np.array(sct.grab(ocr_area))
                            current_count = self.detect_count(count_screenshot, state.position, name, current_time)
                            
                            if current_count is not None:
                                state.last_count = state.count
                                state.count = current_count
                                state.count_history.append(current_count)
                                state.last_seen = current_time
                                
                                # Only announce if count has changed and hasn't been announced too many times
                                if state.last_count is None or current_count > state.last_count:
                                    if state.announcements < 2:
                                        self.speaker.speak(f"plus {current_count} {name.replace('_', ' ')}")
                                        state.announcements += 1
                        
                        # Remove inactive resources
                        for name in resources_to_remove:
                            del self.active_resources[name]
                    
                    time.sleep(0.3)
                except Exception as e:
                    print(f"Error in monitor loop: {str(e)}")
                    time.sleep(1.0)

    def start_monitoring(self):
        if not self.running:
            self.running = True
            self.stop_event.clear()
            self.thread = Thread(target=self.monitor_loop, daemon=True)
            self.thread.start()

    def stop_monitoring(self):
        self.stop_event.set()
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

# Create a single instance
resource_monitor = ResourceMonitor()