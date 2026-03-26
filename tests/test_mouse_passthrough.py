"""Tests for lib/mouse_passthrough/ module."""
import os
import sys
import json
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestMouseDevice:
    def test_dpi_scale_1600(self):
        from lib.mouse_passthrough.raw_input import MouseDevice
        device = MouseDevice(
            vendor_id="046D", product_id="C08B",
            friendly_name="Test Mouse", dpi=1600
        )
        assert device._dpi_scale == 2.0

    def test_dpi_scale_800(self):
        from lib.mouse_passthrough.raw_input import MouseDevice
        device = MouseDevice(
            vendor_id="046D", product_id="C08B",
            friendly_name="Test Mouse", dpi=800
        )
        assert device._dpi_scale == 1.0

    def test_dpi_scale_400(self):
        from lib.mouse_passthrough.raw_input import MouseDevice
        device = MouseDevice(
            vendor_id="046D", product_id="C08B",
            friendly_name="Test Mouse", dpi=400
        )
        assert device._dpi_scale == 0.5

    def test_matches_same_vid_pid(self):
        from lib.mouse_passthrough.raw_input import MouseDevice
        device = MouseDevice(
            vendor_id="046D", product_id="C08B",
            friendly_name="Test Mouse", dpi=1600
        )
        assert device.matches("046D", "C08B")

    def test_matches_different_vid_pid(self):
        from lib.mouse_passthrough.raw_input import MouseDevice
        device = MouseDevice(
            vendor_id="046D", product_id="C08B",
            friendly_name="Test Mouse", dpi=1600
        )
        assert not device.matches("1532", "C08B")
        assert not device.matches("046D", "FFFF")

    def test_update_dpi_scale(self):
        from lib.mouse_passthrough.raw_input import MouseDevice
        device = MouseDevice(
            vendor_id="046D", product_id="C08B",
            friendly_name="Test Mouse", dpi=800
        )
        assert device._dpi_scale == 1.0
        device.dpi = 1600
        device.update_dpi_scale()
        assert device._dpi_scale == 2.0


class TestDevicePathParsing:
    def test_parse_device_path(self):
        from lib.mouse_passthrough.raw_input import _parse_device_path
        vid, pid = _parse_device_path("\\\\?\\HID#VID_046D&PID_C08B#something")
        assert vid == "046D"
        assert pid == "C08B"

    def test_parse_device_path_lowercase(self):
        from lib.mouse_passthrough.raw_input import _parse_device_path
        vid, pid = _parse_device_path("\\\\?\\hid#vid_1532&pid_007a#stuff")
        assert vid == "1532"
        assert pid == "007A"

    def test_parse_device_path_no_ids(self):
        from lib.mouse_passthrough.raw_input import _parse_device_path
        vid, pid = _parse_device_path("something_without_ids")
        assert vid == "0000"
        assert pid == "0000"


class TestFriendlyName:
    def test_known_brand_logitech(self):
        from lib.mouse_passthrough.raw_input import _get_friendly_name
        name = _get_friendly_name("\\\\?\\HID#VID_046D&PID_C08B#stuff")
        assert "Logitech" in name
        assert "046D" in name

    def test_known_brand_razer(self):
        from lib.mouse_passthrough.raw_input import _get_friendly_name
        name = _get_friendly_name("\\\\?\\HID#VID_1532&PID_007A#stuff")
        assert "Razer" in name

    def test_unknown_brand(self):
        from lib.mouse_passthrough.raw_input import _get_friendly_name
        name = _get_friendly_name("\\\\?\\HID#VID_ABCD&PID_1234#stuff")
        assert "Gaming" in name


class TestServiceConfig:
    def test_config_registration(self, tmp_path):
        """Service registers 'mouse_passthrough' config on creation."""
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        os.makedirs('config', exist_ok=True)

        from lib.config.config_manager import ConfigManager
        # Use a fresh config manager
        import lib.mouse_passthrough.service as svc_mod
        old_cm = svc_mod.config_manager
        fresh_cm = ConfigManager()
        svc_mod.config_manager = fresh_cm

        try:
            from lib.mouse_passthrough.service import MousePassthroughService
            service = MousePassthroughService()
            assert 'mouse_passthrough' in fresh_cm._registries
        finally:
            svc_mod.config_manager = old_cm
            os.chdir(old_cwd)

    def test_service_update_dpi(self, mock_speaker):
        from lib.mouse_passthrough.raw_input import MouseDevice
        from lib.mouse_passthrough.service import MousePassthroughService

        service = MousePassthroughService.__new__(MousePassthroughService)
        service.speaker = mock_speaker
        device = MouseDevice(
            vendor_id="046D", product_id="C08B",
            friendly_name="Test", dpi=800
        )
        service.target_device = device
        service.config = {"DPI": 800}

        # Mock the hook
        service.mouse_hook = MagicMock()

        service.update_dpi(1600)
        assert device.dpi == 1600
        assert device._dpi_scale == 2.0

    def test_service_toggle(self, mock_speaker):
        from lib.mouse_passthrough.service import MousePassthroughService

        service = MousePassthroughService.__new__(MousePassthroughService)
        service.speaker = mock_speaker
        service.running = True
        service.mouse_hook = MagicMock()
        service.heartbeat_thread = None
        service.target_device = MagicMock()

        # Toggle off
        service.toggle()
        assert not service.running
        mock_speaker.speak.assert_called_with("Mouse passthrough disabled.")


class TestMovementScaling:
    def test_raw_to_scaled(self):
        """raw (10, 20) at 1600 DPI (scale=2.0) should produce scaled (20, 40)."""
        from lib.mouse_passthrough.raw_input import MouseDevice
        device = MouseDevice(
            vendor_id="046D", product_id="C08B",
            friendly_name="Test", dpi=1600
        )
        raw_dx, raw_dy = 10, 20
        scaled_dx = int(raw_dx * device._dpi_scale)
        scaled_dy = int(raw_dy * device._dpi_scale)
        assert scaled_dx == 20
        assert scaled_dy == 40

    def test_raw_to_scaled_800dpi(self):
        """At 800 DPI (scale=1.0), raw == scaled."""
        from lib.mouse_passthrough.raw_input import MouseDevice
        device = MouseDevice(
            vendor_id="046D", product_id="C08B",
            friendly_name="Test", dpi=800
        )
        raw_dx, raw_dy = 15, 25
        scaled_dx = int(raw_dx * device._dpi_scale)
        scaled_dy = int(raw_dy * device._dpi_scale)
        assert scaled_dx == 15
        assert scaled_dy == 25
