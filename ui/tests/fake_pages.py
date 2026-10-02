"""Canned answers for the Discover and Quests and passes pages, for fake_core.py.

The texts come from the same wx-free functions the real handlers call
(lib/utilities/discovery_ops.py, quest_view.py, passes_view.py), fed with data
shaped like Epic's responses, so the UI sees what the real core would send.
"""
from __future__ import annotations

import os
import sys
import time
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from lib.utilities import discovery_ops, passes_view, quest_view  # noqa: E402
from lib.utilities.epic_passes import PassAction, load_pass_catalog, pages  # noqa: E402


def island(code, title, creator="Epic", ccu=-1, description=None):
    return SimpleNamespace(link_code=code, title=title, creator_name=creator, global_ccu=ccu, description=description)


EPIC = [island("1234-1234-1234", "Zone Wars", ccu=2210), island("2345-2345-2345", "Box Fight", ccu=980),
        island("3456-3456-3456", "Reload", ccu=14500), island("4567-4567-4567", "Creative Hub")]
BROWSE = [island("5678-5678-5678", "Deathrun Deluxe", "Skyline", 6400), island("6789-6789-6789", "Pirate Cove", "Mapper", 310),
          island("7890-7890-7890", "Parkour Paradise", None)]


class FakeApi:
    def scrape_creator_maps(self, name, limit=50, start_page=1):
        return EPIC if name == "epic" else ([island("1111-2222-3333", "Cool Map", name, 12)] if name != "nobody" else [])

    def scrape_fortnite_gg(self, search_query="", limit=50):
        if search_query == "none":
            return []
        return BROWSE if not search_query else [i for i in BROWSE if search_query.lower() in i.title.lower()]

    def get_island_by_code(self, code):
        if code == "5678-5678-5678":
            return island(code, "Deathrun Deluxe", "Skyline", 6400, "Run, jump and avoid the traps.")
        return None


def _quest(qid, name, tags, state="Active", achieved=3, required=10):
    return dict(id=qid, template="Quest:" + qid, name=name, description="Do the thing.", state=state, expiry=None,
                expired=False,
                objectives=[dict(key="o", achieved=achieved, required=required, description="Do the thing", hidden=False)],
                completion_count=None, categories=list(tags), products=[], hidden=False, metadata_available=True,
                bundle_id=None, source="epic_account_api", updated_at=1)


QUEST_SNAPSHOT = {"updated_at": time.time(), "quests": [
    _quest("daily1", "Search chests in different matches", ["QuestCategory.BR.Daily"], achieved=2, required=5),
    _quest("daily2", "Eliminate opponents", ["QuestCategory.BR.Daily"], achieved=0, required=3),
    _quest("daily3", "Land at named locations", ["QuestCategory.BR.Daily"], state="Completed", achieved=1, required=1),
]}


class Pages:
    """State for the three pages: scopes and the pending pass action."""

    def __init__(self):
        self.api = FakeApi()
        self.definitions = load_pass_catalog()
        self.scopes = {}
        self.token = 0
        self.claimed = set()
        self.refreshed = False

    def _snapshot(self):
        return dict(passes={d["key"]: dict(active=True, purchased=d["key"] == "br", level=42, claimed=set(self.claimed))
                            for d in self.definitions},
                    balances={}, quests=[], updated_at=time.time(), account_id="acct")

    def _context(self, params):
        definition = next(d for d in self.definitions if d["key"] == params.get("pass"))
        page_list = pages(definition)
        category, page = page_list[min(max(int(params.get("page", 0)), 0), len(page_list) - 1)]
        index = int(params.get("reward", -1))
        return definition, category, page, page["rewards"][index] if 0 <= index < len(page["rewards"]) else None

    def answer(self, method, params, signed_in):
        if method == "discover.epic":
            return discovery_ops.load_epic(self.api)
        if method == "discover.browse":
            return discovery_ops.load_browse(self.api)
        if method == "discover.search":
            return discovery_ops.load_search(self.api, params.get("query", ""))
        if method == "discover.creator":
            return discovery_ops.load_creator(self.api, params.get("name", ""))
        if method == "discover.lookup":
            island_ = self.api.get_island_by_code(params.get("code", ""))
            return {"text": discovery_ops.lookup_text(island_, params.get("code", "")),
                    "announce": discovery_ops.lookup_speech(island_)}
        if method == "discover.copy":
            code = params.get("code", "")
            return {"announce": "No code available" if not code else
                    (f"Copied code: {code}" if discovery_ops.is_standard_code_format(code) else f"Copied code: {params.get('title')}")}
        if method == "discover.launch":
            return {"launched": bool(params.get("code")), "announce": "No code available"}

        if method == "quests.state":
            return {"signed_in": signed_in}
        if method == "quests.refresh":
            return {"signed_in": signed_in}
        if method == "quests.close":
            return {}
        if method == "quests.view":
            if not signed_in:
                return {"signed_in": False}
            scope = self.scopes.get(str(params.get("scope_id") or ""))
            snapshot = QUEST_SNAPSHOT
            if scope:
                snapshot = {"updated_at": QUEST_SNAPSHOT["updated_at"], "quests": QUEST_SNAPSHOT["quests"]}
            result = quest_view.render_quests(
                snapshot, mode=params.get("mode"), category=params.get("category"),
                status=params.get("status") or "Active", query=params.get("query") or "",
                expired=bool(params.get("expired")), templates=scope["templates"] if scope else None,
                scope_label=scope["label"] if scope else None)
            result.update(signed_in=True, revision=1, heading=scope["heading"] if scope else "")
            return result

        if method == "passes.definitions":
            return {"help": passes_view.HELP_TEXT,
                    "passes": [{"key": d["key"], "name": d["name"], "pages": passes_view.page_choices(d)}
                               for d in self.definitions]}
        if method == "passes.refresh":
            time.sleep(0.3)
            self.refreshed = True
            return {"message": "Passes refreshed."}
        if method == "passes.view":
            definition, category, page, reward = self._context(params)
            snapshot = self._snapshot() if self.refreshed else None
            return {
                "status": passes_view.status_text(definition, snapshot),
                "rewards": passes_view.reward_labels(definition, category, page, snapshot, {}),
                "reward": int(params.get("reward", -1)) if reward is not None else -1,
                "details": passes_view.reward_details(definition, category, page, reward, snapshot, {}),
                "buttons": passes_view.button_states(definition, category, page, reward, snapshot, False),
                "set_notice": passes_view.SET_NOTICE, "busy": False}
        if method == "passes.prepare":
            definition, category, page, reward = self._context(params)
            if params.get("kind") == "set" and category["id"] == "Set_SheerWill":
                return {"message": passes_view.SHEER_WILL_TEXT}
            self.token += 1
            action = PassAction("acct", definition["key"], "claim", ("x",), (), ("Test reward",), 0)
            return {"summary": action.summary, "token": self.token}
        if method == "passes.execute":
            return {"message": "Claimed Test reward."}
        if method == "passes.quest_scope":
            definition, category, page, reward = self._context(params)
            scope = passes_view.quest_scope(definition, None, {}, reward)
            scope_id = str(len(self.scopes) + 1)
            # The test quests aren't linked to a pass, so the scoped view shows them all.
            self.scopes[scope_id] = {"templates": {q["template"].lower() for q in QUEST_SNAPSHOT["quests"]},
                                     "heading": scope["heading"], "label": scope["label"]}
            return {"scope_id": scope_id, "heading": scope["heading"], "label": scope["label"]}
        raise KeyError(method)
