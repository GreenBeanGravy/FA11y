"""Choose the lobby's island in a running Fortnite without touching the screen.

Fortnite started with -named_pipe=<name> listens on \\\\.\\pipe\\<name> for command-line text,
the way the Epic Games Launcher hands it island links from fortnite.com. Sending
"-IslandOverride=<island code or playlist>" makes the lobby select that island, the same as
picking it in Discover.

The message is UTF-16 text ending in a null. The game skips the first four characters, so four
spaces go first. The game logs what it got under LogExternalApplicationCommand and
LogFortDeepLinks in FortniteGame.log, which is how the result is checked.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

PIPE_ARG = "-named_pipe="
PIPE_SUFFIX = "Fortnite"
_PREFIX = "    "  # skipped by the game
LOG = os.path.join(os.environ.get("LOCALAPPDATA", ""), "FortniteGame", "Saved", "Logs", "FortniteGame.log")


def launch_arg(account_id: Optional[str]) -> str:
    """The argument that makes Fortnite open the pipe. The Epic Games Launcher names it
    <accountId>\\Fortnite, so with the same name its island links keep working too."""
    return f"{PIPE_ARG}{account_id or 'FA11y'}\\{PIPE_SUFFIX}"


def pipe_path() -> Optional[str]:
    """The running game's pipe, from its command line, or None."""
    import psutil
    for proc in psutil.process_iter(["name", "cmdline"]):
        name = (proc.info.get("name") or "").lower()
        if not name.startswith("fortniteclient-win64-shipping"):
            continue
        try:
            for arg in proc.info.get("cmdline") or []:
                if arg.lower().startswith(PIPE_ARG):
                    return "\\\\.\\pipe\\" + arg[len(PIPE_ARG):].strip('"')
        except (psutil.Error, TypeError):
            continue
    return None


def normalize_link(link: str) -> str:
    """'123456789012' -> '1234-5678-9012'; playlists and dashed codes are kept as they are."""
    link = link.strip()
    if re.fullmatch(r"\d{12}", link):
        return f"{link[:4]}-{link[4:8]}-{link[8:]}"
    return link


def _log_size() -> int:
    try:
        return os.path.getsize(LOG)
    except OSError:
        return -1


def judge(text: str, link: str, expected_island=None, expected_settings=None) -> Optional[bool]:
    """Read the game's log lines since the message. True when the island stuck, False when the game
    rejected it or switched away again (an unknown code is selected, then dropped within a second),
    None while it's still undecided."""
    wanted = f"mnemonic=[{(expected_island or link).lower()}]"
    changed = False
    for line in text.lower().splitlines():
        if "did not parse into valid command" in line:
            return False
        # An old playlist name becomes an island plus settings: playlist_nobuildbr_duo is
        # experience_br with TeamSize Duo and BuildMode Zero.
        converted = re.search(r"converting \[([^\]]*)\] to corresponding \w+ tile \[([^\]]+)\]", line)
        if converted and converted.group(1) == link.lower():
            wanted = f"mnemonic=[{converted.group(2)}]"
        if "link id changing" in line:
            before, _, after = line.partition(" to ")
            if wanted in after:
                changed = True
            elif changed and wanted in before:
                return False  # dropped again
        if not expected_settings and changed and "found playable island" in line and wanted in line:
            return True
    if expected_settings:
        # A settings-only change stays on the same consolidated island. Require
        # the actual selected settings, not merely successful link resolution.
        selected = []
        for block in re.split(r"(?im)^\s*Selected Island:\s*\r?\n", text)[1:]:
            block = re.split(r"\r?\n(?:to:|from:|\[|\s*Current Island:)", block, maxsplit=1)[0]
            fields = dict(re.findall(r"/[^\s\[]+:(TeamSize|BuildMode|Ranked)\s+\[([^\]]+)\]", block))
            if "linkid" in block.lower() and fields:
                selected.append((block.lower(), fields))
            elif fields and selected:
                # Fortnite also logs incremental `to: Selected Island` updates.
                # A later changed field must override an earlier full snapshot.
                old_block, old_fields = selected[-1]
                selected.append((old_block, {**old_fields, **fields}))
        if selected:
            block, fields = selected[-1]
            if wanted in block and all(fields.get(k, '').casefold() == v.casefold()
                                      for k,v in expected_settings.items()):
                return True
    return None  # parsed with no change yet: the change may still be on its way


def _wait_for_result(start: int, link: str, timeout: float, expected_island=None, expected_settings=None) -> Optional[bool]:
    """Require observed selection/settings confirmation; a parsed command alone is insufficient."""
    if start < 0:
        return None
    text = ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.15)
        try:
            with open(LOG, "r", encoding="utf-8", errors="replace") as f:
                f.seek(start)
                text = f.read()
        except OSError:
            return None
        result = judge(text, link, expected_island, expected_settings)
        if result is not None:
            return result
    return None


def select_island(link: str, timeout: float = 3.0, *, expected_island=None, expected_settings=None) -> Tuple[bool, Optional[str]]:
    """Select an island or playlist in the running Fortnite. Returns (ok, error)."""
    link = normalize_link(link)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", link):
        return False, "That isn't an island code or playlist"
    path = pipe_path()
    if path is None:
        return False, "no pipe"
    start = _log_size()
    message = f"{_PREFIX}-IslandOverride={link}\0".encode("utf-16-le")
    try:
        with open(path, "wb", buffering=0) as pipe:
            pipe.write(message)
    except OSError as e:
        logger.warning(f"Could not write to Fortnite's pipe {path}: {e}")
        return False, "Fortnite didn't answer"
    result = _wait_for_result(start, link, timeout, expected_island, expected_settings)
    logger.info(f"[gamemode] pipe select {link!r}: {result}")
    if result is False:
        return False, "Fortnite didn't accept that island"
    if result is None:
        return False, "Selection was sent, but Fortnite has not confirmed it. Close open screens and check the lobby before retrying."
    return True, None
