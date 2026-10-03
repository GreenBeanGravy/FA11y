"""The settings editor's schema and the requests that edit it, with and without a window."""
from unittest.mock import Mock

import pytest

from lib import config_schema as schema
from lib.app import state
from lib.shell.handlers import settings as handlers
from lib.utilities import input as keys
from lib.utilities import utilities


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    path = tmp_path / "config.txt"
    monkeypatch.setattr(utilities, "CONFIG_FILE", str(path))
    utilities.clear_config_cache()
    monkeypatch.setattr(handlers, "_schedule_reload", Mock())
    yield path
    utilities.clear_config_cache()


def stored(section, key):
    parser = utilities.read_config(use_cache=False)
    return parser.get(section, key)


def flat(tab):
    return [(group["heading"], setting["key"]) for group in tab["groups"] for setting in group["settings"]]


def test_schema_has_the_tabs_of_each_view(temp_config):
    settings = handlers.settings_schema({"view": "settings"})
    assert [tab["name"] for tab in settings["tabs"]] == ["General", "Toggles", "Values", "Audio", "GameObjects", "Advanced"]
    keybinds = handlers.settings_schema({"view": "keybinds"})
    assert [tab["name"] for tab in keybinds["tabs"]] == ["Keybinds"]
    with pytest.raises(ValueError):
        handlers.settings_schema({"view": "nope"})


def test_schema_is_json_and_keys_are_unique(temp_config):
    import json
    for view in ("settings", "keybinds"):
        data = handlers.settings_schema({"view": view})
        json.dumps(data)
        ids = [s["id"] for tab in data["tabs"] for g in tab["groups"] for s in g["settings"]]
        assert len(ids) == len(set(ids))


def test_general_tab(temp_config):
    tab = handlers.settings_schema({"view": "settings"})["tabs"][0]
    assert [g["heading"] for g in tab["groups"]] == ["Startup and updates", "FA11y window"]
    window = {s["key"]: s for s in tab["groups"][1]["settings"]}
    assert window["CloseAction"]["kind"] == "choice"
    assert window["CloseAction"]["label"] == "When I close the FA11y window"
    assert window["CloseAction"]["section"] == "Hub"
    assert [c["value"] for c in window["CloseAction"]["choices"]] == ["ask", "tray", "quit"]
    assert window["CloseAction"]["default"] == "ask"
    assert window["NavigationSounds"]["kind"] == "toggle"
    assert window["NavigationSounds"]["label"] == "Play navigation sounds in the FA11y window"


def test_setting_kinds_ranges_and_defaults(temp_config):
    tabs = {t["name"]: t for t in handlers.settings_schema({"view": "settings"})["tabs"]}
    by_key = {s["key"]: s for t in tabs.values() for g in t["groups"] for s in g["settings"]}
    master = by_key["MasterVolume"]
    assert (master["kind"], master["value"], master["min"], master["max"]) == ("volume", 100, 0, 100)
    assert master["default"] == 100
    delay = by_key["RecenterDelay"]
    assert delay["kind"] == "number" and delay["decimals"] == 2 and delay["step"] == 0.01
    assert delay["default"] == 0.01
    assert by_key["RecenterDelay"]["section"] == "Values"
    dpi = by_key["MousePassthroughDPI"]
    assert dpi["kind"] == "number" and dpi["decimals"] == 0 and dpi["min"] == 100
    assert by_key["AnnounceDeath"]["section"] == "MatchEvents"
    assert tabs["Toggles"]["groups"][2]["heading"] == "Match events"
    # Per-map object settings come with the map picker and are fetched per map.
    objects = tabs["GameObjects"]
    assert objects["maps"][0]["key"] == "main"
    main = handlers.settings_map({"map": "main"})
    assert main["groups"][0]["settings"][0]["section"] == "MainGameObjects"
    assert not main["groups"][0]["settings"][0]["show_description"]
    with pytest.raises(ValueError):
        handlers.settings_map({"map": "no such map"})


def test_keybinds_tab_groups(temp_config):
    tab = handlers.settings_schema({"view": "keybinds"})["tabs"][0]
    assert [g["heading"] for g in tab["groups"]][:2] == ["FA11y", "Mouse and camera"]
    fire = next(s for g in tab["groups"] for s in g["settings"] if s["key"] == "Fire")
    assert fire["kind"] == "keybind" and fire["value"] == "lctrl" and fire["display"] == "Left Control"
    assert not fire["show_description"] and fire["description"]


