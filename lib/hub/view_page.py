"""Hub page that hosts an EmbeddedView (quests, social, locker and so on)."""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

import wx

from lib.guis.view_host import EmbeddedView, focus_view
from lib.hub import theme
from lib.hub.page import HubPage
from lib.hub.widgets import text

logger = logging.getLogger(__name__)


class ViewPage(HubPage):
    """Creates its view on first show.

    make_view(parent) builds the view, or returns None when the feature
    isn't available (for example, not signed in); the page then shows
    unavailable_text and tries again next time it's shown.

    With load, the page first runs load() on a worker thread (for slow
    network or disk work) and then calls make_view(parent, data).

    With identity, the page rebuilds its view whenever identity() returns
    a different object, such as a new social manager after signing in.

    The hub calls prepare() while it's idle, so the view is created and
    its data loaded (view.prefetch()) before the user first opens the
    page. Pages whose view depends on the Epic account (after_login)
    wait until the startup sign-in has settled. While a view is being
    created or reloaded, the page shows a focusable "Loading…" text.
    """

    unavailable_text = ""

    def __init__(self, parent: wx.Window, hub, title: str,
                 make_view: Callable[..., Optional[EmbeddedView]],
                 unavailable_text: str = "",
                 load: Optional[Callable[[], Any]] = None,
                 identity: Optional[Callable[[], Any]] = None,
                 loading_text: str = "Loading…", after_login: bool = False):
        self.title = title
        super().__init__(parent, hub)
        # Views manage their own scrolling lists; the page itself doesn't scroll.
        self.SetScrollRate(0, 0)
        self._make_view = make_view
        self.unavailable_text = unavailable_text or f"{title} isn't available right now."
        self._load = load
        self._identity = identity
        self._identity_value: Any = None
        self._loading = False
        self.loading_text = loading_text
        self.after_login = after_login
        self.view: Optional[EmbeddedView] = None
        self._placeholder = None
        self._focus_was_on_message = False
        self._prepare_tried = False

    def build(self) -> None:
        self._placeholder = text(self, "", theme.TEXT_SECONDARY, wrap=560)
        self.content.Add(self._placeholder, 0, wx.ALL, 4)

    def _show_message(self, message: str) -> None:
        self._placeholder.SetLabel(message)
        self._placeholder.Show()
        self.Layout()

    def prepare(self) -> None:
        """Create the view and start loading its data before the page is shown."""
        self.ensure_built()
        self._prepare_tried = True
        if self.view is None and not self._loading:
            self._ensure_view()

    @property
    def prepared(self) -> bool:
        return self._prepare_tried or self.view is not None or self._loading

    def _ensure_view(self) -> None:
        if self._identity is not None:
            current = self._identity()
            if self.view is not None and current is not self._identity_value:
                self.reset_view()
            self._identity_value = current
        if self.view is not None or self._loading:
            return
        if self.hub.current_page() is self and self._load is None:
            # Creating the view takes a moment; say so, then create it.
            self._loading = True
            self._show_message(self.loading_text)
            wx.CallLater(30, self._create_after_message)
            return
        if self._load is not None:
            self._loading = True
            self._show_message(self.loading_text)
            load = self._load

            def work():
                try:
                    data = load()
                except Exception:
                    logger.exception(f"Loading {self.title} failed")
                    data = None
                wx.CallAfter(self._loaded, data)
            threading.Thread(target=work, name=f"Load-{self.title}", daemon=True).start()
            return
        self._install_view(lambda: self._make_view(self))

    def _create_after_message(self) -> None:
        if not self:
            return
        self._loading = False
        self._install_view(lambda: self._make_view(self))
        self._after_install()

    def _loaded(self, data: Any) -> None:
        if not self:
            return
        self._loading = False
        if data is None:
            self._show_message(self.unavailable_text)
            return
        self._install_view(lambda: self._make_view(self, data))
        self._after_install()

    def _after_install(self) -> None:
        if self.view is None or self.hub.current_page() is not self:
            return
        self.view.activate()
        # Move focus into the new view only if the user was already in
        # this page, not if they've gone back to the sidebar meanwhile.
        focused = wx.Window.FindFocus()
        if self._focus_was_on_message or (focused is not None and (focused is self or self.IsDescendant(focused))):
            focus_view(self.view)

    def _install_view(self, create: Callable[[], Optional[EmbeddedView]]) -> None:
        try:
            view = create()
        except Exception:
            logger.exception(f"Creating the {self.title} view failed")
            view = None
        if view is None:
            self._show_message(self.unavailable_text)
            return
        self._focus_was_on_message = self._placeholder.HasFocus()
        self._placeholder.Hide()
        view.host = self
        theme.style_tree(view)
        self.content.Add(view, 1, wx.EXPAND)
        self.view = view
        if self._identity is not None:
            # make_view may create what identity() returns (Discover's API).
            self._identity_value = self._identity()
        self.Layout()
        self.FitInside()
        prefetch = getattr(view, "prefetch", None)
        if callable(prefetch):
            try:
                prefetch()
            except Exception:
                logger.exception(f"Prefetching {self.title} failed")

    def reset_view(self) -> None:
        """Drop the view so it's created again (e.g. after signing in)."""
        self._prepare_tried = False
        if self.view is not None:
            focused = wx.Window.FindFocus()
            had_focus = focused is not None and self.view.IsDescendant(focused)
            try:
                self.view.deactivate()
            finally:
                self.view.Destroy()
                self.view = None
            if self._placeholder is not None:
                self._show_message(self.loading_text)
                if had_focus:
                    # Keep focus in the page, on "Loading…", so the screen
                    # reader says what's happening.
                    self._placeholder.SetFocus()

    def on_show(self) -> None:
        self._ensure_view()
        if self.view is not None:
            self.view.activate()

    def on_hide(self) -> None:
        if self.view is not None:
            self.view.deactivate()

    def handle_escape(self) -> bool:
        return self.view is not None and self.view.handle_escape()

    def first_focus(self) -> wx.Window:
        if self.view is not None:
            target = self.view.initial_focus()
            if target is not None:
                return target
            from lib.guis.view_host import first_focusable
            return first_focusable(self.view) or self
        return super().first_focus()

    # Host protocol for EmbeddedView -------------------------------------

    def close_view(self, view: EmbeddedView, code: int = wx.ID_CANCEL) -> None:
        self.hub.leave_page()

    def view_title_changed(self, view: EmbeddedView, title: str) -> None:
        pass
