"""Tests for the hub window: sidebar, page switching, settings, onboarding, update state."""
from unittest.mock import Mock

import pytest
import wx

from lib.utilities import utilities


@pytest.fixture
def app():
    return wx.App.Get() or wx.App(False)


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    """Point FA11y's config at a temp file so tests never touch config/config.txt."""
    path = tmp_path / "config.txt"
    monkeypatch.setattr(utilities, "CONFIG_FILE", str(path))
    utilities.clear_config_cache()
    yield path
    utilities.clear_config_cache()


@pytest.fixture
def hub(app, temp_config, monkeypatch):
    from lib.app import state
    from lib.hub import game_watch
    from lib.hub.frame import HubFrame, HubServices, PageSpec
    from lib.hub.page import HubPage
    from lib.hub.sidebar import SidebarEntry

    monkeypatch.setattr(state, "speaker", Mock())
    import lib.guis.welcome_wizard as welcome_wizard
    monkeypatch.setattr(welcome_wizard, "speaker", Mock())
    monkeypatch.setattr(game_watch.GameWatcher, "start", lambda self: None)
    monkeypatch.setattr(game_watch, "is_fortnite_running", lambda: False)

    class Simple(HubPage):
        def __init__(self, parent, hub, title):
            self.title = title
            super().__init__(parent, hub)
            self.shown = 0
            self.hidden = 0

        def build(self):
            self.add_heading()
            self.button = wx.Button(self, label=f"{self.title} button")
            self.content.Add(self.button)

        def on_show(self):
            self.shown += 1

        def on_hide(self):
            self.hidden += 1

    def spec(key, label, group=""):
        return PageSpec(SidebarEntry(key, label, "home", group),
                        lambda parent, hub, t=label: Simple(parent, hub, t))

    services = HubServices(quit=Mock(), reload_config=Mock(), speak=Mock())
    frame = HubFrame(services, [spec("home", "Home"), spec("a", "Alpha", "Group"),
                                spec("b", "Beta", "Group")])
    frame.start(show=False)
    yield frame
    frame.quit()
    frame.Destroy()
    app.ProcessPendingEvents()


def test_show_page_switches_and_calls_lifecycle(hub):
    home, alpha = hub.page("home"), hub.page("a")
    assert hub.current_page() is home and home.shown == 1
    hub.show_page("a")
    assert hub.current_page() is alpha
    assert home.hidden == 1 and alpha.shown == 1
    assert hub.sidebar.selected_key() == "a"
    assert hub.GetTitle() == "FA11y - Alpha"


def test_sidebar_selection_shows_page(hub):
    hub._on_sidebar_select("b")
    assert hub.current_page() is hub.page("b")


def test_cycle_page_wraps(hub):
    hub.show_page("b")
    hub.cycle_page(1)
    assert hub.current_page() is hub.page("home")
    hub.cycle_page(-1)
    assert hub.current_page() is hub.page("b")


def test_idle_prebuild_builds_every_page(hub):
    assert not hub.page("b").built
    for _ in range(3):
        hub._prebuild_on_idle(Mock())
    assert all(hub.page(k).built for k in ("home", "a", "b"))


def test_close_asks_first_time_and_remembers(hub, monkeypatch, temp_config):
    from lib.hub import frame as frame_module, settings

    class FakeDialog:
        def __init__(self, parent):
            self.remember = Mock(GetValue=lambda: True)

        def ShowModal(self):
            return wx.ID_YES

        def Destroy(self):
            pass

    monkeypatch.setattr(frame_module, "CloseChoiceDialog", FakeDialog)
    event = Mock(CanVeto=lambda: True)
    hub._on_close(event)
    event.Veto.assert_called_once()
    assert settings.close_action() == settings.CLOSE_TRAY
    hub.services.quit.assert_not_called()


def test_close_action_quit_quits(hub, temp_config):
    from lib.hub import settings
    settings.set_close_action(settings.CLOSE_QUIT)
    hub._on_close(Mock(CanVeto=lambda: True))
    hub.services.quit.assert_called_once()


