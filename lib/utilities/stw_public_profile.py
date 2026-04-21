"""
Public profile lookup for Save the World.

Given an Epic display name, resolve it to an account ID and then query the
public campaign profile via `QueryPublicProfile`. Everything is privacy-
permitting — Epic can 404/200-with-empty-profile at its discretion.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple

import requests

from lib.utilities.epic_auth import EpicAuth
from lib.utilities.stw_api import (
    FORT_STAT_ORDER,
    THEATER_SLOT_NAMES,
    rate_limit_state,
    _parse_retry_after,
)

logger = logging.getLogger(__name__)


class PublicProfileAPI:
    """Look up other players' STW profiles by display name."""

    ACCOUNT_LOOKUP_URL = (
        "https://account-public-service-prod.ol.epicgames.com"
        "/account/api/public/account/displayName"
    )
    MCP_GATEWAY = "https://fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api/game/v2/profile"

    def __init__(self, auth: EpicAuth):
        self.auth = auth
        # display_name -> (account_id, fetched_at)
        self._name_cache: Dict[str, Tuple[str, float]] = {}
        # account_id -> (profile_dict, fetched_at)
        self._profile_cache: Dict[str, Tuple[Dict, float]] = {}

    # ------------------------------------------------------------------
    # Display name -> account ID
    # ------------------------------------------------------------------
    def lookup_account_id(
        self, display_name: str, cache_seconds: float = 300.0
    ) -> Optional[str]:
        if not display_name:
            return None

        key = display_name.lower()
        now = time.time()
        hit = self._name_cache.get(key)
        if hit and (now - hit[1]) < cache_seconds:
            return hit[0]

        if not self.auth.access_token:
            logger.warning("PublicProfileAPI.lookup_account_id: not authenticated")
            return None

        wait = rate_limit_state.seconds_until_safe()
        if wait > 0:
            logger.warning(
                f"PublicProfileAPI.lookup_account_id skipped; cool-down {wait:.0f}s"
            )
            return None

        url = f"{self.ACCOUNT_LOOKUP_URL}/{requests.utils.quote(display_name)}"
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.auth.access_token}"},
                timeout=30,
            )
        except requests.RequestException as e:
            logger.error(f"PublicProfileAPI.lookup_account_id error: {e}")
            return None

        if response.status_code == 429:
            rate_limit_state.note_throttled(_parse_retry_after(response))
            return None
        if response.status_code == 404:
            # Unknown display name
            return None
        if response.status_code != 200:
            logger.error(
                f"PublicProfileAPI.lookup_account_id HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )
            return None

        try:
            data = response.json()
        except ValueError:
            return None

        account_id = data.get("id")
        if account_id:
            self._name_cache[key] = (account_id, now)
        return account_id

    # ------------------------------------------------------------------
    # Public campaign profile
    # ------------------------------------------------------------------
    def query_public_campaign_profile(
        self, account_id: str, force: bool = False, cache_seconds: float = 120.0
    ) -> Optional[Dict]:
        if not account_id:
            return None
        now = time.time()
        if not force:
            hit = self._profile_cache.get(account_id)
            if hit and (now - hit[1]) < cache_seconds:
                return hit[0]

        if not self.auth.access_token:
            logger.warning("PublicProfileAPI.query_public_campaign_profile: not authenticated")
            return None

        wait = rate_limit_state.seconds_until_safe()
        if wait > 0:
            return None

        url = f"{self.MCP_GATEWAY}/{account_id}/public/QueryPublicProfile"
        try:
            response = requests.post(
                url,
                params={"profileId": "campaign", "rvn": -1},
                headers={
                    "Authorization": f"Bearer {self.auth.access_token}",
                    "Content-Type": "application/json",
                },
                json={},
                timeout=30,
            )
        except requests.RequestException as e:
            logger.error(
                f"PublicProfileAPI.query_public_campaign_profile error: {e}"
            )
            return None

        if response.status_code == 429:
            rate_limit_state.note_throttled(_parse_retry_after(response))
            return None
        if response.status_code == 401:
            try:
                self.auth.invalidate_auth()
            except Exception:
                pass
            return None
        if response.status_code == 403:
            # Profile is private
            logger.info(
                f"PublicProfileAPI: profile {account_id} is private (403)"
            )
            return None
        if response.status_code != 200:
            logger.error(
                f"PublicProfileAPI.query_public_campaign_profile HTTP "
                f"{response.status_code}: {response.text[:200]}"
            )
            return None

        try:
            payload = response.json()
        except ValueError:
            return None
        changes = payload.get("profileChanges") or []
        if not changes:
            return None
        profile = changes[0].get("profile") or {}
        if profile:
            self._profile_cache[account_id] = (profile, now)
        return profile or None

    # ------------------------------------------------------------------
    # Convenience extractors (mirror STWApi helpers for public profile)
    # ------------------------------------------------------------------
    @staticmethod
    def extract_summary(profile: Dict) -> Dict[str, object]:
        """Pull a user-facing summary out of a public campaign profile."""
        stats = (profile.get("stats") or {}).get("attributes") or {}
        items = profile.get("items") or {}

        level = int(stats.get("level", 0) or 0)
        research = stats.get("research_levels") or {}
        fort = {k: int(research.get(k, 0) or 0) for k in FORT_STAT_ORDER}
        homebase_name = str(stats.get("homebase_name", "") or "")

        # Count items by category — more useful than raw lists.
        counts = {
            "heroes": 0,
            "schematics": 0,
            "survivors": 0,
            "defenders": 0,
        }
        for item in items.values():
            tid = item.get("templateId") or ""
            if tid.startswith("Hero:"):
                counts["heroes"] += 1
            elif tid.startswith("Schematic:"):
                counts["schematics"] += 1
            elif tid.startswith("Worker:"):
                counts["survivors"] += 1
            elif tid.startswith("Defender:"):
                counts["defenders"] += 1

        # Approximate PL: average FORT divided by 1.5.
        power_level = max(1, int(round(sum(fort.values()) / (len(FORT_STAT_ORDER) * 1.5))))

        # V-Bucks on public profile are typically NOT returned (privacy); if
        # they are, include the total.
        vbucks = 0
        for item in items.values():
            tid = item.get("templateId") or ""
            if tid in (
                "AccountResource:currency_mtxpurchased",
                "AccountResource:currency_mtxgiveaway",
                "AccountResource:currency_mtxcomplimentary",
            ):
                try:
                    vbucks += int(item.get("quantity", 0) or 0)
                except (TypeError, ValueError):
                    pass

        return {
            "level": level,
            "fort": fort,
            "power_level": power_level,
            "homebase_name": homebase_name,
            "counts": counts,
            "vbucks_visible": vbucks,
        }
