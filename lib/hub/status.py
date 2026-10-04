"""Status lines shown on the Home page, and FA11y update state.

Each *_status() function returns a dict with value, detail and level
("ok", "warn", "error" or ""). They may block on disk or network, so call
them from a worker thread.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_update_lock = threading.Lock()
_available_update: Optional[str] = None
_last_install_info = None

REPO_URL = "https://github.com/GreenBeanGravy/FA11y"

KEY_NAMES = {
    "lalt": "Left Alt", "ralt": "Right Alt", "lctrl": "Left Control", "rctrl": "Right Control",
    "lshift": "Left Shift", "rshift": "Right Shift", "grave": "Grave", "equals": "Equals",
    "minus": "Minus", "semicolon": "Semicolon", "apostrophe": "Apostrophe", "period": "Period",
    "comma": "Comma", "bracketleft": "Left Bracket", "bracketright": "Right Bracket",
    "delete": "Delete", "backspace": "Backspace", "space": "Space", "tab": "Tab",
    "enter": "Enter", "escape": "Escape",
}


def key_display_name(combo: str) -> str:
    """'lalt+lshift+f' -> 'Left Alt + Left Shift + F'."""
    if not combo:
        return "no key"
    parts = []
    for part in combo.split("+"):
        part = part.strip().lower()
        if part in KEY_NAMES:
            parts.append(KEY_NAMES[part])
        elif part.startswith("num "):
            parts.append("Numpad " + part[4:].upper())
        else:
            parts.append(part.upper() if len(part) <= 3 else part.title())
    return " + ".join(parts)


def open_hub_keybind() -> str:
    from lib.utilities.utilities import get_config_value, read_config
    combo, _ = get_config_value(read_config(), "Open FA11y", "")
    return key_display_name(combo)


def latest_changelog_entry(path: str = "CHANGELOG.txt") -> str:
    """First block of CHANGELOG.txt (up to the first blank line)."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read().strip()
    except OSError:
        return ""
    return text.split("\n\n", 1)[0].strip()


def full_changelog(path: str = "CHANGELOG.txt") -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "No changelog found."


def open_folder(name: str) -> None:
    """Open one of FA11y's folders (logs, config) in Explorer."""
    path = os.path.abspath(name)
    os.makedirs(path, exist_ok=True)
    os.startfile(path)


# FA11y updates ------------------------------------------------------------

def set_available_update(version: Optional[str]) -> None:
    global _available_update
    with _update_lock:
        _available_update = version


def available_update() -> Optional[str]:
    with _update_lock:
        return _available_update


def local_version() -> str:
    try:
        with open("VERSION", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


LAUNCHER_EXE = "FA11y_Launcher.exe"


def launcher_path() -> str:
    """The launcher that started FA11y, or "" when FA11y wasn't started by one. An older launcher
    still running under its old name ("FA11y Launcher.exe") points at a file the updater has since
    renamed, so fall back to the current name next to it."""
    launcher = os.environ.get("FA11Y_LAUNCHER", "")
    if not launcher or os.path.exists(launcher):
        return launcher
    renamed = os.path.join(os.path.dirname(launcher), LAUNCHER_EXE)
    return renamed if os.path.exists(renamed) else ""


def can_restart_to_update() -> bool:
    """Only installs started by FA11y_Launcher.exe can update by restarting."""
    return bool(launcher_path())


def restart_to_update(hub) -> None:
    """Start the launcher again (it updates before starting FA11y), then quit."""
    launcher = launcher_path()
    if not launcher:
        return
    try:
        # --update makes the launcher update even when AutoUpdates is off.
        subprocess.Popen([launcher, "--update"], cwd=os.path.dirname(launcher),
                         creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True)
    except OSError as e:
        logger.error(f"Could not start the launcher: {e}")
        return
    hub.quit()


def switch_branch(hub, name: str) -> None:
    """Start the launcher on another branch (it updates first), then quit."""
    launcher = launcher_path()
    if not launcher:
        return
    try:
        subprocess.Popen([launcher, "--update", "--branch", name], cwd=os.path.dirname(launcher),
                         creationflags=subprocess.CREATE_NEW_CONSOLE, close_fds=True)
    except OSError as e:
        logger.error(f"Could not start the launcher: {e}")
        return
    hub.quit()


# Home page cards ----------------------------------------------------------

def fa11y_status() -> dict:
    version = local_version()
    update = available_update()
    if update:
        return {"value": version or "Unknown", "detail": f"Update available: {update}",
                "level": "warn", "update": update}
    return {"value": version or "Unknown", "detail": "Up to date", "level": "ok"}


def account_status() -> dict:
    try:
        from lib.utilities.epic_auth import get_epic_auth_instance
        auth = get_epic_auth_instance()
    except Exception:
        auth = None
    if auth is None or not auth.access_token:
        return {"value": "Signed out", "detail": "Sign in on the Epic account page", "level": "warn"}
    if not auth.is_valid:
        return {"value": "Session expired", "detail": "Sign in again on the Epic account page",
                "level": "error", "name": auth.display_name}
    return {"value": "Signed in", "detail": auth.display_name or "", "level": "ok",
            "name": auth.display_name}


def last_install_info():
    """The install status from the most recent Home page check, or None before one has run."""
    return _last_install_info


def fortnite_status() -> dict:
    global _last_install_info
    from lib.hub import game_watch
    if game_watch.is_fortnite_running():
        return {"value": "Running", "detail": "", "level": "ok"}
    try:
        from lib.fortnite import get_manager
        info = get_manager().status()
    except Exception as e:
        logger.debug(f"Fortnite status failed: {e}")
        return {"value": "Unknown", "detail": "Couldn't check the install", "level": ""}
    _last_install_info = info
    if not info.installed:
        if getattr(info, "egl_install_path", None):
            return {"value": "In Epic Games Launcher", "detail": "Set up on the Fortnite page",
                    "level": "warn"}
        return {"value": "Not installed", "detail": "Install on the Fortnite page", "level": "warn"}
    if info.update_available:
        return {"value": _short_version(info.version), "detail": "Update available", "level": "warn"}
    return {"value": _short_version(info.version), "detail": "Ready", "level": "ok"}


def _short_version(build: str) -> str:
    from lib.hub.fortnite_ops import short_version
    return short_version(build) or "Installed"
