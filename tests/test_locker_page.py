"""Locker: filtering, equip planning, owned filter, favorites, loadouts and the page's requests (Epic APIs mocked)."""
from unittest.mock import Mock

import pytest

from lib.managers import locker_manager as lm
from lib.shell.handlers import locker as handlers


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    """No speech, no sleeping, no mouse."""
    monkeypatch.setattr(lm, "speaker", Mock())
    monkeypatch.setattr(lm.time, "sleep", lambda s: None)


def cosmetic(cid, name, kind="AthenaCharacter", rarity="rare", value=3, favorite=False, description=""):
    return {"id": cid, "name": name, "type": kind, "rarity": rarity, "rarity_value": value,
            "introduction_chapter": "2", "introduction_season": "5", "favorite": favorite,
            "description": description}


@pytest.fixture
def cosmetics():
    return [
        cosmetic("skin_a", "Alpha", rarity="epic", value=4, description="Wears a hat"),
        cosmetic("skin_b", "Beta", rarity="rare", value=3, favorite=True),
        cosmetic("skin_c", "Alpha", rarity="rare", value=3),
        cosmetic("axe_a", "Axe", kind="AthenaPickaxe", rarity="marvel", value=6),
        cosmetic("emote_a", "Wave", kind="AthenaDance"),
        cosmetic("song_a", "Tune", kind="SparksSong"),
    ]


# --- lists --------------------------------------------------------------------

def test_a_category_lists_its_cosmetics_highest_rarity_first(cosmetics):
    result = lm.category_cosmetics(cosmetics, "Outfit")
    assert [c["id"] for c in result] == ["skin_a", "skin_c", "skin_b"]


def test_all_cosmetics_and_lobby_track_special_cases(cosmetics):
    assert len(lm.category_cosmetics(cosmetics, "All Cosmetics")) == 6
    assert [c["id"] for c in lm.category_cosmetics(cosmetics, "Lobby Track")] == ["song_a"]
    assert [c["id"] for c in lm.category_cosmetics(cosmetics, "Jam Track")] == ["song_a"]


def test_owned_only_keeps_the_owned_ids(cosmetics):
    result = lm.category_cosmetics(cosmetics, "Outfit", owned_only=True, owned_ids={"skin_b"})
    assert [c["id"] for c in result] == ["skin_b"]


def test_filter_by_favorites_and_search_in_name_description_and_rarity(cosmetics):
    outfits = lm.category_cosmetics(cosmetics, "Outfit")
    assert [c["id"] for c in lm.filter_cosmetics(outfits, favorites_only=True)] == ["skin_b"]
    assert [c["id"] for c in lm.filter_cosmetics(outfits, search="HAT")] == ["skin_a"]
    assert [c["id"] for c in lm.filter_cosmetics(outfits, search="epic")] == ["skin_a"]
    assert [c["id"] for c in lm.filter_cosmetics(outfits, search="alpha")] == ["skin_a", "skin_c"]


def test_favorites_first_sorting(cosmetics):
    outfits = lm.category_cosmetics(cosmetics, "Outfit")
    assert [c["id"] for c in lm.sort_favorites_first(outfits)] == ["skin_b", "skin_a", "skin_c"]


def test_rarity_season_and_type_text(cosmetics):
    assert lm.rarity_display(cosmetics[3]) == "Marvel series"
    assert lm.rarity_display(cosmetics[0]) == "Epic"
    assert lm.season_text(cosmetics[0]) == "C2S5"
    assert lm.season_text({}) == "C?S?"
    assert lm.friendly_type("AthenaPickaxe") == "Pickaxe"
    assert lm.friendly_type("Mystery") == "Mystery"


def test_results_label():
    assert lm.results_label(3, "Outfit") == "Showing 3 Outfit cosmetics"
    assert lm.results_label(1, "Outfit", "al", True) == "Showing 1 Outfit cosmetics matching 'al' (favorites only)"
    assert lm.results_label(2, "Outfit", favorites_first=True) == "Showing 2 Outfit cosmetics (favorites first)"


