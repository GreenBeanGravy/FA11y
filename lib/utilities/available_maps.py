"""
Downloadable list of currently-available maps.

The repo ships ``data/available_maps.txt`` — one FA11y map slug per line
(matching the ``data/maps/map_<slug>_pois.txt`` file names). Epic rotates
which Reload/Blitz arenas are playable far more often than FA11y itself
releases, and the auto-updater only syncs repo files on version bumps, so
this file gets its own lightweight update channel:

1. At startup FA11y calls :func:`sync_local_from_remote` to refresh the
   local copy straight from GitHub.
2. While FA11y runs, :func:`check_for_map_list_updates` (daemon thread)
   watches the remote copy exactly like the VERSION check does and
   announces once per change that a restart will pull the new list.
3. Map discovery calls :func:`read_local_available_maps` and hides any
   map whose slug is not in the list, even when its data files exist.

Missing or unreadable list -> fail open (no filtering, no announcements)
so offline use never loses maps.
"""
from __future__ import annotations

import logging
import os
import time
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/GreenBeanGravy/FA11y/main"
REMOTE_URL = f"{GITHUB_RAW_BASE}/data/available_maps.txt"
LOCAL_PATH = os.path.join("data", "available_maps.txt")

# The map selector always offers the main battle-royale map, list or no list.
ALWAYS_AVAILABLE = ("main",)

ANNOUNCEMENT = (
    "A new map list is available! Restart FA11y to pull an up-to-date "
    "list of currently available maps!"
)


def _parse_map_list(text: str) -> List[str]:
    """Parse list text into normalized slugs (comments/blanks dropped)."""
    slugs: List[str] = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        slug = line.lower().replace(" ", "_")
        if slug not in slugs:
            slugs.append(slug)
    return slugs


def read_local_available_maps() -> Optional[List[str]]:
    """Return the local list's slugs, or None when no usable list exists.

    None tells callers to fail open (offer every map found on disk).
    """
    try:
        if not os.path.exists(LOCAL_PATH):
            return None
        with open(LOCAL_PATH, "r", encoding="utf-8") as f:
            slugs = _parse_map_list(f.read())
        return slugs or None
    except Exception as e:
        logger.warning("Could not read %s: %s", LOCAL_PATH, e)
        return None


def is_map_available(slug: str) -> bool:
    """True when ``slug`` should be offered to the user."""
    if slug in ALWAYS_AVAILABLE:
        return True
    allowed = read_local_available_maps()
    if allowed is None:
        return True
    return slug in allowed


def fetch_remote_map_list(timeout: float = 10.0) -> Optional[str]:
    """Fetch the remote list text (cache-busting), or None on any failure."""
    try:
        response = requests.get(REMOTE_URL, timeout=timeout,
                                params={"t": int(time.time())})
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.debug("Available-maps fetch failed: %s", e)
        return None


def sync_local_from_remote(timeout: float = 10.0) -> bool:
    """Overwrite the local list with the remote one when they differ.

    Best-effort: returns True only when the local file was rewritten.
    Called once at startup so a restart is all it takes to pick up a new
    list, independent of FA11y version bumps.
    """
    remote_text = fetch_remote_map_list(timeout=timeout)
    if remote_text is None or not _parse_map_list(remote_text):
        return False

    local_text = None
    try:
        if os.path.exists(LOCAL_PATH):
            with open(LOCAL_PATH, "r", encoding="utf-8") as f:
                local_text = f.read()
    except Exception:
        pass

    if local_text is not None and _parse_map_list(local_text) == _parse_map_list(remote_text):
        return False

    try:
        os.makedirs(os.path.dirname(LOCAL_PATH), exist_ok=True)
        with open(LOCAL_PATH, "w", encoding="utf-8") as f:
            f.write(remote_text)
        logger.info("Available-maps list updated from GitHub.")
        return True
    except Exception as e:
        logger.warning("Could not write %s: %s", LOCAL_PATH, e)
        return False


def check_for_map_list_updates(speaker, shutdown_event, update_sound) -> None:
    """Daemon-thread loop: announce when the remote map list changes.

    Mirrors ``lib.app.updater_check.check_for_updates``: wakes every 15 s,
    compares the remote list against the local file, and announces each
    distinct remote list at most once. When local and remote match again
    (e.g. after a restart pulled the new list) the guard resets.
    """
    last_announced: Optional[tuple] = None

    while not shutdown_event.is_set():
        # 15 s sleep that wakes promptly on shutdown.
        for _ in range(150):
            if shutdown_event.is_set():
                return
            time.sleep(0.1)
        if shutdown_event.is_set():
            return

        remote_text = fetch_remote_map_list()
        if remote_text is None:
            continue
        remote_maps = _parse_map_list(remote_text)
        if not remote_maps:
            continue

        local_maps = read_local_available_maps()
        if local_maps is None:
            # No local list yet — adopt the remote one quietly instead of
            # nagging for a restart that wouldn't change anything visible.
            sync_local_from_remote()
            continue

        if remote_maps == local_maps:
            last_announced = None
            continue

        remote_key = tuple(remote_maps)
        if remote_key != last_announced and not shutdown_event.is_set():
            try:
                update_sound.play()
            except Exception:
                pass
            speaker.speak(ANNOUNCEMENT)
            print(ANNOUNCEMENT)
            last_announced = remote_key
