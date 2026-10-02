"""How the settings editor presents settings: readable names, groups, rows.

Config keys stay as they are in config.txt ("AnnounceInventoryStatus");
this module turns them into labels ("Announce inventory status") and
decides which group box each one appears in on its tab.
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

import wx

from lib.hub import theme
from lib.hub.controls import SettingsGroup

# Labels that the automatic CamelCase split gets wrong or could say better.
LABEL_OVERRIDES: Dict[str, str] = {
    "StartFortniteOnLaunch": "Start Fortnite when FA11y opens",
    "HideHubWhenFortniteStarts": "Hide the FA11y window when Fortnite starts",
    "NavigationSounds": "Play navigation sounds in the FA11y window",
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


def setting_label(key: str, tab: str = "") -> str:
    """What the user sees and hears for a config key."""
    if key in LABEL_OVERRIDES:
        return LABEL_OVERRIDES[key]
    if " " in key:  # keybind actions are already words
        return key
    if tab.endswith("GameObjects") and tab != "GameObjects":
        parts = object_setting(key)
        if parts:
            return parts[1]
    return split_words(key)


# Group headings for each tab, in display order, with the keys each holds.
# Keys not listed land in the tab's last group (OTHER).
OTHER = "Other"
_GROUPS: Dict[str, Tuple[Tuple[str, Tuple[str, ...]], ...]] = {
    "General": (
        ("Startup and updates", ("StartFortniteOnLaunch", "AutoUpdates", "CreateDesktopShortcut")),
        ("FA11y window", ("HideHubWhenFortniteStarts", "NavigationSounds", "CloseAction")),
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
    if tab.endswith("GameObjects") and tab != "GameObjects":
        parts = object_setting(key)
        return parts[0] if parts else OTHER
    groups = _GROUPS.get(tab)
    if not groups:
        return OTHER
    for heading, keys in groups:
        if key in keys:
            return heading
    if len(groups) == 1:
        return groups[0][0]
    return OTHER


DESCRIPTION_WIDTH = 560
CONTROL_WIDTH = 130
KEY_WIDTH = 220


class SettingsSection:
    """One group box of settings: checkboxes on their own lines, other
    settings as aligned label and control rows, each optionally followed
    by its description in small muted text."""

    def __init__(self, parent: wx.Window, heading: str, show_descriptions: bool = True):
        self.heading = heading
        self.box = SettingsGroup(parent, heading)
        self.show_descriptions = show_descriptions
        self.sizer = wx.StaticBoxSizer(self.box, wx.VERTICAL)
        self.grid = wx.GridBagSizer(self.box.FromDIP(4), self.box.FromDIP(16))
        self.labels = []
        top, other = self.box.GetBordersForSizer()
        heading_height = self.box.GetFullTextExtent(heading or "M", self.box.heading_font())[1]
        pad = self.box.FromDIP(16)
        extra_top = max(self.box.FromDIP(10) + heading_height + self.box.FromDIP(8) - top, 0)
        inner = wx.BoxSizer(wx.VERTICAL)
        inner.AddSpacer(extra_top)
        inner.Add(self.grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, pad)
        inner.AddSpacer(max(self.box.FromDIP(12) - other, 0))
        self.sizer.Add(inner, 0, wx.EXPAND)
        self._row = 0

    @property
    def parent(self) -> wx.Window:
        return self.box

    def _description(self, text: str, indent: int = 0) -> None:
        if not (self.show_descriptions and text):
            return
        note = wx.StaticText(self.box, label=text)
        note.SetForegroundColour(theme.TEXT_MUTED)
        note.SetFont(theme.small_font(note))
        note.Wrap(self.box.FromDIP(DESCRIPTION_WIDTH))
        self.grid.Add(note, (self._row, 0), (1, 2), wx.LEFT | wx.BOTTOM, indent)
        self._row += 1

    def add_check(self, checkbox: wx.CheckBox, description: str = "") -> None:
        self.grid.Add(checkbox, (self._row, 0), (1, 2))
        self._row += 1
        self._description(description, self.box.FromDIP(22))

    def add_row(self, label: wx.StaticText, control, description: str = "") -> None:
        self.grid.Add(label, (self._row, 0), flag=wx.ALIGN_CENTER_VERTICAL)
        self.labels.append(label)
        self.grid.Add(control, (self._row, 1), flag=wx.ALIGN_CENTER_VERTICAL)
        self._row += 1
        self._description(description)


def section_for(container: wx.Window, heading: str, show_descriptions: bool = True) -> SettingsSection:
    """The section with ``heading`` in ``container``, created (and added to
    the container's sizer) the first time it's asked for."""
    sections = getattr(container, "_settings_sections", None)
    if sections is None:
        sections = container._settings_sections = {}
    section = sections.get(heading)
    if section is None:
        section = SettingsSection(container, heading, show_descriptions)
        sizer = container.GetSizer()
        if sizer is None:
            sizer = wx.BoxSizer(wx.VERTICAL)
            container.SetSizer(sizer)
            container.sizer = sizer
        sizer.Add(section.sizer, 0, wx.EXPAND | wx.RIGHT | wx.BOTTOM, container.FromDIP(12))
        sections[heading] = section
    return section


def reset_sections(container: wx.Window) -> None:
    container._settings_sections = {}


def finish_sections(container: wx.Window, tab: str) -> None:
    """Once ``container``'s settings are built: give every group the same
    label column width so controls line up down the page, and put the
    groups in the order _GROUPS lists for ``tab`` (unlisted groups last),
    on screen and in Tab order."""
    sections = list(getattr(container, "_settings_sections", {}).values())
    labels = [label for section in sections for label in section.labels]
    if labels:
        width = max(label.GetBestSize().width for label in labels)
        for label in labels:
            label.SetMinSize((width, -1))
    sizer = container.GetSizer()
    if len(sections) < 2 or sizer is None:
        return
    order = [heading for heading, _keys in _GROUPS.get(tab, ())]
    wanted = sorted(sections, key=lambda s: order.index(s.heading) if s.heading in order else len(order))
    if wanted == sections:
        return
    items = [item.GetSizer() for item in sizer.GetChildren()]
    slots = sorted(items.index(section.sizer) for section in sections)
    for section in sections:
        sizer.Detach(section.sizer)
    for slot, section in zip(slots, wanted):
        sizer.Insert(slot, section.sizer, 0, wx.EXPAND | wx.RIGHT | wx.BOTTOM, container.FromDIP(12))
    for before, after in zip(wanted, wanted[1:]):
        after.box.MoveAfterInTabOrder(before.box)
