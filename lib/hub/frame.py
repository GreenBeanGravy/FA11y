"""The hub window: sidebar of pages, page area, tray icon, notifications."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import wx
import wx.adv

from lib.hub import game_watch, set_hub, settings, sounds, theme
from lib.hub.controls import PageStack, StyledButton, TabbedBook
from lib.hub.page import HubPage
from lib.hub.sidebar import Sidebar, SidebarEntry

logger = logging.getLogger(__name__)

SIDEBAR_WIDTH = 210


@dataclass
class HubServices:
    """Callbacks into the rest of FA11y, supplied by FA11y.py."""
    quit: Callable[[], None]
    reload_config: Callable[[], None]
    speak: Callable[[str], None]


@dataclass
class PageSpec:
    entry: SidebarEntry
    factory: Callable[[wx.Window, "HubFrame"], HubPage]


def app_icon(size: int = 32) -> wx.Icon:
    """FA11y's logo as an icon, taken from the .ico size closest to ``size``."""
    icon = wx.Icon(theme.LOGO_ICO, wx.BITMAP_TYPE_ICO, size, size)
    if not icon.IsOk():
        icon = wx.Icon()
        icon.CopyFromBitmap(app_bitmap(size))
    return icon


_logo_bitmaps: Dict[int, wx.Bitmap] = {}


def app_bitmap(size: int) -> wx.Bitmap:
    """FA11y's logo scaled to ``size`` pixels."""
    bitmap = _logo_bitmaps.get(size)
    if bitmap is None:
        image = wx.Image(theme.LOGO_PNG, wx.BITMAP_TYPE_PNG) if os.path.exists(theme.LOGO_PNG) else wx.Image()
        if image.IsOk():
            bitmap = wx.Bitmap(image.Scale(size, size, wx.IMAGE_QUALITY_HIGH))
        else:
            bitmap = wx.Bitmap(size, size, 32)
        _logo_bitmaps[size] = bitmap
    return bitmap


class _Decoration(wx.Panel):
    """A panel that only draws (the logo, the divider), so it is never a tab stop.

    A wx.Panel with nothing focusable inside takes focus itself, and screen
    readers would read it as an unnamed "panel".
    """

    def AcceptsFocus(self) -> bool:
        return False

    def AcceptsFocusFromKeyboard(self) -> bool:
        return False


class HubTrayIcon(wx.adv.TaskBarIcon):
    def __init__(self, hub: "HubFrame"):
        super().__init__()
        self.hub = hub
        self.SetIcon(app_icon(wx.SystemSettings.GetMetric(wx.SYS_SMALLICON_X)), "FA11y")
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, lambda e: hub.summon())
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_UP, lambda e: hub.summon())

    def CreatePopupMenu(self):
        menu = wx.Menu()
        items = [
            ("Open FA11y", lambda: self.hub.summon()),
            ("Play Fortnite", lambda: self.hub.play_fortnite()),
            ("Settings", lambda: self.hub.show_page("settings", summon=True)),
            (None, None),
            ("Quit FA11y", lambda: self.hub.quit()),
        ]
        for label, action in items:
            if label is None:
                menu.AppendSeparator()
                continue
            item = menu.Append(wx.ID_ANY, label)
            self.Bind(wx.EVT_MENU, lambda e, a=action: a(), item)
        return menu


class CloseChoiceDialog(wx.Dialog):
    """Asked the first time the window is closed: keep running in the tray, or quit."""

    def __init__(self, parent: wx.Window):
        super().__init__(parent, title="Keep FA11y running?")
        theme.style_window(self)
        self.SetFont(theme.base_font())
        sizer = wx.BoxSizer(wx.VERTICAL)
        text = wx.StaticText(self, label="FA11y's keybinds only work while FA11y is running. "
                                         "You can keep it running in the system tray, or quit it now.")
        text.Wrap(380)
        sizer.Add(text, 0, wx.ALL, 16)
        self.remember = wx.CheckBox(self, label="&Don't ask again")
        self.remember.SetValue(True)
        sizer.Add(self.remember, 0, wx.LEFT | wx.RIGHT, 16)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        quit_btn = StyledButton(self, wx.ID_NO, "&Quit FA11y")
        tray_btn = StyledButton(self, wx.ID_YES, "&Hide to tray", variant="primary")
        tray_btn.SetDefault()
        buttons.Add(quit_btn, 0, wx.RIGHT, 8)
        buttons.Add(tray_btn)
        sizer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 16)
        self.SetSizerAndFit(sizer)
        quit_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_NO))
        tray_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_YES))
        self.SetEscapeId(wx.ID_CANCEL)
        self.CentreOnParent()
        wx.CallAfter(tray_btn.SetFocus)


