"""The Fortnite page's requests and first-run setup, with the Fortnite manager and the hub mocked."""
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lib.fortnite import FortniteStatus, OperationResult
from lib.hub import fortnite_ops, setup_ops, sounds, status
from lib.shell.bridge import registry
from lib.shell.handlers import fortnite as handlers
from lib.shell.handlers import setup as setup_handlers
from lib.utilities import utilities


def call(method, params=None):
    return registry.handlers[method](params or {})


def wait_for(condition, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    raise AssertionError("timed out")


class FakeHub:
    def __init__(self):
        self.events = []
        self.services = SimpleNamespace(speak=Mock())
        self.finished = []

    def send(self, name, data=None):
        self.events.append((name, data))

    def named(self, name):
        return [d for n, d in self.events if n == name]

    def finish_onboarding(self, egl):
        self.finished.append(egl)


@pytest.fixture
def hub(monkeypatch):
    fake = FakeHub()
    monkeypatch.setattr(handlers, "get_hub", lambda: fake)
    monkeypatch.setattr(setup_handlers, "get_hub", lambda: fake)
    return fake


@pytest.fixture
def manager(monkeypatch, hub):
    mgr = Mock()
    mgr.status.return_value = FortniteStatus(installed=True, version="++Fortnite+Release-31.10-CL-1-Windows",
                                             install_path=r"D:\Fortnite", install_size_bytes=60 * 1024 ** 3,
                                             logged_in=True)
    monkeypatch.setattr("lib.fortnite.get_manager", lambda: mgr)
    monkeypatch.setattr(sounds, "ui", Mock())
    monkeypatch.setattr(handlers, "_last_status", None)
    monkeypatch.setattr(handlers, "_operation", None)
    monkeypatch.setattr(status, "_last_install_info", None)
    from lib.hub import game_watch
    monkeypatch.setattr(game_watch, "is_fortnite_running", lambda: False)
    return mgr


# Status ---------------------------------------------------------------------

def test_state_for_an_installed_copy(manager):
    result = call("fortnite.state")
    assert result["installed"] and result["checked"]
    assert result["summary"] == "31.10 · managed by FA11y · D:\\Fortnite · 60 GB"
    assert not result["show_signin"] and not result["show_install"] and not result["egl_only"]
    assert result["running"] is False and result["operation"] is None
    manager.status.assert_called_once_with(check_updates=False)
    assert status.last_install_info() is manager.status.return_value


def test_state_when_an_update_is_available(manager):
    manager.status.return_value.update_available = True
    manager.status.return_value.remote_version = "32.00"
    result = call("fortnite.state", {"check_updates": True})
    assert result["update_available"]
    assert result["summary"].endswith("update available (32.00)")
    assert result["message"] == "Update available: 32.00."
    manager.status.assert_called_once_with(check_updates=True)


def test_state_up_to_date_message(manager):
    assert call("fortnite.state", {"check_updates": True})["message"] == "Fortnite is up to date."


def test_state_for_the_epic_games_launcher_install(manager):
    manager.status.return_value = FortniteStatus(installed=False, egl_install_path=r"C:\EGL\Fortnite",
                                                 egl_version="++Fortnite+Release-30.00-CL-2-Windows", logged_in=True)
    result = call("fortnite.state")
    assert result["egl_only"] and not result["show_install"]
    assert result["summary"] == "Installed through the Epic Games Launcher."
    assert result["egl_text"] == (r"Fortnite is installed through the Epic Games Launcher at C:\EGL\Fortnite, "
                                  "version 30.00.")


def test_state_not_installed_and_signed_out(manager):
    manager.status.return_value = FortniteStatus(installed=False, logged_in=False)
    result = call("fortnite.state")
    assert result["summary"] == "Fortnite isn't installed."
    assert result["show_install"] and result["show_signin"]


def test_state_when_legendary_is_missing(manager):
    manager.status.return_value = FortniteStatus(legendary_available=False, error="legendary is missing")
    result = call("fortnite.state")
    assert result["summary"] == "legendary is missing"
    assert not result["show_install"] and not result["show_signin"]


def test_short_version():
    assert fortnite_ops.short_version("++Fortnite+Release-42.20-CL-58011042-Windows") == "42.20"
    assert fortnite_ops.short_version("weird") == "weird"
    assert fortnite_ops.size_text(0) == "" and fortnite_ops.size_text(5 * 1024 ** 3) == "5.0 GB"


# Operations ------------------------------------------------------------------

def test_an_operation_reports_progress_and_finishes(manager, hub):
    gate = threading.Event()

    def install(base, progress, cancel):
        progress(10.0, "Downloading 10%")
        gate.wait(5)
        return OperationResult(True, "Fortnite is installed.")

    manager.install.side_effect = install
    started = call("fortnite.install", {"base": r"D:\Games"})
    assert started["name"] == "Installing" and started["id"] > 0
    wait_for(lambda: hub.named("operation.progress"))
    assert hub.named("operation.progress")[0] == {"id": started["id"], "percent": 10.0, "message": "Downloading 10%"}
    # The page can find the operation again after the window restarts.
    assert call("fortnite.state")["operation"]["message"] == "Downloading 10%"
    gate.set()
    wait_for(lambda: hub.named("operation.finished"))
    assert hub.named("operation.finished")[0] == {"id": started["id"], "ok": True,
                                                  "message": "Fortnite is installed.", "cancelled": False}
    assert call("fortnite.state")["operation"] is None
    assert hub.named("home.changed")
    sounds.ui.assert_called_with("done")
    manager.install.assert_called_once()
    assert manager.install.call_args.args[0] == r"D:\Games"


def test_only_one_operation_at_a_time(manager):
    gate = threading.Event()
    manager.verify_and_repair.side_effect = lambda progress, cancel: (gate.wait(5), OperationResult(True, "Done."))[1]
    call("fortnite.verify")
    with pytest.raises(RuntimeError):
        call("fortnite.update")
    gate.set()
    wait_for(lambda: handlers._operation is None)


def test_cancel_sets_the_event_the_operation_sees(manager, hub):
    def move(target, progress, cancel):
        assert cancel.wait(5)
        return OperationResult(False, "Move cancelled.", cancelled=True)

    manager.move.side_effect = move
    call("fortnite.move", {"target": r"E:\Games"})
    assert call("fortnite.cancel") == {"cancelling": True}
    wait_for(lambda: hub.named("operation.finished"))
    finished = hub.named("operation.finished")[0]
    assert finished["cancelled"] is True and finished["ok"] is False
    sounds.ui.assert_called_with("error")
    assert call("fortnite.cancel") == {"cancelling": False}


def test_an_operation_that_raises_finishes_with_an_error(manager, hub):
    manager.uninstall.side_effect = OSError("disk gone")
    call("fortnite.uninstall")
    wait_for(lambda: hub.named("operation.finished"))
    finished = hub.named("operation.finished")[0]
    assert finished["ok"] is False and "disk gone" in finished["message"]
    assert handlers._operation is None


def test_progress_is_clamped_and_indeterminate_is_kept(manager, hub):
    def update(progress, cancel):
        progress(None, "Checking files")
        progress(250.0, "Almost")
        return OperationResult(True, "Updated.")

    manager.update.side_effect = update
    call("fortnite.update")
    wait_for(lambda: hub.named("operation.finished"))
    percents = [d["percent"] for d in hub.named("operation.progress")]
    assert percents == [None, 100.0]


def test_the_epic_games_launcher_choices(manager, hub):
    manager.status.return_value = FortniteStatus(installed=False, egl_install_path=r"C:\EGL\Fortnite")
    manager.import_egl.return_value = OperationResult(True, "FA11y now manages Fortnite.")
    manager.egl_sync.return_value = OperationResult(True, "Synced.")
    assert call("fortnite.import_egl")["name"] == "Setting up"  # fetches the install path itself
    wait_for(lambda: handlers._operation is None)
    assert manager.import_egl.call_args.args[0] == r"C:\EGL\Fortnite"
    assert call("fortnite.egl_sync")["name"] == "Syncing"
    wait_for(lambda: len(hub.named("operation.finished")) == 2)


def test_install_question_and_missing_folders(manager):
    question = call("fortnite.install_question", {"base": r"D:\Games"})["question"]
    assert question.startswith(r"Install Fortnite in D:\Games\Fortnite? It needs about 100 GB")
    for method in ("fortnite.install", "fortnite.move", "fortnite.install_question"):
        with pytest.raises(ValueError):
            call(method, {})


# Other actions ------------------------------------------------------------------

def test_play_uses_the_shared_launch_code_and_reports_a_failure(manager, hub, monkeypatch):
    import lib.hub.play as play
    seen = {}

    def fake_play(h, mgr=None, info=None, on_failed=None):
        seen.update(hub=h, manager=mgr, info=info)
        on_failed("It didn't start.")

    monkeypatch.setattr(play, "play_fortnite", fake_play)
    call("fortnite.state")
    call("fortnite.play")
    assert seen["hub"] is hub and seen["manager"] is manager
    assert seen["info"] is manager.status.return_value
    assert hub.named("fortnite.launch_failed") == [{"message": "It didn't start."}]
    hub.services.speak.assert_called_once_with("It didn't start.")
    sounds.ui.assert_called_with("error")


def test_sign_in_needs_the_epic_account_first(manager, monkeypatch):
    import lib.utilities.epic_auth as epic_auth
    monkeypatch.setattr(epic_auth, "get_epic_auth_instance", lambda: None)
    result = call("fortnite.sign_in")
    assert result == {"ok": False, "needs_account": True, "message": "Sign in to your Epic account first."}
    manager.login_with_exchange_code.assert_not_called()


def test_sign_in_with_the_account(manager, monkeypatch):
    import lib.utilities.epic_auth as epic_auth
    auth = SimpleNamespace(access_token="t", is_valid=True, get_exchange_code=lambda: "code")
    monkeypatch.setattr(epic_auth, "get_epic_auth_instance", lambda: auth)
    manager.login_with_exchange_code.return_value = OperationResult(True, "Signed in to Fortnite downloads.")
    result = call("fortnite.sign_in")
    assert result["ok"] and result["message"] == "Signed in to Fortnite downloads."
    manager.login_with_exchange_code.assert_called_once_with("code")


def test_open_folder_uses_the_last_status(manager, monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr("os.startfile", opened.append, raising=False)
    assert call("fortnite.open_folder") == {"ok": False}
    manager.status.return_value.install_path = str(tmp_path)
    call("fortnite.state")
    assert call("fortnite.open_folder") == {"ok": True}
    assert opened == [str(tmp_path)]


def test_launch_options_round_trip(manager, monkeypatch):
    saved = {}
    monkeypatch.setattr("lib.fortnite.load_launch_options",
                        lambda: SimpleNamespace(api="dx12", skip_splash=True, extra="-foo"))
    monkeypatch.setattr("lib.fortnite.save_launch_options", lambda options: saved.update(vars(options)) or True)
    options = call("fortnite.launch_options")
    assert (options["api"], options["skip_splash"], options["extra"]) == ("dx12", True, "-foo")
    assert [c["label"] for c in options["choices"]] == ["Default", "DirectX 11", "DirectX 12", "Performance mode"]
    assert call("fortnite.save_launch_options", {"api": "bogus", "skip_splash": False, "extra": "-x"}) == {"ok": True}
    assert saved == {"api": "default", "skip_splash": False, "extra": "-x"}


def test_mouse_detection_reports_through_an_event(manager, hub, monkeypatch):
    service = SimpleNamespace(target_device=None, describe=lambda: "No mouse selected.", callback=None)
    service.recapture_mouse = lambda on_done: setattr(service, "callback", on_done)
    monkeypatch.setattr("lib.mouse_passthrough.get_mouse_passthrough", lambda: service)
    assert call("fortnite.mouse") == {"available": True, "text": "No mouse selected.", "detected": False}
    assert call("fortnite.detect_mouse") == {"text": "Move the mouse you play with now."}
    service.callback(None)
    assert hub.named("fortnite.mouse_detected") == [
        {"available": True, "text": "No mouse moved, so nothing changed. No mouse selected.", "detected": False,
         "found": False}]
    sounds.ui.assert_called_with("error")
    service.target_device = object()
    service.describe = lambda: "Using Logitech mouse."
    service.callback(service.target_device)
    assert hub.named("fortnite.mouse_detected")[1]["text"] == "Using Logitech mouse."
    assert hub.named("fortnite.mouse_detected")[1]["found"] is True
    sounds.ui.assert_called_with("done")


def test_mouse_is_unavailable_when_the_service_fails(monkeypatch):
    def boom():
        raise RuntimeError("no driver")

    monkeypatch.setattr("lib.mouse_passthrough.get_mouse_passthrough", boom)
    info = call("fortnite.mouse")
    assert info["available"] is False and info["text"] == "Mouse passthrough isn't available: no driver"


# First-run setup ------------------------------------------------------------------

@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    path = tmp_path / "config.txt"
    monkeypatch.setattr(utilities, "CONFIG_FILE", str(path))
    utilities.clear_config_cache()
    yield path
    utilities.clear_config_cache()


def test_answers_become_the_same_config_keys_as_the_wx_steps():
    values = setup_ops.collect_values({"start_fortnite": True, "hide_on_launch": False, "nav_sounds": True,
                                       "close_action": "quit", "simplified_speech": True, "volume": 55,
                                       "dpi": 1600, "passthrough": False})
    assert values == {
        ("Toggles", "StartFortniteOnLaunch"): "true",
        ("Toggles", "HideHubWhenFortniteStarts"): "false",
        ("Toggles", "NavigationSounds"): "true",
        ("Hub", "CloseAction"): "quit",
        ("Toggles", "SimplifySpeechOutput"): "true",
        ("Audio", "MasterVolume"): "0.55",
        ("Values", "MousePassthroughDPI"): "1600",
        ("Toggles", "MousePassthrough"): "false",
    }


def test_bad_answers_fall_back_to_safe_values():
    values = setup_ops.collect_values({"close_action": "nonsense", "volume": "loud", "dpi": 5})
    assert values[("Hub", "CloseAction")] == "ask"
    assert values[("Audio", "MasterVolume")] == "1.0"
    assert values[("Values", "MousePassthroughDPI")] == "100"


def test_finishing_setup_saves_the_choices(hub, temp_config, monkeypatch):
    monkeypatch.setattr(sounds, "ui", Mock())
    monkeypatch.setattr(sounds, "set_enabled", Mock())
    monkeypatch.setattr(setup_handlers, "_audio", Mock())
    result = call("setup.finish", {"save": True, "egl": "manage",
                                   "answers": {"start_fortnite": True, "close_action": "quit", "dpi": 1200}})
    assert result == {"saved": True}
    config = utilities.read_config(use_cache=False)
    assert config.get("Toggles", "StartFortniteOnLaunch").startswith("true")
    assert config.get("Hub", "CloseAction").startswith("quit")
    assert config.get("Values", "MousePassthroughDPI").startswith("1200")
    assert config.get("Setup", "FirstRunComplete").startswith("true")
    assert hub.finished == ["manage"]
    sounds.ui.assert_called_with("done")


def test_skipping_setup_only_marks_it_complete(hub, temp_config, monkeypatch):
    monkeypatch.setattr(sounds, "ui", Mock())
    monkeypatch.setattr(sounds, "set_enabled", Mock())
    monkeypatch.setattr(setup_handlers, "_audio", Mock())
    call("setup.finish", {"save": False, "egl": "sync", "answers": {"start_fortnite": True}})
    config = utilities.read_config(use_cache=False)
    assert config.get("Setup", "FirstRunComplete").startswith("true")
    assert not config.has_option("Toggles", "StartFortniteOnLaunch") or \
        config.get("Toggles", "StartFortniteOnLaunch").startswith("false")
    assert hub.finished == [None]  # skipping never changes how Fortnite is managed
    sounds.ui.assert_not_called()


def test_the_fortnite_step_offers_the_choice_only_for_an_epic_games_launcher_install(manager):
    assert setup_ops.fortnite_step_state()["offer_choice"] is False
    manager.status.return_value = FortniteStatus(installed=False, egl_install_path=r"C:\EGL\Fortnite")
    state = call("setup.fortnite")
    assert state["offer_choice"] is True and r"C:\EGL\Fortnite" in state["message"]
    manager.status.return_value = FortniteStatus(installed=False)
    assert "After setup, open the Fortnite page" in call("setup.fortnite")["message"]
    manager.status.side_effect = RuntimeError("legendary broke")
    assert call("setup.fortnite")["message"].startswith("FA11y couldn't check for Fortnite.")


def test_signin_step_text(monkeypatch):
    import lib.utilities.epic_auth as epic_auth
    monkeypatch.setattr(epic_auth, "get_epic_auth_instance", lambda: None)
    assert call("setup.signin_state") == {"signed_in": False, "text": "Not signed in."}
    auth = SimpleNamespace(access_token="t", is_valid=True, display_name="Ann")
    monkeypatch.setattr(epic_auth, "get_epic_auth_instance", lambda: auth)
    assert call("setup.signin_state") == {"signed_in": True, "text": "Signed in as Ann."}


def test_setup_runs_through_the_remote_hub(monkeypatch):
    import wx
    from lib.app import state
    from lib.hub.services import HubServices
    from lib.shell.remote_hub import RemoteHub

    monkeypatch.setattr(wx, "CallAfter", lambda func, *args: func(*args))
    hub = RemoteHub.__new__(RemoteHub)
    hub.send = Mock()
    hub._setup_done = None
    hub._shown = True
    hub.services = HubServices(quit=Mock(), reload_config=Mock(), speak=Mock())
    done = Mock()
    hub.start_onboarding(done)
    assert state.wizard_open.is_set()
    hub.send.assert_called_with("setup.start", {"summon": True})
    hub.finish_onboarding("sync")
    done.assert_called_once_with("sync")
    assert not state.wizard_open.is_set()
    hub.finish_onboarding("sync")  # a second call does nothing
    done.assert_called_once()
    hub.show_page = Mock()
    hub.apply_egl_choice("manage")
    hub.show_page.assert_called_once_with("fortnite")
    hub.send.assert_called_with("fortnite.setup_choice", {"choice": "manage"})


def test_apply_setup_choice_goes_to_the_remote_hub():
    from lib.hub.pages.fortnite import apply_setup_choice
    hub = Mock(is_remote=True)
    apply_setup_choice(hub, "sync")
    hub.apply_egl_choice.assert_called_once_with("sync")
    other = Mock(is_remote=True)
    apply_setup_choice(other, None)
    other.show_page.assert_called_once_with("home", focus_sidebar=True)
