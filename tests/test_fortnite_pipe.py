import pytest
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
        "playlist_nobuildbr_duo", "Battle Royale Zero Build Duos Unranked", "Set other match options such as team fill in Fortnite.")
    link, _, note = d.apply_options("experience_br", "Battle Royale", {"team": "trio", "zero_build": True, "ranked": True})
    assert link is None and "Solo, Duos and Squads" in note
    assert d.apply_options("experience_blitz", "Blitz Royale", {"team": "squad", "ranked": True}) == (
        "playlist_forbiddenfruitnobuildbrsquad", "Blitz Royale Squads Unranked", "Blitz Royale has no ranked. Set other match options such as team fill in Fortnite.")
    assert d.apply_options("experience_blitz", "Blitz Royale", {"team": "trio"})[0] is None
    assert d.apply_options("experience_reload", "Reload", zb_duo)[0] == "playlist_blastberrynobuildduo"
    assert d.apply_options("campaign", "Save the World", zb_duo) == ("campaign", "Save the World", "")
    assert d.apply_options("experience_br", "Battle Royale", None) == ("experience_br", "Battle Royale", "")


def test_no_pipe_falls_back_and_says_options_need_fortnite_from_fa11y(monkeypatch):
    from lib.utilities import discovery_ops as d, gamemode_selection
    import threading
    from lib.utilities import fortnite_pipe
    monkeypatch.setattr(fortnite_pipe, "select_island", lambda *a, **k: (False, "no pipe"))
    monkeypatch.setattr(gamemode_selection, "select_gamemode", lambda *a, **k: (True, None))
    said, done = [], threading.Event()
    d.launch_gamemode("experience_br", "Battle Royale", lambda m: (said.append(m), done.set()),
                      {"team": "duo", "zero_build": True, "ranked": False})
    assert done.wait(3)
    assert "Play button" in said[0]


@pytest.mark.parametrize("link", ['experience_br\0-uilink=Bad', 'code&bad', 'code with spaces'])
def test_malformed_links_never_open_the_pipe(monkeypatch, link):
    from lib.utilities import fortnite_pipe
    from unittest.mock import Mock
    discover = Mock()
    monkeypatch.setattr(fortnite_pipe, "pipe_path", discover)
    assert fortnite_pipe.select_island(link)[0] is False
    discover.assert_not_called()


def test_unconfirmed_command_is_not_reported_as_selection(monkeypatch):
    from lib.utilities import fortnite_pipe
    from unittest.mock import mock_open
    monkeypatch.setattr(fortnite_pipe, "pipe_path", lambda: "fake")
    monkeypatch.setattr(fortnite_pipe, "_log_size", lambda: 0)
    monkeypatch.setattr(fortnite_pipe, "_wait_for_result", lambda *args: None)
    monkeypatch.setattr("builtins.open", mock_open())
    ok, error = fortnite_pipe.select_island("experience_br")
    assert not ok and "has not confirmed" in error


@pytest.mark.parametrize('team', ['solo','duo','squad'])
@pytest.mark.parametrize('zero', [False,True])
def test_reload_specifics_are_not_discarded(team, zero):
    from lib.utilities.discovery_ops import apply_options
    link,name,_=apply_options('experience_reload','Reload',dict(team=team,zero_build=zero))
    assert link == f"playlist_blastberry{'nobuild' if zero else ''}{team}"
    assert ('Zero Build' in name) == zero


def test_unverified_reload_options_do_not_claim_success():
    from lib.utilities.discovery_ops import apply_options
    assert apply_options('experience_reload','Reload',dict(team='trio'))[0] is None
    assert apply_options('experience_reload','Reload',dict(team='solo',ranked=True))[0] is None


def selected_log(build='Zero', team='Solo'):
    return f'''LogFortIslandOverride: Converting [playlist_blastberrynobuildsolo] to corresponding consoldiated tile [experience_reload] with settings [
    Selected Island:
        LinkId [Mnemonic=[experience_reload] Version=[latest]]
        MatchmakingSettings (V2) [
        /Fortnite.com/Matchmaking:Ranked [Unranked]
        /Fortnite.com/BattleRoyale/Matchmaking:TeamSize [{team}]
        /Fortnite.com/BattleRoyale/Matchmaking:BuildMode [{build}]]
        Timestamp: 2026.10.12-12.00.00'''


def test_same_island_settings_change_is_verified_without_link_change():
    settings={'BuildMode':'Zero','TeamSize':'Solo','Ranked':'Unranked'}
    assert judge(selected_log(),'playlist_blastberrynobuildsolo','experience_reload',settings) is True
    assert judge(selected_log(build='Build'),'playlist_blastberrynobuildsolo','experience_reload',settings) is None
    assert judge(selected_log(team='Duo'),'playlist_blastberrynobuildsolo','experience_reload',settings) is None


def test_playable_island_alone_cannot_confirm_requested_settings():
    assert judge(TAKEN,'8765-4125-9209',expected_settings={'TeamSize':'Solo'}) is None


def test_later_settings_override_does_not_confirm_old_requested_state():
    log=selected_log()+'\nfrom:\n'+selected_log()+'\nto:\n'+selected_log(build='Build')
    assert judge(log,'playlist_blastberrynobuildsolo','experience_reload',{'BuildMode':'Zero'}) is None
    partial=selected_log()+'\nto:\n Selected Island:\n  /Fortnite.com/BattleRoyale/Matchmaking:BuildMode [Build]'
    assert judge(partial,'playlist_blastberrynobuildsolo','experience_reload',{'BuildMode':'Zero'}) is None


def test_bridge_launch_passes_the_exact_requested_settings(monkeypatch):
    from lib.utilities import discovery_ops as d, fortnite_pipe
    from unittest.mock import Mock
    import threading
    send=Mock(return_value=(True,None))
    monkeypatch.setattr(fortnite_pipe,'select_island',send)
    done=threading.Event()
    d.launch_gamemode('experience_reload','Reload',lambda _:done.set(),
                     dict(team='solo',zero_build=True,ranked=False))
    assert done.wait(3)
    send.assert_called_once_with('playlist_blastberrynobuildsolo',expected_island='experience_reload',
                                 expected_settings={'TeamSize':'Solo','Ranked':'Unranked','BuildMode':'Zero'})


def test_blitz_confirmation_does_not_require_a_ranked_control(monkeypatch):
    from lib.utilities import discovery_ops as d, fortnite_pipe
    from unittest.mock import Mock
    import threading
    send=Mock(return_value=(True,None));done=threading.Event()
    monkeypatch.setattr(fortnite_pipe,'select_island',send)
    d.launch_gamemode('experience_blitz','Blitz',lambda _:done.set(),dict(team='duo'))
    assert done.wait(3)
    send.assert_called_once_with('playlist_forbiddenfruitnobuildbrduo',expected_island='experience_blitz',
                                 expected_settings={'TeamSize':'Duo'})