def test_category_options():
    assert lm.category_options("All Cosmetics") == {"random": False, "randomize": False, "unequip": None}
    assert lm.category_options("Emote") == {"random": False, "randomize": False, "unequip": "Empty"}
    assert lm.category_options("Outfit") == {"random": True, "randomize": False, "unequip": "Default"}
    assert lm.category_options("Glider")["unequip"] == "Glider"
    assert lm.category_options("Jam Track") == {"random": True, "randomize": True, "unequip": "Empty"}


def test_details_text(cosmetics):
    assert lm.cosmetic_details(cosmetics[0]) == (
        "Name: Alpha\nType: Outfit\nRarity: Epic\nSeason: Chapter 2, Season 5\n\nDescription: Wears a hat")
    assert lm.cosmetic_details(cosmetics[1]).endswith("\n\n⭐ FAVORITE")
    assert lm.special_details("random").startswith("Random\n\n")
    assert "'Default'" in lm.special_details("unequip", "Default")


def test_compact_records_have_what_the_page_needs(cosmetics):
    record = lm.compact_record(cosmetics[3])
    assert record == {"i": "axe_a", "n": "Axe", "t": "Pickaxe", "r": "Marvel series", "k": "marvel", "v": 6,
                      "s": "C2S5", "c": "2", "e": "5", "d": "", "f": False}


# --- equip planning ---------------------------------------------------------------

def test_planning_a_cosmetic_with_a_fixed_slot(cosmetics):
    plan = lm.plan_equip(lm.EquipRequest("Outfit", "cosmetic", cosmetics[0]))
    assert plan == {"name": "Alpha", "category": "Character", "slot": 1, "cosmetic_type": "AthenaCharacter"}


def test_planning_a_multi_slot_type_leaves_the_slot_open_and_has_a_prompt(cosmetics):
    plan = lm.plan_equip(lm.EquipRequest("Emote", "cosmetic", cosmetics[4]))
    assert plan["category"] == "Emotes" and plan["slot"] is None
    prompt = lm.slot_prompt(plan["cosmetic_type"], plan["name"])
    assert prompt["title"] == "Select Emote Slot" and len(prompt["choices"]) == 8
    assert lm.slot_prompt("AthenaItemWrap", "x")["choices"][0] == "Rifles"
    assert len(lm.slot_prompt("SparksSong", "x")["choices"]) == 4
    assert lm.slot_prompt("AthenaSpray", "x") is None


def test_a_jam_track_in_lobby_track_goes_to_the_lobby_music_slot(cosmetics):
    plan = lm.plan_equip(lm.EquipRequest("Lobby Track", "cosmetic", cosmetics[5]))
    assert (plan["category"], plan["slot"]) == ("Lobby", 2)


def test_planning_an_unknown_type_fails_with_a_message(cosmetics):
    plan = lm.plan_equip(lm.EquipRequest("All Cosmetics", "cosmetic", cosmetic("x", "Odd", kind="Unknown")))
    assert plan == {"error": "Cannot equip Odd.\nUnknown cosmetic category."}


def test_random_and_unequip_act_on_the_category(cosmetics):
    plan = lm.plan_equip(lm.EquipRequest("Pickaxe", "random"))
    assert (plan["name"], plan["category"], plan["slot"]) == ("Random", "Character", 3)
    plan = lm.plan_equip(lm.EquipRequest("Lobby Track", "unequip"))
    assert (plan["name"], plan["category"], plan["slot"]) == ("Unequip", "Lobby", 2)
    assert "error" in lm.plan_equip(lm.EquipRequest("Nonsense", "random"))


def test_randomize_picks_from_the_candidates(cosmetics, monkeypatch):
    monkeypatch.setattr(lm.random, "choice", lambda items: items[-1])
    request = lm.EquipRequest("Jam Track", "randomize", candidates=[cosmetics[5], cosmetics[4]])
    plan = lm.plan_equip(request)
    assert request.cosmetic is cosmetics[4] and plan["name"] == "Wave"
    assert lm.plan_equip(lm.EquipRequest("Jam Track", "randomize")) == {"error": "No cosmetics available to randomize."}


