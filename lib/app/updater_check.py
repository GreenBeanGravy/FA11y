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
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Remote URLs — kept here so FA11y.py doesn't need to care.
GITHUB_REPO_URL = "https://raw.githubusercontent.com/GreenBeanGravy/FA11y/main"
VERSION_URL = f"{GITHUB_REPO_URL}/VERSION"
CHANGELOG_URL = f"{GITHUB_REPO_URL}/CHANGELOG.txt"


def get_version() -> Optional[str]:
    """Get version from GitHub repository with cache-busting."""
    try:
        response = requests.get(VERSION_URL, timeout=10,
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
        response = requests.get(CHANGELOG_URL, timeout=10)
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
    result = subprocess.run(
        [sys.executable, 'updater.py', '--run-by-fa11y'],
        capture_output=True, text=True,
    )
    update_performed = result.returncode == 1
    if update_performed:
        handle_update_with_changelog(speaker)
    return update_performed


def check_for_updates(speaker, shutdown_event, update_sound) -> None:
    """Periodically check for updates with shutdown awareness.

    Call as a daemon thread target: thread wakes every 15 s and compares
    local ``VERSION`` against the remote file. Each new remote version is
    announced at most once (``last_announced_remote_version`` guard).
    """
    last_announced_remote_version = None

    while not shutdown_event.is_set():
        # 15 s sleep that wakes promptly on shutdown.
        for _ in range(150):
            if shutdown_event.is_set():
                return
            time.sleep(0.1)
        if shutdown_event.is_set():
            return

        local_version = None
        if os.path.exists('VERSION'):
            with open('VERSION', 'r') as f:
                local_version = f.read().strip()

        remote_version = get_version()
        if not local_version or not remote_version:
            continue

        try:
            local_v = parse_version(local_version)
            remote_v = parse_version(remote_version)
        except ValueError:
            continue

        if local_v < remote_v:
            if (remote_version != last_announced_remote_version
                    and not shutdown_event.is_set()):
                try:
                    update_sound.play()
                except Exception:
                    pass
                speaker.speak(
                    "An update is available for FA11y! Restart FA11y to update!"
                )
                print(
                    "An update is available for FA11y! Restart FA11y to update!"
                )
                last_announced_remote_version = remote_version
        elif local_v >= remote_v:
            last_announced_remote_version = None
