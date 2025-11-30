"""
FA11y Developer Mode Module

This module provides developer tools and utilities for FA11y development.
Currently includes:
- Pixel Inspector: Visual tool for examining screenshot pixels with zoom and color info
- Health/Shield Debugger: Visualizes health and shield bar detection with pixel-by-pixel analysis
- Health Calibrator: Auto-calibration tool that finds pixel positions for health bar detection
- PPI Configurator: Interactive tool for configuring and visualizing minimap position detection
- Direction Configurator: Interactive tool for configuring player direction detection
"""

import cv2
import numpy as np
import sys
import os
from datetime import datetime
from typing import Optional, Tuple, List, Dict
from mss import mss
import glob

# Add parent directory to path to import FA11y modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from lib.managers.screenshot_manager import screenshot_manager
from lib.detection import ppi
from lib.utilities.utilities import read_config


class PixelInspector:
    """
    Developer tool for inspecting screenshot pixels.

    Features:
    - Displays FA11y screenshot in real-time
    - Zoomed view of pixels under mouse cursor
    - Displays exact RGB values that FA11y processes
    - Click to save pixel information to file
    """

    def __init__(self, zoom_factor: int = 10, zoom_box_size: int = 20):
        """
        Initialize the Pixel Inspector.

        Args:
            zoom_factor: How much to zoom the pixel view (default 10x)
            zoom_box_size: Size of the area to zoom (default 20x20 pixels)
        """
        self.zoom_factor = zoom_factor
        self.zoom_box_size = zoom_box_size
        self.clicked_pixels: List[Dict] = []
        self.output_file = os.path.join(os.path.dirname(__file__), '../../pixel_inspector_log.txt')
        self.running = False

        # Window names
        self.main_window = "FA11y Pixel Inspector - Screenshot View"
        self.zoom_window = "FA11y Pixel Inspector - Zoomed View"
        self.info_window = "FA11y Pixel Inspector - Info"

        # Mouse tracking
        self.mouse_x = 0
        self.mouse_y = 0
        self.current_screenshot = None

        print(f"[Dev Mode] Pixel Inspector initialized")
        print(f"[Dev Mode] Output file: {self.output_file}")
        print(f"[Dev Mode] Zoom factor: {self.zoom_factor}x")
        print(f"[Dev Mode] Zoom box size: {self.zoom_box_size}x{self.zoom_box_size} pixels")

    def mouse_callback(self, event, x, y, flags, param):
        """
        Callback for mouse events in the main window.

        Args:
            event: OpenCV mouse event type
            x: Mouse x coordinate
            y: Mouse y coordinate
            flags: Additional flags
            param: User-defined parameter
        """
        self.mouse_x = x
        self.mouse_y = y

        # Handle left click - save pixel information
        if event == cv2.EVENT_LBUTTONDOWN:
            self.save_pixel_info(x, y)

    def get_pixel_color(self, screenshot, x: int, y: int) -> Optional[Tuple[int, int, int]]:
        """
        Get the RGB color of a pixel at the specified coordinates.

        Args:
            screenshot: The screenshot array (in RGB format)
            x: X coordinate
            y: Y coordinate

        Returns:
            Tuple of (R, G, B) values, or None if coordinates are invalid
        """
        if screenshot is None:
            return None

        h, w = screenshot.shape[:2]
        if 0 <= x < w and 0 <= y < h:
            # Screenshot is already in RGB format
            rgb = screenshot[y, x]
            return (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        return None

    def save_pixel_info(self, x: int, y: int):
        """
        Save pixel information to the log file and internal list.

        Args:
            x: X coordinate of the pixel
            y: Y coordinate of the pixel
        """
        if self.current_screenshot is None:
            print(f"[Dev Mode] Warning: No screenshot available")
            return

        color = self.get_pixel_color(self.current_screenshot, x, y)
        if color is None:
            print(f"[Dev Mode] Warning: Invalid coordinates ({x}, {y})")
            return

        r, g, b = color
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        pixel_info = {
            'timestamp': timestamp,
            'x': x,
            'y': y,
            'r': r,
            'g': g,
            'b': b
        }

        self.clicked_pixels.append(pixel_info)

        # Write to file
        try:
            mode = 'a' if os.path.exists(self.output_file) else 'w'
            with open(self.output_file, mode) as f:
                if mode == 'w':
                    f.write("FA11y Pixel Inspector Log\n")
                    f.write("=" * 60 + "\n\n")

                f.write(f"[{timestamp}]\n")
                f.write(f"Coordinates: ({x}, {y})\n")
                f.write(f"RGB: ({r}, {g}, {b})\n")
                f.write(f"Hex: #{r:02X}{g:02X}{b:02X}\n")
                f.write("-" * 60 + "\n\n")

            print(f"[Dev Mode] Saved pixel: ({x}, {y}) = RGB({r}, {g}, {b})")
        except Exception as e:
            print(f"[Dev Mode] Error saving pixel info: {e}")

    def create_zoom_view(self, screenshot, center_x: int, center_y: int) -> np.ndarray:
        """
        Create a zoomed view of the area around the specified coordinates.

        Args:
            screenshot: The source screenshot (RGB format)
            center_x: Center x coordinate
            center_y: Center y coordinate

        Returns:
            Zoomed image as numpy array
        """
        if screenshot is None:
            return np.zeros((200, 200, 3), dtype=np.uint8)

        h, w = screenshot.shape[:2]

        # Calculate the region to extract
        half_box = self.zoom_box_size // 2
        x1 = max(0, center_x - half_box)
        y1 = max(0, center_y - half_box)
        x2 = min(w, center_x + half_box)
        y2 = min(h, center_y + half_box)

        # Extract the region
        region = screenshot[y1:y2, x1:x2].copy()

        if region.size == 0:
            return np.zeros((200, 200, 3), dtype=np.uint8)

        # Resize with nearest neighbor to maintain pixel clarity
        zoomed = cv2.resize(region, None, fx=self.zoom_factor, fy=self.zoom_factor,
                           interpolation=cv2.INTER_NEAREST)

        # Draw grid lines to show individual pixels
        grid_color = (100, 100, 100)  # Gray
        for i in range(0, zoomed.shape[0], self.zoom_factor):
            cv2.line(zoomed, (0, i), (zoomed.shape[1], i), grid_color, 1)
        for i in range(0, zoomed.shape[1], self.zoom_factor):
            cv2.line(zoomed, (i, 0), (i, zoomed.shape[0]), grid_color, 1)

        # Draw crosshair at center
        center_px = (zoomed.shape[1] // 2, zoomed.shape[0] // 2)
        crosshair_color = (0, 255, 0)  # Green
        crosshair_size = self.zoom_factor
        cv2.line(zoomed,
                (center_px[0] - crosshair_size, center_px[1]),
                (center_px[0] + crosshair_size, center_px[1]),
                crosshair_color, 2)
        cv2.line(zoomed,
                (center_px[0], center_px[1] - crosshair_size),
                (center_px[0], center_px[1] + crosshair_size),
                crosshair_color, 2)

        return zoomed

    def create_info_panel(self, x: int, y: int, rgb: Optional[Tuple[int, int, int]]) -> np.ndarray:
        """
        Create an information panel showing pixel details.

        Args:
            x: X coordinate
            y: Y coordinate
            rgb: RGB color tuple

        Returns:
            Info panel image as numpy array
        """
        # Create a black panel
        panel = np.zeros((200, 400, 3), dtype=np.uint8)

        if rgb is None:
            cv2.putText(panel, "No pixel data", (10, 100),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            return panel

        r, g, b = rgb

        # Draw color swatch
        swatch_size = 80
        swatch_x = 10
        swatch_y = 10
        # RGB color swatch
        cv2.rectangle(panel, (swatch_x, swatch_y),
                     (swatch_x + swatch_size, swatch_y + swatch_size),
                     (int(r), int(g), int(b)), -1)
        cv2.rectangle(panel, (swatch_x, swatch_y),
                     (swatch_x + swatch_size, swatch_y + swatch_size),
                     (255, 255, 255), 2)

        # Text information
        text_x = swatch_x + swatch_size + 20
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        color = (255, 255, 255)
        thickness = 1
        line_height = 25

        y_pos = swatch_y + 20
        cv2.putText(panel, f"Position: ({x}, {y})", (text_x, y_pos),
                   font, font_scale, color, thickness)

        y_pos += line_height
        cv2.putText(panel, f"RGB: ({r}, {g}, {b})", (text_x, y_pos),
                   font, font_scale, color, thickness)

        y_pos += line_height
        cv2.putText(panel, f"Hex: #{r:02X}{g:02X}{b:02X}", (text_x, y_pos),
                   font, font_scale, color, thickness)

        # Instructions
        y_pos = 120
        cv2.putText(panel, "Controls:", (10, y_pos),
                   font, font_scale, (0, 255, 255), thickness)

        y_pos += line_height
        cv2.putText(panel, "- Move mouse to inspect pixels", (10, y_pos),
                   font, 0.5, color, thickness)

        y_pos += line_height - 5
        cv2.putText(panel, "- Left click to save pixel info", (10, y_pos),
                   font, 0.5, color, thickness)

        y_pos += line_height - 5
        cv2.putText(panel, "- Yellow highlight = current pixel", (10, y_pos),
                   font, 0.5, color, thickness)

        y_pos += line_height - 5
        cv2.putText(panel, "- Press 'q' or ESC to exit", (10, y_pos),
                   font, 0.5, color, thickness)

        y_pos += line_height - 5
        cv2.putText(panel, f"- Saved pixels: {len(self.clicked_pixels)}", (10, y_pos),
                   font, 0.5, (0, 255, 0), thickness)

        return panel

    def run(self):
        """
        Run the pixel inspector tool.
        """
        print("\n" + "=" * 60)
        print("FA11y Pixel Inspector - Developer Mode")
        print("=" * 60)
        print("\nControls:")
        print("  - Move mouse over the screenshot to inspect pixels")
        print("  - Left click on a pixel to save its information")
        print("  - Press 'q' or ESC to exit")
        print(f"\nPixel data will be saved to: {self.output_file}")
        print("=" * 60 + "\n")

        self.running = True

        # Create resizable windows with 16:9 aspect ratio
        cv2.namedWindow(self.main_window, cv2.WINDOW_NORMAL)
        cv2.namedWindow(self.zoom_window, cv2.WINDOW_NORMAL)
        cv2.namedWindow(self.info_window, cv2.WINDOW_NORMAL)

        # Set window sizes with 16:9 aspect ratio
        cv2.resizeWindow(self.main_window, 1280, 720)  # 16:9 ratio
        cv2.resizeWindow(self.zoom_window, 640, 360)   # 16:9 ratio
        cv2.resizeWindow(self.info_window, 640, 360)   # 16:9 ratio

        # Set mouse callback
        cv2.setMouseCallback(self.main_window, self.mouse_callback)

        # Position windows
        cv2.moveWindow(self.main_window, 50, 50)
        cv2.moveWindow(self.zoom_window, 1350, 50)
        cv2.moveWindow(self.info_window, 1350, 440)

        try:
            while self.running:
                # Capture screenshot using FA11y's screenshot manager
                # This ensures we see EXACTLY what FA11y processes
                screenshot_bgr = screenshot_manager.capture_full_screen()

                if screenshot_bgr is None:
                    print("[Dev Mode] Warning: Failed to capture screenshot")
                    continue

                # Convert BGR to RGB for correct color display and processing
                # This is critical - FA11y processes in RGB, so we must show RGB
                self.current_screenshot = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2RGB)

                # For display, convert back to BGR (OpenCV displays in BGR)
                display_screenshot = screenshot_bgr.copy()

                # Highlight the current pixel in yellow instead of using a crosshair
                if 0 <= self.mouse_x < display_screenshot.shape[1] and \
                   0 <= self.mouse_y < display_screenshot.shape[0]:
                    # Draw a yellow filled rectangle over the current pixel
                    # Make it slightly larger (3x3) so it's visible
                    highlight_color = (0, 255, 255)  # Yellow in BGR
                    highlight_size = 3  # Size of the highlight square

                    # Calculate highlight bounds
                    x1 = max(0, self.mouse_x - highlight_size // 2)
                    y1 = max(0, self.mouse_y - highlight_size // 2)
                    x2 = min(display_screenshot.shape[1], self.mouse_x + highlight_size // 2 + 1)
                    y2 = min(display_screenshot.shape[0], self.mouse_y + highlight_size // 2 + 1)

                    # Create a yellow highlight overlay with transparency
                    overlay = display_screenshot.copy()
                    cv2.rectangle(overlay, (x1, y1), (x2, y2), highlight_color, -1)

                    # Blend the overlay with the original image (50% transparency)
                    cv2.addWeighted(overlay, 0.5, display_screenshot, 0.5, 0, display_screenshot)

                    # Draw box showing zoom area
                    half_box = self.zoom_box_size // 2
                    box_x1 = max(0, self.mouse_x - half_box)
                    box_y1 = max(0, self.mouse_y - half_box)
                    box_x2 = min(display_screenshot.shape[1], self.mouse_x + half_box)
                    box_y2 = min(display_screenshot.shape[0], self.mouse_y + half_box)
                    cv2.rectangle(display_screenshot, (box_x1, box_y1), (box_x2, box_y2),
                                 (255, 0, 0), 2)  # Blue box in BGR

                # Get current pixel color (from RGB screenshot)
                current_color = self.get_pixel_color(self.current_screenshot,
                                                     self.mouse_x, self.mouse_y)

                # Create zoom view (from RGB screenshot, then convert to BGR for display)
                zoom_view_rgb = self.create_zoom_view(self.current_screenshot,
                                                      self.mouse_x, self.mouse_y)
                zoom_view_bgr = cv2.cvtColor(zoom_view_rgb, cv2.COLOR_RGB2BGR)

                # Create info panel (displays RGB values correctly)
                info_panel_rgb = self.create_info_panel(self.mouse_x, self.mouse_y, current_color)
                info_panel_bgr = cv2.cvtColor(info_panel_rgb, cv2.COLOR_RGB2BGR)

                # Display all windows
                cv2.imshow(self.main_window, display_screenshot)
                cv2.imshow(self.zoom_window, zoom_view_bgr)
                cv2.imshow(self.info_window, info_panel_bgr)

                # Check for key press
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:  # 'q' or ESC
                    break

        except KeyboardInterrupt:
            print("\n[Dev Mode] Interrupted by user")

        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources and close windows."""
        print(f"\n[Dev Mode] Shutting down Pixel Inspector...")
        print(f"[Dev Mode] Total pixels saved: {len(self.clicked_pixels)}")

        self.running = False
        cv2.destroyAllWindows()

        # Give a moment for windows to close
        cv2.waitKey(1)

        print(f"[Dev Mode] Pixel data saved to: {self.output_file}")
        print("[Dev Mode] Pixel Inspector closed.")


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
        import pyautogui

        if self.use_minimap:
            region = (self.minimap_x, self.minimap_y, self.minimap_width, self.minimap_height)
        else:
            region = (self.main_x, self.main_y, self.main_width, self.main_height)

        screenshot_rgba = np.array(pyautogui.screenshot(region=region))
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


class DevMode:
    """
    Main developer mode controller.

    Provides access to various developer tools and utilities.
    """

    def __init__(self):
        """Initialize developer mode."""
        self.tools = {
            'pixel_inspector': PixelInspector,
            'health_shield_debugger': HealthShieldDebugger,
            'health_calibrator': HealthCalibrator,
            'ppi_configurator': PPIConfigurator,
            'direction_configurator': DirectionConfigurator,
        }
        print("[Dev Mode] FA11y Developer Mode initialized")

    def list_tools(self):
        """List available developer tools."""
        print("\nAvailable Developer Tools:")
        print("-" * 40)
        for tool_name in self.tools.keys():
            print(f"  - {tool_name}")
        print("-" * 40)

    def run_tool(self, tool_name: str):
        """
        Run a specific developer tool.

        Args:
            tool_name: Name of the tool to run
        """
        if tool_name not in self.tools:
            print(f"[Dev Mode] Error: Unknown tool '{tool_name}'")
            self.list_tools()
            return

        print(f"[Dev Mode] Starting tool: {tool_name}")
        tool_class = self.tools[tool_name]
        tool_instance = tool_class()
        tool_instance.run()


def main():
    """
    Main entry point for developer mode.

    Usage:
        python -m lib.dev.dev_mode pixel_inspector
    """
    import argparse

    parser = argparse.ArgumentParser(description='FA11y Developer Mode')
    parser.add_argument('tool', nargs='?', default='pixel_inspector',
                       help='Tool to run (default: pixel_inspector)')

    args = parser.parse_args()

    dev_mode = DevMode()
    dev_mode.run_tool(args.tool)


if __name__ == "__main__":
    main()
