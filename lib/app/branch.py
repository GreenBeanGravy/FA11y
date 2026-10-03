"""Which GitHub branch this FA11y follows, and the branches it can switch to.

wx-free. The updater records the branch in ``.fa11y-install.json`` next to
FA11y.py; installs from before branches existed have none and follow main.
The list of choices is ``installer/branches.json``, read from GitHub on the
installed branch (cached for the session) with the local copy as fallback.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_BRANCH = "main"
REPO = "GreenBeanGravy/FA11y"
STATE_FILE = ".fa11y-install.json"
BRANCHES_PATH = "installer/branches.json"

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_cache_lock = threading.Lock()
_cache: Optional[list] = None


def current_branch() -> str:
    """The branch the updater last installed, or main."""
    try:
        with open(os.path.join(_ROOT, STATE_FILE), encoding="utf-8") as f:
            name = json.load(f).get("branch")
    except (OSError, ValueError, AttributeError):
        return DEFAULT_BRANCH
    return name.strip() if isinstance(name, str) and name.strip() else DEFAULT_BRANCH


def raw_url(path: str, branch: Optional[str] = None) -> str:
    return f"https://raw.githubusercontent.com/{REPO}/{branch or current_branch()}/{path}"


def _clean(data) -> list:
    out = []
    if not isinstance(data, list):
        return out
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"]:
            out.append({"name": item["name"],
                        "label": str(item.get("label") or item["name"]),
                        "description": str(item.get("description") or "")})
    return out


def _local_branches() -> list:
    try:
        with open(os.path.join(_ROOT, *BRANCHES_PATH.split("/")), encoding="utf-8") as f:
            return _clean(json.load(f))
    except (OSError, ValueError):
        return []


def available_branches() -> list:
    """Branches the user can choose, as {name, label, description}."""
    global _cache
    with _cache_lock:
        if _cache is not None:
            return list(_cache)
    branches = []
    try:
        response = requests.get(raw_url(BRANCHES_PATH), timeout=5)
        response.raise_for_status()
        branches = _clean(response.json())
    except (requests.RequestException, ValueError) as e:
        logger.info("Could not read the branch list from GitHub: %s", e)
    if not branches:
        branches = _local_branches()
    if not branches:
        branches = [{"name": DEFAULT_BRANCH, "label": "Stable", "description": ""}]
    with _cache_lock:
        _cache = branches
    return list(branches)


def branch_info(name: Optional[str] = None) -> dict:
    """The list entry for name (default: the current branch), or a bare one."""
    name = name or current_branch()
    for b in available_branches():
        if b["name"] == name:
            return b
    return {"name": name, "label": name, "description": ""}
