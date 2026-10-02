"""
Minimap-based storm detection using PPI-aligned reference comparison.
Uses PPI's feature matching to determine exactly what area of the map
is visible on the minimap, crops and resizes the reference map to match,
then compares pixel-by-pixel to detect the storm overlay.
"""

import threading
import time
import os
import numpy as np
import cv2
from typing import Optional, Tuple
from accessible_output2.outputs.auto import Auto
from lib.utilities.utilities import read_config, get_config_boolean, get_config_float, calculate_distance, get_minimap_region, on_config_change
from lib.managers.screenshot_manager import capture_region

from lib.monitors.background_monitor import monitor
from lib.detection import ppi as ppi_module
from lib.detection.ppi import PPI_CAPTURE_REGION, PPI_CAPTURE_REGION_LEGACY
from lib.utilities.spatial_audio import SpatialAudio

def _get_position_tracker():
    from lib.detection.player_position import position_tracker
    return position_tracker

def _get_find_minimap_icon_direction():
    from lib.detection.player_position import find_minimap_icon_direction
    return find_minimap_icon_direction


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
        self.current_player_position = None
        self.position_lock = threading.Lock()

    def start(self, position: Tuple[int, int], distance: float, player_position=None):
        with self.position_lock:
            self.current_position = position
            self.current_distance = distance
            self.current_player_position = player_position
        if not self.thread or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._audio_loop, daemon=True)
            self.thread.start()

    def update_position(self, position: Tuple[int, int], distance: float, player_position=None):
        with self.position_lock:
            self.current_position = position
            self.current_distance = distance
            self.current_player_position = player_position

    def stop(self):
        self.stop_event.set()
        if self.audio_instance:
            try:
                self.audio_instance.stop()
            except Exception:
                pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def _audio_loop(self):
        while not self.stop_event.is_set():
            try:
                with self.position_lock:
                    position = self.current_position
                    distance = self.current_distance
                    player_pos = self.current_player_position
                if position and distance is not None:
                    _, player_angle = _get_find_minimap_icon_direction()()
                    if player_angle is not None:
                        if player_pos:
                            self._play_spatial_audio(player_pos, player_angle, position, distance)
                if self.stop_event.wait(timeout=self.ping_interval):
                    break
            except Exception:
                time.sleep(0.1)

    def _play_spatial_audio(self, player_pos, player_angle, storm_pos, distance):
        if not self.audio_instance:
            return
        try:
            distance, relative_angle = SpatialAudio.calculate_distance_and_angle(
                player_pos, player_angle, storm_pos
            )
            max_distance = 300.0
            distance_factor = min(distance / max_distance, 1.0)
            volume_factor = (1.0 - distance_factor) ** 1.5
            final_volume = self.volume * volume_factor
            final_volume = np.clip(final_volume, 0.1, self.volume)
            self.audio_instance.play_audio(distance=distance, relative_angle=relative_angle, volume=final_volume)
        except Exception:
            pass


from lib.monitors.base import BaseMonitor


