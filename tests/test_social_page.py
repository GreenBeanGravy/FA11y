"""Social: what the lists show, the manager's view helpers, and the page's requests (Epic APIs mocked)."""
from datetime import datetime
from unittest.mock import Mock

import pytest

from lib.managers import social_manager as sm
from lib.shell.handlers import social as handlers
from lib.utilities.epic_social import Friend, FriendRequest, PartyMember


def friend(account_id, name):
    return Friend(account_id=account_id, display_name=name, status="offline", created_at=datetime(2024, 1, 1))


def request(account_id, name, direction):
    return FriendRequest(account_id=account_id, display_name=name, direction=direction,
                         created_at=datetime(2024, 1, 1))


def member(account_id, name, leader=False):
    return PartyMember(account_id=account_id, display_name=name, is_leader=leader, joined_at=datetime(2024, 1, 1))


@pytest.fixture
def manager(monkeypatch):
    """A social manager with no files, no network and no speech."""
    monkeypatch.setattr(sm, "speaker", Mock())
    monkeypatch.setattr(sm.config_manager, "register", lambda *a, **k: None)
    monkeypatch.setattr(sm.SocialManager, "load_cache", lambda self: None)
    monkeypatch.setattr(sm.SocialManager, "load_favorites", lambda self: None)
    monkeypatch.setattr(sm.SocialManager, "save_cache", lambda self: None)
    monkeypatch.setattr(sm.SocialManager, "save_favorites", lambda self: None)
    monkeypatch.setattr(sm, "EpicSocial", lambda auth: Mock(auth=auth))
    auth = Mock(account_id="me", is_valid=True)
    m = sm.SocialManager(auth)
    m.all_friends = [friend("1", "Zed"), friend("2", "amy"), friend("3", "Bob"), friend("4", "Cy")]
    m.favorite_friends = {"3"}
    m.incoming_requests = [request("5", "Ann", "inbound")]
    m.outgoing_requests = [request("6", "Out", "outbound")]
    m.party_members = [member("me", "Me", True), member("7", "Pal")]
    return m


def names(friends):
    return [f.display_name for f in friends]


# --- views ----------------------------------------------------------------

def test_friends_view_puts_favorites_first_then_sorts_by_name_ignoring_case(manager):
    assert names(manager.friends_view()) == ["Bob", "amy", "Cy", "Zed"]


def test_friends_view_can_show_favorites_only_and_search(manager):
    assert names(manager.friends_view(favorites_only=True)) == ["Bob"]
    assert names(manager.friends_view(search="Z")) == ["Zed"]
    assert names(manager.friends_view(favorites_only=True, search="z")) == []


def test_requests_view_picks_the_direction(manager):
    assert [r.account_id for r in manager.requests_view(True)] == ["5"]
    assert [r.account_id for r in manager.requests_view(False)] == ["6"]


def test_party_view_knows_whether_i_lead(manager):
    members, am_leader = manager.party_view()
    assert len(members) == 2 and am_leader
    manager.party_members = [member("me", "Me"), member("7", "Pal", True)]
    assert manager.party_view()[1] is False
    manager.party_members = []
    assert manager.party_view() == ([], False)


def test_count_texts_match_what_the_wx_view_says():
    assert sm.friends_count_text(3) == "3 friends"
    assert sm.friends_count_text(0) == "No friends"
    assert sm.friends_count_text(2, True) == "2 favorite friends"
    assert sm.friends_count_text(0, True) == "No favorite friends"
    assert sm.requests_count_text(1, True) == "1 incoming requests"
    assert sm.requests_count_text(0, True) == "No incoming friend requests"
    assert sm.requests_count_text(0, False) == "No outgoing friend requests"
    assert sm.party_count_text(2) == "2 party members"
    assert sm.party_count_text(0) == "Not in a party"


def test_friend_name_falls_back_to_the_id():
    assert sm.friend_name(friend("9", "")) == "9"
    assert sm.friend_name(friend("9", "Neo")) == "Neo"


