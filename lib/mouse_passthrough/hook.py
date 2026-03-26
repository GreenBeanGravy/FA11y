"""
Mouse hook for processing raw input movements and sending them through FakerInput.
"""

import time
from typing import Optional

from lib.mouse_passthrough.raw_input import MouseDevice, RawInputCapture
from lib.mouse_passthrough.faker_input import send_mouse_move, initialize_fakerinput


class MouseHook:
    def __init__(self, config):
        self.config = config
        self.target_device: Optional[MouseDevice] = None
        self.raw_input_capture = None

        self.total_movements = 0
        self.movements_since_last = 0
        self.last_perf_time = time.perf_counter()

        initialize_fakerinput(config["CACHE_INT16_RANGE"])

    def process_movement(self, raw_dx, raw_dy):
        if not self.target_device:
            return

        scaled_dx = int(raw_dx * self.target_device._dpi_scale)
        scaled_dy = int(raw_dy * self.target_device._dpi_scale)

        if scaled_dx != 0 or scaled_dy != 0:
            if send_mouse_move(scaled_dx, scaled_dy, self.config["CACHE_INT16_RANGE"]):
                self.total_movements += 1
                self.movements_since_last += 1

    def start_hook(self):
        if not self.target_device:
            return False

        print("[INFO] Starting capture...")

        self.raw_input_capture = RawInputCapture(
            self.target_device,
            self.process_movement,
            self.config["BUFFER_SIZE"]
        )

        if self.raw_input_capture.start_capture():
            print("[INFO] Capture started")
            return True
        else:
            return False

    def stop_hook(self):
        if self.raw_input_capture:
            self.raw_input_capture.stop_capture()
            self.raw_input_capture = None