def test_run_equip_picks_the_automation_and_reports(cosmetics, monkeypatch):
    equip = Mock(return_value=True)
    scroll = Mock(return_value=False)
    monkeypatch.setattr(lm, "perform_equip_automation", equip)
    monkeypatch.setattr(lm, "perform_scroll_and_click_automation", scroll)
    request = lm.EquipRequest("Outfit", "cosmetic", cosmetics[0])
    assert lm.run_equip(request, lm.plan_equip(request), 1) == (True, "Alpha")
    equip.assert_called_once_with("Character", 1, "Alpha")
    request = lm.EquipRequest("Outfit", "unequip")
    assert lm.run_equip(request, lm.plan_equip(request), 1) == (False, "Unequip")
    scroll.assert_called_once_with("Character", 1, 1020, 350)
    request = lm.EquipRequest("Outfit", "random")
    lm.run_equip(request, lm.plan_equip(request), 1)
    scroll.assert_called_with("Character", 1, 1175, 385)


# --- owned ----------------------------------------------------------------

def test_owned_ids_add_placeholders_and_stamp_favorites(cosmetics):
    auth = Mock(favorite_cosmetic_ids={"skin_c"})
    owned = lm.apply_owned_ids(cosmetics, auth, ["SKIN_A", "Brand_New_Item_With_A_Long_Name"])
    assert owned == {"skin_a", "brand_new_item_with_a_long_name"}
    placeholder = cosmetics[-1]
    assert placeholder["name"] == "[Unknown Item] brand_new_item_with_"
    assert [c["favorite"] for c in cosmetics[:3]] == [False, False, True]


def test_favorite_flags_are_left_alone_when_none_were_fetched(cosmetics):
    assert lm.apply_favorite_flags(cosmetics, None) == 0
    assert cosmetics[1]["favorite"] is True


def test_turning_the_owned_filter_on_fetches_once(cosmetics):
    auth = Mock(favorite_cosmetic_ids=None)
    auth.fetch_owned_cosmetics.return_value = ["skin_a"]
    result = lm.set_owned_only(cosmetics, auth, set(), True)
    assert result.owned_only and result.owned_ids == {"skin_a"}
    assert result.messages == ["Enabled: Show only owned cosmetics", "Fetching owned cosmetics",
                               "Found 1 owned cosmetics"]
    again = lm.set_owned_only(cosmetics, auth, result.owned_ids, True)
    assert again.messages == ["Enabled: Show only owned cosmetics"]
    assert auth.fetch_owned_cosmetics.call_count == 1
    off = lm.set_owned_only(cosmetics, auth, result.owned_ids, False)
    assert not off.owned_only and off.messages == ["Disabled: Showing all cosmetics"]


def test_owned_filter_when_the_login_expired_or_the_fetch_failed(cosmetics):
    auth = Mock()
    auth.fetch_owned_cosmetics.return_value = "AUTH_EXPIRED"
    result = lm.set_owned_only(cosmetics, auth, set(), True)
    assert result.expired and not result.owned_only
    assert result.messages[-1] == "Your login has expired. Please log in again."
    auth.fetch_owned_cosmetics.return_value = None
    result = lm.set_owned_only(cosmetics, auth, set(), True)
    assert not result.expired and not result.owned_only
    assert result.error.startswith("Failed to fetch your owned cosmetics")


# --- favorites ----------------------------------------------------------------

@pytest.fixture
def locker_api(monkeypatch):
    api = Mock(template_id_map={"x": "guid"})
    api.set_favorite.return_value = True
    monkeypatch.setattr("lib.utilities.epic_auth.get_locker_api", lambda auth: api)
    return api


