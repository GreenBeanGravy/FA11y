"""Exercise tracking methods without starting audio or desktop monitors."""
import ast
import configparser
from pathlib import Path
from types import SimpleNamespace
from typing import Optional, Tuple
from unittest.mock import Mock

import pytest


def _method(filename, class_name, method_name, **globals_):
    tree = ast.parse(Path(filename).read_text(encoding="utf-8"))
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == class_name)
    method = next(node for node in cls.body
                  if isinstance(node, ast.FunctionDef) and node.name == method_name)
    namespace = {"Optional": Optional, "Tuple": Tuple, **globals_}
    exec(compile(ast.Module(body=[method], type_ignores=[]), filename, "exec"), namespace)
    return namespace[method_name]


def test_navigation_discards_previous_position_when_detection_fails():
    detect = Mock(side_effect=[(900, 500), None, RuntimeError("capture failed")])
    direction = Mock(return_value=("East", 90))
    update = _method("lib/detection/player_position.py", "PlayerPositionTracker",
                     "get_position_and_angle", find_player_position=detect,
                     find_minimap_icon_direction=direction)
    tracker = SimpleNamespace(last_position=None, last_angle=None)
    assert update(tracker) == ((900, 500), 90)
    assert update(tracker, force_update=True) == (None, None)
    tracker.last_position, tracker.last_angle = (900, 500), 90
    assert update(tracker, force_update=True) == (None, None)


def test_navigation_does_not_reuse_old_direction():
    update = _method("lib/detection/player_position.py", "PlayerPositionTracker",
                     "get_position_and_angle",
                     find_player_position=lambda: (950, 550),
                     find_minimap_icon_direction=lambda: (None, None))
    tracker = SimpleNamespace(last_position=(900, 500), last_angle=90)
    assert update(tracker) == ((950, 550), None)


def test_navigation_invalidates_position_on_config_change():
    changed = _method("lib/detection/player_position.py", "PlayerPositionTracker",
                      "_on_config_change", get_config_float=lambda *args: 0.5)
    tracker = SimpleNamespace(last_position=(900, 500), last_angle=90)
    changed(tracker, object())
    assert (tracker.last_position, tracker.last_angle) == (None, None)


def test_visit_tracker_discards_previous_position(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "lib.detection.player_position",
                        SimpleNamespace(find_player_position=lambda: None))
    update = _method("lib/detection/match_tracker.py", "MatchTracker",
                     "_update_player_position")
    tracker = SimpleNamespace(current_player_position=(900, 500))
    update(tracker)
    assert tracker.current_player_position is None


@pytest.mark.parametrize("map_name", ["main", "o_g", "reload_surfcity"])
def test_visit_settings_use_the_section_saved_by_the_settings_screen(map_name):
    cfg = configparser.ConfigParser()
    cfg[f"{map_name.title()}GameObjects"] = {
        "TrackVisitsChests": 'false "Disabled"',
        "AnnounceCampfiresVisits": 'true "Enabled"',
        "ChestsVisitDistance": '5 "Metres"',
    }
    boolean = _method("lib/detection/match_tracker.py", "MatchTracker",
                      "_get_config_boolean_for_map")
    floating = _method("lib/detection/match_tracker.py", "MatchTracker",
                       "_get_config_float_for_map")
    assert boolean(None, cfg, "TrackVisitsChests", map_name, True) is False
    assert boolean(None, cfg, "AnnounceCampfiresVisits", map_name, False) is True
    assert floating(None, cfg, "ChestsVisitDistance", map_name, 8) == 5


def test_legacy_flat_visit_settings_still_work():
    cfg = configparser.ConfigParser()
    cfg["GameObjects"] = {"TrackVisitsChests": "false", "ChestsVisitDistance": "4"}
    boolean = _method("lib/detection/match_tracker.py", "MatchTracker",
                      "_get_config_boolean_for_map")
    floating = _method("lib/detection/match_tracker.py", "MatchTracker",
                       "_get_config_float_for_map")
    assert boolean(None, cfg, "TrackVisitsChests", "main", True) is False
    assert floating(None, cfg, "ChestsVisitDistance", "main", 8) == 4
