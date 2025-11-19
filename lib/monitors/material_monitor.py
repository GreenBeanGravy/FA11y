import cv2
import numpy as np
from mss import mss
import os
from threading import Thread, Event, Lock
from accessible_output2.outputs.auto import Auto
import time
from pathlib import Path
from lib.managers.ocr_manager import get_ocr_manager

# Screen coordinates
MATERIAL_ICON_AREA = {
    'left': 480,
    'top': 675,
    'width': 63,  # 543 - 480
    'height': 51  # 726 - 675
}

MATERIAL_COUNT_AREA = {
    'left': 544,
    'top': 673,
    'width': 79,  # 618 - 544 + 5
    'height': 47  # 715 - 673 + 5
}

class MaterialMonitor:
    def __init__(self):
        self.speaker = Auto()
        self.running = False
        self.stop_event = Event()
        self.thread = None
        
        # Get OCR manager instance
        self.ocr_manager = get_ocr_manager()
        
        # State tracking
        self.current_material = None
        self.last_count = None
        self.material_templates = {}
        
        # Load templates
        self.load_material_templates()

    def load_material_templates(self):
        """Load material template images."""
        templates = {}
        mats_folder = Path("mats")
        materials = ['wood', 'stone', 'metal']
        
        for material in materials:
            template_path = mats_folder / f"{material}.png"
            if template_path.exists():
                img = cv2.imread(str(template_path))
                if img is not None:
                    # Remove black background more precisely
                    mask = cv2.inRange(img, np.array([5, 5, 5]), np.array([255, 255, 255]))
                    masked = cv2.bitwise_and(img, img, mask=mask)
                    
                    # Store original size for detection
                    templates[material] = {
                        'original': img,
                        'masked': masked
                    }
                else:
                    print(f"Failed to load template for {material}")
        
        self.material_templates = templates

    def detect_material(self, screenshot):
        """Detect material using template matching with masking."""
        # Convert from BGRA to BGR if needed
        if screenshot.shape[2] == 4:
            screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
            
        best_match = None
        best_score = 0
        
        # Convert screenshot to grayscale
        gray_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        
        for material, template_dict in self.material_templates.items():
            template = template_dict['original']
            gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            
            # Create mask for non-black pixels in template
            mask = cv2.threshold(gray_template, 10, 255, cv2.THRESH_BINARY)[1]
            
            # Try template matching with mask
            result = cv2.matchTemplate(gray_screenshot, gray_template, cv2.TM_CCORR_NORMED, mask=mask)
            score = result.max()
            
            if score > best_score and score > 0.975:  # High threshold for confident match
                best_match = material
                best_score = score
        
        return best_match

    def detect_count(self, screenshot):
        """Detect number using OCR with specific color range filtering."""
        if not self.ocr_manager.is_ready():
            return None

        try:
            # Convert from BGRA to BGR if needed
            if screenshot.shape[2] == 4:
                screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
                
            # Color mask for specific RGB range
            lower_bound = np.array([255, 226, 182])  # BGR format
            upper_bound = np.array([255, 255, 255])
            color_mask = cv2.inRange(screenshot, lower_bound, upper_bound)
            filtered = cv2.bitwise_and(screenshot, screenshot, mask=color_mask)
            
            # Convert to grayscale
            gray = cv2.cvtColor(filtered, cv2.COLOR_BGR2GRAY)
            
            # Binary threshold
            _, gray = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
            
            # Resize
            gray = cv2.resize(gray, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_LINEAR)
            
            results = self.ocr_manager.read_numbers(gray,
                                        allowlist='0123456789',
                                        paragraph=False,
                                        min_size=10,
                                        text_threshold=0.4,
                                        width_ths=0.8)
            
            if results:
                count_text = results[0][1]
                return int(count_text) if count_text.isdigit() else None
                    
        except Exception as e:
            print(f"Error in count detection: {e}")
        return None

    def monitor_loop(self):
        """Main monitoring loop."""
        with mss() as sct:
            last_material_time = 0
            
            while not self.stop_event.is_set():
                try:
                    # Capture material icon area
                    icon_screenshot = np.array(sct.grab(MATERIAL_ICON_AREA))
                    
                    # Detect material
                    detected_material = self.detect_material(icon_screenshot)
                    current_time = time.time()
                    
                    if detected_material:
                        last_material_time = current_time
                        
                        if self.current_material != detected_material:
                            # Reset state for new material
                            self.current_material = detected_material
                            self.last_count = None
                            
                            # Get initial count when new material detected
                            count_screenshot = np.array(sct.grab(MATERIAL_COUNT_AREA))
                            current_count = self.detect_count(count_screenshot)
                            if current_count is not None:
                                # Announce initial detection
                                self.speaker.speak(f"plus {current_count} {detected_material}")
                                self.last_count = current_count
                        else:
                            # Continue monitoring count for same material
                            count_screenshot = np.array(sct.grab(MATERIAL_COUNT_AREA))
                            current_count = self.detect_count(count_screenshot)
                            
                            if current_count is not None and current_count != self.last_count:
                                # Announce count changes
                                if self.last_count is not None:
                                    self.speaker.speak(f"plus {current_count}")
                                self.last_count = current_count
                            
                    # Only consider material gone if not seen for 1.5 seconds
                    elif self.current_material and current_time - last_material_time > 1.5:
                        self.current_material = None
                        self.last_count = None
                    
                    time.sleep(0.3)  # Check every 0.3 seconds
                    
                except Exception as e:
                    print(f"Error in material monitor loop: {e}")
                    time.sleep(0.5)

    def start_monitoring(self):
        """Start the material monitoring."""
        if not self.running:
            self.running = True
            self.stop_event.clear()
            self.thread = Thread(target=self.monitor_loop, daemon=True)
            self.thread.start()

    def stop_monitoring(self):
        """Stop the material monitoring."""
        self.stop_event.set()
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

# Create a single instance
material_monitor = MaterialMonitor()