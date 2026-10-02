"""Tests for the settings editor's layout: readable labels, groups, and saving."""
from unittest.mock import Mock

import pytest
import wx

from lib.guis import config_layout
from lib.utilities import utilities


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    path = tmp_path / "config.txt"
    monkeypatch.setattr(utilities, "CONFIG_FILE", str(path))
    utilities.clear_config_cache()
    yield path
    utilities.clear_config_cache()


@pytest.fixture
def view_factory(temp_config, monkeypatch):
    import lib.guis.config_gui as config_gui
    monkeypatch.setattr(config_gui, "speaker", Mock())
    app = wx.App.Get() or wx.App(False)
    frame = wx.Frame(None)
    saved = []

    def make(tabs):
        config = utilities.Config()
        config.config = utilities.read_config(use_cache=False)
        view = config_gui.ConfigView(frame, config, saved.append, tabs=tabs)
        view._ensure_populated()
        for tab in view.tab_names:
            view._build_tab(tab)
        return view

    yield make, saved
    frame.Destroy()
    app.ProcessPendingEvents()


def test_setting_labels():
    assert config_layout.setting_label("AnnounceKillFeed") == "Announce kill feed"
    assert config_layout.setting_label("MousePassthroughDPI") == "Mouse DPI"
    assert config_layout.setting_label("StormPingInterval") == "Storm ping interval"
    assert config_layout.setting_label("Turn Left") == "Turn Left"
    assert config_layout.setting_label("ChestsVisitDistance", "MainGameObjects") == "Visit distance (meters)"
    assert config_layout.group_for("MainGameObjects", "TrackVisitsSupplyDrops") == "Supply drops"
    assert config_layout.group_for("Toggles", "AnnounceAmmo") == "Announcements"
    assert config_layout.group_for("Toggles", "SomethingNew") == config_layout.OTHER


def test_widgets_sit_in_named_groups(view_factory):
    make, _saved = view_factory
    view = make(["Toggles", "Values", "Advanced"])
    ammo = view.tab_variables["Toggles"]["AnnounceAmmo"]
    assert ammo.GetLabel() == "Announce ammo"
    assert isinstance(ammo.GetParent(), wx.StaticBox)
    assert ammo.GetParent().GetLabel() == "Announcements"
    # Groups follow the defined order on screen.
    panel = view.tabs["Toggles"]
    headings = [section.heading for section in panel._settings_sections.values()]
    boxes = [item.GetSizer().GetStaticBox().GetLabel() for item in panel.GetSizer().GetChildren()]
    assert boxes[:2] == ["Mouse and movement", "Announcements"]
    assert set(boxes) == set(headings)


def test_match_events_show_on_toggles_and_save_to_their_section(view_factory):
    make, saved = view_factory
    view = make(["Toggles"])
    death = view.tab_variables["MatchEvents"]["AnnounceDeath"]
    assert death.GetParent().GetLabel() == "Match events"
    death.SetValue(False)
    view._dirty_keys.add(("MatchEvents", "AnnounceDeath"))
    assert view.save_changes()
    value = saved[-1].get("MatchEvents", "AnnounceDeath")
    assert value.startswith("false")


def test_decimal_settings_use_number_boxes_and_keep_their_format(view_factory):
    make, saved = view_factory
    view = make(["Advanced"])
    delay = view.tab_variables["Advanced"]["RecenterDelay"]
    assert isinstance(delay, wx.SpinCtrlDouble)
    delay.SetValue(0.05)
    view._dirty_keys.add(("Advanced", "RecenterDelay"))
    assert view.save_changes()
    assert saved[-1].get("Values", "RecenterDelay").startswith("0.05 ")


def test_keybind_button_names_action_but_draws_key(view_factory):
    make, _saved = view_factory
    view = make(["Keybinds"])
    fire = view.tab_variables["Keybinds"]["Fire"]
    assert fire.GetLabel() == "Fire: Left Control"
    assert fire.display_text == "Left Control"
    assert fire.GetParent().GetLabel() == "Mouse and camera"
