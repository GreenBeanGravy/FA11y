"""Requests for the Settings and Keybinds pages.

The editor is described by lib/config_schema.py; these handlers send that
description to the window and save what the user changes. A change is saved
to config.txt at once, then the rest of FA11y picks it up (key bindings,
navigation sounds), the way the wx editor's update callback does when it saves.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from lib import config_schema as schema
from lib.shell.bridge import handler

logger = logging.getLogger(__name__)

VIEWS = ("settings", "keybinds")
KINDS = ("toggle", "number", "text", "choice", "volume")
# The window's kinds as config_schema names them.
SCHEMA_KINDS = {"toggle": "check", "number": "value", "text": "value", "choice": "choice", "volume": "volume"}
CAPTURE_TIMEOUT = 30.0

_lock = threading.RLock()
_maps: Optional[Dict[str, Any]] = None
_tester = schema.VolumeTester()
_reload_lock = threading.Lock()
_reload_pending = False
_capture_timer: Optional[threading.Timer] = None


def _view(params: dict) -> str:
    view = params.get("view", "settings")
    if view not in VIEWS:
        raise ValueError("Unknown view.")
    return view


def _maps_with_objects() -> Dict[str, Any]:
    """The maps that have game object settings. Read from disk once; the map files don't change while FA11y runs."""
    global _maps
    if _maps is None:
        from lib.utilities.utilities import get_maps_with_game_objects
        _maps = get_maps_with_game_objects()
    return _maps


def _read():
    from lib.utilities.utilities import read_config
    return read_config(use_cache=False)


def _save(parser) -> None:
    """Write the config, then let FA11y pick the change up (off this request's thread)."""
    from lib.utilities.utilities import save_config
    if not save_config(parser):
        raise RuntimeError("Could not save the configuration.")
    _schedule_reload(parser)


def _schedule_reload(parser) -> None:
    """Reload FA11y's config and the sounds setting; several quick changes share one reload."""
    global _reload_pending
    from lib.utilities.utilities import get_config_boolean
    with _reload_lock:
        already = _reload_pending
        _reload_pending = True
    if already:
        return

    def work() -> None:
        global _reload_pending
        with _reload_lock:
            _reload_pending = False
        try:
            from lib.hub import get_hub, sounds
            hub = get_hub()
            if hub is not None:
                hub.services.reload_config()
                keybinds_edited = getattr(hub, "keybinds_edited", None)
                if keybinds_edited is not None:
                    keybinds_edited()
            sounds.set_enabled(get_config_boolean(_read(), "NavigationSounds", True))
        except Exception:
            logger.exception("Applying the saved settings failed")

    threading.Thread(target=work, name="ApplySettings", daemon=True).start()


# Reading ------------------------------------------------------------------------------

@handler("settings.schema")
def settings_schema(params: dict) -> dict:
    """Every tab of the editor with its groups and settings, for view 'settings' or 'keybinds'."""
    view = _view(params)
    return schema.build_schema(_read(), view, _maps_with_objects())


@handler("settings.map")
def settings_map(params: dict) -> dict:
    """The object settings of one map, for the GameObjects tab's map picker."""
    name = str(params.get("map", ""))
    if name not in _maps_with_objects():
        raise ValueError("Unknown map.")
    return schema.build_map(_read(), name)


@handler("settings.search_index")
def search_index(params: dict) -> dict:
    """Every setting of a view as 'label, tab', for Ctrl+F."""
    view = _view(params)
    return {"entries": schema.search_entries(_read(), view, _maps_with_objects())}


# Changing settings ------------------------------------------------------------------------

def _stored_value(kind: str, key: str, value: Any, current: str):
    """(text to store, value the control should show) for a value the user entered."""
    if kind == "toggle":
        on = bool(value)
        return ("true" if on else "false"), on
    if kind == "volume":
        percent = max(0, min(int(round(float(value))), 100))
        return str(percent / 100.0), percent
    if kind == "number":
        spec = schema.number_spec(key, current)
        number = float(value)
        if spec is None:
            decimals = 0 if float(number).is_integer() else 3
        else:
            decimals = spec["decimals"]
            number = max(spec["min"], min(number, spec["max"]))
        stored = schema.format_number(number, decimals)
        return stored, (float(stored) if decimals else int(stored))
    if kind == "choice":
        allowed = [stored for stored, _label in schema.CLOSE_ACTION_CHOICES]
        text = str(value).lower()
        if text not in allowed:
            raise ValueError("That isn't one of the choices.")
        return text, text
    text = str(value).replace('"', "'").strip()
    return text, text


@handler("settings.set")
def settings_set(params: dict) -> dict:
    """Save one setting. value is what the control holds: true or false, a number (a percent for
    volumes), a choice's value, or text."""
    section, key, kind = str(params.get("section", "")), str(params.get("key", "")), str(params.get("kind", ""))
    if kind not in KINDS:
        raise ValueError("Unknown kind of setting.")
    with _lock:
        parser = _read()
        if not parser.has_option(section, key):
            raise ValueError("Unknown setting.")
        current, description = schema.extract_value_and_description(parser.get(section, key))
        stored, shown = _stored_value(kind, key, params.get("value"), current)
        parser.set(section, key, schema.stored_string(stored, description))
        _save(parser)
    return {"value": shown}


