import threading
import time
import math
import queue
import pyautogui
from accessible_output2.outputs.auto import Auto
from lib.utilities import read_config
from lib.input_handler import is_key_pressed, VK_KEYS

class InventoryHandler:
    def __init__(self):
        self.speaker = Auto()
        self.inventory_open = False
        self.current_slot = 0
        self.dragging = False
        self.monitoring_thread = None
        self.movement_thread = None
        self.stop_monitoring = threading.Event()
        self.movement_queue = queue.Queue()
        
        # Mouse movement parameters - optimized for snappy response
        self.MOVEMENT_DURATION = 0.08  # Reduced for snappier movement
        self.MOVEMENT_STEPS = 15       # Reduced steps while maintaining smoothness
        
        # Key state tracking
        self.key_states = {
            'left': False,
            'right': False,
            'space': False
        }
        self.key_press_times = {
            'left': 0,
            'right': 0,
            'space': 0
        }
        
        # Timing constants - adjusted for better responsiveness
        self.REPEAT_DELAY = 0.3  # Reduced from 0.4
        self.REPEAT_RATE = 0.08  # Reduced from 0.1
        
        # Slot coordinates
        self.slots = [
            (1265, 820),  # Slot 1
            (1396, 820),  # Slot 2
            (1528, 820),  # Slot 3
            (1664, 820),  # Slot 4
            (1794, 820)   # Slot 5
        ]
        
        # Start threads
        self.start_monitoring()
        self.start_movement_handler()

    def smooth_move_to(self, x, y):
        """Queue a smooth movement request"""
        self.movement_queue.put((x, y))

    def handle_movement_queue(self):
        """Handle movement requests in a separate thread"""
        while not self.stop_monitoring.is_set():
            try:
                x, y = self.movement_queue.get(timeout=0.1)
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

    def navigate_to_slot(self, slot_index):
        """Move to a specific inventory slot"""
        self.smooth_move_to(self.slots[slot_index][0], self.slots[slot_index][1])
        self.speaker.speak(f"Slot {slot_index + 1}")

    def check_inventory_state(self):
        """Check if inventory is open based on UI pixels"""
        try:
            pixels = [(1800, 1028), (1783, 1027)]
            return all(
                pyautogui.pixelMatchesColor(x, y, (255, 255, 255))
                for x, y in pixels
            )
        except Exception:
            return False

    def handle_left_arrow(self):
        """Handle left arrow key press"""
        if not self.inventory_open:
            return
        self.current_slot = (self.current_slot - 1) % len(self.slots)
        self.navigate_to_slot(self.current_slot)

    def handle_right_arrow(self):
        """Handle right arrow key press"""
        if not self.inventory_open:
            return
        self.current_slot = (self.current_slot + 1) % len(self.slots)
        self.navigate_to_slot(self.current_slot)

    def handle_space(self):
        """Toggle drag state"""
        if not self.inventory_open:
            return
        self.dragging = not self.dragging
        if self.dragging:
            pyautogui.mouseDown(button='left', _pause=False)
            self.speaker.speak("Dragging")
        else:
            pyautogui.mouseUp(button='left', _pause=False)
            self.speaker.speak("Released")

    def should_handle_key(self, key):
        """Check if we should handle a key press based on timing"""
        current_time = time.time()
        key_pressed = is_key_pressed(key)
        was_pressed = self.key_states[key]
        last_press_time = self.key_press_times[key]
        
        if key_pressed:
            if not was_pressed:  # Initial press
                self.key_states[key] = True
                self.key_press_times[key] = current_time
                return True
            elif current_time - last_press_time > self.REPEAT_DELAY:
                if (current_time - last_press_time - self.REPEAT_DELAY) % self.REPEAT_RATE < 0.016:
                    return True
        else:
            self.key_states[key] = False
        
        return False

    def monitor_inventory(self):
        """Monitor inventory state and handle key presses"""
        prev_state = False
        
        while not self.stop_monitoring.is_set():
            try:
                current_state = self.check_inventory_state()
                
                # Handle inventory state change
                if current_state != prev_state:
                    self.inventory_open = current_state
                    if current_state:
                        self.current_slot = 0
                        self.navigate_to_slot(0)
                    elif self.dragging:
                        pyautogui.mouseUp(button='left', _pause=False)
                        self.dragging = False
                
                # Handle key presses if inventory is open
                if self.inventory_open:
                    if self.should_handle_key('left'):
                        self.handle_left_arrow()
                    elif self.should_handle_key('right'):
                        self.handle_right_arrow()
                    elif self.should_handle_key('space'):
                        self.handle_space()
                
                prev_state = current_state
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
        """Stop all threads"""
        self.stop_monitoring.set()
        if self.dragging:
            pyautogui.mouseUp(button='left', _pause=False)
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=1.0)
        if self.movement_thread:
            self.movement_thread.join(timeout=1.0)

# Create a single instance
inventory_handler = InventoryHandler()