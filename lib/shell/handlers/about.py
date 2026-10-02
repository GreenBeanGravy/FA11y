"""Requests for the About and updates page."""
from __future__ import annotations

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


@handler("about.check_updates")
def about_check_updates(_params: dict) -> dict:
    """Check GitHub now. found is true (newer version), false (up to date) or null (couldn't check)."""
    from lib.app.updater_check import check_once
    found = check_once()
    return {"found": found, "update": status.available_update(),
            "can_restart_to_update": status.can_restart_to_update()}
