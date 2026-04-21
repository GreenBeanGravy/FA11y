"""
Save the World mission alerts via the /world/info endpoint.

Parses the WorldInfoResponse into mission-alert records annotated with:
  - zone display name (inferred from the mission generator path + alert name,
    NOT theaterSlot — Epic recycles slot numbers across events so slot=2 can
    be Canny Valley on one account and the Phoenix event on another)
  - difficulty label (from missionDifficultyInfo.rowName)
  - four-player flag (from the mission generator; e.g. "FtS" = Fight the Storm)
  - reward template ids + quantities + rarity
  - time-until-expiry
  - flags for V-Bucks, X-Ray Tickets, Legendary/Mythic survivor, Evo mats,
    PERK-UP (for filter UI and the background announcer)

Mission alerts roll over at 00:00 UTC daily. Default cache window is 60s
and the alert monitor keeps its own seen-set keyed by missionAlertGuid.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from lib.utilities.epic_auth import EpicAuth
from lib.utilities.stw_api import (
    THEATER_SLOT_NAMES,
    parse_template_name,
    rate_limit_state,
    _parse_retry_after,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reward classification
# ---------------------------------------------------------------------------

VBUCK_MARKERS = ("voucher_mtx", "mtxgiveaway", "currency_mtxgiveaway")
XRAY_MARKERS = ("xrayllama", "currency_xrayllama")
LEGENDARY_SURVIVOR_MARKERS = ("worker:manager",)
LEGENDARY_RARITY_SUFFIXES = ("_sr_", "_ur_", "_sr.", "_ur.")
EVO_MAT_MARKERS = ("reagent_c_t0",)
PERKUP_MARKERS = ("reagent_alteration_upgrade_",)


# Zone inference: mapped from substrings in the alert name / categoryName /
# missionGenerator. Order matters — we use the first match found when
# scanning a string.
_ZONE_MARKERS: List[Tuple[str, str]] = [
    ("plankerton", "Plankerton"),
    ("cannyvalley", "Canny Valley"),
    ("canny_valley", "Canny Valley"),
    ("twinepeaks", "Twine Peaks"),
    ("twine_peaks", "Twine Peaks"),
    ("phoenix", "Ventures"),
    ("ventures", "Ventures"),
    ("stonewood", "Stonewood"),
    ("start", "Stonewood"),  # Theater_Start_* = Stonewood
]

# Mission generators hint at the mission type + group size. FtS, RtS, D3S
# are group-only (4-player); RtL, EtS, DtE can be solo.
_FOUR_PLAYER_GEN_MARKERS = (
    "_fts", "fight_the_storm", "ridetolightning",  # 4p mutators
    "_dts", "defend_the_shields",
    "_catx", "category4",  # cat-4 storms
    "mutantstorm", "mutant_storm",
)
_TEST_GENERATOR_MARKERS = (
    "/test", "testmissiongens", "dudebro", "debug_",
)


class MissionAlert:
    """Normalized mission alert record."""

    __slots__ = (
        "mission_alert_guid",
        "mission_guid",
        "theater_slot",
        "theater_name",
        "theater_id",
        "mission_type",
        "tile_index",
        "available_until",
        "difficulty_label",
        "row_name",
        "mission_generator",
        "raw_rewards",
        "reward_summary",
        "has_vbucks",
        "has_xray",
        "has_legendary_survivor",
        "has_evo_mat",
        "has_perkup",
        "is_four_player",
        "is_test_only",
    )

    def __init__(self) -> None:
        self.mission_alert_guid: str = ""
        self.mission_guid: str = ""
        self.theater_slot: int = -1
        self.theater_name: str = "Unknown"
        self.theater_id: str = ""
        self.mission_type: str = ""
        self.tile_index: int = -1
        self.available_until: str = ""
        self.difficulty_label: str = ""
        self.row_name: str = ""
        self.mission_generator: str = ""
        self.raw_rewards: List[Dict[str, Any]] = []
        self.reward_summary: str = ""
        self.has_vbucks: bool = False
        self.has_xray: bool = False
        self.has_legendary_survivor: bool = False
        self.has_evo_mat: bool = False
        self.has_perkup: bool = False
        self.is_four_player: bool = False
        self.is_test_only: bool = False

    def time_until_expiry_seconds(self) -> int:
        if not self.available_until:
            return -1
        try:
            ts = datetime.fromisoformat(self.available_until.replace("Z", "+00:00"))
            delta = ts - datetime.now(timezone.utc)
            return max(0, int(delta.total_seconds()))
        except (TypeError, ValueError):
            return -1

    def expiry_display(self) -> str:
        seconds = self.time_until_expiry_seconds()
        if seconds < 0:
            return "unknown"
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds // 60}m"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"

    def priority_score(self) -> int:
        """Higher = more interesting. Used for flat-list sort order."""
        score = 0
        if self.has_vbucks:
            score += 100
        if self.has_xray:
            score += 90
        if self.has_legendary_survivor:
            score += 80
        if self.has_evo_mat:
            score += 50
        if self.has_perkup:
            score += 20
        return score


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _classify_reward(template_id: str) -> Dict[str, bool]:
    lower = (template_id or "").lower()
    return {
        "vbucks": any(m in lower for m in VBUCK_MARKERS),
        "xray": any(m in lower for m in XRAY_MARKERS),
        "legendary_survivor": (
            any(m in lower for m in LEGENDARY_SURVIVOR_MARKERS)
            and any(s in lower for s in LEGENDARY_RARITY_SUFFIXES)
        ),
        "evo_mat": any(m in lower for m in EVO_MAT_MARKERS),
        "perkup": any(m in lower for m in PERKUP_MARKERS),
    }


def _reward_display_name(template_id: str, quantity: int) -> str:
    """Turn a raw reward template into a screen-reader-friendly string."""
    lower = (template_id or "").lower()
    if "voucher_mtx" in lower or "mtxgiveaway" in lower:
        return f"{quantity:,} V-Bucks"
    if "xrayllama" in lower:
        return f"{quantity:,} X-Ray Tickets"
    if "reagent_c_t01" in lower:
        return f"{quantity} Pure Drop of Rain"
    if "reagent_c_t02" in lower:
        return f"{quantity} Lightning in a Bottle"
    if "reagent_c_t03" in lower:
        return f"{quantity} Eye of the Storm"
    if "reagent_c_t04" in lower:
        return f"{quantity} Storm Shard"
    if "reagent_alteration_upgrade_c" in lower:
        return f"{quantity} Common PERK-UP"
    if "reagent_alteration_upgrade_uc" in lower:
        return f"{quantity} Uncommon PERK-UP"
    if "reagent_alteration_upgrade_r" in lower:
        return f"{quantity} Rare PERK-UP"
    if "reagent_alteration_upgrade_vr" in lower:
        return f"{quantity} Epic PERK-UP"
    if "reagent_alteration_upgrade_sr" in lower:
        return f"{quantity} Legendary PERK-UP"
    if "reagent_promotion_sr" in lower:
        return f"{quantity} Legendary Flux"
    if "reagent_promotion_vr" in lower:
        return f"{quantity} Epic Flux"
    if "reagent_promotion_r" in lower:
        return f"{quantity} Rare Flux"
    if "phoenixxp_reward" in lower:
        return f"{quantity:,} Phoenix XP"
    if "campaign_event_currency" in lower:
        return f"{quantity:,} Event Currency"
    if "worker:manager" in lower:
        rarity = "Legendary" if "_sr_" in lower else ("Mythic" if "_ur_" in lower else "Lead")
        return f"{rarity} Lead Survivor"
    # Fall through to the shared parser for Hero:, Schematic:, Defender:,
    # Worker:, etc — it produces readable names like
    # "Soldier Grenadegun (Uncommon T1)".
    if ":" in template_id:
        parsed = parse_template_name(template_id)
        bits = [parsed["name"]]
        trailing = []
        if parsed["rarity"]:
            trailing.append(parsed["rarity"])
        if parsed["tier"]:
            trailing.append(f"T{parsed['tier']}")
        if trailing:
            bits.append(f"({' '.join(trailing)})")
        qty_prefix = f"{quantity}x " if quantity and quantity != 1 else ""
        return f"{qty_prefix}{' '.join(bits)}"
    return f"{quantity}x {template_id}"


def _pretty_mission_type(generator: str) -> str:
    """Turn an Unreal missionGenerator path into a readable label."""
    if not generator:
        return "Unknown"
    last = generator.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
    for prefix in ("MissionGen_", "MissionGeneratorData_"):
        if last.startswith(prefix):
            last = last[len(prefix):]
    if last.endswith("_C"):
        last = last[:-2]
    # Strip leading difficulty/tier tokens like T1_, T2_, R5_.
    parts = last.split("_")
    while parts and (parts[0].startswith("T") and parts[0][1:].isdigit()
                     or parts[0].startswith("R") and parts[0][1:].isdigit()):
        parts = parts[1:]
    last = "_".join(parts)
    out = []
    for i, ch in enumerate(last):
        if i > 0 and ch.isupper() and (
            last[i - 1].islower()
            or (i + 1 < len(last) and last[i + 1].islower())
        ):
            out.append(" ")
        out.append(ch)
    return "".join(out).replace("_", " ").strip()


def _infer_zone(alert_name: str, category_name: str, row_name: str,
                generator: str, theater_slot: int) -> str:
    """Try very hard to figure out which zone this alert belongs to. Order:
       1. missionGenerator path (most reliable — contains /Plankerton/ etc.)
       2. missionDifficultyInfo.rowName (Theater_Phoenix_Zone5, etc.)
       3. alert name / categoryName (MutantStonewood, Phoenix, ...)
       4. theaterSlot as a last resort (often wrong on live accounts)
    """
    for marker, zone in _ZONE_MARKERS:
        if marker in (generator or "").lower():
            return zone
    for marker, zone in _ZONE_MARKERS:
        if marker in (row_name or "").lower():
            return zone
    for marker, zone in _ZONE_MARKERS:
        if marker in (alert_name or "").lower():
            return zone
    for marker, zone in _ZONE_MARKERS:
        if marker in (category_name or "").lower():
            return zone
    if isinstance(theater_slot, int):
        return THEATER_SLOT_NAMES.get(theater_slot, "Unknown")
    return "Unknown"


def _format_difficulty(row_name: str) -> str:
    """Theater_Hard_Zone5 -> 'Hard (Z5)'. Theater_Start_Zone1 -> 'Start (Z1)'.
    Returns '-' when rowName is empty."""
    if not row_name:
        return "-"
    # Strip Theater_ prefix.
    if row_name.startswith("Theater_"):
        row_name = row_name[len("Theater_"):]
    # Split into difficulty + zone.
    parts = row_name.split("_")
    if len(parts) >= 2 and parts[-1].lower().startswith("zone"):
        difficulty = " ".join(parts[:-1]).replace("_", " ")
        zone_token = parts[-1].lower().replace("zone", "Z")
        return f"{difficulty.strip().title()} ({zone_token})"
    return row_name.replace("_", " ").title()


def _is_four_player(generator: str, category_name: str) -> bool:
    lower = (generator or "").lower() + " " + (category_name or "").lower()
    return any(marker in lower for marker in _FOUR_PLAYER_GEN_MARKERS)


def _is_test_only(generator: str, theater_hidden: bool) -> bool:
    if theater_hidden:
        return True
    lower = (generator or "").lower()
    return any(marker in lower for marker in _TEST_GENERATOR_MARKERS)


# ---------------------------------------------------------------------------
# WorldInfo API
# ---------------------------------------------------------------------------

class WorldInfoAPI:
    """Fetches /world/info and parses mission alerts."""

    WORLD_INFO_URL = (
        "https://fortnite-public-service-prod11.ol.epicgames.com"
        "/fortnite/api/game/v2/world/info"
    )

    def __init__(self, auth: EpicAuth):
        self.auth = auth
        self._cached_raw: Optional[Dict] = None
        self._cached_at: float = 0.0

    def fetch(self, force: bool = False, cache_seconds: float = 60.0) -> bool:
        now = time.time()
        if (
            not force
            and self._cached_raw is not None
            and (now - self._cached_at) < cache_seconds
        ):
            return True
        if not self.auth.access_token:
            logger.warning("WorldInfoAPI.fetch: not authenticated")
            return False
        wait = rate_limit_state.seconds_until_safe()
        if wait > 0:
            logger.warning(
                f"WorldInfoAPI.fetch skipped; rate-limit cool-down {wait:.0f}s"
            )
            return False
        try:
            response = requests.get(
                self.WORLD_INFO_URL,
                params={"lang": "en-US"},
                headers={"Authorization": f"Bearer {self.auth.access_token}"},
                timeout=30,
            )
        except requests.RequestException as e:
            logger.error(f"WorldInfoAPI.fetch request error: {e}")
            return False
        if response.status_code == 429:
            rate_limit_state.note_throttled(_parse_retry_after(response))
            return False
        if response.status_code == 401:
            try:
                self.auth.invalidate_auth()
            except Exception:
                pass
            return False
        if response.status_code != 200:
            logger.error(
                f"WorldInfoAPI.fetch HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )
            return False
        try:
            self._cached_raw = response.json()
        except ValueError as e:
            logger.error(f"WorldInfoAPI.fetch JSON parse error: {e}")
            return False
        self._cached_at = now
        logger.info(
            f"WorldInfoAPI.fetch ok: theaters={len(self._cached_raw.get('theaters') or [])}, "
            f"missions buckets={len(self._cached_raw.get('missions') or [])}, "
            f"missionAlerts buckets={len(self._cached_raw.get('missionAlerts') or [])}"
        )
        return True

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    def _theaters(self) -> List[Dict[str, Any]]:
        return (self._cached_raw or {}).get("theaters", []) or []

    def parse_alerts(self, include_test: bool = False) -> List[MissionAlert]:
        """Parse the cached WorldInfoResponse into MissionAlert records."""
        if not self._cached_raw:
            return []

        # Index theaters by uniqueId for slot + hidden lookup.
        theaters_by_id: Dict[str, Dict[str, Any]] = {}
        for theater in self._theaters():
            unique_id = theater.get("uniqueId") or ""
            if unique_id:
                theaters_by_id[unique_id] = theater

        # Index missions by (theaterId, tileIndex) for alert cross-reference.
        # Epic puts mission defs under `availableMissions` (not `missions`).
        missions_by_tile: Dict[Tuple[str, int], Dict[str, Any]] = {}
        for bucket in (self._cached_raw.get("missions") or []):
            theater_id = bucket.get("theaterId", "")
            for m in bucket.get("availableMissions") or []:
                tile = m.get("tileIndex", -1)
                if theater_id and isinstance(tile, int):
                    missions_by_tile[(theater_id, tile)] = m

        out: List[MissionAlert] = []
        test_count = 0
        for bucket in (self._cached_raw.get("missionAlerts") or []):
            theater_id = bucket.get("theaterId", "")
            theater = theaters_by_id.get(theater_id) or {}
            slot = theater.get("theaterSlot")
            if not isinstance(slot, int):
                slot = -1
            theater_hidden = bool(
                theater.get("bHideLikeTestTheater") or theater.get("bIsTestTheater")
            )

            for alert_entry in bucket.get("availableMissionAlerts", []) or []:
                alert = MissionAlert()
                alert.mission_alert_guid = alert_entry.get("missionAlertGuid", "")
                alert.tile_index = int(alert_entry.get("tileIndex", -1) or -1)
                alert.available_until = alert_entry.get("availableUntil", "")
                alert.theater_slot = slot
                alert.theater_id = theater_id

                name = alert_entry.get("name") or ""
                category = alert_entry.get("categoryName") or ""

                # Cross-reference the bucketed mission by tileIndex to get
                # the mission generator + difficulty rowName.
                mission_def = missions_by_tile.get((theater_id, alert.tile_index)) or {}
                alert.mission_guid = mission_def.get("missionGuid", "")
                alert.mission_generator = mission_def.get("missionGenerator", "") or ""
                alert.row_name = (
                    (mission_def.get("missionDifficultyInfo") or {}).get("rowName")
                    or ""
                )
                alert.mission_type = _pretty_mission_type(alert.mission_generator) or "?"
                alert.difficulty_label = _format_difficulty(alert.row_name)
                alert.theater_name = _infer_zone(
                    name, category, alert.row_name, alert.mission_generator, slot
                )
                alert.is_four_player = _is_four_player(alert.mission_generator, category)
                alert.is_test_only = _is_test_only(alert.mission_generator, theater_hidden)

                if alert.is_test_only:
                    test_count += 1
                    if not include_test:
                        continue

                # Rewards.
                reward_items = (alert_entry.get("missionAlertRewards") or {}).get(
                    "items", []
                ) or []
                reward_strs: List[str] = []
                for reward in reward_items:
                    template_id = reward.get("itemType", "")
                    quantity = int(reward.get("quantity", 0) or 0)
                    alert.raw_rewards.append(
                        {
                            "template_id": template_id,
                            "quantity": quantity,
                            "attributes": reward.get("attributes") or {},
                        }
                    )
                    flags = _classify_reward(template_id)
                    alert.has_vbucks = alert.has_vbucks or flags["vbucks"]
                    alert.has_xray = alert.has_xray or flags["xray"]
                    alert.has_legendary_survivor = (
                        alert.has_legendary_survivor or flags["legendary_survivor"]
                    )
                    alert.has_evo_mat = alert.has_evo_mat or flags["evo_mat"]
                    alert.has_perkup = alert.has_perkup or flags["perkup"]
                    reward_strs.append(_reward_display_name(template_id, quantity))
                alert.reward_summary = ", ".join(reward_strs) or "(no rewards)"
                out.append(alert)

        logger.info(
            f"parse_alerts: total={len(out)} "
            f"(skipped {test_count} test/hidden-theater alerts)"
        )
        return out

    def get_filtered_alerts(
        self, unlocked_zones: Optional[List[str]] = None
    ) -> List[MissionAlert]:
        """Return alerts filtered to zones the player has unlocked.
        Pass `unlocked_zones` from STWApi.get_unlocked_zones()."""
        alerts = self.parse_alerts()
        if unlocked_zones is None:
            return alerts
        allowed = set(unlocked_zones)
        # Always allow Ventures (event theaters) unless the caller explicitly
        # dropped it. Every STW account can enter Ventures regardless of
        # campaign progression, so filtering out Ventures would hide the
        # post-F2P X-Ray Ticket reward slate.
        allowed.add("Ventures")
        filtered = [a for a in alerts if a.theater_name in allowed]
        logger.info(
            f"get_filtered_alerts: {len(filtered)}/{len(alerts)} match "
            f"unlocked zones {sorted(allowed)}"
        )
        return filtered

    def get_alerts_sorted_by_priority(
        self, unlocked_zones: Optional[List[str]] = None
    ) -> List[MissionAlert]:
        alerts = self.get_filtered_alerts(unlocked_zones)
        alerts.sort(key=lambda a: (-a.priority_score(), a.theater_name, a.tile_index))
        return alerts
