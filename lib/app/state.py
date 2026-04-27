"""Shared runtime state for action handlers (speaker, events, singletons)."""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from accessible_output2.outputs.auto import Auto  # noqa: F401
    from lib.managers.poi_data_manager import POIData  # noqa: F401


# Init-once globals — FA11y.py assigns these at startup.
speaker: "Optional[Auto]" = None
logger: logging.Logger = logging.getLogger("fa11y.app")
update_sound = None


# Thread-synchronization events — authoritative; FA11y aliases these.
shutdown_requested: threading.Event = threading.Event()
stop_key_listener: threading.Event = threading.Event()
auth_expired: threading.Event = threading.Event()

# Per-GUI "is open" flags so we don't open the same window twice.
config_gui_open: threading.Event = threading.Event()
social_gui_open: threading.Event = threading.Event()
discovery_gui_open: threading.Event = threading.Event()
locker_gui_open: threading.Event = threading.Event()
gamemode_gui_open: threading.Event = threading.Event()
visited_objects_gui_open: threading.Event = threading.Event()
custom_poi_gui_open: threading.Event = threading.Event()

# Wizard takes exclusive control — key listener short-circuits while set.
wizard_open: threading.Event = threading.Event()


# Lazy singletons — use getters; ``import`` would freeze the reference.
_poi_data_instance = None
_active_pinger = None
_social_manager = None
_discovery_api = None
_current_poi_category = "special"
_keybinds_enabled = True
_auth_expiration_announced = False


def get_poi_data():
    """Return the POIData singleton, creating it on first access."""
    global _poi_data_instance
    if _poi_data_instance is None:
        from lib.managers.poi_data_manager import POIData
        _poi_data_instance = POIData()
    return _poi_data_instance


def set_poi_data(value) -> None:
    global _poi_data_instance
    _poi_data_instance = value


def get_active_pinger():
    return _active_pinger


def set_active_pinger(value) -> None:
    global _active_pinger
    _active_pinger = value


def get_social_manager():
    return _social_manager


def set_social_manager(value) -> None:
    global _social_manager
    _social_manager = value


def get_discovery_api():
    return _discovery_api


def set_discovery_api(value) -> None:
    global _discovery_api
    _discovery_api = value


def get_current_poi_category() -> str:
    return _current_poi_category


def set_current_poi_category(value: str) -> None:
    global _current_poi_category
    _current_poi_category = value


def are_keybinds_enabled() -> bool:
    return _keybinds_enabled


def set_keybinds_enabled(value: bool) -> None:
    global _keybinds_enabled
    _keybinds_enabled = value


def is_auth_expiration_announced() -> bool:
    return _auth_expiration_announced


def set_auth_expiration_announced(value: bool) -> None:
    global _auth_expiration_announced
    _auth_expiration_announced = value
