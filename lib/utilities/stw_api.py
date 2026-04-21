"""
Save the World (campaign profile) API helper for FA11y.

Full-featured wrapper around the Epic MCP campaign profile plus adjacent
STW-relevant profiles (common_core, common_public, theater0, outpost0,
collection_book_*). Supports read operations, destructive operations
(claim/recycle/upgrade/promote), and progression queries used to filter
mission alerts to zones the player has actually unlocked.

Shares the EpicAuth instance used by LockerAPI so the user only has to
sign in once for all Epic-backed features.
"""
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from lib.utilities.epic_auth import EpicAuth

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Resource catalog
# ---------------------------------------------------------------------------

# Friendly names for known AccountResource / Token templates. Unknown ones
# are still shown so nothing is silently dropped.
RESOURCE_NAMES: Dict[str, str] = {
    # Hard currency
    "AccountResource:currency_mtxpurchased": "V-Bucks",
    "AccountResource:currency_mtxgiveaway": "V-Bucks (earned)",
    "AccountResource:currency_mtxcomplimentary": "V-Bucks (complimentary)",
    "AccountResource:currency_xrayllama": "X-Ray Tickets",
    "AccountResource:eventcurrency_scaling": "Event Tickets",
    "AccountResource:voucher_generic": "Generic Voucher",
    "AccountResource:phoenixxp": "Phoenix XP",
    "AccountResource:founderschestgrantingxpforpt": "Founders Chest XP",
    # XP pools
    "AccountResource:hero_xp": "Hero XP",
    "AccountResource:schematic_xp": "Schematic XP",
    "AccountResource:personnel_xp": "Survivor XP",
    "AccountResource:reagent_c_xp": "Collection Book XP",
    # Evolution materials
    "AccountResource:reagent_c_t01": "Pure Drop of Rain",
    "AccountResource:reagent_c_t02": "Lightning in a Bottle",
    "AccountResource:reagent_c_t03": "Eye of the Storm",
    "AccountResource:reagent_c_t04": "Storm Shard",
    # PERK-UP by rarity
    "AccountResource:reagent_alteration_upgrade_c": "Common PERK-UP",
    "AccountResource:reagent_alteration_upgrade_uc": "Uncommon PERK-UP",
    "AccountResource:reagent_alteration_upgrade_r": "Rare PERK-UP",
    "AccountResource:reagent_alteration_upgrade_vr": "Epic PERK-UP",
    "AccountResource:reagent_alteration_upgrade_sr": "Legendary PERK-UP",
    "AccountResource:reagent_alteration_generic": "RE-PERK",
    # Flux
    "AccountResource:reagent_promotion_r": "Rare Flux",
    "AccountResource:reagent_promotion_vr": "Epic Flux",
    "AccountResource:reagent_promotion_sr": "Legendary Flux",
    "AccountResource:reagent_promotion_heroes": "Hero Flux",
    "AccountResource:reagent_promotion_survivors": "Survivor Flux",
    # Evolution recipes
    "AccountResource:reagent_evolverecipe_t01": "Training Manual",
    "AccountResource:reagent_evolverecipe_t02": "Weapon Research Manual",
    "AccountResource:reagent_evolverecipe_t03": "Trap Research Manual",
    "AccountResource:reagent_evolverecipe_t04": "People Research Manual",
    # Skill/Research points
    "Token:homebasepoints": "Skill Points",
    "Token:collectionresource_nuts_and_bolts": "Nuts and Bolts",
}

# Display order for the Overview resources section. Any resource not listed
# here is appended in alphabetical order at the end.
RESOURCE_ORDER: List[str] = [
    "AccountResource:currency_mtxpurchased",
    "AccountResource:currency_mtxgiveaway",
    "AccountResource:currency_mtxcomplimentary",
    "AccountResource:currency_xrayllama",
    "AccountResource:eventcurrency_scaling",
    "Token:homebasepoints",
    "AccountResource:reagent_c_t01",
    "AccountResource:reagent_c_t02",
    "AccountResource:reagent_c_t03",
    "AccountResource:reagent_c_t04",
    "AccountResource:hero_xp",
    "AccountResource:schematic_xp",
    "AccountResource:personnel_xp",
    "AccountResource:reagent_alteration_upgrade_c",
    "AccountResource:reagent_alteration_upgrade_uc",
    "AccountResource:reagent_alteration_upgrade_r",
    "AccountResource:reagent_alteration_upgrade_vr",
    "AccountResource:reagent_alteration_upgrade_sr",
    "AccountResource:reagent_alteration_generic",
    "AccountResource:reagent_promotion_r",
    "AccountResource:reagent_promotion_vr",
    "AccountResource:reagent_promotion_sr",
    "AccountResource:reagent_evolverecipe_t01",
    "AccountResource:reagent_evolverecipe_t02",
    "AccountResource:reagent_evolverecipe_t03",
    "AccountResource:reagent_evolverecipe_t04",
]

FORT_STAT_ORDER: List[str] = ["fortitude", "offense", "resistance", "technology"]
FORT_STAT_DISPLAY = {
    "fortitude": "Fortitude",
    "offense": "Offense",
    "resistance": "Resistance",
    "technology": "Tech",
}

# Zone theater slot hints. Epic recycles slot numbers across event theaters
# (e.g. Phoenix Ventures also lands on slot=2), so these are a fallback only.
# Real zone inference goes through quest + homebase-node markers below.
THEATER_SLOT_NAMES: Dict[int, str] = {
    0: "Stonewood",
    1: "Plankerton",
    2: "Canny Valley",
    3: "Twine Peaks",
    4: "Ventures",
}

# Zone inference markers. Applied as case-insensitive substring matches
# across Quest: item templateIds (any state) AND HomebaseNode: templateIds.
# Stonewood is present on every post-tutorial account; the others require
# a direct substring hit.
ZONE_MARKERS: Dict[str, List[str]] = {
    "Stonewood": ["stonewood"],
    "Plankerton": ["plankerton"],
    "Canny Valley": ["cannyvalley", "canny_valley"],
    "Twine Peaks": ["twinepeaks", "twine_peaks"],
}


# ---------------------------------------------------------------------------
# Template -> friendly name parser
# ---------------------------------------------------------------------------

_RARITY_CODE_TO_NAME: Dict[str, str] = {
    "c": "Common",
    "uc": "Uncommon",
    "r": "Rare",
    "vr": "Epic",
    "sr": "Legendary",
    "ur": "Mythic",
}

# Schematic FAMILY codes (first segment after sid_) -> default type label.
# For families with multiple sub-types (edged, blunt), an explicit sub-type
# token in the next segment overrides this default.
_SCHEMATIC_FAMILY_MAP: Dict[str, str] = {
    "assault": "Assault Rifle",
    "pistol": "Pistol",
    "shotgun": "Shotgun",
    "smg": "SMG",
    "sniper": "Sniper Rifle",
    "launcher": "Launcher",
    "rocketlauncher": "Rocket Launcher",
    "edged": "Sword",          # default; overridden by axe/scythe/spear subtype
    "blunt": "Club",            # default; overridden by hammer subtype
    "wall": "Wall Trap",
    "floor": "Floor Trap",
    "ceiling": "Ceiling Trap",
    "ammo": "Ammo",
    "ingredient": "Ingredient",
}

