import cv2
import numpy as np
from mss import mss
import os
from threading import Thread, Event, Lock
from accessible_output2.outputs.auto import Auto
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

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
    announcements: int = 0  # Track number of announcements made

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
        self.recently_removed_positions = []  # Track recently used positions
        self.position_cooldown = 0.2  # 200ms cooldown
        self.initialize_easyocr()
        self.load_resource_templates()

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
            
            for pt in zip(*locations[::-1]):
                confidence = result[pt[1], pt[0]]
                if name in self.active_resources:
                    old_pos = self.active_resources[name].position
                    distance = np.sqrt((pt[0] - old_pos[0])**2 + (pt[1] - old_pos[1])**2)
                    if distance < 20:
                        self.active_resources[name].last_seen = time.time()
                        self.active_resources[name].confidence = confidence
                        self.active_resources[name].position = pt
                        continue
                detections.append((name, pt, confidence))
        
        return detections

    def detect_count(self, screenshot):
        if not self.easyocr_available or not self.easyocr_ready.is_set():
            return None

        try:
            if screenshot.shape[2] == 4:
                screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)

            # Color mask for specific BGR range - same as material monitor
            lower_bound = np.array([255, 226, 182], dtype=np.uint8)  # BGR format
            upper_bound = np.array([255, 255, 255], dtype=np.uint8)
            color_mask = cv2.inRange(screenshot, lower_bound, upper_bound)
            filtered = cv2.bitwise_and(screenshot, screenshot, mask=color_mask)
            
            # Convert to grayscale
            gray = cv2.cvtColor(filtered, cv2.COLOR_BGR2GRAY)
            
            # Binary threshold
            _, gray = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
            
            # Resize for better OCR performance - same as material monitor
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
                    # Only allow values up to 999
                    if count <= 999:
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
                    detections = self.detect_resource(screenshot)
                    
                    with self.lock:
                        for name, position, confidence in detections:
                            if name not in self.active_resources:
                                template_data = self.resource_templates[name]
                                icon_width = template_data['width']
                                icon_height = template_data['height']
                                
                                ocr_x = SCAN_REGION['left'] + position[0] + icon_width + 5
                                ocr_y = SCAN_REGION['top'] + position[1] + (icon_height // 2) - (OCR_OFFSET['height'] // 2)
                                
                                ocr_area = {
                                    'left': ocr_x,
                                    'top': ocr_y,
                                    'width': OCR_OFFSET['width'],
                                    'height': OCR_OFFSET['height']
                                }
                                
                                count_screenshot = np.array(sct.grab(ocr_area))
                                count = self.detect_count(count_screenshot)
                                
                                self.active_resources[name] = ResourceState(
                                    name=name,
                                    position=position,
                                    count=count,
                                    last_seen=current_time,
                                    confidence=confidence
                                )
                                
                                if count is not None:
                                    self.speaker.speak(f"plus {count} {name.replace('_', ' ')}")
                            
                        resources_to_remove = []
                        for name, state in self.active_resources.items():
                            if current_time - state.last_seen > 2.0:
                                resources_to_remove.append(name)
                            else:
                                template_data = self.resource_templates[name]
                                icon_width = template_data['width']
                                icon_height = template_data['height']
                                
                                ocr_x = SCAN_REGION['left'] + state.position[0] + icon_width + 5
                                ocr_y = SCAN_REGION['top'] + state.position[1] + (icon_height // 2) - (OCR_OFFSET['height'] // 2)
                                
                                ocr_area = {
                                    'left': ocr_x,
                                    'top': ocr_y,
                                    'width': OCR_OFFSET['width'],
                                    'height': OCR_OFFSET['height']
                                }
                                
                                count_screenshot = np.array(sct.grab(ocr_area))
                                current_count = self.detect_count(count_screenshot)
                                
                                if current_count is not None and current_count > state.count and state.announcements < 2:
                                    self.speaker.speak(f"plus {current_count} {name.replace('_', ' ')}")
                                    state.count = current_count
                                    state.last_seen = current_time
                                    state.announcements += 1
                                elif current_count is not None:
                                    state.count = current_count
                                    state.last_seen = current_time
                        
                        for name in resources_to_remove:
                            del self.active_resources[name]
                    
                    time.sleep(0.3)
                except:
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
