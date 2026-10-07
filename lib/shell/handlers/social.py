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


@handler("social.horde_rank")
def social_horde_rank(_params: dict) -> dict:
    """The Horde Rush rank box of the Me tab. Calls the Epic API."""
    from lib.utilities.epic_quests import QuestQueryError
    from lib.utilities.horde_ranks import HordeRankAPI, rank_text
    auth = getattr(_require(), "auth", None)
    if not auth or not auth.is_valid:
        return {"text": rank_text(error="Sign in through FA11y to load your Horde rank.")}
    try:
        text = rank_text(HordeRankAPI(auth).query())
    except QuestQueryError as exc:
        text = rank_text(error="Horde rank unavailable. " + str(exc))
    except Exception:
        logger.exception("Horde rank lookup failed")
        text = rank_text(error="Could not load your Horde rank. Refresh to retry.")
    return {"text": text}


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


# Party invites and join requests ----------------------------------------------------------


def invites_payload(manager: SocialManager) -> dict:
    invites, join_requests = manager.invites_view()
    count = len(invites) + len(join_requests)
    return {
        "invites": [{"id": i.from_account_id, "name": manager._ensure_display_name(i.from_display_name)}
                    for i in invites],
        "join_requests": [{"id": r.account_id, "name": manager._ensure_display_name(r.display_name)}
                          for r in join_requests],
        "summary": f"{count} pending" if count else "No party invites or join requests",
    }


@handler("social.invites")
def social_invites(params: dict) -> dict:
    manager = _require()
    if params.get("refresh"):
        manager.force_refresh_data("party")
    return invites_payload(manager)


def _answer(params: dict, accept: bool) -> dict:
    manager = _require()
    account_id = str(params.get("id", ""))
    if params.get("kind") == "join_request":
        request = manager.find_join_request(account_id)
        if request is None:
            return {"message": "That request is no longer pending."}
        (manager._accept_join_request if accept else manager._decline_join_request)(request)
    else:
        invite = manager.find_invite(account_id)
        if invite is None:
            return {"message": "That invite is no longer pending."}
        (manager._accept_party_invite if accept else manager._decline_party_invite)(invite)
    time.sleep(SETTLE_SECONDS)
    return {}


@handler("social.accept_invite")
def accept_invite(params: dict) -> dict:
    return _answer(params, accept=True)


@handler("social.decline_invite")
def decline_invite(params: dict) -> dict:
    return _answer(params, accept=False)


# Messages -----------------------------------------------------------------------------------

_chat_listening: Optional[SocialManager] = None


def _chat_changed(conversation_id: str) -> None:
    hub = get_hub()
    if hub is not None:
        hub.send("social.chat", {"id": conversation_id})


def _chat_manager() -> SocialManager:
    manager = _require()
    global _chat_listening
    if manager is not _chat_listening:
        _chat_listening = manager
        manager.chat_listeners.append(_chat_changed)
    return manager


def _eos_call(call):
    """Run an Epic call; an EosError becomes {"message": reason} for the page to speak."""
    from lib.utilities.epic_eos import EosError
    try:
        return call()
    except EosError as e:
        return {"message": str(e)}


def message_lines(manager: SocialManager, messages: list) -> list:
    me = manager.auth.account_id
    lines = []
    for message in messages:
        who = "You" if message.sender_id == me else manager.name_for(message.sender_id)
        when = message.sent_at.astimezone().strftime("%I:%M %p").lstrip("0") if message.sent_at else ""
        lines.append({"sender": who, "text": message.text, "time": when, "me": message.sender_id == me})
    return lines


@handler("social.chats")
def social_chats(_params: dict) -> dict:
    manager = _chat_manager()

    def load():
        rows = manager.conversations_view()
        return {"chats": [{"id": c.id, "type": c.type, "title": title, "members": c.members, "unread": c.unread}
                          for c, title in rows]}
    return _eos_call(load)


@handler("social.chat_messages")
def social_chat_messages(params: dict) -> dict:
    manager = _chat_manager()
    conversation_id = str(params.get("id", ""))
    kind = str(params.get("type") or "dm")
    return _eos_call(lambda: {"messages": message_lines(
        manager, manager.conversation_messages(conversation_id, kind))})


@handler("social.open_dm")
def social_open_dm(params: dict) -> dict:
    """The DM conversation with a friend, for the Message button on the Friends tab."""
    manager = _chat_manager()
    friend = _friend(manager, params)
    return _eos_call(lambda: {"id": manager.dm_conversation(friend.account_id), "type": "dm",
                              "title": friend_name(friend), "members": [manager.auth.account_id, friend.account_id]})


@handler("social.send_message")
def social_send_message(params: dict) -> dict:
    manager = _chat_manager()
    conversation_id = str(params.get("id", ""))
    members = [str(m) for m in params.get("members") or []]
    text = str(params.get("text") or "")
    party = params.get("type") == "epic_party"

    def send():
        manager.send_chat_message(conversation_id, members, text, party=party)
        return {}
    return _eos_call(send)