# Sub-family override tokens that take precedence over the family default.
# Encountered as the second token after sid_ in e.g. sid_edged_axe_*.
_SCHEMATIC_SUBFAMILY_MAP: Dict[str, str] = {
    "sword": "Sword",
    "axe": "Axe",
    "scythe": "Scythe",
    "spear": "Spear",
    "dagger": "Dagger",
    "hammer": "Hammer",
    "club": "Club",
}

# Element / material codes used on schematic templates.
_SCHEMATIC_MATERIAL_MAP: Dict[str, str] = {
    "ore": "Ore",
    "crystal": "Crystal",
    "shadowshard": "Shadowshard",
    "sunbeam": "Sunbeam",
    "obsidian": "Obsidian",
    "brightcore": "Brightcore",
    "physical": "Physical",
    "fire": "Fire",
    "water": "Water",
    "nature": "Nature",
    "energy": "Energy",
}

_HERO_CLASS_MAP: Dict[str, str] = {
    "soldier": "Soldier",
    "ninja": "Ninja",
    "constructor": "Constructor",
    "outlander": "Outlander",
    "commando": "Soldier",
    "assassin": "Ninja",
    "sentinel": "Constructor",
    "raider": "Outlander",
}


def _titleize(token: str) -> str:
    """Insert spaces between camelCase boundaries and title-case the result."""
    if not token:
        return ""
    out: List[str] = []
    for i, ch in enumerate(token):
        if i > 0 and ch.isupper() and (
            token[i - 1].islower()
            or (i + 1 < len(token) and token[i + 1].islower())
        ):
            out.append(" ")
        out.append(ch)
    return "".join(out).replace("_", " ").strip().title()


def parse_template_name(template_id: str) -> Dict[str, str]:
    """Extract a readable name + rarity + tier from a full templateId.

    Returns a dict with at least {"name", "rarity", "tier", "kind"}.
    Handles Hero:, Schematic:, Worker:, Defender:, Token:, AccountResource:,
    Gadget:, TeamPerk:, Alteration:. Falls back to the last segment title-
    cased when the template doesn't fit a known pattern.
    """
    if not template_id:
        return {"name": "(unknown)", "rarity": "", "tier": "", "kind": ""}

    kind, _, remainder = template_id.partition(":")
    kind = kind or ""
    segments = remainder.lower().split("_") if remainder else []

    rarity = ""
    tier = ""
    # Tier is the trailing "t01".."t05" segment.
    if segments and segments[-1].startswith("t") and segments[-1][1:].isdigit():
        tier = str(int(segments[-1][1:]))
        segments = segments[:-1]
    # Rarity is the segment matching a code. Scan from right so that
    # `ore_t01` style templates pick the correct rarity before the material.
    for idx in range(len(segments) - 1, -1, -1):
        if segments[idx] in _RARITY_CODE_TO_NAME:
            rarity = _RARITY_CODE_TO_NAME[segments[idx]]
            segments = segments[:idx] + segments[idx + 1:]
            break

    # Per-kind parsing.
    if kind == "Hero":
        # Expected: hid_<class>_<subclass...>
        if segments and segments[0] == "hid":
            segments = segments[1:]
        cls = ""
        if segments and segments[0] in _HERO_CLASS_MAP:
            cls = _HERO_CLASS_MAP[segments[0]]
            segments = segments[1:]
        sub = " ".join(_titleize(s) for s in segments) if segments else ""
        name = f"{cls} {sub}".strip() or _titleize(remainder)
    elif kind == "Schematic":
        # Expected: sid_<family>_<subtype...>_<rarity>_<material>_<tier>
        #   family   = edged|blunt|pistol|assault|shotgun|sniper|smg|launcher|
        #              wall|floor|ceiling
        #   subtype  = specific weapon name (auto, sword, boltrevolver, …)
        #   material = ore|crystal|shadowshard|… (melee+ranged only)
        #
        # Produces names like:
        #   sid_pistol_auto_uc_ore_t01              -> "Auto Pistol (Ore)"
        #   sid_edged_sword_light_c_ore_t01          -> "Light Sword (Ore)"
        #   sid_edged_axe_medium_laser_vr_ore_t01    -> "Medium Laser Axe (Ore)"
        #   sid_wall_wood_spikes_r_t01                -> "Wood Spikes Wall Trap"
        #   ammo_explosive                            -> "Explosive Ammo"
        #   ingredient_blastpowder                    -> "Blast Powder Ingredient"
        if segments and segments[0] == "sid":
            segments = segments[1:]

        # Pull out material (ore/crystal/etc.) — weapon-only token.
        material = ""
        for mat_code in list(_SCHEMATIC_MATERIAL_MAP.keys()):
            if mat_code in segments:
                material = _SCHEMATIC_MATERIAL_MAP[mat_code]
                segments = [s for s in segments if s != mat_code]
                break

        # Family default label.
        family_label = ""
        if segments and segments[0] in _SCHEMATIC_FAMILY_MAP:
            family_label = _SCHEMATIC_FAMILY_MAP[segments[0]]
            segments = segments[1:]

        # Sub-family override: edged_axe / edged_scythe / blunt_hammer.
        # These take priority over the family default ("Axe" not "Sword").
        if segments and segments[0] in _SCHEMATIC_SUBFAMILY_MAP:
            family_label = _SCHEMATIC_SUBFAMILY_MAP[segments[0]]
            segments = segments[1:]

        # Drop any descriptor word that's already baked into family_label.
        # Prevents "Sword Sword Light" when family==Sword and descriptor
        # accidentally echoes it.
        if family_label:
            family_words = {w.lower() for w in family_label.split()}
            segments = [s for s in segments if s.lower() not in family_words]

        descriptor_words = [_titleize(s) for s in segments if s]

        # Reading order: "{Descriptor} {Family}" — so sid_pistol_auto_*
        # becomes "Auto Pistol" and sid_edged_axe_medium_laser_* becomes
        # "Medium Laser Axe".
        if family_label and descriptor_words:
            name = f"{' '.join(descriptor_words)} {family_label}".strip()
        elif family_label:
            name = family_label
        elif descriptor_words:
            name = " ".join(descriptor_words)
        else:
            name = _titleize(remainder) or "Schematic"

        # Material goes in parens so the main name stays clean. Rarity/tier
        # are appended by format_template_display.
        if material:
            name = f"{name} ({material})"
    elif kind == "Worker":
        # Examples: workerbasic_uc_t01, manager_martialartist_sr_ore_t03
        if segments and segments[0] == "workerbasic":
            name = "Survivor"
        elif segments and segments[0] in ("manager", "leaderbasic"):
            # Managers are squad leaders with a specialty.
            specialty = " ".join(_titleize(s) for s in segments[1:])
            name = f"Lead Survivor{': ' + specialty if specialty else ''}"
        else:
            name = _titleize("_".join(segments)) or "Survivor"
    elif kind == "Defender":
        # Examples: defender_soldier_r_t01, defender_ninja_vr_ore_t03,
        #           did_defendersniper_basic_c_t01 (from reward streams)
        if segments and segments[0] in ("defender", "did"):
            segments = segments[1:]
        # Some defender templates carry "defender<weapon>_basic" — split out.
        if segments and segments[0].startswith("defender"):
            weapon = segments[0][len("defender"):] or "generic"
            segments = [weapon] + segments[1:]
        cls = ""
        if segments and segments[0] in _HERO_CLASS_MAP:
            cls = _HERO_CLASS_MAP[segments[0]]
            segments = segments[1:]
        extra = " ".join(_titleize(s) for s in segments if s != "basic")
        name = f"Defender ({cls or (extra or 'Generic')})"
        if cls and extra:
            name = f"Defender ({cls}) {extra}"
    elif kind in ("Gadget", "TeamPerk", "Alteration"):
        if segments and segments[0] in ("g", "tp", "aid", "att"):
            segments = segments[1:]
        name = " ".join(_titleize(s) for s in segments) or _titleize(remainder)
    elif kind == "AccountResource":
        # Fallback to RESOURCE_NAMES where available; else titleize.
        name = RESOURCE_NAMES.get(template_id, _titleize(remainder))
    elif kind == "Token":
        name = RESOURCE_NAMES.get(template_id, _titleize(remainder))
    else:
        name = _titleize(remainder) or template_id

    return {
        "name": name,
        "rarity": rarity,
        "tier": tier,
        "kind": kind,
    }