def test_choose_user_prefers_the_exact_match_then_a_single_result():
    exact = {"match_type": "exact", "account_id": "a", "display_name": "A", "mutual_friends": 0}
    prefix = {"match_type": "prefix", "account_id": "b", "display_name": "B", "mutual_friends": 2}
    assert sm.SocialManager.choose_user([prefix, exact]) is exact
    assert sm.SocialManager.choose_user([prefix]) is prefix
    assert sm.SocialManager.choose_user([prefix, dict(prefix, account_id="c")]) is None
    assert sm.SocialManager.user_choice_label(prefix) == "B (2 mutual friends)"


def test_problems_with_actions(manager):
    assert manager.accept_problem(request("6", "Out", "outbound")) == "Cannot accept outgoing request"
    assert manager.accept_problem(request("5", "Ann", "inbound")) is None
    assert manager.promote_problem(member("me", "Me", True)) == "Member is already the leader"
    assert manager.promote_problem(member("7", "Pal")) is None
    assert manager.kick_problem(member("me", "Me", True)) == "Cannot kick yourself. Use Leave Party instead."
    assert manager.kick_problem(member("7", "Pal")) is None


def test_refresh_after_operation_picks_the_right_refresh(manager, monkeypatch):
    slow, fast = Mock(), Mock()
    monkeypatch.setattr(manager, "refresh_slow_data", slow)
    monkeypatch.setattr(manager, "refresh_fast_data", fast)
    manager.refresh_after_operation("friends")
    slow.assert_called_once()
    fast.assert_not_called()
    manager.refresh_after_operation("requests")
    fast.assert_called_once()


# --- change notifications ---------------------------------------------------

def test_listeners_hear_about_a_change_once(manager):
    heard = []
    manager.change_listeners.append(lambda: heard.append(1))
    manager.notify_changed()
    manager.notify_changed()
    assert heard == [1]
    manager.all_friends.append(friend("8", "New"))
    manager.notify_changed()
    assert heard == [1, 1]


def test_toggling_a_favorite_notifies(manager):
    heard = []
    manager.change_listeners.append(lambda: heard.append(1))
    manager.notify_changed()
    manager.toggle_favorite(manager.all_friends[0])
    assert heard == [1, 1]
    assert manager.is_favorite(manager.all_friends[0])


def test_a_failing_listener_does_not_stop_the_others(manager):
    heard = []

    def bad():
        raise RuntimeError("boom")

    manager.change_listeners.extend([bad, lambda: heard.append(1)])
    manager.notify_changed()
    assert heard == [1]


# --- the Me tab -------------------------------------------------------------

def test_account_info_without_auth_or_with_expired_auth(manager):
    manager.auth = None
    assert manager.account_info_texts()[1] == "Not authenticated."
    manager.auth = Mock(is_valid=False)
    assert manager.account_info_texts()[0].startswith("Authentication expired")


def test_account_info_text_for_each_box(manager):
    auth = Mock(is_valid=True)
    auth.get_account_info.return_value = {"displayName": "Neo", "email": "n@x.y", "id": "abc"}
    auth.get_player_stats.return_value = {
        "wins": 1234, "kills": 5, "matches_played": 10, "kd_ratio": 1.5, "win_rate": 12.345,
        "minutes_played": 120, "players_outlived": 7, "score": 99, "top3": 4,
        "mode_breakdown": {"solo": {"matches": 2, "wins": 1, "kills": 3, "kd_ratio": 3.0, "win_rate": 50.0}},
    }
    auth.get_ranked_progress.return_value = {}
    manager.auth = auth
    epic, fortnite, ranked = manager.account_info_texts()
    assert epic == "Username: Neo\nEmail: n@x.y\nAccount ID: abc"
    lines = fortnite.split("\n")
    assert lines[0] == "OVERALL CAREER STATS"
    assert "Total Wins: 1,234" in lines
    assert "Win Rate: 12.35%" in lines
    assert "Time Played: 120 minutes (2.0 hours / 0.1 days)" in lines
    assert "Solos: 1 wins, 3 kills, 2 matches (K/D: 3.00, WR: 50.0%)" in lines
    assert "Top 3: 4" in lines and "Top 5: 0" not in lines
    assert lines[-1] == "Total Score: 99"
    assert ranked == "No ranked data available.\nPlay ranked matches to see your progress here."


