"""How the settings editor presents settings: readable names, groups, rows.

Config keys stay as they are in config.txt ("AnnounceInventoryStatus");
this module turns them into labels ("Announce inventory status") and
decides which group box each one appears in on its tab.
"""
from __future__ import annotations

import wx

from lib.hub import theme
from lib.hub.controls import SettingsGroup

# Labels, groups and their order live in lib/config_schema.py, shared with the new window.
from lib.config_schema import (  # noqa: E402,F401
    GROUPS as _GROUPS, LABEL_OVERRIDES, OTHER, group_for, object_setting, order_groups, setting_label, split_words,
)


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
    rank = {heading: index for index, heading in enumerate(order_groups(tab, [s.heading for s in sections]))}
    wanted = sorted(sections, key=lambda s: rank[s.heading])
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