def format_template_display(template_id: str, level: str = "") -> str:
    """Shorthand: 'Name (Rarity T2 L5)'. Omits empty parts."""
    parsed = parse_template_name(template_id)
    extras = []
    if parsed["rarity"]:
        extras.append(parsed["rarity"])
    if parsed["tier"]:
        extras.append(f"T{parsed['tier']}")
    if level:
        extras.append(f"L{level}")
    suffix = f" ({' '.join(extras)})" if extras else ""
    return f"{parsed['name']}{suffix}"


# ---------------------------------------------------------------------------
# Perk (Alteration) parsing
# ---------------------------------------------------------------------------

# Stat codes used in Alteration templates.
_PERK_STAT_MAP: Dict[str, str] = {
    "damage": "Damage",
    "damage_physical": "Physical Damage",
    "damage_energy": "Energy Damage",
    "firerate": "Fire Rate",
    "firerate_ranged": "Fire Rate",
    "firerate_melee": "Attack Speed",
    "reloadspeed": "Reload Speed",
    "reloadspeed_ranged": "Reload Speed",
    "magazinesize": "Magazine Size",
    "critchance": "Crit Chance",
    "critdamage": "Crit Damage",
    "headshotdamage": "Headshot Damage",
    "stability": "Stability",
    "accuracy": "Accuracy",
    "range": "Range",
    "maxdurability": "Durability",
    "maxdurability_trap": "Trap Durability",
    "buildingmaxhealth": "Trap Max Health",
    "lifeleech": "Life Leech",
    "knockback": "Knockback",
    "weapon_swap_speed": "Swap Speed",
}

_PERK_ELEMENT_MAP: Dict[str, str] = {
    "fire": "Fire",
    "water": "Water",
    "nature": "Nature",
    "energy": "Energy",
}

_PERK_CONDITIONAL_MAP: Dict[str, str] = {
    "slowed": "vs Slowed",
    "afflicted": "vs Afflicted",
    "stunned": "vs Stunned",
    "knocked_back": "vs Knocked-back",
    "airborne": "vs Airborne",
    "lowhealth": "at Low HP",
    "fullhealth": "at Full HP",
    "fullmag": "on Full Mag",
    "emptymag": "on Empty Mag",
}

_PERK_CONDITIONAL_EFFECT_MAP: Dict[str, str] = {
    "dmgbonus": "damage",
    "critrate": "crit rate",
    "critdamage": "crit damage",
    "reload": "reload speed",
    "firerate": "fire rate",
    "movespeed": "move speed",
}

# Special unique-effect perks (the 6th slot on most weapons).
_PERK_GENERIC_MAP: Dict[str, str] = {
    "onmeleehit_stackbuff_critrate": "On melee hit: stacking crit rate",
    "ranged_headshot_explodeondeath_v2": "Headshot kill: enemies explode",
    "onrangedfire_stackbuff_damage": "Ranged hits: stacking damage",
    "weapon_knockback_impact_v2": "Melee impact: bonus knockback",
    "weapon_pellet_chain": "Shotgun pellet chain reaction",
    "melee_slow_on_hit": "Melee hits slow enemies",
    "ranged_reloadspeed_on_empty": "Empty mag: faster reload",
}


def parse_perk(template_id: str) -> Dict[str, str]:
    """Parse an Alteration templateId into a short description + tier.

    Inputs look like:
        Alteration:aid_att_damage_physical_t02
        Alteration:aid_ele_fire_t03
        Alteration:aid_conditional_slowed_dmgbonus_t03
        Alteration:aid_g_onmeleehit_stackbuff_critrate

    Output: {"desc": human string, "tier": "1"|"2"|"3"|"4"|"5"|"", "raw": tid}
    """
    if not template_id:
        return {"desc": "(empty)", "tier": "", "raw": template_id}
    remainder = template_id.split(":", 1)[-1].lower()
    segments = remainder.split("_")
    # Strip 'aid' prefix.
    if segments and segments[0] == "aid":
        segments = segments[1:]
    # Extract tier if trailing _t0N.
    tier = ""
    if segments and segments[-1].startswith("t") and segments[-1][1:].isdigit():
        tier = str(int(segments[-1][1:]))
        segments = segments[:-1]
    if not segments:
        return {"desc": _titleize(remainder), "tier": tier, "raw": template_id}

    kind = segments[0]
    rest = segments[1:]

    if kind == "att":
        # att_<stat>[_<qualifier>]
        joined = "_".join(rest)
        stat_label = _PERK_STAT_MAP.get(joined)
        if not stat_label and len(rest) >= 2:
            # Try dropping trailing qualifier.
            stat_label = _PERK_STAT_MAP.get("_".join(rest[:-1]))
            if stat_label:
                rest = rest[:-1]
        if not stat_label:
            stat_label = _titleize(joined)
        desc = f"+{stat_label}"
    elif kind == "ele":
        element = _PERK_ELEMENT_MAP.get(rest[0] if rest else "", _titleize(rest[0]) if rest else "")
        desc = f"{element} Damage"
    elif kind == "conditional":
        if len(rest) >= 2:
            cond = _PERK_CONDITIONAL_MAP.get(rest[0], _titleize(rest[0]))
            effect = _PERK_CONDITIONAL_EFFECT_MAP.get(rest[1], _titleize(rest[1]))
            desc = f"{cond}: +{effect}"
        else:
            desc = _titleize("_".join(rest))
    elif kind == "g":
        joined = "_".join(rest)
        desc = _PERK_GENERIC_MAP.get(joined) or _titleize(joined)
    else:
        desc = _titleize("_".join(segments))
    return {"desc": desc, "tier": tier, "raw": template_id}


def format_perk(template_id: str) -> str:
    parsed = parse_perk(template_id)
    if parsed["tier"]:
        return f"{parsed['desc']} (T{parsed['tier']})"
    return parsed["desc"]


