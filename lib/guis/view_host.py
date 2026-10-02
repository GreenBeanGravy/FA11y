"""Views that can live either in a hub page or in a standalone dialog.

A view is a wx.Panel holding one feature's controls and logic (quests,
social, locker and so on). A host shows it: the hub shows views as pages,
and ViewDialog shows them as a modal popup when the hub isn't available.
Views never call EndModal, Close or Destroy on their window; they call
request_close() and let the host decide what that means.
"""
from __future__ import annotations

from typing import Callable, Optional

import wx

from lib.hub import theme


class EmbeddedView(wx.Panel):
    """Base class for a feature panel.

    Lifecycle: the host calls activate() each time the view becomes visible
    and deactivate() each time it's hidden or closed. Start timers and
    refresh data in activate(); stop timers in deactivate(). A view may be
    activated and deactivated many times while it lives in the hub.
    """

    view_title = ""

    def __init__(self, parent: wx.Window):
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.host = None
        self.SetName(self.view_title)

    def activate(self) -> None:
        """The view became visible."""

    def deactivate(self) -> None:
        """The view was hidden or its host is closing."""

    def can_close(self) -> bool:
        """Return False to veto a dialog close (e.g. while a request is running)."""
        return True

    def handle_escape(self) -> bool:
        """Return True if Escape was used inside the view (e.g. to leave a sub-view).

        Returning False lets the host close or hide the view.
        """
        return False

    def initial_focus(self) -> Optional[wx.Window]:
        """Control to focus when the view is shown; None picks the first focusable control."""
        return None

    def request_close(self, code: int = wx.ID_CANCEL) -> None:
        """Ask the host to close the view (dialog) or leave it (hub)."""
        if self.host is not None:
            self.host.close_view(self, code)

    def set_view_title(self, title: str) -> None:
        self.view_title = title
        self.SetName(title)
        if self.host is not None:
            self.host.view_title_changed(self, title)


def first_focusable(window: wx.Window) -> Optional[wx.Window]:
    for child in window.GetChildren():
        if not child.IsShown() or not child.IsEnabled():
            continue
        if isinstance(child, wx.StaticText):
            continue
        if child.AcceptsFocus():
            return child
        found = first_focusable(child)
        if found is not None:
            return found
    return None


def focus_view(view: EmbeddedView) -> None:
    target = view.initial_focus() or first_focusable(view)
    if target is not None:
        target.SetFocus()


class ViewDialog(wx.Dialog):
    """Shows one EmbeddedView as a resizable modal dialog."""

    def __init__(self, parent: Optional[wx.Window], make_view: Callable[[wx.Window], EmbeddedView],
                 size: tuple = (900, 650)):
        super().__init__(parent, size=size, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetFont(theme.base_font())
        self.view = make_view(self)
        self.view.host = self
        theme.style_tree(self)
        self.SetTitle(self.view.view_title)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.view, 1, wx.EXPAND)
        self.SetSizer(sizer)
        self.SetMinSize((520, 400))
        self.CentreOnScreen()
        self._closed = False
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self.Bind(wx.EVT_CLOSE, self._on_close)

    # Host protocol -------------------------------------------------------

    def close_view(self, view: EmbeddedView, code: int = wx.ID_CANCEL) -> None:
        self._finish(code)

    def view_title_changed(self, view: EmbeddedView, title: str) -> None:
        self.SetTitle(title)

    # ---------------------------------------------------------------------

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_ESCAPE and not event.HasAnyModifiers():
            if not self.view.handle_escape():
                self._finish(wx.ID_CANCEL)
            return
        event.Skip()

    def _on_close(self, _event: wx.CloseEvent) -> None:
        self._finish(wx.ID_CANCEL)

    def _finish(self, code: int) -> None:
        if self._closed or not self.view.can_close():
            return
        self._closed = True
        try:
            self.view.deactivate()
        finally:
            if self.IsModal():
                self.EndModal(code)
            else:
                self.Destroy()

    def run(self) -> int:
        from lib.guis.gui_utilities import force_focus_window
        self.view.activate()
        wx.CallAfter(force_focus_window, self, None, lambda: focus_view(self.view))
        try:
            return self.ShowModal()
        finally:
            self.Destroy()


def show_view(page_key: str, make_view: Callable[[wx.Window], EmbeddedView],
              size: tuple = (900, 650)) -> None:
    """Show a feature: as a hub page when the hub is running, else as a modal dialog.

    Must run on the main thread. With the hub, this returns immediately;
    without it, it blocks until the dialog closes.
    """
    from lib.hub import get_hub
    hub = get_hub()
    if hub is not None and hub.has_page(page_key):
        hub.show_page(page_key, summon=True)
        return
    ViewDialog(None, make_view, size).run()