def test_search_index(temp_config):
    entries = handlers.search_index({"view": "settings"})["entries"]
    texts = {e["id"]: e["text"] for e in entries}
    assert texts["Toggles/AnnounceAmmo"] == "Announce ammo, Toggles"
    assert texts["MatchEvents/AnnounceDeath"] == "Announce death, Toggles"
    assert any(e["map"] == "main" and e["tab"] == "GameObjects (Main)" and e["tab_name"] == "GameObjects"
               for e in entries)
    assert not any(e["id"].startswith("Keybinds/") for e in entries)
    keybind_entries = handlers.search_index({"view": "keybinds"})["entries"]
    assert any(e["text"] == "Fire, Keybinds" for e in keybind_entries)


def test_set_keeps_description_and_formats(temp_config):
    description = schema.extract_value_and_description(stored("Toggles", "AnnounceAmmo"))[1]
    assert handlers.settings_set({"section": "Toggles", "key": "AnnounceAmmo", "kind": "toggle", "value": False}) \
        == {"value": False}
    assert stored("Toggles", "AnnounceAmmo") == f'false "{description}"'

    assert handlers.settings_set({"section": "Values", "key": "RecenterDelay", "kind": "number", "value": 0.05}) \
        == {"value": 0.05}
    assert stored("Values", "RecenterDelay").startswith('0.05 "')
    assert handlers.settings_set({"section": "Values", "key": "TurnSteps", "kind": "number", "value": 7.0}) \
        == {"value": 7}
    assert stored("Values", "TurnSteps").startswith('7 "')
    # Out of range values are held to the range.
    assert handlers.settings_set({"section": "Values", "key": "TurnSteps", "kind": "number", "value": -5})["value"] == 1

    assert handlers.settings_set({"section": "Audio", "key": "MasterVolume", "kind": "volume", "value": 70}) \
        == {"value": 70}
    assert stored("Audio", "MasterVolume").startswith('0.7 "')

    handlers.settings_set({"section": "Hub", "key": "CloseAction", "kind": "choice", "value": "quit"})
    assert stored("Hub", "CloseAction").startswith('quit "')
    with pytest.raises(ValueError):
        handlers.settings_set({"section": "Hub", "key": "CloseAction", "kind": "choice", "value": "explode"})
    with pytest.raises(ValueError):
        handlers.settings_set({"section": "Toggles", "key": "NoSuchKey", "kind": "toggle", "value": True})
    handlers._schedule_reload.assert_called()


def test_reset_to_default(temp_config):
    handlers.settings_set({"section": "Values", "key": "TurnSteps", "kind": "number", "value": 9})
    result = handlers.settings_reset({"section": "Values", "key": "TurnSteps", "kind": "number",
                                      "label": "Turn steps"})
    assert result == {"changed": True, "value": 5, "message": "Turn steps reset to default: 5"}
    assert stored("Values", "TurnSteps").startswith('5 "')

    handlers.settings_set({"section": "Toggles", "key": "AnnounceAmmo", "kind": "toggle", "value": False})
    result = handlers.settings_reset({"section": "Toggles", "key": "AnnounceAmmo", "kind": "toggle",
                                      "label": "Announce ammo"})
    assert result["message"] == "Announce ammo reset to default: checked"

    handlers.settings_set({"section": "Audio", "key": "StormVolume", "kind": "volume", "value": 10})
    result = handlers.settings_reset({"section": "Audio", "key": "StormVolume", "kind": "volume",
                                      "label": "Storm volume"})
    assert result["value"] == 50 and result["message"] == "Storm volume reset to default: 50%"

    handlers.settings_set({"section": "Hub", "key": "CloseAction", "kind": "choice", "value": "quit"})
    result = handlers.settings_reset({"section": "Hub", "key": "CloseAction", "kind": "choice", "label": "Closing"})
    assert result["message"] == "Closing reset to default: Ask me"

    # Per-map settings can be reset too.
    handlers.settings_set({"section": "MainGameObjects", "key": "ChestsVisitDistance", "kind": "number",
                           "value": 30})
    result = handlers.settings_reset({"section": "MainGameObjects", "key": "ChestsVisitDistance", "kind": "number",
                                      "label": "Visit distance (meters)"})
    assert result["value"] == 5


def test_bind_swaps_with_the_action_that_has_the_key(temp_config):
    result = handlers.keybinds_bind({"action": "Fire", "combo": "rctrl"})
    assert result["ok"]
    assert result["message"] == ("Right Control was used by Target. "
                                 "Swapped: Target is now Left Control.")
    values = {c["action"]: c["value"] for c in result["changes"]}
    assert values == {"Fire": "rctrl", "Target": "lctrl"}
    assert stored("Keybinds", "Fire").startswith('rctrl "')
    assert stored("Keybinds", "Target").startswith('lctrl "')


