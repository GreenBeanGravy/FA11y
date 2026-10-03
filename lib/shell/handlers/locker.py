"""Requests for the Locker page.

The page loads the cosmetics once (locker.load), then asks for one category at
a time as compact records and filters and sorts them itself. Everything it
does (favorites, equipping, loadouts) calls lib/managers/locker_manager.py,
the same code the wx view uses. Nothing here touches an Epic account except
when the user presses a button that does.
"""
from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional

from lib.hub import get_hub
from lib.managers import locker_manager as lm
from lib.shell.bridge import handler
from lib.shell.wx_thread import call_on_wx

logger = logging.getLogger(__name__)


def _auth():
    from lib.utilities.epic_auth import get_epic_auth_instance
    return get_epic_auth_instance()


class LockerSession:
    """The cosmetics loaded for the page, which of them the account owns, and the loadouts last fetched."""

    def __init__(self, cosmetics: List[dict], auth):
        self.cosmetics = cosmetics
        self.auth = auth
        self.owned_ids: set = set()
        self.owned_only = False
        self.loadouts: List[dict] = []
        self.lock = threading.RLock()

    @property
    def signed_in(self) -> bool:
        return bool(self.auth and self.auth.display_name)

    def find(self, cosmetic_id: str) -> Optional[dict]:
        for c in self.cosmetics:
            if c.get("id") == cosmetic_id:
                return c
        return None


_session: Optional[LockerSession] = None
_session_lock = threading.Lock()


def _require() -> LockerSession:
    if _session is None:
        raise RuntimeError("The locker isn't loaded yet.")
    return _session


def load_session() -> Optional[LockerSession]:
    """Load the cosmetics and (when signed in) what the account owns. None when the cosmetics can't be loaded."""
    from lib.utilities.epic_auth import get_or_create_cosmetics_cache
    cosmetics = get_or_create_cosmetics_cache(force_refresh=False, owned_only=False)
    if cosmetics is None:
        return None
    auth = _auth()
    session = LockerSession(cosmetics, auth)
    if session.signed_in:
        session.owned_only = True
        try:
            fetched = auth.fetch_owned_cosmetics()
        except Exception:
            logger.exception("Fetching owned cosmetics failed")
            fetched = None
        if fetched and fetched != "AUTH_EXPIRED":
            session.owned_ids = lm.apply_owned_ids(cosmetics, auth, fetched)
    return session


@handler("locker.load")
def locker_load(_params: dict) -> dict:
    """(Re)load everything. Slow: reads the cosmetics database and asks Epic what the account owns."""
    global _session
    session = load_session()
    with _session_lock:
        _session = session
    if session is None:
        return {"available": False}
    return {
        "available": True,
        "signed_in": session.signed_in,
        "name": (session.auth.display_name or "") if session.auth else "",
        "owned_only": session.owned_only,
        "categories": lm.CATEGORIES,
        "total": len(session.cosmetics),
    }


@handler("locker.category")
def locker_category(params: dict) -> dict:
    """One category's cosmetics, highest rarity first, with the special rows it has."""
    session = _require()
    name = str(params.get("name", ""))
    with session.lock:
        cosmetics = lm.category_cosmetics(session.cosmetics, name, session.owned_only, session.owned_ids)
        records = [lm.compact_record(c) for c in cosmetics]
    options = lm.category_options(name)
    special = {"random": lm.special_details("random"), "randomize": lm.special_details("randomize"),
               "unequip": lm.special_details("unequip", options["unequip"])}
    return {"name": name, "options": options, "special": special, "records": records}


@handler("locker.set_owned_only")
def locker_set_owned_only(params: dict) -> dict:
    session = _require()
    if not session.signed_in:
        return {"owned_only": False, "messages": ["Please log in first"], "expired": False, "error": None}
    with session.lock:
        outcome = lm.set_owned_only(session.cosmetics, session.auth, session.owned_ids, bool(params.get("value")))
        session.owned_only = outcome.owned_only
        session.owned_ids = outcome.owned_ids
    return {"owned_only": outcome.owned_only, "messages": outcome.messages,
            "expired": outcome.expired, "error": outcome.error}


@handler("locker.toggle_favorite")
def locker_toggle_favorite(params: dict) -> dict:
    session = _require()
    cosmetic = session.find(str(params.get("id", "")))
    if cosmetic is None:
        return {"result": "missing", "favorite": False}
    result = lm.toggle_favorite(session.auth, session.cosmetics, cosmetic)
    return {"result": result, "favorite": bool(cosmetic.get("favorite", False))}


def _equip_request(session: LockerSession, params: dict) -> lm.EquipRequest:
    kind = str(params.get("kind", "cosmetic"))
    category = str(params.get("category", ""))
    cosmetic = None
    candidates: List[dict] = []
    if kind == "cosmetic":
        cosmetic = session.find(str(params.get("id", "")))
        if cosmetic is None:
            raise ValueError("That cosmetic isn't in the list any more.")
    elif kind == "randomize":
        wanted = set(params.get("ids") or [])
        candidates = [c for c in session.cosmetics if c.get("id") in wanted]
    return lm.EquipRequest(category, kind, cosmetic, candidates)


@handler("locker.equip_plan")
def locker_equip_plan(params: dict) -> dict:
    """What an equip needs before it runs: an error, a slot question (ask), or ready with the slot and name."""
    session = _require()
    request = _equip_request(session, params)
    plan = lm.plan_equip(request)
    if "error" in plan:
        return {"error": plan["error"]}
    cosmetic_id = request.cosmetic.get("id") if request.cosmetic else None
    kind = "cosmetic" if request.kind == "randomize" else request.kind
    result = {"kind": kind, "id": cosmetic_id, "name": plan["name"], "slot": plan["slot"]}
    if plan["slot"] is None:
        prompt = lm.slot_prompt(plan["cosmetic_type"], plan["name"])
        if prompt is None:
            result["slot"] = 1
        else:
            result["ask"] = prompt
    return result


