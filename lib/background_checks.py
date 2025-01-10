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
        
        # Public status flags that can be accessed by other modules
        self.map_open = False
        self.is_spectating = False
        self.inventory_open = False
        self.drop_menu_open = False
        
        self.config = read_config()
        
        # Config flags
        self.announce_map = get_config_boolean(self.config, 'AnnounceMapStatus', True)
        self.announce_spectating = get_config_boolean(self.config, 'AnnounceSpectatingStatus', True)
        self.announce_inventory = get_config_boolean(self.config, 'AnnounceInventoryStatus', True)
        self.announce_drop_menu = get_config_boolean(self.config, 'AnnounceDropMenu', True)

    def reload_config(self):
        """Reload configuration values."""
        self.config = read_config()
        self.announce_map = get_config_boolean(self.config, 'AnnounceMapStatus', True)
        self.announce_spectating = get_config_boolean(self.config, 'AnnounceSpectatingStatus', True)
        self.announce_inventory = get_config_boolean(self.config, 'AnnounceInventoryStatus', True)
        self.announce_drop_menu = get_config_boolean(self.config, 'AnnounceDropMenu', True)

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
        """Check if inventory is open/closed."""
        if self.map_open or self.is_spectating:  # Don't check if map is open or spectating
            return
            
        try:
            pixels = [(1724, 1028), (1728, 1028), (1731, 1028)]
            target_color = (15, 13, 28)
            all_match = all(
                pyautogui.pixel(x, y) == target_color
                for x, y in pixels
            )
            
            if all_match != self.inventory_open:
                self.inventory_open = all_match
                if self.announce_inventory:
                    self.speaker.speak(
                        "Inventory opened" if all_match else "Inventory closed"
                    )
                    
        except Exception as e:
            print(f"Error checking inventory status: {e}")

    def check_drop_menu_status(self):
        """Check if drop items menu is open."""
        if self.map_open or self.is_spectating:  # Don't check if map is open or spectating
            return
            
        try:
            # Dark border pixels
            dark_pixels = [
                (865, 653), (882, 653),  # Top
                (882, 671), (866, 670)   # Bottom
            ]
            # White center pixels
            white_pixels = [
                (867, 662), (877, 662)   # Center
            ]
            
            # Check for dark border (15, 13, 28)
            dark_match = all(
                pyautogui.pixel(x, y) == (15, 13, 28)
                for x, y in dark_pixels
            )
            
            # Check for white center
            white_match = all(
                pyautogui.pixel(x, y) == (255, 255, 255)
                for x, y in white_pixels
            )
            
            is_drop_menu = dark_match and white_match
            
            if is_drop_menu != self.drop_menu_open:
                self.drop_menu_open = is_drop_menu
                if self.announce_drop_menu:
                    self.speaker.speak(
                        "Drop menu opened" if is_drop_menu else "Drop menu closed"
                    )
                    
        except Exception as e:
            print(f"Error checking drop menu status: {e}")

    def monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            if self.announce_map:
                self.check_map_status()
            if self.announce_spectating:
                self.check_spectating_status()
            if self.announce_inventory:
                self.check_inventory_status()
            if self.announce_drop_menu:
                self.check_drop_menu_status()
            time.sleep(0.1)

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