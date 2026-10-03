"""Requests for the About and updates page."""
from __future__ import annotations

from lib.app import branch
from lib.hub import status
from lib.shell.bridge import handler


@handler("about.info")
def about_info(_params: dict) -> dict:
    return {
        "version": status.local_version(),
        "update": status.available_update(),
        "can_restart_to_update": status.can_restart_to_update(),
        "changelog": status.full_changelog(),
    }


@handler("about.branches")
def about_branches(_params: dict) -> dict:
    """The branches FA11y can switch to, and the one this install follows."""
    return {"current": branch.current_branch(), "branches": branch.available_branches(),
            "can_switch": status.can_restart_to_update()}


@handler("about.switch_branch")
def about_switch_branch(params: dict) -> dict:
    """Update to another branch through the launcher, then quit."""
    from lib.shell.handlers.app import _hub
    name = str(params.get("name", ""))
    if name not in {b["name"] for b in branch.available_branches()}:
        raise ValueError("That branch isn't available.")
    if not status.can_restart_to_update():
        raise ValueError("Switching branches needs FA11y Launcher.exe. Run Updater.exe with --branch instead.")
    status.switch_branch(_hub(), name)
    return {}


@handler("about.check_updates")
def about_check_updates(_params: dict) -> dict:
    """Check GitHub now. found is true (newer version), false (up to date) or null (couldn't check)."""
    from lib.app.updater_check import check_once
    found = check_once()
    return {"found": found, "update": status.available_update(),
            "can_restart_to_update": status.can_restart_to_update()}