def test_toggling_a_favorite_updates_the_cosmetic_and_the_database_copy(cosmetics, locker_api):
    target = dict(cosmetics[0])  # a copy, like a record the list holds
    assert lm.toggle_favorite(Mock(access_token="t"), cosmetics, target) == "ok"
    locker_api.set_favorite.assert_called_once_with("AthenaCharacter:skin_a", True)
    assert target["favorite"] is True and cosmetics[0]["favorite"] is True
    assert lm.toggle_favorite(Mock(access_token="t"), cosmetics, target) == "ok"
    locker_api.set_favorite.assert_called_with("AthenaCharacter:skin_a", False)


def test_toggling_a_favorite_when_it_cannot_work(cosmetics, locker_api):
    assert lm.toggle_favorite(Mock(access_token=None), cosmetics, cosmetics[0]) == "login"
    assert lm.toggle_favorite(Mock(access_token="t"), cosmetics, {"name": "No id"}) == "missing"
    locker_api.set_favorite.return_value = False
    assert lm.toggle_favorite(Mock(access_token="t"), cosmetics, cosmetics[0]) == "failed"
    assert cosmetics[0]["favorite"] is False
    locker_api.set_favorite.side_effect = RuntimeError("down")
    assert lm.toggle_favorite(Mock(access_token="t"), cosmetics, cosmetics[0]) == "error"


def test_the_profile_is_loaded_first_when_needed(cosmetics, locker_api):
    locker_api.template_id_map = {}
    lm.toggle_favorite(Mock(access_token="t"), cosmetics, cosmetics[0])
    locker_api.load_profile.assert_called_once()


# --- equipped and loadouts -----------------------------------------------------------

def test_equipped_text_names_items_from_the_database(cosmetics):
    auth = Mock()
    auth.get_equipped_cosmetics.return_value = {
        "Character": {"slots": {"LoadoutSlot_Character": {"equipped_id": "AthenaCharacter:SKIN_A"},
                               "LoadoutSlot_Pickaxe": {"equipped_id": ""}}},
        "Platform": {"slots": {"LoadoutSlot_LobbyMusic": {"equipped_id": "Unknown:thing"}}},
    }
    assert lm.equipped_text(auth, cosmetics) == (
        "--- Character ---\n  Character: Alpha\n  Pickaxe: (empty)\n\n--- Lobby ---\n  LobbyMusic: thing\n")
    auth.get_equipped_cosmetics.return_value = None
    assert lm.equipped_text(auth, cosmetics) is None


@pytest.fixture
def local_loadouts(monkeypatch):
    store = {"items": []}
    monkeypatch.setattr(lm, "_local_loadouts", lambda: list(store["items"]))
    monkeypatch.setattr(lm, "_save_local_loadouts", lambda items: store.update(items=list(items)))
    return store


def preset(name, loadout_type, item="AthenaCharacter:skin_a"):
    return {"displayName": name, "loadoutType": loadout_type, "shuffleType": "DISABLED",
            "loadoutSlots": [{"slotTemplate": "LoadoutSlot:LoadoutSlot_Character", "equippedItemId": item}]}


CHAR = "CosmeticLoadout:LoadoutSchema_Character"
EMOTES = "CosmeticLoadout:LoadoutSchema_Emotes"


def test_loadouts_merge_epic_presets_by_name_then_add_local_ones(local_loadouts):
    local_loadouts["items"] = [{"display_name": "Mine", "categories": {CHAR: {"loadoutSlots": []}}}]
    auth = Mock()
    auth.query_locker_items.return_value = {"loadoutPresets": [preset("Set", CHAR), preset("Set", EMOTES),
                                                               preset("", CHAR)]}
    entries = lm.load_loadouts(auth)
    # Epic's presets come first; the local ones follow, including the copies just imported from Epic
    # (the wx view has always listed them twice the first time).
    assert [(e["displayName"], e["source"], sorted(e["categories"])) for e in entries] == [
        ("Set", "epic", [CHAR, EMOTES]), ("(unnamed)", "epic", [CHAR]), ("Mine", "local", [CHAR]),
        ("Set", "local", [CHAR, EMOTES]), ("(unnamed)", "local", [CHAR])]
    # Epic's presets were copied to local storage for editing, once
    assert [i["display_name"] for i in local_loadouts["items"]] == ["Mine", "Set", "(unnamed)"]
    lm.load_loadouts(auth)
    assert len(local_loadouts["items"]) == 3


