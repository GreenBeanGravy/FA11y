"""Regression tests for Habanero ranked-track discovery."""
from unittest.mock import MagicMock

from lib.utilities import epic_auth
from lib.utilities.epic_auth import EpicAuth
from lib.utilities.ranked_modes import ordered_ranking_types, ranked_mode_name


def _auth():
    auth = EpicAuth.__new__(EpicAuth)
    auth.access_token = "test-token"
    auth.account_id = "test-account"
    auth.invalidate_auth = MagicMock()
    return auth


def _response(status, payload):
    response = MagicMock(status_code=status)
    response.json.return_value = payload
    return response


def test_ranked_progress_discovers_combined_reload_track(monkeypatch):
    tracks = _response(200, [
        {"rankingType": "ranked-blastberry-combined"},
        {"rankingType": "ranked-feral"},
    ])
    progress = _response(200, [{
        "rankingType": "ranked-blastberry-combined",
        "currentDivision": 7,
        "highestDivision": 8,
        "promotionProgress": 0.42,
        "trackguid": "reload-current",
        "lastUpdated": "2026-08-19T00:00:00Z",
    }])
    monkeypatch.setattr(epic_auth.requests, "get", MagicMock(return_value=tracks))
    post = MagicMock(return_value=progress)
    monkeypatch.setattr(epic_auth.requests, "post", post)

    result = _auth().get_ranked_progress()

    assert list(result) == ["ranked-blastberry-combined"]
    assert result["ranked-blastberry-combined"]["trackguid"] == "reload-current"
    assert post.call_args.kwargs["params"]["rankingType"] == "ranked-blastberry-combined"


def test_ranked_progress_logs_non_success_and_continues(monkeypatch, caplog):
    monkeypatch.setattr(
        epic_auth.requests, "get", MagicMock(return_value=_response(503, {}))
    )
    monkeypatch.setattr(
        epic_auth.requests, "post", MagicMock(return_value=_response(404, {}))
    )

    assert _auth().get_ranked_progress() == {}
    assert "Ranked-track discovery failed with HTTP 503" in caplog.text
    assert "failed with HTTP 404" in caplog.text


def test_ranked_progress_uses_fallback_when_discovery_raises(monkeypatch, caplog):
    monkeypatch.setattr(
        epic_auth.requests, "get", MagicMock(side_effect=RuntimeError("offline"))
    )
    post = MagicMock(return_value=_response(200, []))
    monkeypatch.setattr(epic_auth.requests, "post", post)

    assert _auth().get_ranked_progress() == {}
    assert post.call_count > 1
    assert "using fallback identifiers" in caplog.text


def test_combined_reload_has_friendly_name_and_display_order():
    data = {
        "ranked-figment-build": {},
        "ranked-blastberry-combined": {},
    }
    assert ranked_mode_name("ranked-blastberry-combined") == "Reload"
    assert list(ordered_ranking_types(data)) == [
        "ranked-blastberry-combined",
        "ranked-figment-build",
    ]
