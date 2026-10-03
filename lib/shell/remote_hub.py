"""RemoteHub: the hub as the rest of FA11y sees it, with the window in another program.

It has the public methods of the wx HubFrame (show_page, summon, toggle,
quit, notify and so on), so FA11y.py and the action modules don't care
which window is running. Calls turn into events for FA11y.UI.exe, and the
UI's own events (visible, active, current page) are tracked here. It also
owns what HubFrame did besides drawing: watching for Fortnite and keeping
the keybinds on while Fortnite runs.

Events sent to the UI:
    core.hello         the starting state, sent when the UI says ui.ready
    ui.summon          bring the window forward {focus_content, over_game}
    ui.show_page       switch pages {key, summon, focus_sidebar, over_game}
    ui.hide            hide to the tray
    ui.quit            exit
    ui.notify          a toast {title, message}
    keybinds.changed   {enabled, open_keybind}
    fortnite.running   {running}
    update.available   {version}
    home.changed, account.changed, about.changed, fortnite.changed, social.changed, locker.changed
                       a page's data changed (account pages also get it after signing in or out)
    fortnite.setup_choice  {choice} take over or sync the Epic Games Launcher install
    setup.start        show first-run setup {summon}
    views.reset        {keys}, signed in or out: ported pages that depend on the account reload
    quests.changed     {revision}, quests changed (match packets or an account refresh)
Events from the UI:
    ui.ready           the window is on screen and listening
    ui.visibility      {visible, active}
    ui.page            {key}, the user changed pages
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, Optional, Sequence, Union

from lib.hub import game_watch, set_hub, settings, sounds, status
from lib.hub.services import HubServices
from lib.shell.bridge import Bridge, registry

logger = logging.getLogger(__name__)

PORTED_PAGES = ("home", "fortnite", "discover", "account", "locker", "social", "quests", "settings",
                "keybinds", "about")
EDITOR_PAGES = ("settings", "keybinds")  # the config editor's two views
PAGE_KEYS = ("home", "fortnite", "discover", "account", "locker", "social", "quests",
             "settings", "keybinds", "about")


class _PageProxy:
    """Stands in for a ported page: refresh() tells the UI to reload that page's data."""

    built = True

    def __init__(self, hub: "RemoteHub", key: str):
        self._hub = hub
        self.key = key

    def refresh(self) -> None:
        if self.key in EDITOR_PAGES:
            self._hub.send("views.reset", {"keys": [self.key]})
        else:
            self._hub.send(f"{self.key}.changed")


