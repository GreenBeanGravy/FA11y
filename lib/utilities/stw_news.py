"""
Unauthenticated STW news/MOTD and Lightswitch service status.

These endpoints are useful to surface in the STW manager even when the
user isn't signed in, so they live here separately from stw_api.py.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

import requests

from lib.utilities.epic_auth import EpicAuth

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# STW News / MOTD
# ---------------------------------------------------------------------------

class FortniteNewsAPI:
    """Fetches the STW news/MOTD page (no auth required)."""

    NEWS_URL = (
        "https://fortnitecontent-website-prod07.ol.epicgames.com"
        "/content/api/pages/fortnite-game/savetheworldnews"
    )

    def __init__(self):
        self._cache: Optional[Dict] = None
        self._cache_at: float = 0.0

    def fetch(self, force: bool = False, cache_seconds: float = 300.0) -> bool:
        now = time.time()
        if not force and self._cache is not None and (now - self._cache_at) < cache_seconds:
            return True
        try:
            response = requests.get(self.NEWS_URL, timeout=20)
        except requests.RequestException as e:
            logger.error(f"FortniteNewsAPI.fetch error: {e}")
            return False
        if response.status_code != 200:
            logger.error(
                f"FortniteNewsAPI.fetch HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )
            return False
        try:
            self._cache = response.json()
        except ValueError:
            return False
        self._cache_at = now
        return True

    def get_motd_entries(self) -> List[Dict[str, str]]:
        """Return a list of {title, body, image} entries for the STW MOTD."""
        out: List[Dict[str, str]] = []
        if not self._cache:
            return out
        news = (
            (self._cache.get("savetheworldnews") or {})
            .get("news", {})
            .get("messages")
        ) or []
        for entry in news:
            out.append(
                {
                    "title": str(entry.get("title", "") or ""),
                    "body": str(entry.get("body", "") or ""),
                    "image": str(entry.get("image", "") or ""),
                }
            )
        return out


# ---------------------------------------------------------------------------
# Lightswitch service status
# ---------------------------------------------------------------------------

class LightswitchAPI:
    """Queries Fortnite service status (/lightswitch/...)."""

    LIGHTSWITCH_URL = (
        "https://lightswitch-public-service-prod06.ol.epicgames.com"
        "/lightswitch/api/service/bulk/status"
    )

    def __init__(self, auth: EpicAuth):
        self.auth = auth
        self._cache: Optional[List[Dict]] = None
        self._cache_at: float = 0.0

    def fetch(self, force: bool = False, cache_seconds: float = 60.0) -> bool:
        if not self.auth.access_token:
            return False
        now = time.time()
        if not force and self._cache is not None and (now - self._cache_at) < cache_seconds:
            return True
        try:
            response = requests.get(
                self.LIGHTSWITCH_URL,
                params={"serviceId": "Fortnite"},
                headers={"Authorization": f"Bearer {self.auth.access_token}"},
                timeout=20,
            )
        except requests.RequestException as e:
            logger.error(f"LightswitchAPI.fetch error: {e}")
            return False
        if response.status_code != 200:
            logger.error(
                f"LightswitchAPI.fetch HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )
            return False
        try:
            self._cache = response.json()
        except ValueError:
            return False
        self._cache_at = now
        return True

    def get_status_summary(self) -> Dict[str, str]:
        """Return {status, message, allowedActions} for the main Fortnite service."""
        if not self._cache:
            return {"status": "Unknown", "message": "", "allowed_actions": ""}
        for entry in self._cache:
            if entry.get("serviceInstanceId") == "fortnite":
                allowed = ", ".join(entry.get("allowedActions", []) or [])
                return {
                    "status": str(entry.get("status", "") or ""),
                    "message": str(entry.get("message", "") or ""),
                    "allowed_actions": allowed,
                }
        return {"status": "Unknown", "message": "", "allowed_actions": ""}
