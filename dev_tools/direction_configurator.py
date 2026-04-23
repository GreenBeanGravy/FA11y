"""
FA11y Direction Configurator

Standalone dev utility. Ported out of the old ``lib/dev/dev_mode.py`` during
the 18.x refactor so the lib/ runtime no longer carries dev-only code.

Run from the repo root:

    python dev_tools/direction_configurator.py
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
from lib.detection import ppi

class DirectionConfigurator:
    """
    Developer tool for configuring and visualizing player direction detection.

    Features:
    - Live minimap icon capture
    - Contour detection visualization
    - Triangle tip detection
    - Direction angle and cardinal direction
    - Interactive parameter adjustment
    """

    def __init__(self):
        """Initialize the Direction Configurator."""
        # Detection parameters
        self.scale_factor = 4
        self.white_threshold_min = 253
        self.white_threshold_max = 255
        self.min_area = 800
        self.max_area = 1100

        # Minimap regions (editable)
        self.minimap_x = 1735
        self.minimap_y = 154
        self.minimap_width = 31  # 1766 - 1735
        self.minimap_height = 30  # 184 - 154

        # Main screen regions (editable)
        self.main_x = 524
        self.main_y = 84
        self.main_width = 866  # 1390 - 524
        self.main_height = 926  # 1010 - 84

        self.main_min_area = 1008
        self.main_max_area = 1386

        # State
        self.running = False
        self.use_minimap = True  # True = minimap, False = main screen
        self.view_mode = 0  # 0=all, 1=original, 2=upscaled, 3=mask, 4=contours
        self.window_name = "FA11y Direction Configurator (Interactive)"

        # Keyboard state tracking (using pynput)
        self.keys_pressed = set()
        self.shift_pressed = False
        self.keyboard_listener = None

        print(f"[Dev Mode] Direction Configurator initialized")
        print(f"[Dev Mode] Default scale factor: {self.scale_factor}x")

    def find_triangle_tip(self, contour, center_mass):
        """Find the tip of a triangular shape."""
        triangle = cv2.minEnclosingTriangle(contour)[1]
        if triangle is None or len(triangle) < 3:
            return None

        points = triangle.reshape(-1, 2).astype(np.int32)

        distances = np.zeros((3, 3))
        for i in range(3):
            for j in range(3):
                distances[i, j] = np.linalg.norm(points[i] - points[j])

        total_distances = np.sum(distances, axis=1)
        tip_idx = np.argmax(total_distances)

        return points[tip_idx]

    def get_cardinal_direction(self, angle):
        """Convert angle to cardinal direction."""
        directions = ['North', 'Northeast', 'East', 'Southeast',
                     'South', 'Southwest', 'West', 'Northwest']
        return directions[int((angle + 22.5) % 360 // 45)]

    def capture_region(self):
        """Capture the appropriate region based on current mode."""
        from lib.utilities.mouse import screenshot as _screenshot

        if self.use_minimap:
            region = (self.minimap_x, self.minimap_y, self.minimap_width, self.minimap_height)
        else:
            region = (self.main_x, self.main_y, self.main_width, self.main_height)

        screenshot_rgba = np.array(_screenshot(region=region))
        if screenshot_rgba.shape[2] == 4:
            return cv2.cvtColor(screenshot_rgba, cv2.COLOR_RGBA2RGB)
        return screenshot_rgba

    def process_and_detect(self, screenshot):
        """Process screenshot and detect direction."""
        # Upscale
        screenshot_large = cv2.resize(screenshot, None,
                                     fx=self.scale_factor, fy=self.scale_factor,
                                     interpolation=cv2.INTER_LINEAR)

        # Create white mask
        white_mask = cv2.inRange(screenshot_large,
                                (self.white_threshold_min,) * 3,
                                (self.white_threshold_max,) * 3)

        # Find contours
        contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Detection results
        detected_direction = None
        detected_angle = None
        valid_contour = None
        center_mass = None
        tip_point = None

        # Get appropriate area thresholds
        min_area = self.min_area if self.use_minimap else self.main_min_area
        max_area = self.max_area if self.use_minimap else self.main_max_area

        for contour in contours:
            area = cv2.contourArea(contour)
            if min_area < area < max_area:
                M = cv2.moments(contour)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    center_mass = np.array([cx, cy])

                    tip_point = self.find_triangle_tip(contour, center_mass)
                    if tip_point is not None:
                        direction_vector = tip_point - center_mass
                        angle = np.degrees(np.arctan2(-direction_vector[1], direction_vector[0]))
                        angle = (90 - angle) % 360

                        detected_angle = angle
                        detected_direction = self.get_cardinal_direction(angle)
                        valid_contour = contour
                        break

        return {
            'screenshot_large': screenshot_large,
            'white_mask': white_mask,
            'contours': contours,
            'valid_contour': valid_contour,
            'center_mass': center_mass,
            'tip_point': tip_point,
            'angle': detected_angle,
            'direction': detected_direction,
            'min_area': min_area,
            'max_area': max_area
        }

    def draw_visualization(self, screenshot, results):
        """Draw the complete visualization."""
        screenshot_large = results['screenshot_large']
        white_mask = results['white_mask']
        contours = results['contours']
        valid_contour = results['valid_contour']
        center_mass = results['center_mass']
        tip_point = results['tip_point']
        angle = results['angle']
        direction = results['direction']
        min_area = results['min_area']
        max_area = results['max_area']

        # Create display images based on view mode
        if self.view_mode == 0:  # All views
            # Original
            original_display = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
            original_display = cv2.resize(original_display, (300, 300), interpolation=cv2.INTER_NEAREST)

            # Upscaled
            upscaled_display = cv2.cvtColor(screenshot_large, cv2.COLOR_RGB2BGR)

            # Mask
            mask_display = cv2.cvtColor(white_mask, cv2.COLOR_GRAY2BGR)

            # Contours view
            contours_display = cv2.cvtColor(screenshot_large, cv2.COLOR_RGB2BGR)

            # Draw all contours
            for contour in contours:
                area = cv2.contourArea(contour)
                if min_area < area < max_area:
                    cv2.drawContours(contours_display, [contour], -1, (0, 255, 0), 2)
                else:
                    cv2.drawContours(contours_display, [contour], -1, (0, 0, 255), 1)

            # Draw detection on valid contour
            if valid_contour is not None:
                # Draw contour
                cv2.drawContours(contours_display, [valid_contour], -1, (0, 255, 0), 3)

                # Draw center of mass
                if center_mass is not None:
                    cv2.circle(contours_display, tuple(center_mass), 5, (255, 0, 0), -1)

                # Draw triangle tip
                if tip_point is not None:
                    cv2.circle(contours_display, tuple(tip_point), 5, (0, 0, 255), -1)

                    # Draw direction line
                    if center_mass is not None:
                        cv2.line(contours_display, tuple(center_mass), tuple(tip_point),
                                (0, 255, 255), 2)

                        # Draw extended direction line
                        direction_vector = tip_point - center_mass
                        extended_point = center_mass + direction_vector * 3
                        cv2.arrowedLine(contours_display, tuple(center_mass),
                                      tuple(extended_point.astype(int)), (255, 0, 255), 3, tipLength=0.3)

            # Stack views
            top_row = np.hstack([original_display,
                                cv2.resize(mask_display, (300, 300))])
            bottom_row = contours_display

            # Make bottom row same width as top row
            scale = top_row.shape[1] / bottom_row.shape[1]
            bottom_row = cv2.resize(bottom_row, None, fx=scale, fy=scale)

            main_view = np.vstack([top_row, bottom_row])

        else:  # Individual views
            if self.view_mode == 1:
                main_view = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
            elif self.view_mode == 2:
                main_view = cv2.cvtColor(screenshot_large, cv2.COLOR_RGB2BGR)
            elif self.view_mode == 3:
                main_view = cv2.cvtColor(white_mask, cv2.COLOR_GRAY2BGR)
            else:  # mode 4
                main_view = cv2.cvtColor(screenshot_large, cv2.COLOR_RGB2BGR)

            # Resize for consistent display
            main_view = cv2.resize(main_view, (800, 800), interpolation=cv2.INTER_NEAREST)

        # Create info panel
        panel_height = 300
        panel_width = main_view.shape[1]
        panel = np.zeros((panel_height, panel_width, 3), dtype=np.uint8)

        font = cv2.FONT_HERSHEY_SIMPLEX
        y_pos = 25

        # Title
        cv2.putText(panel, "DIRECTION CONFIGURATOR", (10, y_pos),
                   font, 0.7, (0, 255, 255), 2)

        y_pos += 30
        mode_text = "MINIMAP" if self.use_minimap else "MAIN SCREEN"
        cv2.putText(panel, f"Mode: {mode_text}", (10, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        y_pos += 25
        if direction and angle is not None:
            cv2.putText(panel, f"Direction: {direction} ({angle:.1f} deg)", (10, y_pos),
                       font, 0.5, (0, 255, 0), 2)
        else:
            cv2.putText(panel, "Direction: NOT DETECTED", (10, y_pos),
                       font, 0.5, (0, 0, 255), 1)

        y_pos += 30
        cv2.putText(panel, f"Scale Factor: {self.scale_factor}x", (10, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        y_pos += 22
        cv2.putText(panel, f"White Threshold: {self.white_threshold_min}-{self.white_threshold_max}",
                   (10, y_pos), font, 0.5, (255, 255, 255), 1)

        y_pos += 22
        cv2.putText(panel, f"Area Range: {min_area}-{max_area}", (10, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        y_pos += 22
        cv2.putText(panel, f"Contours Found: {len(contours)}", (10, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        y_pos += 22
        if self.use_minimap:
            region_text = f"Region: ({self.minimap_x}, {self.minimap_y}) {self.minimap_width}x{self.minimap_height}"
        else:
            region_text = f"Region: ({self.main_x}, {self.main_y}) {self.main_width}x{self.main_height}"
        cv2.putText(panel, region_text, (10, y_pos), font, 0.5, (255, 255, 255), 1)

        # Controls
        y_pos += 25
        cv2.putText(panel, "CONTROLS:", (10, y_pos), font, 0.5, (0, 255, 255), 1)

        y_pos += 18
        cv2.putText(panel, "T: Mode | Arrows: Move region | HJKL: Resize", (10, y_pos),
                   font, 0.4, (255, 255, 255), 1)

        y_pos += 18
        cv2.putText(panel, "W/S: White min | E/D: White max | A/Z: Min area", (10, y_pos),
                   font, 0.4, (255, 255, 255), 1)

        y_pos += 18
        cv2.putText(panel, "V: View mode | P: Print | ESC: Exit", (10, y_pos),
                   font, 0.4, (255, 255, 255), 1)

        # Combine
        combined = np.vstack([main_view, panel])

        return combined

    def _on_key_press(self, key):
        """Handle key press events."""
        from pynput import keyboard
        try:
            # Check for shift
            if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                self.shift_pressed = True
            # Store other keys
            elif hasattr(key, 'char'):
                self.keys_pressed.add(key.char)
            else:
                self.keys_pressed.add(key)
        except AttributeError:
            pass

    def _on_key_release(self, key):
        """Handle key release events."""
        from pynput import keyboard
        try:
            # Check for shift release
            if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                self.shift_pressed = False
            # Remove from pressed set
            elif hasattr(key, 'char'):
                self.keys_pressed.discard(key.char)
            else:
                self.keys_pressed.discard(key)
        except AttributeError:
            pass

    def print_current_config(self):
        """Print current configuration to console."""
        print("\n" + "="*60)
        print("DIRECTION CONFIGURATOR - CURRENT CONFIGURATION:")
        print("="*60)
        print(f"Mode: {'MINIMAP' if self.use_minimap else 'MAIN SCREEN'}")
        if self.use_minimap:
            print(f"Minimap Region: x={self.minimap_x}, y={self.minimap_y}, width={self.minimap_width}, height={self.minimap_height}")
            print(f"Area Range: {self.min_area}-{self.max_area}")
        else:
            print(f"Main Screen Region: x={self.main_x}, y={self.main_y}, width={self.main_width}, height={self.main_height}")
            print(f"Area Range: {self.main_min_area}-{self.main_max_area}")
        print(f"Scale Factor: {self.scale_factor}x")
        print(f"White Threshold: {self.white_threshold_min}-{self.white_threshold_max}")
        print(f"View Mode: {self.view_mode}")
        print("="*60 + "\n")

    def run(self):
        """Run the direction configurator tool."""
        print("\n" + "=" * 60)
        print("FA11y Direction Configurator")
        print("=" * 60)
        print("\nControls:")
        print("  T           - Toggle between minimap and main screen icon")
        print("  Arrow Keys  - Move capture region (hold Shift for fine control)")
        print("  H/L         - Decrease/increase region width")
        print("  J/K         - Decrease/increase region height")
        print("  1/2         - Increase/decrease scale factor")
        print("  W/S         - Adjust white threshold min")
        print("  E/D         - Adjust white threshold max")
        print("  A/Z         - Adjust min area")
        print("  V           - Cycle view mode")
        print("  P           - Print current config")
        print("  ESC         - Exit")
        print("=" * 60 + "\n")

        self.running = True
        self.print_current_config()

        # Start keyboard listener (pynput)
        from pynput import keyboard
        self.keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        self.keyboard_listener.start()

        # Create window
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, 900, 900)

        # Track last processed keys to avoid repeats
        last_keys = set()

        try:
            while self.running:
                # Capture region
                screenshot = self.capture_region()

                # Process and detect
                results = self.process_and_detect(screenshot)

                # Draw visualization
                visualization = self.draw_visualization(screenshot, results)
                cv2.imshow(self.window_name, visualization)

                # Keep window responsive
                cv2.waitKey(1)

                # Handle keyboard input using pynput state
                from pynput import keyboard
                current_keys = self.keys_pressed.copy()

                # Process newly pressed keys (avoid repeats)
                new_keys = current_keys - last_keys

                # Determine step size based on Shift modifier
                if self.use_minimap:
                    step_size = 1 if self.shift_pressed else 5
                else:
                    step_size = 1 if self.shift_pressed else 10

                # Character keys (one-time actions)
                if keyboard.Key.esc in current_keys:
                    break
                elif 't' in new_keys:
                    self.use_minimap = not self.use_minimap
                    mode = "MINIMAP" if self.use_minimap else "MAIN SCREEN"
                    print(f"[Dev Mode] Mode: {mode}")
                elif '1' in new_keys:
                    self.scale_factor = min(10, self.scale_factor + 1)
                    print(f"[Dev Mode] Scale factor: {self.scale_factor}x")
                elif '2' in new_keys:
                    self.scale_factor = max(1, self.scale_factor - 1)
                    print(f"[Dev Mode] Scale factor: {self.scale_factor}x")
                elif 'h' in new_keys:
                    if self.use_minimap:
                        self.minimap_width = max(10, self.minimap_width - 5)
                        print(f"[Dev Mode] Minimap size: {self.minimap_width}x{self.minimap_height}")
                    else:
                        self.main_width = max(50, self.main_width - 10)
                        print(f"[Dev Mode] Main size: {self.main_width}x{self.main_height}")
                elif 'l' in new_keys:
                    if self.use_minimap:
                        self.minimap_width += 5
                        print(f"[Dev Mode] Minimap size: {self.minimap_width}x{self.minimap_height}")
                    else:
                        self.main_width += 10
                        print(f"[Dev Mode] Main size: {self.main_width}x{self.main_height}")
                elif 'j' in new_keys:
                    if self.use_minimap:
                        self.minimap_height = max(10, self.minimap_height - 5)
                        print(f"[Dev Mode] Minimap size: {self.minimap_width}x{self.minimap_height}")
                    else:
                        self.main_height = max(50, self.main_height - 10)
                        print(f"[Dev Mode] Main size: {self.main_width}x{self.main_height}")
                elif 'k' in new_keys:
                    if self.use_minimap:
                        self.minimap_height += 5
                        print(f"[Dev Mode] Minimap size: {self.minimap_width}x{self.minimap_height}")
                    else:
                        self.main_height += 10
                        print(f"[Dev Mode] Main size: {self.main_width}x{self.main_height}")
                elif 'w' in new_keys:
                    self.white_threshold_min = min(255, self.white_threshold_min + 1)
                    print(f"[Dev Mode] White threshold: {self.white_threshold_min}-{self.white_threshold_max}")
                elif 's' in new_keys:
                    self.white_threshold_min = max(0, self.white_threshold_min - 1)
                    print(f"[Dev Mode] White threshold: {self.white_threshold_min}-{self.white_threshold_max}")
                elif 'e' in new_keys:
                    self.white_threshold_max = min(255, self.white_threshold_max + 1)
                    print(f"[Dev Mode] White threshold: {self.white_threshold_min}-{self.white_threshold_max}")
                elif 'd' in new_keys:
                    self.white_threshold_max = max(0, self.white_threshold_max - 1)
                    print(f"[Dev Mode] White threshold: {self.white_threshold_min}-{self.white_threshold_max}")
                elif 'a' in new_keys:
                    if self.use_minimap:
                        self.min_area += 10
                        print(f"[Dev Mode] Min area: {self.min_area}")
                    else:
                        self.main_min_area += 10
                        print(f"[Dev Mode] Min area: {self.main_min_area}")
                elif 'z' in new_keys:
                    if self.use_minimap:
                        self.min_area = max(0, self.min_area - 10)
                        print(f"[Dev Mode] Min area: {self.min_area}")
                    else:
                        self.main_min_area = max(0, self.main_min_area - 10)
                        print(f"[Dev Mode] Min area: {self.main_min_area}")
                elif 'q' in new_keys:
                    if self.use_minimap:
                        self.max_area += 10
                        print(f"[Dev Mode] Max area: {self.max_area}")
                    else:
                        self.main_max_area += 10
                        print(f"[Dev Mode] Max area: {self.main_max_area}")
                elif 'x' in new_keys:
                    if self.use_minimap:
                        self.max_area = max(0, self.max_area - 10)
                        print(f"[Dev Mode] Max area: {self.max_area}")
                    else:
                        self.main_max_area = max(0, self.main_max_area - 10)
                        print(f"[Dev Mode] Main area: {self.main_max_area}")
                elif 'v' in new_keys:
                    self.view_mode = (self.view_mode + 1) % 5
                    modes = ["All", "Original", "Upscaled", "Mask", "Contours"]
                    print(f"[Dev Mode] View mode: {modes[self.view_mode]}")
                elif 'p' in new_keys:
                    self.print_current_config()

                # Arrow keys (allow continuous movement)
                if keyboard.Key.up in current_keys:
                    if self.use_minimap:
                        self.minimap_y = max(0, self.minimap_y - step_size)
                        print(f"[Dev Mode] Minimap region moved to ({self.minimap_x}, {self.minimap_y})")
                    else:
                        self.main_y = max(0, self.main_y - step_size)
                        print(f"[Dev Mode] Main region moved to ({self.main_x}, {self.main_y})")
                if keyboard.Key.down in current_keys:
                    if self.use_minimap:
                        self.minimap_y += step_size
                        print(f"[Dev Mode] Minimap region moved to ({self.minimap_x}, {self.minimap_y})")
                    else:
                        self.main_y += step_size
                        print(f"[Dev Mode] Main region moved to ({self.main_x}, {self.main_y})")
                if keyboard.Key.left in current_keys:
                    if self.use_minimap:
                        self.minimap_x = max(0, self.minimap_x - step_size)
                        print(f"[Dev Mode] Minimap region moved to ({self.minimap_x}, {self.minimap_y})")
                    else:
                        self.main_x = max(0, self.main_x - step_size)
                        print(f"[Dev Mode] Main region moved to ({self.main_x}, {self.main_y})")
                if keyboard.Key.right in current_keys:
                    if self.use_minimap:
                        self.minimap_x += step_size
                        print(f"[Dev Mode] Minimap region moved to ({self.minimap_x}, {self.minimap_y})")
                    else:
                        self.main_x += step_size
                        print(f"[Dev Mode] Main region moved to ({self.main_x}, {self.main_y})")

                last_keys = current_keys

        except KeyboardInterrupt:
            print("\n[Dev Mode] Interrupted by user")

        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        print(f"\n[Dev Mode] Shutting down Direction Configurator...")
        self.running = False

        # Stop keyboard listener
        if self.keyboard_listener:
            self.keyboard_listener.stop()
            self.keyboard_listener = None

        cv2.destroyAllWindows()
        cv2.waitKey(1)
        print("[Dev Mode] Direction Configurator closed.")

def main():
    tool = DirectionConfigurator()
    try:
        tool.run()
    except Exception as e:
        print(f"[DirectionConfigurator] fatal: {e}")
        raise


if __name__ == "__main__":
    main()
