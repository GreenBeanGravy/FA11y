import threading
import time
import pyautogui
import cv2
import numpy as np
from mss import mss
from pathlib import Path
from accessible_output2.outputs.auto import Auto
from lib.utilities import read_config, get_config_boolean
import threading

class BackgroundMonitor:
    def __init__(self):
        self.speaker = Auto()
        self.running = False
        self.thread = None
        
        # Thread-local storage for MSS
        self.thread_local = threading.local()
        
        # Public status flags that can be accessed by other modules
        self.map_open = False
        self.is_spectating = False
        self.inventory_open = False
        
        self.config = read_config()
        
        # Config flags
        self.announce_map = get_config_boolean(self.config, 'AnnounceMapStatus', True)
        self.announce_spectating = get_config_boolean(self.config, 'AnnounceSpectatingStatus', True)
        self.announce_inventory = get_config_boolean(self.config, 'AnnounceInventoryStatus', True)
        
        # Load escape key template
        self.escape_template = None
        self.load_escape_template()
        
        # Define inventory scan region
        self.inventory_region = {
            'left': 1711,
            'top': 1012,
            'width': 121,  # 1832 - 1711
            'height': 28   # 1040 - 1012
        }

    def get_mss(self):
        """Get thread-local MSS instance."""
        if not hasattr(self.thread_local, 'mss'):
            self.thread_local.mss = mss()
        return self.thread_local.mss

    def reload_config(self):
        """Reload configuration values."""
        self.config = read_config()
        self.announce_map = get_config_boolean(self.config, 'AnnounceMapStatus', True)
        self.announce_spectating = get_config_boolean(self.config, 'AnnounceSpectatingStatus', True)
        self.announce_inventory = get_config_boolean(self.config, 'AnnounceInventoryStatus', True)

    def load_escape_template(self):
        """Load the escape key template for detection."""
        template_path = Path("keys") / "escape.png"
        if template_path.exists():
            try:
                img = cv2.imread(str(template_path))
                if img is not None:
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    self.escape_template = cv2.Canny(gray, 100, 200)
            except Exception as e:
                print(f"Error loading escape template: {e}")
                self.escape_template = None

    def detect_escape_key(self, screenshot):
        """Detect escape key using template matching."""
        try:
            if self.escape_template is None or screenshot is None:
                return False
                
            if screenshot.shape[2] == 4:  # Convert BGRA to BGR if needed
                screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
                
            gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 100, 200)
            
            result = cv2.matchTemplate(edges, self.escape_template, cv2.TM_CCOEFF_NORMED)
            threshold = 0.45
            
            return np.max(result) >= threshold
        except Exception as e:
            print(f"Error in detect_escape_key: {e}")
            return False

    def check_map_status(self):
        """Check if the map is open/closed."""
        try:
            pixel_color = pyautogui.pixel(220, 60)
            is_map_color = all(abs(a - b) <= 10 for a, b in zip(pixel_color, (247, 255, 26)))
            
            if is_map_color != self.map_open:
                self.map_open = is_map_color
                if self.announce_map:
                    self.speaker.speak("Map " + ("opened" if is_map_color else "closed"))
                    
        except Exception as e:
            print(f"Error checking map status: {e}")

    def check_spectating_status(self):
        """Check if player is spectating."""
        if self.map_open:  # Don't check if map is open
            return
            
        try:
            pixels = [(888, 20), (903, 20), (921, 20), (937, 20)]
            all_white = all(
                pyautogui.pixel(x, y) == (255, 255, 255)
                for x, y in pixels
            )
            
            if all_white != self.is_spectating:
                self.is_spectating = all_white
                if self.announce_spectating:
                    self.speaker.speak(
                        "Now spectating" if all_white else "Stopped spectating"
                    )
                    
        except Exception as e:
            print(f"Error checking spectating status: {e}")

    def check_inventory_status(self):
        """Check if inventory is open/closed using template matching."""
        if self.map_open or self.is_spectating:  # Don't check if map is open or spectating
            return
            
        try:
            sct = self.get_mss()
            screenshot = np.array(sct.grab(self.inventory_region))
            is_escape_visible = self.detect_escape_key(screenshot)
            
            if is_escape_visible != self.inventory_open:
                self.inventory_open = is_escape_visible
                if self.announce_inventory:
                    self.speaker.speak(
                        "Inventory opened" if is_escape_visible else "Inventory closed"
                    )
                    
        except Exception as e:
            print(f"Error checking inventory status: {e}")
            time.sleep(0.5)  # Add a small delay on error

    def monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            try:
                if self.announce_map:
                    self.check_map_status()
                if self.announce_spectating:
                    self.check_spectating_status()
                if self.announce_inventory:
                    self.check_inventory_status()
                time.sleep(0.1)
            except Exception as e:
                print(f"Error in monitor loop: {e}")
                time.sleep(0.5)  # Add a small delay on error

    def start_monitoring(self):
        """Start the background monitoring thread."""
        if not self.running:
            self.running = True
            self.stop_event = threading.Event()
            self.thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.thread.start()

    def stop_monitoring(self):
        """Stop the background monitoring thread."""
        self.running = False
        if hasattr(self, 'stop_event'):
            self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1.0)
            
        # Clean up MSS instances
        if hasattr(self.thread_local, 'mss'):
            self.thread_local.mss.close()

# Create a single instance
monitor = BackgroundMonitor()