def test_loadouts_none_means_failed_and_empty_means_no_presets(local_loadouts):
    auth = Mock()
    auth.query_locker_items.return_value = None
    assert lm.load_loadouts(auth) is None
    auth.query_locker_items.return_value = {"loadoutPresets": []}
    assert lm.load_loadouts(auth) == []


def test_loadout_labels_filters_and_details(cosmetics):
    both = {"displayName": "Set", "source": "epic", "categories": {CHAR: {"loadoutSlots": preset("", CHAR)["loadoutSlots"]},
                                                                   EMOTES: {"loadoutSlots": []}}}
    single = {"displayName": "Solo", "source": "local", "categories": {CHAR: {"loadoutSlots": []}}}
    assert lm.loadout_label(both) == "Set [Character + Emotes]"
    assert lm.loadout_label(single) == "Solo [Character]"
    assert lm.loadout_label({"displayName": "Empty", "categories": {}}) == "Empty [?]"
    assert lm.filter_loadouts([both, single], "All") == [both, single]
    assert lm.filter_loadouts([both, single], "Multi-Category Only") == [both]
    assert lm.filter_loadouts([both, single], "Emotes") == [both]
    assert lm.loadout_filter_choices()[:2] == ["All", "Multi-Category Only"]
    detail = lm.loadout_detail_text(both, cosmetics)
    assert detail.startswith("Loadout: Set\nSource: epic\nCategories: Character + Emotes\n\n--- Character ---")
    assert "  Character: Alpha" in detail


def test_loadout_items_for_mouse_automation(cosmetics):
    entry = {"displayName": "Set", "categories": {
        CHAR: {"loadoutSlots": [
            {"slotTemplate": "LoadoutSlot:LoadoutSlot_Character", "equippedItemId": "AthenaCharacter:skin_a"},
            {"slotTemplate": "LoadoutSlot:LoadoutSlot_Pickaxe", "equippedItemId": ""},
            {"slotTemplate": "LoadoutSlot:LoadoutSlot_Unknown", "equippedItemId": "x:y"},
            {"slotTemplate": "LoadoutSlot:LoadoutSlot_JamSong0", "equippedItemId": "SparksSong:song_a"}]}}}
    items = lm.loadout_ui_items(entry, cosmetics)
    assert items == [{"name": "Alpha", "category": "Character", "slot": 1, "slot_key": "LoadoutSlot_Character"}]
    assert "Alpha → Character slot 1" in lm.loadout_ui_prompt(entry, items)
    assert "Categories: Character" in lm.loadout_api_prompt(entry)


def test_equipping_a_loadout_through_the_api(cosmetics):
    entry = {"displayName": "Set", "categories": {CHAR: {"shuffleType": "ENABLED", "loadoutSlots": [
        {"slotTemplate": "a", "equippedItemId": "b", "itemCustomizations": [1]}, {"slotTemplate": "c"}]}}}
    auth = Mock()
    auth.update_active_loadout.return_value = True
    assert lm.equip_loadout_via_api(auth, entry)
    auth.update_active_loadout.assert_called_once_with({CHAR: {"shuffleType": "ENABLED", "loadoutSlots": [
        {"slotTemplate": "a", "itemCustomizations": [1], "equippedItemId": "b"},
        {"slotTemplate": "c", "itemCustomizations": []}]}})
    auth.update_active_loadout.return_value = False
    assert not lm.equip_loadout_via_api(auth, entry)


def test_deleting_and_checking_local_loadouts(local_loadouts):
    local_loadouts["items"] = [{"display_name": "A"}, {"display_name": "B"}]
    assert lm.loadout_exists("a") and not lm.loadout_exists("C")
    assert lm.delete_local_loadout("A")
    assert local_loadouts["items"] == [{"display_name": "B"}]
    assert lm.is_local_loadout({"source": "local"}) and not lm.is_local_loadout({"source": "epic"})


