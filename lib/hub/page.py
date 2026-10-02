"""Base class for hub pages."""
from __future__ import annotations

import wx

from lib.hub import theme
from lib.hub.widgets import PAGE_MARGIN, heading


class HubPage(wx.ScrolledWindow):
    """One page of the hub, shown when its sidebar entry is selected.

    Pages are built the first time they're shown (or ahead of time while
    the hub is idle), so opening the hub never waits on every page.
    Subclasses implement build(), and may override on_show(), on_hide()
    and handle_escape().
    """

    title = ""

    def __init__(self, parent: wx.Window, hub):
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.hub = hub
        self.built = False
        theme.style_window(self)
        self.SetScrollRate(0, 20)
        self.SetName(self.title)
        self.content = wx.BoxSizer(wx.VERTICAL)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self.content, 1, wx.EXPAND | wx.ALL, PAGE_MARGIN)
        self.SetSizer(outer)

    def ensure_built(self) -> None:
        if self.built:
            return
        self.built = True
        self.Freeze()
        try:
            self.build()
            self.Layout()
            self.FitInside()
        finally:
            self.Thaw()

    def add_heading(self, text: str = "") -> wx.StaticText:
        ctrl = heading(self, text or self.title)
        self.content.Add(ctrl, 0, wx.BOTTOM, 12)
        return ctrl

    def build(self) -> None:
        raise NotImplementedError

    def on_show(self) -> None:
        """Called each time the page becomes visible."""

    def on_hide(self) -> None:
        """Called when another page replaces this one."""

    def handle_escape(self) -> bool:
        """Return True if the page used Escape (e.g. to leave a sub-view)."""
        return False

    def first_focus(self) -> wx.Window:
        """Control that gets focus when the user moves into the page."""
        for child in self.GetChildren():
            if child.IsShown() and child.IsEnabled() and child.AcceptsFocus():
                return child
        return self