# ---------------------------------------------------------------------------
# Rate limit / throttle tracking (shared across all API classes)
# ---------------------------------------------------------------------------

class RateLimitState:
    """Shared back-off tracker. First 429 permanently slows background polling
    to 5 min for the rest of the session (per §10 of the STW API reference).

    All API classes consult this via the module-level singleton so a 429 from
    any endpoint (world info, MCP, etc.) influences every subsequent poll.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._retry_until: float = 0.0
        self._throttled_this_session: bool = False

    def note_throttled(self, retry_after_seconds: float) -> None:
        now = time.time()
        with self._lock:
            self._retry_until = max(self._retry_until, now + max(retry_after_seconds, 1.0))
            self._throttled_this_session = True
        logger.warning(
            f"STW API rate limit hit. Backing off until {self._retry_until:.0f} "
            f"(+{retry_after_seconds:.0f}s). Background polling downgraded to 5 min."
        )

    def seconds_until_safe(self) -> float:
        with self._lock:
            remaining = self._retry_until - time.time()
            return max(0.0, remaining)

    def throttled_this_session(self) -> bool:
        with self._lock:
            return self._throttled_this_session


rate_limit_state = RateLimitState()


def _parse_retry_after(response: requests.Response) -> float:
    """Extract the retry-after hint from a 429 response, preferring Epic's
    messageVars[0] (which is the canonical form) before falling back to the
    standard Retry-After header or a 60s default."""
    try:
        body = response.json()
    except ValueError:
        body = {}
    message_vars = body.get("messageVars") if isinstance(body, dict) else None
    if isinstance(message_vars, list) and message_vars:
        try:
            return float(message_vars[0])
        except (TypeError, ValueError):
            pass
    header = response.headers.get("Retry-After")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    return 60.0


# ---------------------------------------------------------------------------
# STWApi — own-account campaign profile with full MCP operation set
# ---------------------------------------------------------------------------

class STWApi:
    """Full-featured accessor for the Save the World (campaign) MCP profile."""

    # Gateway MCP host (preferred per §3).
    MCP_GATEWAY = "https://fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api/game/v2/profile"

    def __init__(self, auth: EpicAuth):
        self.auth = auth
        self.profile: Optional[Dict] = None
        self.common_core: Optional[Dict] = None
        self._profile_fetch_time: float = 0.0
        self._common_core_fetch_time: float = 0.0
        # Last Epic error from an MCP call — exposed so callers can show
        # specific messages (e.g. "already claimed today" vs "out of currency").
        self.last_error_code: str = ""
        self.last_error_message: str = ""

    # ------------------------------------------------------------------
    # Low-level MCP plumbing
    # ------------------------------------------------------------------
    def _mcp_request(
        self,
        operation: str,
        profile_id: str = "campaign",
        body: Optional[Dict] = None,
        rvn: int = -1,
        scope: str = "client",
    ) -> Optional[Dict]:
        """POST a single MCP operation. Returns the parsed JSON response, or
        None on HTTP/transport failure. Callers handle None as 'operation did
        not run' and surface to the user separately."""
        if not self.auth.access_token or not self.auth.account_id:
            logger.warning(f"STWApi._mcp_request({operation}): not authenticated")
            return None

        # Respect the shared back-off window. If we're in a cool-down, refuse
        # the call rather than piling more throttles on top.
        wait = rate_limit_state.seconds_until_safe()
        if wait > 0:
            logger.warning(
                f"STWApi._mcp_request({operation}) skipped; rate-limit cool-down "
                f"has {wait:.0f}s remaining"
            )
            return None

        # Don't log the body for QueryProfile since we call it often; log other
        # ops at INFO so destructive actions leave an audit trail.
        if operation not in ("QueryProfile",):
            body_summary = "{}"
            if body:
                # Trim body to keep logs readable; keys matter most.
                try:
                    body_summary = str({k: v for k, v in body.items() if k != "targetItemIds"})
                    if "targetItemIds" in body:
                        body_summary += f", targetItemIds=[{len(body['targetItemIds'])} items]"
                except Exception:
                    body_summary = "<unloggable>"
            logger.info(
                f"STWApi MCP {operation} profile={profile_id} body={body_summary}"
            )

        url = f"{self.MCP_GATEWAY}/{self.auth.account_id}/{scope}/{operation}"
        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.auth.access_token}",
                    "Content-Type": "application/json",
                },
                params={"profileId": profile_id, "rvn": rvn},
                json=body if body is not None else {},
                timeout=30,
            )
        except requests.RequestException as e:
            logger.error(f"STWApi._mcp_request({operation}) request error: {e}")
            return None

        if response.status_code == 429:
            rate_limit_state.note_throttled(_parse_retry_after(response))
            return None

        if response.status_code == 401:
            # Delegate to EpicAuth's invalidation path (which triggers the
            # existing auto-reauth flow).
            logger.warning(f"STWApi._mcp_request({operation}): 401, invalidating auth")
            try:
                self.auth.invalidate_auth()
            except Exception:
                pass
            return None

        if response.status_code != 200:
            # Capture structured error details for callers.
            try:
                err_body = response.json()
            except ValueError:
                err_body = {"errorMessage": response.text[:500]}
            self.last_error_code = str(err_body.get("errorCode") or "")
            self.last_error_message = str(err_body.get("errorMessage") or "")
            logger.error(
                f"STWApi._mcp_request({operation}) HTTP {response.status_code}: "
                f"{self.last_error_code} — {self.last_error_message[:300]}"
            )
            return None

        # Clear error state on success.
        self.last_error_code = ""
        self.last_error_message = ""

        try:
            parsed = response.json()
        except ValueError as e:
            logger.error(f"STWApi._mcp_request({operation}) JSON parse error: {e}")
            return None

        # Useful post-op logging: count notifications (loot, rewards).
        if operation not in ("QueryProfile",):
            notes = parsed.get("notifications") or []
            logger.info(
                f"STWApi MCP {operation} ok: "
                f"profileRevision={parsed.get('profileRevision', '?')}, "
                f"notifications={len(notes)}"
            )
        return parsed

    # ------------------------------------------------------------------
    # Profile fetches
    # ------------------------------------------------------------------
    def query_profile(self, force: bool = False, cache_seconds: float = 30.0) -> bool:
        """Fetch the campaign profile. Uses a 30s cache by default so opening
        multiple sub-dialogs in sequence doesn't round-trip each time."""
        now = time.time()
        if (
            not force
            and self.profile is not None
            and (now - self._profile_fetch_time) < cache_seconds
        ):
            logger.debug("STWApi.query_profile: cache hit")
            return True

        payload = self._mcp_request("QueryProfile", profile_id="campaign")
        if not payload:
            logger.warning("STWApi.query_profile: MCP request failed")
            return False
        changes = payload.get("profileChanges") or []
        if not changes:
            logger.warning("STWApi.query_profile: no profileChanges in response")
            return False
        self.profile = changes[0].get("profile") or {}
        self._profile_fetch_time = now
        item_count = len(self.profile.get("items") or {})
        logger.info(
            f"STWApi.query_profile ok: {item_count} items, "
            f"rvn={self.profile.get('rvn', '?')}, "
            f"commandRevision={self.profile.get('commandRevision', '?')}"
        )
        return bool(self.profile)

    def query_common_core(self, force: bool = False, cache_seconds: float = 60.0) -> bool:
        """Fetch the common_core profile (V-Bucks, catalog purchases, gift boxes)."""
        now = time.time()
        if (
            not force
            and self.common_core is not None
            and (now - self._common_core_fetch_time) < cache_seconds
        ):
            return True

        payload = self._mcp_request("QueryProfile", profile_id="common_core")
        if not payload:
            return False
        changes = payload.get("profileChanges") or []
        if not changes:
            return False
        self.common_core = changes[0].get("profile") or {}
        self._common_core_fetch_time = now
        return bool(self.common_core)

    # ------------------------------------------------------------------
    # Profile extraction helpers
    # ------------------------------------------------------------------
    def _items(self) -> Dict[str, Dict]:
        return (self.profile or {}).get("items", {}) or {}

    def _stats(self) -> Dict:
        return ((self.profile or {}).get("stats") or {}).get("attributes") or {}

    def _common_core_items(self) -> Dict[str, Dict]:
        return (self.common_core or {}).get("items", {}) or {}

    def get_commander_level(self) -> Tuple[int, int]:
        stats = self._stats()
        level = int(stats.get("level", 0) or 0)
        xp = int(stats.get("xp", 0) or 0)
        return level, xp

    def get_fort_stats(self) -> Dict[str, int]:
        stats = self._stats()
        research = stats.get("research_levels") or {}
        out: Dict[str, int] = {}
        for key in FORT_STAT_ORDER:
            try:
                out[key] = int(research.get(key, 0) or 0)
            except (TypeError, ValueError):
                out[key] = 0
        return out

    def get_resources(self) -> List[Tuple[str, str, int]]:
        totals: Dict[str, int] = {}
        for item in self._items().values():
            template = item.get("templateId") or ""
            if not (
                template.startswith("AccountResource:")
                or template.startswith("Token:")
            ):
                continue
            try:
                qty = int(item.get("quantity", 0) or 0)
            except (TypeError, ValueError):
                qty = 0
            totals[template] = totals.get(template, 0) + qty

        ordered: List[Tuple[str, str, int]] = []
        seen: set = set()
        for tid in RESOURCE_ORDER:
            if tid in totals:
                ordered.append((tid, RESOURCE_NAMES.get(tid, tid), totals[tid]))
                seen.add(tid)

        extras = sorted(
            (tid for tid in totals if tid not in seen),
            key=lambda t: RESOURCE_NAMES.get(t, t).lower(),
        )
        for tid in extras:
            ordered.append((tid, RESOURCE_NAMES.get(tid, tid), totals[tid]))
        return ordered

    def get_resource_quantity(self, template_id: str) -> int:
        total = 0
        for item in self._items().values():
            if item.get("templateId") == template_id:
                try:
                    total += int(item.get("quantity", 0) or 0)
                except (TypeError, ValueError):
                    pass
        return total

    def get_total_vbucks(self) -> int:
        # Sum across both campaign and common_core since different Epic
        # accounts store V-Bucks in different buckets post-F2P.
        total = 0
        buckets = (
            "AccountResource:currency_mtxpurchased",
            "AccountResource:currency_mtxgiveaway",
            "AccountResource:currency_mtxcomplimentary",
            "Currency:MtxPurchased",
            "Currency:MtxGiveaway",
            "Currency:MtxComplimentary",
        )
        for item in self._items().values():
            if item.get("templateId") in buckets:
                try:
                    total += int(item.get("quantity", 0) or 0)
                except (TypeError, ValueError):
                    pass
        for item in self._common_core_items().values():
            if item.get("templateId") in buckets:
                try:
                    total += int(item.get("quantity", 0) or 0)
                except (TypeError, ValueError):
                    pass
        return total

    def get_research_points_available(self) -> int:
        stats = self._stats()
        try:
            return int(stats.get("research_points", 0) or 0)
        except (TypeError, ValueError):
            return 0

    def get_homebase_name(self) -> str:
        return str(self._stats().get("homebase_name", "") or "")

    def get_equipped_hero(self) -> Optional[Dict[str, str]]:
        """Return info about the currently active commander. Uses the schema
        Epic actually returns: attributes.crew_members (lowercase keys)."""
        stats = self._stats()
        loadout_guid = stats.get("selected_hero_loadout")
        if not loadout_guid:
            logger.debug("get_equipped_hero: no selected_hero_loadout in stats")
            return None
        loadout = self._items().get(loadout_guid)
        if not loadout:
            logger.debug(
                f"get_equipped_hero: loadout guid {loadout_guid} not in items"
            )
            return None
        attrs = loadout.get("attributes") or {}
        # The real schema uses `crew_members` with lowercase slot keys:
        #   commanderslot, followerslot1..followerslot5
        crew = attrs.get("crew_members") or attrs.get("crew_slots_items") or {}
        commander_id = ""
        if isinstance(crew, dict):
            commander_id = (
                crew.get("commanderslot")
                or crew.get("CommanderSlot")
                or ""
            )
        if not commander_id:
            logger.debug("get_equipped_hero: commander slot empty")
            return None
        commander_item = self._items().get(commander_id) or {}
        template_id = commander_item.get("templateId", "")
        level = str((commander_item.get("attributes") or {}).get("level", "") or "")
        return {
            "loadout_name": attrs.get("loadout_name", "")
                           or loadout.get("templateId", "").rsplit(":", 1)[-1],
            "template_id": template_id,
            "level": level,
            "display_name": format_template_display(template_id, level=level),
        }

    # ------------------------------------------------------------------
    # Progression / zone unlock
    # ------------------------------------------------------------------
    def get_founder_status(self) -> bool:
        """Heuristic: the player is a Founder if their campaign profile has
        ever been granted the Founders' Chest item (HomebaseBannerIcon:
        sb_founderspack_*) or has any mtxgiveaway V-Bucks history. Post-F2P
        players lack both. Overridable via STW settings."""
        items = self._items()
        for item in items.values():
            template = (item.get("templateId") or "").lower()
            if "founderspack" in template or "founders_pack" in template:
                return True
            if template == "accountresource:currency_mtxgiveaway":
                try:
                    if int(item.get("quantity", 0) or 0) > 0:
                        return True
                except (TypeError, ValueError):
                    pass
        # stats.attributes may also carry an explicit flag
        stats = self._stats()
        if stats.get("mfa_reward_claimed") and stats.get("founder_pack_id"):
            return True
        return False

    def get_unlocked_zones(self) -> List[str]:
        """Return a list of zone display names the player has unlocked.

        Only counts evidence of actual progression, never commander level —
        on the current F2P account a level-56 user can still be gated in
        Stonewood. Evidence accepted:
          - Any Quest: or HomebaseNode: templateId containing the zone's
            marker substring.
          - Ventures: any ventures_* / phoenix_* / campaign_event_currency
            / event_currency key or item.

        Stonewood is always included because every account that completed
        the tutorial has it; the data exposes this as homebaseonboarding*.
        """
        items = self._items()
        zone_hits: Dict[str, int] = {zone: 0 for zone in ZONE_MARKERS}

        for item in items.values():
            template = (item.get("templateId") or "").lower()
            if not (
                template.startswith("quest:")
                or template.startswith("homebasenode:")
            ):
                continue
            for zone, markers in ZONE_MARKERS.items():
                if any(marker in template for marker in markers):
                    zone_hits[zone] += 1

        unlocked = {zone for zone, count in zone_hits.items() if count > 0}
        unlocked.add("Stonewood")  # tutorial minimum

        # Ventures: presence of ventures_* / phoenix_* stat or
        # campaign_event_currency (the post-F2P Phoenix event).
        stats = self._stats()
        for key in stats.keys():
            lower = key.lower()
            if "ventures" in lower or "phoenix" in lower or "event_currency" in lower:
                unlocked.add("Ventures")
                break
        if "Ventures" not in unlocked:
            for item in items.values():
                tid = (item.get("templateId") or "").lower()
                if "phoenix" in tid or "event_currency" in tid or "ventures" in tid:
                    unlocked.add("Ventures")
                    break

        order = ["Stonewood", "Plankerton", "Canny Valley", "Twine Peaks", "Ventures"]
        result = [z for z in order if z in unlocked]
        logger.info(
            f"get_unlocked_zones: {result} (hits: "
            f"{ {z: c for z, c in zone_hits.items() if c} })"
        )
        return result

    def get_power_level(self) -> int:
        """Approximate power level from FORT stats. The true in-game PL
        formula incorporates squad bonuses + research + training + survivor
        leads; this approximation is good enough for a 'roughly around PL X'
        announcement."""
        fort = self.get_fort_stats()
        # Epic's PL formula averages the four FORT stats and divides by 1.5.
        total = sum(fort.values())
        return max(1, int(round(total / (len(FORT_STAT_ORDER) * 1.5))))

    # ------------------------------------------------------------------
    # Item listings (by templateId prefix)
    # ------------------------------------------------------------------
    def list_items_by_prefix(self, prefix: str) -> List[Tuple[str, Dict]]:
        """Return (itemId, item_dict) pairs for every profile item whose
        templateId starts with `prefix`. Prefixes of interest:
          Hero:      heroes
          Schematic: weapons/traps/melee
          Worker:    survivors (prefix covers Worker: and Worker:manager_)
          Defender:  AI defenders
        """
        out: List[Tuple[str, Dict]] = []
        for item_id, item in self._items().items():
            template = item.get("templateId") or ""
            if template.startswith(prefix):
                out.append((item_id, item))
        return out

    def get_prerolled_offers(self) -> List[Tuple[str, Dict]]:
        """Return PrerollData:* items — the llama store offers. Each item's
        attributes.items[] array is the llama's contents preview, and
        attributes.offerId is what you pass to PurchaseCatalogEntry."""
        return self.list_items_by_prefix("PrerollData:")

    def get_card_packs(self) -> List[Tuple[str, Dict]]:
        """Return CardPack:* items — unopened llamas owned by the account."""
        return self.list_items_by_prefix("CardPack:")

    def get_hero_loadouts(self) -> List[Tuple[str, Dict]]:
        return self.list_items_by_prefix("CampaignHeroLoadout:")

    def get_heroes(self) -> List[Tuple[str, Dict]]:
        return self.list_items_by_prefix("Hero:")

    def get_assignable_heroes(self) -> List[Tuple[str, Dict]]:
        """Return heroes that are usable: NOT in inventory overflow.

        In STW, when the player's hero collection exceeds the limit, Epic
        moves surplus heroes into an "overflow" state. Overflow heroes
        CANNOT be slotted, claimed, or used until the player clears
        overflow in-game (recycle/transform excess to drop under the cap).

        Epic's signal for this: the hero's `attributes.inventory_overflow_date`
        attribute is present. The date value is when the hero was moved to
        overflow — not an expiry — so treat any presence of the field as
        "overflow, unusable". Assigning an overflow hero returns
        `errors.com.epicgames.fortnite.invalid_inventory_overflow_operation`.
        """
        out: List[Tuple[str, Dict]] = []
        overflow_count = 0
        for hero_id, item in self.get_heroes():
            attrs = item.get("attributes") or {}
            if attrs.get("inventory_overflow_date"):
                overflow_count += 1
                continue
            out.append((hero_id, item))
        if overflow_count:
            logger.info(
                f"get_assignable_heroes: {overflow_count} heroes in overflow, "
                f"excluded from assignment options"
            )
        return out

    def get_unlocked_follower_slots(self) -> int:
        """Return the number of follower slots unlocked (1-5). Detected by
        counting HomebaseNode items matching `questreward_newfollower<N>_slot`.
        Slot 0 (commander) is always available."""
        unlocked = 0
        for item in self._items().values():
            tid = (item.get("templateId") or "").lower()
            # Match questreward_newfollower<digit>_slot
            for n in (1, 2, 3, 4, 5):
                if f"questreward_newfollower{n}_slot" in tid:
                    unlocked = max(unlocked, n)
        return unlocked

    def get_schematics(self) -> List[Tuple[str, Dict]]:
        return self.list_items_by_prefix("Schematic:")

    def get_survivors(self) -> List[Tuple[str, Dict]]:
        return self.list_items_by_prefix("Worker:")

    def get_defenders(self) -> List[Tuple[str, Dict]]:
        return self.list_items_by_prefix("Defender:")

    # ------------------------------------------------------------------
    # Quest / expedition helpers
    # ------------------------------------------------------------------
    def get_daily_quests(self) -> List[Tuple[str, Dict]]:
        """Return (itemId, quest_item) pairs for daily quests currently on
        the campaign profile. Only quests whose quest_state is Active are
        returned, so freshly-claimed ones drop off automatically."""
        out: List[Tuple[str, Dict]] = []
        for item_id, item in self._items().items():
            template = (item.get("templateId") or "")
            if not template.startswith("Quest:"):
                continue
            name = template.lower()
            attrs = item.get("attributes") or {}
            state = attrs.get("quest_state", "")
            # "daily" markers identify the rotating slate.
            if ("daily" in name or "dailyquest" in name) and state == "Active":
                out.append((item_id, item))
        return out

    def get_expeditions(self) -> Dict[str, List[Tuple[str, Dict]]]:
        """Separate expedition items into 'active' (in-progress) and
        'completed' (ready to collect)."""
        active: List[Tuple[str, Dict]] = []
        completed: List[Tuple[str, Dict]] = []
        for item_id, item in self._items().items():
            template = item.get("templateId") or ""
            if not template.startswith("Expedition:"):
                continue
            attrs = item.get("attributes") or {}
            if attrs.get("expedition_end_time"):
                # Expiration time is in ISO-8601; anything past now is
                # completed and ready to collect.
                end_time = attrs.get("expedition_end_time", "")
                if self._is_iso_past(end_time):
                    completed.append((item_id, item))
                else:
                    active.append((item_id, item))
            else:
                active.append((item_id, item))
        return {"active": active, "completed": completed}

    @staticmethod
    def _is_iso_past(iso_string: str) -> bool:
        if not iso_string:
            return False
        try:
            from datetime import datetime, timezone
            ts = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
            return ts < datetime.now(timezone.utc)
        except (TypeError, ValueError):
            return False

    # ------------------------------------------------------------------
    # MCP write operations
    # ------------------------------------------------------------------
    def claim_mission_alert_rewards(self) -> bool:
        res = self._mcp_request("ClaimMissionAlertRewards")
        return res is not None

    def claim_quest_reward(self, quest_id: str, selected_reward_index: int = 0) -> bool:
        res = self._mcp_request(
            "ClaimQuestReward",
            body={"questId": quest_id, "selectedRewardIndex": selected_reward_index},
        )
        return res is not None

    def client_quest_login(self) -> bool:
        res = self._mcp_request("ClientQuestLogin")
        return res is not None

    def generate_daily_quests(self) -> bool:
        res = self._mcp_request("GenerateDailyQuests")
        return res is not None

    def reroll_daily_quest(self, quest_id: str) -> bool:
        res = self._mcp_request("FortRerollDailyQuest", body={"questId": quest_id})
        return res is not None

    def update_quest_client_objectives(self, advance: List[Dict]) -> bool:
        res = self._mcp_request(
            "UpdateQuestClientObjectives", body={"advance": advance}
        )
        return res is not None

    def refresh_expeditions(self) -> bool:
        res = self._mcp_request("RefreshExpeditions")
        return res is not None

    def collect_expedition(self, expedition_id: str, expedition_template: str) -> bool:
        res = self._mcp_request(
            "CollectExpedition",
            body={
                "expeditionId": expedition_id,
                "expeditionTemplate": expedition_template,
            },
        )
        return res is not None

    def abandon_expedition(self, expedition_id: str) -> bool:
        res = self._mcp_request(
            "AbandonExpedition", body={"expeditionId": expedition_id}
        )
        return res is not None

    def populate_prerolled_offers(self) -> bool:
        res = self._mcp_request("PopulatePrerolledOffers")
        return res is not None

    def purchase_catalog_entry(
        self,
        offer_id: str,
        purchase_quantity: int = 1,
        currency: str = "MtxCurrency",
        currency_sub_type: str = "",
        expected_total_price: int = 0,
        game_context: str = "",
    ) -> Optional[Dict]:
        return self._mcp_request(
            "PurchaseCatalogEntry",
            profile_id="common_core",
            body={
                "offerId": offer_id,
                "purchaseQuantity": purchase_quantity,
                "currency": currency,
                "currencySubType": currency_sub_type,
                "expectedTotalPrice": expected_total_price,
                "gameContext": game_context,
            },
        )

    def open_card_pack(self, card_pack_item_id: str, selection_idx: int = -1) -> Optional[Dict]:
        return self._mcp_request(
            "OpenCardPack",
            body={"cardPackItemId": card_pack_item_id, "selectionIdx": selection_idx},
        )

    def assign_worker_to_squad(
        self, squad_id: str, character_id: str, slot_idx: int
    ) -> bool:
        res = self._mcp_request(
            "AssignWorkerToSquad",
            body={"squadId": squad_id, "characterId": character_id, "slotIdx": slot_idx},
        )
        return res is not None

    def unassign_all_squads(self) -> bool:
        res = self._mcp_request("UnassignAllSquads")
        return res is not None

    def set_active_hero_loadout(self, selected_loadout: str) -> bool:
        res = self._mcp_request(
            "SetActiveHeroLoadout", body={"selectedLoadout": selected_loadout}
        )
        return res is not None

    def assign_hero_to_loadout(
        self, slot_name: str, loadout_id: str, hero_id: str
    ) -> bool:
        res = self._mcp_request(
            "AssignHeroToLoadout",
            body={"slotName": slot_name, "loadoutId": loadout_id, "heroId": hero_id},
        )
        return res is not None

    def assign_gadget_to_loadout(
        self, slot_index: int, loadout_id: str, item_id: str
    ) -> bool:
        res = self._mcp_request(
            "AssignGadgetToLoadout",
            body={
                "slotIndex": slot_index,
                "loadoutId": loadout_id,
                "itemId": item_id,
            },
        )
        return res is not None

    def assign_team_perk_to_loadout(self, loadout_id: str, item_id: str) -> bool:
        res = self._mcp_request(
            "AssignTeamPerkToLoadout",
            body={"loadoutId": loadout_id, "itemId": item_id},
        )
        return res is not None

    def clear_hero_loadout(self, loadout_id: str) -> bool:
        res = self._mcp_request("ClearHeroLoadout", body={"loadoutId": loadout_id})
        return res is not None

    def purchase_or_upgrade_homebase_node(self, node_id: str) -> bool:
        res = self._mcp_request(
            "PurchaseOrUpgradeHomebaseNode", body={"nodeId": node_id}
        )
        return res is not None

    def purchase_research_stat_upgrade(self, stat_id: str) -> bool:
        res = self._mcp_request(
            "PurchaseResearchStatUpgrade", body={"statId": stat_id}
        )
        return res is not None

    def set_homebase_name(self, homebase_name: str) -> bool:
        res = self._mcp_request("SetHomebaseName", body={"homebaseName": homebase_name})
        return res is not None

    def set_homebase_banner(self, banner_icon_id: str, banner_color_id: str) -> bool:
        res = self._mcp_request(
            "SetHomebaseBanner",
            body={
                "homebaseBannerIconId": banner_icon_id,
                "homebaseBannerColorId": banner_color_id,
            },
        )
        return res is not None

    def unlock_region(self, region_id: str) -> bool:
        res = self._mcp_request("UnlockRegion", body={"regionId": region_id})
        return res is not None

    def upgrade_item_rarity(self, target_item_id: str) -> bool:
        res = self._mcp_request(
            "UpgradeItemRarity", body={"targetItemId": target_item_id}
        )
        return res is not None

    def promote_item(self, target_item_id: str) -> bool:
        res = self._mcp_request("PromoteItem", body={"targetItemId": target_item_id})
        return res is not None

    def recycle_item(self, target_item_id: str) -> bool:
        res = self._mcp_request("RecycleItem", body={"targetItemId": target_item_id})
        return res is not None

    def recycle_item_batch(self, target_item_ids: List[str]) -> bool:
        res = self._mcp_request(
            "RecycleItemBatch", body={"targetItemIds": target_item_ids}
        )
        return res is not None

    def apply_alteration(
        self, target_item_id: str, alteration_id: str, alteration_slot: int
    ) -> bool:
        res = self._mcp_request(
            "ApplyAlteration",
            body={
                "targetItemId": target_item_id,
                "alterationId": alteration_id,
                "alterationSlot": alteration_slot,
            },
        )
        return res is not None

    def respec_alteration(self, target_item_id: str) -> bool:
        res = self._mcp_request(
            "RespecAlteration", body={"targetItemId": target_item_id}
        )
        return res is not None

    def convert_item(
        self,
        target_item_id: str,
        conversion_index: int = 0,
        conversion_recipe_idx: int = 0,
    ) -> bool:
        res = self._mcp_request(
            "ConvertItem",
            body={
                "targetItemId": target_item_id,
                "conversionIndex": conversion_index,
                "conversionRecipeIdx": conversion_recipe_idx,
            },
        )
        return res is not None

    def craft_world_item(
        self, target_schematic_item_id: str, target_count: int = 1
    ) -> bool:
        res = self._mcp_request(
            "CraftWorldItem",
            body={
                "targetSchematicItemId": target_schematic_item_id,
                "targetCount": target_count,
            },
        )
        return res is not None

    def claim_collection_book_rewards(self) -> bool:
        res = self._mcp_request("ClaimCollectionBookRewards")
        return res is not None

    def research_item_from_collection_book(self, template_id: str) -> bool:
        res = self._mcp_request(
            "ResearchItemFromCollectionBook", body={"templateId": template_id}
        )
        return res is not None

    def claim_collected_resources(self, collectors_to_claim: List[str]) -> bool:
        res = self._mcp_request(
            "ClaimCollectedResources",
            body={"collectorsToClaim": collectors_to_claim},
        )
        return res is not None

    def storage_transfer(self, transfer_operations: List[Dict]) -> bool:
        res = self._mcp_request(
            "StorageTransfer", body={"transferOperations": transfer_operations}
        )
        return res is not None

    def mark_new_quest_notification_sent(self, item_ids: List[str]) -> bool:
        res = self._mcp_request(
            "MarkNewQuestNotificationSent", body={"itemIds": item_ids}
        )
        return res is not None


