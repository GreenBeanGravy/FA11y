"""
Template-ID to real game-name lookup for Save the World items.

Source data: `lib/utilities/data/stw_name_lookup.json` — extracted directly
from the Fortnite PAK files via a CUE4Parse-backed `stw_parser` tool. Keyed
by the exact lowercase templateId form that Epic's MCP QueryProfile returns.

Example: `Schematic:sid_assault_bone_vr_ore_t04` -> "Primal Rifle".

When `resolve_template_name()` misses the exact key, a small amount of
normalization is attempted (see `_fallback_keys`) for known formatting
variations (e.g. defender weapon-class-only lookups, reward-stream `did_`
prefixes). If no variant matches, returns None so the caller can fall back
to the heuristic parser in stw_api.py.

This module is loaded lazily on first call and cached for the process
lifetime. The JSON file is ~800 KB — no runtime cost outside of the first
import.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


_DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "name_lookup.json"
)


class _Lookup:
    """Thread-safe lazy loader for the name lookup JSON."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: Optional[Dict[str, Dict]] = None
        self._version: str = ""
        self._load_attempted: bool = False
        self._load_failed: bool = False

    def load(self) -> bool:
        # Fast path — already loaded.
        if self._items is not None:
            return True
        if self._load_failed:
            return False
        with self._lock:
            if self._items is not None:
                return True
            if self._load_failed:
                return False
            self._load_attempted = True
            if not os.path.exists(_DATA_PATH):
                logger.warning(
                    f"stw_name_lookup: data file not found at {_DATA_PATH}; "
                    f"falling back to heuristic names only"
                )
                self._load_failed = True
                return False
            try:
                with open(_DATA_PATH, "r", encoding="utf-8") as fh:
                    payload = json.load(fh)
            except (OSError, ValueError) as e:
                logger.error(
                    f"stw_name_lookup: failed to load {_DATA_PATH}: {e}"
                )
                self._load_failed = True
                return False
            items = payload.get("items")
            if not isinstance(items, dict):
                logger.error(
                    f"stw_name_lookup: unexpected payload shape in {_DATA_PATH}"
                )
                self._load_failed = True
                return False
            self._items = items
            self._version = str(payload.get("version", ""))
            logger.info(
                f"stw_name_lookup: loaded {len(self._items)} entries "
                f"(version={self._version or 'unknown'})"
            )
            return True

    def get(self, key: str) -> Optional[Dict]:
        if not self.load():
            return None
        return self._items.get(key) if self._items else None

    def stats(self) -> Dict[str, object]:
        self.load()
        return {
            "loaded": self._items is not None,
            "version": self._version,
            "entry_count": len(self._items) if self._items else 0,
            "data_path": _DATA_PATH,
            "data_exists": os.path.exists(_DATA_PATH),
        }


_lookup_singleton = _Lookup()


# ---------------------------------------------------------------------------
# Key normalisation helpers
# ---------------------------------------------------------------------------

_RARITY_TOKENS = ("c", "uc", "r", "vr", "sr", "ur")
_MATERIAL_TOKENS = (
    "ore", "crystal", "shadowshard", "sunbeam", "obsidian", "brightcore",
)


def _strip_rarity_material_tier(segments: List[str]) -> List[str]:
    """Return segments with known rarity codes, material codes, and
    trailing tier tokens removed. Preserves order."""
    out: List[str] = []
    for seg in segments:
        if seg.startswith("t") and seg[1:].isdigit():
            # Trailing tier
            continue
        if seg in _RARITY_TOKENS:
            continue
        if seg in _MATERIAL_TOKENS:
            continue
        out.append(seg)
    return out


