import cv2
import numpy as np
import pyautogui
import time
import threading
from lib.spatial_audio import SpatialAudio
from lib.player_location import get_angle_and_direction, get_relative_direction
from lib.minimap_direction import find_minimap_icon_direction

# Constants for storm detection
MINIMAP_START = (1610, 10)
MINIMAP_END = (1910, 310)
MINIMAP_CENTER = (1750, 180)

# Storm detection settings
TARGET_COLOR = np.array([165, 29, 146])  # Purple color of the storm
COLOR_TOLERANCE = 70
MIN_CONTOUR_AREA = 500
SCALE_FACTOR = 4  # Upscaling factor for better accuracy

# Audio feedback settings
STORM_SOUND_FILE = 'sounds/storm.ogg'
STORM_WARNING_DISTANCE = 100  # Distance at which to start warning (in pixels)
STORM_CHECK_INTERVAL = 3.0  # Seconds between storm checks
STORM_VOLUME = 0.15  # 15% volume for storm warnings

class StormDetector:
    def __init__(self):
        """Initialize storm detector with spatial audio support."""
        self.spatial_storm = SpatialAudio(STORM_SOUND_FILE)
        self.stop_event = threading.Event()
        self.last_sound_time = 0
        self.monitoring = False

    def capture_minimap(self):
        """Capture the minimap region of the screen.
        
        Returns:
            numpy.ndarray: Screenshot of the minimap area
        """
        region = (
            MINIMAP_START[0],
            MINIMAP_START[1],
            MINIMAP_END[0] - MINIMAP_START[0],
            MINIMAP_END[1] - MINIMAP_START[1]
        )
        return np.array(pyautogui.screenshot(region=region))

    def find_storm_edge(self):
        """Find the closest point on the storm's edge to the player.
        
        Returns:
            tuple: (x, y) coordinates of closest storm point or None if not found
        """
        # Capture and process minimap
        screenshot = self.capture_minimap()
        screenshot_large = cv2.resize(screenshot, None, fx=SCALE_FACTOR, fy=SCALE_FACTOR,
                                   interpolation=cv2.INTER_LINEAR)
        
        # Create mask for storm color
        lower_bound = np.maximum(0, TARGET_COLOR - COLOR_TOLERANCE)
        upper_bound = np.minimum(255, TARGET_COLOR + COLOR_TOLERANCE)
        mask = cv2.inRange(screenshot_large, lower_bound, upper_bound)
        
        # Find contours of the storm
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
            
        # Find the closest point to minimap center
        center = np.array([screenshot_large.shape[1] // 2, screenshot_large.shape[0] // 2])
        closest_point = None
        min_distance = float('inf')
        
        for contour in contours:
            if cv2.contourArea(contour) < MIN_CONTOUR_AREA:
                continue
                
            contour_points = contour.reshape(-1, 2)
            distances = np.linalg.norm(contour_points - center, axis=1)
            idx = np.argmin(distances)
            
            if distances[idx] < min_distance:
                min_distance = distances[idx]
                closest_point = contour_points[idx]
        
        if closest_point is not None:
            # Convert back to original scale and add offset
            x = (closest_point[0] // SCALE_FACTOR) + MINIMAP_START[0]
            y = (closest_point[1] // SCALE_FACTOR) + MINIMAP_START[1]
            return (int(x), int(y))
        
        return None

    def play_storm_warning(self, storm_point):
        """Play spatial audio warning for nearby storm edge.
        
        Args:
            storm_point (tuple): (x, y) coordinates of closest storm point
        """
        current_time = time.time()
        if current_time - self.last_sound_time < STORM_CHECK_INTERVAL:
            return

        # Calculate direction to storm point
        direction, player_angle = find_minimap_icon_direction()
        if direction is None or player_angle is None:
            return

        # Calculate relative angle to storm
        storm_vector = np.array(storm_point) - np.array(MINIMAP_CENTER)
        storm_angle, _ = get_angle_and_direction(storm_vector)
        relative_direction = get_relative_direction(player_angle, storm_angle)

        # Calculate audio parameters based on direction
        angle_diff = (storm_angle - player_angle + 180) % 360 - 180
        pan = np.clip(angle_diff / 90, -1, 1)
        left_weight = np.clip((1 - pan) / 2, 0, 1)
        right_weight = np.clip((1 + pan) / 2, 0, 1)

        # Play spatial audio
        self.spatial_storm.play_audio(
            left_weight=left_weight,
            right_weight=right_weight,
            volume=STORM_VOLUME
        )
        self.last_sound_time = current_time

    def monitor_storm(self):
        """Continuously monitor storm distance and provide audio feedback."""
        while not self.stop_event.is_set():
            storm_point = self.find_storm_edge()
            if storm_point:
                distance = np.linalg.norm(np.array(storm_point) - np.array(MINIMAP_CENTER))
                if distance < STORM_WARNING_DISTANCE:
                    self.play_storm_warning(storm_point)
            time.sleep(0.1)

    def start_monitoring(self):
        """Start storm monitoring in a separate thread."""
        if not self.monitoring:
            self.monitoring = True
            self.stop_event.clear()
            threading.Thread(target=self.monitor_storm, daemon=True).start()

    def stop_monitoring(self):
        """Stop storm monitoring."""
        self.stop_event.set()
        self.monitoring = False

# Global instance for the storm detector
storm_detector = None

def get_storm_detector():
    """Get or create the global storm detector instance.
    
    Returns:
        StormDetector: The global storm detector instance
    """
    global storm_detector
    if storm_detector is None:
        storm_detector = StormDetector()
    return storm_detector