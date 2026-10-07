"""Discover logic without any window code: list texts, copying and launching.

The Discover handlers call these.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Callable, Iterable, Optional, Tuple

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


# Match options --------------------------------------------------------------------

TEAM_SIZES = ("solo", "duo", "trio", "squad")
TEAM_NAMES = {"solo": "Solo", "duo": "Duos", "trio": "Trios", "squad": "Squads"}

# Old playlist names the game turns into an Epic gamemode with these settings (checked against
# Fortnite's log). Ranked Zero Build has no trios.
_BR_PLAYLISTS = {
    (False, False): {"solo": "playlist_defaultsolo", "duo": "playlist_defaultduo",
                     "trio": "playlist_trios", "squad": "playlist_defaultsquad"},
    (True, False): {size: f"playlist_nobuildbr_{size}" for size in TEAM_SIZES},
    (False, True): {size: f"playlist_habanero{size}" for size in TEAM_SIZES},
    (True, True): {size: f"playlist_nobuildbr_habanero_{size}" for size in ("solo", "duo", "squad")},
}
_BLITZ_PLAYLISTS = {size: f"playlist_forbiddenfruitnobuildbr{size}" for size in ("solo", "duo", "squad")}

BATTLE_ROYALE = "experience_br"
BLITZ = "experience_blitz"
# Modes with match options in Fortnite that FA11y can't set yet.
_OPTIONS_IN_GAME = {"experience_reload", "experience_og"}


def br_playlist(team: str, zero_build: bool, ranked: bool) -> Optional[str]:
    """The playlist for a Battle Royale choice, or None when Epic doesn't offer it."""
    return _BR_PLAYLISTS[(bool(zero_build), bool(ranked))].get(team)


def br_title(team: str, zero_build: bool, ranked: bool) -> str:
    """'Ranked Zero Build Duos'."""
    parts = (["Ranked"] if ranked else []) + (["Zero Build"] if zero_build else ["Build"]) + [TEAM_NAMES.get(team, team)]
    return " ".join(parts)


def apply_options(code: str, title: str, options: Optional[dict]) -> Tuple[Optional[str], str, str]:
    """What to send for an Epic gamemode with the chosen match options.

    Returns (link, title to speak, note). link is None when the mode doesn't offer that
    combination; note then says why. Otherwise note is anything else worth saying (a
    choice the mode ignores), or empty.
    """
    if not options:
        return code, title, ""
    team = str(options.get("team", "duo"))
    zero_build = bool(options.get("zero_build"))
    ranked = bool(options.get("ranked"))
    key = code.lower()
    if key == BATTLE_ROYALE:
        playlist = br_playlist(team, zero_build, ranked)
        name = br_title(team, zero_build, ranked)
        if playlist is None:
            return None, name, f"{name} isn't available. Ranked Zero Build has Solo, Duos and Squads."
        label = f"Battle Royale {'Zero Build' if zero_build else 'Build'} {TEAM_NAMES.get(team, team)} {'Ranked' if ranked else 'Unranked'}"
        return playlist, label, "Set other match options such as team fill in Fortnite."
    if key == BLITZ:
        playlist = _BLITZ_PLAYLISTS.get(team)
        if playlist is None:
            return None, title, f"{title} has Solo, Duos and Squads, not {TEAM_NAMES.get(team, team)}."
        # Blitz is always Zero Build, so only a ranked choice is worth mentioning.
        note = f"{title} has no ranked." if ranked else ""
        note = " ".join(filter(None, [note, "Set other match options such as team fill in Fortnite."]))
        return playlist, f"{title} {TEAM_NAMES.get(team, team)} Unranked", note
    if key in _OPTIONS_IN_GAME:
        name = f"{title} {TEAM_NAMES.get(team, team)} {'Ranked' if ranked else 'Unranked'}"
        return code, name, "Set its team size and ranked choice, and other match options such as team fill, in Fortnite."
    return code, title, ""


def launch_gamemode(code: str, title: str, speak: Callable[[str], None],
                    options: Optional[dict] = None) -> None:
    """Pick the gamemode in Fortnite's menu, in the background, speaking the result. Epic
    gamemodes take the match options they offer (team size, building, ranked)."""
    link, name, note = apply_options(code, title, options)
    if link is None:
        speak(note)
        return

    def work():
        try:
            # A game started with -named_pipe (by FA11y or the Epic Games Launcher) takes the island
            # straight from its link code, like fortnite.com's island links. No screen reading.
            from lib.utilities import fortnite_pipe
            success, error = fortnite_pipe.select_island(link)
            if success or error != "no pipe":
                speak(" ".join(filter(None, [f"{name} selected!", note, 'Press "P" to ready up!'])) if success
                      else f"Failed to select gamemode: {error}")
                return
            # Otherwise pick it in Fortnite's menus by reading the screen. Match options need the pipe.
            from lib.utilities.gamemode_selection import select_gamemode
            search_text = code if is_standard_code_format(code) else title
            success, error = select_gamemode(search_text, expected_title=title)
            unset = "" if link == code else (" Its match options weren't changed. Start Fortnite from FA11y's "
                                             "Play button to set them.")
            speak(f'{title} selected!{unset} Press "P" to ready up!' if success else f"Failed to select gamemode: {error}")
        except Exception as e:
            logger.error(f"Error launching gamemode: {e}")
            speak(f"Failed to select gamemode: {e}")

    threading.Thread(target=work, daemon=True).start()