@handler("settings.reset")
def settings_reset(params: dict) -> dict:
    """Put one setting back to its default. Returns the new value, and the sentence to announce."""
    section, key = str(params.get("section", "")), str(params.get("key", ""))
    kind, label = str(params.get("kind", "")), str(params.get("label", key))
    if kind == "keybind":
        return _reset_keybind(key, label)
    if kind not in KINDS:
        raise ValueError("Unknown kind of setting.")
    default = schema.default_for_section(section, key)
    if default is None:
        return {"changed": False, "message": ""}
    choices = schema.CLOSE_ACTION_CHOICES if kind == "choice" else ()
    schema_kind = SCHEMA_KINDS[kind]
    value = schema.default_ui_value(schema_kind, key, default, choices)
    if value is None:
        return {"changed": False, "message": ""}
    with _lock:
        parser = _read()
        if not parser.has_option(section, key):
            raise ValueError("Unknown setting.")
        current, description = schema.extract_value_and_description(parser.get(section, key))
        stored, shown = _stored_value(kind, key, value, current)
        parser.set(section, key, schema.stored_string(stored, description))
        _save(parser)
    return {"changed": True, "value": shown, "message": schema.reset_message(label, schema_kind, value, choices)}


@handler("settings.test_volume")
def test_volume(params: dict) -> dict:
    """Play the sound for a volume setting at the percent the user has set."""
    key = str(params.get("key", ""))
    try:
        volume = float(params.get("value", 100)) / 100.0
    except (TypeError, ValueError):
        return {}
    master = 1.0
    try:
        text = _read().get("Audio", "MasterVolume", fallback="1.0")
        master = float(schema.extract_value_and_description(text)[0])
    except (TypeError, ValueError):
        master = 1.0
    _tester.play(key, volume, master)
    return {}


@handler("settings.leave")
def settings_leave(_params: dict) -> dict:
    """The page was hidden: let go of the test sounds."""
    _tester.cleanup()
    return {}


# Keybinds -----------------------------------------------------------------------------------

def _keybind_result(parser, action: str, message: str, changed: Dict[str, str]) -> dict:
    """The answer to a bind or clear: what to show on each button that changed."""
    table = schema.KeybindTable.from_parser(parser)
    changes = []
    for name, combo in {action: table.values.get(action, ""), **changed}.items():
        changes.append({"action": name, "value": combo, "display": schema.key_name(combo) if combo else "Unbound"})
    return {"ok": True, "message": message, "changes": changes}


def _write_keybinds(parser, changed: Dict[str, str]) -> None:
    for name, combo in changed.items():
        _current, description = schema.extract_value_and_description(parser.get("Keybinds", name))
        parser.set("Keybinds", name, schema.stored_string(combo, description))


@handler("keybinds.bind")
def keybinds_bind(params: dict) -> dict:
    """Bind a key to an action, swapping with whichever action has it. The key is either a stored
    combination ('combo') or the raw key press the window saw: vk, the main key's virtual key code,
    and modifiers, the virtual key codes of the Shift and Alt keys held."""
    from lib.utilities.input import combination_from_keys, validate_key_combination
    action = str(params.get("action", ""))
    combo = str(params.get("combo") or "")
    if not combo and params.get("vk") is not None:
        combo = combination_from_keys(int(params["vk"]), params.get("modifiers") or [])
    with _lock:
        parser = _read()
        if not parser.has_option("Keybinds", action):
            raise ValueError("Unknown action.")
        if not combo or not validate_key_combination(combo):
            return {"ok": False, "message": schema.CANT_USE_KEY, "changes": []}
        table = schema.KeybindTable.from_parser(parser)
        note, changed = table.bind(action, combo)
        changed = {action: combo, **changed}
        _write_keybinds(parser, changed)
        _save(parser)
    return _keybind_result(parser, action, schema.bind_message(action, combo, note), changed)


@handler("keybinds.clear")
def keybinds_clear(params: dict) -> dict:
    """Unbind an action."""
    action = str(params.get("action", ""))
    with _lock:
        parser = _read()
        if not parser.has_option("Keybinds", action):
            raise ValueError("Unknown action.")
        changed = schema.KeybindTable.from_parser(parser).clear(action)
        if changed:
            _write_keybinds(parser, changed)
            _save(parser)
    return _keybind_result(parser, action, f"{action} unbound", changed)


def _reset_keybind(action: str, label: str) -> dict:
    """Reset a keybind to its default, swapping like a new binding does."""
    default = (schema.default_for_section("Keybinds", action) or "").strip()
    with _lock:
        parser = _read()
        if not parser.has_option("Keybinds", action):
            raise ValueError("Unknown action.")
        table = schema.KeybindTable.from_parser(parser)
        if default:
            note, changed = table.bind(action, default)
            changed = {action: default, **changed}
            message = note or schema.reset_message(action, "keybind", default, key_name=schema.key_name(default))
        else:
            changed = table.clear(action)
            message = schema.reset_message(label, "keybind", "")
        if changed:
            _write_keybinds(parser, changed)
            _save(parser)
    result = _keybind_result(parser, action, message, changed)
    result["changed"] = True
    return result


@handler("keybinds.capture")
def keybinds_capture(params: dict) -> dict:
    """The window is (or is no longer) waiting for a key press to bind. While it is, FA11y's own
    keybinds stay quiet so the key being pressed isn't also an action. It ends by itself after
    CAPTURE_TIMEOUT seconds in case the window goes away mid-capture."""
    global _capture_timer
    from lib.app import state
    with _lock:
        if _capture_timer is not None:
            _capture_timer.cancel()
            _capture_timer = None
        if params.get("active"):
            state.key_capture_active.set()
            _capture_timer = threading.Timer(CAPTURE_TIMEOUT, state.key_capture_active.clear)
            _capture_timer.daemon = True
            _capture_timer.start()
        else:
            state.key_capture_active.clear()
    return {}
