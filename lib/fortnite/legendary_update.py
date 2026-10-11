"""Keep legendary.exe at the version FA11y is tested with.

The updater installs legendary.exe as a component of the install manifest,
which pins one release by URL and SHA-256. Updaters from before the
manifest could say "this exact file" only checked that legendary.exe
existed, so installs kept whatever copy they got first. This module checks
the copy FA11y has against the pin and, when it differs, downloads the
pinned release, verifies it and puts it in place. It runs in the background
once FA11y has started, so it works whichever updater a user has.

The pin is read from the manifest copy the updater saves next to FA11y.py
(``.fa11y-manifest.json``), or from ``installer/manifest.json`` in a checkout.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)

COMPONENT_ID = "legendary"
EXE_NAME = "legendary.exe"
MANIFEST_COPY = ".fa11y-manifest.json"
REPO_MANIFEST = os.path.join("installer", "manifest.json")
# Set-aside copies of a legendary.exe that was running when it was replaced.
MAX_ASIDE = 20

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_lock = threading.Lock()


@dataclass
class Pin:
    version: str
    url: str
    sha256: str


@dataclass
class Check:
    """The result of comparing legendary.exe with the pin."""

    state: str  # "current", "outdated", "missing" or "unknown" (no pin to compare with)
    path: str
    pinned: Optional[Pin] = None
    installed_version: str = ""


def _manifest_paths(root: str):
    return [os.path.join(root, MANIFEST_COPY), os.path.join(root, REPO_MANIFEST)]


def load_pin(root: str = _ROOT) -> Optional[Pin]:
    """The legendary release the install manifest pins, or None when there is no usable manifest."""
    for path in _manifest_paths(root):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        for component in data.get("components") or []:
            if not isinstance(component, dict) or component.get("id") != COMPONENT_ID:
                continue
            download = component.get("download") or {}
            url, sha = str(download.get("url") or ""), str(download.get("sha256") or "").lower()
            if url.startswith("https://") and len(sha) == 64:
                return Pin(version=str(component.get("version") or ""), url=url, sha256=sha)
    return None


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def installed_version(path: str) -> str:
    """'0.20.34' from ``legendary --version`` (``legendary version "0.20.34", codename ...``), or ""."""
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30,
                             stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return ""
    text = out.stdout or ""
    start = text.find('"')
    end = text.find('"', start + 1)
    return text[start + 1:end] if 0 <= start < end else ""


def check(root: str = _ROOT, ask_version: bool = False) -> Check:
    """Compare legendary.exe in root with the pin. ask_version also runs it for its version (slow)."""
    path = os.path.join(root, EXE_NAME)
    pin = load_pin(root)
    if not os.path.isfile(path):
        return Check("missing" if pin else "unknown", path, pin)
    version = installed_version(path) if ask_version else ""
    if pin is None:
        return Check("unknown", path, None, version)
    try:
        same = sha256_of(path) == pin.sha256
    except OSError:
        return Check("unknown", path, pin, version)
    return Check("current" if same else "outdated", path, pin, version)


def _aside_names(path: str):
    yield path + ".old"
    for n in range(1, MAX_ASIDE):
        yield f"{path}.{n}.old"


def cleanup(path: str) -> None:
    """Delete copies set aside by earlier replacements that nothing runs any more."""
    for name in _aside_names(path):
        try:
            os.remove(name)
        except FileNotFoundError:
            continue
        except OSError:
            continue  # still running; a later start removes it


def _replace(staged: str, target: str) -> None:
    """Move staged over target. A running legendary.exe can't be deleted but can be renamed, so set
    it aside first (under a free name, in case an earlier set-aside copy is still running too)."""
    try:
        os.replace(staged, target)
        return
    except OSError:
        pass
    for name in _aside_names(target):
        try:
            if os.path.exists(name):
                os.remove(name)
            os.rename(target, name)
            break
        except OSError:
            continue
    else:
        raise OSError(f"{EXE_NAME} is in use and could not be moved aside")
    os.replace(staged, target)


def download(pin: Pin, target: str, session=None) -> None:
    """Download the pinned release next to target, verify it, and put it in place."""
    staged = target + ".download"
    http = session or requests
    h = hashlib.sha256()
    try:
        with http.get(pin.url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with open(staged, "wb") as f:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    if chunk:
                        f.write(chunk)
                        h.update(chunk)
        if h.hexdigest() != pin.sha256:
            raise ValueError(f"the download of legendary {pin.version} didn't match its SHA-256")
        _replace(staged, target)
    finally:
        if os.path.exists(staged):
            try:
                os.remove(staged)
            except OSError:
                pass


def ensure_current(root: str = _ROOT, manager=None, session=None) -> Optional[str]:
    """Update legendary.exe in root to the pinned release when it differs. Returns a message when
    it was updated, None when nothing needed doing or it couldn't be done right now.

    manager (the FortniteManager) is used so this never runs during an install or update, and so
    none starts while the file is being replaced.
    """
    if not _lock.acquire(blocking=False):
        return None
    try:
        result = check(root)
        cleanup(result.path)
        if result.state not in ("outdated", "missing") or result.pinned is None:
            return None
        pin = result.pinned

        def run():
            download(pin, result.path, session)
            return pin

        if manager is not None:
            if manager.current_operation:
                logger.info("Not updating legendary during the %s operation", manager.current_operation)
                return None
            outcome = manager._exclusive("legendary update", lambda: _as_result(run))
            if not getattr(outcome, "ok", False):
                logger.warning("Updating legendary failed: %s", getattr(outcome, "message", outcome))
                return None
        else:
            run()
        logger.info("legendary.exe updated to %s", pin.version or pin.sha256[:12])
        return f"Updated Legendary to version {pin.version}." if pin.version else "Updated Legendary."
    except Exception:
        logger.exception("Updating legendary failed")
        return None
    finally:
        _lock.release()


def _as_result(run: Callable[[], Pin]):
    from lib.fortnite.legendary_manager import OperationResult
    try:
        run()
    except Exception as e:  # reported by ensure_current
        return OperationResult(False, str(e))
    return OperationResult(True, "legendary updated")


def ensure_current_in_background(manager=None, on_updated: Optional[Callable[[str], None]] = None) -> None:
    """ensure_current on a daemon thread; on_updated gets the message when legendary was updated."""
    def work():
        message = ensure_current(manager=manager)
        if message and on_updated is not None:
            try:
                on_updated(message)
            except Exception:
                logger.exception("Legendary update callback failed")
    threading.Thread(target=work, name="LegendaryUpdate", daemon=True).start()
