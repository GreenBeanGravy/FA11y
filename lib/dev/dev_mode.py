"""
FA11y Developer Mode Module

This module provides developer tools and utilities for FA11y development.
Currently includes:
- Pixel Inspector: Visual tool for examining screenshot pixels with zoom and color info
- Health/Shield Debugger: Visualizes health and shield bar detection with pixel-by-pixel analysis
"""

import cv2
import numpy as np
import sys
import os
from datetime import datetime
from typing import Optional, Tuple, List, Dict

# Add parent directory to path to import FA11y modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from lib.managers.screenshot_manager import screenshot_manager


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
        self.tolerance = 70
        self.health_decreases = [4, 4, 3, 3]
        self.shield_decreases = [4, 4, 3, 3]
        self.health_start_x = 408
        self.health_y = 1000
        self.shield_start_x = 408
        self.shield_y = 970

        self.window_name = "FA11y Health/Shield Debugger"
        self.running = False

        print(f"[Dev Mode] Health/Shield Debugger initialized")

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
        vis = screenshot_bgr.copy()

        # Draw all checked pixels
        for data in pixels_data:
            x, y = data['x'], data['y']
            within_tol = data['within_tolerance']
            name = data['name']

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

        # Draw starting positions with larger markers
        cv2.circle(vis, (self.health_start_x, self.health_y), 7, (0, 255, 255), 2)  # Yellow
        cv2.putText(vis, "Health Start", (self.health_start_x + 10, self.health_y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        cv2.circle(vis, (self.shield_start_x, self.shield_y), 7, (0, 255, 255), 2)  # Yellow
        cv2.putText(vis, "Shield Start", (self.shield_start_x + 10, self.shield_y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        # Create info panel
        panel_height = 300
        panel_width = vis.shape[1]
        panel = np.zeros((panel_height, panel_width, 3), dtype=np.uint8)

        # Display detected values
        font = cv2.FONT_HERSHEY_SIMPLEX
        y_pos = 30

        cv2.putText(panel, "HEALTH & SHIELD DEBUGGER", (10, y_pos),
                   font, 0.8, (0, 255, 255), 2)

        y_pos += 40
        health_text = f"Health: {detected_health if detected_health else 'NOT DETECTED'}"
        health_color = (0, 255, 0) if detected_health else (0, 0, 255)
        cv2.putText(panel, health_text, (10, y_pos), font, 0.7, health_color, 2)

        y_pos += 35
        shield_text = f"Shield: {detected_shield if detected_shield else 'NOT DETECTED'}"
        shield_color = (0, 255, 0) if detected_shield else (0, 0, 255)
        cv2.putText(panel, shield_text, (10, y_pos), font, 0.7, shield_color, 2)

        # Display target colors
        y_pos += 50
        cv2.putText(panel, "Target Colors:", (10, y_pos), font, 0.6, (255, 255, 255), 1)

        y_pos += 30
        cv2.putText(panel, f"Health RGB: {self.health_color}", (10, y_pos),
                   font, 0.5, (255, 255, 255), 1)
        # Draw color swatch for health
        cv2.rectangle(panel, (250, y_pos - 15), (280, y_pos + 5),
                     (self.health_color[2], self.health_color[1], self.health_color[0]), -1)

        y_pos += 25
        cv2.putText(panel, f"Shield RGB: {self.shield_color}", (10, y_pos),
                   font, 0.5, (255, 255, 255), 1)
        # Draw color swatch for shield
        cv2.rectangle(panel, (250, y_pos - 15), (280, y_pos + 5),
                     (self.shield_color[2], self.shield_color[1], self.shield_color[0]), -1)

        y_pos += 25
        cv2.putText(panel, f"Tolerance: +/- {self.tolerance}", (10, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        # Legend
        y_pos += 40
        cv2.putText(panel, "Legend:", (10, y_pos), font, 0.6, (255, 255, 255), 1)

        y_pos += 25
        cv2.circle(panel, (20, y_pos - 5), 3, (0, 255, 0), -1)
        cv2.putText(panel, "= Pixel within tolerance (MATCH)", (35, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        y_pos += 20
        cv2.circle(panel, (20, y_pos - 5), 1, (0, 0, 255), -1)
        cv2.putText(panel, "= Health pixel checked (no match)", (35, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        y_pos += 20
        cv2.circle(panel, (20, y_pos - 5), 1, (255, 0, 0), -1)
        cv2.putText(panel, "= Shield pixel checked (no match)", (35, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        y_pos += 20
        cv2.circle(panel, (20, y_pos - 5), 7, (0, 255, 255), 2)
        cv2.putText(panel, "= Starting position", (35, y_pos),
                   font, 0.5, (255, 255, 255), 1)

        # Controls
        y_pos = panel_height - 30
        cv2.putText(panel, "Press 'q' or ESC to exit | Press 's' to save screenshot",
                   (10, y_pos), font, 0.5, (200, 200, 200), 1)

        # Combine visualization and panel
        combined = np.vstack([vis, panel])

        return combined

    def run(self):
        """Run the health/shield debugger tool."""
        print("\n" + "=" * 60)
        print("FA11y Health/Shield Debugger - Developer Mode")
        print("=" * 60)
        print("\nThis tool visualizes the health and shield bar detection process.")
        print("\nControls:")
        print("  - Press 'q' or ESC to exit")
        print("  - Press 's' to save a screenshot")
        print("  - Press SPACE to refresh")
        print("=" * 60 + "\n")

        self.running = True

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
                elif key == ord(' '):  # Space to refresh
                    print("[Dev Mode] Refreshing...")

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
