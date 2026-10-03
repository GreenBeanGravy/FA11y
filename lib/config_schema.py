"""What the settings editor shows, with no window code.

The WPF window reads this through lib/shell/handlers/settings.py: which tab and group each
config key appears in, its label, what kind of control it gets, its range
and default, how a keybind swap works, and how a value is stored back.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Tabs -------------------------------------------------------------------------

# Every tab the editor knows, in display order.
ALL_TABS = ("General", "Toggles", "Values", "Audio", "GameObjects", "Keybinds", "Advanced")
SETTINGS_TABS = ["General", "Toggles", "Values", "Audio", "GameObjects", "Advanced"]
KEYBINDS_TABS = ["Keybinds"]

# Keys routed to the "Advanced" tab regardless of source section.
ADVANCED_KEYS = frozenset({
    "SimplifySpeechOutput",
    "IgnoreNumlock",
    "ResetSensitivity",
    "TurnAroundSensitivity",
    "RecenterDelay",
    "TurnDelay",
    "RecenterStepDelay",
    "RecenterStepSpeed",
    "RecenterLookDown",
    "RecenterLookUp",
    "ResetRecenterLookDown",
    "ResetRecenterLookUp",
    "StormPingInterval",
    "ContinuousPingMinInterval",
    "ContinuousPingMaxInterval",
    "ContinuousPingDistanceExponent",
    "PositionUpdateInterval",
    "MaxInstancesForGameObjectPositioning",
    # Onboarding wizard re-run toggle.
    "FirstRunComplete",
})

# Settings shown on the "General" tab, with the config section each one is
# saved back to. They're removed from their natural tabs while General is shown.
GENERAL_TOGGLE_KEYS = (
    "StartFortniteOnLaunch",
    "HideHubWhenFortniteStarts",
    "NavigationSounds",
    "MinimizeToTray",
    "NotifyWhenReady",
    "NotifyWhenHiddenToTray",
    "AutoUpdates",
    "CreateDesktopShortcut",
)
GENERAL_KEY_SECTIONS = {key: "Toggles" for key in GENERAL_TOGGLE_KEYS}
GENERAL_KEY_SECTIONS["CloseAction"] = "Hub"

CLOSE_ACTION_LABEL = "When I close the FA11y window"
# (config value, label shown to the user)
CLOSE_ACTION_CHOICES = (
    ("ask", "Ask me"),
    ("tray", "Keep running in the tray"),
    ("quit", "Quit FA11y"),
)

# Config sections whose settings appear on another tab. Their widgets are
# tracked under the section's own name so they save back to it.
TRACKED_ELSEWHERE = {"MatchEvents": "Toggles"}

# Labels and groups -------------------------------------------------------------

# Labels that the automatic CamelCase split gets wrong or could say better.
LABEL_OVERRIDES: Dict[str, str] = {
    "StartFortniteOnLaunch": "Start Fortnite when FA11y opens",
    "HideHubWhenFortniteStarts": "Hide the FA11y window when Fortnite starts",
    "NavigationSounds": "Play navigation sounds in the FA11y window",
    "MinimizeToTray": "Minimize to the system tray",
    "NotifyWhenReady": "Show a notification when FA11y is ready",
    "NotifyWhenHiddenToTray": "Show a notification when the window goes to the tray",
    "AutoUpdates": "Update FA11y automatically",
    "CreateDesktopShortcut": "Create a desktop shortcut",
    "MouseKeys": "Mouse keys (look around, click, and aim with the keyboard)",
    "UseFA11yOWPosition": "Use FA11y-OW for player position",
    "AnnounceUITabs": "Announce lobby tabs",
    "AnnounceSidebarStatus": "Announce sidebar and pause menu",
    "AnnounceMapStatus": "Announce map opening and closing",
    "AnnounceInventoryStatus": "Announce inventory opening and closing",
    "QuestAnnouncements": "Announce quest progress",
    "PlayPOISound": "Play POI direction sound",
    "MonitorDynamicObjects": "Play sounds for dynamic objects",
    "MonitorStorm": "Play storm sounds",
    "MonitorBloom": "Play crosshair bloom sounds",
    "PingVolumeMaxDistance": "Ping volume distance limit",
    "MinimumPOIVolume": "Minimum POI volume",
    "MaximumPOIVolume": "Maximum POI volume",
    "MousePassthroughDPI": "Mouse DPI",
    "IgnoreNumlock": "Ignore Num Lock",
    "SimplifySpeechOutput": "Simplify speech",
    "FirstRunComplete": "First-run setup is complete",
    "MaxInstancesForGameObjectPositioning": "Most instances used for object positioning",
    "MonitorMatchEvents": "Announce match events",
    "AnnounceReloadKnocked": "Announce being knocked in Reload",
    "AnnounceReloadRespawn": "Announce Reload respawns",
    "AnnounceFinalCountdown": "Announce final countdown",
}

# Words kept in capitals (or their own spelling) when splitting CamelCase.
_KEEP_CASE = {"POI", "UI", "DPI", "OW", "FA11y", "GEP", "OG", "API"}
_WORD = re.compile(r"FA11y|[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|[A-Z]+|\d+")

# Per-map object settings: TrackVisitsChests, ChestsVisitDistance, AnnounceChestsVisits.
_OBJECT_PATTERNS = (
    (re.compile(r"^TrackVisits(?P<object>\w+)$"), "Track visits"),
    (re.compile(r"^(?P<object>\w+)VisitDistance$"), "Visit distance (meters)"),
    (re.compile(r"^Announce(?P<object>\w+)Visits$"), "Announce visits"),
)


def split_words(key: str) -> str:
    """'AnnounceInventoryStatus' -> 'Announce inventory status'."""
    words = _WORD.findall(key.replace("_", " ")) or [key]
    out = []
    for index, word in enumerate(words):
        if word in _KEEP_CASE or (word.isupper() and len(word) > 1):
            out.append(word)
        elif index == 0:
            out.append(word[:1].upper() + word[1:].lower())
        else:
            out.append(word.lower())
    return " ".join(out)


def object_setting(key: str) -> Optional[Tuple[str, str]]:
    """(object name, setting label) for a per-map object key, else None."""
    for pattern, label in _OBJECT_PATTERNS:
        match = pattern.match(key)
        if match:
            return split_words(match.group("object")), label
    return None


def is_per_map_tab(tab: str) -> bool:
    """True for the tracking names of per-map sections ('MainGameObjects')."""
    return tab.endswith("GameObjects") and tab != "GameObjects"


def setting_label(key: str, tab: str = "") -> str:
    """What the user sees and hears for a config key."""
    if key in LABEL_OVERRIDES:
        return LABEL_OVERRIDES[key]
    if " " in key:  # keybind actions are already words
        return key
    if is_per_map_tab(tab):
        parts = object_setting(key)
        if parts:
            return parts[1]
    return split_words(key)


# Group headings for each tab, in display order, with the keys each holds.
# Keys not listed land in the tab's last group (OTHER).
OTHER = "Other"
GROUPS: Dict[str, Tuple[Tuple[str, Tuple[str, ...]], ...]] = {
    "General": (
        ("Startup and updates", ("StartFortniteOnLaunch", "AutoUpdates", "CreateDesktopShortcut")),
        ("FA11y window", ("HideHubWhenFortniteStarts", "MinimizeToTray", "NavigationSounds", "NotifyWhenReady",
                         "NotifyWhenHiddenToTray", "CloseAction")),
    ),
    "Toggles": (
        ("Mouse and movement", ("MouseKeys", "MousePassthrough", "AutoTurn")),
        ("Announcements", ("AnnounceAmmo", "AnnounceItemEquip", "AnnounceItemPickup", "AnnounceMapStatus",
                           "AnnounceInventoryStatus", "AnnounceSidebarStatus", "AnnounceUITabs",
                           "AnnounceTeammateEvents", "AnnounceKillFeed", "QuestAnnouncements")),
        ("Match events", ()),
        ("Position", ("UseFA11yOWPosition",)),
    ),
    "MatchEvents": (
        ("Match events", ()),
    ),
    "Values": (
        ("Turning", ("TurnSensitivity", "SecondaryTurnSensitivity", "TurnSteps", "RecenterSteps")),
        ("Mouse", ("ScrollSensitivity", "MousePassthroughDPI")),
    ),
    "Audio": (
        ("Volume", ("MasterVolume", "POIVolume", "StormVolume", "DynamicObjectVolume",
                    "MinimumPOIVolume", "MaximumPOIVolume", "PingVolumeMaxDistance")),
        ("Sounds", ("PlayPOISound", "MonitorStorm", "MonitorDynamicObjects", "MonitorBloom")),
    ),
    "GameObjects": (
        ("All maps", ()),
    ),
    "Advanced": (
        ("Speech", ("SimplifySpeechOutput",)),
        ("Mouse keys", ("IgnoreNumlock", "ResetSensitivity", "TurnAroundSensitivity", "TurnDelay",
                        "RecenterDelay", "RecenterStepDelay", "RecenterStepSpeed", "RecenterLookDown",
                        "RecenterLookUp", "ResetRecenterLookDown", "ResetRecenterLookUp")),
        ("Audio pings", ("StormPingInterval", "ContinuousPingMinInterval", "ContinuousPingMaxInterval",
                         "ContinuousPingDistanceExponent")),
        ("Game objects", ("PositionUpdateInterval", "MaxInstancesForGameObjectPositioning")),
        ("Setup", ("FirstRunComplete",)),
    ),
    "Keybinds": (
        ("FA11y", ("Toggle Keybinds", "Open FA11y", "Open Configuration Menu", "Recapture Mouse",
                   "Toggle Mouse Passthrough", "Calibrate FA11y-OW Position")),
        ("Mouse and camera", ("Fire", "Target", "Turn Left", "Turn Right", "Secondary Turn Left",
                              "Secondary Turn Right", "Look Up", "Look Down", "Turn Around", "Recenter",
                              "Scroll Up", "Scroll Down")),
        ("Navigation and POIs", ("Start Navigation", "Cycle Map", "Cycle Map Backwards", "Cycle POI",
                                 "Cycle POI Backwards", "Cycle POI Category", "Cycle POI Category Backwards",
                                 "Toggle Continuous Ping", "Toggle POI Favorite", "Create Custom P O I",
                                 "Mark Bad Game Object", "Check Hotspots", "Open Visited Objects",
                                 "Announce Direction Faced")),
        ("Player and items", ("Check Health Shields", "Announce Ammo", "Check Rarity", "Detect Hotbar 1",
                              "Detect Hotbar 2", "Detect Hotbar 3", "Detect Hotbar 4", "Detect Hotbar 5",
                              "Get Match Stats", "Check Display Mode")),
        ("Menus and matches", ("Open Quest Browser", "Open Locker Selector", "Open Match Options",
                               "Open Social Menu", "Open Discovery GUI", "Open Authentication",
                               "Accept Notification", "Decline Notification", "Exit Match",
                               "Announce Reload Map Rotation", "Sync Current Map To Reload Rotation")),
    ),
}


def group_for(tab: str, key: str) -> str:
    """The group heading ``key`` appears under on ``tab``."""
    if is_per_map_tab(tab):
        parts = object_setting(key)
        return parts[0] if parts else OTHER
    groups = GROUPS.get(tab)
    if not groups:
        return OTHER
    for heading, keys in groups:
        if key in keys:
            return heading
    if len(groups) == 1:
        return groups[0][0]
    return OTHER


def order_groups(tab: str, headings: Sequence[str]) -> List[str]:
    """``headings`` in the order GROUPS lists them for ``tab`` (unlisted ones last, in the order given)."""
    order = [heading for heading, _keys in GROUPS.get(tab, ())]
    return sorted(headings, key=lambda h: order.index(h) if h in order else len(order))


# Values -------------------------------------------------------------------------

def extract_value_and_description(value_string: str) -> Tuple[str, str]:
    """Split a config string 'value "description"' into its two parts."""
    value_string = value_string.strip()
    if '"' in value_string:
        quote_pos = value_string.find('"')
        value = value_string[:quote_pos].strip()
        description = value_string[quote_pos + 1:]
        if description.endswith('"'):
            description = description[:-1]
        return value, description
    return value_string, ""


def is_bool_value(value: str) -> bool:
    return value.lower() in ("true", "false")


def is_volume_key(key: str) -> bool:
    return key.endswith("Volume") or key == "MasterVolume"


def get_value_range(key: str) -> Tuple[int, int]:
    """Reasonable min and max for a numeric setting."""
    key_lower = key.lower()
    if 'volume' in key_lower:
        return (0, 1000)
    elif 'sensitivity' in key_lower:
        return (1, 50000)
    elif 'delay' in key_lower:
        return (0, 10000)
    elif 'steps' in key_lower:
        return (1, 10000)
    elif 'speed' in key_lower:
        return (0, 10000)
    elif 'distance' in key_lower or 'radius' in key_lower:
        return (1, 10000)
    elif 'dpi' in key_lower:
        return (100, 50000)
    elif 'interval' in key_lower or 'exponent' in key_lower:
        return (0, 100)
    return (-10000, 10000)


def number_spec(key: str, value: str) -> Optional[Dict[str, Any]]:
    """How a number box for ``value`` behaves: value, min, max, step, decimals. None if it isn't a number."""
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    min_val, max_val = get_value_range(key)
    if "." in value:
        digits = min(max(len(value.split(".", 1)[1]), 1), 3)
        return {"value": number, "min": min(min_val, number), "max": max(max_val, number),
                "step": 10 ** -digits, "decimals": digits}
    number = int(number)
    return {"value": number, "min": min(min_val, number), "max": max(max_val, number),
            "step": 1, "decimals": 0}


