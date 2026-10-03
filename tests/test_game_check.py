from lib.app.display_actions import build_game_checks


def by_name(checks):
    return {c["name"]: c for c in checks}


def test_windowed_and_odd_resolution_are_problems():
    log = "- Resolution: 1600x900@60.0Hz at 100.0% 3D Resolution\n- Fullscreen mode: Windowed, VSync: 0\n"
    checks = by_name(build_game_checks(log, (1920, 1080), True))
    assert checks["Window mode"]["status"] == "problem"
    assert checks["Game resolution"]["status"] == "problem"
    assert sum(c["status"] == "problem" for c in checks.values()) == 2


def test_good_log_is_ok():
    log = "Resolution: 1920x1080@144.0Hz\nFullscreen mode: WindowedFullscreen, VSync: 0\n"
    checks = by_name(build_game_checks(log, (1920, 1080), True))
    assert checks["Window mode"]["text"] == "Window mode: Windowed Fullscreen. OK."
    assert checks["Game resolution"]["text"] == "Game resolution: 1920 by 1080. OK."
    assert all(c["status"] == "ok" for c in checks.values())


def test_empty_log_is_unknown():
    checks = by_name(build_game_checks("", (1920, 1080), True))
    for name in ("Window mode", "Game resolution"):
        assert checks[name]["status"] == "unknown"
        assert "Start Fortnite once" in checks[name]["text"]


def test_screen_and_driver_problems():
    checks = by_name(build_game_checks("", (1920, 1200), False))
    assert checks["Screen resolution"]["status"] == "problem"
    assert checks["FakerInput driver"]["status"] == "problem"
