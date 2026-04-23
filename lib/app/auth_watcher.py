"""
Epic auth expiration watcher + token validation helpers.

Lifted out of ``FA11y.py`` to keep the main entry focused on event
dispatch. This module has no FA11y imports — callers pass the shutdown
event and the ``on_auth_success`` callback that ``FA11y`` uses to wire
up dependent subsystems after a refresh.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)


def get_legendary_username() -> Optional[str]:
    """Return the username reported by ``legendary status``, or ``None``.

    Runs the Legendary CLI in a subprocess. The caller is expected to
    handle the ``None`` case (not logged in / Legendary not installed).
    """
    try:
        # chdir to this repo so legendary's config lives in the right place.
        script_dir = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)
        )))
        os.chdir(script_dir)
        result = subprocess.run(
            ["legendary", "status"], capture_output=True, text=True,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            if "Epic account:" in line:
                username = line.split("Epic account:")[1].strip()
                if username and username != "<not logged in>":
                    return username
        return None
    except Exception as e:
        print(f"Failed to run 'legendary status': {e}")
        return None


def validate_epic_auth(epic_auth) -> bool:
    """Validate an EpicAuth by hitting a cheap account endpoint.

    Returns True when the 200 response comes back, False on a clear 401.
    Any other outcome (network blip, unusual status) is optimistically
    treated as valid to avoid blocking startup on transient errors.
    """
    if not epic_auth or not epic_auth.access_token:
        return False
    try:
        response = requests.get(
            (
                "https://account-public-service-prod.ol.epicgames.com"
                f"/account/api/public/account/{epic_auth.account_id}"
            ),
            headers={"Authorization": f"Bearer {epic_auth.access_token}"},
            timeout=5,
        )
        if response.status_code == 401:
            logger.debug("Epic auth token expired (401 response)")
            return False
        if response.status_code == 200:
            logger.debug("Epic auth token validated successfully")
            return True
        logger.warning(
            f"Unexpected status during auth validation: {response.status_code}"
        )
        return True
    except Exception as e:
        logger.warning(f"Error validating Epic auth token: {e}")
        return True


def check_auth_expiration(
    shutdown_event: threading.Event,
    on_auth_success: Callable,
    *,
    initial_delay_s: float = 30.0,
    poll_interval_s: float = 60.0,
    refresh_window_minutes: int = 5,
) -> None:
    """Proactively refresh the Epic token just before it expires.

    Intended to run on a daemon thread. Wakes every ``poll_interval_s``,
    inspects the cached expiry from ``config_manager['epic_auth']``, and
    triggers ``epic_auth.refresh_access_token()`` when the token is inside
    the ``refresh_window_minutes`` window.

    On a successful refresh, calls ``on_auth_success(epic_auth)`` so the
    caller (FA11y.py) can re-wire any downstream systems that depend on
    the new token.
    """
    # Small initial wait so this doesn't race the first interactive login.
    if shutdown_event.wait(timeout=initial_delay_s):
        return

    # Lazy imports so this module remains dependency-light.
    from lib.utilities.epic_auth import get_epic_auth_instance
    from lib.config.config_manager import config_manager
    from datetime import datetime as dt, timedelta as td

    while not shutdown_event.is_set():
        if shutdown_event.wait(timeout=poll_interval_s):
            return
        try:
            epic_auth = get_epic_auth_instance()
            if not epic_auth.access_token or not epic_auth.is_valid:
                continue

            auth_data = config_manager.get("epic_auth")
            if not auth_data:
                continue

            expiry_str = auth_data.get("expires_at")
            if not expiry_str:
                continue

            expiry = dt.fromisoformat(expiry_str)
            time_until_expiry = expiry - dt.now()
            if time_until_expiry <= td(minutes=refresh_window_minutes):
                logger.info(
                    f"Token expires in {time_until_expiry}. "
                    "Attempting proactive refresh..."
                )
                if epic_auth.refresh_access_token():
                    logger.info("Proactive token refresh succeeded")
                    try:
                        on_auth_success(epic_auth)
                    except Exception as e:
                        logger.warning(
                            f"on_auth_success raised during proactive "
                            f"refresh wiring: {e}"
                        )
                else:
                    logger.warning(
                        "Proactive token refresh failed; "
                        "will fall back on 401 handling"
                    )
        except Exception as e:
            logger.error(f"Error in auth expiration check: {e}")