def volume_percent(value: str) -> int:
    """A stored volume ('0.5') as the percent the editor shows."""
    try:
        return int(float(value) * 100)
    except (ValueError, TypeError):
        return 100


def format_number(number: float, decimals: int) -> str:
    """A number as it is stored in config.txt."""
    if decimals > 0:
        return f"{number:.{decimals}f}"
    return str(int(round(number)))


# Where a setting goes -----------------------------------------------------------

@dataclass(frozen=True)
class Item:
    """One setting on one tab."""
    tab: str            # the tab it is shown on
    tracking: str       # what it is tracked under: group, label and save section come from this
    kind: str           # check, value, volume, keybind or choice
    key: str
    value_string: str   # as stored: value "description"
    choices: Tuple[Tuple[str, str], ...] = ()
    label: str = ""


def _kind_for(key: str, value: str, volumes: bool) -> str:
    if is_bool_value(value):
        return "check"
    if volumes and is_volume_key(key):
        return "volume"
    return "value"


def _resolve(natural_tab: str, key: str) -> str:
    return "Advanced" if key in ADVANCED_KEYS else natural_tab


def route_setting(section: str, key: str, value_string: str,
                  maps: Optional[Dict[str, Any]] = None) -> Optional[Tuple[str, str, str]]:
    """(tab, tracking name, kind) for a key found in config section ``section``, or None when it isn't
    shown in the generic tabs (the layouts of GameObjects and General, per-map sections, other sections).

    The General tab's keys are not handled here; callers skip GENERAL_KEY_SECTIONS while General is shown.
    """
    if section == "POI":
        return None
    value, _ = extract_value_and_description(value_string)
    if section == "Toggles":
        tab = _resolve("Toggles", key)
        return tab, tab, "check"
    if section == "Values":
        tab = _resolve("Values", key)
        return tab, tab, "value"
    if section == "Audio":
        tab = _resolve("Audio", key)
        return tab, tab, _kind_for(key, value, True)
    if section == "GameObjects":
        # The universal keys are laid out with the map picker; only advanced-routed ones are generic.
        tab = _resolve("GameObjects", key)
        if tab == "GameObjects":
            return None
        return tab, tab, _kind_for(key, value, False)
    if section.endswith("GameObjects"):
        return None
    if section in ("Keybinds", "SCRIPT KEYBINDS"):
        return "Keybinds", "Keybinds", "keybind"
    if section == "Setup":
        tab = _resolve("Advanced", key)
        return tab, tab, _kind_for(key, value, False)
    if section == "SETTINGS":
        if is_audio_setting(key):
            tab = _resolve("Audio", key)
            return tab, tab, _kind_for(key, value, True)
        if is_game_objects_setting(key):
            tab = _resolve("GameObjects", key)
            return tab, tab, _kind_for(key, value, False)
        if is_map_specific_game_object_setting(key):
            legacy_target = "MainGameObjects"
            for map_name in (maps or {}).keys():
                if map_name == 'main':
                    legacy_target = f"{map_name.title()}GameObjects"
                    break
            tab = _resolve(legacy_target, key)
            return tab, tab, _kind_for(key, value, False)
        if is_bool_value(value):
            tab = _resolve("Toggles", key)
            return tab, tab, "check"
        tab = _resolve("Values", key)
        return tab, tab, "value"
    if section in TRACKED_ELSEWHERE:
        shown_on = TRACKED_ELSEWHERE[section]
        tab = _resolve(shown_on, key)
        tracking = section if tab == shown_on else tab
        return tab, tracking, "check" if is_bool_value(value) else "value"
    return None


