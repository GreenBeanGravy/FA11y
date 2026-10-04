"""RemoteHub: the hub as the rest of FA11y sees it, with the window in another program.

It has the methods the rest of FA11y calls (show_page, summon, toggle,
quit, notify and so on). Calls turn into events for FA11y.UI.exe, and the
UI's own events (visible, active, current page) are tracked here. It also
watches for Fortnite and keeps the keybinds on while Fortnite runs.

When the window program can't start or keeps stopping, FA11y keeps running
without a window: the keybinds still work and the user is told once how to
repair it.

Events sent to the UI:
    core.hello         the starting state, sent when the UI says ui.ready
    startup.progress   {percent, message} what FA11y is doing while it starts
    startup.done       startup finished; the window leaves its startup screen
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

READY_TIMEOUT_SECONDS = 10.0
NO_WINDOW_MESSAGE = "FA11y's window couldn't start. Run Updater.exe to repair FA11y."
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
    def __init__(self, services: HubServices, exe_path: Union[None, str, Sequence[str]], root: str,
                 ready_timeout: float = READY_TIMEOUT_SECONDS):
        self.services = services
        self.root = root
        self._exe_path = exe_path
        self._ready_timeout = ready_timeout
        self._ready = False
        self._no_window = False
        self._hidden_notice_given = False
        self._current = "home"
        self._shown = False
        self._active = False
        self._summoned_over_game = False
        self._quitting = False
        self._login_settled = False
        self._startup_lock = threading.Lock()
        self._startup_done = False
        self._startup = {"percent": 0, "message": ""}
        self._proxies: Dict[str, _PageProxy] = {key: _PageProxy(self, key) for key in PAGE_KEYS}
        self._setup_done: Optional[Callable] = None
        self.watcher = game_watch.GameWatcher(self._on_fortnite_changed)

        self._load_handlers()
        self.bridge = Bridge(exe_path or "", root, registry.handlers, on_give_up=self._on_give_up)
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
        self._start_window(args)
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

    def _start_window(self, args) -> None:
        """Start FA11y.UI.exe and give it a few seconds to say it is ready."""
        if not self._exe_path:
            self._window_unavailable("FA11y.UI.exe was not found")
            return
        try:
            self.bridge.start(args)
        except Exception as e:
            logger.exception("Could not start FA11y.UI.exe")
            self._window_unavailable(f"FA11y.UI.exe could not be started: {e}")
            return
        timer = threading.Timer(self._ready_timeout, self._check_ready)
        timer.daemon = True
        timer.start()

    def _check_ready(self) -> None:
        if self._ready or self._quitting or self._no_window:
            return
        proc = getattr(self.bridge, "_proc", None)
        code = proc.poll() if proc is not None else None
        detail = "it is still starting" if code is None else f"it exited with code {code}"
        self._window_unavailable(f"FA11y.UI.exe sent no ui.ready within {self._ready_timeout:g} seconds ({detail}). "
                                 "A missing .NET Desktop Runtime is the usual cause")

    def _on_give_up(self) -> None:
        """The UI keeps crashing."""
        self._window_unavailable("FA11y.UI.exe keeps stopping")

    def _window_unavailable(self, reason: str) -> None:
        """No window this session: say why once, and keep FA11y running so the keybinds still work."""
        if self._no_window or self._quitting:
            return
        self._no_window = True
        self._shown = False
        logger.error(f"{reason}. Running without a window.")
        try:
            self.services.speak(NO_WINDOW_MESSAGE)
        except Exception:
            logger.exception("Could not speak the window message")
        self.finish_onboarding(None)  # setup can't run without the window; start FA11y anyway

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
        self._ready = True
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
            "starting": not self._startup_done,
            "startup": dict(self._startup),
        }

    def startup_progress(self, percent: int, message: str) -> None:
        """Tell the window how far startup is. Progress only goes up. Safe from any thread."""
        with self._startup_lock:
            if self._startup_done:
                return
            percent = max(int(percent), self._startup["percent"])
            self._startup = {"percent": percent, "message": message}
        self.send("startup.progress", {"percent": percent, "message": message})

    def startup_finished(self) -> None:
        """Startup is over; the window swaps its startup screen for the pages. Sent once. Safe from any thread."""
        with self._startup_lock:
            if self._startup_done:
                return
            self._startup_done = True
        self.send("startup.done")

    def send(self, name: str, data: Optional[dict] = None) -> None:
        """Send the UI an event. Safe from any thread."""
        self.bridge.send_event(name, data)

    # Pages ---------------------------------------------------------------

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

    def hide_to_tray(self, refocus_game: bool = False, notify: bool = False) -> None:
        if notify and self._shown:
            self._notify_hidden(in_game=True)
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
            self._notify_hidden(in_game=refocus_game)
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

    def notify_ready(self) -> None:
        """Startup finished (the moment the core speaks its ready line): toast it if the user wants that."""
        if settings.flag("NotifyWhenReady", True):
            self.notify("", "Ready")

    def _notify_hidden(self, in_game: bool) -> None:
        """The window went to the tray: say where FA11y is. Over a game it is said once per session."""
        if not settings.flag("NotifyWhenHiddenToTray", True):
            return
        if in_game:
            if self._hidden_notice_given:
                return
            self._hidden_notice_given = True
        keybind = _safe(status.open_hub_keybind, "")
        opener = f"Press {keybind} to open." if keybind else "Open from the tray icon."
        self.notify("", f"Running in the background. {opener}")

    # Fortnite and keybinds -------------------------------------------------

    def _on_fortnite_changed(self, running: bool) -> None:
        game_watch.sync_keybinds_with_game(running)
        self.send("fortnite.running", {"running": running})
        if running and settings.flag("HideHubWhenFortniteStarts", True) and self._shown:
            self.hide_to_tray(notify=True)

    def keybinds_edited(self) -> None:
        """The user changed a keybind in the editor: the Open FA11y key shown on Home may have changed."""
        from lib.app import state
        self._on_keybinds_changed(state.are_keybinds_enabled())

    def _on_keybinds_changed(self, enabled: bool) -> None:
        self.send("keybinds.changed", {"enabled": enabled,
                                       "open_keybind": _safe(status.open_hub_keybind, "")})

    # First-run setup -------------------------------------------------------

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

    def apply_setup_choice(self, egl_choice) -> None:
        """After setup: the Fortnite page takes over ("manage") or syncs with ("sync") the Epic Games Launcher
        install; otherwise go home."""
        if egl_choice not in ("manage", "sync"):
            self.show_page("home", focus_sidebar=True)
            return
        self.show_page("fortnite")
        self.send("fortnite.setup_choice", {"choice": egl_choice})


def _safe(func, default):
    try:
        return func()
    except Exception:
        logger.debug("Reading state for the UI failed", exc_info=True)
        return default