def _fallback_keys(template_id: str) -> List[str]:
    """Generate alternative lookup keys for a templateId that missed on the
    exact-match lookup. Only returns keys that are likely to match the kind
    of synthetic / collapsed entries we store in the data file.

    Focuses on:
      - Defender: MCP returns instance variants like
        `Defender:defender_pistol_r_ore_t04` but we only store the Blueprint
        CDO variants `Defender:default__defender_pistol_c`. Map between them.
      - Reward-stream shorthand: `did_defenderpistol_basic_c_t01` style that
        ItemGrants lists, vs the profile form.
    """
    alts: List[str] = []
    if ":" not in template_id:
        return alts
    kind, _, rest = template_id.partition(":")
    kind_lower = kind.lower()
    rest_lower = rest.lower()

    if kind_lower == "schematic":
        # MCP returns ingredient schematics under the Schematic: prefix
        # (e.g. `Schematic:ingredient_blastpowder`) but our data file
        # stores those under `Ingredient:`. Redirect.
        # (Ammo_* schematic items aren't extracted — fallback to heuristic.)
        if rest_lower.startswith("ingredient_"):
            alts.append(f"ingredient:{rest_lower}")

    if kind_lower == "defender":
        # `defender_pistol_r_ore_t04` -> `default__defender_pistol_c`
        # `defenderpistol_basic_r_ore_t04` -> same
        segments = rest_lower.split("_")
        if segments and segments[0] in ("did",):
            segments = segments[1:]
        # Collapse `defenderpistol` -> ["defender", "pistol"]
        if segments and segments[0].startswith("defender") and segments[0] != "defender":
            weapon_tail = segments[0][len("defender"):]
            segments = ["defender", weapon_tail] + segments[1:]
        # Strip `basic` / rarity / material / tier
        segments = [s for s in segments if s != "basic"]
        segments = _strip_rarity_material_tier(segments)
        if segments and segments[0] == "defender" and len(segments) >= 2:
            # "Defender:default__defender_<weapon>_c" (Blueprint CDO form)
            weapon = "_".join(segments[1:])
            alts.append(f"defender:default__defender_{weapon}_c")
    elif kind_lower == "hero":
        # Rare: modern heroes encode the specialty in extra _xyz segments.
        # Try stripping the trailing tier only — sometimes the same hero
        # at different tiers isn't in the lookup but the baseline T1 is.
        segments = rest_lower.split("_")
        if segments and segments[-1].startswith("t") and segments[-1][1:].isdigit():
            # Try T01 if a higher tier missed
            head = "_".join(segments[:-1])
            alts.append(f"hero:{head}_t01")
    elif kind_lower == "worker":
        # Try stripping a trailing material token we don't store for survivors
        segments = rest_lower.split("_")
        segments = [s for s in segments if s not in _MATERIAL_TOKENS]
        alts.append(f"worker:{'_'.join(segments)}")

    return alts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_template_name(template_id: str) -> Optional[Dict]:
    """Resolve a full Epic templateId to its real in-game display name.

    Returns a dict with {name, rarity, tier, cat, sub} or None if the
    templateId isn't in the lookup (caller should fall back to heuristic).

    Example:
        >>> resolve_template_name("Schematic:sid_assault_bone_vr_ore_t04")
        {'name': 'Primal Rifle', 'cat': 'Schematic', 'rar': 'Epic', 'tier': 4}
    """
    if not template_id:
        return None
    key = template_id.lower()
    entry = _lookup_singleton.get(key)
    if entry is not None:
        return entry
    for alt in _fallback_keys(template_id):
        entry = _lookup_singleton.get(alt)
        if entry is not None:
            return entry
    return None


def resolve_display_name(template_id: str) -> Optional[str]:
    """Shorthand returning just the name string, or None if unknown."""
    entry = resolve_template_name(template_id)
    if not entry:
        return None
    return entry.get("name") or None


def lookup_stats() -> Dict[str, object]:
    """Diagnostic — how many entries are loaded, where the file lives."""
    return _lookup_singleton.stats()


def reload_lookup() -> bool:
    """Force a reload from disk. Mostly for tests."""
    global _lookup_singleton
    _lookup_singleton = _Lookup()
    return _lookup_singleton.load()