# ---------------------------------------------------------------------------
# Storefront catalog (for llama pricing)
# ---------------------------------------------------------------------------

class CatalogAPI:
    """Fetches /fortnite/api/storefront/v2/catalog and provides per-offer
    pricing lookups. Prices aren't on the PrerollData profile items — they
    live in the catalog, keyed by offerId.

    STW-relevant storefronts at time of writing:
      CardPackStorePreroll          — the daily llamas (free + paid)
      STWRotationalEventStorefront  — event schematic/hero purchases
      STWSpecialEventStorefront     — event-limited purchases
      CardPackStoreGameplay         — quest/reward vouchers (bronze etc.)
    """

    CATALOG_URL = (
        "https://fngw-mcp-gc-livefn.ol.epicgames.com"
        "/fortnite/api/storefront/v2/catalog"
    )

    # Storefronts whose catalog entries are worth fetching for STW. The rest
    # (BR season data, music passes, etc.) aren't useful here.
    STW_STOREFRONT_NAMES = {
        "CardPackStorePreroll",
        "STWRotationalEventStorefront",
        "STWSpecialEventStorefront",
        "CardPackStoreGameplay",
    }

    def __init__(self, auth: EpicAuth):
        self.auth = auth
        self._cache: Optional[Dict] = None
        self._cache_at: float = 0.0
        # offer_id -> pricing dict
        self._offer_index: Dict[str, Dict] = {}

    def fetch(self, force: bool = False, cache_seconds: float = 300.0) -> bool:
        now = time.time()
        if not force and self._cache is not None and (now - self._cache_at) < cache_seconds:
            return True
        if not self.auth.access_token:
            logger.warning("CatalogAPI.fetch: not authenticated")
            return False
        wait = rate_limit_state.seconds_until_safe()
        if wait > 0:
            logger.warning(f"CatalogAPI.fetch skipped; cool-down {wait:.0f}s")
            return False
        try:
            response = requests.get(
                self.CATALOG_URL,
                headers={"Authorization": f"Bearer {self.auth.access_token}"},
                timeout=30,
            )
        except requests.RequestException as e:
            logger.error(f"CatalogAPI.fetch request error: {e}")
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
                f"CatalogAPI.fetch HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )
            return False
        try:
            self._cache = response.json()
        except ValueError as e:
            logger.error(f"CatalogAPI.fetch JSON parse error: {e}")
            return False
        self._cache_at = now
        self._rebuild_offer_index()
        logger.info(
            f"CatalogAPI.fetch ok: indexed {len(self._offer_index)} STW offers"
        )
        return True

    def _rebuild_offer_index(self) -> None:
        self._offer_index.clear()
        if not self._cache:
            return
        for storefront in self._cache.get("storefronts") or []:
            name = storefront.get("name", "")
            if name not in self.STW_STOREFRONT_NAMES:
                continue
            for entry in storefront.get("catalogEntries") or []:
                offer_id = entry.get("offerId") or entry.get("devName") or ""
                if not offer_id:
                    continue
                prices = entry.get("prices") or []
                primary = prices[0] if prices else {}
                meta = entry.get("meta") or {}
                # Purchase limits: Epic sometimes puts them on meta, sometimes
                # in meta.EventLimit or via daily_limit semantics.
                purchase_limit = None
                for lim_key in ("EventLimit", "DailyLimit", "purchaseLimit"):
                    if lim_key in meta:
                        try:
                            purchase_limit = int(meta[lim_key])
                            break
                        except (TypeError, ValueError):
                            pass
                self._offer_index[offer_id] = {
                    "offer_id": offer_id,
                    "dev_name": entry.get("devName", ""),
                    "storefront": name,
                    "currency": primary.get("currencyType", "") or "",
                    "currency_sub_type": primary.get("currencySubType", "") or "",
                    "final_price": int(primary.get("finalPrice", 0) or 0),
                    "regular_price": int(primary.get("regularPrice", 0) or 0),
                    "purchase_limit": purchase_limit,
                    "meta": meta,
                    "raw": entry,
                }

    def get_offer_pricing(self, offer_id: str) -> Optional[Dict]:
        if not offer_id:
            return None
        # Attempt lazy fetch on first lookup.
        if not self._offer_index:
            self.fetch()
        return self._offer_index.get(offer_id)

    def list_offers_for_storefront(self, storefront_name: str) -> List[Dict]:
        if not self._offer_index:
            self.fetch()
        return [
            entry for entry in self._offer_index.values()
            if entry.get("storefront") == storefront_name
        ]


