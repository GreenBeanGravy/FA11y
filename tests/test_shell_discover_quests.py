"""Discover, quests and passes: the wx-free logic and the requests the new window makes. Epic is mocked."""
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lib.app import state
from lib.hub import set_hub
from lib.managers.quest_manager import QuestStore, quest_store
from lib.shell.handlers import discover, passes, quests
from lib.utilities import discovery_ops, passes_view, quest_view
from lib.utilities.epic_passes import PassAction, PassError, load_pass_catalog, pages
from lib.utilities.epic_quests import QuestQueryError


def island(code="1234-1234-1234", title="Zone Wars", creator="Epic", ccu=-1, description=None):
    return SimpleNamespace(link_code=code, title=title, creator_name=creator, global_ccu=ccu, description=description)


class FakeApi:
    def __init__(self):
        self.epic = [island(ccu=12), island("5678-5678-5678", "Box Fight", ccu=-1)]
        self.browse = [island(ccu=5), island("9999-9999-9999", "No Count", creator=None)]
        self.searched = []

    def scrape_creator_maps(self, name, limit=50, start_page=1):
        return self.epic if name == "epic" else []

    def scrape_fortnite_gg(self, search_query="", limit=50):
        self.searched.append(search_query)
        return self.browse if search_query in ("", "box") else []

    def get_island_by_code(self, code):
        return island(code, "Found Map", description="A map.", ccu=3) if code == "1234-1234-1234" else None


