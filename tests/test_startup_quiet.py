"""FA11y stays quiet and out of the way while it loads."""
from pathlib import Path

from lib.app import state
from lib.hub import game_watch
from lib.monitors.base import BaseMonitor


def test_screen_monitors_wait_for_startup_and_a_settled_fortnite(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(game_watch.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(game_watch, "_running", True)
    monkeypatch.setattr(game_watch, "_on_screen_cache", (0.0, False))
    monkeypatch.setattr(game_watch, "_in_front_since", None)
    monkeypatch.setattr(game_watch, "is_fortnite_foreground", lambda: True)
    state.startup_done.clear()
    try:
        assert BaseMonitor.screen_paused()          # FA11y still loading
        state.startup_done.set()
        assert BaseMonitor.screen_paused()          # Fortnite just came to the front
        clock[0] += game_watch.SETTLE_SECONDS + 0.5
        assert not BaseMonitor.screen_paused()
        monkeypatch.setattr(game_watch, "is_fortnite_foreground", lambda: False)
        clock[0] += 1
        assert BaseMonitor.screen_paused()          # another window in front
    finally:
        state.startup_done.clear()


def test_silent_sign_in_never_shows_a_window_or_blocks(monkeypatch):
    from lib.guis import epic_browser_login

    shown = []

    class FakeWindow:
        def __init__(self, auth, timeout, on_done):
            pass

        def ShowWithoutActivating(self):
            shown.append("background")

        def ShowModal(self):
            raise AssertionError("silent sign-in must not be modal")

    monkeypatch.setattr(epic_browser_login, "SilentAuthDialog", FakeWindow)
    assert epic_browser_login.silent_webview_auth(object(), lambda ok: None) is None
    assert shown == ["background"]


def test_a_failed_sign_in_does_not_open_the_account_page():
    source = (Path(__file__).resolve().parents[1] / "FA11y.py").read_text(encoding="utf-8")
    assert 'show_page("account"' not in source and "show_page('account'" not in source
