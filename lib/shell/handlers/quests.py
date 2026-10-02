"""Requests for the Quests tab (and the quests a pass reward links to).

The wx QuestView and this module share lib.utilities.quest_view for what is
shown. Quest changes from match packets or an account refresh reach the UI as
the event quests.changed {revision}, a short moment after the last change.
"""
from __future__ import annotations

import itertools
import logging
import threading
from typing import Dict, Optional

from lib.hub import get_hub
from lib.managers.quest_manager import quest_store
from lib.shell.bridge import handler
from lib.utilities.epic_quests import EpicQuestAPI, QuestQueryError
from lib.utilities.quest_view import render_quests

logger = logging.getLogger(__name__)

CHANGE_DELAY = 0.4  # seconds to wait for more changes before telling the UI

_refresh_lock = threading.Lock()
_state_lock = threading.Lock()
_error: Optional[str] = None
_api = None
_api_auth = None
_scopes: Dict[str, dict] = {}
_scope_ids = itertools.count(1)
_timer: Optional[threading.Timer] = None


def _auth():
    from lib.utilities.epic_auth import get_epic_auth_instance
    return get_epic_auth_instance()


def _signed_in(auth) -> bool:
    return bool(auth and auth.access_token and auth.is_valid)


def _api_for(auth):
    global _api, _api_auth
    with _state_lock:
        if _api is None or _api_auth is not auth:
            _api, _api_auth = EpicQuestAPI(auth), auth
        return _api


def register_scope(templates, heading: str, label: str) -> str:
    """Remember a set of quest templates (from a pass reward) the quest view can be limited to."""
    with _state_lock:
        scope_id = str(next(_scope_ids))
        _scopes[scope_id] = {"templates": set(templates), "heading": heading, "label": label}
        while len(_scopes) > 20:
            _scopes.pop(next(iter(_scopes)))
    return scope_id


# Changes ------------------------------------------------------------------------

def _send_changed() -> None:
    global _timer
    _timer = None
    hub = get_hub()
    if hub is not None:
        hub.send("quests.changed", {"revision": quest_store.snapshot()[0]})


def _on_store_changed() -> None:
    global _timer
    with _state_lock:
        if _timer is not None:
            return
        _timer = threading.Timer(CHANGE_DELAY, _send_changed)
        _timer.daemon = True
        _timer.start()


quest_store.add_listener(_on_store_changed)


# Requests -----------------------------------------------------------------------

@handler("quests.state")
def state(_params: dict) -> dict:
    return {"signed_in": _signed_in(_auth())}


@handler("quests.refresh")
def refresh(_params: dict) -> dict:
    """Load the account's quests from Epic. error is set when that failed (older quests stay)."""
    global _error
    auth = _auth()
    if not _signed_in(auth):
        return {"signed_in": False}
    if not _refresh_lock.acquire(blocking=False):
        return {"signed_in": True, "busy": True}
    try:
        try:
            snapshot, error = _api_for(auth).query(), None
        except QuestQueryError as exc:
            snapshot, error = None, str(exc)
        except Exception:
            logger.exception("Quest query failed")
            snapshot, error = None, "Unable to load quests. Refresh to retry."
        if error:
            _error = error + " Previously loaded quests remain available."
            return {"signed_in": True, "error": _error}
        _error = None
        quest_store.replace_api(snapshot)
        return {"signed_in": True}
    finally:
        _refresh_lock.release()


@handler("quests.view")
def view(params: dict) -> dict:
    """The browser for these filters. scope_id limits it to the quests of a pass reward."""
    scope = _scopes.get(str(params.get("scope_id", ""))) if params.get("scope_id") else None
    if scope is None and not _signed_in(_auth()):
        return {"signed_in": False}
    revision, snapshot = quest_store.snapshot()
    result = render_quests(
        snapshot, mode=params.get("mode"), category=params.get("category"),
        status=str(params.get("status") or "Active"), query=str(params.get("query") or ""),
        expired=bool(params.get("expired")), templates=scope["templates"] if scope else None,
        scope_label=scope["label"] if scope else None, error=None if scope else _error)
    result.update(signed_in=True, revision=revision, heading=scope["heading"] if scope else "")
    return result


@handler("quests.close")
def close(_params: dict) -> dict:
    """Escape from a page the way the wx views close: hide over a game, else back to the sidebar."""
    hub = get_hub()
    if hub is not None:
        hub.leave_page()
    return {}