def is_audio_setting(key: str) -> bool:
    from lib.utilities.utilities import is_audio_setting as check
    return check(key)


def is_game_objects_setting(key: str) -> bool:
    from lib.utilities.utilities import is_game_objects_setting as check
    return check(key)


def is_map_specific_game_object_setting(key: str) -> bool:
    from lib.utilities.utilities import is_map_specific_game_object_setting as check
    return check(key)


def general_value_string(parser, key: str) -> str:
    """The stored ``value "description"`` string for a General-tab key."""
    from lib.utilities.utilities import get_default_config_value_string
    section = GENERAL_KEY_SECTIONS[key]
    if parser.has_option(section, key):
        return parser.get(section, key)
    for other in parser.sections():
        if parser.has_option(other, key):
            return parser.get(other, key)
    return get_default_config_value_string(section, key) or ""


def tab_items(parser, tab: str, general_active: bool = True,
              maps: Optional[Dict[str, Any]] = None) -> List[Item]:
    """The settings on ``tab``, in the order they are created (config order).

    The GameObjects tab returns only its universal settings; per-map ones come from map_items().
    """
    if tab == "General":
        items = [Item("General", "General", "check", key, general_value_string(parser, key))
                 for key in GENERAL_TOGGLE_KEYS]
        items.append(Item("General", "General", "choice", "CloseAction",
                          general_value_string(parser, "CloseAction"),
                          choices=CLOSE_ACTION_CHOICES, label=CLOSE_ACTION_LABEL))
        return items
    if tab == "GameObjects":
        items = []
        if parser.has_section("GameObjects"):
            for key in parser["GameObjects"]:
                if key in ADVANCED_KEYS:
                    continue
                value_string = parser["GameObjects"][key]
                value, _ = extract_value_and_description(value_string)
                items.append(Item("GameObjects", "GameObjects", "check" if is_bool_value(value) else "value",
                                  key, value_string))
        return items
    items = []
    for section in parser.sections():
        if section == "POI":
            continue
        for key in parser[section]:
            if general_active and key in GENERAL_KEY_SECTIONS:
                continue
            value_string = parser[section][key]
            route = route_setting(section, key, value_string, maps)
            if route is not None and route[0] == tab:
                items.append(Item(route[0], route[1], route[2], key, value_string))
    return items