def test_saving_a_loadout_stores_what_is_equipped_and_replaces_the_same_name(local_loadouts):
    auth = Mock()
    auth.query_locker_items.return_value = {"activeLoadoutGroup": {"loadouts": {
        CHAR: {"loadoutSlots": [1, 2], "shuffleType": "ENABLED"}, EMOTES: {"loadoutSlots": [3]}}}}
    result = lm.save_loadout(auth, "All Categories", None, "Mine")
    assert result["ok"] and "Total slots: 3" in result["message"]
    assert local_loadouts["items"][0]["categories"][CHAR] == {"loadoutSlots": [1, 2], "shuffleType": "ENABLED"}
    result = lm.save_loadout(auth, "Character", CHAR, "mine")
    assert result["ok"]
    assert len(local_loadouts["items"]) == 1 and list(local_loadouts["items"][0]["categories"]) == [CHAR]
    result = lm.save_loadout(auth, "Wraps", "CosmeticLoadout:LoadoutSchema_Wraps", "W")
    assert result == {"ok": False, "message": "No equipped items found for Wraps"}
    auth.query_locker_items.return_value = None
    assert not lm.save_loadout(auth, "All Categories", None, "X")["ok"]


# --- the page's requests -------------------------------------------------------------------

@pytest.fixture
def session(cosmetics, monkeypatch):
    auth = Mock(display_name="Neo", is_valid=True, access_token="t")
    s = handlers.LockerSession(cosmetics, auth)
    monkeypatch.setattr(handlers, "_session", s)
    return s


def test_requests_need_a_loaded_locker(monkeypatch):
    monkeypatch.setattr(handlers, "_session", None)
    with pytest.raises(RuntimeError):
        handlers.locker_category({"name": "Outfit"})


def test_load_reports_unavailable_when_the_database_is_missing(monkeypatch):
    monkeypatch.setattr("lib.utilities.epic_auth.get_or_create_cosmetics_cache", lambda **k: None)
    assert handlers.locker_load({}) == {"available": False}


def test_load_defaults_to_owned_only_when_signed_in(cosmetics, monkeypatch):
    auth = Mock(display_name="Neo", favorite_cosmetic_ids=None)
    auth.fetch_owned_cosmetics.return_value = ["skin_b"]
    monkeypatch.setattr("lib.utilities.epic_auth.get_or_create_cosmetics_cache", lambda **k: cosmetics)
    monkeypatch.setattr(handlers, "_auth", lambda: auth)
    monkeypatch.setattr(handlers, "_session", None)
    result = handlers.locker_load({})
    assert result["available"] and result["signed_in"] and result["owned_only"]
    assert result["name"] == "Neo" and result["total"] == 6 and result["categories"][0] == "All Cosmetics"
    assert [r["i"] for r in handlers.locker_category({"name": "Outfit"})["records"]] == ["skin_b"]


def test_load_signed_out_shows_everything(cosmetics, monkeypatch):
    auth = Mock(display_name=None)
    monkeypatch.setattr("lib.utilities.epic_auth.get_or_create_cosmetics_cache", lambda **k: cosmetics)
    monkeypatch.setattr(handlers, "_auth", lambda: auth)
    monkeypatch.setattr(handlers, "_session", None)
    result = handlers.locker_load({})
    assert not result["signed_in"] and not result["owned_only"]
    assert len(handlers.locker_category({"name": "Outfit"})["records"]) == 3
    assert handlers.locker_set_owned_only({"value": True})["messages"] == ["Please log in first"]


