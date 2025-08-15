"""
Minimap-based storm detection and spatial audio system (RGB version, uses utilities.process_minimap)
Enhanced: Always finds closest true edge of the storm (not the minimap border), works both inside and outside. Performance improved.
"""

import threading
import time
import os
import numpy as np
import cv2
from typing import Optional, Tuple
from accessible_output2.outputs.auto import Auto
from lib.utils.utilities import read_config, get_config_boolean, get_config_float, calculate_distance, process_minimap, MINIMAP_REGION
from lib.monitors.background_checks import monitor
from lib.vision.player_position import find_player_position, find_minimap_icon_direction
from lib.audio.spatial_audio import SpatialAudio

class StormAudioThread:
    """Manages audio for storm with configurable ping intervals"""
    def __init__(self, audio_instance: SpatialAudio, ping_interval: float, volume: float):
        self.audio_instance = audio_instance
        self.ping_interval = ping_interval
        self.volume = volume
        self.stop_event = threading.Event()
        self.thread = None
        self.current_position = None
        self.current_distance = None
        self.position_lock = threading.Lock()

    def start(self, position: Tuple[int, int], distance: float):
        """Start the audio thread"""
        with self.position_lock:
            self.current_position = position
            self.current_distance = distance

        if not self.thread or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._audio_loop, daemon=True)
            self.thread.start()

    def update_position(self, position: Tuple[int, int], distance: float):
        """Update the storm's position and distance"""
        with self.position_lock:
            self.current_position = position
            self.current_distance = distance

    def stop(self):
        """Stop the audio thread"""
        self.stop_event.set()
        if self.audio_instance:
            try:
                self.audio_instance.stop()
            except Exception:
                pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def _audio_loop(self):
        """Main audio loop that plays pings at configured intervals"""
        while not self.stop_event.is_set():
            try:
                with self.position_lock:
                    position = self.current_position
                    distance = self.current_distance

                if position and distance is not None:
                    _, player_angle = find_minimap_icon_direction()
                    if player_angle is not None:
                        player_pos = find_player_position()
                        if player_pos:
                            self._play_spatial_audio(player_pos, player_angle, position, distance)

                if self.stop_event.wait(timeout=self.ping_interval):
                    break

            except Exception:
                time.sleep(0.1)

    def _play_spatial_audio(self, player_pos: Tuple[int, int], player_angle: float,
                           storm_pos: Tuple[int, int], distance: float):
        """Play spatial audio for the storm"""
        if not self.audio_instance:
            return
        try:
            # Calculate distance and relative angle using universal calculation
            calc_distance, relative_angle = SpatialAudio.calculate_distance_and_angle(
                player_pos, player_angle, storm_pos
            )

            # Distance-based volume falloff
            max_distance = 300.0
            distance_factor = min(distance / max_distance, 1.0)
            volume_factor = (1.0 - distance_factor) ** 1.5
            final_volume = self.volume * volume_factor
            final_volume = np.clip(final_volume, 0.1, self.volume)

            self.audio_instance.play_audio(
                distance=calc_distance,
                relative_angle=relative_angle,
                volume=final_volume
            )

        except Exception:
            pass

