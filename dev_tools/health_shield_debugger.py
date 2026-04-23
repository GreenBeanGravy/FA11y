"""
FA11y Health / Shield Debugger

Standalone dev utility. Ported out of the old ``lib/dev/dev_mode.py`` during
the 18.x refactor so the lib/ runtime no longer carries dev-only code.

Run from the repo root:

    python dev_tools/health_shield_debugger.py
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


class HealthShieldDebugger:
    """
    Developer tool for debugging health and shield bar detection.

    Features:
    - Visualizes exactly which pixels are being checked
    - Shows RGB values at each pixel location
    - Displays tolerance check results
    - Highlights the matching pixel (if found)
    - Shows the path the checker follows
    """

    def __init__(self):
        """Initialize the Health/Shield Debugger."""
        # Health/Shield detection parameters (from hsr.py)
        self.health_color = (247, 255, 26)
        self.shield_color = (213, 255, 232)
        self.tolerance = 30  # Stricter tolerance

        # Full calibrated decrease pattern (from health_calibrator)
        self.health_decreases = [3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 3, 4, 4, 3, 4, 3, 3, 3, 4, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 3]
        self.shield_decreases = self.health_decreases

        self.health_start_x = 408
        self.health_y = 1000
        self.shield_start_x = 408
        self.shield_y = 970

        self.window_name = "FA11y Health/Shield Debugger (Interactive)"
        self.running = False

        # Interactive mode state
        self.selected_pattern_index = 0  # Which decrease pattern index is selected
        self.editing_health = True  # True = editing health, False = editing shield

        print(f"[Dev Mode] Health/Shield Debugger initialized")
        print(f"[Dev Mode] Interactive mode enabled - use keyboard to adjust parameters")

    def pixel_within_tolerance(self, pixel_color, target_color, tol):
        """Check if pixel color is within tolerance of target color."""
        return all(abs(pc - tc) <= tol for pc, tc in zip(pixel_color, target_color))

    def get_checked_pixels(self, start_x, y, decreases, max_value=100):
        """
        Get the list of pixel coordinates that will be checked.

        Returns:
            List of (x, y, value) tuples
        """
        pixels = []
        x = start_x
        for i in range(max_value, 0, -1):
            pixels.append((x, y, i))
            if decreases:
                x -= decreases[i % len(decreases)]
            else:
                x -= 1
        return pixels

    def check_and_visualize_bar(self, screenshot_rgb, start_x, y, decreases, color,
                                name, pixels_data):
        """
        Check a health/shield bar and collect visualization data.

        Args:
            screenshot_rgb: Screenshot in RGB format
            start_x: Starting x coordinate
            y: Y coordinate of the bar
            decreases: Array of x-decrements
            color: Target RGB color
            name: Name of the bar (Health/Shield)
            pixels_data: List to append pixel data to

        Returns:
            Detected value or None
        """
        x = start_x
        detected_value = None

        for i in range(100, 0, -1):
            if 0 <= x < screenshot_rgb.shape[1] and 0 <= y < screenshot_rgb.shape[0]:
                pixel_rgb = screenshot_rgb[y, x]
                pixel_color = (int(pixel_rgb[0]), int(pixel_rgb[1]), int(pixel_rgb[2]))

                within_tol = self.pixel_within_tolerance(pixel_color, color, self.tolerance)

                pixels_data.append({
                    'x': x,
                    'y': y,
                    'value': i,
                    'color': pixel_color,
                    'within_tolerance': within_tol,
                    'name': name
                })

                if within_tol and detected_value is None:
                    detected_value = i

            if decreases:
                x -= decreases[i % len(decreases)]
            else:
                x -= 1

        return detected_value

    def print_current_config(self):
        """Print the current configuration to console."""
        print("\n" + "="*60)
        print("CURRENT CONFIGURATION:")
        print("="*60)
        print(f"Health Start Position: ({self.health_start_x}, {self.health_y})")
        print(f"Shield Start Position: ({self.shield_start_x}, {self.shield_y})")
        print(f"Health Decreases: {self.health_decreases}")
        print(f"Shield Decreases: {self.shield_decreases}")
        print(f"Tolerance: {self.tolerance}")
        print("="*60 + "\n")

    def get_bounding_box(self, pixels_data, padding=50):
        """
        Calculate the bounding box that encompasses all checked pixels.

        Args:
            pixels_data: List of pixel data dictionaries
            padding: Extra padding around the bounding box

        Returns:
            Tuple of (x1, y1, x2, y2) or None if no pixels
        """
        if not pixels_data:
            return None

        x_coords = [p['x'] for p in pixels_data]
        y_coords = [p['y'] for p in pixels_data]

        min_x = max(0, min(x_coords) - padding)
        max_x = max(x_coords) + padding
        min_y = max(0, min(y_coords) - padding)
        max_y = max(y_coords) + padding

        return (min_x, min_y, max_x, max_y)

    def draw_visualization(self, screenshot_bgr, pixels_data, detected_health, detected_shield):
        """
        Draw visualization overlay on the screenshot.

        Args:
            screenshot_bgr: Screenshot in BGR format (for OpenCV display)
            pixels_data: List of pixel data dictionaries
            detected_health: Detected health value
            detected_shield: Detected shield value

        Returns:
            Annotated screenshot
        """
        # Get bounding box and crop the visualization
        bbox = self.get_bounding_box(pixels_data, padding=100)
        if bbox is None:
            # Fallback if no pixels
            vis = screenshot_bgr.copy()
            crop_offset_x, crop_offset_y = 0, 0
        else:
            x1, y1, x2, y2 = bbox
            # Crop to the bounding box
            vis = screenshot_bgr[y1:y2, x1:x2].copy()
            crop_offset_x, crop_offset_y = x1, y1

        # Draw all checked pixels (adjust coordinates for cropped view)
        for data in pixels_data:
            x, y = data['x'] - crop_offset_x, data['y'] - crop_offset_y
            within_tol = data['within_tolerance']
            name = data['name']

            # Skip if outside cropped area
            if x < 0 or y < 0 or x >= vis.shape[1] or y >= vis.shape[0]:
                continue

            # Color code the pixels
            if within_tol:
                # Green for pixels within tolerance
                color = (0, 255, 0)
                size = 3
            else:
                # Red for pixels outside tolerance
                if name == 'Health':
                    color = (0, 0, 255)  # Red for health
                else:
                    color = (255, 0, 0)  # Blue for shield
                size = 1

            # Draw a circle at each checked pixel
            cv2.circle(vis, (x, y), size, color, -1)

        # Draw starting positions with larger markers (adjust for crop)
        health_x = self.health_start_x - crop_offset_x
        health_y = self.health_y - crop_offset_y
        shield_x = self.shield_start_x - crop_offset_x
        shield_y = self.shield_y - crop_offset_y

        if 0 <= health_x < vis.shape[1] and 0 <= health_y < vis.shape[0]:
            marker_color = (0, 255, 255) if self.editing_health else (128, 128, 128)
            cv2.circle(vis, (health_x, health_y), 7, marker_color, 2)
            cv2.putText(vis, "Health Start", (health_x + 10, health_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, marker_color, 1)

        if 0 <= shield_x < vis.shape[1] and 0 <= shield_y < vis.shape[0]:
            marker_color = (0, 255, 255) if not self.editing_health else (128, 128, 128)
            cv2.circle(vis, (shield_x, shield_y), 7, marker_color, 2)
            cv2.putText(vis, "Shield Start", (shield_x + 10, shield_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, marker_color, 1)

        # Create info panel
        panel_height = 400
        panel_width = vis.shape[1]
        panel = np.zeros((panel_height, panel_width, 3), dtype=np.uint8)

        # Display detected values
        font = cv2.FONT_HERSHEY_SIMPLEX
        y_pos = 25

        # Title
        cv2.putText(panel, "INTERACTIVE HEALTH & SHIELD DEBUGGER", (10, y_pos),
                   font, 0.7, (0, 255, 255), 2)

        y_pos += 35
        health_text = f"Health: {detected_health if detected_health else 'NOT DETECTED'}"
        health_color = (0, 255, 0) if detected_health else (0, 0, 255)
        cv2.putText(panel, health_text, (10, y_pos), font, 0.6, health_color, 2)

        y_pos += 30
        shield_text = f"Shield: {detected_shield if detected_shield else 'NOT DETECTED'}"
        shield_color = (0, 255, 0) if detected_shield else (0, 0, 255)
        cv2.putText(panel, shield_text, (10, y_pos), font, 0.6, shield_color, 2)

        # Current settings
        y_pos += 35
        mode = "HEALTH" if self.editing_health else "SHIELD"
        cv2.putText(panel, f"Editing: {mode} (Press TAB to switch)", (10, y_pos),
                   font, 0.5, (255, 255, 0), 1)

        y_pos += 25
        current_decreases = self.health_decreases if self.editing_health else self.shield_decreases
        pattern_display = [f"[{val}]" if i == self.selected_pattern_index else f"{val}"
                          for i, val in enumerate(current_decreases)]
        cv2.putText(panel, f"Pattern: {' '.join(pattern_display)}", (10, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        y_pos += 20
        cv2.putText(panel, f"Tolerance: {self.tolerance}", (10, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        # Interactive Controls
        y_pos += 35
        cv2.putText(panel, "CONTROLS:", (10, y_pos), font, 0.5, (0, 255, 255), 1)

        y_pos += 22
        cv2.putText(panel, "Arrow Keys: Move start position", (10, y_pos),
                   font, 0.4, (255, 255, 255), 1)

        y_pos += 18
        cv2.putText(panel, "1-4: Select pattern index | +/-: Adjust selected value", (10, y_pos),
                   font, 0.4, (255, 255, 255), 1)

        y_pos += 18
        cv2.putText(panel, "T/G: Increase/Decrease tolerance", (10, y_pos),
                   font, 0.4, (255, 255, 255), 1)

        y_pos += 18
        cv2.putText(panel, "TAB: Switch Health/Shield | P: Print config to console", (10, y_pos),
                   font, 0.4, (255, 255, 255), 1)

        y_pos += 18
        cv2.putText(panel, "S: Save screenshot | Q/ESC: Exit", (10, y_pos),
                   font, 0.4, (255, 255, 255), 1)

        # Legend
        y_pos += 30
        cv2.circle(panel, (15, y_pos - 3), 3, (0, 255, 0), -1)
        cv2.putText(panel, "Match", (30, y_pos), font, 0.4, (255, 255, 255), 1)

        cv2.circle(panel, (100, y_pos - 3), 1, (0, 0, 255), -1)
        cv2.putText(panel, "Health", (115, y_pos), font, 0.4, (255, 255, 255), 1)

        cv2.circle(panel, (190, y_pos - 3), 1, (255, 0, 0), -1)
        cv2.putText(panel, "Shield", (205, y_pos), font, 0.4, (255, 255, 255), 1)

        # Combine visualization and panel
        combined = np.vstack([vis, panel])

        return combined

    def run(self):
        """Run the health/shield debugger tool."""
        print("\n" + "=" * 60)
        print("FA11y INTERACTIVE Health/Shield Debugger")
        print("=" * 60)
        print("\nThis tool lets you adjust detection parameters in real-time.")
        print("\nControls:")
        print("  Arrow Keys - Move start position")
        print("  1-4        - Select pattern index to edit")
        print("  +/-        - Increase/decrease selected pattern value")
        print("  T/G        - Increase/decrease tolerance")
        print("  TAB        - Switch between Health/Shield editing")
        print("  P          - Print current config to console")
        print("  S          - Save screenshot")
        print("  Q/ESC      - Exit")
        print("=" * 60 + "\n")

        self.running = True

        # Print initial config
        self.print_current_config()

        # Create window
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, 1280, 900)

        try:
            while self.running:
                # Capture screenshot
                screenshot_bgr = screenshot_manager.capture_full_screen()

                if screenshot_bgr is None:
                    print("[Dev Mode] Warning: Failed to capture screenshot")
                    continue

                # Convert to RGB for processing (same as FA11y does)
                screenshot_rgb = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2RGB)

                # Collect pixel data
                pixels_data = []

                # Check health bar
                detected_health = self.check_and_visualize_bar(
                    screenshot_rgb, self.health_start_x, self.health_y,
                    self.health_decreases, self.health_color, 'Health', pixels_data
                )

                # Check shield bar
                detected_shield = self.check_and_visualize_bar(
                    screenshot_rgb, self.shield_start_x, self.shield_y,
                    self.shield_decreases, self.shield_color, 'Shield', pixels_data
                )

                # Draw visualization
                visualization = self.draw_visualization(
                    screenshot_bgr, pixels_data, detected_health, detected_shield
                )

                # Display
                cv2.imshow(self.window_name, visualization)

                # Check for key press
                key = cv2.waitKey(1) & 0xFF

                if key == ord('q') or key == 27:  # 'q' or ESC
                    break
                elif key == ord('s'):  # Save screenshot
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"health_shield_debug_{timestamp}.png"
                    cv2.imwrite(filename, visualization)
                    print(f"[Dev Mode] Screenshot saved: {filename}")
                elif key == ord('p'):  # Print config
                    self.print_current_config()
                elif key == 9:  # TAB - switch between health/shield
                    self.editing_health = not self.editing_health
                    mode = "HEALTH" if self.editing_health else "SHIELD"
                    print(f"[Dev Mode] Now editing: {mode}")

                # Arrow keys - move start position
                elif key == 82:  # Up arrow
                    if self.editing_health:
                        self.health_y -= 1
                    else:
                        self.shield_y -= 1
                elif key == 84:  # Down arrow
                    if self.editing_health:
                        self.health_y += 1
                    else:
                        self.shield_y += 1
                elif key == 81:  # Left arrow
                    if self.editing_health:
                        self.health_start_x -= 1
                    else:
                        self.shield_start_x -= 1
                elif key == 83:  # Right arrow
                    if self.editing_health:
                        self.health_start_x += 1
                    else:
                        self.shield_start_x += 1

                # Pattern index selection (1-4 keys)
                elif key in [ord('1'), ord('2'), ord('3'), ord('4')]:
                    self.selected_pattern_index = int(chr(key)) - 1
                    current_decreases = self.health_decreases if self.editing_health else self.shield_decreases
                    if self.selected_pattern_index < len(current_decreases):
                        print(f"[Dev Mode] Selected pattern index: {self.selected_pattern_index}")

                # Adjust selected pattern value
                elif key == ord('+') or key == ord('='):  # + key
                    if self.editing_health:
                        if self.selected_pattern_index < len(self.health_decreases):
                            self.health_decreases[self.selected_pattern_index] += 1
                            print(f"[Dev Mode] Health pattern: {self.health_decreases}")
                    else:
                        if self.selected_pattern_index < len(self.shield_decreases):
                            self.shield_decreases[self.selected_pattern_index] += 1
                            print(f"[Dev Mode] Shield pattern: {self.shield_decreases}")
                elif key == ord('-') or key == ord('_'):  # - key
                    if self.editing_health:
                        if self.selected_pattern_index < len(self.health_decreases):
                            self.health_decreases[self.selected_pattern_index] = max(1, self.health_decreases[self.selected_pattern_index] - 1)
                            print(f"[Dev Mode] Health pattern: {self.health_decreases}")
                    else:
                        if self.selected_pattern_index < len(self.shield_decreases):
                            self.shield_decreases[self.selected_pattern_index] = max(1, self.shield_decreases[self.selected_pattern_index] - 1)
                            print(f"[Dev Mode] Shield pattern: {self.shield_decreases}")

                # Tolerance adjustment
                elif key == ord('t'):  # Increase tolerance
                    self.tolerance += 1
                    print(f"[Dev Mode] Tolerance: {self.tolerance}")
                elif key == ord('g'):  # Decrease tolerance
                    self.tolerance = max(1, self.tolerance - 1)
                    print(f"[Dev Mode] Tolerance: {self.tolerance}")

        except KeyboardInterrupt:
            print("\n[Dev Mode] Interrupted by user")

        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources and close windows."""
        print(f"\n[Dev Mode] Shutting down Health/Shield Debugger...")
        self.running = False
        cv2.destroyAllWindows()
        cv2.waitKey(1)
        print("[Dev Mode] Health/Shield Debugger closed.")

def main():
    tool = HealthShieldDebugger()
    try:
        tool.run()
    except Exception as e:
        print(f"[HealthShieldDebugger] fatal: {e}")
        raise


if __name__ == "__main__":
    main()
