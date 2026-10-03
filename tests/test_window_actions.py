"""Keybinds that open a page of the FA11y window go through the hub's show_page."""
import time
from unittest.mock import Mock

import pytest

from lib.app import menu_actions, quest_actions, social_actions, state
from lib.hub import set_hub


@pytest.fixture
def hub():
    hub = Mock()
    set_hub(hub)
    yield hub
    set_hub(None)


def test_each_keybind_opens_its_page(hub, monkeypatch):
    monkeypatch.setattr(menu_actions, "_stop_active_pinger_for_menu", Mock())
    menu_actions.open_config_gui(Mock())
    menu_actions.open_locker_selector()
    quest_actions.open_quest_browser()
    social_actions.open_discovery_gui()
    opened = [call.args[0] for call in hub.show_page.call_args_list]
    assert opened == ["settings", "locker", "quests", "discover"]
    assert all(call.kwargs == {"summon": True} for call in hub.show_page.call_args_list)


def test_the_locker_keybind_stops_the_pinger(hub, monkeypatch):
    stop = Mock()
    monkeypatch.setattr(menu_actions, "_stop_active_pinger_for_menu", stop)
    menu_actions.open_locker_viewer()
    stop.assert_called_once()


def test_the_social_keybind_waits_for_data_then_opens_the_page(hub, monkeypatch):
    manager = Mock()
    manager.initial_data_loaded.is_set.return_value = False
    manager.wait_for_initial_data.return_value = True
    monkeypatch.setattr(state, "get_social_manager", lambda: manager)
    monkeypatch.setattr(state, "speaker", Mock())
    social_actions.open_social_menu()
    deadline = time.time() + 3
    while not hub.show_page.called and time.time() < deadline:
        time.sleep(0.02)
    hub.show_page.assert_called_once_with("social", summon=True)
    manager.wait_for_initial_data.assert_called_once()


def test_the_social_keybind_opens_the_page_when_signed_out(hub, monkeypatch):
    monkeypatch.setattr(state, "get_social_manager", lambda: None)
    monkeypatch.setattr(state, "speaker", Mock())
    social_actions.open_social_menu()
    deadline = time.time() + 3
    while not hub.show_page.called and time.time() < deadline:
        time.sleep(0.02)
    hub.show_page.assert_called_once_with("social", summon=True)


def test_keybinds_do_nothing_without_a_hub():
    set_hub(None)
    menu_actions.open_config_gui(Mock())
    quest_actions.open_quest_browser()
    social_actions.open_discovery_gui()
