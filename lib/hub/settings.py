"""Read and write the hub's own settings in FA11y's config file."""
from __future__ import annotations

from lib.utilities.utilities import get_config_boolean, read_config, save_config

CLOSE_ASK = "ask"
CLOSE_TRAY = "tray"
CLOSE_QUIT = "quit"


def flag(key: str, default: bool) -> bool:
    return get_config_boolean(read_config(), key, default)


def close_action() -> str:
    raw = read_config().get("Hub", "CloseAction", fallback=CLOSE_ASK)
    value = raw.split('"')[0].strip().lower()
    return value if value in (CLOSE_ASK, CLOSE_TRAY, CLOSE_QUIT) else CLOSE_ASK


def interface() -> str:
    """Which window to use: "classic" (the wx window) or "auto" (the new one when it's installed)."""
    raw = read_config().get("Hub", "Interface", fallback="auto")
    value = raw.split('"')[0].strip().lower()
    return "classic" if value == "classic" else "auto"


def set_value(section: str, key: str, value: str) -> bool:
    """Set section.key, keeping the description text stored after the value."""
    config = read_config(use_cache=False)
    if not config.has_section(section):
        config.add_section(section)
    old = config.get(section, key, fallback="")
    description = ""
    if '"' in old:
        description = old[old.index('"'):]
    config.set(section, key, f"{value} {description}".strip())
    return save_config(config)


def set_close_action(action: str) -> bool:
    return set_value("Hub", "CloseAction", action)
