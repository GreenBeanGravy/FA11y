"""RemoteHub: the hub interface FA11y.py uses, backed by the separate window program (a fake UI here)."""
import json
import os
import sys
import threading
import time
from unittest.mock import Mock

import pytest

from lib.app import state
from lib.hub import game_watch, settings, sounds, status
from lib.hub.services import HubServices
from lib.shell.remote_hub import NO_WINDOW_MESSAGE, RemoteHub

FAKE_UI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "fake_ui.py")


def wait_for(condition, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = condition()
        if result:
            return result
        time.sleep(0.02)
    raise AssertionError("timed out waiting for the condition")


def read_log(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def events(path, name):
    return [m["data"] for m in read_log(path) if m.get("type") == "event" and m.get("name") == name]


@pytest.fixture
def world(monkeypatch):
    """Fortnite's state, config flags and sounds, all controllable."""
    world = type("World", (), {})()
    world.running = False
    world.foreground = False
    world.flags = {"HideHubWhenFortniteStarts": True, "NavigationSounds": True}
    world.focus = Mock()
    world.ui_sound = Mock()
    monkeypatch.setattr(game_watch, "is_fortnite_running", lambda: world.running)
    monkeypatch.setattr(game_watch, "is_fortnite_foreground", lambda: world.foreground)
    monkeypatch.setattr(game_watch, "focus_fortnite", world.focus)
    monkeypatch.setattr(game_watch.GameWatcher, "start", lambda self: None)
    monkeypatch.setattr(settings, "flag", lambda key, default: world.flags.get(key, default))
    monkeypatch.setattr(settings, "close_action", lambda: "tray")
    monkeypatch.setattr(sounds, "ui", world.ui_sound)
    monkeypatch.setattr(sounds, "preload", lambda: None)
    monkeypatch.setattr(sounds, "set_enabled", lambda enabled: None)
    monkeypatch.setattr(status, "local_version", lambda: "9.9.9")
    monkeypatch.setattr(status, "open_hub_keybind", lambda: "Left Alt + F")
    monkeypatch.setattr(status, "available_update", lambda: "10.0.0")
    previous = state.are_keybinds_enabled()
    yield world
    state.set_keybinds_enabled(previous)


@pytest.fixture
def make_hub(tmp_path, world):
    from lib.hub import set_hub
    hubs = []

    def make(ui_args=(), show=True):
        log = str(tmp_path / "ui.log")
        services = HubServices(quit=Mock(), reload_config=Mock(), speak=Mock())
        hub = RemoteHub(services, [sys.executable, FAKE_UI, "--log", log, *ui_args], str(tmp_path))
        hubs.append(hub)
        hub.start(show=show)
        wait_for(lambda: events(log, "core.hello"))  # the UI said ui.ready and got its hello
        return hub, log

    yield make
    for hub in hubs:
        hub.watcher.stop()
        hub.bridge.stop(timeout=2)
    set_hub(None)


def visible(active=True):
    return json.dumps([{"name": "ui.visibility", "data": {"visible": True, "active": active}}])


def test_every_page_has_a_proxy(make_hub):
    hub, _ = make_hub()
    assert hub.page("home") is not None and hub.page("home").built
    assert hub.page("nope") is None


def test_hello_carries_the_starting_state(make_hub):
    state.set_keybinds_enabled(False)
    hub, log = make_hub()
    hello = events(log, "core.hello")[0]
    assert hello["version"] == "9.9.9"
    assert hello["open_keybind"] == "Left Alt + F"
    assert hello["update"] == "10.0.0"
    assert hello["keybinds_on"] is False
    assert hello["fortnite_running"] is False
    assert hello["page"] == "home"
    assert hello["setup"] is False


def test_startup_progress_and_done(make_hub):
    hub, log = make_hub()
    assert events(log, "core.hello")[0]["starting"] is True
    hub.startup_progress(30, "Loading settings")
    hub.startup_progress(10, "Earlier stage")  # progress only goes up
    hello = hub.hello()
    assert hello["starting"] is True
    assert hello["startup"] == {"percent": 30, "message": "Earlier stage"}
    hub.startup_finished()
    hub.startup_finished()
    wait_for(lambda: events(log, "startup.done"))
    time.sleep(0.2)
    assert len(events(log, "startup.done")) == 1
    sent = events(log, "startup.progress")
    assert sent[0] == {"percent": 30, "message": "Loading settings"}
    assert [e["percent"] for e in sent] == [30, 30]
    assert hub.hello()["starting"] is False
    hub.startup_progress(90, "Too late")
    assert hub.hello()["startup"]["percent"] == 30


def test_the_window_starts_hidden_when_fortnite_is_running(make_hub, world):
    world.running = True
    hub, log = make_hub()
    started = next(m for m in read_log(log) if m.get("started"))
    assert "--hidden" in started["argv"]
    assert not hub.IsShown()


def test_show_page_and_current_page(make_hub):
    hub, log = make_hub()
    hub.show_page("locker")
    hub.show_page("account", summon=True, focus_sidebar=False)
    wait_for(lambda: len(events(log, "ui.show_page")) == 2)
    first, second = events(log, "ui.show_page")
    assert first == {"key": "locker", "summon": False, "focus_sidebar": False}
    assert second["key"] == "account" and second["summon"] is True and "over_game" in second
    assert hub.current_page() is hub.page("account")
    hub.show_page("not-a-page")
    assert hub.current_page() is hub.page("account")


def test_the_pages_the_user_visits_are_tracked(make_hub):
    hub, log = make_hub(ui_args=("--emit", json.dumps([{"name": "ui.page", "data": {"key": "about"}}])))
    wait_for(lambda: hub.current_page() is hub.page("about"))


def test_summon_sends_an_event_and_plays_the_open_sound_once(make_hub, world):
    hub, log = make_hub(show=False)
    world.foreground = True
    hub.summon(focus_content=True)
    wait_for(lambda: events(log, "ui.summon"))
    assert events(log, "ui.summon")[0] == {"focus_content": True, "over_game": True}
    assert world.ui_sound.call_args_list == [(("open",),)]
    assert hub.IsShown()
    hub.summon()
    wait_for(lambda: len(events(log, "ui.summon")) == 2)
    assert world.ui_sound.call_count == 1


def test_toggle_summons_or_hides_depending_on_the_window(make_hub, world):
    hub, log = make_hub(ui_args=("--emit", visible(active=True)))
    wait_for(lambda: hub.IsShown() and hub._active)
    hub.toggle()
    wait_for(lambda: events(log, "ui.hide"))
    assert not hub.IsShown()
    assert ("close",) in [c.args for c in world.ui_sound.call_args_list]
    hub.toggle()
    wait_for(lambda: events(log, "ui.summon"))


def test_toggle_summons_a_visible_window_that_is_not_in_front(make_hub):
    hub, log = make_hub(ui_args=("--emit", visible(active=False)))
    wait_for(lambda: hub.IsShown())
    hub.toggle()
    wait_for(lambda: events(log, "ui.summon"))
    assert not events(log, "ui.hide")


def test_visibility_events_track_a_hidden_window(make_hub):
    emit = json.dumps([{"name": "ui.visibility", "data": {"visible": True, "active": True}},
                       {"name": "ui.visibility", "data": {"visible": False, "active": False}}])
    hub, _ = make_hub(ui_args=("--emit", emit))
    wait_for(lambda: not hub.IsShown() and not hub._active)


def test_keybinds_follow_fortnite_and_the_ui_hears_about_it(make_hub, world):
    hub, log = make_hub()
    world.running = True
    hub._on_fortnite_changed(True)
    assert state.are_keybinds_enabled() is True
    wait_for(lambda: events(log, "fortnite.running"))
    assert events(log, "fortnite.running")[0] == {"running": True}
    wait_for(lambda: events(log, "keybinds.changed") or True)
    world.running = False
    hub._on_fortnite_changed(False)
    assert state.are_keybinds_enabled() is False
    wait_for(lambda: len(events(log, "fortnite.running")) == 2)


def test_toggling_keybinds_by_hand_is_sent_to_the_ui(make_hub):
    state.set_keybinds_enabled(False)
    hub, log = make_hub()
    state.set_keybinds_enabled(True)
    wait_for(lambda: events(log, "keybinds.changed"))
    assert events(log, "keybinds.changed")[-1] == {"enabled": True, "open_keybind": "Left Alt + F"}


def test_the_window_hides_when_fortnite_starts_if_the_setting_is_on(make_hub, world):
    hub, log = make_hub(ui_args=("--emit", visible()))
    wait_for(lambda: hub.IsShown())
    world.running = True
    hub._on_fortnite_changed(True)
    wait_for(lambda: events(log, "ui.hide"))
    assert not hub.IsShown()


def test_the_window_stays_when_fortnite_starts_if_the_setting_is_off(make_hub, world):
    world.flags["HideHubWhenFortniteStarts"] = False
    hub, log = make_hub(ui_args=("--emit", visible()))
    wait_for(lambda: hub.IsShown())
    world.running = True
    hub._on_fortnite_changed(True)
    wait_for(lambda: events(log, "fortnite.running"))
    time.sleep(0.2)
    assert not events(log, "ui.hide")
    assert hub.IsShown()


def test_page_refresh_notifies_the_ui(make_hub):
    hub, log = make_hub()
    hub.page("home").refresh()
    hub.page("account").refresh()
    wait_for(lambda: events(log, "home.changed") and events(log, "account.changed"))


def test_login_settled_refreshes_account_and_home(make_hub):
    hub, log = make_hub()
    hub.login_settled()
    wait_for(lambda: events(log, "account.changed") and events(log, "home.changed"))


def test_update_and_notification_events(make_hub):
    hub, log = make_hub()
    hub.update_available_changed()
    hub.notify("A title", "A message")
    wait_for(lambda: events(log, "update.available") and events(log, "ui.notify"))
    assert events(log, "update.available")[0] == {"version": "10.0.0"}
    assert events(log, "ui.notify")[0] == {"title": "A title", "message": "A message"}


def test_leave_page_hides_over_a_game_otherwise_focuses_the_sidebar(make_hub, world):
    hub, log = make_hub(ui_args=("--emit", visible()))
    wait_for(lambda: hub.IsShown())
    hub.leave_page()
    wait_for(lambda: events(log, "ui.focus_sidebar"))
    world.running = True
    hub.leave_page()
    wait_for(lambda: events(log, "ui.hide"))


def test_the_ui_can_ask_the_core_for_things(make_hub, world):
    calls = [{"method": "app.close_action"}, {"method": "app.summon", "params": {"focus_content": True}},
             {"method": "app.sound", "params": {"name": "navigate"}}, {"method": "app.nothing"}]
    hub, log = make_hub(ui_args=("--call", json.dumps(calls)))
    wait_for(lambda: len([m for m in read_log(log) if m.get("type") == "response"]) == 4)
    responses = {m["id"]: m for m in read_log(log) if m.get("type") == "response"}
    assert responses[1]["result"] == {"action": "tray"}
    assert responses[2]["ok"] is True
    assert responses[3]["ok"] is True
    assert responses[4]["ok"] is False
    wait_for(lambda: events(log, "ui.summon"))
    assert events(log, "ui.summon")[0]["focus_content"] is True
    assert ("navigate",) in [c.args for c in world.ui_sound.call_args_list]


def test_the_ui_hiding_itself_plays_the_close_sound_and_returns_to_the_game(make_hub, world):
    world.running = True
    hub, log = make_hub(ui_args=("--emit", visible(),
                                 "--call", json.dumps({"method": "app.window_hidden", "params": {"refocus_game": True}})))
    wait_for(lambda: world.focus.called)
    assert not hub.IsShown()
    assert ("close",) in [c.args for c in world.ui_sound.call_args_list]


def test_play_fortnite_runs_the_shared_launch_code(make_hub, monkeypatch):
    import lib.hub.play as play
    launched = threading.Event()
    seen = {}

    def fake_play(hub, manager=None, info=None, on_failed=None):
        seen["hub"] = hub
        launched.set()

    monkeypatch.setattr(play, "play_fortnite", fake_play)
    hub, _ = make_hub()
    hub.play_fortnite()
    assert launched.wait(5)
    assert seen["hub"] is hub


def test_quit_stops_the_window_and_calls_the_service(make_hub):
    from lib.hub import get_hub
    hub, log = make_hub()
    assert get_hub() is hub
    hub.quit()
    hub.quit()  # a second call does nothing
    hub.services.quit.assert_called_once()
    assert get_hub() is None
    assert not hub.bridge.is_running()
    assert any(m.get("name") == "ui.quit" for m in read_log(log))


def test_keeps_running_without_a_window_when_it_keeps_crashing(make_hub):
    hub, _ = make_hub(ui_args=("--exit-after", "0.2"))
    wait_for(lambda: hub._no_window, timeout=30)
    hub.services.speak.assert_called_with(NO_WINDOW_MESSAGE)
    assert not hub.IsShown()
    hub.show_page("settings", summon=True)  # nothing to show it in, and nothing breaks
    hub.summon()


def test_no_window_when_the_program_is_missing(tmp_path, world):
    from lib.hub import set_hub
    services = HubServices(quit=Mock(), reload_config=Mock(), speak=Mock())
    hub = RemoteHub(services, None, str(tmp_path))
    try:
        hub.start()
        services.speak.assert_called_once_with(NO_WINDOW_MESSAGE)
        assert not hub.IsShown()
        hub.apply_setup_choice(None)
    finally:
        hub.watcher.stop()
        set_hub(None)


def test_no_window_when_it_never_says_ready(tmp_path, world):
    from lib.hub import set_hub
    services = HubServices(quit=Mock(), reload_config=Mock(), speak=Mock())
    log = str(tmp_path / "ui.log")
    hub = RemoteHub(services, [sys.executable, FAKE_UI, "--log", log, "--no-ready"], str(tmp_path), ready_timeout=0.3)
    try:
        hub.start()
        wait_for(lambda: hub._no_window)
        services.speak.assert_called_once_with(NO_WINDOW_MESSAGE)
    finally:
        hub.watcher.stop()
        hub.bridge.stop(timeout=2)
        set_hub(None)


def test_setup_finishes_when_there_is_no_window(tmp_path, world, monkeypatch):
    import wx
    from lib.hub import set_hub
    monkeypatch.setattr(wx, "CallAfter", lambda func, *args: func(*args))
    services = HubServices(quit=Mock(), reload_config=Mock(), speak=Mock())
    hub = RemoteHub(services, None, str(tmp_path))
    done = []
    try:
        hub._setup_done = done.append
        hub._window_unavailable("test")
        assert hub._setup_done is None  # handed on, so FA11y starts without waiting for a window
        assert done == [None]
    finally:
        hub.watcher.stop()
        set_hub(None)


def notices(log):
    return events(log, "ui.notify")


def test_ready_notification_follows_its_setting(make_hub, world):
    hub, log = make_hub()
    hub.notify_ready()
    wait_for(lambda: notices(log))
    assert notices(log) == [{"title": "", "message": "Ready"}]
    world.flags["NotifyWhenReady"] = False
    hub.notify_ready()
    time.sleep(0.2)
    assert len(notices(log)) == 1


def test_closing_to_the_tray_says_how_to_open_fa11y_again(make_hub, world):
    hub, log = make_hub(ui_args=("--emit", visible()))
    wait_for(lambda: hub.IsShown())
    hub.window_hidden(refocus_game=False)
    wait_for(lambda: notices(log))
    assert notices(log)[0]["message"] == "Running in the background. Press Left Alt + F to open."
    hub._shown = True
    hub.window_hidden(refocus_game=False)  # closing by hand tells you every time
    wait_for(lambda: len(notices(log)) == 2)


def test_minimizing_to_the_tray_notifies(make_hub, world):
    hub, log = make_hub(ui_args=("--emit", visible()))
    wait_for(lambda: hub.IsShown())
    hub._shown = False  # minimizing reports "not visible" before the window hides
    hub.window_hidden(refocus_game=False, was_shown=True)
    wait_for(lambda: notices(log))


def test_hiding_over_the_game_is_announced_once_per_session(make_hub, world):
    hub, log = make_hub(ui_args=("--emit", visible()))
    wait_for(lambda: hub.IsShown())
    world.running = True
    hub._on_fortnite_changed(True)
    wait_for(lambda: notices(log))
    for _ in range(2):
        hub._shown = True
        hub._on_fortnite_changed(True)
        hub._shown = True
        hub.window_hidden(refocus_game=True)  # Escape in the game
    time.sleep(0.3)
    assert len(notices(log)) == 1


def test_tray_notification_follows_its_setting(make_hub, world):
    world.flags["NotifyWhenHiddenToTray"] = False
    hub, log = make_hub(ui_args=("--emit", visible()))
    wait_for(lambda: hub.IsShown())
    hub.window_hidden(refocus_game=False)
    world.running = True
    hub._shown = True
    hub._on_fortnite_changed(True)
    wait_for(lambda: events(log, "ui.hide"))
    time.sleep(0.2)
    assert not notices(log)


def test_hiding_with_the_keybind_or_by_leaving_a_page_does_not_notify(make_hub, world):
    hub, log = make_hub(ui_args=("--emit", visible()))
    wait_for(lambda: hub.IsShown())
    hub.toggle()
    wait_for(lambda: events(log, "ui.hide"))
    time.sleep(0.2)
    assert not notices(log)


def test_no_tray_notice_when_fortnite_starts_with_the_window_already_hidden(make_hub, world):
    hub, log = make_hub(ui_args=("--emit", json.dumps([{"name": "ui.visibility", "data": {"visible": False}}])))
    world.running = True
    hub._on_fortnite_changed(True)
    wait_for(lambda: events(log, "fortnite.running"))
    time.sleep(0.2)
    assert not notices(log)
