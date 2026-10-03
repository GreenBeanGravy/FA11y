"""
Update-check loop + changelog-on-update handling.

Lifted out of ``FA11y.py`` to keep the main entry file focused on event
dispatch. Callers inject ``speaker``, ``shutdown_event``, and
``update_sound`` so this module has no implicit dependency on FA11y
globals.

Public API:

    check_for_updates(speaker, shutdown_event, update_sound)
        Long-running loop. Intended to be launched on a daemon thread.

    run_updater() -> bool
        One-shot call: shell out to ``updater.py`` and, if it applied an
        update, surface the changelog to the user.

    get_version() -> Optional[str]
        Fetch current released version from GitHub (cache-busting).

    parse_version(s) -> tuple
        ``"18.6.7" -> (18, 6, 7)`` for comparison.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from typing import Optional

import requests

from lib.app import branch

logger = logging.getLogger(__name__)

# Remote URLs - kept here so FA11y.py doesn't need to care.
def version_url() -> str:
    """VERSION on the branch this install follows."""
    return branch.raw_url("VERSION")


def changelog_url() -> str:
    return branch.raw_url("CHANGELOG.txt")


def get_version() -> Optional[str]:
    """Get version from GitHub repository with cache-busting."""
    try:
        response = requests.get(version_url(), timeout=10,
                                params={"t": int(time.time())})
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException as e:
        print(f"Failed to fetch version from GitHub: {e}")
        return None


def parse_version(version: str) -> tuple:
    """Parse version string into tuple."""
    return tuple(map(int, version.split('.')))


def handle_update_with_changelog(speaker) -> None:
    """Notify the user of an update; optionally open the changelog file."""
    local_changelog_path = 'CHANGELOG.txt'
    local_changelog_exists = os.path.exists(local_changelog_path)

    remote_changelog = None
    try:
        response = requests.get(changelog_url(), timeout=10)
        response.raise_for_status()
        remote_changelog = response.text
    except requests.RequestException as e:
        print(f"Failed to fetch remote changelog: {e}")
        speaker.speak("FA11y has been updated! Closing in 5 seconds...")
        print("FA11y has been updated! Closing in 5 seconds...")
        time.sleep(5)
        return

    changelog_updated = True
    if local_changelog_exists:
        try:
            with open(local_changelog_path, 'r', encoding='utf-8') as f:
                local_changelog = f.read()
            changelog_updated = remote_changelog != local_changelog
        except Exception as e:
            print(f"Error reading local changelog: {e}")

    try:
        with open(local_changelog_path, 'w', encoding='utf-8') as f:
            f.write(remote_changelog)
    except Exception as e:
        print(f"Error saving changelog: {e}")

    if changelog_updated:
        speaker.speak(
            "FA11y has been updated! Open changelog? "
            "Press Y for yes, or any other key for no."
        )
        print("FA11y has been updated! Open changelog? (Y/N)")

        try:
            import msvcrt
            key = msvcrt.getch().decode('utf-8', errors='ignore').lower()
            if key == 'y':
                _open_path(local_changelog_path, speaker)
            else:
                speaker.speak("Closing in 5 seconds...")
                print("Closing in 5 seconds...")
        except Exception:
            print("Press Y and Enter to open changelog, or just Enter to close")
            response = input().strip().lower()
            if response == 'y':
                _open_path(local_changelog_path, speaker)

        time.sleep(5)
    else:
        speaker.speak("FA11y has been updated! Closing in 5 seconds...")
        print("FA11y has been updated! Closing in 5 seconds...")
        time.sleep(5)


def _open_path(path: str, speaker) -> None:
    try:
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.call(['open', path])
        else:
            subprocess.call(['xdg-open', path])
    except Exception as e:
        print(f"Failed to open {path}: {e}")
        speaker.speak("Failed to open changelog. Closing in 5 seconds...")
        print("Failed to open changelog. Closing in 5 seconds...")
        time.sleep(5)


def run_updater(speaker) -> bool:
    """Run the updater script and surface the changelog on a real update."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)
    )))
    updater_path = os.path.join(project_root, 'updater.py')
    result = subprocess.run(
        [sys.executable, updater_path],
        cwd=project_root,
        capture_output=True, text=True,
    )
    update_performed = result.returncode == 1
    if update_performed:
        handle_update_with_changelog(speaker)
    elif result.returncode != 0:
        details = (result.stderr or result.stdout or "unknown updater error").strip()
        logger.error("FA11y updater failed with code %s: %s",
                     result.returncode, details)
        print(f"FA11y updater failed: {details}")
    return update_performed


def check_once() -> Optional[bool]:
    """Compare local VERSION with GitHub's.

    Returns True if a newer version exists (and records it for the hub),
    False if up to date, None if the check couldn't run.
    """
    local_version = None
    if os.path.exists('VERSION'):
        with open('VERSION', 'r') as f:
            local_version = f.read().strip()
    remote_version = get_version()
    if not local_version or not remote_version:
        return None
    try:
        newer = parse_version(local_version) < parse_version(remote_version)
    except ValueError:
        return None
    from lib.hub import status
    status.set_available_update(remote_version if newer else None)
    return newer


_startup_lock = threading.Lock()
_startup_done = False
_startup_pending: Optional[str] = None


def announce_update(speaker, version: str, at_startup: bool = False) -> None:
    """Tell the user about a new version.

    At startup it's one more spoken line after "FA11y is ready". Versions
    released while FA11y runs also get a quiet sound and a Windows
    notification.
    """
    from lib.hub import get_hub, sounds
    message = f"FA11y {version} is available. Run the updater to update or update through the app."
    if not at_startup:
        sounds.update_available()
    speaker.speak(message)
    print(message)
    hub = get_hub()
    if hub is not None:
        if not at_startup:
            hub.notify("FA11y update available", message)
        hub.update_available_changed()


def startup_finished(speaker) -> None:
    """FA11y has said it's ready: now announce an update found at startup, if any."""
    global _startup_done, _startup_pending
    with _startup_lock:
        _startup_done = True
        version, _startup_pending = _startup_pending, None
    if version:
        announce_update(speaker, version, at_startup=True)


def _announce_startup_update(speaker, version: str) -> None:
    global _startup_pending
    with _startup_lock:
        if not _startup_done:
            _startup_pending = version  # spoken by startup_finished()
            return
    announce_update(speaker, version, at_startup=True)


def check_for_updates(speaker, shutdown_event, update_sound=None) -> None:
    """Check for updates now, then every 15 s, with shutdown awareness.

    Call as a daemon thread target. An update that's already out when
    FA11y starts is spoken once, after FA11y's ready message. Versions
    released while FA11y runs are announced once each.
    """
    last_announced_remote_version = None
    first = True

    while not shutdown_event.is_set():
        if not first:
            # 15 s sleep that wakes promptly on shutdown.
            if shutdown_event.wait(15):
                return
        startup_check = first
        first = False

        newer = check_once()
        if newer is False:
            last_announced_remote_version = None
        if not newer:
            continue

        from lib.hub import status
        remote_version = status.available_update()
        if not remote_version or remote_version == last_announced_remote_version or shutdown_event.is_set():
            continue
        last_announced_remote_version = remote_version
        if startup_check:
            _announce_startup_update(speaker, remote_version)
        else:
            announce_update(speaker, remote_version)
