"""Epic Parties, chat and the push channel: parsing, signing and how the social manager announces them."""
import base64
import json
from datetime import datetime
from unittest.mock import Mock

import pytest

from lib.managers import social_manager as sm
from lib.utilities import epic_chat, epic_eos, epic_push
from lib.utilities.epic_social import JoinRequest, PartyInvite

USER_RECORD = {
    "current": {
        "id": "party1", "party_lead": "me", "chat_conversation_id": "ep-party1",
        "members": [
            {"account_id": "me", "connections": [
                {"id": "launcher", "deployment_id": "_", "meta": {}},
                {"id": "conn#sub-eas-private-1", "deployment_id": epic_eos.DEPLOYMENT_ID, "meta": {"game": "fn"}},
            ]},
            {"account_id": "pal", "connections": []},
        ],
    },
    "invites": [{"party_id": "party2", "sent_by": "joni", "sent_at": "2026-10-07T07:31:17.900Z"}],
    "join_requests": [{"requester_id": "joni", "requester_dn": "Joni the Red",
                       "sent_at": "2026-10-07T07:31:37.900Z", "expires_at": "2026-10-07T08:31:37.900Z"}],
}


def test_party_state_reads_party_invites_and_join_requests():
    state = epic_eos.parse_party_state(USER_RECORD)
    assert state.party.id == "party1"
    assert state.party.leader_id == "me"
    assert state.party.member_ids == ["me", "pal"]
    assert state.party.chat_conversation_id == "ep-party1"
    assert [(i.party_id, i.inviter_id) for i in state.invites] == [("party2", "joni")]
    assert [(r.requester_id, r.requester_name) for r in state.join_requests] == [("joni", "Joni the Red")]
    assert state.join_requests[0].expires_at.hour == 8


def test_party_state_without_a_party():
    state = epic_eos.parse_party_state({"current": None, "invites": [], "join_requests": []})
    assert state.party is None and state.invites == [] and state.join_requests == []


def test_joining_uses_the_running_games_connection():
    connection = epic_eos.game_connection(USER_RECORD["current"]["members"], "me")
    assert connection == {"id": "conn#sub-eas-private-1", "deployment_id": epic_eos.DEPLOYMENT_ID,
                          "meta": {"game": "fn"}}
    assert epic_eos.game_connection(USER_RECORD["current"]["members"], "pal") is None


def test_message_body_round_trips_and_its_signature_verifies():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    body = epic_chat.build_body("me", "conv1", "hello there")
    decoded = epic_chat.decode_body(body)
    assert decoded["msg"] == "hello there" and decoded["sid"] == "me" and decoded["rid"] == "conv1"
    assert decoded["cty"] == "Persistent" and len(decoded["mid"]) == 32
    key = Ed25519PrivateKey.generate()
    signature = key.sign(body.encode("ascii") + b"\0")
    key.public_key().verify(signature, body.encode("ascii") + b"\0")  # raises when it doesn't match


def test_history_entries_become_messages_and_system_entries_are_skipped():
    body = base64.b64encode(json.dumps({"msg": "hi", "sid": "joni"}).encode()).decode()
    page = [{"msgId": "m1", "senderId": "joni", "createdAt": "2026-10-07T07:15:07.866Z", "message": {"body": body}},
            {"type": "MEMBERS_JOIN"}]
    found = [m for m in (epic_chat.parse_message(item, "conv1") for item in page) if m]
    assert [(m.id, m.sender_id, m.text, m.conversation_id) for m in found] == [("m1", "joni", "hi", "conv1")]


def test_stomp_frames_split_into_command_headers_and_body():
    command, headers, body = epic_push.parse_frame("MESSAGE\ndestination:x/account/me\ncontent-type:application/json\n\n{\"a\":1}\0")
    assert command == "MESSAGE"
    assert headers["destination"] == "x/account/me"
    assert json.loads(body) == {"a": 1}


