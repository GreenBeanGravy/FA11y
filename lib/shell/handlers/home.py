"""Requests for the Home page. Each status check is its own request so cards fill in independently."""
from __future__ import annotations

from lib.hub import game_watch, status
from lib.shell.bridge import handler


@handler("home.info")
def home_info(_params: dict) -> dict:
    from lib.app import state
    return {
        "keybinds_on": state.are_keybinds_enabled(),
        "open_keybind": status.open_hub_keybind(),
        "fortnite_running": game_watch.is_fortnite_running(),
        "can_restart_to_update": status.can_restart_to_update(),
        "whats_new": status.latest_changelog_entry(),
    }


@handler("home.account")
def home_account(_params: dict) -> dict:
    return status.account_status()


@handler("home.fa11y")
def home_fa11y(_params: dict) -> dict:
    return status.fa11y_status()


@handler("home.fortnite")
def home_fortnite(_params: dict) -> dict:
    return status.fortnite_status()
