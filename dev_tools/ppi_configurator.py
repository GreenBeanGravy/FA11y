"""
FA11y PPI Configurator

Standalone dev utility. Ported out of the old ``lib/dev/dev_mode.py`` during
the 18.x refactor so the lib/ runtime no longer carries dev-only code.

Run from the repo root:

    python dev_tools/ppi_configurator.py
"""
from __future__ import annotations

import glob
import os
import sys
from datetime import datetime
from typing import Optional, Tuple, List, Dict

import cv2
import numpy as np
from mss import mss

# Let us import from lib/ without being installed as a package.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
os.chdir(_REPO_ROOT)

from lib.managers.screenshot_manager import screenshot_manager
from lib.detection import ppi

class PPIConfigurator:
    """
    Developer tool for configuring and visualizing PPI (Player Position Interface).

    Features:
    - Live minimap capture visualization
    - SIFT keypoint detection and matching
    - Map position overlay
    - Interactive parameter adjustment
    - GPU/CPU status display
    """

    def __init__(self):
        """Initialize the PPI Configurator."""
        # PPI parameters
        self.lowe_ratio = 0.75
        self.min_matches = 10
        self.show_keypoints = True
        self.show_matches = True

        # Capture region (editable)
        self.region_top = ppi.PPI_CAPTURE_REGION["top"]
        self.region_left = ppi.PPI_CAPTURE_REGION["left"]
        self.region_width = ppi.PPI_CAPTURE_REGION["width"]
        self.region_height = ppi.PPI_CAPTURE_REGION["height"]

        # Available maps
        self.available_maps = self._find_available_maps()
        self.current_map_index = 0

        # SIFT detector
        self.sift = cv2.SIFT_create()
        self.bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)

        # State
        self.running = False
        self.window_name = "FA11y PPI Configurator (Interactive)"

        # Keyboard state tracking (using pynput)
        self.keys_pressed = set()
        self.shift_pressed = False
        self.keyboard_listener = None

        print(f"[Dev Mode] PPI Configurator initialized")
        print(f"[Dev Mode] Found {len(self.available_maps)} maps")
        print(f"[Dev Mode] GPU acceleration: {cv2.ocl.haveOpenCL()}")

    def _find_available_maps(self) -> List[str]:
        """Find all available map files."""
        map_files = glob.glob("maps/*.png")
        # Extract map names without path and extension
        maps = [os.path.splitext(os.path.basename(f))[0] for f in map_files]
        return sorted(maps) if maps else ["main"]

    def capture_minimap(self):
        """Capture the minimap region using current settings."""
        region = {
            "top": self.region_top,
            "left": self.region_left,
            "width": self.region_width,
            "height": self.region_height
        }
        with mss() as sct:
            screenshot_rgba = np.array(sct.grab(region))
        return cv2.cvtColor(screenshot_rgba, cv2.COLOR_BGRA2GRAY)

    def load_map(self, map_name: str):
        """Load a map file."""
        map_file = f"maps/{map_name}.png"
        if not os.path.exists(map_file):
            return None
        return cv2.imread(map_file, cv2.IMREAD_GRAYSCALE)

    def find_matches_with_debug(self, captured_area, map_image):
        """
        Find matches between captured area and map with debug info.

        Returns:
            Tuple of (transformed_pts, good_matches, kp1, kp2, num_matches)
        """
        # Detect keypoints
        kp1, des1 = self.sift.detectAndCompute(captured_area, None)
        kp2, des2 = self.sift.detectAndCompute(map_image, None)

        if des1 is None or des2 is None:
            return None, None, kp1, kp2, 0

        # Match descriptors
        matches = self.bf.knnMatch(des1, des2, k=2)

        # Apply Lowe's ratio test
        good_matches = []
        for match_pair in matches:
            if len(match_pair) == 2:
                m, n = match_pair
                if m.distance < self.lowe_ratio * n.distance:
                    good_matches.append(m)

        num_matches = len(good_matches)

        if num_matches > self.min_matches:
            src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

            M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

            if M is not None and np.all(np.isfinite(M)):
                try:
                    h, w = captured_area.shape
                    pts = np.float32([[0, 0], [0, h-1], [w-1, h-1], [w-1, 0]]).reshape(-1, 1, 2)
                    transformed_pts = cv2.perspectiveTransform(pts, M)

                    if np.all(np.isfinite(transformed_pts)):
                        return transformed_pts, good_matches, kp1, kp2, num_matches
                except cv2.error:
                    pass

        return None, good_matches, kp1, kp2, num_matches

    def draw_visualization(self, captured_area, map_image, transformed_pts, good_matches, kp1, kp2, num_matches):
        """Draw the complete visualization."""
        # Convert to BGR for display
        minimap_bgr = cv2.cvtColor(captured_area, cv2.COLOR_GRAY2BGR)
        map_bgr = cv2.cvtColor(map_image, cv2.COLOR_GRAY2BGR)

        # Draw keypoints on minimap if enabled
        if self.show_keypoints and kp1:
            minimap_bgr = cv2.drawKeypoints(minimap_bgr, kp1, None,
                                           color=(0, 255, 0),
                                           flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)

        # Resize minimap for better visibility
        minimap_display = cv2.resize(minimap_bgr, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)

        # Draw detected region on map
        map_display = map_bgr.copy()
        if transformed_pts is not None:
            # Draw the matched region
            cv2.polylines(map_display, [np.int32(transformed_pts)], True, (0, 255, 0), 3)

            # Calculate and draw center point
            center = np.mean(transformed_pts, axis=0).reshape(-1).astype(int)
            cv2.circle(map_display, tuple(center), 10, (0, 0, 255), -1)
            cv2.circle(map_display, tuple(center), 15, (0, 255, 255), 2)

            # Calculate position in game coordinates
            map_h, map_w = map_image.shape
            x = int(center[0] * (ppi.WIDTH / map_w) + ppi.ROI_START_ORIG[0])
            y = int(center[1] * (ppi.HEIGHT / map_h) + ppi.ROI_START_ORIG[1])

            # Draw position text
            cv2.putText(map_display, f"Position: ({x}, {y})", (center[0] + 20, center[1]),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        # Draw keypoints on map if enabled
        if self.show_keypoints and kp2:
            map_display = cv2.drawKeypoints(map_display, kp2, map_display,
                                          color=(255, 0, 0),
                                          flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)

        # Create info panel - match minimap display width
        panel_height = 250
        panel_width = minimap_display.shape[1]  # Match minimap width exactly
        panel = np.zeros((panel_height, panel_width, 3), dtype=np.uint8)

        font = cv2.FONT_HERSHEY_SIMPLEX
        y_pos = 25

        # Title
        cv2.putText(panel, "PPI CONFIGURATOR", (10, y_pos),
                   font, 0.7, (0, 255, 255), 2)

        y_pos += 30
        current_map = self.available_maps[self.current_map_index] if self.available_maps else "None"
        cv2.putText(panel, f"Map: {current_map}", (10, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        y_pos += 25
        match_color = (0, 255, 0) if transformed_pts is not None else (0, 0, 255)
        cv2.putText(panel, f"Matches: {num_matches} / {self.min_matches} required", (10, y_pos),
                   font, 0.5, match_color, 1)

        y_pos += 25
        cv2.putText(panel, f"Lowe's Ratio: {self.lowe_ratio:.2f}", (10, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        y_pos += 25
        gpu_status = "GPU (OpenCL)" if cv2.ocl.haveOpenCL() else "CPU"
        cv2.putText(panel, f"Acceleration: {gpu_status}", (10, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        y_pos += 25
        kp_text = f"Keypoints: {len(kp1) if kp1 else 0} (minimap) / {len(kp2) if kp2 else 0} (map)"
        cv2.putText(panel, kp_text, (10, y_pos), font, 0.5, (255, 255, 255), 1)

        y_pos += 25
        region_text = f"Region: ({self.region_left}, {self.region_top}) {self.region_width}x{self.region_height}"
        cv2.putText(panel, region_text, (10, y_pos), font, 0.5, (255, 255, 255), 1)

        # Controls
        y_pos += 30
        cv2.putText(panel, "CONTROLS:", (10, y_pos), font, 0.5, (0, 255, 255), 1)

        y_pos += 18
        cv2.putText(panel, "M: Cycle maps | R/F: Lowe ratio | N/B: Min matches", (10, y_pos),
                   font, 0.4, (255, 255, 255), 1)

        y_pos += 18
        cv2.putText(panel, "Arrows: Move region | [/]: Width | ;/': Height", (10, y_pos),
                   font, 0.4, (255, 255, 255), 1)

        y_pos += 18
        cv2.putText(panel, "K: Toggle keypoints | P: Print | S: Save | Q/ESC: Exit", (10, y_pos),
                   font, 0.4, (255, 255, 255), 1)

        # Combine visualizations
        # Stack minimap and panel vertically
        left_panel = np.vstack([minimap_display, panel])

        # Resize map to match height if needed
        target_height = left_panel.shape[0]
        scale = target_height / map_display.shape[0]
        map_resized = cv2.resize(map_display, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)

        # Combine side by side
        combined = np.hstack([left_panel, map_resized])

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
        print("PPI CONFIGURATOR - CURRENT CONFIGURATION:")
        print("="*60)
        current_map = self.available_maps[self.current_map_index] if self.available_maps else "None"
        print(f"Current Map: {current_map}")
        print(f"Capture Region: top={self.region_top}, left={self.region_left}, width={self.region_width}, height={self.region_height}")
        print(f"Lowe's Ratio: {self.lowe_ratio}")
        print(f"Min Matches: {self.min_matches}")
        print(f"Show Keypoints: {self.show_keypoints}")
        print(f"GPU Acceleration: {cv2.ocl.haveOpenCL()}")
        print(f"Available Maps: {', '.join(self.available_maps)}")
        print("="*60 + "\n")

    def run(self):
        """Run the PPI configurator tool."""
        print("\n" + "=" * 60)
        print("FA11y PPI Configurator")
        print("=" * 60)
        print("\nControls:")
        print("  M         - Cycle through available maps")
        print("  R/F       - Increase/decrease Lowe's ratio")
        print("  N/B       - Increase/decrease min matches")
        print("  K         - Toggle keypoint visualization")
        print("  Arrow Keys- Move capture region (hold Shift for 1px steps)")
        print("  [/]       - Decrease/increase region width")
        print("  ;/'       - Decrease/increase region height")
        print("  P         - Print current config to console")
        print("  S         - Save screenshot")
        print("  Q/ESC     - Exit")
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
        cv2.resizeWindow(self.window_name, 1400, 700)

        # Track last processed keys to avoid repeats
        last_keys = set()

        try:
            while self.running:
                # Capture minimap
                captured_area = self.capture_minimap()

                # Load current map
                current_map = self.available_maps[self.current_map_index] if self.available_maps else None
                if current_map:
                    map_image = self.load_map(current_map)

                    if map_image is not None:
                        # Find matches
                        transformed_pts, good_matches, kp1, kp2, num_matches = \
                            self.find_matches_with_debug(captured_area, map_image)

                        # Draw visualization
                        visualization = self.draw_visualization(
                            captured_area, map_image, transformed_pts,
                            good_matches, kp1, kp2, num_matches
                        )

                        cv2.imshow(self.window_name, visualization)
                    else:
                        print(f"[Dev Mode] Error: Could not load map {current_map}")

                # Keep window responsive
                cv2.waitKey(1)

                # Handle keyboard input using pynput state
                current_keys = self.keys_pressed.copy()

                # Process newly pressed keys (avoid repeats)
                new_keys = current_keys - last_keys

                # Determine step size based on Shift modifier
                step_size = 1 if self.shift_pressed else 10

                # Character keys (one-time actions)
                if 'q' in new_keys or keyboard.Key.esc in current_keys:
                    break
                elif 'm' in new_keys:
                    self.current_map_index = (self.current_map_index + 1) % len(self.available_maps)
                    print(f"[Dev Mode] Switched to map: {self.available_maps[self.current_map_index]}")
                elif 'r' in new_keys:
                    self.lowe_ratio = min(0.99, self.lowe_ratio + 0.05)
                    print(f"[Dev Mode] Lowe's ratio: {self.lowe_ratio:.2f}")
                elif 'f' in new_keys:
                    self.lowe_ratio = max(0.50, self.lowe_ratio - 0.05)
                    print(f"[Dev Mode] Lowe's ratio: {self.lowe_ratio:.2f}")
                elif 'n' in new_keys:
                    self.min_matches += 1
                    print(f"[Dev Mode] Min matches: {self.min_matches}")
                elif 'b' in new_keys:
                    self.min_matches = max(1, self.min_matches - 1)
                    print(f"[Dev Mode] Min matches: {self.min_matches}")
                elif 'k' in new_keys:
                    self.show_keypoints = not self.show_keypoints
                    print(f"[Dev Mode] Keypoints: {'ON' if self.show_keypoints else 'OFF'}")
                elif 'p' in new_keys:
                    self.print_current_config()
                elif 's' in new_keys:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"ppi_debug_{timestamp}.png"
                    if 'visualization' in locals():
                        cv2.imwrite(filename, visualization)
                        print(f"[Dev Mode] Screenshot saved: {filename}")
                elif '[' in new_keys:
                    self.region_width = max(50, self.region_width - 10)
                    print(f"[Dev Mode] Region size: {self.region_width}x{self.region_height}")
                elif ']' in new_keys:
                    self.region_width += 10
                    print(f"[Dev Mode] Region size: {self.region_width}x{self.region_height}")
                elif ';' in new_keys:
                    self.region_height = max(50, self.region_height - 10)
                    print(f"[Dev Mode] Region size: {self.region_width}x{self.region_height}")
                elif "'" in new_keys:
                    self.region_height += 10
                    print(f"[Dev Mode] Region size: {self.region_width}x{self.region_height}")

                # Arrow keys (allow continuous movement)
                if keyboard.Key.up in current_keys:
                    self.region_top = max(0, self.region_top - step_size)
                    print(f"[Dev Mode] Region moved to ({self.region_left}, {self.region_top})")
                if keyboard.Key.down in current_keys:
                    self.region_top += step_size
                    print(f"[Dev Mode] Region moved to ({self.region_left}, {self.region_top})")
                if keyboard.Key.left in current_keys:
                    self.region_left = max(0, self.region_left - step_size)
                    print(f"[Dev Mode] Region moved to ({self.region_left}, {self.region_top})")
                if keyboard.Key.right in current_keys:
                    self.region_left += step_size
                    print(f"[Dev Mode] Region moved to ({self.region_left}, {self.region_top})")

                last_keys = current_keys

        except KeyboardInterrupt:
            print("\n[Dev Mode] Interrupted by user")

        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        print(f"\n[Dev Mode] Shutting down PPI Configurator...")
        self.running = False

        # Stop keyboard listener
        if self.keyboard_listener:
            self.keyboard_listener.stop()

        cv2.destroyAllWindows()
        cv2.waitKey(1)
        print("[Dev Mode] PPI Configurator closed.")

def main():
    tool = PPIConfigurator()
    try:
        tool.run()
    except Exception as e:
        print(f"[PPIConfigurator] fatal: {e}")
        raise


if __name__ == "__main__":
    main()
