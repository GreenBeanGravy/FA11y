"""
Background STW mission-alert poller.

Polls /world/info on an interval and speaks alerts for new V-Buck missions,
X-Ray Ticket missions, Legendary/Mythic survivor rewards, and Evo-mat /
PERK-UP rewards on 4-player missions. Filters to zones the player has
unlocked so brand-new F2P accounts don't hear Twine Peaks callouts.

Safety:
  - Default poll rate is 60 seconds (user-configurable).
  - On first 429 from any STW endpoint, the shared rate_limit_state flag
    trips and this monitor permanently downgrades to 5-minute polling for
    the remainder of the session.
  - Auto-suspends when FA11y isn't signed in to Epic.
  - Seen-set keyed by missionAlertGuid, reset at 00:00 UTC daily.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional, Set

from accessible_output2.outputs.auto import Auto

from lib.config.config_manager import config_manager
from lib.stw.api import STWApi, rate_limit_state
from lib.stw.world_info import MissionAlert, WorldInfoAPI

logger = logging.getLogger(__name__)


DEFAULT_POLL_SECONDS = 60
THROTTLED_POLL_SECONDS = 300  # downgraded rate after first 429
DEFAULT_TRIGGERS = {
    "vbucks": True,
    "xray": True,
    "legendary_survivor": True,
    "evo_mat_four_player": True,
    "perkup_four_player": True,
}


def _register_config() -> None:
    """Register the STW settings file with config_manager (idempotent)."""
    config_manager.register(
        "stw_settings",
        "config/stw_settings.json",
        format="json",
        default={
            "background_alerts_enabled": True,
            "poll_seconds": DEFAULT_POLL_SECONDS,
            "triggers": DEFAULT_TRIGGERS,
            "founder_override": "auto",  # auto | founder | non_founder
        },
    )


from lib.monitors.base import BaseMonitor


class STWAlertMonitor(BaseMonitor):
    """Polls /world/info and speaks high-value mission alerts."""

    _THREAD_NAME = "STWAlertMonitor"

    def __init__(self) -> None:
        super().__init__()
        self.speaker = Auto()

        # Seen-set, reset at UTC midnight.
        self._seen_alert_guids: Set[str] = set()
        self._last_reset_date: str = ""

        # Lazily constructed API objects — require EpicAuth singleton.
        self._world_info: Optional[WorldInfoAPI] = None
        self._stw_api: Optional[STWApi] = None

        _register_config()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------
    def _settings(self) -> dict:
        return config_manager.get("stw_settings") or {}

    def _enabled(self) -> bool:
        return bool(self._settings().get("background_alerts_enabled", True))

    def _poll_seconds(self) -> int:
        # Permanent throttle-downgrade once the session has seen a 429.
        if rate_limit_state.throttled_this_session():
            return THROTTLED_POLL_SECONDS
        try:
            return max(15, int(self._settings().get("poll_seconds", DEFAULT_POLL_SECONDS)))
        except (TypeError, ValueError):
            return DEFAULT_POLL_SECONDS

    def _triggers(self) -> dict:
        t = self._settings().get("triggers") or {}
        out = dict(DEFAULT_TRIGGERS)
        out.update({k: bool(v) for k, v in t.items() if k in DEFAULT_TRIGGERS})
        return out

    def _founder_override(self) -> str:
        return str(self._settings().get("founder_override", "auto") or "auto").lower()

    # ------------------------------------------------------------------
    # Auth / API bootstrap
    # ------------------------------------------------------------------
    def _ensure_apis(self) -> bool:
        """Lazily construct the API objects. Returns True when auth is
        available and objects exist."""
        if self._world_info is not None and self._stw_api is not None:
            return True
        try:
            from lib.utilities.epic_auth import get_epic_auth_instance
        except ImportError:
            return False
        auth = get_epic_auth_instance()
        if not auth or not auth.access_token or not auth.account_id:
            return False
        self._world_info = WorldInfoAPI(auth)
        self._stw_api = STWApi(auth)
        return True

    # ------------------------------------------------------------------
    # Day / seen-set rollover
    # ------------------------------------------------------------------
    def _reset_if_new_utc_day(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._last_reset_date:
            self._seen_alert_guids.clear()
            self._last_reset_date = today
            logger.info("STWAlertMonitor: UTC day rollover, seen-set cleared")

    # ------------------------------------------------------------------
    # Core poll
    # ------------------------------------------------------------------
    def _detect_new_alerts(self) -> List[MissionAlert]:
        """Fetch /world/info, filter to the user's unlocked zones, and
        return only alerts we haven't spoken yet."""
        if not self._ensure_apis():
            return []
        assert self._world_info is not None and self._stw_api is not None

        if not self._world_info.fetch():
            return []

        # Get unlocked zones; falls back to just Stonewood on error.
        try:
            if not self._stw_api.query_profile(cache_seconds=120):
                return []
            unlocked = self._stw_api.get_unlocked_zones()
        except Exception as e:
            logger.debug(f"STWAlertMonitor: unlocked-zone query failed: {e}")
            unlocked = ["Stonewood"]

        alerts = self._world_info.get_filtered_alerts(unlocked_zones=unlocked)
        triggers = self._triggers()
        founder_mode = self._founder_override()

        new_alerts: List[MissionAlert] = []
        for alert in alerts:
            if alert.mission_alert_guid in self._seen_alert_guids:
                continue

            worth_speaking = False
            if triggers.get("vbucks") and alert.has_vbucks:
                if founder_mode in ("auto", "founder"):
                    worth_speaking = True
            if triggers.get("xray") and alert.has_xray:
                if founder_mode in ("auto", "non_founder"):
                    worth_speaking = True
            if triggers.get("legendary_survivor") and alert.has_legendary_survivor:
                worth_speaking = True
            if triggers.get("evo_mat_four_player") and alert.has_evo_mat and alert.is_four_player:
                worth_speaking = True
            if triggers.get("perkup_four_player") and alert.has_perkup and alert.is_four_player:
                worth_speaking = True

            if worth_speaking:
                new_alerts.append(alert)
            # Mark every processed alert as seen regardless, so we don't
            # re-examine the same GUID every tick.
            self._seen_alert_guids.add(alert.mission_alert_guid)

        return new_alerts

    def _speak_new_alerts(self, alerts: List[MissionAlert]) -> None:
        if not alerts:
            return
        # Group the first few into a combined announcement so a bulk reset
        # doesn't produce a TTS firehose.
        capped = alerts[:4]
        parts = ["Save the World alerts."]
        for alert in capped:
            difficulty = alert.difficulty_label or ""
            where = f"{alert.theater_name}"
            if difficulty and difficulty != "-":
                where += f" {difficulty}"
            parts.append(
                f"{where}, {alert.mission_type or 'mission'}. "
                f"Reward: {alert.reward_summary}."
            )
        extra = len(alerts) - len(capped)
        if extra > 0:
            parts.append(f"Plus {extra} more in today's reset.")
        try:
            self.speaker.speak(" ".join(parts))
        except Exception as e:
            logger.info(f"STWAlertMonitor: speak failed: {e}")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def _monitor_loop(self) -> None:
        logger.info("STWAlertMonitor: loop started")
        # Small delay on first iteration so FA11y boot logs don't get drowned.
        first_delay = 20.0
        if self.stop_event.wait(timeout=first_delay):
            return
        while self.running:
            try:
                self._reset_if_new_utc_day()
                if not self._enabled():
                    # Check again in 30s.
                    if self.stop_event.wait(timeout=30.0):
                        return
                    continue
                new = self._detect_new_alerts()
                self._speak_new_alerts(new)
            except Exception as e:
                logger.debug(f"STWAlertMonitor: loop error: {e}")
            # Sleep interval honouring throttle state.
            interval = float(self._poll_seconds())
            if self.stop_event.wait(timeout=interval):
                return

    # Lifecycle inherited from BaseMonitor


stw_alert_monitor = STWAlertMonitor()