def test_a_failed_owned_fetch_still_loads(cosmetics, monkeypatch):
    auth = Mock(display_name="Neo")
    auth.fetch_owned_cosmetics.side_effect = RuntimeError("down")
    monkeypatch.setattr("lib.utilities.epic_auth.get_or_create_cosmetics_cache", lambda **k: cosmetics)
    monkeypatch.setattr(handlers, "_auth", lambda: auth)
    monkeypatch.setattr(handlers, "_session", None)
    assert handlers.locker_load({})["available"]


def test_category_request_returns_records_and_options(session):
    result = handlers.locker_category({"name": "Outfit"})
    assert [r["i"] for r in result["records"]] == ["skin_a", "skin_c", "skin_b"]
    assert result["options"]["unequip"] == "Default"


def test_owned_filter_request(session):
    session.auth.fetch_owned_cosmetics.return_value = ["skin_c"]
    session.auth.favorite_cosmetic_ids = None
    result = handlers.locker_set_owned_only({"value": True})
    assert result["owned_only"] and session.owned_ids == {"skin_c"}
    assert [r["i"] for r in handlers.locker_category({"name": "Outfit"})["records"]] == ["skin_c"]
    assert not handlers.locker_set_owned_only({"value": False})["owned_only"]


def test_favorite_request(session, locker_api):
    assert handlers.locker_toggle_favorite({"id": "skin_a"}) == {"result": "ok", "favorite": True}
    assert handlers.locker_toggle_favorite({"id": "nope"}) == {"result": "missing", "favorite": False}


def test_equip_plan_request_asks_for_a_slot_when_needed(session):
    assert handlers.locker_equip_plan({"kind": "cosmetic", "category": "Outfit", "id": "skin_a"}) == {
        "kind": "cosmetic", "id": "skin_a", "name": "Alpha", "slot": 1}
    result = handlers.locker_equip_plan({"kind": "cosmetic", "category": "Emote", "id": "emote_a"})
    assert result["slot"] is None and result["ask"]["title"] == "Select Emote Slot"
    # A spray has several slots but nothing to ask: slot 1
    session.cosmetics.append(cosmetic("spray_a", "Tag", kind="AthenaSpray"))
    assert handlers.locker_equip_plan({"kind": "cosmetic", "category": "Spray", "id": "spray_a"})["slot"] == 1
    assert handlers.locker_equip_plan({"kind": "random", "category": "Pickaxe"})["name"] == "Random"
    assert "error" not in handlers.locker_equip_plan({"kind": "cosmetic", "category": "All Cosmetics", "id": "skin_a"})


def test_equip_plan_for_randomize_names_the_pick(session, monkeypatch):
    monkeypatch.setattr(lm.random, "choice", lambda items: items[0])
    result = handlers.locker_equip_plan({"kind": "randomize", "category": "Jam Track", "ids": ["song_a"]})
    assert (result["kind"], result["id"], result["name"], result["slot"]) == ("cosmetic", "song_a", "Tune", None)
    assert result["ask"]["title"] == "Select Jam Track Slot"
    assert handlers.locker_equip_plan({"kind": "randomize", "category": "Jam Track", "ids": []}) == {
        "error": "No cosmetics available to randomize."}


def test_equip_request_runs_the_automation_and_reports(session, monkeypatch):
    run = Mock(return_value=(True, "Alpha"))
    monkeypatch.setattr(lm, "run_equip", run)
    result = handlers.locker_equip({"kind": "cosmetic", "category": "Outfit", "id": "skin_a"})
    assert result == {"ok": True, "name": "Alpha", "message": ""}
    assert run.call_args.args[2] == 1
    run.return_value = (False, "Alpha")
    assert handlers.locker_equip({"kind": "cosmetic", "category": "Outfit", "id": "skin_a"})["message"] \
        == lm.EQUIP_FAILED_MESSAGE
    run.side_effect = RuntimeError("no mouse")
    assert handlers.locker_equip({"kind": "cosmetic", "category": "Outfit", "id": "skin_a"})["message"] \
        == "Error: no mouse"
    run.reset_mock(side_effect=True)
    handlers.locker_equip({"kind": "cosmetic", "category": "Emote", "id": "emote_a", "slot": 5})
    assert run.call_args.args[2] == 5