@pytest.fixture
def manager(monkeypatch):
    """A social manager with no files, no network and no speech."""
    monkeypatch.setattr(sm, "speaker", Mock())
    monkeypatch.setattr(sm.config_manager, "register", lambda *a, **k: None)
    monkeypatch.setattr(sm.SocialManager, "load_cache", lambda self: None)
    monkeypatch.setattr(sm.SocialManager, "load_favorites", lambda self: None)
    monkeypatch.setattr(sm.SocialManager, "save_cache", lambda self: None)
    monkeypatch.setattr(sm, "EpicSocial", lambda auth: Mock(auth=auth, last_party_error=""))
    m = sm.SocialManager(Mock(account_id="me", is_valid=True))
    monkeypatch.setattr(m, "_ensure_display_name", lambda name: name)
    m._show_notification = Mock()
    return m


def invite(account_id, name):
    return PartyInvite(party_id="p-" + account_id, invite_id=account_id, from_account_id=account_id,
                       from_display_name=name, created_at=datetime(2026, 1, 1))


def join_request(account_id, name):
    return JoinRequest(account_id=account_id, display_name=name, created_at=datetime(2026, 1, 1))


def test_pending_invites_at_startup_are_not_announced_but_new_ones_are(manager):
    manager.party_invites = [invite("old", "Old")]
    manager._check_for_new_items()
    manager._show_notification.assert_not_called()

    manager.party_invites = [invite("old", "Old"), invite("joni", "Joni")]
    manager.join_requests = [join_request("pal", "Pal")]
    manager._check_for_new_items()
    calls = [(c.args[0].__class__.__name__, c.args[1]) for c in manager._show_notification.call_args_list]
    assert calls == [("PartyInvite", "party_invite"), ("JoinRequest", "join_request")]

    manager._show_notification.reset_mock()
    manager._check_for_new_items()
    manager._show_notification.assert_not_called()


def test_an_invite_after_our_join_request_is_accepted_without_asking(manager, monkeypatch):
    manager._check_for_new_items()
    manager.outgoing_join_requests["joni"] = (datetime.now(), "Joni")
    started = []
    monkeypatch.setattr(sm.threading, "Thread", lambda target, args, daemon: Mock(start=lambda: started.append(args)))
    manager.party_invites = [invite("joni", "Joni")]
    manager._check_for_new_items()
    manager._show_notification.assert_not_called()
    assert started and started[0][1] == "Joni"


def test_a_withdrawn_invite_stops_being_the_current_notification(manager):
    pending = invite("joni", "Joni")
    manager.current_notification = (pending, "party_invite")
    manager.party_invites = []
    manager._drop_stale_notifications()
    assert manager.current_notification is None


def test_accepting_the_notification_answers_the_join_request(manager):
    request = join_request("pal", "Pal")
    manager.current_notification = (request, "join_request")
    manager.social_api.accept_join_request.return_value = True
    manager.accept_notification()
    manager.social_api.accept_join_request.assert_called_once_with("pal")


def test_a_pushed_message_from_a_friend_is_spoken_with_their_name(manager, monkeypatch):
    monkeypatch.setattr(manager, "_announce_chat_enabled", lambda: True)
    monkeypatch.setattr(manager, "name_for", lambda account_id: "Joni")
    body = base64.b64encode(json.dumps({"msg": "gg", "sid": "joni"}).encode()).decode()
    manager._on_push_event({"type": "social.chat.v1.NEW_MESSAGE", "payload": {
        "conversation": {"conversationId": "dm1", "type": "dm"},
        "message": {"body": body}, "senderId": "joni", "msgId": "m1"}})
    spoken = sm.speaker.speak.call_args.args[0]
    assert "Joni" in spoken and "gg" in spoken
    assert [m.text for m in manager.messages["dm1"]] == ["gg"]


def test_our_own_pushed_message_is_stored_but_not_spoken(manager, monkeypatch):
    monkeypatch.setattr(manager, "_announce_chat_enabled", lambda: True)
    body = base64.b64encode(json.dumps({"msg": "hello", "sid": "me"}).encode()).decode()
    manager._on_push_event({"payload": {"conversation": {"conversationId": "dm1", "type": "dm"},
                                        "message": {"body": body}, "senderId": "me", "msgId": "m2"}})
    sm.speaker.speak.assert_not_called()
    assert [m.text for m in manager.messages["dm1"]] == ["hello"]
