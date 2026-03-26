"""Performance benchmark tests — establish baselines and validate optimizations."""
import os
import sys
import time
import json
import configparser
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestConfigManagerPerformance:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.old_cwd = os.getcwd()
        os.chdir(tmp_path)
        os.makedirs('config', exist_ok=True)
        from lib.config.config_manager import ConfigManager
        self.mgr = ConfigManager()
        self.mgr.register('perf', 'config/perf.json', format='json',
                          default={'key': 'value'}, cache_timeout=60)
        yield
        os.chdir(self.old_cwd)

    def test_cached_get_performance(self):
        """1000 cached gets should complete in < 50ms."""
        # Warm cache
        self.mgr.get('perf')

        start = time.perf_counter()
        for _ in range(1000):
            self.mgr.get('perf', 'key')
        elapsed = time.perf_counter() - start

        assert elapsed < 0.05, f"1000 cached gets took {elapsed:.3f}s (limit: 0.05s)"

    def test_set_performance(self):
        """100 set+save cycles should complete in < 2s."""
        start = time.perf_counter()
        for i in range(100):
            self.mgr.set('perf', 'count', i)
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f"100 sets took {elapsed:.3f}s (limit: 2.0s)"


class TestScreenshotPerformance:
    def test_format_conversion_speed(self, large_screenshot):
        """100 BGRA->BGR conversions of 1920x1080 should complete in < 1s."""
        from lib.managers.screenshot_manager import ScreenshotManager
        ScreenshotManager._instance = None
        mgr = ScreenshotManager()

        start = time.perf_counter()
        for _ in range(100):
            mgr._convert_format(large_screenshot, 'bgr')
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"100 conversions took {elapsed:.3f}s (limit: 1.0s)"

    def test_cache_eviction_speed(self):
        """1000 OrderedDict evictions should complete in < 100ms."""
        from collections import OrderedDict
        cache = OrderedDict()

        # Pre-fill
        for i in range(1020):
            cache[i] = np.zeros((10, 10, 3), dtype=np.uint8)

        start = time.perf_counter()
        for _ in range(1000):
            cache.popitem(last=False)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.1, f"1000 evictions took {elapsed:.3f}s (limit: 0.1s)"


class TestDefaultConfigPerformance:
    def test_default_config_generation_speed(self):
        """100 get_default_config() calls should complete in < 500ms."""
        from lib.utilities.utilities import get_default_config

        start = time.perf_counter()
        for _ in range(100):
            get_default_config()
        elapsed = time.perf_counter() - start

        assert elapsed < 0.5, f"100 config generations took {elapsed:.3f}s (limit: 0.5s)"


class TestKeyCombinationPerformance:
    def test_parse_speed(self):
        """10000 parse_key_combination() calls should complete in < 100ms."""
        from lib.utilities.input import parse_key_combination

        combos = ["lctrl+lshift+m", "f8", "lalt+p", "num 1", "a"]

        start = time.perf_counter()
        for _ in range(2000):
            for combo in combos:
                parse_key_combination(combo)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.1, f"10000 parses took {elapsed:.3f}s (limit: 0.1s)"


class TestDPIScalePerformance:
    def test_dpi_calculation_speed(self):
        """100000 DPI scale calculations should complete in < 100ms."""
        start = time.perf_counter()
        for dpi in range(100, 100100):
            _ = dpi / 800.0
        elapsed = time.perf_counter() - start

        assert elapsed < 0.1, f"100000 calcs took {elapsed:.3f}s (limit: 0.1s)"