@handler("locker.equip")
def locker_equip(params: dict) -> dict:
    """Equip with the mouse in Fortnite. Blocks until done; the window should be out of the way."""
    session = _require()
    request = _equip_request(session, params)
    plan = lm.plan_equip(request)
    if "error" in plan:
        return {"ok": False, "name": "", "message": plan["error"]}
    slot = params.get("slot") or plan["slot"] or 1
    try:
        success, name = lm.run_equip(request, plan, int(slot))
    except Exception as e:
        logger.exception("Equipping failed")
        return {"ok": False, "name": plan["name"], "message": f"Error: {e}"}
    return {"ok": success, "name": name, "message": "" if success else lm.EQUIP_FAILED_MESSAGE}


@handler("locker.equipped")
def locker_equipped(_params: dict) -> dict:
    session = _require()
    if not session.auth or not session.auth.is_valid:
        return {"login": True}
    text = lm.equipped_text(session.auth, session.cosmetics)
    return {"text": text}


def _loadout_record(session: LockerSession, index: int, entry: dict) -> dict:
    return {
        "id": index,
        "name": entry.get("displayName", "(unnamed)"),
        "label": lm.loadout_label(entry),
        "local": lm.is_local_loadout(entry),
        "detail": lm.loadout_detail_text(entry, session.cosmetics),
    }


@handler("locker.loadouts")
def locker_loadouts(params: dict) -> dict:
    """Saved loadouts. fetch=true asks Epic again. status: ok, login, failed or none."""
    session = _require()
    if not session.auth or not session.auth.is_valid:
        return {"status": "login"}
    with session.lock:
        if params.get("fetch", True):
            loadouts = lm.load_loadouts(session.auth)
            if loadouts is None:
                return {"status": "failed"}
            if not loadouts:
                return {"status": "none"}
            session.loadouts = loadouts
        filter_type = str(params.get("filter") or "All")
        entries = lm.filter_loadouts(session.loadouts, filter_type)
        records = [_loadout_record(session, session.loadouts.index(e), e) for e in entries]
        return {"status": "ok", "total": len(session.loadouts), "filters": lm.loadout_filter_choices(),
                "records": records}


def _entry(session: LockerSession, params: dict) -> dict:
    index = int(params.get("id", -1))
    if not 0 <= index < len(session.loadouts):
        raise ValueError("That loadout isn't in the list any more.")
    return session.loadouts[index]


@handler("locker.loadout_api_prompt")
def locker_loadout_api_prompt(params: dict) -> dict:
    session = _require()
    return {"prompt": lm.loadout_api_prompt(_entry(session, params))}


@handler("locker.loadout_equip_api")
def locker_loadout_equip_api(params: dict) -> dict:
    session = _require()
    entry = _entry(session, params)
    return {"ok": lm.equip_loadout_via_api(session.auth, entry), "name": entry.get("displayName", "(unnamed)")}


@handler("locker.loadout_ui_plan")
def locker_loadout_ui_plan(params: dict) -> dict:
    """What equipping a loadout with the mouse would do: the question to confirm, or none when nothing can be equipped."""
    session = _require()
    entry = _entry(session, params)
    items = lm.loadout_ui_items(entry, session.cosmetics)
    if not items:
        return {"count": 0}
    return {"count": len(items), "prompt": lm.loadout_ui_prompt(entry, items)}


@handler("locker.loadout_equip_ui")
def locker_loadout_equip_ui(params: dict) -> dict:
    session = _require()
    entry = _entry(session, params)
    items = lm.loadout_ui_items(entry, session.cosmetics)
    lm.perform_loadout_ui_automation(items, entry.get("displayName", "(unnamed)"))
    return {}


@handler("locker.loadout_delete")
def locker_loadout_delete(params: dict) -> dict:
    session = _require()
    with session.lock:
        entry = _entry(session, params)
        if not lm.is_local_loadout(entry):
            return {"ok": False, "message": "This loadout is from Epic's servers and cannot be deleted from FA11y."}
        name = entry.get("displayName", "(unnamed)")
        ok = lm.delete_local_loadout(name)
        if ok:
            session.loadouts = [m for m in session.loadouts
                                if not (m.get("displayName") == name and m.get("source") == "local")]
    return {"ok": ok, "message": ""}


@handler("locker.save_choices")
def locker_save_choices(_params: dict) -> dict:
    session = _require()
    if not session.auth or not session.auth.is_valid:
        return {"login": True}
    return {"choices": [name for name, _schema in lm.SAVE_LOADOUT_CHOICES]}


@handler("locker.save_loadout")
def locker_save_loadout(params: dict) -> dict:
    """Save what is equipped. exists=true comes back when the name is taken and overwrite wasn't set."""
    session = _require()
    name = str(params.get("name") or "").strip()
    friendly_name, loadout_type = lm.SAVE_LOADOUT_CHOICES[int(params.get("choice", 0))]
    if lm.loadout_exists(name) and not params.get("overwrite"):
        return {"exists": True}
    return lm.save_loadout(session.auth, friendly_name, loadout_type, name)


@handler("locker.open_passes")
def locker_open_passes(_params: dict) -> dict:
    """Battle passes: the Quests and passes page."""
    _require()
    hub = get_hub()
    if hub is not None:
        hub.show_page("quests", summon=True)
    return {}