def test_bind_to_a_free_key_and_unbound_swap(temp_config):
    result = handlers.keybinds_bind({"action": "Fire", "combo": "lalt+f9"})
    assert result["message"] == "Fire set to Left Alt + F9"
    handlers.keybinds_clear({"action": "Target"})
    # Target has no key now, so whoever takes Fire's key leaves Fire's holder unbound.
    result = handlers.keybinds_bind({"action": "Target", "combo": "lalt+f9"})
    assert result["message"] == "Left Alt + F9 was used by Fire. Swapped: Fire is now unbound."
    assert stored("Keybinds", "Fire").startswith(' "') or stored("Keybinds", "Fire").startswith('"')


def test_bind_from_raw_keys_and_invalid_keys(temp_config):
    f = 0x7A  # F11
    result = handlers.keybinds_bind({"action": "Recenter", "vk": f,
                                     "modifiers": [keys.MODIFIER_KEYS["lshift"], keys.MODIFIER_KEYS["lalt"]]})
    assert result["message"] == "Recenter set to Left Alt + Left Shift + F11"
    assert stored("Keybinds", "Recenter").startswith('lalt+lshift+f11 "')
    result = handlers.keybinds_bind({"action": "Recenter", "vk": 0x0D})  # Enter is reserved
    assert result == {"ok": False, "message": "That key can't be used.", "changes": []}
    assert handlers.keybinds_bind({"action": "Recenter", "vk": 0x10})["ok"] is False  # Shift alone
    assert stored("Keybinds", "Recenter").startswith('lalt+lshift+f11 "')
    with pytest.raises(ValueError):
        handlers.keybinds_bind({"action": "No such action", "combo": "f"})


def test_clear_and_reset_a_keybind(temp_config):
    result = handlers.keybinds_clear({"action": "Fire"})
    assert result["message"] == "Fire unbound"
    assert result["changes"] == [{"action": "Fire", "value": "", "display": "Unbound"}]
    assert not stored("Keybinds", "Fire").startswith("lctrl")
    result = handlers.settings_reset({"section": "Keybinds", "key": "Fire", "kind": "keybind", "label": "Fire"})
    assert result["message"] == "Fire reset to default: Left Control"
    assert stored("Keybinds", "Fire").startswith('lctrl "')
    handlers.keybinds_bind({"action": "Target", "combo": "lctrl"})
    result = handlers.settings_reset({"section": "Keybinds", "key": "Fire", "kind": "keybind", "label": "Fire"})
    assert "was used by Target" in result["message"]


def test_capture_switches_the_key_listener_off(temp_config):
    handlers.keybinds_capture({"active": True})
    assert state.key_capture_active.is_set()
    handlers.keybinds_capture({"active": False})
    assert not state.key_capture_active.is_set()


def test_combination_from_keys():
    lshift, ralt = keys.MODIFIER_KEYS["lshift"], keys.MODIFIER_KEYS["ralt"]
    assert keys.combination_from_keys(ord("A"), []) == "a"
    assert keys.combination_from_keys(ord("5"), [ralt, lshift]) == "lshift+ralt+5"
    assert keys.combination_from_keys(0x65, []) == "num 5"
    assert keys.combination_from_keys(0xC0, []) == "grave"
    assert keys.combination_from_keys(0xA2, [lshift]) == "lshift+lctrl"
    assert keys.combination_from_keys(0x70, []) == "f1"
    assert keys.combination_from_keys(keys.MODIFIER_KEYS["lshift"], []) == ""
    assert keys.combination_from_keys(0xFF, []) == ""


def test_keybind_table_matches_the_old_swap_rules():
    table = schema.KeybindTable({"Fire": "lctrl", "Target": "rctrl", "Spare": ""})
    note, changed = table.bind("Spare", "rctrl")
    assert note == "Right Control was used by Target. Swapped: Target is now unbound."
    assert changed == {"Target": "", "Spare": "rctrl"}
    note, changed = table.bind("Spare", "rctrl")
    assert (note, changed) == ("", {})
    assert table.clear("Fire") == {"Fire": ""}
    assert table.clear("Fire") == {}


# Labels and groups -----------------------------------------------------------------------

def test_setting_labels():
    assert schema.setting_label("AnnounceKillFeed") == "Announce kill feed"
    assert schema.setting_label("MousePassthroughDPI") == "Mouse DPI"
    assert schema.setting_label("StormPingInterval") == "Storm ping interval"
    assert schema.setting_label("Turn Left") == "Turn Left"
    assert schema.setting_label("ChestsVisitDistance", "MainGameObjects") == "Visit distance (meters)"
    assert schema.setting_label("NotifyWhenReady") == "Show a notification when FA11y is ready"
