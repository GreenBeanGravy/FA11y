"""Speak FA11y-OW SSE events: teammate-feed mentions, item equips, item
pickups.

This is a thin consumer of ``lib.utilities.fa11y_ow_client``. It only does
work when both the FA11y-OW helper is up *and* the user has the relevant
toggle enabled in config — otherwise the listeners are no-ops.

Each toggle is independent so users can opt into just the parts they want:

    [Toggles]
    AnnounceTeammateEvents      = true   "Announce when teammates appear in
                                          the kill / message feed."
    AnnounceItemEquip           = true   "Announce the name of the weapon or
                                          item you equip when switching slots."
    AnnounceItemPickup          = true   "Announce items as you pick them up."
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from accessible_output2.outputs.auto import Auto

from lib.utilities.fa11y_ow_client import client as ow_client
from lib.utilities.utilities import get_config_boolean, on_config_change, read_config

logger = logging.getLogger(__name__)


# Items the game auto-issues at match start that aren't real "pickups" or
# user-facing equips: the pickaxe, the build edit tool, the creative phone,
# and the four wall/floor/stair/roof structural pieces. Filtering them
# silences the noise the user hits on every match.
_STRUCTURAL_PREFIXES = ("BuildingItemData_", "WID_Harvest_")
_STRUCTURAL_EXACT = frozenset({
    "EditTool",
    "WID_LiveEditTool",
    "WID_CreativeTool",
})


def _is_structural(name: str) -> bool:
    if not name or not name.strip():
        return True
    name = name.strip()
    if name in _STRUCTURAL_EXACT:
        return True
    return any(name.startswith(p) for p in _STRUCTURAL_PREFIXES)


def _toggles() -> Dict[str, bool]:
    cfg = read_config()
    return {
        "teammate": get_config_boolean(cfg, "AnnounceTeammateEvents", True),
        "equip": get_config_boolean(cfg, "AnnounceItemEquip", True),
        "pickup": get_config_boolean(cfg, "AnnounceItemPickup", True),
    }


class Fa11yOwAnnouncer:
    """Subscribes to the FA11y-OW SSE client and speaks selected events.

    Owns no thread of its own — the SSE thread inside ``ow_client`` calls our
    listeners directly. We keep the speaker call out of the stream parsing
    code path by re-using the existing accessible-output speaker which is
    safe to call from worker threads.
    """

    def __init__(self) -> None:
        self.speaker = Auto()
        self._toggles = _toggles()
        self._last_equipped_id: Optional[str] = None
        self._registered = False

    # -- public lifecycle ------------------------------------------------

    def start(self) -> None:
        if self._registered:
            return
        ow_client.add_listener("teammateEvent", self._on_teammate_event)
        ow_client.add_listener("itemEquipped", self._on_item_equipped)
        ow_client.add_listener("itemPickup", self._on_item_pickup)
        on_config_change(self._on_config_change)
        self._registered = True

    def stop(self) -> None:
        if not self._registered:
            return
        ow_client.remove_listener("teammateEvent", self._on_teammate_event)
        ow_client.remove_listener("itemEquipped", self._on_item_equipped)
        ow_client.remove_listener("itemPickup", self._on_item_pickup)
        self._registered = False

    # -- listeners -------------------------------------------------------

    def _on_teammate_event(self, ev: Optional[Dict[str, Any]]) -> None:
        if not ev or not self._toggles.get("teammate"):
            return
        player = str(ev.get("player") or "").strip()
        ev_type = str(ev.get("type") or "")
        message = str(ev.get("message") or "").strip()
        if not player:
            return

        if ev_type == "kill":
            phrase = f"{player} got an elimination."
        elif ev_type == "death":
            phrase = f"{player} was eliminated."
        else:
            # Generic feed mention — voice the underlying message verbatim
            # since it carries useful detail (revives, thanks, item finds,
            # etc.) and the player name is already inside it.
            phrase = message or f"{player} appeared in the feed."
        self._speak(phrase)

    def _on_item_equipped(self, item: Optional[Dict[str, Any]]) -> None:
        if not self._toggles.get("equip"):
            return
        if not item:
            # Slot transitioned to empty (or to secondary quickbar). Reset
            # the dedupe so re-equipping the prior weapon announces again.
            self._last_equipped_id = None
            return
        raw_id = str(item.get("rawId") or "")
        if _is_structural(raw_id):
            self._last_equipped_id = None
            return
        # Suppress repeats when the same item gets re-emitted (e.g. ammo
        # ticks down on the equipped weapon) — only re-announce on rawId
        # change. Pickup events still fire on transitions empty -> populated.
        if raw_id and raw_id == self._last_equipped_id:
            return
        self._last_equipped_id = raw_id

        name = str(item.get("displayName") or item.get("rawId") or "").strip()
        if not name:
            return
        rarity = str(item.get("rarity") or "").strip()
        ammo = item.get("ammoCurrent")
        parts = [name]
        if rarity and rarity != "-":
            parts.insert(0, rarity)
        speech = " ".join(parts)
        if isinstance(ammo, (int, float)) and ammo > 0:
            speech = f"{speech}, {int(ammo)} rounds"
        self._speak(speech)

    def _on_item_pickup(self, item: Optional[Dict[str, Any]]) -> None:
        if not item or not self._toggles.get("pickup"):
            return
        raw_id = str(item.get("rawId") or "")
        if _is_structural(raw_id):
            return
        name = str(item.get("displayName") or item.get("rawId") or "").strip()
        if not name:
            return
        count = item.get("count")
        if isinstance(count, (int, float)) and count > 1:
            self._speak(f"Picked up {int(count)} {name}")
        else:
            self._speak(f"Picked up {name}")

    # -- helpers ---------------------------------------------------------

    def _speak(self, text: str) -> None:
        try:
            self.speaker.speak(text)
        except Exception:
            logger.exception("Fa11yOwAnnouncer speak failed")

    def _on_config_change(self, _config: Any) -> None:
        # Pick up toggle changes without restarting the listener.
        try:
            self._toggles = _toggles()
        except Exception:
            logger.debug("FA11y-OW announcer: failed to refresh toggles")


announcer = Fa11yOwAnnouncer()
