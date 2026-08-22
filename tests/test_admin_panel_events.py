"""Log-driven accessibility tests for the Override Admin Panel."""

from lib.monitors.match_event_monitor import MatchEventMonitor


def _monitor(announce=True):
    monitor = MatchEventMonitor.__new__(MatchEventMonitor)
    monitor._admin_panel_open = False
    monitor.announce_ui_tabs = announce
    spoken = []
    monitor._speak = spoken.append
    return monitor, spoken


def test_admin_panel_open_close_are_announced_once():
    monitor, spoken = _monitor()
    opened = (
        "LogDynamicUI: Adding scene: "
        "UIScene_HackSystemFrontendIUI_CheatCode [FortLocalPlayer_1]"
    )
    closed = (
        "LogDynamicUI: Removing scene: "
        "UIScene_HackSystemFrontendIUI_CheatCode [FortLocalPlayer_1]"
    )

    monitor._process_line(opened)
    monitor._process_line(opened)
    monitor._process_line(closed)
    monitor._process_line(closed)

    assert spoken == ["Admin Panel opened", "Admin Panel closed"]
    assert monitor._admin_panel_open is False


def test_admin_panel_uses_existing_ui_tab_announcement_setting():
    monitor, spoken = _monitor(announce=False)

    monitor._process_line(
        "LogDynamicUI: Adding scene: UIScene_HackSystemFrontendIUI_CheatCode"
    )
    assert monitor._admin_panel_open is True

    monitor._process_line(
        "LogDynamicUI: Removing scene: UIScene_HackSystemFrontendIUI_CheatCode"
    )
    assert monitor._admin_panel_open is False
    assert spoken == []