def map_items(parser, map_name: str) -> List[Item]:
    """The settings of one map's object section, for the GameObjects tab's map picker."""
    section = f"{map_name.title()}GameObjects"
    items = []
    if not parser.has_section(section):
        return items
    for key in parser[section]:
        if key in ADVANCED_KEYS:
            continue
        value_string = parser[section][key]
        value, _ = extract_value_and_description(value_string)
        items.append(Item("GameObjects", section, "check" if is_bool_value(value) else "value", key, value_string))
    return items


def map_names(maps: Dict[str, Any]) -> List[str]:
    """The maps with object settings, 'main' first."""
    names = sorted(maps.keys()) if maps else []
    if "main" in names:
        names.remove("main")
        names.insert(0, "main")
    return names


def map_display_name(map_name: str) -> str:
    return map_name.replace("_", " ").title()


# Defaults and saving ---------------------------------------------------------------

_default_parser = None


def default_parser():
    """The default config, parsed once."""
    global _default_parser
    if _default_parser is None:
        from lib.utilities.utilities import DEFAULT_CONFIG, _create_config_parser_with_case_preserved
        parser = _create_config_parser_with_case_preserved()
        parser.read_string(DEFAULT_CONFIG)
        _default_parser = parser
    return _default_parser


def default_section_for_key(key: str) -> Optional[str]:
    """The default-config section that owns ``key``."""
    parser = default_parser()
    for section in parser.sections():
        if parser.has_option(section, key):
            return section
    return None


