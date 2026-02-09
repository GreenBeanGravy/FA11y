"""
SpatialAudio facade - maintains the original API while delegating to the
centralized FA11y audio engine (Steam Audio HRTF + low-latency backend).
"""

import math
import threading
import time
import numpy as np
from typing import Tuple


class SpatialAudio:
    def __init__(self, audio_file, chunk_size=4096):
        self.audio_file = audio_file
        self._sound_id = audio_file
        self._active_playback_id = None
        self._playback_lock = threading.Lock()

        self.volume = 1.0
        self.master_volume = 1.0
        self.individual_volume = 1.0

        self.audio_initialized = False
        self.initialization_attempted = False

        self._load_into_engine()

    def _load_into_engine(self):
        """Load this sound into the shared engine"""
        if self.initialization_attempted:
            return
        self.initialization_attempted = True

        try:
            from lib.audio import get_engine
            engine = get_engine()
            if engine and engine.load_sound(self._sound_id, self.audio_file):
                self.audio_initialized = True
        except Exception:
            self.audio_initialized = False

    @property
    def is_playing(self):
        with self._playback_lock:
            pid = self._active_playback_id
        if pid is not None:
            try:
                from lib.audio import get_engine
                engine = get_engine()
                if engine:
                    return engine.is_sound_playing(pid)
            except Exception:
                pass
        return False

    def set_volume(self, volume):
        self.volume = max(0.0, min(1.0, volume))

    def set_master_volume(self, volume):
        self.master_volume = max(0.0, min(1.0, volume))

    def set_individual_volume(self, volume):
        self.individual_volume = max(0.0, min(1.0, volume))

    def play_audio(self, left_weight=None, right_weight=None, volume=1.0,
                   pitch_shift=None, distance=None, relative_angle=None):
        """Play audio with either spatial parameters or legacy stereo weights.

        Callers already compute volume-from-distance, so the engine position is
        used ONLY for directionality (HRTF / stereo panning).  We place the
        source at a fixed small radius (1.0) in the correct direction and
        disable engine-side distance attenuation so the caller's `volume`
        parameter is the sole loudness control.
        """
        self.stop()

        if not self.audio_initialized:
            self._load_into_engine()
            if not self.audio_initialized:
                return

        try:
            from lib.audio import get_engine
            engine = get_engine()
            if not engine:
                return

            final_volume = volume * self.master_volume * self.individual_volume
            pitch = pitch_shift if pitch_shift and pitch_shift != 1.0 else 1.0

            if distance is not None and relative_angle is not None:
                # Place source at a fixed small radius in the correct direction.
                # This gives the engine the angle for HRTF / panning without
                # any distance attenuation (min_distance >= placement radius).
                #
                # Engine coordinate convention: +X Forward, +Y Left, +Z Up
                # FA11y convention: relative_angle > 0 = RIGHT, < 0 = LEFT
                # So we negate Y so positive angle → negative Y (right in engine).
                FIXED_RADIUS = 1.0
                angle_rad = math.radians(relative_angle)
                x = math.cos(angle_rad) * FIXED_RADIUS
                y = -math.sin(angle_rad) * FIXED_RADIUS
                z = 0.0

                if self.is_behind(relative_angle):
                    self._play_behind_sound(x, y, z, final_volume, pitch)
                    return

                with self._playback_lock:
                    self._active_playback_id = engine.play_sound(
                        self._sound_id, x, y, z,
                        volume=final_volume, pitch=pitch,
                        min_distance=FIXED_RADIUS, max_distance=100.0,
                        min_volume=1.0
                    )
            else:
                # Legacy stereo panning (config_gui test playback)
                # Play at center position (directly in front)
                with self._playback_lock:
                    self._active_playback_id = engine.play_sound(
                        self._sound_id, 1.0, 0.0, 0.0,
                        volume=final_volume, pitch=pitch,
                        min_distance=1.0, max_distance=100.0,
                        min_volume=1.0
                    )

        except Exception:
            pass

    def _play_behind_sound(self, x, y, z, volume, pitch):
        """Play the double-tap behind indicator"""
        def behind_worker():
            try:
                from lib.audio import get_engine
                engine = get_engine()
                if not engine:
                    return

                pid1 = engine.play_sound(
                    self._sound_id, x, y, z,
                    volume=volume, pitch=pitch,
                    min_distance=1.0, max_distance=100.0,
                    min_volume=1.0
                )
                with self._playback_lock:
                    self._active_playback_id = pid1

                time.sleep(0.15)

                if self._active_playback_id is not None:
                    engine.play_sound(
                        self._sound_id, x, y, z,
                        volume=volume, pitch=pitch,
                        min_distance=1.0, max_distance=100.0,
                        min_volume=1.0
                    )
            except Exception:
                pass

        t = threading.Thread(target=behind_worker, daemon=True)
        t.start()

    def update_spatial_position(self, distance: float, relative_angle: float, volume: float = 1.0):
        """Update spatial position for a currently playing sound.

        Like play_audio, we place the source at a fixed small radius for
        directionality only.  The caller's volume is the sole loudness control.
        """
        with self._playback_lock:
            pid = self._active_playback_id
        if pid is None:
            return

        try:
            from lib.audio import get_engine
            engine = get_engine()
            if not engine:
                return

            final_volume = volume * self.master_volume * self.individual_volume
            FIXED_RADIUS = 1.0
            angle_rad = math.radians(relative_angle)
            x = math.cos(angle_rad) * FIXED_RADIUS
            y = -math.sin(angle_rad) * FIXED_RADIUS
            z = 0.0

            engine.update_source_position(pid, x, y, z, volume=final_volume)
        except Exception:
            pass

    def update_panning(self, left_weight, right_weight, volume=None):
        """Legacy panning update - now handled by update_spatial_position"""
        pass

    def apply_pitch_shift(self, factor):
        """Pitch is applied at play time via the engine"""
        pass

    def stop(self):
        """Stop current playback"""
        with self._playback_lock:
            pid = self._active_playback_id
            self._active_playback_id = None

        if pid is not None:
            try:
                from lib.audio import get_engine
                engine = get_engine()
                if engine:
                    engine.stop_sound(pid)
            except Exception:
                pass

    def cleanup(self):
        """Clean up resources"""
        self.stop()

    # ========================================================================
    # Static utility methods (preserved exactly from original)
    # ========================================================================

    @staticmethod
    def calculate_spatial_panning(player_position: Tuple[int, int],
                                 player_angle: float,
                                 target_position: Tuple[int, int]) -> Tuple[float, float]:
        """Calculate stereo panning weights based on player and target positions."""
        try:
            target_vector = np.array(target_position) - np.array(player_position)
            target_angle = (90 - np.degrees(np.arctan2(-target_vector[1], target_vector[0]))) % 360
            relative_angle = (target_angle - player_angle + 180) % 360 - 180
            return SpatialAudio.calculate_stereo_weights(relative_angle)
        except Exception:
            return 0.5, 0.5

    @staticmethod
    def calculate_distance_and_angle(player_position: Tuple[int, int],
                                     player_angle: float,
                                     target_position: Tuple[int, int]) -> Tuple[float, float]:
        """Calculate distance and relative angle from player to target."""
        try:
            target_vector = np.array(target_position) - np.array(player_position)
            distance = np.linalg.norm(target_vector) * 2.65
            target_angle = (90 - np.degrees(np.arctan2(-target_vector[1], target_vector[0]))) % 360
            relative_angle = (target_angle - player_angle + 180) % 360 - 180
            return distance, relative_angle
        except Exception:
            return 0.0, 0.0

    @staticmethod
    def calculate_stereo_weights(relative_angle: float) -> Tuple[float, float]:
        """Calculate stereo weights from relative angle."""
        angle_rad = np.radians(relative_angle)
        pan_factor = np.sin(angle_rad)

        if abs(pan_factor) > 0.1:
            pan_factor = np.sign(pan_factor) * (abs(pan_factor) ** 0.7)

        left_weight = np.clip((1 - pan_factor) / 2, 0.1, 0.9)
        right_weight = np.clip((1 + pan_factor) / 2, 0.1, 0.9)
        return left_weight, right_weight

    @staticmethod
    def is_behind(relative_angle: float) -> bool:
        """Check if the sound source is behind the player."""
        return abs(relative_angle) > 90

    @staticmethod
    def get_volume_from_config(config, volume_key: str, master_key: str = 'MasterVolume',
                               fallback: float = 1.0) -> Tuple[float, float]:
        """Get master and individual volume from config."""
        try:
            from lib.utilities.utilities import get_config_float
            master_volume = get_config_float(config, master_key, 1.0)
            individual_volume = get_config_float(config, volume_key, fallback)
            return master_volume, individual_volume
        except Exception:
            return 1.0, fallback
