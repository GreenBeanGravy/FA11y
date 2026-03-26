"""Tests for lib/config/config_manager.py"""
import os
import json
import time
import threading
import pytest

from lib.config.config_manager import ConfigManager


@pytest.fixture
def mgr(tmp_path):
    """Fresh ConfigManager with temp working dir."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    os.makedirs('config', exist_ok=True)
    m = ConfigManager()
    yield m
    os.chdir(old_cwd)


class TestConfigManagerBasics:
    def test_register_json_config(self, mgr):
        mgr.register('test', 'config/test.json', format='json', default={'key': 'value'})
        result = mgr.get('test')
        assert result == {'key': 'value'}

    def test_register_idempotent(self, mgr):
        mgr.register('test', 'config/test.json', format='json', default={'a': 1})
        mgr.register('test', 'config/test.json', format='json', default={'a': 999})
        # Second register should not overwrite
        result = mgr.get('test')
        assert result == {'a': 1}

    def test_get_set_json_key(self, mgr):
        mgr.register('test', 'config/test.json', format='json', default={})
        mgr.set('test', 'name', 'fa11y')
        assert mgr.get('test', 'name') == 'fa11y'

    def test_get_set_entire_json(self, mgr):
        mgr.register('test', 'config/test.json', format='json', default={})
        mgr.set('test', data={'x': 1, 'y': 2})
        result = mgr.get('test')
        assert result == {'x': 1, 'y': 2}

    def test_get_nonexistent_key_returns_default(self, mgr):
        mgr.register('test', 'config/test.json', format='json', default={})
        assert mgr.get('test', 'missing', default='fallback') == 'fallback'

    def test_exists_check(self, mgr):
        mgr.register('test', 'config/test.json', format='json', default={'a': 1})
        mgr.get('test')  # Force file creation
        assert mgr.exists('test')
        assert mgr.exists('test', 'a')
        assert not mgr.exists('test', 'missing')

    def test_reload_clears_cache(self, mgr):
        mgr.register('test', 'config/test.json', format='json', default={'v': 1}, cache_timeout=60)
        # Two gets: first creates file, second populates cache
        mgr.get('test')
        mgr.get('test')

        # Directly modify file
        with open('config/test.json', 'w') as f:
            json.dump({'v': 999}, f)

        # Without reload, cache returns old value
        assert mgr.get('test', 'v') == 1

        # After reload, gets new value
        mgr.reload('test')
        assert mgr.get('test', 'v') == 999


class TestConfigManagerCache:
    def test_cache_returns_cached_value(self, mgr):
        mgr.register('test', 'config/test.json', format='json', default={'v': 1}, cache_timeout=60)
        # First get creates the file from default
        mgr.get('test')
        # Second get reads the file and populates cache
        mgr.get('test')

        # Modify file behind the cache
        with open('config/test.json', 'w') as f:
            json.dump({'v': 999}, f)

        # Should still return cached value (cache_timeout=60)
        assert mgr.get('test', 'v') == 1

    def test_cache_expires(self, mgr):
        mgr.register('test', 'config/test.json', format='json', default={'v': 1}, cache_timeout=0.01)
        # First get creates the file, second populates cache
        mgr.get('test')
        mgr.get('test')

        with open('config/test.json', 'w') as f:
            json.dump({'v': 999}, f)

        time.sleep(0.02)  # Wait for cache to expire
        assert mgr.get('test', 'v') == 999


class TestConfigManagerThreadSafety:
    def test_concurrent_get_set(self, mgr):
        mgr.register('test', 'config/test.json', format='json', default={'count': 0})
        errors = []

        def writer():
            try:
                for i in range(50):
                    mgr.set('test', 'count', i)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(50):
                    val = mgr.get('test', 'count')
                    assert isinstance(val, int)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestConfigManagerEdgeCases:
    def test_json_corruption_returns_default(self, mgr):
        mgr.register('test', 'config/test.json', format='json', default={'safe': True})

        # Write corrupt JSON
        with open('config/test.json', 'w') as f:
            f.write('{invalid json!!!}')

        mgr.reload('test')
        result = mgr.get('test')
        assert result == {'safe': True}

    def test_unregistered_config_raises(self, mgr):
        with pytest.raises(KeyError):
            mgr.get('nonexistent')