def target_section(parser, tracking: str, key: str) -> Optional[str]:
    """The config section a setting tracked under ``tracking`` is saved to."""
    if tracking == "General":
        section = GENERAL_KEY_SECTIONS.get(key)
        if section and parser.has_option(section, key):
            return section
    if tracking in ("Advanced", "General"):
        # Advanced and General settings save back to their real section.
        for sec in parser.sections():
            if parser.has_option(sec, key):
                return sec
        if tracking == "General":
            return GENERAL_KEY_SECTIONS.get(key)
        return default_section_for_key(key)
    return tracking


def default_value_string(tracking: str, key: str) -> Optional[str]:
    """The default ``value "description"`` for a setting tracked under ``tracking``, or None."""
    section = tracking
    if tracking == "Advanced":
        section = default_section_for_key(key) or tracking
    elif tracking == "General":
        section = GENERAL_KEY_SECTIONS.get(key, tracking)
    parser = default_parser()
    return parser.get(section, key) if parser.has_option(section, key) else None


def default_for_section(section: str, key: str) -> Optional[str]:
    """The default value (no description) of ``key`` in config ``section``, falling back to wherever
    the default config keeps that key. None when there is no default."""
    parser = default_parser()
    if parser.has_option(section, key):
        text = parser.get(section, key)
    else:
        owner = default_section_for_key(key)
        if owner is None:
            return None
        text = parser.get(owner, key)
    return extract_value_and_description(text)[0]


