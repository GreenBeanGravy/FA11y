"""
Shared mutable state for FA11y's action handlers.

Before the split, all runtime state lived as module-level globals in
``FA11y.py``. Extracting action handlers into ``lib/app/*`` modules broke
their access to that state, because Python's ``global`` keyword only
rebinds names within the *same module*.

This module is the new single source of truth. It owns:

* The shared ``speaker`` (Auto() wrapper)
* The shared ``update_sound`` (pygame Sound) / ``logger``
* Every ``threading.Event`` used as a GUI-open flag or a lifecycle gate
* Lazy singleton getters for objects that can legitimately be ``None``
  before their owning feature is first used (POI data, social manager,
  discovery API, active POI pinger)

Extracted modules access state through ``from lib.app import state`` and
then ``state.speaker``, ``state.get_poi_data()``, etc. Assignments to
module-level attributes of this module (e.g. ``state.active_pinger = x``)
are visible to every consumer — that's the central property this module
relies on, and it's how the old ``global`` contract is preserved.

``FA11y.py`` initializes this module's fields at startup. Callers that
run before startup (which would only be ``import FA11y``) will see
placeholder ``None`` / default values. That's fine — no action handler
fires before ``main()`` completes startup.
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    # Type-only imports — avoid runtime circulars.
    from accessible_output2.outputs.auto import Auto  # noqa: F401
    from lib.managers.poi_data_manager import POIData  # noqa: F401


# ---------------------------------------------------------------------------
# Init-once globals (assigned by FA11y.py at startup)
# ---------------------------------------------------------------------------

#: Main TTS wrapper. Assigned by FA11y.py after ``Auto()`` is constructed.
speaker: "Optional[Auto]" = None

#: Root logger for action-handler modules.
logger: logging.Logger = logging.getLogger("fa11y.app")

#: Pygame ``Sound`` for the "update available" alert. Optional — may be
#: ``None`` if audio init failed.
update_sound = None


# ---------------------------------------------------------------------------
# Thread-synchronization events
#
# Constructed here at import time so both FA11y.py and the action modules
# see the same Event objects. These are authoritative — FA11y.py should
# NOT construct its own copies.
# ---------------------------------------------------------------------------

#: Global shutdown signal. Set by signal_handler / cleanup paths.
shutdown_requested: threading.Event = threading.Event()

#: Signal sent by key_listener / GUI threads to stop the main listener loop.
stop_key_listener: threading.Event = threading.Event()

#: True when Epic returned 401 somewhere; triggers the re-auth flow.
auth_expired: threading.Event = threading.Event()

#: One flag per GUI window so we don't open the same one twice.
config_gui_open: threading.Event = threading.Event()
social_gui_open: threading.Event = threading.Event()
discovery_gui_open: threading.Event = threading.Event()
locker_gui_open: threading.Event = threading.Event()
gamemode_gui_open: threading.Event = threading.Event()
visited_objects_gui_open: threading.Event = threading.Event()
custom_poi_gui_open: threading.Event = threading.Event()
stw_gui_open: threading.Event = threading.Event()


# ---------------------------------------------------------------------------
# Lazy singletons — accessed via getters so the caller always sees the
# current value, even if the owning FA11y startup hasn't bound it yet.
# ---------------------------------------------------------------------------

# These are reassigned by FA11y.py as it wires up subsystems. Access
# through the getter/setter helpers; callers should NOT ``import`` these
# names directly (imports freeze the reference at import time, but
# ``state.xxx`` reads hit the current binding).
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
    """Assign the POIData singleton (used during startup + reload)."""
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
