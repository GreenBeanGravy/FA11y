"""Regression from the visible 42.30 minimap captured on 2026-10-02."""
from pathlib import Path

import cv2
import numpy as np

from lib.detection import ppi


def test_live_main_map_capture_matches_through_complete_ppi_path(monkeypatch):
    capture = cv2.imread(str(Path(__file__).parent / "fixtures/ppi/main_4230_minimap.png"),
                         cv2.IMREAD_GRAYSCALE)
    assert capture is not None
    manager = ppi.MapManager()
    monkeypatch.setattr(ppi, "map_manager", manager)
    monkeypatch.setattr(ppi, "_cached_current_map", "main")
    monkeypatch.setattr(ppi, "capture_map_screen", lambda map_name: capture)
    monkeypatch.setattr(ppi, "_resolve_matcher_config",
                        lambda map_name: ppi.MatcherConfig.from_name("sift"))

    position = ppi.find_player_position()
    assert position is not None
    assert np.linalg.norm(np.array(position) - [1052, 822]) <= 2
    assert ppi.last_match_failure is None
    assert ppi.last_match_outcome.num_inliers >= 100

    # A missing terrain view must not produce a substitute position.
    monkeypatch.setattr(ppi, "capture_map_screen", lambda map_name: np.zeros_like(capture))
    assert ppi.find_player_position() is None
