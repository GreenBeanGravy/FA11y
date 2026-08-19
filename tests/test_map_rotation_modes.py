from pathlib import Path

from lib.utilities import map_rotation
from lib.utilities.map_rotation import CurrentReloadMap, RotationEntry


def test_detects_latest_ranked_reload_selection(tmp_path):
    log = tmp_path / "FortniteGame.log"
    log.write_text(
        "Selected Island:\n"
        "    LinkId [Mnemonic [playlist_other]]\n"
        "    /Fortnite.com/Matchmaking:Ranked [Ranked]\n"
        "[2026.08.19] next record\n"
        "Selected Island:\n"
        "    LinkId [Mnemonic [playlist_experience_reload]]\n"
        "    /Fortnite.com/Matchmaking:Ranked [Unranked]\n",
        encoding="utf-8",
    )

    assert map_rotation.detect_reload_ranked_state(log) is False


def test_ranked_and_unranked_use_separate_urls(monkeypatch):
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"rotation"

    def fake_urlopen(request, timeout):
        seen.append(request.full_url)
        return Response()

    monkeypatch.setattr(map_rotation.urllib.request, "urlopen", fake_urlopen)

    assert map_rotation._fetch_rotation_html(True) == "rotation"
    assert map_rotation._fetch_rotation_html(False) == "rotation"
    assert seen == [
        map_rotation.FORTNITE_GG_RANKED_URL,
        map_rotation.FORTNITE_GG_UNRANKED_URL,
    ]


def test_single_unranked_current_card_is_parsed():
    data = map_rotation._extract_rotation_from_cards(
        "<div class='current-card'><h2 class='current-name'>Springfield</h2></div>"
    )
    assert data["maps"] == [{"name": "Springfield", "duration": 86400}]
    assert data["cycle"] == 86400


def test_announcement_names_mode_and_single_active_map(monkeypatch):
    entry = RotationEntry("Springfield", 1200, 0, 1200, True, "reload_springfield")
    state = CurrentReloadMap(entry, entry, [entry])
    monkeypatch.setattr(map_rotation, "current_reload_map", lambda ranked: state)

    assert map_rotation.speech_announcement(False) == (
        "Current Unranked Reload map: Springfield. "
        "This is the only active map."
    )


def test_mode_caches_are_distinct():
    assert map_rotation._cache_path(True) != map_rotation._cache_path(False)