def test_account_info_private_and_error_states(manager):
    auth = Mock(is_valid=True)
    auth.get_account_info.return_value = {"displayName": "Neo", "email": "e", "id": "i"}
    auth.get_player_stats.return_value = {"private": True}
    auth.get_ranked_progress.return_value = None
    manager.auth = auth
    _, fortnite, ranked = manager.account_info_texts()
    assert fortnite == "Statistics are set to private.\nChange privacy settings in-game to view stats."
    assert ranked == "Couldn't load ranked stats. Try refreshing."
    auth.get_account_info.return_value = None
    assert manager.account_info_texts()[0].startswith("Couldn't load account information")
    auth.get_account_info.side_effect = RuntimeError("down")
    assert manager.account_info_texts() == ("Error: down",) * 3


def test_ranked_lines_show_progress_and_peak(manager, monkeypatch):
    monkeypatch.setattr("lib.utilities.ranked_modes.ordered_ranking_types", lambda data: list(data))
    monkeypatch.setattr("lib.utilities.ranked_modes.ranked_mode_name", lambda t: t.title())
    data = {"br": {"currentDivision": 3, "highestDivision": 5, "promotionProgress": 0.5}}
    assert manager._ranked_stats_lines(data) == ["Br: Silver I (50% to Silver II)", "  Peak: Silver III"]


# --- the page's requests ------------------------------------------------------

@pytest.fixture
def page(manager, monkeypatch):
    monkeypatch.setattr(handlers.state, "get_social_manager", lambda: manager)
    monkeypatch.setattr(handlers, "SETTLE_SECONDS", 0)
    monkeypatch.setattr(handlers, "_listening", None)
    return manager


def test_state_says_when_there_is_no_manager(monkeypatch):
    monkeypatch.setattr(handlers.state, "get_social_manager", lambda: None)
    assert handlers.social_state({}) == {"available": False}
    with pytest.raises(RuntimeError):
        handlers.social_friends({})


def test_state_starts_listening_for_changes_once(page, monkeypatch):
    sent = []
    monkeypatch.setattr(handlers, "get_hub", lambda: Mock(send=lambda name, data=None: sent.append(name)))
    assert handlers.social_state({}) == {"available": True}
    handlers.social_state({})
    assert page.change_listeners == [handlers._changed]
    page.all_friends.append(friend("8", "New"))
    page.notify_changed()
    assert sent == ["social.changed"]


def test_friends_request_returns_records_and_the_summary(page):
    result = handlers.social_friends({"favorites_only": False, "search": ""})
    assert result["summary"] == "4 friends"
    assert result["friends"][0] == {"id": "3", "name": "Bob", "favorite": True}
    assert handlers.social_friends({"favorites_only": True})["summary"] == "1 favorite friends"
    assert handlers.social_friends({"search": "nobody"})["summary"] == "No friends"


def test_a_refresh_asks_the_manager_first(page, monkeypatch):
    refresh = Mock()
    monkeypatch.setattr(page, "force_refresh_data", refresh)
    handlers.social_friends({"refresh": True})
    handlers.social_requests({"refresh": True})
    handlers.social_party({"refresh": True})
    assert [c.args for c in refresh.call_args_list] == [("friends",), ("requests",), ("party",)]


def test_requests_and_party_payloads(page):
    incoming = handlers.social_requests({"incoming": True})
    assert incoming == {"requests": [{"id": "5", "name": "Ann", "incoming": True}],
                        "summary": "1 incoming requests"}
    assert handlers.social_requests({"incoming": False})["requests"][0]["incoming"] is False
    party = handlers.social_party({})
    assert party["am_leader"] is True and party["summary"] == "2 party members"
    assert party["members"][0] == {"id": "me", "name": "Me", "leader": True, "me": True}


