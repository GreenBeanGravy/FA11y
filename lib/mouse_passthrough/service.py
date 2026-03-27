"""
Mouse Passthrough Service - orchestrates mouse capture, FakerInput relay, and heartbeat.
Integrates with FA11y as a built-in module.
"""

import threading
import time
import ctypes
import logging
from typing import Optional
from dataclasses import asdict

from lib.config.config_manager import config_manager
from lib.mouse_passthrough.raw_input import MouseDevice, detect_mouse_device
from lib.mouse_passthrough.hook import MouseHook
from lib.mouse_passthrough.faker_input import send_mouse_move

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "DPI": 800,
    "BUFFER_SIZE": 256,
    "HEARTBEAT_ENABLED": True,
    "HEARTBEAT_INTERVAL": 0.3,
    "HEARTBEAT_DISTANCE": 2,
    "CACHE_INT16_RANGE": 100,
    "DETECTION_TIMEOUT": 10.0
}


def _is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


class MousePassthroughService:
    def __init__(self):
        config_manager.register(
            'mouse_passthrough',
            'config/mouse_passthrough.json',
            format='json',
            default=DEFAULT_CONFIG.copy()
        )

        self.config = config_manager.get('mouse_passthrough')

        # Merge defaults for any missing keys
        final_config = DEFAULT_CONFIG.copy()
        for key in DEFAULT_CONFIG:
            if key in self.config:
                final_config[key] = self.config[key]
        self.config = final_config

        self.target_device: Optional[MouseDevice] = None
        self.running = False
        self.mouse_hook = MouseHook(self.config)
        self.heartbeat_thread = None
        self.speaker = None

        if _is_admin():
            print("[INFO] Mouse passthrough: Running with Administrator privileges")

    def _on_config_change(self, config):
        """Handle main config change event — sync DPI."""
        from lib.utilities.utilities import get_config_value
        try:
            dpi_str, _ = get_config_value(config, 'MousePassthroughDPI', '800')
            main_dpi = int(float(dpi_str))
            if 50 <= main_dpi <= 50000:
                self.config["DPI"] = main_dpi
                if self.target_device and self.target_device.dpi != main_dpi:
                    self.target_device.dpi = main_dpi
                    self.target_device.update_dpi_scale()
        except (ValueError, TypeError):
            pass

    def initialize(self, speaker):
        """Initialize the mouse passthrough service. Called from FA11y main().

        Args:
            speaker: The TTS Auto() instance for announcing status
        """
        self.speaker = speaker
        self._load_device_from_config()

        # Subscribe to main config changes for DPI sync
        from lib.utilities.utilities import read_config, get_config_boolean, get_config_value, on_config_change
        on_config_change(self._on_config_change)

        main_config = read_config()
        enabled = get_config_boolean(main_config, 'MousePassthrough', True)

        # Seed DPI from main config (authoritative source)
        try:
            dpi_str, _ = get_config_value(main_config, 'MousePassthroughDPI', '800')
            main_dpi = int(float(dpi_str))
            if 50 <= main_dpi <= 50000:
                self.config["DPI"] = main_dpi
                if self.target_device and self.target_device.dpi != main_dpi:
                    self.target_device.dpi = main_dpi
                    self.target_device.update_dpi_scale()
        except (ValueError, TypeError):
            pass

        if self.target_device:
            if enabled:
                self.start()
            else:
                print("[INFO] Mouse passthrough disabled in config")
        else:
            # First-time setup (only if enabled)
            if enabled:
                self._first_time_setup()

    def _first_time_setup(self):
        """Guide the user through first-time mouse setup. Skippable."""
        if self.speaker:
            self.speaker.speak("No mouse configured for passthrough. Move your mouse to detect it, or press Enter to skip.")

        print("[INFO] No mouse configured. Move your mouse to detect it (or wait to skip)...")

        device = detect_mouse_device(
            dpi=self.config["DPI"],
            timeout=self.config["DETECTION_TIMEOUT"]
        )

        if not device:
            if self.speaker:
                self.speaker.speak("No mouse detected. You can recapture later with Alt Shift M.")
            print("[INFO] No mouse detected. Skipping passthrough setup.")
            return

        self.target_device = device
        self.mouse_hook.target_device = device
        self._save_device_to_config()
        self.start()

        if self.speaker:
            self.speaker.speak(f"Mouse passthrough started with {device.friendly_name} at {device.dpi} D P I.")

    def recapture_mouse(self):
        """Recapture the mouse device. Triggered by keybind."""
        if self.speaker:
            self.speaker.speak("Move your mouse to detect it.")

        # Stop current capture if running
        was_running = self.running
        if was_running:
            self.stop()

        device = detect_mouse_device(
            dpi=self.config["DPI"],
            timeout=self.config["DETECTION_TIMEOUT"]
        )

        if not device:
            if self.speaker:
                self.speaker.speak("No mouse detected.")
            # Restart previous capture if we had one
            if was_running and self.target_device:
                self.start()
            return

        # Preserve DPI if same device
        if self.target_device and self.target_device.matches(device.vendor_id, device.product_id):
            device.dpi = self.target_device.dpi
            device.update_dpi_scale()

        self.target_device = device
        self.mouse_hook.target_device = device
        self._save_device_to_config()
        self.start()

        if self.speaker:
            self.speaker.speak(f"Mouse recaptured: {device.friendly_name} at {device.dpi} D P I.")

    def toggle(self):
        """Toggle mouse passthrough on/off. Announces state via TTS."""
        if self.running:
            self.stop()
            if self.speaker:
                self.speaker.speak("Mouse passthrough disabled.")
            print("[INFO] Mouse passthrough disabled")
        else:
            if self.target_device:
                self.start()
                if self.speaker:
                    self.speaker.speak("Mouse passthrough enabled.")
                print("[INFO] Mouse passthrough enabled")
            else:
                if self.speaker:
                    self.speaker.speak("No mouse configured. Use recapture mouse first.")

    def update_dpi(self, new_dpi):
        """Update DPI in real-time without restarting capture."""
        if not self.target_device:
            return

        if not (50 <= new_dpi <= 50000):
            return

        self.target_device.dpi = new_dpi
        self.target_device.update_dpi_scale()
        self.mouse_hook.target_device = self.target_device
        self.config["DPI"] = new_dpi
        print(f"[INFO] DPI updated to {new_dpi}")

    def start(self):
        """Start the mouse passthrough (hook + heartbeat). Non-blocking."""
        if not self.target_device:
            print("[WARN] Cannot start passthrough: no mouse configured")
            return False

        self.mouse_hook.target_device = self.target_device

        if not self.mouse_hook.start_hook():
            print("[ERROR] Failed to start mouse capture")
            return False

        self.running = True

        self.mouse_hook.total_movements = 0
        self.mouse_hook.movements_since_last = 0

        if self.config.get("HEARTBEAT_ENABLED", True):
            self.heartbeat_thread = threading.Thread(target=self._heartbeat_worker, daemon=True)
            self.heartbeat_thread.start()

        print(f"[INFO] Mouse passthrough active: {self.target_device.friendly_name} @ {self.target_device.dpi} DPI")
        return True

    def stop(self):
        """Stop the mouse passthrough."""
        self.running = False
        self.mouse_hook.stop_hook()

    def _heartbeat_worker(self):
        """Send periodic micro-movements to keep FakerInput alive."""
        while self.running:
            time.sleep(self.config.get("HEARTBEAT_INTERVAL", 0.3))
            if not self.running:
                break

            if not self.config.get("HEARTBEAT_ENABLED", True):
                continue

            try:
                steps = self.config.get("HEARTBEAT_DISTANCE", 2)
                duration_s = 0.002
                sleep_between_steps = duration_s / steps

                for _ in range(steps):
                    if not self.running:
                        break
                    send_mouse_move(1, 0, self.config["CACHE_INT16_RANGE"])
                    time.sleep(sleep_between_steps)

                if not self.running:
                    break

                for _ in range(steps):
                    if not self.running:
                        break
                    send_mouse_move(-1, 0, self.config["CACHE_INT16_RANGE"])
                    time.sleep(sleep_between_steps)

            except Exception as e:
                print(f"[ERROR] Heartbeat failed: {e}")

    def _load_device_from_config(self):
        """Load saved mouse device from config."""
        try:
            device_data = config_manager.get('mouse_passthrough', 'device')

            if device_data and isinstance(device_data, dict):
                if device_data.get("vendor_id") and device_data.get("product_id"):
                    if "dpi" not in device_data:
                        device_data["dpi"] = self.config["DPI"]

                    self.target_device = MouseDevice(**device_data)
                    self.mouse_hook.target_device = self.target_device
                    print(f"[INFO] Loaded mouse: {self.target_device.friendly_name} @ {self.target_device.dpi} DPI")

                    self.config["DPI"] = self.target_device.dpi
        except Exception:
            pass

    def _save_device_to_config(self):
        """Save the current mouse device and full config to disk together."""
        try:
            # Build complete config with device data included
            save_data = self.config.copy()
            if self.target_device:
                device_dict = asdict(self.target_device)
                if '_dpi_scale' in device_dict:
                    del device_dict['_dpi_scale']
                save_data['device'] = device_dict

            config_manager.set('mouse_passthrough', data=save_data)
        except Exception as e:
            print(f"[ERROR] Failed to save config: {e}")
