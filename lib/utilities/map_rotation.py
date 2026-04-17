"""
Fetch and parse Fortnite.gg's Reload map rotation.

The page at https://fortnite.gg/map-rotation embeds the rotation schedule in a
JavaScript global::

    MapRotation = {
        "maps": [
            {"name": "Venture",    "duration": 1200, ...},
            {"name": "Oasis",      "duration": 1200, ...},
            {"name": "Slurp Rush", "duration": 1200, ...}
        ],
        "cycle": 3600
    }

Each map holds for ``duration`` seconds, and the full cycle repeats every
``cycle`` seconds, anchored to UTC midnight. This module pulls that data
with a 10-minute on-disk cache and exposes:

    current_rotation()       -> list[RotationEntry]
    current_reload_map()     -> CurrentReloadMap
    fa11y_map_for_display(name) -> str or None   # "Oasis" -> "reload oasis"

FA11y uses this to:
    1. Know which map is live right now (before any match starts)
    2. Announce the rotation schedule via keybind
    3. Pre-sync POI.current_map when the user is about to load into Reload
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

FORTNITE_GG_URL = "https://fortnite.gg/map-rotation"

# Fortnite.gg 403s known bot UAs — use a real browser UA.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Cache rotation data for 10 minutes to avoid hammering fortnite.gg. The
# rotation schedule doesn't change mid-day; only on Epic patch deploys.
CACHE_TTL_SECONDS = 600

# Display name -> FA11y map_name. These match the files in the ``maps/``
# directory. Extend as new Reload arenas rotate in.
DISPLAY_TO_FA11Y_MAP = {
    "Venture":      "reload venture",
    "Oasis":        "reload oasis",
    "Slurp Rush":   "reload slurp rush",
    "Surf City":    "reload surfcity",
    "Squid Grounds": None,                # No FA11y file yet
    "PunchBerry":   "reload oasis",        # codename fallback
    "BlastBerry":   "reload venture",
    "DashBerry":    "reload slurp rush",
}


@dataclass
class RotationEntry:
    name: str
    duration_seconds: int
    start_unix: int        # When this window starts
    end_unix: int          # When it ends
    is_current: bool
    fa11y_map: Optional[str]

    @property
    def time_until_start_seconds(self) -> int:
        return max(0, self.start_unix - int(time.time()))

    @property
    def time_until_end_seconds(self) -> int:
        return max(0, self.end_unix - int(time.time()))


@dataclass
class CurrentReloadMap:
    current: RotationEntry
    next: RotationEntry
    all_rotation: List[RotationEntry]


# ---------------------------------------------------------------------------
# Fetch + parse
# ---------------------------------------------------------------------------


def _cache_path() -> Path:
    """Where we stash the fetched rotation payload on disk."""
    project_root = Path(__file__).resolve().parents[2]
    cache_dir = project_root / 'config'
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / 'map_rotation_cache.json'


def _fetch_rotation_html(timeout: float = 10.0) -> Optional[str]:
    """Fetch the fortnite.gg/map-rotation HTML with a real UA."""
    req = urllib.request.Request(
        FORTNITE_GG_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning("fortnite.gg/map-rotation fetch failed: %s", e)
        return None


_ROTATION_RE = re.compile(
    r"MapRotation\s*=\s*(\{.*?\})\s*[;<]",
    re.DOTALL,
)


def _extract_rotation_json(html: str) -> Optional[dict]:
    """Find the ``MapRotation = { ... }`` blob in the page source."""
    m = _ROTATION_RE.search(html)
    if not m:
        return None
    raw = m.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse MapRotation JSON: %s", e)
        return None


def _load_or_refresh_rotation() -> Optional[dict]:
    """Return cached rotation or refresh from fortnite.gg. Always best-effort."""
    cache = _cache_path()
    try:
        if cache.exists():
            mtime = cache.stat().st_mtime
            if (time.time() - mtime) < CACHE_TTL_SECONDS:
                with cache.open("r", encoding="utf-8") as f:
                    return json.load(f)
    except Exception as e:
        logger.warning("Cache read failed: %s", e)

    html = _fetch_rotation_html()
    if not html:
        # Fall back to stale cache if available
        try:
            if cache.exists():
                with cache.open("r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return None
    data = _extract_rotation_json(html)
    if not data:
        return None
    try:
        with cache.open("w", encoding="utf-8") as f:
            json.dump({**data, "_fetched_at": int(time.time())}, f)
    except Exception as e:
        logger.warning("Cache write failed: %s", e)
    return data


# ---------------------------------------------------------------------------
# Cycle math (mirrors the JS algorithm on fortnite.gg/map-rotation)
# ---------------------------------------------------------------------------


def _compute_rotation(now_unix: int, data: dict) -> Optional[CurrentReloadMap]:
    maps = data.get("maps") or []
    cycle = int(data.get("cycle") or 0)
    if not maps or cycle <= 0:
        return None

    # Anchor to UTC midnight — matches the fortnite.gg algorithm exactly.
    utc_midnight = (now_unix // 86400) * 86400
    elapsed_today = now_unix - utc_midnight
    cycle_start = utc_midnight + (elapsed_today // cycle) * cycle
    cycle_offset = now_unix - cycle_start

    # Walk through the maps' cumulative durations to find the current one.
    durations = [int(m.get("duration") or 0) for m in maps]
    cumulative = [0]
    for d in durations:
        cumulative.append(cumulative[-1] + d)
    # cumulative[i] = start offset of map[i] within the cycle
    # cumulative[-1] should == sum of all durations; remainder is idle if short

    current_idx = 0
    for i, (start, end) in enumerate(zip(cumulative, cumulative[1:])):
        if start <= cycle_offset < end:
            current_idx = i
            break
    else:
        # We landed in an "idle" gap after the last map — treat last as current
        current_idx = len(maps) - 1

    next_idx = (current_idx + 1) % len(maps)

    def _build_entry(idx: int, start_offset_in_cycle: int) -> RotationEntry:
        start = cycle_start + start_offset_in_cycle
        if start < now_unix and idx != current_idx:
            # Next instance is in the NEXT cycle
            start += cycle
        end = start + durations[idx]
        m = maps[idx]
        return RotationEntry(
            name=m.get("name", "?"),
            duration_seconds=durations[idx],
            start_unix=start,
            end_unix=end,
            is_current=(idx == current_idx),
            fa11y_map=DISPLAY_TO_FA11Y_MAP.get(m.get("name", ""), None),
        )

    entries: List[RotationEntry] = [
        _build_entry(i, cumulative[i]) for i in range(len(maps))
    ]
    return CurrentReloadMap(
        current=entries[current_idx],
        next=entries[next_idx],
        all_rotation=entries,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def current_reload_map() -> Optional[CurrentReloadMap]:
    """Return current + next Reload map with timing info, or None if fetch fails."""
    data = _load_or_refresh_rotation()
    if not data:
        return None
    return _compute_rotation(int(time.time()), data)


def fa11y_map_for_display(display_name: Optional[str]) -> Optional[str]:
    """Resolve a Reload map display name (e.g. ``'Oasis'``) to FA11y's map slug."""
    if not display_name:
        return None
    return DISPLAY_TO_FA11Y_MAP.get(display_name.strip())


def speech_announcement() -> str:
    """One-line TTS-friendly summary for an FA11y keybind."""
    state = current_reload_map()
    if state is None:
        return "Reload map rotation data unavailable."
    cur = state.current
    nxt = state.next
    cur_rem = cur.time_until_end_seconds
    cur_rem_min = cur_rem // 60
    cur_rem_sec = cur_rem % 60
    return (
        f"Current Reload map: {cur.name}. "
        f"{cur_rem_min} minutes {cur_rem_sec} seconds remaining. "
        f"Next: {nxt.name}."
    )