class StormMonitor(BaseMonitor):
    """Minimap-based storm monitor using PPI-aligned reference comparison"""
    def __init__(self):
        super().__init__()
        self.speaker = Auto()

        self.min_contour_area = 3000
        self.minimap_scale_factor = 0.5

        self.storm_audio = None
        self.active_audio_thread = None
        self.detection_interval = 0.5

        # Color reference map (cached per map)
        self._color_ref = None
        self._color_ref_name = None
        self._capture_to_map = None
        self._detected_player_pos = None

        # Cached config values
        self._cached_enabled = True
        self._cached_storm_volume = 0.5
        self._cached_ping_interval = 1.5
        self._cached_current_map = 'main'

        self.initialize_audio()
        self._init_cached_config()
        on_config_change(self._on_config_change)

    def _init_cached_config(self):
        try:
            config = read_config()
            self._cached_current_map = config.get('POI', 'current_map', fallback='main')
        except Exception:
            pass

    def _on_config_change(self, config):
        self._cached_enabled = get_config_boolean(config, 'MonitorStorm', True)
        self._cached_storm_volume = get_config_float(config, 'StormVolume', 0.5)
        self._cached_ping_interval = get_config_float(config, 'StormPingInterval', 1.5)
        new_map = config.get('POI', 'current_map', fallback='main')
        if new_map != self._cached_current_map:
            self._cached_current_map = new_map
            self._color_ref = None
            self._color_ref_name = None
        if self.storm_audio:
            master_volume, storm_volume = SpatialAudio.get_volume_from_config(
                config, 'StormVolume', 'MasterVolume', 0.5
            )
            self.storm_audio.set_master_volume(master_volume)
            self.storm_audio.set_individual_volume(storm_volume)

    def initialize_audio(self):
        storm_sound_path = 'assets/sounds/storm.ogg'
        if os.path.exists(storm_sound_path):
            try:
                self.storm_audio = SpatialAudio(storm_sound_path)
                config = read_config()
                master_volume, storm_volume = SpatialAudio.get_volume_from_config(
                    config, 'StormVolume', 'MasterVolume', 0.5
                )
                self.storm_audio.set_master_volume(master_volume)
                self.storm_audio.set_individual_volume(storm_volume)
            except Exception:
                self.storm_audio = None

    def is_enabled(self) -> bool:
        return self._cached_enabled

    def should_monitor(self) -> bool:
        return self.is_enabled() and not monitor.map_open

    def get_storm_volume(self) -> float:
        return self._cached_storm_volume

    def get_storm_ping_interval(self) -> float:
        return self._cached_ping_interval

    # ── Reference map ───────────────────────────────────────────────

    def _get_color_ref(self) -> Optional[np.ndarray]:
        """Load and cache the reference map image in RGB."""
        name = self._cached_current_map
        if self._color_ref is not None and self._color_ref_name == name:
            return self._color_ref
        path = f"data/maps/{name}.png"
        if not os.path.exists(path):
            return None
        bgr = cv2.imread(path, cv2.IMREAD_COLOR)
        if bgr is None:
            return None
        self._color_ref = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        self._color_ref_name = name
        return self._color_ref

    def _get_ppi_capture_region(self) -> dict:
        """Get the PPI capture region for the current map."""
        if self._cached_current_map == "o_g":
            return PPI_CAPTURE_REGION_LEGACY
        return PPI_CAPTURE_REGION

    # ── Alignment via PPI matched region ────────────────────────────

    def _get_ref_aligned(self, screenshot: np.ndarray) -> Optional[np.ndarray]:
        """
        Match this minimap frame and warp the reference using that transform.
        """
        self._capture_to_map = None
        self._detected_player_pos = None
        ref_map = self._get_color_ref()
        if ref_map is None:
            return None

        # Match this frame instead of reusing another capture's old quad.
        if not ppi_module.map_manager.switch_map(self._cached_current_map):
            return None
        matched = ppi_module.find_best_match(cv2.cvtColor(screenshot, cv2.COLOR_RGB2GRAY))
        if matched is None:
            return None
        cap_h, cap_w = screenshot.shape[:2]
        corners = np.float32([[0, 0], [0, cap_h - 1],
                              [cap_w - 1, cap_h - 1], [cap_w - 1, 0]])
        transform = cv2.getPerspectiveTransform(corners, matched.reshape(4, 2).astype(np.float32))
        if not np.all(np.isfinite(transform)):
            return None
        self._capture_to_map = transform
        map_h, map_w = ref_map.shape[:2]
        roi_start, roi_end = ppi_module.get_roi_coordinates(self._cached_current_map)
        self._map_to_screen_scale = ((roi_end[0] - roi_start[0]) / map_w,
                                     (roi_end[1] - roi_start[1]) / map_h)
        self._map_screen_origin = roi_start
        center = np.float32([[[cap_w // 2, cap_h // 2]]])
        mapped_center = cv2.perspectiveTransform(center, transform)[0, 0]
        self._detected_player_pos = (
            float(mapped_center[0] * self._map_to_screen_scale[0] + roi_start[0]),
            float(mapped_center[1] * self._map_to_screen_scale[1] + roi_start[1]),
        )
        # Preserve the match's translation, scale, and rotation.
        return cv2.warpPerspective(ref_map, np.linalg.inv(transform), (cap_w, cap_h))

    def detect_storm_mask(self, screenshot: np.ndarray, ref_aligned: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compare live minimap vs aligned reference to detect the storm overlay.
        Returns (storm_mask, purple_shift).
        """
        live = screenshot.astype(np.float32)
        ref = ref_aligned.astype(np.float32)
        diff = live - ref

        r_shift = diff[:, :, 0]
        g_shift = diff[:, :, 1]
        b_shift = diff[:, :, 2]

        # Storm overlay adds purple tint: R and B increase, G relatively less
        purple_shift = ((r_shift + b_shift) * 0.5) - g_shift
        storm_mask = (purple_shift > 50).astype(np.uint8) * 255

        # Morphological cleanup
        kernel_small = np.ones((3, 3), np.uint8)
        storm_mask = cv2.morphologyEx(storm_mask, cv2.MORPH_CLOSE, kernel_small)
        storm_mask = cv2.morphologyEx(storm_mask, cv2.MORPH_OPEN, kernel_small)

        kernel_large = np.ones((15, 15), np.uint8)
        storm_mask = cv2.morphologyEx(storm_mask, cv2.MORPH_CLOSE, kernel_large)

        return storm_mask, purple_shift

    # ── Main detection ──────────────────────────────────────────────

    def detect_storm_on_minimap(self) -> Optional[Tuple[int, int]]:
        """Detect storm using PPI-aligned reference comparison."""
        try:
            # Capture from the SAME region PPI uses
            ppi_region = self._get_ppi_capture_region()
            screenshot = capture_region(ppi_region, 'rgb')
            if screenshot is None:
                return None

            # Get aligned reference
            ref_aligned = self._get_ref_aligned(screenshot)

            mask = None
            purple_shift = None
            storm_contour = None
            closest_point = None
            result = None

            if ref_aligned is not None:
                mask, purple_shift = self.detect_storm_mask(screenshot, ref_aligned)

                # Safe circles are holes inside the storm mask. External-only
                # retrieval loses their boundary when storm surrounds the player.
                contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
                h, w = mask.shape
                candidates = []
                for contour in contours:
                    if cv2.contourArea(contour) < self.min_contour_area:
                        continue
                    points = contour.reshape(-1, 2)
                    interior = (
                        (points[:, 0] > 1) & (points[:, 0] < w - 2) &
                        (points[:, 1] > 1) & (points[:, 1] < h - 2)
                    )
                    if np.any(interior):
                        candidates.append(points[interior])
                # Capture edges are not storm boundaries. An entirely covered
                # minimap provides no visible boundary to guide toward.
                if candidates:
                    safe_pts = np.concatenate(candidates)
                    center = np.array((w // 2, h // 2))
                    dists = np.linalg.norm(safe_pts - center, axis=1)
                    closest_point = safe_pts[np.argmin(dists)]
                    result = (int(closest_point[0] + ppi_region['left']),
                              int(closest_point[1] + ppi_region['top']))

            return result
        except Exception as e:
            print(f"[storm] detect error: {e}")
            return None

    def convert_minimap_to_fullmap_coords(self, minimap_coords: Tuple[int, int],
                                        player_fullmap_pos: Tuple[int, int]) -> Optional[Tuple[float, float]]:
        region = self._get_ppi_capture_region()
        local = np.float32([[[minimap_coords[0] - region['left'],
                             minimap_coords[1] - region['top']]]])
        transform = getattr(self, '_capture_to_map', None)
        if transform is None:
            return None
        mapped = cv2.perspectiveTransform(local, transform)[0, 0]
        scale_x, scale_y = self._map_to_screen_scale
        origin_x, origin_y = self._map_screen_origin
        return (float(mapped[0] * scale_x + origin_x),
                float(mapped[1] * scale_y + origin_y))

    def _monitor_loop(self):
        last_detection_time = 0
        while not self.stop_event.is_set():
            try:
                if self.wizard_paused():
                    self.cleanup_audio_thread()
                    time.sleep(0.5)
                    continue
                current_time = time.time()
                if not self.should_monitor():
                    self.cleanup_audio_thread()
                    time.sleep(2.0)
                    continue
                if current_time - last_detection_time >= self.detection_interval:
                    storm_minimap_coords = self.detect_storm_on_minimap()
                    if storm_minimap_coords:
                        player_fullmap_pos = self._detected_player_pos
                        if player_fullmap_pos:
                            storm_fullmap_coords = self.convert_minimap_to_fullmap_coords(
                                storm_minimap_coords, player_fullmap_pos
                            )
                            distance = calculate_distance(player_fullmap_pos, storm_fullmap_coords)
                            volume = self.get_storm_volume()
                            ping_interval = self.get_storm_ping_interval()
                            if self.active_audio_thread:
                                self.active_audio_thread.update_position(storm_fullmap_coords, distance, player_fullmap_pos)
                            else:
                                if self.storm_audio:
                                    self.active_audio_thread = StormAudioThread(
                                        self.storm_audio, ping_interval, volume
                                    )
                                    self.active_audio_thread.start(storm_fullmap_coords, distance, player_fullmap_pos)
                    else:
                        self.cleanup_audio_thread()
                    last_detection_time = current_time
                time.sleep(0.1)
            except Exception:
                time.sleep(2.0)

    def cleanup_audio_thread(self):
        if self.active_audio_thread:
            self.active_audio_thread.stop()
            self.active_audio_thread = None

    def get_current_storm_location(self) -> Optional[Tuple[int, int]]:
        if not self.is_enabled():
            return None
        storm_minimap_coords = self.detect_storm_on_minimap()
        if storm_minimap_coords:
            player_fullmap_pos = self._detected_player_pos
            if player_fullmap_pos:
                return self.convert_minimap_to_fullmap_coords(
                    storm_minimap_coords, player_fullmap_pos
                )
        return None

    def start_monitoring(self):
        """Kick the position tracker first so the storm loop has live
        player coords available when it fires, then defer the rest of
        the lifecycle to BaseMonitor."""
        if self.running:
            return
        try:
            tracker = _get_position_tracker()
            if not tracker.monitoring:
                tracker.start_monitoring()
        except Exception:
            pass
        super().start_monitoring()

    def stop_monitoring(self):
        """Stop any active audio threads + the spatial audio loop, then
        let BaseMonitor tear down the detection thread."""
        self.cleanup_audio_thread()
        super().stop_monitoring()
        if self.storm_audio:
            try:
                self.storm_audio.stop()
            except Exception:
                pass

storm_monitor = StormMonitor()