# Friendly currency labels for UI rendering.
CURRENCY_DISPLAY_NAMES: Dict[str, str] = {
    "AccountResource:currency_xrayllama": "X-Ray Tickets",
    "AccountResource:eventcurrency_scaling": "Event Currency",
    "AccountResource:voucher_cardpack_bronze": "Bronze Voucher",
    "AccountResource:voucher_cardpack_silver": "Silver Voucher",
    "AccountResource:voucher_cardpack_gold": "Gold Voucher",
    "AccountResource:voucher_cardpack_persistent_anniversary": "Anniversary Voucher",
    "AccountResource:voucher_basicpack": "Mini Llama Voucher",
    "AccountResource:voucher_custom_firecracker_r": "Daily Login Voucher",
    "AccountResource:campaign_event_currency": "Event Currency",
}


def format_price(pricing: Optional[Dict]) -> str:
    """Turn a CatalogAPI pricing dict into a short human string."""
    if not pricing:
        return "?"
    final = pricing.get("final_price", 0)
    currency = pricing.get("currency", "")
    sub = pricing.get("currency_sub_type", "")
    if currency == "MtxCurrency":
        label = "V-Bucks"
    elif currency == "RealMoney":
        label = "USD"
    else:
        label = CURRENCY_DISPLAY_NAMES.get(sub, sub.rsplit(":", 1)[-1] or "?")
    if final == 0:
        return f"FREE ({label})"
    return f"{final:,} {label}"
