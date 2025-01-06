import threading
import time
import pyautogui
from accessible_output2.outputs.auto import Auto
from lib.utilities import read_config, get_config_boolean

class BackgroundMonitor:
    def __init__(self):
        self.speaker = Auto()
        self.running = False
        self.thread = None
        self.map_open = False
        self.is_spectating = False
        self.config = read_config()
        
        # Config flags
        self.announce_map = get_config_boolean(self.config, 'AnnounceMapStatus', True)
        self.announce_spectating = get_config_boolean(self.config, 'AnnounceSpectatingStatus', True)

    def reload_config(self):
        """Reload configuration values."""
        self.config = read_config()
        self.announce_map = get_config_boolean(self.config, 'AnnounceMapStatus', True)
        self.announce_spectating = get_config_boolean(self.config, 'AnnounceSpectatingStatus', True)

    def check_map_status(self):
        """Check if the map is open/closed."""
        try:
            # Check the specific pixel color for map status
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
            # Check all four pixels for spectating status
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

    def monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            if self.announce_map:
                self.check_map_status()
            if self.announce_spectating:
                self.check_spectating_status()
            time.sleep(0.1)  # Small delay to prevent high CPU usage

    def start_monitoring(self):
        """Start the background monitoring thread."""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.thread.start()

    def stop_monitoring(self):
        """Stop the background monitoring thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

# Create a single instance
monitor = BackgroundMonitor()