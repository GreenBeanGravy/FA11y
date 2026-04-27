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
        self.position_lock = threading.Lock()

    def start(self, position: Tuple[int, int], distance: float):
        with self.position_lock:
            self.current_position = position
            self.current_distance = distance
        if not self.thread or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._audio_loop, daemon=True)
            self.thread.start()

    def update_position(self, position: Tuple[int, int], distance: float):
        with self.position_lock:
            self.current_position = position
            self.current_distance = distance

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
                if position and distance is not None:
                    _, player_angle = _get_find_minimap_icon_direction()()
                    if player_angle is not None:
                        player_pos = _get_position_tracker().get_cached_position()
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
        storm_sound_path = 'sounds/storm.ogg'
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
        path = f"maps/{name}.png"
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
        if self._cached_current_map == "o g":
            return PPI_CAPTURE_REGION_LEGACY
        return PPI_CAPTURE_REGION

    # ── Alignment via PPI matched region ────────────────────────────

    def _get_ref_aligned(self, screenshot: np.ndarray) -> Optional[np.ndarray]:
        """
        Use PPI's last matched region to crop and resize the reference map
        so it aligns pixel-for-pixel with the live minimap capture.
        """
        ref_map = self._get_color_ref()
        if ref_map is None:
            return None

        matched = ppi_module.last_matched_region
        if matched is None:
            return None

        pts = matched.reshape(4, 2)  # 4 corners on map image

        # Center of matched quad = player position on map image
        center_x, center_y = np.mean(pts, axis=0)

        # Size of quad = how much of the map image the minimap covers
        # pts order: [top-left, bottom-left, bottom-right, top-right]
        quad_w = (np.linalg.norm(pts[3] - pts[0]) + np.linalg.norm(pts[2] - pts[1])) / 2
        quad_h = (np.linalg.norm(pts[1] - pts[0]) + np.linalg.norm(pts[2] - pts[3])) / 2

        if quad_w < 10 or quad_h < 10:
            return None

        map_h, map_w = ref_map.shape[:2]
        cap_h, cap_w = screenshot.shape[:2]

        # Crop reference map centered on player, sized to the matched quad
        hw = int(quad_w / 2)
        hh = int(quad_h / 2)
        cx = int(center_x)
        cy = int(center_y)

        # Clamp + pad for edges
        x1, y1 = cx - hw, cy - hh
        x2, y2 = cx + hw, cy + hh

        pad_left = max(0, -x1)
        pad_top = max(0, -y1)
        pad_right = max(0, x2 - map_w)
        pad_bottom = max(0, y2 - map_h)

        cx1 = max(0, x1)
        cy1 = max(0, y1)
        cx2 = min(map_w, x2)
        cy2 = min(map_h, y2)

        ref_crop = ref_map[cy1:cy2, cx1:cx2]
        if ref_crop.size == 0:
            return None

        if pad_left or pad_top or pad_right or pad_bottom:
            ref_crop = cv2.copyMakeBorder(
                ref_crop, pad_top, pad_bottom, pad_left, pad_right,
                cv2.BORDER_CONSTANT, value=(0, 0, 0)
            )

        # Resize to match the minimap capture dimensions
        return cv2.resize(ref_crop, (cap_w, cap_h), interpolation=cv2.INTER_LINEAR)

    # ── Storm detection ─────────────────────────────────────────────

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

    # ── Debug output ────────────────────────────────────────────────

    def _save_debug_image(self, screenshot: np.ndarray, ref_aligned,
                          purple_shift, mask,
                          contour=None, closest_point=None):
        """TEMPORARY: Save debug image every tick."""
        try:
            h, w = screenshot.shape[:2]
            center = (w // 2, h // 2)
            font = cv2.FONT_HERSHEY_SIMPLEX
            has_ref = ref_aligned is not None

            # Panel 1: Live minimap
            live_bgr = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)

            # Panel 2: Aligned reference (or placeholder)
            if has_ref:
                ref_bgr = cv2.cvtColor(ref_aligned, cv2.COLOR_RGB2BGR)
            else:
                ref_bgr = np.zeros_like(live_bgr)
                cv2.putText(ref_bgr, "Waiting for PPI match...", (10, h // 2), font, 0.4, (100, 100, 100), 1)

            # Panel 3: Difference (amplified)
            if has_ref:
                abs_diff = np.abs(screenshot.astype(np.float32) - ref_aligned.astype(np.float32))
                diff_vis = np.clip(abs_diff * 3, 0, 255).astype(np.uint8)
                diff_bgr = cv2.cvtColor(diff_vis, cv2.COLOR_RGB2BGR)
            else:
                diff_bgr = np.zeros_like(live_bgr)

            # Panel 4: Storm overlay on live
            overlay = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
            if mask is not None and np.any(mask > 0):
                storm_layer = np.zeros_like(overlay)
                storm_layer[mask > 0] = (180, 50, 180)
                overlay = cv2.addWeighted(overlay, 0.6, storm_layer, 0.4, 0)
            if contour is not None:
                cv2.drawContours(overlay, [contour], -1, (0, 255, 0), 2)
            if closest_point is not None:
                cv2.circle(overlay, tuple(closest_point), 5, (0, 0, 255), -1)
                cv2.line(overlay, center, tuple(closest_point), (0, 0, 255), 2)
            cv2.circle(overlay, center, 4, (255, 255, 0), -1)

            # Grid
            top_row = np.hstack([live_bgr, ref_bgr])
            bot_row = np.hstack([diff_bgr, overlay])
            grid = np.vstack([top_row, bot_row])

            labels = ["Live (PPI region)", "Aligned Reference", "Difference (x3)", "Storm Overlay"]
            for i, label in enumerate(labels):
                cv2.putText(grid, label, ((i % 2) * w + 5, (i // 2) * h + 20),
                            font, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

            # Stats bar
            text_bar = np.zeros((60, grid.shape[1], 3), dtype=np.uint8)
            storm_count = int(np.sum(mask > 0)) if mask is not None else 0

            # Scale info from PPI
            matched = ppi_module.last_matched_region
            scale_str = "N/A"
            if matched is not None:
                pts = matched.reshape(4, 2)
                qw = (np.linalg.norm(pts[3] - pts[0]) + np.linalg.norm(pts[2] - pts[1])) / 2
                scale_str = f"{qw / w:.2f}"

            cv2.putText(text_bar,
                        f"Storm: {storm_count}px  Scale: {scale_str}  Map: {self._cached_current_map}",
                        (5, 18), font, 0.4, (200, 200, 200), 1, cv2.LINE_AA)

            if purple_shift is not None and storm_count > 0:
                sv = purple_shift[mask > 0]
                cv2.putText(text_bar,
                            f"Purple shift (storm): mean={np.mean(sv):.1f} min={np.min(sv):.1f} max={np.max(sv):.1f}",
                            (5, 38), font, 0.35, (180, 180, 255), 1, cv2.LINE_AA)
            elif purple_shift is not None:
                cv2.putText(text_bar,
                            f"Purple shift (all): mean={np.mean(purple_shift):.1f} min={np.min(purple_shift):.1f} max={np.max(purple_shift):.1f}",
                            (5, 38), font, 0.35, (200, 200, 200), 1, cv2.LINE_AA)

            final = np.vstack([grid, text_bar])
            debug_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'storm_debug.png')
            cv2.imwrite(os.path.abspath(debug_path), final)
        except Exception as e:
            print(f"[storm debug] Failed to save debug image: {e}")

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

                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    storm_contour = max(contours, key=cv2.contourArea)
                    if cv2.contourArea(storm_contour) >= self.min_contour_area:
                        h, w = mask.shape
                        mm_cx, mm_cy = w // 2, h // 2
                        contour_points = storm_contour.reshape(-1, 2)
                        edge_mask = (
                            (contour_points[:, 0] > 1) & (contour_points[:, 0] < w - 2) &
                            (contour_points[:, 1] > 1) & (contour_points[:, 1] < h - 2)
                        )
                        safe_pts = contour_points[edge_mask]
                        if len(safe_pts) == 0:
                            safe_pts = contour_points
                        if len(safe_pts) > 0:
                            center = np.array((mm_cx, mm_cy))
                            dists = np.linalg.norm(safe_pts - center, axis=1)
                            closest_point = safe_pts[np.argmin(dists)]
                            result = (int(closest_point[0] + ppi_region['left']),
                                      int(closest_point[1] + ppi_region['top']))
                    else:
                        storm_contour = None

            # TEMPORARY: Always save debug
            self._save_debug_image(screenshot, ref_aligned, purple_shift, mask,
                                   storm_contour, closest_point)

            return result
        except Exception as e:
            print(f"[storm] detect error: {e}")
            return None

    def convert_minimap_to_fullmap_coords(self, minimap_coords: Tuple[int, int],
                                        player_fullmap_pos: Tuple[int, int]) -> Tuple[int, int]:
        minimap_x, minimap_y = minimap_coords
        player_fullmap_x, player_fullmap_y = player_fullmap_pos
        minimap_region = get_minimap_region()
        minimap_center_x = minimap_region['left'] + minimap_region['width'] // 2
        minimap_center_y = minimap_region['top'] + minimap_region['height'] // 2
        offset_x = minimap_x - minimap_center_x
        offset_y = minimap_y - minimap_center_y
        fullmap_x = int(player_fullmap_x + (offset_x * self.minimap_scale_factor))
        fullmap_y = int(player_fullmap_y + (offset_y * self.minimap_scale_factor))
        return (fullmap_x, fullmap_y)

    # ── Loop & lifecycle ────────────────────────────────────────────

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
                        player_fullmap_pos = _get_position_tracker().get_cached_position()
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
            player_fullmap_pos = _get_position_tracker().get_cached_position()
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