class HubFrame(wx.Frame):
    def __init__(self, services: HubServices, pages: List[PageSpec]):
        super().__init__(None, title="FA11y", size=(980, 660),
                         style=wx.DEFAULT_FRAME_STYLE)
        self.services = services
        icons = wx.IconBundle(theme.LOGO_ICO, wx.BITMAP_TYPE_ICO)
        if not icons.IsEmpty():
            self.SetIcons(icons)
        else:
            self.SetIcon(app_icon(32))
        self.SetMinSize((760, 480))
        theme.style_window(self)
        self.SetFont(theme.base_font())

        self._specs: Dict[str, PageSpec] = {spec.entry.key: spec for spec in pages}
        self._order = [spec.entry.key for spec in pages]
        self._pages: Dict[str, HubPage] = {}
        self._current: Optional[str] = None
        self._summoned_over_game = False
        self._quitting = False
        self._toasts_ready = False

        root = wx.Panel(self)
        root.SetBackgroundColour(theme.WINDOW_BG)
        self.sidebar = Sidebar(root, [spec.entry for spec in pages], self._on_sidebar_select)
        self.sidebar.on_activate = self.focus_content
        self.book = PageStack(root)
        self.book.SetBackgroundColour(theme.WINDOW_BG)
        divider = _Decoration(root, size=(1, -1))
        divider.SetBackgroundColour(theme.CARD_BORDER)

        column = wx.BoxSizer(wx.VERTICAL)
        column.Add(self._brand(root), 0, wx.EXPAND)
        column.Add(self.sidebar, 1, wx.EXPAND)
        self._main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._main_sizer.Add(column, 0, wx.EXPAND)
        self._main_sizer.Add(divider, 0, wx.EXPAND)
        self._main_sizer.Add(self.book, 1, wx.EXPAND)
        self.sidebar.SetMinSize((self.FromDIP(SIDEBAR_WIDTH), -1))
        self._root = root
        self._root_sizer = wx.BoxSizer(wx.VERTICAL)
        self._root_sizer.Add(self._main_sizer, 1, wx.EXPAND)
        root.SetSizer(self._root_sizer)
        self._onboarding = None

        for key in self._order:
            page = self._specs[key].factory(self.book, self)
            self._pages[key] = page
            self.book.AddPage(page, self._specs[key].entry.label)

        self.tray = HubTrayIcon(self)
        self.watcher = game_watch.GameWatcher(self._on_fortnite_changed)

        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self.Bind(wx.EVT_IDLE, self._prebuild_on_idle)

        sounds.set_enabled(settings.flag("NavigationSounds", True))
        set_hub(self)
        self.CentreOnScreen()

    def _brand(self, parent: wx.Window) -> wx.Panel:
        """FA11y's icon and name at the top of the sidebar."""
        panel = _Decoration(parent)
        panel.SetBackgroundColour(theme.SIDEBAR_BG)
        size = self.FromDIP(32)
        icon = wx.StaticBitmap(panel, bitmap=app_bitmap(size))
        name = wx.StaticText(panel, label="FA11y")
        name.SetFont(theme.heading_font(panel, 3))
        name.SetForegroundColour(theme.TEXT)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(icon, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(name, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.FromDIP(10))
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(sizer, 0, wx.LEFT | wx.TOP | wx.BOTTOM, self.FromDIP(18))
        panel.SetSizer(outer)
        return panel

    # Lifecycle -----------------------------------------------------------

    def start(self, show: bool = True) -> None:
        """Show the window on Home and start watching for Fortnite."""
        self.show_page(self._order[0], focus_sidebar=True)
        self.watcher.start()
        if show and not game_watch.is_fortnite_running():
            self.Show()
            self.Raise()
        sounds.preload()

    def start_onboarding(self, on_finished: Callable[[Optional[str]], None]) -> None:
        """Replace the sidebar and pages with first-run setup until it's finished or skipped.

        on_finished receives the Epic Games Launcher choice from the Fortnite
        step: "manage", "sync" or None.
        """
        from lib.hub.onboarding import OnboardingPanel

        def done(egl_choice):
            panel = self._onboarding
            self._onboarding = None
            self._root_sizer.Show(self._main_sizer)
            if panel is not None:
                self._root_sizer.Detach(panel)
                panel.Destroy()
            self._root.Layout()
            self.SetTitle(f"FA11y - {self._specs[self._current].entry.label}" if self._current else "FA11y")
            self.sidebar.SetFocus()
            on_finished(egl_choice)

        self._onboarding = OnboardingPanel(self._root, done)
        self._root_sizer.Hide(self._main_sizer)
        self._root_sizer.Add(self._onboarding, 1, wx.EXPAND)
        self._root.Layout()
        self.SetTitle("FA11y setup")
        if not self.IsShown():
            self.Show()
        self.Raise()
        self._onboarding.begin()

    def quit(self) -> None:
        """Quit FA11y entirely."""
        if self._quitting:
            return
        self._quitting = True
        self.watcher.stop()
        for page in self._pages.values():
            if page.built:
                try:
                    page.on_hide()
                except Exception:
                    pass
        try:
            self.tray.RemoveIcon()
            self.tray.Destroy()
        except Exception:
            pass
        set_hub(None)
        self.services.quit()

    # Pages ---------------------------------------------------------------

    def has_page(self, key: str) -> bool:
        return key in self._pages

    def page(self, key: str) -> Optional[HubPage]:
        return self._pages.get(key)

    def current_page(self) -> Optional[HubPage]:
        return self._pages.get(self._current) if self._current else None

    def show_page(self, key: str, summon: bool = False, focus_sidebar: bool = False) -> None:
        """Switch to a page. summon=True also brings the window forward and focuses the page."""
        if not wx.IsMainThread():
            wx.CallAfter(self.show_page, key, summon, focus_sidebar)
            return
        if key not in self._pages:
            return
        if key != self._current:
            old = self.current_page()
            if old is not None and old.built:
                old.on_hide()
            page = self._pages[key]
            page.ensure_built()
            theme.style_tree(page)
            self.book.ChangeSelection(self._order.index(key))
            self._current = key
            self.sidebar.select(key)
            self.SetTitle(f"FA11y - {self._specs[key].entry.label}")
            page.on_show()
        if summon:
            self.summon(focus_content=True)
        elif focus_sidebar:
            self.sidebar.SetFocus()

    def reset_views(self, keys) -> None:
        """Rebuild the views on these pages next time they're shown (e.g. after signing in or out)."""
        for key in keys:
            page = self._pages.get(key)
            if page is not None and page.built and hasattr(page, "reset_view"):
                page.reset_view()
                if key == self._current:
                    page.on_show()

    def leave_page(self) -> None:
        """A page asked to close: hide over a game, otherwise go back to the sidebar."""
        if self._summoned_over_game or game_watch.is_fortnite_running():
            self.hide_to_tray(refocus_game=True)
        else:
            self.sidebar.SetFocus()

    def focus_content(self) -> None:
        page = self.current_page()
        if page is not None:
            target = page.first_focus()
            if target is not None:
                target.SetFocus()

    def _on_sidebar_select(self, key: str) -> None:
        if key != self._current:
            sounds.ui("navigate")
            self.show_page(key)

    def _prebuild_on_idle(self, event: wx.IdleEvent) -> None:
        # Build one unbuilt page per idle pass, so first visits are instant
        # without delaying the window's first paint.
        for key in self._order:
            page = self._pages[key]
            if not page.built:
                try:
                    page.ensure_built()
                except Exception:
                    logger.exception(f"Building page {key} failed")
                event.RequestMore()
                return
        self.Unbind(wx.EVT_IDLE)

    def cycle_page(self, step: int) -> None:
        index = self._order.index(self._current) if self._current else 0
        key = self._order[(index + step) % len(self._order)]
        sounds.ui("navigate")
        self.show_page(key)
        self.sidebar.SetFocus()

    # Showing and hiding --------------------------------------------------

    def summon(self, focus_content: bool = False) -> None:
        """Bring the window to the front, e.g. from a keybind while in game."""
        if not wx.IsMainThread():
            wx.CallAfter(self.summon, focus_content)
            return
        self._summoned_over_game = game_watch.is_fortnite_foreground()
        was_visible = self.IsShown() and not self.IsIconized()
        if self.IsIconized():
            self.Iconize(False)
        from lib.guis.gui_utilities import force_focus_window
        focus = self.focus_content if focus_content else self.sidebar.SetFocus
        force_focus_window(self, None, focus)
        if not was_visible:
            sounds.ui("open")

    def toggle(self) -> None:
        """Open FA11y keybind: summon, or hide when already in front."""
        if self.IsShown() and self.IsActive():
            self.hide_to_tray(refocus_game=True)
        else:
            self.summon()

    def hide_to_tray(self, refocus_game: bool = False) -> None:
        if self.IsShown():
            sounds.ui("close")
        self.Hide()
        if refocus_game and game_watch.is_fortnite_running():
            game_watch.focus_fortnite()
        self._summoned_over_game = False

    def _on_fortnite_changed(self, running: bool) -> None:
        home = self._pages.get("home")
        if home is not None and home.built and hasattr(home, "refresh"):
            home.refresh()
        if running and settings.flag("HideHubWhenFortniteStarts", True) and self.IsShown():
            self.hide_to_tray()

    def play_fortnite(self) -> None:
        page = self._pages.get("fortnite")
        if page is not None and hasattr(page, "play"):
            page.ensure_built()
            page.play()

    # Notifications -------------------------------------------------------

    def update_available_changed(self) -> None:
        """Refresh pages that show FA11y's update state. Safe from any thread."""
        if not wx.IsMainThread():
            wx.CallAfter(self.update_available_changed)
            return
        for key in ("home", "about"):
            page = self._pages.get(key)
            if page is not None and page.built and key == self._current:
                page.refresh()

    def notify(self, title: str, message: str) -> None:
        """Windows toast notification. Safe to call from any thread."""
        if not wx.IsMainThread():
            wx.CallAfter(self.notify, title, message)
            return
        try:
            if not self._toasts_ready:
                wx.adv.NotificationMessage.MSWUseToasts()
                self._toasts_ready = True
            note = wx.adv.NotificationMessage(title, message, self)
            note.SetIcon(app_icon(64))
            note.Show()
        except Exception as e:
            logger.debug(f"Notification failed: {e}")

    # Keyboard ------------------------------------------------------------

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        if self._onboarding is not None:
            event.Skip()
            return
        key = event.GetKeyCode()
        mods = event.GetModifiers()
        if key == wx.WXK_TAB and mods & wx.MOD_CONTROL:
            if self._focus_in_tabs():
                event.Skip()  # the tabs inside the page switch instead
                return
            self.cycle_page(-1 if mods & wx.MOD_SHIFT else 1)
            return
        if key == wx.WXK_F6 and not mods:
            if self.sidebar.HasFocus():
                self.focus_content()
            else:
                self.sidebar.SetFocus()
            return
        if key == wx.WXK_ESCAPE and not mods:
            page = self.current_page()
            if page is not None and page.handle_escape():
                return
            if self.sidebar.HasFocus() or self._summoned_over_game or game_watch.is_fortnite_running():
                self.hide_to_tray(refocus_game=True)
            else:
                self.sidebar.SetFocus()
            return
        event.Skip()

    @staticmethod
    def _focus_in_tabs() -> bool:
        window = wx.Window.FindFocus()
        while window is not None and not window.IsTopLevel():
            if isinstance(window, (TabbedBook, wx.Notebook)):
                return True
            window = window.GetParent()
        return False

    # Closing -------------------------------------------------------------

    def _on_close(self, event: wx.CloseEvent) -> None:
        if self._quitting or not event.CanVeto():
            self.quit()
            return
        event.Veto()
        action = settings.close_action()
        if action == settings.CLOSE_ASK:
            dialog = CloseChoiceDialog(self)
            result = dialog.ShowModal()
            remember = dialog.remember.GetValue()
            dialog.Destroy()
            if result == wx.ID_CANCEL:
                return
            action = settings.CLOSE_TRAY if result == wx.ID_YES else settings.CLOSE_QUIT
            if remember:
                settings.set_close_action(action)
        if action == settings.CLOSE_QUIT:
            self.quit()
        else:
            self.hide_to_tray()
