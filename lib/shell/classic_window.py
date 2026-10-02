"""The existing wx pages, opened in their own windows.

Pages the new window hasn't taken over yet (Fortnite, Discover, Locker,
Social, Quests, Settings, Keybinds) still live in lib/hub/pages as wx
pages. Each one opens here, in a small window of its own, when the user
presses its "Open" button. Setup ("Run setup again") also runs here.
All of this runs on the wx main thread.
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

import wx

from lib.hub import theme

logger = logging.getLogger(__name__)

PAGE_SIZE = (860, 660)


class PageHost:
    """What a wx page expects of its hub, answered for a page in its own window."""

    def __init__(self, remote, window: "PageWindow"):
        self._remote = remote
        self._window = window
        self.services = remote.services

    # The page's own window.
    def current_page(self):
        return self._window.page

    def page(self, key: str):
        return self._window.page if key == self._window.key else None

    def has_page(self, key: str) -> bool:
        return key == self._window.key

    def leave_page(self) -> None:
        self._window.close_window()

    def reset_views(self, keys) -> None:
        self._remote.reset_views(keys)

    # Everything else is the main window's business.
    def show_page(self, key: str, summon: bool = False, focus_sidebar: bool = False) -> None:
        if key == self._window.key:
            if summon:
                self._window.open()
            return
        self._remote.show_page(key, summon=summon, focus_sidebar=focus_sidebar)

    def play_fortnite(self) -> None:
        self._remote.play_fortnite()

    def notify(self, title: str, message: str) -> None:
        self._remote.notify(title, message)

    def update_available_changed(self) -> None:
        self._remote.update_available_changed()

    def login_settled(self) -> None:
        self._remote.login_settled()

    def start_onboarding(self, on_finished) -> None:
        self._remote.start_onboarding(on_finished)


class PageWindow(wx.Frame):
    """One wx hub page in a window. Escape leaves a sub-view, then closes the window."""

    def __init__(self, remote, key: str, label: str, factory: Callable):
        super().__init__(None, title=f"FA11y - {label}", size=PAGE_SIZE)
        from lib.hub.frame import app_icon
        self.key = key
        self.SetIcon(app_icon(32))
        self.SetMinSize((640, 480))
        theme.style_window(self)
        self.SetFont(theme.base_font())
        self._host = PageHost(remote, self)
        self.page = factory(self, self._host)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.page, 1, wx.EXPAND)
        self.SetSizer(sizer)
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self.CentreOnScreen()

    def open(self) -> None:
        from lib.guis.gui_utilities import force_focus_window
        was_shown = self.IsShown()
        self.page.ensure_built()
        theme.style_tree(self.page)
        if not was_shown:
            self.page.on_show()
        force_focus_window(self, None, self._focus_first)

    def _focus_first(self) -> None:
        if self:
            target = self.page.first_focus()
            if target is not None:
                target.SetFocus()

    def close_window(self) -> None:
        if self.IsShown():
            if self.page.built:
                self.page.on_hide()
            self.Hide()
        self._return_focus()

    def _return_focus(self) -> None:
        from lib.hub import game_watch
        if game_watch.is_fortnite_running():
            game_watch.focus_fortnite()

    def _on_close(self, event: wx.CloseEvent) -> None:
        if event.CanVeto():
            event.Veto()
            self.close_window()
        else:
            self.Destroy()

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_ESCAPE and not event.HasAnyModifiers():
            if self.page.built and self.page.handle_escape():
                return
            self.close_window()
            return
        event.Skip()


class OnboardingWindow(wx.Frame):
    """First-run setup, run from About's "Run setup again"."""

    def __init__(self, on_finished: Callable[[Optional[str]], None]):
        super().__init__(None, title="FA11y setup", size=(820, 620))
        from lib.hub.frame import app_icon
        from lib.hub.onboarding import OnboardingPanel
        self.SetIcon(app_icon(32))
        self.SetMinSize((640, 480))
        theme.style_window(self)
        self.SetFont(theme.base_font())
        self._on_finished = on_finished
        self._finished = False
        self.panel = OnboardingPanel(self, self._done)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.panel, 1, wx.EXPAND)
        self.SetSizer(sizer)
        self.Bind(wx.EVT_CLOSE, lambda e: self.Destroy())
        self.CentreOnScreen()

    def begin(self) -> None:
        from lib.guis.gui_utilities import force_focus_window
        theme.style_tree(self)
        self.Show()
        force_focus_window(self, None, None)
        self.panel.begin()

    def _done(self, egl_choice) -> None:
        if self._finished:
            return
        self._finished = True
        self.Hide()
        self._on_finished(egl_choice)
        wx.CallAfter(self.Destroy)


class ClassicWindows:
    """Creates each page's window once and opens it on request."""

    def __init__(self, remote):
        self._remote = remote
        self._windows: Dict[str, PageWindow] = {}
        self._onboarding: Optional[OnboardingWindow] = None

    def open(self, key: str) -> bool:
        """Open the wx window for a page. Returns False when there isn't one."""
        window = self._windows.get(key)
        if window is None or not window:
            from lib.hub.pages import default_pages
            spec = next((s for s in default_pages() if s.entry.key == key), None)
            if spec is None:
                return False
            window = PageWindow(self._remote, key, spec.entry.label, spec.factory)
            self._windows[key] = window
        window.open()
        return True

    def host(self, key: str) -> PageHost:
        """The hub stand-in for a page that has a window (see PageHost)."""
        return self._windows[key]._host

    def reset_views(self, keys) -> None:
        for key in keys:
            window = self._windows.get(key)
            page = window.page if window else None
            if page is not None and page.built and hasattr(page, "reset_view"):
                page.reset_view()
                if window.IsShown():
                    page.on_show()

    def start_onboarding(self, on_finished) -> None:
        if self._onboarding:
            self._onboarding.Raise()
            return
        self._onboarding = OnboardingWindow(on_finished)
        self._onboarding.begin()
