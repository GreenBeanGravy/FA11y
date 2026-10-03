from pathlib import Path

import cv2
import numpy as np

from lib.detection import ppi
from lib.monitors import storm_monitor as storm


def _monitor():
    monitor = storm.StormMonitor.__new__(storm.StormMonitor)
    monitor._cached_current_map = "main"
    monitor._color_ref = None
    monitor._color_ref_name = None
    monitor.min_contour_area = 3000
    return monitor


def test_horde_screenshot_targets_inner_storm_boundary(monkeypatch):
    image = cv2.imread(str(Path(__file__).parent / "fixtures/storm/horde_rush_minimap.png"))
    capture = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    monkeypatch.setattr(ppi, "map_manager", ppi.MapManager())
    monkeypatch.setattr(ppi, "_cached_current_map", "main")
    monkeypatch.setattr(ppi, "capture_map_screen",
                        lambda name: cv2.cvtColor(capture, cv2.COLOR_RGB2GRAY))
    monkeypatch.setattr(ppi, "_resolve_matcher_config",
                        lambda name: ppi.MatcherConfig.from_name("sift"))
    monkeypatch.setattr(ppi, "last_matched_region", None)
    assert ppi.find_player_position() is not None
    monkeypatch.setattr(storm, "capture_region", lambda *args: capture)
    monitor = _monitor()
    point = monitor.detect_storm_on_minimap()
    assert point is not None
    local = np.array(point) - [1637, 33]
    # The previous external-only search selected (241, 240), at the corner.
    assert np.linalg.norm(local - [125, 125]) < 45
    assert 90 < local[0] < 150 and 140 < local[1] < 180


def test_close_west_storm_is_ahead_in_audio_coordinates(monkeypatch):
    image = cv2.imread(str(Path(__file__).parent / "fixtures/storm/horde_rush_close_west.png"))
    capture = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    monkeypatch.setattr(ppi, "map_manager", ppi.MapManager())
    monkeypatch.setattr(ppi, "_resolve_matcher_config",
                        lambda name: ppi.MatcherConfig.from_name("sift"))
    monkeypatch.setattr(storm, "capture_region", lambda *args: capture)
    monitor = _monitor()
    point = monitor.detect_storm_on_minimap()
    assert point is not None
    player = monitor._detected_player_pos
    target = monitor.convert_minimap_to_fullmap_coords(point, player)
    distance, angle = storm.SpatialAudio.calculate_distance_and_angle(player, 271, target)
    assert abs(angle) < 10
    assert distance < 35
    # The old conversion centered on (1750, 170), moving this target right.
    old_target = (player[0] + (point[0] - 1750) * .5,
                  player[1] + (point[1] - 170) * .5)
    _, old_angle = storm.SpatialAudio.calculate_distance_and_angle(player, 271, old_target)
    assert old_angle > 40
    # Current geometry does not depend on a separately cached player position.
    assert monitor.convert_minimap_to_fullmap_coords(point, (0, 0)) == target


def test_failed_alignment_invalidates_old_storm_transform(monkeypatch):
    monitor = _monitor()
    monitor._capture_to_map = np.eye(3)
    monitor._detected_player_pos = (900, 500)
    monkeypatch.setattr(monitor, "_get_color_ref", lambda: np.zeros((926, 866, 3), np.uint8))
    monkeypatch.setattr(ppi, "find_best_match", lambda capture: None)
    assert monitor._get_ref_aligned(np.zeros((250, 250, 3), np.uint8)) is None
    assert monitor._detected_player_pos is None
    assert monitor.convert_minimap_to_fullmap_coords((1700, 150), (900, 500)) is None


def test_full_storm_does_not_target_capture_border(monkeypatch):
    capture = np.zeros((250, 250, 3), np.uint8)
    monitor = _monitor()
    monkeypatch.setattr(storm, "capture_region", lambda *args: capture)
    monkeypatch.setattr(monitor, "_get_ref_aligned", lambda image: capture)
    monkeypatch.setattr(monitor, "detect_storm_mask",
                        lambda *args: (np.full((250, 250), 255, np.uint8), None))
    assert monitor.detect_storm_on_minimap() is None


def test_storm_crossing_minimap_still_finds_visible_boundary(monkeypatch):
    capture = np.zeros((250, 250, 3), np.uint8)
    mask = np.zeros((250, 250), np.uint8)
    mask[:, :75] = 255
    monitor = _monitor()
    monkeypatch.setattr(storm, "capture_region", lambda *args: capture)
    monkeypatch.setattr(monitor, "_get_ref_aligned", lambda image: capture)
    monkeypatch.setattr(monitor, "detect_storm_mask", lambda *args: (mask, None))
    assert monitor.detect_storm_on_minimap() == (1711, 158)
