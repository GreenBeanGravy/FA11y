"""Social announcements follow the Simplify speech setting."""
from datetime import datetime
from unittest.mock import Mock

import pytest

from lib.app import speech
from lib.managers import social_manager as sm
from lib.utilities.epic_social import FriendRequest


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.setattr(sm, "speaker", Mock())
    monkeypatch.setattr(sm.config_manager, "register", lambda *a, **k: None)
    monkeypatch.setattr(sm.SocialManager, "load_cache", lambda self: None)
    m = sm.SocialManager.__new__(sm.SocialManager)
    m._ensure_display_name = lambda name: name
    return m


@pytest.mark.parametrize("on, spoken", [(True, "Request from Ann"), (False, "Friend request from Ann")])
def test_incoming_request_announcement(manager, monkeypatch, on, spoken):
    monkeypatch.setattr(speech, "_simple", on)
    req = FriendRequest(account_id="1", display_name="Ann", direction="inbound", created_at=datetime(2024, 1, 1))
    manager._announce_friend_request(req)
    sm.speaker.speak.assert_called_once_with(spoken)
