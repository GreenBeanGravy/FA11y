"""Requests for the Discover page. List texts and messages come from lib.utilities.discovery_ops."""
from __future__ import annotations

from lib.hub import get_hub
from lib.shell.bridge import handler
from lib.utilities import discovery_ops


def _speak(message: str) -> None:
    hub = get_hub()
    if hub is not None:
        hub.services.speak(message)


@handler("discover.epic")
def epic(_params: dict) -> dict:
    return discovery_ops.load_epic(discovery_ops.get_api())


@handler("discover.browse")
def browse(_params: dict) -> dict:
    return discovery_ops.load_browse(discovery_ops.get_api())


@handler("discover.search")
def search(params: dict) -> dict:
    query = str(params.get("query", "")).strip()
    if not query:
        raise ValueError("Please enter a search term")
    return discovery_ops.load_search(discovery_ops.get_api(), query)


@handler("discover.creator")
def creator(params: dict) -> dict:
    name = str(params.get("name", "")).strip()
    if not name:
        raise ValueError("Please enter a creator name")
    return discovery_ops.load_creator(discovery_ops.get_api(), name)


@handler("discover.lookup")
def lookup(params: dict) -> dict:
    code = str(params.get("code", "")).strip()
    if not code:
        raise ValueError("Please enter an island code")
    island = discovery_ops.get_api().get_island_by_code(code)
    return {"text": discovery_ops.lookup_text(island, code), "announce": discovery_ops.lookup_speech(island)}


@handler("discover.copy")
def copy(params: dict) -> dict:
    return {"announce": discovery_ops.copy_text(str(params.get("code", "")), str(params.get("title", "")))}


@handler("discover.launch")
def launch(params: dict) -> dict:
    """Pick the gamemode in Fortnite, with the match options an Epic gamemode offers. The window
    leaves first."""
    code = str(params.get("code", ""))
    title = str(params.get("title", ""))
    if not code:
        return {"announce": "No code available", "launched": False}
    options = params.get("options") if isinstance(params.get("options"), dict) else None
    link, _name, note = discovery_ops.apply_options(code, title, options)
    if link is None:
        return {"announce": note, "launched": False}
    _speak(f"Launching {title}")
    hub = get_hub()
    if hub is not None:
        hub.leave_page()
    discovery_ops.launch_gamemode(code, title, _speak, options)
    return {"launched": True}