@pytest.fixture
def api(monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(state, "get_discovery_api", lambda: fake)
    return fake


@pytest.fixture
def hub():
    fake = Mock()
    set_hub(fake)
    yield fake
    set_hub(None)


# Discover ---------------------------------------------------------------------------

def test_list_labels_match_the_wx_view():
    assert discovery_ops.epic_label(island(ccu=12)) == "Zone Wars (12 playing)"
    assert discovery_ops.epic_label(island()) == "Zone Wars"
    assert discovery_ops.browse_label(island(ccu=5)) == "Zone Wars (5 playing) - 1234-1234-1234"
    assert discovery_ops.browse_label(island(creator=None)) == "Zone Wars by Unknown - 1234-1234-1234"
    assert discovery_ops.search_label(island()) == "Zone Wars by Epic - 1234-1234-1234"
    assert discovery_ops.creator_label(island()) == "Zone Wars - 1234-1234-1234"


def test_epic_list_speaks_the_count_only_to_someone_on_the_list(api):
    result = discover.epic({})
    assert [r["label"] for r in result["rows"]] == ["Zone Wars (12 playing)", "Box Fight"]
    assert result["rows"][0]["code"] == "1234-1234-1234"
    assert result["announce"] == "2 Epic gamemodes loaded" and result["only_if_focused"]


def test_failed_loads_show_and_speak_an_error(api):
    api.epic, api.browse = [], []
    epic = discover.epic({})
    assert epic["rows"][0] == {"label": "Couldn't load Epic gamemodes. Try refreshing.", "code": "", "title": ""}
    assert epic["announce"] == "Couldn't load Epic gamemodes" and not epic["only_if_focused"]
    assert discover.browse({})["announce"] == "Couldn't load islands"


def test_search_creator_and_lookup(api):
    assert discover.search({"query": " box "})["announce"] == "2 islands found"
    assert api.searched[-1] == "box"
    none = discover.search({"query": "zzz"})
    assert none["rows"][0]["label"] == "No islands found matching 'zzz'" and none["announce"] == "No results for zzz"
    with pytest.raises(ValueError, match="search term"):
        discover.search({"query": " "})
    assert discover.creator({"name": "epic"})["announce"] == "2 maps loaded for epic"
    assert discover.creator({"name": "nobody"})["announce"] == "No islands found for nobody"
    found = discover.lookup({"code": "1234-1234-1234"})
    assert found["text"] == "Title: Found Map\nCode: 1234-1234-1234\nCreator: Epic\n\nDescription: A map.\n\nPlayers: 3"
    assert found["announce"] == "Found: Found Map"
    assert discover.lookup({"code": "0000"}) == {"text": "Island not found for code: 0000", "announce": "Island not found"}


def test_copy_says_the_code_or_the_title(monkeypatch):
    copied = []
    monkeypatch.setattr("pyperclip.copy", copied.append)
    assert discover.copy({"code": "1234-1234-1234", "title": "T"})["announce"] == "Copied code: 1234-1234-1234"
    assert discover.copy({"code": "mymap", "title": "My Map"})["announce"] == "Copied code: My Map"
    assert copied == ["1234-1234-1234", "mymap"]
    assert discover.copy({"code": "", "title": ""})["announce"] == "No code available"


def test_launch_leaves_the_window_then_selects(monkeypatch, hub):
    calls = []
    monkeypatch.setattr(discovery_ops, "launch_gamemode", lambda code, title, speak, options=None: calls.append((code, title)))
    assert discover.launch({"code": "1234-1234-1234", "title": "Zone Wars"}) == {"launched": True}
    hub.services.speak.assert_called_with("Launching Zone Wars")
    hub.leave_page.assert_called_once()
    assert calls == [("1234-1234-1234", "Zone Wars")]
    assert discover.launch({"code": "", "title": "x"})["launched"] is False


def test_launch_refuses_a_mode_without_those_options_and_stays(hub):
    result = discover.launch({"code": "experience_br", "title": "Battle Royale",
                              "options": {"team": "trio", "zero_build": True, "ranked": True}})
    assert result["launched"] is False and "Solo, Duos and Squads" in result["announce"]
    hub.leave_page.assert_not_called()


def test_launch_uses_the_title_for_nonstandard_codes(monkeypatch):
    import sys
    spoken, picked = [], []
    fake = SimpleNamespace(select_gamemode=lambda text, expected_title=None: (picked.append(text) or True, None))
    monkeypatch.setitem(sys.modules, "lib.utilities.gamemode_selection", fake)
    done = __import__("threading").Event()
    discovery_ops.launch_gamemode("mymap", "My Map", lambda m: (spoken.append(m), done.set()))
    assert done.wait(3)
    assert picked == ["My Map"] and spoken == ["My Map selected!"]


# Quests -------------------------------------------------------------------------------

def quest(qid, name, tags=("QuestCategory.BR.Daily",), state="Active", achieved=3, required=10, **extra):
    row = dict(id=qid, template="Quest:" + qid, name=name, description="", state=state, expiry=None, expired=False,
               objectives=[dict(key="o", achieved=achieved, required=required, description="Do it", hidden=False)],
               completion_count=None, categories=list(tags), products=[], hidden=False, metadata_available=True,
               bundle_id=None, source="epic_account_api", updated_at=1)
    row.update(extra)
    return row


def snapshot(*quests_):
    return {"quests": list(quests_), "updated_at": 100}


def test_render_picks_battle_royale_first_and_lists_progress():
    view = quest_view.render_quests(snapshot(quest("a", "Search chests"), quest("b", "Done", state="Completed")))
    assert view["mode"] == "Battle Royale" and view["modes"][0] == "All modes"
    assert view["category"] == "All categories" and "Daily Quests" in view["categories"]
    assert [r["label"] for r in view["rows"]] == ["Search chests, 3 of 10, Daily Quests"]
    assert "Search chests" in view["rows"][0]["details"] and "3 of 10" in view["rows"][0]["details"]
    assert view["status"].startswith("1 quests shown.") and "Account snapshot:" in view["status"]


def test_render_filters_and_keeps_choices_valid():
    snap = snapshot(quest("a", "Search chests"), quest("b", "Done", state="Completed"))
    done = quest_view.render_quests(snap, mode="All modes", status="Completed")
    assert [r["id"] for r in done["rows"]] == ["b"]
    assert "Battle Royale / " in done["rows"][0]["label"]
    assert quest_view.render_quests(snap, mode="All modes", status="All")["rows"].__len__() == 2
    assert quest_view.render_quests(snap, mode="All modes", status="All", query="chests")["rows"][0]["id"] == "a"
    stale = quest_view.render_quests(snap, mode="Gone", category="Gone")
    assert stale["mode"] == "All modes" and stale["category"] == "All categories"
    empty = quest_view.render_quests(snapshot(), error="Offline.")
    assert empty["rows"] == [] and empty["status"] == "Offline." and empty["mode"] == "All modes"


def test_scoped_render_keeps_hidden_item_quests():
    hidden = quest("c", "Item task", hidden=True, state="Claimed")
    view = quest_view.render_quests(snapshot(hidden), mode="All modes", status="All", templates={"quest:c"},
                                    scope_label="Pass quests")
    assert view["categories"] == ["Pass quests"] and len(view["rows"]) == 1
    assert "Completed (reward claimed)" in view["rows"][0]["details"]


@pytest.fixture
def signed_in(monkeypatch):
    auth = SimpleNamespace(access_token="t", is_valid=True, account_id="acct")
    monkeypatch.setattr("lib.utilities.epic_auth.get_epic_auth_instance", lambda: auth)
    monkeypatch.setattr(quests, "_error", None)
    monkeypatch.setattr(quests, "_api", None)
    original = quest_store.api
    yield auth
    quest_store.api = original


def test_quests_need_a_signed_in_account(monkeypatch):
    monkeypatch.setattr("lib.utilities.epic_auth.get_epic_auth_instance", lambda: None)
    assert quests.state({}) == {"signed_in": False}
    assert quests.view({}) == {"signed_in": False}
    assert quests.refresh({}) == {"signed_in": False}


def test_refresh_fills_the_store_and_view_reads_it(signed_in, monkeypatch):
    api = Mock()
    api.query.return_value = snapshot(quest("a", "Search chests"))
    monkeypatch.setattr(quests, "EpicQuestAPI", lambda auth: api)
    assert quests.refresh({}) == {"signed_in": True}
    view = quests.view({})
    assert view["signed_in"] and [r["id"] for r in view["rows"]] == ["a"]
    assert view["revision"] == quest_store.snapshot()[0]


def test_refresh_errors_keep_older_quests_and_show_in_the_status(signed_in, monkeypatch):
    api = Mock()
    api.query.side_effect = QuestQueryError("Epic is down.")
    monkeypatch.setattr(quests, "EpicQuestAPI", lambda auth: api)
    result = quests.refresh({})
    assert result["error"] == "Epic is down. Previously loaded quests remain available."
    assert quests.view({})["status"] == result["error"]
    api.query.side_effect = RuntimeError("boom")
    monkeypatch.setattr(quests, "_api", None)
    assert quests.refresh({})["error"] == "Unable to load quests. Refresh to retry. Previously loaded quests remain available."


def test_store_changes_become_one_event(signed_in, hub, monkeypatch):
    time.sleep(quests.CHANGE_DELAY + 0.2)  # let timers other tests started fire first
    hub.send.reset_mock()
    monkeypatch.setattr(quests, "CHANGE_DELAY", 0.05)
    for _ in range(3):
        quest_store.replace_api(snapshot())
    time.sleep(0.4)
    names = [c.args[0] for c in hub.send.call_args_list]
    assert names == ["quests.changed"]
    assert hub.send.call_args.args[1]["revision"] == quest_store.snapshot()[0]


def test_store_listeners_are_notified_and_errors_ignored():
    store = QuestStore()
    seen = []
    store.add_listener(lambda: seen.append(store.revision))
    store.add_listener(Mock(side_effect=RuntimeError))
    store.replace_api(snapshot())
    store.reset_packet("epoch")
    store.reset_packet("epoch")
    assert seen == [1, 2]


def test_scoped_view_uses_the_registered_templates(signed_in):
    quest_store.replace_api(snapshot(quest("c", "Item task", hidden=True, state="Claimed"), quest("d", "Other")))
    scope_id = quests.register_scope({"quest:c"}, "Quests for X", "Pass quests")
    view = quests.view({"scope_id": scope_id, "mode": "All modes", "status": "All"})
    assert [r["id"] for r in view["rows"]] == ["c"] and view["heading"] == "Quests for X"
    assert quests.view({"scope_id": "nope"})["signed_in"]


def test_close_leaves_the_page(hub):
    quests.close({})
    hub.leave_page.assert_called_once()


# Passes -------------------------------------------------------------------------------

@pytest.fixture
def pass_world(monkeypatch):
    definitions = load_pass_catalog()
    api = Mock(definitions=definitions)
    api.auth = SimpleNamespace(account_id="acct")
    monkeypatch.setattr(passes, "_api", api)
    monkeypatch.setattr(passes, "_api_auth", None)
    monkeypatch.setattr(passes, "_snapshot", None)
    monkeypatch.setattr(passes, "_metadata", {})
    monkeypatch.setattr(passes, "_busy", False)
    monkeypatch.setattr(passes, "_pending", None)
    monkeypatch.setattr(passes, "_api_for_account", lambda: api)
    monkeypatch.setattr(passes, "_cosmetics_metadata", lambda: {})
    api.query = Mock()
    return api


def active_snapshot(definitions, claimed=(), purchased=True):
    return dict(passes={d["key"]: dict(active=True, purchased=purchased, level=50, claimed=set(claimed))
                        for d in definitions},
                balances={}, quests=[], updated_at=time.time(), account_id="acct")


def test_definitions_list_the_passes_and_pages(pass_world):
    result = passes.definitions({})
    assert [p["key"] for p in result["passes"]][0] == "br"
    assert result["passes"][0]["pages"][0].startswith("1 of ")
    assert sum("Bonus" in p for p in result["passes"][0]["pages"]) == 10


def test_view_before_and_after_refresh(pass_world):
    first = passes.view({"pass": "br", "page": 0, "reward": 0})
    assert "Account status unavailable" in first["status"]
    assert first["rewards"] and not any(first["buttons"][k] for k in ("reward", "page", "set", "unlock", "purchase"))
    pass_world.query.return_value = active_snapshot(pass_world.definitions)
    assert passes.refresh({}) == {"message": "Passes refreshed."}
    second = passes.view({"pass": "br", "page": 0, "reward": 0})
    assert "Premium pass owned." in second["status"]
    assert second["buttons"]["page"] and second["buttons"]["set"]
    assert second["reward"] == 0 and second["details"]


def test_refresh_failure_clears_the_snapshot(pass_world):
    pass_world.query.side_effect = PassError("Epic limited these requests. Try again later.")
    assert passes.refresh({}) == {"message": "Epic limited these requests. Try again later."}
    assert "unavailable" in passes.view({"pass": "br", "page": 0})["status"]
    pass_world.query.side_effect = RuntimeError("x")
    assert passes.refresh({})["message"] == "Pass data could not be loaded. Refresh to retry."


def test_prepare_then_execute_needs_the_confirmed_token(pass_world):
    definitions = pass_world.definitions
    passes._snapshot = active_snapshot(definitions)
    index = next(i for i, (c, p) in enumerate(pages(definitions[0])) if any(r["kind"] == "reward" for r in p["rewards"]))
    reward_index = next(i for i, r in enumerate(pages(definitions[0])[index][1]["rewards"]) if r["kind"] == "reward")
    action = PassAction("acct", "br", "claim", ("x",), (("currency", 0),), ("Reward",), 0)
    pass_world.prepare.return_value = action
    pass_world.execute.return_value = (active_snapshot(definitions, claimed={"x"}), "Claimed Reward.")
    prepared = passes.prepare({"pass": "br", "page": index, "reward": reward_index, "kind": "reward"})
    assert prepared["summary"].startswith("Claim:") and "token" in prepared
    assert pass_world.prepare.call_args.args[:2] == ("br", "claim")
    pass_world.execute.assert_not_called()
    stale = passes.execute({"token": prepared["token"] + 1})
    assert "no longer available" in stale["message"]
    assert passes.execute({"token": prepared["token"]}) == {"message": "Claimed Reward."}
    pass_world.execute.assert_called_once_with(action)
    assert passes.execute({"token": prepared["token"]})["message"].startswith("That action")


def test_prepare_reports_errors_and_the_sheer_will_rule(pass_world):
    definitions = pass_world.definitions
    passes._snapshot = active_snapshot(definitions)
    pass_world.prepare.side_effect = PassError("Refresh the pass before claiming or purchasing.")
    assert passes.prepare({"pass": "br", "page": 0, "reward": 0, "kind": "page"})["message"].startswith("Refresh")
    sheer = next(i for i, (c, p) in enumerate(pages(definitions[0])) if c["id"] == "Set_SheerWill")
    assert passes.prepare({"pass": "br", "page": sheer, "reward": 0, "kind": "set"}) == {
        "message": passes_view.SHEER_WILL_TEXT}
    with pytest.raises(ValueError):
        passes.prepare({"pass": "nope", "page": 0, "kind": "page"})


def test_prepare_does_nothing_without_a_snapshot_or_while_busy(pass_world):
    assert passes.prepare({"pass": "br", "page": 0, "reward": 0, "kind": "page"}) == {}
    passes._snapshot = active_snapshot(pass_world.definitions)
    passes._busy = True
    assert passes.prepare({"pass": "br", "page": 0, "reward": 0, "kind": "page"}) == {}
    assert passes.refresh({}) == {"message": passes.BUSY, "busy": True}


def test_quest_scope_registers_templates(pass_world):
    definitions = pass_world.definitions
    for i, (category, page) in enumerate(pages(definitions[0])):
        indices = [j for j, r in enumerate(page["rewards"]) if r["kind"] == "quest"]
        if indices:
            result = passes.quest_scope({"pass": "br", "page": i, "reward": indices[0]})
            assert result["label"] == definitions[0]["name"] + " quests"
            assert result["heading"].startswith("Quests for ")
            assert result["scope_id"] in quests._scopes
            break
    whole = passes.quest_scope({"pass": "br", "page": 0})
    assert whole["heading"].endswith("quests linked to this pass and its rewards.")


def test_the_new_pages_are_known_to_the_hub():
    from lib.shell.remote_hub import PAGE_KEYS
    assert "discover" in PAGE_KEYS and "quests" in PAGE_KEYS