def stored_string(value: str, description: str) -> str:
    """A config line's text: the value, then its description in quotes."""
    return f'{value} "{description}"' if description else str(value)


def default_ui_value(kind: str, key: str, default_part: str, choices=()) -> Any:
    """A default value in the form the editor's control holds it, or None when it can't be shown."""
    if kind == "check":
        return default_part.lower() == "true"
    if kind == "volume":
        return volume_percent(default_part) if default_part.strip() else 100
    if kind == "value":
        spec = number_spec(key, default_part)
        return spec["value"] if spec else default_part
    if kind == "choice":
        values = [stored for stored, _label in choices]
        return default_part.lower() if default_part.lower() in values else None
    if kind == "keybind":
        return default_part.strip()
    return default_part


def reset_message(name: str, kind: str, value: Any, choices=(), key_name: str = "") -> str:
    """The sentence spoken after a setting is reset to its default."""
    if kind == "check":
        return f"{name} reset to default: {'checked' if value else 'unchecked'}"
    if kind == "volume":
        return f"{name} reset to default: {value}%"
    if kind == "choice":
        label = next((shown for stored, shown in choices if stored == value), str(value))
        return f"{name} reset to default: {label}"
    if kind == "keybind":
        return f"{name} reset to default: {key_name or 'unbound'}"
    return f"{name} reset to default: {value}"


# Keybinds ---------------------------------------------------------------------------

def key_name(combo: str) -> str:
    """Friendly name for a stored key combination, e.g. 'lalt+f' -> 'Left Alt + F'."""
    from lib.hub.status import key_display_name
    return key_display_name(combo)


