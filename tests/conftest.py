"""Shared test fixtures for FA11y test suite."""
import os
import sys
import json
import tempfile
import shutil
import pytest
import numpy as np
from unittest.mock import MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Temporary config directory with synthetic config files."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def fresh_config_manager(tmp_config_dir):
    """Fresh ConfigManager instance pointing at temp dir."""
    from lib.config.config_manager import ConfigManager
    mgr = ConfigManager()
    # Override its config directory
    return mgr


@pytest.fixture
def sample_json_config():
    """Sample JSON config data."""
    return {
        "DPI": 1600,
        "BUFFER_SIZE": 256,
        "HEARTBEAT_ENABLED": True,
        "device": {
            "vendor_id": "046D",
            "product_id": "C08B",
            "friendly_name": "Logitech Mouse (046D:C08B)",
            "device_path": "\\\\?\\HID#VID_046D&PID_C08B",
            "handle_value": 12345,
            "dpi": 1600
        }
    }


@pytest.fixture
def synthetic_screenshot():
    """Random BGRA numpy array simulating a screenshot."""
    return np.random.randint(0, 256, (100, 100, 4), dtype=np.uint8)


@pytest.fixture
def synthetic_bgr_screenshot():
    """Random BGR numpy array."""
    return np.random.randint(0, 256, (100, 100, 3), dtype=np.uint8)


@pytest.fixture
def mock_speaker():
    """Mock TTS speaker that records calls."""
    speaker = MagicMock()
    speaker.speak = MagicMock()
    return speaker


@pytest.fixture
def large_screenshot():
    """1920x1080 BGRA screenshot for performance tests."""
    return np.random.randint(0, 256, (1080, 1920, 4), dtype=np.uint8)