class RemoteHub:
    def __init__(self, services: HubServices, exe_path: Union[str, Sequence[str]], root: str,
                 fallback: Optional[Callable[[], None]] = None):
        self.services = services
        self.root = root
        self._fallback = fallback
        self._current = "home"
        self._shown = False
        self._active = False
        self._summoned_over_game = False
        self._quitting = False
        self._login_settled = False
        self._proxies: Dict[str, _PageProxy] = {key: _PageProxy(self, key) for key in PORTED_PAGES}
        self._classic = None
        self._setup_done: Optional[Callable] = None
        self.watcher = game_watch.GameWatcher(self._on_fortnite_changed)

        self._load_handlers()
        self.bridge = Bridge(exe_path, root, registry.handlers, on_give_up=self._on_give_up)
        self.bridge.subscribe("ui.ready", self._on_ready)
        self.bridge.subscribe("ui.visibility", self._on_visibility)
        self.bridge.subscribe("ui.page", self._on_page)
        set_hub(self)

    @staticmethod
    def _load_handlers() -> None:
        from lib.shell.handlers import about, account, app, fortnite, home, locker, settings, setup, social  # noqa: F401 (they register themselves)
        from lib.shell.handlers import discover, passes, quests  # noqa: F401

    # Lifecycle -----------------------------------------------------------

    def start(self, show: bool = True) -> None:
        """Start the window and begin watching for Fortnite."""
        from lib.app import state
        running = game_watch.is_fortnite_running()
        sounds.set_enabled(settings.flag("NavigationSounds", True))
        self._shown = show and not running
        args = [] if self._shown else ["--hidden"]
        state.add_keybinds_listener(self._on_keybinds_changed)
        self.bridge.start(args)
        self.watcher.start()
        game_watch.sync_keybinds_with_game(game_watch.is_fortnite_running())
        sounds.preload()

    def quit(self) -> None:
        """Quit FA11y entirely."""
        if self._quitting:
            return
        self._quitting = True
        self.watcher.stop()
        from lib.app import state
        state.remove_keybinds_listener(self._on_keybinds_changed)
        set_hub(None)
        self.services.quit()
        self.bridge.stop()

    def _on_give_up(self) -> None:
        """The UI keeps crashing: use the wx window instead."""
        logger.error("Falling back to the wx window")
        self._shown = False
        self.watcher.stop()  # the wx window starts its own
        from lib.app import state
        state.remove_keybinds_listener(self._on_keybinds_changed)
        if self._fallback is not None and not self._quitting:
            try:
                self._fallback()
            except Exception:
                logger.exception("Could not create the wx window")
        self.finish_onboarding(None)  # setup can't continue in the wx window; start FA11y without it

    # State the UI reports ----------------------------------------------------

    def IsShown(self) -> bool:
        return self._shown

    def _on_visibility(self, data: dict) -> None:
        self._shown = bool(data.get("visible"))
        self._active = bool(data.get("active")) and self._shown
        if not self._shown:
            self._summoned_over_game = False

    def _on_page(self, data: dict) -> None:
        key = data.get("key")
        if key in PAGE_KEYS:
            self._current = key

    def _on_ready(self, _data: dict) -> None:
        self.send("core.hello", self.hello())

    def hello(self) -> dict:
        from lib.app import state
        return {
            "version": status.local_version(),
            "keybinds_on": state.are_keybinds_enabled(),
            "open_keybind": _safe(status.open_hub_keybind, ""),
            "fortnite_running": game_watch.is_fortnite_running(),
            "update": status.available_update(),
            "can_restart_to_update": status.can_restart_to_update(),
            "page": self._current,
            "setup": self._setup_done is not None,
        }

    def send(self, name: str, data: Optional[dict] = None) -> None:
        """Send the UI an event. Safe from any thread."""
        self.bridge.send_event(name, data)

    # Pages ---------------------------------------------------------------

    def has_page(self, key: str) -> bool:
        """True for pages the new window has taken over; the others open wx windows."""
        return key in PORTED_PAGES

    def page(self, key: str) -> Optional[_PageProxy]:
        return self._proxies.get(key)

    def current_page(self) -> Optional[_PageProxy]:
        return self._proxies.get(self._current)

    def show_page(self, key: str, summon: bool = False, focus_sidebar: bool = False) -> None:
        """Switch to a page. summon=True also brings the window forward and focuses the page."""
        if key not in PAGE_KEYS:
            return
        self._current = key
        data = {"key": key, "summon": summon, "focus_sidebar": focus_sidebar}
        if summon:
            data["over_game"] = self._note_summon()
        self.send("ui.show_page", data)

    def reset_views(self, keys) -> None:
        """Reload these pages (after signing in or out, or a config change)."""
        for key in keys:
            if key in self._proxies:
                self.send(f"{key}.changed")
        self.send("views.reset", {"keys": list(keys)})
        classic = self._classic
        if classic is None:
            return
        import wx
        if wx.IsMainThread():
            classic.reset_views(keys)
        else:
            wx.CallAfter(classic.reset_views, keys)

    def login_settled(self) -> None:
        """The startup Epic sign-in finished (or failed)."""
        self._login_settled = True
        self.send("account.changed")
        self.send("home.changed")
        from lib.hub import account_ops
        for key in account_ops.ACCOUNT_PAGES:
            if key in self._proxies:
                self.send(f"{key}.changed")

    def leave_page(self) -> None:
        """A page asked to close: hide over a game, otherwise go back to the sidebar."""
        if self._summoned_over_game or game_watch.is_fortnite_running():
            self.hide_to_tray(refocus_game=True)
        else:
            self.send("ui.focus_sidebar")

    # Showing and hiding --------------------------------------------------

    def _note_summon(self) -> bool:
        """Remember whether the user was in Fortnite when they asked for the window."""
        self._summoned_over_game = game_watch.is_fortnite_foreground()
        if not self._shown:
            sounds.ui("open")
            self._shown = True
        return self._summoned_over_game

    def summon(self, focus_content: bool = False) -> None:
        """Bring the window to the front, e.g. from a keybind while in game."""
        over_game = self._note_summon()
        self.send("ui.summon", {"focus_content": focus_content, "over_game": over_game})

    def toggle(self) -> None:
        """Open FA11y keybind: summon, or hide when already in front."""
        if self._shown and self._active:
            self.hide_to_tray(refocus_game=True)
        else:
            self.summon()

    def hide_to_tray(self, refocus_game: bool = False) -> None:
        if self._shown:
            sounds.ui("close")
        self._shown = False
        self._active = False
        self.send("ui.hide")
        self._summoned_over_game = False
        if refocus_game and game_watch.is_fortnite_running():
            # Give the window a moment to go, so Fortnite is what Windows
            # hands the foreground to.
            threading.Timer(0.08, game_watch.focus_fortnite).start()

    def window_hidden(self, refocus_game: bool) -> None:
        """The UI hid itself (Escape or the close button)."""
        was_shown = self._shown
        self._shown = False
        self._active = False
        self._summoned_over_game = False
        if was_shown:
            sounds.ui("close")
        if refocus_game and game_watch.is_fortnite_running():
            game_watch.focus_fortnite()

    def play_fortnite(self) -> None:
        """Launch Fortnite (or bring it forward). Safe from any thread."""
        from lib.hub.play import play_fortnite

        def work():
            def failed(message: str) -> None:
                sounds.ui("error")
                self.services.speak(message)
            try:
                play_fortnite(self, info=status.last_install_info(), on_failed=failed)
            except Exception:
                logger.exception("Play Fortnite failed")
        threading.Thread(target=work, name="PlayFortnite", daemon=True).start()

    # Notifications -------------------------------------------------------

    def update_available_changed(self) -> None:
        """Refresh what shows FA11y's update state. Safe from any thread."""
        self.send("update.available", {"version": status.available_update()})

    def notify(self, title: str, message: str) -> None:
        """Windows notification. Safe to call from any thread."""
        self.send("ui.notify", {"title": title, "message": message})

    # Fortnite and keybinds -------------------------------------------------

    def _on_fortnite_changed(self, running: bool) -> None:
        game_watch.sync_keybinds_with_game(running)
        self.send("fortnite.running", {"running": running})
        if running and settings.flag("HideHubWhenFortniteStarts", True) and self._shown:
            self.hide_to_tray()

    def keybinds_edited(self) -> None:
        """The user changed a keybind in the editor: the Open FA11y key shown on Home may have changed."""
        from lib.app import state
        self._on_keybinds_changed(state.are_keybinds_enabled())

    def _on_keybinds_changed(self, enabled: bool) -> None:
        self.send("keybinds.changed", {"enabled": enabled,
                                       "open_keybind": _safe(status.open_hub_keybind, "")})

    # wx windows for pages the new window hasn't taken over -------------------------

    def classic(self):
        """The wx fallback windows (created on first use). Main thread only."""
        if self._classic is None:
            from lib.shell.classic_window import ClassicWindows
            self._classic = ClassicWindows(self)
        return self._classic

    def start_onboarding(self, on_finished) -> None:
        """Show first-run setup in the window. on_finished(egl_choice) runs on the wx thread when it ends."""
        from lib.app import state
        if self._setup_done is not None:
            self.summon()
            return
        self._setup_done = on_finished
        state.wizard_open.set()
        if not self._shown:
            self._note_summon()
        self.send("setup.start", {"summon": True})

    def finish_onboarding(self, egl_choice) -> None:
        """Setup ended (the window asks through setup.finish): hand its Epic Games Launcher choice on."""
        from lib.app import state
        callback, self._setup_done = self._setup_done, None
        state.wizard_open.clear()
        if callback is not None:
            import wx
            wx.CallAfter(callback, egl_choice)

    def apply_egl_choice(self, choice: str) -> None:
        """After setup: the Fortnite page takes over ("manage") or syncs with ("sync") the Epic Games Launcher install."""
        self.show_page("fortnite")
        self.send("fortnite.setup_choice", {"choice": choice})

    is_remote = True


def _safe(func, default):
    try:
        return func()
    except Exception:
        logger.debug("Reading state for the UI failed", exc_info=True)
        return default
