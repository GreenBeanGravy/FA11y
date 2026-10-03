"""Requests for the Social page: friends, friend requests, party and the account stats.

The lists come from the social manager's cached data (the manager polls Epic
in the background). Actions call the manager's methods, which speak their own
results through the core's speech.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from lib.app import state
from lib.hub import get_hub
from lib.managers.social_manager import (
    SocialManager, friend_name, friends_count_text, party_count_text, requests_count_text,
)
from lib.shell.bridge import handler

logger = logging.getLogger(__name__)

SETTLE_SECONDS = 0.5  # wait this long before reading back after an action

_listening: Optional[SocialManager] = None


def _manager() -> Optional[SocialManager]:
    manager = state.get_social_manager()
    global _listening
    if manager is not None and manager is not _listening:
        _listening = manager
        manager.change_listeners.append(_changed)
    return manager


def _require() -> SocialManager:
    manager = _manager()
    if manager is None:
        raise RuntimeError("Sign in on the Epic account page to use social features.")
    return manager


def _changed() -> None:
    hub = get_hub()
    if hub is not None:
        hub.send("social.changed")


def _friend_record(manager: SocialManager, friend) -> dict:
    return {"id": friend.account_id, "name": friend_name(friend), "favorite": manager.is_favorite(friend)}


def friends_payload(manager: SocialManager, favorites_only: bool, search: str) -> dict:
    friends = manager.friends_view(favorites_only, search)
    return {
        "friends": [_friend_record(manager, f) for f in friends],
        "summary": friends_count_text(len(friends), favorites_only),
    }


def requests_payload(manager: SocialManager, incoming: bool) -> dict:
    requests = manager.requests_view(incoming)
    return {
        "requests": [{"id": r.account_id, "name": friend_name(r), "incoming": r.direction == "inbound"}
                     for r in requests],
        "summary": requests_count_text(len(requests), incoming),
    }


def party_payload(manager: SocialManager) -> dict:
    members, am_leader = manager.party_view()
    my_id = manager.social_api.auth.account_id if manager.social_api else None
    return {
        "members": [{"id": m.account_id, "name": friend_name(m), "leader": bool(m.is_leader),
                     "me": m.account_id == my_id} for m in members],
        "am_leader": am_leader,
        "summary": party_count_text(len(members)),
    }


@handler("social.state")
def social_state(_params: dict) -> dict:
    """Whether there is a social manager (signed in). The UI shows the sign in text when there isn't."""
    manager = _manager()
    return {"available": manager is not None}


@handler("social.friends")
def social_friends(params: dict) -> dict:
    manager = _require()
    if params.get("refresh"):
        manager.force_refresh_data("friends")
    return friends_payload(manager, bool(params.get("favorites_only")), str(params.get("search") or ""))


@handler("social.requests")
def social_requests(params: dict) -> dict:
    manager = _require()
    if params.get("refresh"):
        manager.force_refresh_data("requests")
    return requests_payload(manager, bool(params.get("incoming", True)))


@handler("social.party")
def social_party(params: dict) -> dict:
    manager = _require()
    if params.get("refresh"):
        manager.force_refresh_data("party")
    return party_payload(manager)


@handler("social.account_info")
def social_account_info(_params: dict) -> dict:
    manager = _require()
    epic, fortnite, ranked = manager.account_info_texts()
    return {"epic": epic, "fortnite": fortnite, "ranked": ranked}


def _friend(manager: SocialManager, params: dict):
    friend = manager.find_friend(str(params.get("id", "")))
    if friend is None:
        raise ValueError("That friend is no longer in the list.")
    return friend


@handler("social.toggle_favorite")
def toggle_favorite(params: dict) -> dict:
    manager = _require()
    manager.toggle_favorite(_friend(manager, params))
    return {}


@handler("social.invite")
def invite(params: dict) -> dict:
    manager = _require()
    manager._invite_friend_to_party(_friend(manager, params))
    return {}


@handler("social.request_join")
def request_join(params: dict) -> dict:
    manager = _require()
    manager._request_to_join_party(_friend(manager, params))
    return {}


@handler("social.remove_friend")
def remove_friend(params: dict) -> dict:
    manager = _require()
    friend = _friend(manager, params)
    manager._remove_friend(friend)
    time.sleep(SETTLE_SECONDS)
    manager.refresh_after_operation("friends")
    return {}


@handler("social.find_users")
def find_users(params: dict) -> dict:
    """Search by name. status: none (no match), sent (one match, request sent) or choose (pick from users)."""
    manager = _require()
    username = str(params.get("username") or "").strip()
    users = manager.social_api.search_users(username)
    if not users:
        return {"status": "none"}
    chosen = manager.choose_user(users)
    if chosen is not None:
        return _send_request(manager, chosen["account_id"], chosen["display_name"])
    return {"status": "choose", "users": [
        {"account_id": u["account_id"], "display_name": u["display_name"],
         "label": manager.user_choice_label(u)} for u in users]}


def _send_request(manager: SocialManager, account_id: str, display_name: str) -> dict:
    manager._send_friend_request_by_account_id(account_id, display_name)
    time.sleep(2 * SETTLE_SECONDS)
    return {"status": "sent"}


@handler("social.send_request")
def send_request(params: dict) -> dict:
    manager = _require()
    return _send_request(manager, str(params.get("account_id", "")), str(params.get("display_name", "")))


@handler("social.accept_request")
def accept_request(params: dict) -> dict:
    manager = _require()
    request = manager.find_request(str(params.get("id", "")), incoming=bool(params.get("incoming", True)))
    if request is None:
        raise ValueError("That request is no longer in the list.")
    problem = manager.accept_problem(request)
    if problem:
        return {"message": problem}
    manager._accept_friend_request(request)
    time.sleep(SETTLE_SECONDS)
    manager.refresh_after_operation("requests")
    return {}


@handler("social.decline_request")
def decline_request(params: dict) -> dict:
    manager = _require()
    request = manager.find_request(str(params.get("id", "")), incoming=bool(params.get("incoming", True)))
    if request is None:
        raise ValueError("That request is no longer in the list.")
    manager._decline_friend_request(request)
    time.sleep(SETTLE_SECONDS)
    manager.refresh_after_operation("requests")
    return {}


def _member(manager: SocialManager, params: dict):
    member = manager.find_member(str(params.get("id", "")))
    if member is None:
        raise ValueError("That member is no longer in the party.")
    return member


@handler("social.promote")
def promote(params: dict) -> dict:
    manager = _require()
    member = _member(manager, params)
    problem = manager.promote_problem(member)
    if problem:
        return {"message": problem}
    manager._promote_party_member(member)
    time.sleep(2 * SETTLE_SECONDS)
    return {}


@handler("social.kick")
def kick(params: dict) -> dict:
    manager = _require()
    member = _member(manager, params)
    problem = manager.kick_problem(member)
    if problem:
        return {"message": problem}
    manager.kick_party_member(member.account_id)
    time.sleep(2 * SETTLE_SECONDS)
    return {}


@handler("social.leave_party")
def leave_party(_params: dict) -> dict:
    manager = _require()
    manager.leave_party()
    time.sleep(2 * SETTLE_SECONDS)
    return {}