class KeybindTable:
    """The keybinds as conflicts are checked: action -> stored combination, and which action holds which key."""

    def __init__(self, values: Dict[str, str]):
        self.values: Dict[str, str] = {}
        self.key_to_action: Dict[str, str] = {}
        self.action_to_key: Dict[str, str] = {}
        for action, combo in values.items():
            combo = (combo or "").strip()
            self.values[action] = combo
            if combo:
                self.key_to_action[combo.lower()] = action
                self.action_to_key[action] = combo.lower()

    @classmethod
    def from_parser(cls, parser) -> "KeybindTable":
        values = {}
        if parser.has_section("Keybinds"):
            for action in parser["Keybinds"]:
                values[action] = extract_value_and_description(parser["Keybinds"][action])[0]
        return cls(values)

    def clear(self, action: str) -> Dict[str, str]:
        """Unbind ``action``. Returns the combinations that changed (action -> value), empty if it had no key."""
        old_value = self.values.get(action, "")
        old_lower = self.action_to_key.pop(action, "") or old_value.lower()
        if old_lower and self.key_to_action.get(old_lower) == action:
            self.key_to_action.pop(old_lower, None)
        self.values[action] = ""
        return {action: ""} if old_value else {}

    def bind(self, action: str, new_key: str) -> Tuple[str, Dict[str, str]]:
        """Bind ``new_key`` to ``action``, swapping with any action that already uses it.

        The other action gets this action's previous key (or becomes unbound if there wasn't one).
        Returns a sentence describing the swap ("" when the key was free) and the combinations that
        changed (action -> value).
        """
        new_lower = new_key.lower()
        previous = self.values.get(action, "")
        conflict = self.key_to_action.get(new_lower)
        if conflict == action:
            conflict = None

        old_lower = self.action_to_key.pop(action, "") or previous.lower()
        if old_lower and self.key_to_action.get(old_lower) == action:
            self.key_to_action.pop(old_lower, None)

        note = ""
        changed: Dict[str, str] = {}
        if conflict:
            self.action_to_key.pop(conflict, None)
            used = f"{key_name(new_key)} was used by {conflict}."
            if previous:
                prev_lower = previous.lower()
                self.key_to_action[prev_lower] = conflict
                self.action_to_key[conflict] = prev_lower
                self.values[conflict] = previous
                note = f"{used} Swapped: {conflict} is now {key_name(previous)}."
            else:
                self.values[conflict] = ""
                note = f"{used} Swapped: {conflict} is now unbound."
            changed[conflict] = self.values[conflict]

        self.key_to_action[new_lower] = action
        self.action_to_key[action] = new_lower
        self.values[action] = new_key
        if previous.lower() != new_lower:
            changed[action] = new_key
        return note, changed


def bind_message(action: str, new_key: str, note: str) -> str:
    return note or f"{action} set to {key_name(new_key)}"


CANT_USE_KEY = "That key can't be used."


# Testing a volume -----------------------------------------------------------------------

class VolumeTester:
    """Plays the sound that goes with a volume setting, so the user can hear the level."""

    def __init__(self) -> None:
        self.instances: Dict[str, Any] = {}

    @staticmethod
    def sound_file(volume_key: str) -> str:
        from lib.utilities.utilities import get_available_sounds
        if volume_key in ('MasterVolume', 'POIVolume'):
            return 'assets/sounds/poi.ogg'
        if volume_key == 'StormVolume':
            return 'assets/sounds/storm.ogg'
        if volume_key == 'DynamicObjectVolume':
            return 'assets/sounds/dynamicobject.ogg'
        clean_key = volume_key.replace('Volume', '').lower()
        for sound_name in get_available_sounds():
            if clean_key in sound_name.lower():
                return f'assets/sounds/{sound_name}.ogg'
        return 'assets/sounds/poi.ogg'

    def play(self, volume_key: str, volume: float, master: float = 1.0) -> None:
        """Play the sound for ``volume_key`` at ``volume`` (0 to 1), with the master volume at ``master``."""
        try:
            volume = max(0.0, min(float(volume), 1.0))
            sound_file = self.sound_file(volume_key)
            if not os.path.exists(sound_file):
                return
            if volume_key not in self.instances:
                from lib.utilities.spatial_audio import SpatialAudio
                self.instances[volume_key] = SpatialAudio(sound_file)
            audio = self.instances[volume_key]
            if volume_key == 'MasterVolume':
                audio.set_master_volume(volume)
                audio.set_individual_volume(1.0)
            else:
                audio.set_master_volume(master)
                audio.set_individual_volume(volume)
            audio.play_audio(left_weight=0.5, right_weight=0.5, volume=1.0)
        except ValueError:
            pass
        except Exception as e:
            logger.error(f"Error testing volume: {e}")

    def cleanup(self) -> None:
        for audio in self.instances.values():
            try:
                audio.cleanup()
            except Exception:
                pass
        self.instances.clear()


# The schema the new window renders ---------------------------------------------------------