def test_set_value_keeps_description(temp_config):
    from lib.hub import settings
    settings.set_value("Toggles", "NavigationSounds", "false")
    raw = utilities.read_config(use_cache=False).get("Toggles", "NavigationSounds")
    assert raw.startswith("false ") and '"' in raw
    assert settings.flag("NavigationSounds", True) is False


def test_key_display_name():
    from lib.hub.status import key_display_name
    assert key_display_name("lalt+lshift+f") == "Left Alt + Left Shift + F"
    assert key_display_name("num 5") == "Numpad 5"
    assert key_display_name("f9") == "F9"
    assert key_display_name("bracketright") == "Right Bracket"
    assert key_display_name("") == "no key"


def test_check_once_records_update(monkeypatch, tmp_path):
    from lib.app import updater_check
    from lib.hub import status
    monkeypatch.chdir(tmp_path)
    (tmp_path / "VERSION").write_text("1.2.3")
    monkeypatch.setattr(updater_check, "get_version", lambda: "1.2.4")
    assert updater_check.check_once() is True
    assert status.available_update() == "1.2.4"
    monkeypatch.setattr(updater_check, "get_version", lambda: "1.2.3")
    assert updater_check.check_once() is False
    assert status.available_update() is None
    monkeypatch.setattr(updater_check, "get_version", lambda: None)
    assert updater_check.check_once() is None


def test_onboarding_finish_writes_choices(hub, temp_config, monkeypatch):
    from lib.hub import onboarding
    monkeypatch.setattr(onboarding.FortniteStep, "_check", lambda self: None)
    done = Mock()
    hub.start_onboarding(done)
    panel = hub._onboarding
    startup = next(s for s in panel._steps if isinstance(s, onboarding.StartupStep))
    startup.auto_launch.SetValue(True)
    startup.close_action.SetSelection(2)
    panel._finish(save_choices=True)
    done.assert_called_once_with(None)
    config = utilities.read_config(use_cache=False)
    assert config.get("Toggles", "StartFortniteOnLaunch").startswith("true")
    assert config.get("Hub", "CloseAction").startswith("quit")
    assert config.get("Setup", "FirstRunComplete").startswith("true")
    assert hub._onboarding is None


def test_onboarding_skip_only_marks_complete(hub, temp_config, monkeypatch):
    from lib.hub import onboarding
    monkeypatch.setattr(onboarding.FortniteStep, "_check", lambda self: None)
    hub.start_onboarding(Mock())
    startup = next(s for s in hub._onboarding._steps if isinstance(s, onboarding.StartupStep))
    startup.auto_launch.SetValue(True)
    hub._onboarding._finish(save_choices=False)
    config = utilities.read_config(use_cache=False)
    assert config.get("Toggles", "StartFortniteOnLaunch").startswith("false")
    assert config.get("Setup", "FirstRunComplete").startswith("true")


def test_view_page_lifecycle_and_reset(app, hub):
    from lib.guis.view_host import EmbeddedView
    from lib.hub.view_page import ViewPage

    created = []

    class Probe(EmbeddedView):
        view_title = "Probe"

        def __init__(self, parent):
            super().__init__(parent)
            self.active = 0
            created.append(self)

        def activate(self):
            self.active += 1

        def deactivate(self):
            self.active -= 1

    page = ViewPage(hub.book, hub, "Probe", lambda host: Probe(host))
    page.ensure_built()
    page.on_show()
    assert len(created) == 1 and created[0].active == 1
    page.on_hide()
    page.on_show()
    assert len(created) == 1 and created[0].active == 1
    page.reset_view()
    assert created[0].active == 0
    page.on_show()
    assert len(created) == 2
    page.Destroy()


def test_view_page_unavailable_then_available(app, hub):
    from lib.guis.view_host import EmbeddedView
    from lib.hub.view_page import ViewPage

    available = {"yes": False}
    page = ViewPage(hub.book, hub, "Gate",
                    lambda host: EmbeddedView(host) if available["yes"] else None,
                    unavailable_text="Sign in first.")
    page.ensure_built()
    page.on_show()
    assert page.view is None and page._placeholder.GetLabel() == "Sign in first."
    available["yes"] = True
    page.on_show()
    assert page.view is not None
    page.Destroy()
