"""Hub pages for FA11y's settings and keybinds (two views of the config editor)."""
from __future__ import annotations

from lib.hub.view_page import ViewPage

SETTINGS_TABS = ["General", "Toggles", "Values", "Audio", "GameObjects", "Advanced"]
KEYBINDS_TABS = ["Keybinds"]


def _make_config_view(host, hub, tabs):
    from lib.guis.config_gui import ConfigView
    from lib.utilities.utilities import Config, get_config_boolean, read_config, save_config

    config_instance = Config()
    config_instance.config = read_config()

    def update_callback(updated_config_parser):
        save_config(updated_config_parser)
        # Re-binds keys and picks up the new settings.
        hub.services.reload_config()
        from lib.hub import sounds
        sounds.set_enabled(get_config_boolean(updated_config_parser, "NavigationSounds", True))

    return ConfigView(host, config_instance, update_callback, tabs=tabs)


def settings_page(parent, hub) -> ViewPage:
    return ViewPage(parent, hub, "Settings",
                    lambda host: _make_config_view(host, hub, SETTINGS_TABS))


def keybinds_page(parent, hub) -> ViewPage:
    return ViewPage(parent, hub, "Keybinds",
                    lambda host: _make_config_view(host, hub, KEYBINDS_TABS))
