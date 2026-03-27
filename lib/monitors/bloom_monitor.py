"""
Crosshair bloom monitor.

Detects bloom lines radiating from screen center and plays a pitch-shifted
440 Hz tone that increases as bloom grows. Also detects pickaxe equip via
center pixel pattern.

Runs at 24 FPS, scanning a 150x150 region around screen center (960, 540).
"""

import threading
import time
import numpy as np
from mss import mss
from accessible_output2.outputs.auto import Auto
from lib.utilities.utilities import read_config, get_config_boolean, on_config_change
from lib.monitors.background_monitor import monitor

# Screen center
CX, CY = 960, 540

# Capture region: 300x300 around center
REGION = {'left': CX - 150, 'top': CY - 150, 'width': 300, 'height': 300}
# Local center within the captured region
LCX, LCY = 150, 150

# Color checks
CENTER_COLOR = np.array([242, 245, 242], dtype=np.uint8)
COLOR_TOLERANCE = 6

# Pitch range: base pitch to 2x pitch, over 0-50 pixel distance
MIN_PITCH = 0.8
MAX_PITCH = 2.0
MAX_BLOOM_DIST = 65

# Tone playback
TONE_VOLUME = 0.25
TONE_COOLDOWN = 0.05  # Minimum seconds between tone plays

# Frame interval for 24 FPS
FRAME_INTERVAL = 1.0 / 24.0


def _color_match(pixel, target, tol=COLOR_TOLERANCE):
    """Check if an RGB pixel matches target within tolerance."""
    return all(abs(int(pixel[i]) - int(target[i])) <= tol for i in range(3))


def _find_bloom_line_distance(img, lcx, lcy, dx, dy, max_dist=75):
    """
    Search outward from center in direction (dx, dy) for a bloom line.
    Returns the distance from center to the closest white pixel of the line,
    or None if no line found.

    Starts searching from 5px out (skip the crosshair itself).
    """
    h, w = img.shape[:2]
    for dist in range(5, max_dist):
        px = lcx + dx * dist
        py = lcy + dy * dist
        if 0 <= px < w and 0 <= py < h:
            r, g, b = img[py, px, 0], img[py, px, 1], img[py, px, 2]
            if r >= 245 and g >= 245 and b >= 245:
                return dist
    return None


class BloomMonitor:
    """Monitors crosshair bloom and pickaxe equip state."""

    def __init__(self):
        self.running = False
        self.stop_event = threading.Event()
        self.thread = None
        self._last_bloom_dist = None
        self._last_tone_time = 0.0

        # Cached config — updated via on_config_change
        self._cached_enabled = True

        # Audio - use engine directly for fire-and-forget playback
        self._sound_id = 'sounds/bloom_tone.ogg'
        self._audio_loaded = False

        on_config_change(self._on_config_change)

    def _on_config_change(self, config):
        """Handle config change event."""
        self._cached_enabled = get_config_boolean(config, 'MonitorBloom', True)

    def is_enabled(self) -> bool:
        """Check if bloom monitoring is enabled."""
        return self._cached_enabled

    def _ensure_audio(self):
        """Lazy-load bloom tone into the audio engine."""
        if self._audio_loaded:
            return True
        try:
            from lib.audio import get_engine
            engine = get_engine()
            if engine and engine.load_sound(self._sound_id, self._sound_id):
                self._audio_loaded = True
                return True
        except Exception:
            pass
        return False

    def _is_center_crosshair(self, img):
        """Check if the center pixel matches the crosshair color."""
        pixel = img[LCY, LCX]
        return _color_match(pixel, CENTER_COLOR)

    def _detect_bloom(self, img):
        """
        Detect bloom lines in 4 cardinal directions.
        Returns closest distance if >= 2 lines found, else None.
        """
        directions = [
            (0, -1),  # up
            (0, 1),   # down
            (-1, 0),  # left
            (1, 0),   # right
        ]

        distances = []
        for dx, dy in directions:
            d = _find_bloom_line_distance(img, LCX, LCY, dx, dy)
            if d is not None:
                distances.append(d)

        if len(distances) >= 2:
            return min(distances)
        return None

    def _play_bloom_tone(self, distance):
        """Play bloom tone with pitch based on distance. Fire-and-forget, rate-limited."""
        now = time.perf_counter()
        if now - self._last_tone_time < TONE_COOLDOWN:
            return

        if not self._ensure_audio():
            return

        try:
            from lib.audio import get_engine
            engine = get_engine()
            if not engine:
                return

            clamped = max(0, min(distance, MAX_BLOOM_DIST))
            t = clamped / MAX_BLOOM_DIST
            pitch = MIN_PITCH + t * (MAX_PITCH - MIN_PITCH)

            engine.play_sound(
                self._sound_id, 1.0, 0.0, 0.0,
                volume=TONE_VOLUME, pitch=pitch,
                min_distance=1.0, max_distance=100.0, min_volume=1.0
            )
            self._last_tone_time = now
        except Exception:
            pass

    def _monitor_loop(self):
        """Main monitor loop at 24 FPS."""
        with mss() as sct:
            while not self.stop_event.is_set():
                loop_start = time.perf_counter()

                try:
                    # Skip if map is open or disabled in config
                    if monitor.map_open or not self.is_enabled():
                        self._last_bloom_dist = None
                        time.sleep(0.25)
                        continue

                    # Capture region
                    raw = np.array(sct.grab(REGION))
                    # Convert BGRA to RGB
                    img = raw[:, :, :3][:, :, ::-1]

                    # Check if crosshair is visible
                    if not self._is_center_crosshair(img):
                        self._last_bloom_dist = None
                        elapsed = time.perf_counter() - loop_start
                        remaining = FRAME_INTERVAL - elapsed
                        if remaining > 0:
                            time.sleep(remaining)
                        continue

                    # Detect bloom - only play when distance changes
                    bloom_dist = self._detect_bloom(img)
                    if bloom_dist is not None:
                        if bloom_dist != self._last_bloom_dist:
                            self._play_bloom_tone(bloom_dist)
                            self._last_bloom_dist = bloom_dist
                    else:
                        self._last_bloom_dist = None

                except Exception:
                    pass

                elapsed = time.perf_counter() - loop_start
                remaining = FRAME_INTERVAL - elapsed
                if remaining > 0:
                    time.sleep(remaining)

    def start_monitoring(self):
        """Start the bloom monitor."""
        if not self.running:
            self.running = True
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.thread.start()

    def stop_monitoring(self):
        """Stop the bloom monitor."""
        self.stop_event.set()
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)


bloom_monitor = BloomMonitor()
