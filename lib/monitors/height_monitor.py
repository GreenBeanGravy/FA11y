"""
Height indicator monitor (skydiving altitude).

Polls a few pixels of the skydive HUD every 2.5 s; when the indicator bar
is visible, interpolates its y-pixel into meters and speaks the value.

This used to be a bare ``start_height_monitor()`` function. It's now a
``BaseMonitor`` subclass so shutdown goes through the same lifecycle as
the other monitors, but a module-level ``start_height_monitor()`` shim is
kept for backward compatibility with existing call sites in FA11y.py.
"""
from __future__ import annotations

import threading
import time
from typing import Tuple

import numpy as np
from PIL import ImageGrab
from accessible_output2.outputs.auto import Auto

from lib.monitors.base import BaseMonitor

speaker = Auto()

# Shared state indicating if the height indicator is currently visible.
_height_indicator_visible = False
_state_lock = threading.Lock()


def is_height_indicator_visible() -> bool:
    """Return True if the height indicator is currently visible on screen."""
    with _state_lock:
        return _height_indicator_visible


def _set_height_visible(value: bool) -> None:
    global _height_indicator_visible
    with _state_lock:
        _height_indicator_visible = value


def _check_pixel_color(x: int, y: int, target_color: Tuple[int, int, int]) -> bool:
    screenshot = ImageGrab.grab(bbox=(x, y, x + 1, y + 1))
    return screenshot.getpixel((0, 0)) == target_color


def _interpolate_height(pixel_y: int):
    """Map a y pixel on the height-bar to meters (piecewise linear).

    Calibrated against three known landmarks on the HUD:

        (y1=37,  h1=750)  — top of the bar
        (y2=163, h2=325)  — mid-point
        (y3=289, h3=0)    — bottom (ground)
    """
    y1, h1 = 37, 750
    y2, h2 = 163, 325
    y3, h3 = 289, 0

    if y1 <= pixel_y <= y2:
        return h1 + (pixel_y - y1) * (h2 - h1) / (y2 - y1)
    if y2 < pixel_y <= y3:
        return h2 + (pixel_y - y2) * (h3 - h2) / (y3 - y2)
    return None


class HeightMonitor(BaseMonitor):
    """Poll the skydive height HUD at 2.5 s cadence."""

    _THREAD_NAME = "HeightMonitor"

    # HUD constants — small enough to inline; tweak here if the HUD moves.
    TARGET_COLOR: Tuple[int, int, int] = (255, 255, 255)
    CHECK_POINTS = [(1576, 319), (1586, 319), (1596, 319), (1599, 23)]
    HEIGHT_X = 1583
    MIN_Y, MAX_Y = 47, 299
    POLL_INTERVAL_S = 2.5

    def _monitor_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                if self.wizard_paused():
                    time.sleep(0.5)
                    continue
                structure_present = all(
                    _check_pixel_color(x, y, self.TARGET_COLOR)
                    for (x, y) in self.CHECK_POINTS
                )

                if structure_present:
                    screenshot = ImageGrab.grab(
                        bbox=(self.HEIGHT_X, self.MIN_Y,
                              self.HEIGHT_X + 1, self.MAX_Y + 1)
                    )
                    img_array = np.array(screenshot)
                    white_pixels = np.where(
                        np.all(img_array == self.TARGET_COLOR, axis=1)
                    )[0]

                    if white_pixels.size > 0:
                        if not is_height_indicator_visible():
                            print("Height indicator appeared")
                        _set_height_visible(True)
                        pixel_y = self.MIN_Y + int(white_pixels[0])
                        meters = _interpolate_height(pixel_y)
                        if meters is not None:
                            print(f"Height detected: {meters:.2f} meters")
                            speaker.speak(f"{meters:.0f} meters high")
                        else:
                            print("Height indicator outside expected range")
                    else:
                        if is_height_indicator_visible():
                            print("Height indicator disappeared")
                        _set_height_visible(False)
                else:
                    if is_height_indicator_visible():
                        print("Height indicator structure disappeared")
                    _set_height_visible(False)
            except Exception as e:
                print(f"Error in height detection: {e}")
                # On error, don't flip state to avoid spurious transitions.

            # Honour the stop event so shutdown is responsive.
            if self.stop_event.wait(timeout=self.POLL_INTERVAL_S):
                return


# Module-level singleton so callers can reach it without re-importing.
height_monitor = HeightMonitor()


def start_height_monitor() -> None:
    """Backward-compatible shim — spin up the monitor if it isn't already.

    FA11y.py called this bare function historically; keep it working.
    """
    height_monitor.start_monitoring()


def stop_height_monitor() -> None:
    """Companion shutdown helper — also used from FA11y shutdown paths."""
    height_monitor.stop_monitoring()
