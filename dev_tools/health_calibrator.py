"""
FA11y Health Bar Calibrator

Standalone dev utility. Ported out of the old ``lib/dev/dev_mode.py`` during
the 18.x refactor so the lib/ runtime no longer carries dev-only code.

Run from the repo root:

    python dev_tools/health_calibrator.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Optional, Tuple, List, Dict

import cv2
import numpy as np

# Let us import from lib/ without being installed as a package.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
os.chdir(_REPO_ROOT)

from lib.managers.screenshot_manager import screenshot_manager


class HealthCalibrator:
    """
    Auto-calibration tool for health bar detection.

    Press 'L' to find the next pixel position automatically.
    The tool searches for matching pixels and calculates the decrease pattern.
    """

    def __init__(self):
        """Initialize the Health Calibrator."""
        from pynput import keyboard

        # Starting known good position (calibrated values)
        self.health_color = (247, 255, 26)
        self.tolerance = 30
        self.start_x = 408
        self.start_y = 1000

        # Calibration state
        self.current_health = 100
        self.positions = {}  # Maps health value to x position
        self.positions[100] = self.start_x  # Known starting position
        self.decreases = []  # Will store the decrease pattern

        self.running = False
        self.searching = False
        self.last_press_time = 0

        # Window settings
        self.window_name = "Health Calibrator"

        # Keyboard listener
        self.listener = None

        print(f"[Calibrator] Health Calibrator initialized")
        print(f"[Calibrator] Starting position: ({self.start_x}, {self.start_y})")
        print(f"[Calibrator] Target color: RGB{self.health_color}, Tolerance: {self.tolerance}")

    def pixel_within_tolerance(self, pixel_color, target_color, tol):
        """Check if pixel color is within tolerance of target color."""
        return all(abs(pc - tc) <= tol for pc, tc in zip(pixel_color, target_color))

    def find_next_pixel(self, screenshot_rgb, start_x, y, max_search=50):
        """
        Find the next pixel that matches the health color.

        Args:
            screenshot_rgb: Screenshot in RGB format
            start_x: X position to start searching from (going left)
            y: Y position
            max_search: Maximum pixels to search

        Returns:
            X position of matching pixel, or None if not found
        """
        for offset in range(1, max_search + 1):
            x = start_x - offset

            if x < 0 or x >= screenshot_rgb.shape[1]:
                continue

            if 0 <= y < screenshot_rgb.shape[0]:
                pixel_rgb = screenshot_rgb[y, x]
                pixel_color = (int(pixel_rgb[0]), int(pixel_rgb[1]), int(pixel_rgb[2]))

                if self.pixel_within_tolerance(pixel_color, self.health_color, self.tolerance):
                    return x

        return None

    def on_key_press(self, key):
        """Handle keyboard input."""
        import time
        try:
            # Prevent double-presses
            current_time = time.time()
            if current_time - self.last_press_time < 0.3:
                return

            if hasattr(key, 'char') and key.char == 'l':
                self.last_press_time = current_time

                if self.current_health <= 1:
                    print("[Calibrator] Already at minimum health (1)")
                    return

                if self.searching:
                    print("[Calibrator] Already searching...")
                    return

                self.searching = True
                print(f"\n[Calibrator] Finding pixel for health {self.current_health - 1}...")

        except AttributeError:
            pass

    def save_calibration(self):
        """Save calibration data to file."""
        import json
        from datetime import datetime

        # Calculate decrease pattern
        if len(self.positions) >= 2:
            health_values = sorted(self.positions.keys(), reverse=True)
            self.decreases = []

            for i in range(len(health_values) - 1):
                current_hp = health_values[i]
                next_hp = health_values[i + 1]
                current_x = self.positions[current_hp]
                next_x = self.positions[next_hp]
                decrease = current_x - next_x
                self.decreases.append(decrease)

        # Prepare data
        calibration_data = {
            'timestamp': datetime.now().isoformat(),
            'health_start_position': (self.start_x, self.start_y),
            'health_color': self.health_color,
            'tolerance': self.tolerance,
            'positions': {str(k): v for k, v in self.positions.items()},
            'decreases_full': self.decreases,
            'decreases_pattern': self._calculate_pattern(),
            'total_calibrated': len(self.positions)
        }

        # Save to file
        filename = 'health_calibration.json'
        with open(filename, 'w') as f:
            json.dump(calibration_data, f, indent=2)

        print(f"\n[Calibrator] Calibration saved to: {filename}")
        print(f"[Calibrator] Total positions calibrated: {len(self.positions)}")
        print(f"[Calibrator] Decreases pattern: {calibration_data['decreases_pattern']}")

        return filename

    def _calculate_pattern(self):
        """Calculate the repeating pattern from decreases."""
        if len(self.decreases) < 4:
            return self.decreases

        # Try to find a repeating pattern
        for pattern_len in [4, 3, 2]:
            if len(self.decreases) >= pattern_len * 3:
                pattern = self.decreases[:pattern_len]
                # Check if it repeats
                matches = True
                for i in range(pattern_len, min(len(self.decreases), pattern_len * 3)):
                    if self.decreases[i] != pattern[i % pattern_len]:
                        matches = False
                        break

                if matches:
                    return pattern

        # No clear pattern, return first 4 or all
        return self.decreases[:min(4, len(self.decreases))]

    def draw_status_window(self):
        """Draw a small status window."""
        # Small window
        window_width = 400
        window_height = 250
        status = np.zeros((window_height, window_width, 3), dtype=np.uint8)

        font = cv2.FONT_HERSHEY_SIMPLEX
        y_pos = 30

        # Title
        cv2.putText(status, "HEALTH BAR CALIBRATOR", (10, y_pos),
                   font, 0.6, (0, 255, 255), 2)

        y_pos += 35
        cv2.putText(status, f"Current: {self.current_health} HP", (10, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        y_pos += 30
        if self.current_health in self.positions:
            cv2.putText(status, f"Position: x={self.positions[self.current_health]}", (10, y_pos),
                       font, 0.5, (0, 255, 0), 1)
        else:
            cv2.putText(status, "Position: Not calibrated", (10, y_pos),
                       font, 0.5, (255, 255, 0), 1)

        y_pos += 30
        cv2.putText(status, f"Calibrated: {len(self.positions)}/100", (10, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        y_pos += 30
        if self.searching:
            cv2.putText(status, "Status: SEARCHING...", (10, y_pos),
                       font, 0.5, (0, 255, 255), 1)
        else:
            cv2.putText(status, "Status: Ready", (10, y_pos),
                       font, 0.5, (0, 255, 0), 1)

        # Instructions
        y_pos += 40
        cv2.putText(status, "CONTROLS:", (10, y_pos),
                   font, 0.5, (0, 255, 255), 1)

        y_pos += 25
        cv2.putText(status, "L - Find next pixel", (10, y_pos),
                   font, 0.4, (255, 255, 255), 1)

        y_pos += 20
        cv2.putText(status, "S - Save calibration", (10, y_pos),
                   font, 0.4, (255, 255, 255), 1)

        y_pos += 20
        cv2.putText(status, "Q - Exit", (10, y_pos),
                   font, 0.4, (255, 255, 255), 1)

        return status

    def run(self):
        """Run the calibration tool."""
        from pynput import keyboard

        print("\n" + "=" * 60)
        print("FA11y Health Bar Auto-Calibrator")
        print("=" * 60)
        print("\nInstructions:")
        print("1. Set your health to 100 in-game")
        print("2. Press 'L' to find each successive pixel")
        print("3. The tool will automatically find the next matching pixel")
        print("4. Press 'S' to save when done")
        print("5. Press 'Q' to exit")
        print("=" * 60 + "\n")

        self.running = True

        # Start keyboard listener
        self.listener = keyboard.Listener(on_press=self.on_key_press)
        self.listener.start()

        # Create window (always on top)
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, 400, 250)
        cv2.setWindowProperty(self.window_name, cv2.WND_PROP_TOPMOST, 1)

        try:
            while self.running:
                # Capture screenshot
                screenshot_bgr = screenshot_manager.capture_full_screen()

                if screenshot_bgr is None:
                    print("[Calibrator] Warning: Failed to capture screenshot")
                    cv2.waitKey(100)
                    continue

                # Convert to RGB
                screenshot_rgb = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2RGB)

                # If searching, find the next pixel
                if self.searching:
                    last_x = self.positions[self.current_health]
                    next_x = self.find_next_pixel(screenshot_rgb, last_x, self.start_y)

                    if next_x is not None:
                        next_health = self.current_health - 1
                        self.positions[next_health] = next_x
                        decrease = last_x - next_x
                        self.decreases.append(decrease)

                        print(f"[Calibrator] Found! {next_health} HP at x={next_x} (decrease: -{decrease})")
                        self.current_health = next_health

                        if next_health == 1:
                            print("\n[Calibrator] Calibration complete!")
                            self.save_calibration()
                    else:
                        print(f"[Calibrator] Could not find pixel for {self.current_health - 1} HP")

                    self.searching = False

                # Draw status window
                status_window = self.draw_status_window()
                cv2.imshow(self.window_name, status_window)

                # Check for key press in OpenCV window
                key = cv2.waitKey(100) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    self.save_calibration()

        except KeyboardInterrupt:
            print("\n[Calibrator] Interrupted by user")

        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        print(f"\n[Calibrator] Shutting down...")

        if self.listener:
            self.listener.stop()

        self.running = False
        cv2.destroyAllWindows()
        cv2.waitKey(1)

        print("[Calibrator] Calibrator closed.")

def main():
    tool = HealthCalibrator()
    try:
        tool.run()
    except Exception as e:
        print(f"[HealthCalibrator] fatal: {e}")
        raise


if __name__ == "__main__":
    main()
