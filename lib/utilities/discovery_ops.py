"""Discover logic without any window code: list texts, copying and launching.

The Discover handlers call these.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Callable, Iterable, Optional

logger = logging.getLogger(__name__)

EPIC_LOADING = "Loading Epic Games gamemodes..."
BROWSE_LOADING = "Loading islands from fortnite.gg..."


def is_standard_code_format(code: str) -> bool:
    """True for ####-####-#### and ############ island codes."""
    if not code:
        return False
    return bool(re.match(r'^\d{4}-\d{4}-\d{4}$', code) or re.match(r'^\d{12}$', code))


def get_api():
    """The shared Discover API, created on first use (it works signed out)."""
    from lib.app import state
    api = state.get_discovery_api()
    if api is None:
        from lib.utilities.epic_auth import get_epic_auth_instance
        from lib.utilities.epic_discovery import EpicDiscovery
        auth = get_epic_auth_instance()
        signed_in = bool(auth and auth.access_token and auth.is_valid)
        api = EpicDiscovery(auth if signed_in else None)
        state.set_discovery_api(api)
    return api


# List texts ---------------------------------------------------------------------

def epic_label(island) -> str:
    if island.global_ccu >= 0:
        return f"{island.title} ({island.global_ccu} playing)"
    return island.title


def browse_label(island) -> str:
    if island.global_ccu >= 0:
        return f"{island.title} ({island.global_ccu} playing) - {island.link_code}"
    creator = island.creator_name if island.creator_name else "Unknown"
    return f"{island.title} by {creator} - {island.link_code}"


def search_label(island) -> str:
    creator = island.creator_name if island.creator_name else "Unknown"
    return f"{island.title} by {creator} - {island.link_code}"


def creator_label(island) -> str:
    if island.global_ccu >= 0:
        return f"{island.title} ({island.global_ccu} playing) - {island.link_code}"
    return f"{island.title} - {island.link_code}"


LABELS = {"epic": epic_label, "browse": browse_label, "search": search_label, "creator": creator_label}


def island_row(island, kind: str) -> dict:
    return {"label": LABELS[kind](island), "code": island.link_code, "title": island.title}


def message_row(text: str) -> dict:
    """A list line that isn't an island (No islands found, an error)."""
    return {"label": text, "code": "", "title": ""}


def list_result(islands: Optional[Iterable], kind: str, *, empty: str, found: str,
                only_if_focused: bool = False, spoken_empty: Optional[str] = None) -> dict:
    """What a list request answers: the rows to show and what to say.

    found is the spoken text when there are islands ("{n}" becomes the count),
    empty is the list line (and the speech) when there are none. With
    only_if_focused the count is only spoken to someone waiting on the list.
    """
    islands = list(islands or [])
    if not islands:
        return {"rows": [message_row(empty)], "announce": spoken_empty or empty, "only_if_focused": False}
    return {"rows": [island_row(i, kind) for i in islands],
            "announce": found.replace("{n}", str(len(islands))), "only_if_focused": only_if_focused}


def load_epic(api) -> dict:
    islands = api.scrape_creator_maps("epic", limit=50)
    if not islands:
        return list_result(None, "epic", empty="Couldn't load Epic gamemodes. Try refreshing.",
                           found="", spoken_empty="Couldn't load Epic gamemodes")
    return list_result(islands, "epic", empty="No gamemodes found",
                       found="{n} Epic gamemodes loaded", only_if_focused=True)


def load_browse(api) -> dict:
    islands = api.scrape_fortnite_gg(search_query="", limit=50)
    if not islands:
        return list_result(None, "browse", empty="Couldn't load islands. Try refreshing.",
                           found="", spoken_empty="Couldn't load islands")
    return list_result(islands, "browse", empty="No islands found", found="{n} islands loaded",
                       only_if_focused=True)


def load_search(api, query: str) -> dict:
    islands = api.scrape_fortnite_gg(search_query=query, limit=50)
    return list_result(islands, "search", empty=f"No islands found matching '{query}'",
                       found="{n} islands found", spoken_empty=f"No results for {query}")


def load_creator(api, name: str) -> dict:
    islands = api.scrape_creator_maps(name, limit=50)
    return list_result(islands, "creator", empty=f"No islands found for '{name}'",
                       found="{n} maps loaded for " + name, spoken_empty=f"No islands found for {name}")


def lookup_text(island, code: str) -> str:
    """The text of the By code tab for an island, or a not found line."""
    if not island:
        return f"Island not found for code: {code}"
    lines = [f"Title: {island.title}", f"Code: {island.link_code}"]
    if island.creator_name:
        lines.append(f"Creator: {island.creator_name}")
    if island.description:
        lines.append(f"\nDescription: {island.description}")
    if island.global_ccu >= 0:
        lines.append(f"\nPlayers: {island.global_ccu}")
    return "\n".join(lines)


def lookup_speech(island) -> str:
    return f"Found: {island.title}" if island else "Island not found"


# Actions ------------------------------------------------------------------------

def copy_text(code: str, title: str) -> str:
    """Copy an island's code (or its title when the code isn't a standard one). Returns what to say."""
    if not code:
        return "No code available"
    import pyperclip
    pyperclip.copy(code)
    if is_standard_code_format(code):
        return f"Copied code: {code}"
    return f"Copied code: {title}"


def launch_gamemode(code: str, title: str, speak: Callable[[str], None]) -> None:
    """Pick the gamemode in Fortnite's menu, in the background, speaking the result."""
    def work():
        try:
            from lib.utilities.gamemode_selection import select_gamemode
            search_text = code if is_standard_code_format(code) else title
            success, error = select_gamemode(search_text, expected_title=title)
            speak(f"{title} selected!" if success else f"Failed to select gamemode: {error}")
        except Exception as e:
            logger.error(f"Error launching gamemode: {e}")
            speak(f"Failed to select gamemode: {e}")

    threading.Thread(target=work, daemon=True).start()