def test_account_info_request(page, monkeypatch):
    monkeypatch.setattr(page, "account_info_texts", lambda: ("a", "b", "c"))
    assert handlers.social_account_info({}) == {"epic": "a", "fortnite": "b", "ranked": "c"}


def test_friend_actions_call_the_manager(page, monkeypatch):
    for name in ("_invite_friend_to_party", "_request_to_join_party", "_remove_friend", "toggle_favorite",
                 "refresh_after_operation"):
        monkeypatch.setattr(page, name, Mock())
    handlers.invite({"id": "1"})
    page._invite_friend_to_party.assert_called_once_with(page.all_friends[0])
    handlers.request_join({"id": "2"})
    page._request_to_join_party.assert_called_once_with(page.all_friends[1])
    handlers.toggle_favorite({"id": "4"})
    page.toggle_favorite.assert_called_once_with(page.all_friends[3])
    handlers.remove_friend({"id": "1"})
    page._remove_friend.assert_called_once_with(page.all_friends[0])
    page.refresh_after_operation.assert_called_once_with("friends")
    with pytest.raises(ValueError):
        handlers.invite({"id": "gone"})


def test_adding_a_friend_sends_to_an_exact_match(page, monkeypatch):
    page.social_api.search_users.return_value = [
        {"match_type": "exact", "account_id": "a", "display_name": "Neo", "mutual_friends": 1},
        {"match_type": "prefix", "account_id": "b", "display_name": "Neon", "mutual_friends": 0}]
    send = Mock()
    monkeypatch.setattr(page, "_send_friend_request_by_account_id", send)
    assert handlers.find_users({"username": " Neo "}) == {"status": "sent"}
    page.social_api.search_users.assert_called_once_with("Neo")
    send.assert_called_once_with("a", "Neo")


def test_adding_a_friend_with_no_result_or_several(page, monkeypatch):
    send = Mock()
    monkeypatch.setattr(page, "_send_friend_request_by_account_id", send)
    page.social_api.search_users.return_value = []
    assert handlers.find_users({"username": "x"}) == {"status": "none"}
    page.social_api.search_users.return_value = [
        {"match_type": "prefix", "account_id": "b", "display_name": "B", "mutual_friends": 2},
        {"match_type": "prefix", "account_id": "c", "display_name": "C", "mutual_friends": 0}]
    result = handlers.find_users({"username": "x"})
    assert result["status"] == "choose"
    assert [u["label"] for u in result["users"]] == ["B (2 mutual friends)", "C (0 mutual friends)"]
    send.assert_not_called()
    assert handlers.send_request({"account_id": "c", "display_name": "C"}) == {"status": "sent"}
    send.assert_called_once_with("c", "C")


def test_accepting_and_declining_requests(page, monkeypatch):
    for name in ("_accept_friend_request", "_decline_friend_request", "refresh_after_operation"):
        monkeypatch.setattr(page, name, Mock())
    assert handlers.accept_request({"id": "5", "incoming": True}) == {}
    page._accept_friend_request.assert_called_once_with(page.incoming_requests[0])
    page.refresh_after_operation.assert_called_with("requests")
    # An outgoing request can't be accepted; the page says why.
    assert handlers.accept_request({"id": "6", "incoming": False}) == {"message": "Cannot accept outgoing request"}
    assert page._accept_friend_request.call_count == 1
    handlers.decline_request({"id": "6", "incoming": False})
    page._decline_friend_request.assert_called_once_with(page.outgoing_requests[0])


def test_party_actions(page, monkeypatch):
    for name in ("_promote_party_member", "kick_party_member", "leave_party"):
        monkeypatch.setattr(page, name, Mock())
    assert handlers.promote({"id": "me"}) == {"message": "Member is already the leader"}
    page._promote_party_member.assert_not_called()
    assert handlers.promote({"id": "7"}) == {}
    page._promote_party_member.assert_called_once_with(page.party_members[1])
    assert handlers.kick({"id": "me"})["message"].startswith("Cannot kick yourself")
    assert handlers.kick({"id": "7"}) == {}
    page.kick_party_member.assert_called_once_with("7")
    handlers.leave_party({})
    page.leave_party.assert_called_once()
