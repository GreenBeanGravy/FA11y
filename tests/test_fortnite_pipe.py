from lib.utilities.fortnite_pipe import judge, normalize_link

# Lines from FortniteGame.log, trimmed.
TAKEN = """LogExternalApplicationCommand: [3c6a] Parsing string: -IslandOverride=8765-4125-9209
MatchmakingLog: [2a77] Link id changing from [Mnemonic=[experience_br] Version=[latest]] to [Mnemonic=[8765-4125-9209] Version=[latest]]
MatchmakingLog: [35e2] Found Playable Island [LinkId [Mnemonic=[8765-4125-9209] Version=[latest]] - Title [1v1v1 Reload]"""
DROPPED = """LogExternalApplicationCommand: [3c6a] Parsing string: -IslandOverride=mymap
MatchmakingLog: [2a77] Link id changing from [Mnemonic=[experience_br] Version=[latest]] to [Mnemonic=[mymap] Version=[latest]]
MatchmakingLog: [2a77] Link id changing from [Mnemonic=[mymap] Version=[latest]] to [Mnemonic=[experience_br] Version=[latest]]"""
GARBLED = """LogFortDeepLinks: Handling Command: 'andOverride=experience_br'
LogFortDeepLinks: Did not parse into valid command"""


def test_island_that_loads_is_taken():
    assert judge(TAKEN, "8765-4125-9209") is True


def test_unknown_island_that_the_game_drops_fails():
    assert judge(DROPPED, "mymap") is False


def test_unparsed_command_fails_and_partial_log_waits():
    assert judge(GARBLED, "experience_br") is False
    assert judge(TAKEN.splitlines()[0], "8765-4125-9209") is None


def test_old_playlist_names_become_an_island_with_settings():
    log = """LogFortIslandOverride: [3c05] Converting [playlist_nobuildbr_duo] to corresponding consoldiated tile [experience_br] with settings [
MatchmakingLog: [2a77] Link id changing from [Mnemonic=[8765-4125-9209] Version=[latest]] to [Mnemonic=[experience_br] Version=[latest]]
MatchmakingLog: [35e2] Found Playable Island [LinkId [Mnemonic=[experience_br] Version=[latest]] - Title [Battle Royale]"""
    assert judge(log, "playlist_nobuildbr_duo") is True


def test_twelve_digit_codes_get_dashes():
    assert normalize_link("876541259209") == "8765-4125-9209"
    assert normalize_link("playlist_defaultsolo") == "playlist_defaultsolo"


def test_battle_royale_playlists():
    from lib.utilities import discovery_ops as d
    assert d.br_playlist("duo", zero_build=True, ranked=False) == "playlist_nobuildbr_duo"
    assert d.br_playlist("trio", zero_build=False, ranked=False) == "playlist_trios"
    assert d.br_playlist("squad", zero_build=False, ranked=True) == "playlist_habanerosquad"
    assert d.br_playlist("solo", zero_build=True, ranked=True) == "playlist_nobuildbr_habanero_solo"
    assert d.br_playlist("trio", zero_build=True, ranked=True) is None
    assert d.br_title("duo", True, True) == "Ranked Zero Build Duos"


def test_epic_gamemodes_take_the_match_options_they_offer():
    from lib.utilities import discovery_ops as d
    zb_duo = {"team": "duo", "zero_build": True, "ranked": False}
    assert d.apply_options("experience_br", "Battle Royale", zb_duo) == (
        "playlist_nobuildbr_duo", "Battle Royale, Zero Build Duos", "")
    link, _, note = d.apply_options("experience_br", "Battle Royale", {"team": "trio", "zero_build": True, "ranked": True})
    assert link is None and "Solo, Duos and Squads" in note
    assert d.apply_options("experience_blitz", "Blitz Royale", {"team": "squad", "ranked": True}) == (
        "playlist_forbiddenfruitnobuildbrsquad", "Blitz Royale, Squads", "Blitz Royale has no ranked.")
    assert d.apply_options("experience_blitz", "Blitz Royale", {"team": "trio"})[0] is None
    assert d.apply_options("experience_reload", "Reload", zb_duo)[0] == "experience_reload"
    assert d.apply_options("campaign", "Save the World", zb_duo) == ("campaign", "Save the World", "")
    assert d.apply_options("experience_br", "Battle Royale", None) == ("experience_br", "Battle Royale", "")


def test_no_pipe_falls_back_and_says_options_need_fortnite_from_fa11y(monkeypatch):
    from lib.utilities import discovery_ops as d, gamemode_selection
    import threading
    monkeypatch.setattr(gamemode_selection, "select_gamemode", lambda *a, **k: (True, None))
    said, done = [], threading.Event()
    d.launch_gamemode("experience_br", "Battle Royale", lambda m: (said.append(m), done.set()),
                      {"team": "duo", "zero_build": True, "ranked": False})
    assert done.wait(3)
    assert "Play button" in said[0]
