"""Hub sidebar: a native Windows list view with grouped pages.

The list is a plain wx.ListCtrl, so screen readers announce it like any
Windows list ("Locker, 5 of 11"). Section headings ("Play", "Account") use
the list view's built-in group feature through Win32 messages, which wx
doesn't expose. Arrow keys skip group headings natively and NVDA reads the
group name when focus moves into a new section.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from dataclasses import dataclass
from typing import Callable, List, Optional

import wx

from lib.hub import theme

LVM_FIRST = 0x1000
LVM_SETITEMW = LVM_FIRST + 76
LVM_INSERTGROUP = LVM_FIRST + 145
LVM_ENABLEGROUPVIEW = LVM_FIRST + 157
LVIF_GROUPID = 0x0100
LVGF_HEADER = 0x0001
LVGF_STATE = 0x0004
LVGF_GROUPID = 0x0010
LVGS_NOHEADER = 0x0004

ICON_SIZE = 20
# Image cells are larger than the icon: the list view sizes rows to fit
# them, which gives the sidebar comfortable spacing.
CELL_WIDTH = 30
CELL_HEIGHT = 32


class _LVGROUP(ctypes.Structure):
    # The pre-Vista layout; comctl32 accepts it and ignores the newer fields.
    _fields_ = [
        ("cbSize", wt.UINT), ("mask", wt.UINT),
        ("pszHeader", wt.LPWSTR), ("cchHeader", ctypes.c_int),
        ("pszFooter", wt.LPWSTR), ("cchFooter", ctypes.c_int),
        ("iGroupId", ctypes.c_int), ("stateMask", wt.UINT),
        ("state", wt.UINT), ("uAlign", wt.UINT),
    ]


class _LVITEMW(ctypes.Structure):
    _fields_ = [
        ("mask", wt.UINT), ("iItem", ctypes.c_int), ("iSubItem", ctypes.c_int),
        ("state", wt.UINT), ("stateMask", wt.UINT),
        ("pszText", wt.LPWSTR), ("cchTextMax", ctypes.c_int),
        ("iImage", ctypes.c_int), ("lParam", wt.LPARAM),
        ("iIndent", ctypes.c_int), ("iGroupId", ctypes.c_int),
        ("cColumns", wt.UINT), ("puColumns", ctypes.POINTER(wt.UINT)),
    ]


_send = ctypes.windll.user32.SendMessageW
_send.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, ctypes.c_void_p]
_send.restype = wt.LPARAM


def _padded_icon(name: str) -> wx.Bitmap:
    icon = theme.icon(name, ICON_SIZE).GetBitmap(wx.Size(ICON_SIZE, ICON_SIZE))
    image = wx.Image(CELL_WIDTH, CELL_HEIGHT)
    image.InitAlpha()
    image.SetAlpha(bytes(CELL_WIDTH * CELL_HEIGHT))
    image.Paste(icon.ConvertToImage(), CELL_WIDTH - ICON_SIZE - 2, (CELL_HEIGHT - ICON_SIZE) // 2)
    return wx.Bitmap(image)


@dataclass
class SidebarEntry:
    key: str
    label: str
    icon: str
    group: str = ""


class Sidebar(wx.ListCtrl):
    """Single-column list of hub pages. Calls on_select(key) when the selection changes."""

    def __init__(self, parent: wx.Window, entries: List[SidebarEntry],
                 on_select: Callable[[str], None]):
        super().__init__(parent, style=wx.LC_REPORT | wx.LC_NO_HEADER | wx.LC_SINGLE_SEL | wx.BORDER_NONE)
        self.SetName("Pages")
        self.SetBackgroundColour(theme.SIDEBAR_BG)
        self.SetForegroundColour(theme.TEXT)
        self._entries = entries
        self._on_select = on_select

        images = wx.ImageList(CELL_WIDTH, CELL_HEIGHT)
        for entry in entries:
            images.Add(_padded_icon(entry.icon))
        self.AssignImageList(images, wx.IMAGE_LIST_SMALL)

        self.InsertColumn(0, "Page")
        for index, entry in enumerate(entries):
            self.InsertItem(index, entry.label, index)
        self._apply_groups()

        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_item_selected)
        self.Bind(wx.EVT_SIZE, self._on_size)

    def _apply_groups(self) -> None:
        hwnd = self.GetHandle()
        # ItemsView draws readable group headings with a divider line in dark mode.
        ctypes.windll.uxtheme.SetWindowTheme(hwnd, "DarkMode_ItemsView", None)
        group_ids = {}
        for entry in self._entries:
            if entry.group in group_ids:
                continue
            group_id = len(group_ids) + 1
            group_ids[entry.group] = group_id
            group = _LVGROUP()
            group.cbSize = ctypes.sizeof(_LVGROUP)
            group.mask = LVGF_HEADER | LVGF_GROUPID | LVGF_STATE
            group.pszHeader = entry.group
            group.iGroupId = group_id
            group.stateMask = LVGS_NOHEADER
            group.state = 0 if entry.group else LVGS_NOHEADER
            _send(hwnd, LVM_INSERTGROUP, -1 & 0xFFFFFFFFFFFFFFFF, ctypes.addressof(group))
        _send(hwnd, LVM_ENABLEGROUPVIEW, 1, None)
        for index, entry in enumerate(self._entries):
            item = _LVITEMW()
            item.mask = LVIF_GROUPID
            item.iItem = index
            item.iGroupId = group_ids[entry.group]
            _send(hwnd, LVM_SETITEMW, 0, ctypes.addressof(item))

    def _on_size(self, event: wx.SizeEvent) -> None:
        self.SetColumnWidth(0, self.GetClientSize().width)
        event.Skip()

    def _on_item_selected(self, event: wx.ListEvent) -> None:
        self._on_select(self._entries[event.GetIndex()].key)

    def select(self, key: str, notify: bool = False) -> None:
        for index, entry in enumerate(self._entries):
            if entry.key == key:
                if not notify:
                    self.Unbind(wx.EVT_LIST_ITEM_SELECTED)
                self.Select(index)
                self.Focus(index)
                self.EnsureVisible(index)
                if not notify:
                    self.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_item_selected)
                return

    def selected_key(self) -> Optional[str]:
        index = self.GetFirstSelected()
        return self._entries[index].key if index >= 0 else None