def test_equipped_request(session, monkeypatch):
    monkeypatch.setattr(lm, "equipped_text", lambda auth, cosmetics: "text")
    assert handlers.locker_equipped({}) == {"text": "text"}
    session.auth.is_valid = False
    assert handlers.locker_equipped({}) == {"login": True}


def test_loadout_requests(session, local_loadouts, monkeypatch):
    session.auth.query_locker_items.return_value = {"loadoutPresets": [preset("Set", CHAR), preset("Set", EMOTES),
                                                                       preset("Solo", CHAR)]}
    result = handlers.locker_loadouts({"fetch": True})
    assert result["status"] == "ok" and result["total"] == 4  # two from Epic, two imported copies
    labels = [r["label"] for r in result["records"]]
    assert labels[0] == "Set [Character + Emotes]"
    multi = handlers.locker_loadouts({"fetch": False, "filter": "Multi-Category Only"})
    assert [(r["name"], r["local"]) for r in multi["records"]] == [("Set", False), ("Set", True)]
    assert multi["records"][0]["detail"].startswith("Loadout: Set")
    first = result["records"][0]["id"]
    assert "Equip loadout 'Set' via API?" in handlers.locker_loadout_api_prompt({"id": first})["prompt"]
    plan = handlers.locker_loadout_ui_plan({"id": first})
    assert plan["count"] == 2 and "Alpha" in plan["prompt"]
    session.auth.update_active_loadout.return_value = True
    assert handlers.locker_loadout_equip_api({"id": first}) == {"ok": True, "name": "Set"}
    automation = Mock()
    monkeypatch.setattr(lm, "perform_loadout_ui_automation", automation)
    handlers.locker_loadout_equip_ui({"id": first})
    assert automation.call_args.args[1] == "Set"
    with pytest.raises(ValueError):
        handlers.locker_loadout_api_prompt({"id": 99})


def test_loadout_requests_when_signed_out_or_failed(session, local_loadouts):
    session.auth.is_valid = False
    assert handlers.locker_loadouts({}) == {"status": "login"}
    session.auth.is_valid = True
    session.auth.query_locker_items.return_value = None
    assert handlers.locker_loadouts({}) == {"status": "failed"}
    session.auth.query_locker_items.return_value = {"loadoutPresets": []}
    assert handlers.locker_loadouts({}) == {"status": "none"}


def test_deleting_a_loadout_only_works_on_local_ones(session, local_loadouts):
    session.auth.query_locker_items.return_value = {"loadoutPresets": [preset("Set", CHAR)]}
    result = handlers.locker_loadouts({})
    epic = next(r for r in result["records"] if not r["local"])
    assert handlers.locker_loadout_delete({"id": epic["id"]})["ok"] is False
    local = next(r for r in result["records"] if r["local"])
    assert handlers.locker_loadout_delete({"id": local["id"]})["ok"] is True
    assert all(m.get("source") != "local" for m in session.loadouts)


def test_save_loadout_requests(session, local_loadouts):
    assert handlers.locker_save_choices({})["choices"][0] == "All Categories"
    session.auth.query_locker_items.return_value = {"activeLoadoutGroup": {"loadouts": {CHAR: {"loadoutSlots": []}}}}
    assert handlers.locker_save_loadout({"choice": 0, "name": " Mine "})["ok"]
    assert handlers.locker_save_loadout({"choice": 0, "name": "mine"}) == {"exists": True}
    assert handlers.locker_save_loadout({"choice": 1, "name": "mine", "overwrite": True})["ok"]
    session.auth.is_valid = False
    assert handlers.locker_save_choices({}) == {"login": True}


def test_passes_go_to_the_quests_page_when_the_new_window_has_it(session, monkeypatch):
    hub = Mock()
    hub.has_page.return_value = True
    monkeypatch.setattr(handlers, "get_hub", lambda: hub)
    handlers.locker_open_passes({})
    hub.show_page.assert_called_once_with("quests", summon=True)
