"""Short or full announcement text, depending on the Simplify speech setting."""

import threading

from lib.utilities.utilities import (
    get_config_boolean, on_config_change, read_config,
)

_KEY = 'SimplifySpeechOutput'
_lock = threading.Lock()
_simple = None
_registered = False


def _on_change(config) -> None:
    global _simple
    try:
        _simple = get_config_boolean(config, _KEY, False)
    except Exception:
        _simple = False


def is_simple() -> bool:
    """True when Simplify speech is on. Reads config once, then follows changes."""
    global _simple, _registered
    if _simple is None:
        with _lock:
            if not _registered:
                on_config_change(_on_change)
                _registered = True
            if _simple is None:
                try:
                    _simple = get_config_boolean(read_config(), _KEY, False)
                except Exception:
                    _simple = False
    return bool(_simple)


def simple(full: str, short: str | None = None) -> str:
    """Return short when Simplify speech is on and a short form exists, else full."""
    if short is not None and is_simple():
        return short
    return full
