"""Hub sidebar: the list of pages, grouped under section headings.

Drawn by NavList (lib/hub/controls.py), which screen readers see as a
list named "Pages" whose items are the pages. Each item's description is
its section ("Play", "Account"), so NVDA reads "Locker, Account".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

import wx

from lib.hub.controls import NavItem, NavList


@dataclass
class SidebarEntry:
    key: str
    label: str
    icon: str
    group: str = ""


class Sidebar(NavList):
    def __init__(self, parent: wx.Window, entries: List[SidebarEntry],
                 on_select: Callable[[str], None]):
        super().__init__(parent, [NavItem(e.key, e.label, e.icon, e.group) for e in entries])
        self._keys = [e.key for e in entries]
        self._on_select_key = on_select
        self.on_select = lambda index: self._on_select_key(self._keys[index])

    def select(self, key: str, notify: bool = False) -> None:
        if key in self._keys:
            self.set_selection(self._keys.index(key), notify=notify)

    def selected_key(self) -> Optional[str]:
        return self._keys[self.selection] if self.selection >= 0 else None
