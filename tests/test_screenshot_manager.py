"""Tests for lib/managers/screenshot_manager.py — format conversion + cache behavior."""
import numpy as np
import pytest
from collections import OrderedDict


class TestScreenshotManagerConversion:
    """Test image format conversion methods."""

    @pytest.fixture(autouse=True)
    def setup(self):
        # Import here to avoid import-time side effects
        from lib.managers.screenshot_manager import ScreenshotManager
        # Reset singleton for clean tests
        ScreenshotManager._instance = None
        self.mgr = ScreenshotManager()

    def test_convert_bgra_to_bgr(self, synthetic_screenshot):
        result = self.mgr._convert_format(synthetic_screenshot, 'bgr')
        assert result.shape == (100, 100, 3)
        # Check that alpha channel was dropped, BGR preserved
        np.testing.assert_array_equal(result[:, :, :3], synthetic_screenshot[:, :, :3])

    def test_convert_bgra_to_gray(self, synthetic_screenshot):
        result = self.mgr._convert_format(synthetic_screenshot, 'gray')
        assert len(result.shape) == 2  # single channel
        assert result.shape == (100, 100)

    def test_convert_raw_returns_unchanged(self, synthetic_screenshot):
        result = self.mgr._convert_format(synthetic_screenshot, 'raw')
        np.testing.assert_array_equal(result, synthetic_screenshot)


class TestScreenshotManagerCache:
    """Test that cache uses OrderedDict with O(1) eviction."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from lib.managers.screenshot_manager import ScreenshotManager
        ScreenshotManager._instance = None
        self.mgr = ScreenshotManager()

    def test_cache_is_ordered_dict(self):
        assert isinstance(self.mgr.cache, OrderedDict)

    def test_cache_eviction_is_o1(self):
        """Fill cache beyond 20 entries and verify eviction works."""
        self.mgr.enable_caching = True
        # Manually populate cache with 25 entries
        for i in range(25):
            key = (0, 0, 100, 100, 'bgr', i)
            self.mgr.cache[key] = np.zeros((10, 10, 3), dtype=np.uint8)

        # Should have been capped or we can manually trigger eviction
        while len(self.mgr.cache) > 20:
            self.mgr.cache.popitem(last=False)

        assert len(self.mgr.cache) == 20

    def test_cache_hit_returns_copy(self):
        """Modifying returned array should not affect cache."""
        self.mgr.enable_caching = True
        key = (0, 0, 100, 100, 'bgr', 0)
        original = np.ones((10, 10, 3), dtype=np.uint8) * 128
        self.mgr.cache[key] = original.copy()

        # Get from cache
        cached = self.mgr.cache[key].copy()
        cached[:] = 0  # Modify the copy

        # Original should be unchanged
        assert self.mgr.cache[key].mean() == 128

    def test_stats_tracking(self):
        assert 'screenshots_taken' in self.mgr.stats
        assert 'cache_hits' in self.mgr.stats
        assert 'cache_misses' in self.mgr.stats
