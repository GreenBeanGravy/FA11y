from lib.app import speech
from lib.monitors.match_event_monitor import MatchEventMonitor


def _set(value):
    speech._simple = value


def test_simple_uses_short_only_when_on_and_present():
    _set(True)
    assert speech.simple("Inventory opened", "Inventory") == "Inventory"
    assert speech.simple("Inventory opened") == "Inventory opened"
    _set(False)
    assert speech.simple("Inventory opened", "Inventory") == "Inventory opened"
    _set(None)


def test_simple_refreshes_on_config_change():
    import configparser

    def Cfg(v):
        c = configparser.ConfigParser()
        c.read_dict({"Toggles": {"SimplifySpeechOutput": "true" if v else "false"}})
        return c

    _set(False)
    speech._on_change(Cfg(True))
    assert speech.is_simple() is True
    speech._on_change(Cfg(False))
    assert speech.is_simple() is False
    _set(None)


def test_match_event_announces_short_form_when_on():
    spoken = []
    mon = MatchEventMonitor.__new__(MatchEventMonitor)
    mon._speak = spoken.append
    mon.announce_final_countdown = True
    mon._last_final_countdown = None
    mon._spectating = False
    mon.announce_phase = True
    mon._last_step = None
    mon._last_phase = None
    line = ("LogBattleRoyaleGamePhaseLogic: UpdateGamePhaseStep. "
            "PhaseStep = EAthenaGamePhaseStep::BusLocked")
    _set(True)
    mon._process_line(line)
    _set(False)
    mon._last_step = None
    mon._process_line(line)
    _set(None)
    assert spoken == ["Bus locked", "Battle bus locked"]
