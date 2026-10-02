"""Requests about the window itself: closing, quitting, sounds, folders, and the wx windows."""
from __future__ import annotations

import threading
import webbrowser

from lib.hub import get_hub, settings, sounds, status
from lib.shell.bridge import handler
from lib.shell.wx_thread import call_on_wx

SOUNDS = ("navigate", "open", "close", "done", "error")
FOLDERS = ("logs", "config")


def _hub():
    hub = get_hub()
    if hub is None:
        raise RuntimeError("FA11y is closing.")
    return hub


@handler("app.close_action")
def close_action(_params: dict) -> dict:
    return {"action": settings.close_action()}


@handler("app.set_close_action")
def set_close_action(params: dict) -> dict:
    action = params.get("action")
    if action not in (settings.CLOSE_TRAY, settings.CLOSE_QUIT):
        raise ValueError("Unknown close action.")
    return {"ok": settings.set_close_action(action)}


@handler("app.quit")
def quit_app(_params: dict) -> dict:
    import wx
    hub = _hub()
    wx.CallAfter(hub.quit)
    return {}


@handler("app.sound")
def play_sound(params: dict) -> dict:
    name = params.get("name")
    if name in SOUNDS:
        sounds.ui(name)
    return {}


@handler("app.window_hidden")
def window_hidden(params: dict) -> dict:
    _hub().window_hidden(bool(params.get("refocus_game")))
    return {}


@handler("app.summon")
def summon(params: dict) -> dict:
    _hub().summon(focus_content=bool(params.get("focus_content")))
    return {}


@handler("app.show_page")
def show_page(params: dict) -> dict:
    _hub().show_page(str(params.get("key", "")), summon=bool(params.get("summon")))
    return {}


@handler("app.play_fortnite")
def play_fortnite(_params: dict) -> dict:
    _hub().play_fortnite()
    return {}


@handler("app.open_folder")
def open_folder(params: dict) -> dict:
    name = params.get("name")
    if name not in FOLDERS:
        raise ValueError("Unknown folder.")
    status.open_folder(name)
    return {}


@handler("app.open_url")
def open_url(params: dict) -> dict:
    url = str(params.get("url", ""))
    if url != status.REPO_URL:
        raise ValueError("That address can't be opened from here.")
    threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    return {}


@handler("app.restart_to_update")
def restart_to_update(_params: dict) -> dict:
    status.restart_to_update(_hub())
    return {}


@handler("app.open_classic")
def open_classic(params: dict) -> dict:
    """Open the wx window for a page the new window doesn't have yet."""
    key = str(params.get("key", ""))
    hub = _hub()
    return {"ok": bool(call_on_wx(lambda: hub.classic().open(key)))}


@handler("app.start_setup")
def start_setup(_params: dict) -> dict:
    """Run first-run setup again, in its own wx window."""
    hub = _hub()

    def finished(egl_choice) -> None:
        hub.reset_views(("settings", "keybinds"))
        if egl_choice in ("manage", "sync"):
            from lib.hub.pages.fortnite import apply_setup_choice
            windows = hub.classic()
            windows.open("fortnite")
            apply_setup_choice(windows.host("fortnite"), egl_choice)
        else:
            hub.show_page("home", summon=True)

    call_on_wx(lambda: hub.start_onboarding(finished))
    return {}


@handler("app.state")
def app_state(_params: dict) -> dict:
    return _hub().hello()