def _setting_dict(item: Item, parser, show_description: bool) -> Dict[str, Any]:
    """One setting as the UI gets it."""
    value, description = extract_value_and_description(item.value_string)
    section = target_section(parser, item.tracking, item.key) or item.tracking
    label = item.label or setting_label(item.key, item.tracking)
    default_string = default_value_string(item.tracking, item.key) if item.kind != "choice" else None
    default_part = extract_value_and_description(default_string)[0] if default_string else None
    out: Dict[str, Any] = {
        "id": f"{section}/{item.key}",
        "section": section,
        "key": item.key,
        "label": label,
        "description": description,
        "show_description": show_description,
    }
    if item.kind == "check":
        out.update(kind="toggle", value=value.lower() == "true")
    elif item.kind == "volume":
        out.update(kind="volume", value=max(0, min(volume_percent(value), 100)), min=0, max=100, step=1, decimals=0)
    elif item.kind == "choice":
        values = [stored for stored, _shown in item.choices]
        out.update(kind="choice", value=value.lower() if value.lower() in values else values[0],
                   choices=[{"value": stored, "label": shown} for stored, shown in item.choices])
        default_string = default_value_string(item.tracking, item.key)
        default_part = extract_value_and_description(default_string)[0] if default_string else None
    elif item.kind == "keybind":
        combo = value.strip()
        out.update(kind="keybind", value=combo, display=key_name(combo) if combo else "Unbound")
    else:
        spec = number_spec(item.key, value)
        if spec is None:
            out.update(kind="text", value=value)
        else:
            out.update(kind="number", **spec)
    default = None
    if default_part is not None:
        default = default_ui_value(item.kind, item.key, default_part, item.choices)
    out["default"] = default
    return out


def _groups(items: Sequence[Item], tab_for_order: str, parser, show_descriptions: bool) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        heading = group_for(item.tracking, item.key)
        groups.setdefault(heading, []).append(_setting_dict(item, parser, show_descriptions))
    return [{"heading": heading, "settings": groups[heading]}
            for heading in order_groups(tab_for_order, list(groups))]


def build_tab(parser, tab: str, general_active: bool = True, maps: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One tab as the UI gets it: groups of settings. GameObjects also lists its maps (their settings
    come from build_map)."""
    items = tab_items(parser, tab, general_active, maps)
    # Match events are tracked under their own section but show among the Toggles groups.
    show = tab != "Keybinds"
    out: Dict[str, Any] = {"name": tab, "groups": _groups(items, tab, parser, show)}
    if tab == "GameObjects":
        names = map_names(maps or {})
        out["maps"] = [{"key": name, "name": map_display_name(name)} for name in names]
    return out


def build_map(parser, map_name: str) -> Dict[str, Any]:
    """One map's object settings: groups with a group per object type."""
    items = map_items(parser, map_name)
    section = f"{map_name.title()}GameObjects"
    return {"map": map_name, "groups": _groups(items, section, parser, False)}


def build_schema(parser, view: str, maps: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The whole editor for ``view`` ('settings' or 'keybinds'): its tabs and their groups."""
    names = SETTINGS_TABS if view == "settings" else KEYBINDS_TABS
    general_active = "General" in names
    return {"view": view, "tabs": [build_tab(parser, tab, general_active, maps) for tab in names]}


def search_entries(parser, view: str, maps: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Every setting in ``view``, for the search box: label, tab, and where to find it."""
    names = SETTINGS_TABS if view == "settings" else KEYBINDS_TABS
    general_active = "General" in names
    entries: List[Dict[str, Any]] = []

    def add(item: Item, shown_tab: str, display_tab: str, map_name: Optional[str]) -> None:
        value, description = extract_value_and_description(item.value_string)
        section = target_section(parser, item.tracking, item.key) or item.tracking
        label = item.label or setting_label(item.key, item.tracking)
        hay = f"{label} {split_words(item.key)} {item.key} {description}".lower()
        entries.append({"id": f"{section}/{item.key}", "label": label, "tab": display_tab, "tab_name": shown_tab,
                        "map": map_name, "description": description, "hay": hay,
                        "text": f"{label}, {display_tab}"})

    for tab in names:
        for item in tab_items(parser, tab, general_active, maps):
            add(item, TRACKED_ELSEWHERE.get(item.tracking, item.tab), TRACKED_ELSEWHERE.get(item.tracking, item.tab), None)
        if tab == "GameObjects":
            for name in map_names(maps or {}):
                for item in map_items(parser, name):
                    add(item, "GameObjects", f"GameObjects ({name.replace('_', ' ').strip().title()})", name)
    entries.sort(key=lambda e: (e["tab"].lower(), e["id"].split("/", 1)[1].lower()))
    return entries
