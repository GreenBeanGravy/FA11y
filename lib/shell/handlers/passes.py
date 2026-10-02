"""Requests for the pass browser (the pass tabs of the Quests and passes page).

Texts and button states come from lib.utilities.passes_view, shared with the wx
PassesView. The core keeps the account snapshot; the UI asks for what to show.
Claiming or buying is two steps: passes.prepare returns the summary the UI asks
the user to confirm, and passes.execute does it.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from lib.managers.quest_manager import quest_store
from lib.shell.bridge import handler
from lib.shell.handlers import quests
from lib.utilities import passes_view
from lib.utilities.epic_passes import EpicPassAPI, PassError, load_pass_catalog, pages

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_api: Optional[EpicPassAPI] = None
_api_auth = None
_snapshot: Optional[dict] = None
_metadata: Optional[dict] = None
_busy = False
_pending = None
_pending_token = 0


def _definitions() -> list:
    global _api
    with _lock:
        if _api is not None:
            return _api.definitions
    return load_pass_catalog()


def _api_for_account() -> EpicPassAPI:
    global _api, _api_auth, _snapshot
    from lib.utilities.epic_auth import get_epic_auth_instance
    auth = get_epic_auth_instance()
    with _lock:
        if _api is None or _api_auth is not auth:
            _api, _api_auth, _snapshot = EpicPassAPI(auth), auth, None
        return _api


def _cosmetics_metadata() -> dict:
    """Names and sets of cosmetics, for reward names. Loaded once; empty when unavailable."""
    global _metadata
    if _metadata is None:
        try:
            from lib.utilities.epic_auth import get_or_create_cosmetics_cache
            _metadata = passes_view.metadata_by_id(get_or_create_cosmetics_cache(force_refresh=False, owned_only=False))
        except Exception:
            logger.exception("Loading cosmetics for passes failed")
            return {}
    return _metadata


def _context(params: dict):
    """The definition, category, page and reward (or None) a request is about."""
    key = str(params.get("pass", ""))
    definition = next((d for d in _definitions() if d["key"] == key), None)
    if definition is None:
        raise ValueError("Unknown pass.")
    page_list = pages(definition)
    category, page = page_list[min(max(int(params.get("page", 0)), 0), len(page_list) - 1)]
    index = int(params.get("reward", -1))
    reward = page["rewards"][index] if 0 <= index < len(page["rewards"]) else None
    return definition, category, page, reward


BUSY = "An account request is in progress."


def _run(operation):
    """Run an account operation, one at a time. Returns (result, error); error is BUSY if one was running."""
    global _busy
    with _lock:
        if _busy:
            return None, BUSY
        _busy = True
    try:
        return operation(), None
    except PassError as exc:
        return None, str(exc)
    except Exception:
        logger.exception("Pass request failed")
        return None, "Pass data could not be loaded. Refresh to retry."
    finally:
        with _lock:
            _busy = False


@handler("passes.definitions")
def definitions(_params: dict) -> dict:
    return {"help": passes_view.HELP_TEXT,
            "passes": [{"key": d["key"], "name": d["name"], "pages": passes_view.page_choices(d)}
                       for d in _definitions()]}


@handler("passes.refresh")
def refresh(_params: dict) -> dict:
    global _snapshot
    api = _api_for_account()
    _cosmetics_metadata()
    result, error = _run(api.query)
    if error == BUSY:
        return {"message": BUSY, "busy": True}
    with _lock:
        _snapshot = result if not error else None
    return {"message": error or "Passes refreshed."}


@handler("passes.view")
def view(params: dict) -> dict:
    definition, category, page, reward = _context(params)
    with _lock:
        snapshot, busy = _snapshot, _busy
    metadata = _metadata or {}
    labels = passes_view.reward_labels(definition, category, page, snapshot, metadata)
    index = int(params.get("reward", -1)) if reward is not None else -1
    return {
        "status": passes_view.status_text(definition, snapshot),
        "rewards": labels,
        "reward": index,
        "details": passes_view.reward_details(definition, category, page, reward, snapshot, metadata),
        "buttons": passes_view.button_states(definition, category, page, reward, snapshot, busy),
        "set_notice": passes_view.SET_NOTICE,
        "busy": busy,
    }


@handler("passes.prepare")
def prepare(params: dict) -> dict:
    """Work out a claim, unlock or purchase. The answer's summary is what the user confirms."""
    global _pending, _pending_token
    definition, category, page, reward = _context(params)
    kind = str(params.get("kind", ""))
    if kind == "set" and category["id"] == "Set_SheerWill":
        return {"message": passes_view.SHEER_WILL_TEXT}
    with _lock:
        snapshot, busy = _snapshot, _busy
    if busy or not snapshot:
        return {}
    if kind == "reward" and reward is None:
        return {}
    state = snapshot["passes"][definition["key"]]
    selected = passes_view.claim_selection(kind, category, page, reward)
    ids = [r["id"] for r in selected if r["id"] not in state["claimed"]]
    try:
        action = _api_for_account().prepare(definition["key"], kind if kind in ("unlock", "purchase") else "claim",
                                            ids, snapshot)
    except PassError as exc:
        return {"message": str(exc)}
    with _lock:
        _pending = action
        _pending_token += 1
        token = _pending_token
    return {"summary": action.summary, "token": token}


@handler("passes.execute")
def execute(params: dict) -> dict:
    global _pending, _snapshot
    with _lock:
        action = _pending if params.get("token") == _pending_token else None
        if action is not None:
            _pending = None
    if action is None:
        return {"message": "That action is no longer available. Try again."}
    result, error = _run(lambda: _api_for_account().execute(action))
    if error == BUSY:
        return {"message": BUSY}
    message = error
    with _lock:
        if error:
            _snapshot = None
        else:
            _snapshot, message = result
    return {"message": message}


@handler("passes.quest_scope")
def quest_scope(params: dict) -> dict:
    """Limit the quest view to the quests linked to a reward (or to the whole pass)."""
    definition, _category, _page, reward = _context(params)
    with _lock:
        snapshot = _snapshot
    quest_snapshot = snapshot.get("quests") if snapshot else None
    if quest_snapshot:
        quest_store.replace_api(quest_snapshot)
    scope = passes_view.quest_scope(definition, snapshot, _metadata or {}, reward)
    return {"scope_id": quests.register_scope(scope["templates"], scope["heading"], scope["label"]),
            "heading": scope["heading"], "label": scope["label"]}