class StormMonitor:
    """Minimap-based storm monitor with spatial audio (RGB version, robust edge logic, performance improved)"""
    def __init__(self):
        self.speaker = Auto()
        self.running = False
        self.stop_event = threading.Event()
        self.detection_thread = None

        # Storm detection parameters for minimap (set as RGB)
        self.storm_color = np.array([166, 40, 140])  # Storm color in RGB
        self.color_tolerance = 40
        self.min_contour_area = 1000  # Adjust as needed for minimap

        # Minimap region (center/scale must match utilities.py)
        self.minimap_scale_factor = 0.5

        # Audio system
        self.storm_audio = None
        self.active_audio_thread = None

        # Timing
        self.detection_interval = 3.0

        self.initialize_audio()

    def initialize_audio(self):
        """Initialize storm audio"""
        storm_sound_path = 'sounds/storm.ogg'
        if os.path.exists(storm_sound_path):
            try:
                self.storm_audio = SpatialAudio(storm_sound_path)
                # Set up volume management
                config = read_config()
                master_volume, storm_volume = SpatialAudio.get_volume_from_config(
                    config, 'StormVolume', 'MasterVolume', 0.5
                )
                self.storm_audio.set_master_volume(master_volume)
                self.storm_audio.set_individual_volume(storm_volume)
            except Exception:
                self.storm_audio = None

    def is_enabled(self) -> bool:
        """Check if storm monitoring is enabled in config"""
        config = read_config()
        return get_config_boolean(config, 'MonitorStorm', True)

    def should_monitor(self) -> bool:
        """Check if monitoring should be active"""
        return self.is_enabled() and not monitor.map_open

    def get_storm_volume(self) -> float:
        """Get storm volume from config"""
        config = read_config()
        return get_config_float(config, 'StormVolume', 0.5)

    def get_storm_ping_interval(self) -> float:
        """Get storm ping interval from config"""
        config = read_config()
        return get_config_float(config, 'StormPingInterval', 1.5)

    def detect_storm_on_minimap(self) -> Optional[Tuple[int, int]]:
        """
        Detect storm on minimap and return closest true storm edge point to player (both inside and out).
        Ignores edge-of-image "contour" points for robustness.
        """
        try:
            screenshot = process_minimap()
            if screenshot is None:
                return None

            lower_bound = np.maximum(0, self.storm_color - self.color_tolerance)
            upper_bound = np.minimum(255, self.storm_color + self.color_tolerance)
            mask = cv2.inRange(screenshot, lower_bound, upper_bound)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                return None

            # Use the largest storm blob as the main storm
            largest_contour = max(contours, key=cv2.contourArea)
            if cv2.contourArea(largest_contour) < self.min_contour_area:
                return None

            # Get player fullmap and minimap coords
            player_fullmap_pos = find_player_position()
            if player_fullmap_pos is None:
                return None

            # Inverse of convert_minimap_to_fullmap_coords: fullmap to minimap (local, not screen)
            minimap_center_x = MINIMAP_REGION['width'] // 2
            minimap_center_y = MINIMAP_REGION['height'] // 2
            # Player is always at center of minimap in standard games
            player_minimap_x, player_minimap_y = minimap_center_x, minimap_center_y

            # Get storm edge points, ignore those on minimap image border
            h, w = mask.shape
            contour_points = largest_contour.reshape(-1, 2)
            edge_mask = (
                (contour_points[:, 0] > 0) & (contour_points[:, 0] < w - 1) &
                (contour_points[:, 1] > 0) & (contour_points[:, 1] < h - 1)
            )
            safe_edge_points = contour_points[edge_mask]
            if safe_edge_points.shape[0] == 0:
                safe_edge_points = contour_points  # fallback if all are at edge

            # Find closest edge point to player
            dists = np.linalg.norm(
                safe_edge_points - np.array([player_minimap_x, player_minimap_y]),
                axis=1
            )
            closest_idx = np.argmin(dists)
            closest_point = safe_edge_points[closest_idx]

            # Convert minimap-local to screen coordinates
            screen_x = int(closest_point[0] + MINIMAP_REGION['left'])
            screen_y = int(closest_point[1] + MINIMAP_REGION['top'])
            return (screen_x, screen_y)
        except Exception:
            return None

    def convert_minimap_to_fullmap_coords(self, minimap_coords: Tuple[int, int],
                                        player_fullmap_pos: Tuple[int, int]) -> Tuple[int, int]:
        """Convert minimap coordinates to full map coordinates"""
        minimap_x, minimap_y = minimap_coords
        player_fullmap_x, player_fullmap_y = player_fullmap_pos
        minimap_center_x = MINIMAP_REGION['left'] + MINIMAP_REGION['width'] // 2
        minimap_center_y = MINIMAP_REGION['top'] + MINIMAP_REGION['height'] // 2
        offset_x = minimap_x - minimap_center_x
        offset_y = minimap_y - minimap_center_y
        fullmap_x = int(player_fullmap_x + (offset_x * self.minimap_scale_factor))
        fullmap_y = int(player_fullmap_y + (offset_y * self.minimap_scale_factor))
        return (fullmap_x, fullmap_y)

    def detection_loop(self):
        """Main detection loop"""
        last_detection_time = 0
        while not self.stop_event.is_set():
            try:
                current_time = time.time()
                if not self.should_monitor():
                    self.cleanup_audio_thread()
                    time.sleep(2.0)
                    continue
                if current_time - last_detection_time >= self.detection_interval:
                    storm_minimap_coords = self.detect_storm_on_minimap()
                    if storm_minimap_coords:
                        player_fullmap_pos = find_player_position()
                        if player_fullmap_pos:
                            storm_fullmap_coords = self.convert_minimap_to_fullmap_coords(
                                storm_minimap_coords, player_fullmap_pos
                            )
                            distance = calculate_distance(player_fullmap_pos, storm_fullmap_coords)
                            volume = self.get_storm_volume()
                            ping_interval = self.get_storm_ping_interval()
                            if self.active_audio_thread:
                                self.active_audio_thread.update_position(storm_fullmap_coords, distance)
                            else:
                                if self.storm_audio:
                                    self.active_audio_thread = StormAudioThread(
                                        self.storm_audio, ping_interval, volume
                                    )
                                    self.active_audio_thread.start(storm_fullmap_coords, distance)
                    else:
                        self.cleanup_audio_thread()
                    last_detection_time = current_time
                time.sleep(1.0)
            except Exception:
                time.sleep(2.0)

    def cleanup_audio_thread(self):
        """Stop and clean up audio thread"""
        if self.active_audio_thread:
            self.active_audio_thread.stop()
            self.active_audio_thread = None

    def get_current_storm_location(self) -> Optional[Tuple[int, int]]:
        """Get current storm location for POI usage"""
        if not self.is_enabled():
            return None
        storm_minimap_coords = self.detect_storm_on_minimap()
        if storm_minimap_coords:
            player_fullmap_pos = find_player_position()
            if player_fullmap_pos:
                return self.convert_minimap_to_fullmap_coords(
                    storm_minimap_coords, player_fullmap_pos
                )
        return None

    def start_monitoring(self):
        """Start storm monitoring"""
        if not self.running:
            self.running = True
            self.stop_event.clear()
            self.detection_thread = threading.Thread(target=self.detection_loop, daemon=True)
            self.detection_thread.start()

    def stop_monitoring(self):
        """Stop storm monitoring"""
        self.stop_event.set()
        self.running = False
        self.cleanup_audio_thread()
        if self.detection_thread:
            self.detection_thread.join(timeout=3.0)
        if self.storm_audio:
            try:
                self.storm_audio.stop()
            except Exception:
                pass

storm_monitor = StormMonitor()