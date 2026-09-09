"""Leave-match control recognition and guarded input sequencing."""
from unittest.mock import Mock

import numpy as np
import pytest

from lib.detection import exit_match as exit_ui


def frame(*names, inverted=False):
    image = np.full((1080, 1920), 42, dtype=np.uint8)
    for name in names:
        template = exit_ui._template(name)
        x, y, _, _ = exit_ui._REGIONS[name]
        if inverted:
            template = 255 - template
        image[y:y+template.shape[0], x:x+template.shape[1]] = template
    return image


@pytest.mark.parametrize('inverted', [False, True])
def test_sidebar_needs_both_icons_and_return_text(inverted):
    assert not exit_ui._sidebar(frame())
    assert not exit_ui._sidebar(frame('menu_tab'))
    image = frame('menu_tab', 'settings_tab', 'return_to_lobby', inverted=inverted)
    assert exit_ui._sidebar(image)
    assert exit_ui._find(image, 'return_to_lobby') is not None
    assert exit_ui._find(frame('menu_tab', 'settings_tab'), 'return_to_lobby') is None


def driver(monkeypatch, images, scale=(1., 1.)):
    observations = iter(images)
    last = images[-1]
    monkeypatch.setattr(exit_ui, '_capture', lambda: (next(observations, last), scale))
    monkeypatch.setattr(exit_ui, '_require_fortnite', lambda: None)
    clock = iter(range(100))
    monkeypatch.setattr(exit_ui.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(exit_ui.time, 'sleep', lambda _: None)
    click = Mock()
    key = Mock()
    speech = Mock()
    monkeypatch.setattr(exit_ui, 'instant_click', click)
    monkeypatch.setattr(exit_ui, 'press_key', key)
    monkeypatch.setattr(exit_ui.speaker, 'speak', speech)
    return click, key, speech


@pytest.mark.parametrize('already_open', [False, True])
def test_opens_sidebar_only_if_needed_and_never_sends_third_click(monkeypatch, already_open):
    social = frame('menu_tab', 'settings_tab')
    menu = frame('menu_tab', 'settings_tab', 'return_to_lobby')
    images = ([social, social, menu, frame()] if already_open
              else [frame(), social, social, menu, frame()])
    click, key, speech = driver(monkeypatch, images)
    assert exit_ui.exit_match() is True
    assert key.call_count == (0 if already_open else 1)
    assert click.call_count == 2
    speech.assert_called_with('Returning to lobby.')


def test_already_on_menu_clicks_return_once_and_scales_coordinates(monkeypatch):
    menu = frame('menu_tab', 'settings_tab', 'return_to_lobby')
    click, key, _ = driver(monkeypatch, [menu, menu, frame()], scale=(.5, .5))
    assert exit_ui.exit_match() is True
    target = exit_ui._find(menu, 'return_to_lobby')
    click.assert_called_once_with(round(target[0]*.5), round(target[1]*.5))
    key.assert_not_called()


def test_absent_sidebar_does_not_click_gameplay(monkeypatch):
    click, key, speech = driver(monkeypatch, [frame()])
    assert exit_ui.exit_match() is False
    key.assert_called_once_with('escape')
    click.assert_not_called()
    assert 'Could not find' in speech.call_args.args[0]


def test_lobby_menu_never_clicks_exit_game_without_return_label(monkeypatch):
    social = frame('menu_tab', 'settings_tab')
    click, key, speech = driver(monkeypatch, [social])
    assert exit_ui.exit_match() is False
    assert click.call_count == 1  # Only the Menu tab, never an unrecognized row.
    key.assert_not_called()
    assert 'Return to lobby was not found' in speech.call_args.args[0]


def test_focus_loss_prevents_all_input(monkeypatch):
    monkeypatch.setattr(exit_ui, 'get_active_window_title', lambda: 'Another app')
    click, key, speech = Mock(), Mock(), Mock()
    monkeypatch.setattr(exit_ui, 'instant_click', click)
    monkeypatch.setattr(exit_ui, 'press_key', key)
    monkeypatch.setattr(exit_ui.speaker, 'speak', speech)
    assert exit_ui.exit_match() is False
    click.assert_not_called()
    key.assert_not_called()
    assert 'active window' in speech.call_args.args[0]
