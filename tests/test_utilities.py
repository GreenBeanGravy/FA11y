"""Tests for lib/utilities/utilities.py and lib/utilities/input.py"""
import os
import sys
import configparser
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.utilities.utilities import (
    get_default_config, get_config_value, get_config_boolean,
    get_default_config_value_string
)
from lib.utilities.input import parse_key_combination

# is_valid_key_or_combination lives in FA11y.py, import it from there
# But FA11y.py has heavy side effects on import, so we test key validation
# through parse_key_combination instead
def is_valid_key_or_combination(key_combo):
    """Lightweight validation: try parsing, return True if no error."""
    if not key_combo:
        return False
    try:
        mods, key = parse_key_combination(str(key_combo))
        return bool(key)
    except Exception:
        return False


class TestParseKeyCombination:
    def test_simple_key(self):
        mods, key = parse_key_combination("a")
        assert key == "a"
        assert mods == []

    def test_single_modifier(self):
        mods, key = parse_key_combination("lshift+a")
        assert "lshift" in mods
        assert key == "a"

    def test_multi_modifier(self):
        # lalt is a valid modifier; lctrl is treated as a regular key in FA11y
        mods, key = parse_key_combination("lalt+lshift+f")
        assert "lalt" in mods
        assert "lshift" in mods
        assert key == "f"

    def test_numpad_key(self):
        mods, key = parse_key_combination("num 1")
        assert key == "num 1"
        assert mods == []


class TestValidateKey:
    def test_valid_keys(self):
        for key in ["a", "f8", "f9", "f12", "lctrl", "lshift+a", "lalt+p"]:
            assert is_valid_key_or_combination(key), f"Expected valid: {key}"

    def test_empty_key_invalid(self):
        assert not is_valid_key_or_combination("")
        assert not is_valid_key_or_combination(None)


class TestGetConfigBoolean:
    def _make_config(self, key, value):
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read_string(f"[Toggles]\n{key} = {value}")
        return config

    def test_true_variants(self):
        for val in ["true", "True", "TRUE"]:
            config = self._make_config("Test", f'{val} "desc"')
            assert get_config_boolean(config, "Test", False) is True

    def test_false_variants(self):
        for val in ["false", "False", "FALSE"]:
            config = self._make_config("Test", f'{val} "desc"')
            assert get_config_boolean(config, "Test", True) is False

    def test_missing_key_returns_default(self):
        config = self._make_config("Other", 'true "desc"')
        assert get_config_boolean(config, "Missing", True) is True
        assert get_config_boolean(config, "Missing", False) is False


class TestGetConfigValue:
    def _make_config(self, key, value_str):
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read_string(f"[Toggles]\n{key} = {value_str}")
        return config

    def test_value_with_description(self):
        config = self._make_config("Test", 'myvalue "This is the description"')
        value, desc = get_config_value(config, "Test")
        assert value == "myvalue"
        assert desc == "This is the description"


class TestDefaultConfig:
    def test_has_all_sections(self):
        config_str = get_default_config()
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read_string(config_str)
        required = ['Toggles', 'Values', 'Audio', 'GameObjects', 'Keybinds', 'POI']
        for section in required:
            assert section in config.sections(), f"Missing section: {section}"

    def test_has_mouse_passthrough_toggle(self):
        config_str = get_default_config()
        assert "MousePassthrough" in config_str

    def test_has_recapture_keybind(self):
        config_str = get_default_config()
        assert "Recapture Mouse" in config_str

    def test_has_toggle_passthrough_keybind(self):
        config_str = get_default_config()
        assert "Toggle Mouse Passthrough" in config_str


def test_open_fa11y_moves_off_left_alt_f(tmp_path, monkeypatch):
    from lib.utilities import utilities
    (tmp_path / "config").mkdir()
    cfg = tmp_path / "config" / "config.txt"
    cfg.write_text('[Keybinds]\nOpen FA11y = lalt+f "Opens."\nToggle POI Favorite = lalt+lshift+f "Favorite."\n',
                   encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    utilities._migrate_open_fa11y_keybind()
    assert cfg.read_text(encoding="utf-8") == (
        '[Keybinds]\nOpen FA11y = lalt+lshift+f "Opens."\nToggle POI Favorite = lalt+lshift+b "Favorite."\n')
    utilities._migrate_open_fa11y_keybind()  # nothing left to move
    assert "Open FA11y = lalt+lshift+f" in cfg.read_text(encoding="utf-8")


def test_open_fa11y_keeps_a_custom_keybind(tmp_path, monkeypatch):
    from lib.utilities import utilities
    (tmp_path / "config").mkdir()
    cfg = tmp_path / "config" / "config.txt"
    text = '[Keybinds]\nOpen FA11y = lalt+f "Opens."\nToggle POI Favorite = lalt+k "Favorite."\n'
    cfg.write_text(text, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    utilities._migrate_open_fa11y_keybind()
    assert cfg.read_text(encoding="utf-8") == text
