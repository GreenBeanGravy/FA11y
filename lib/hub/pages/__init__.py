"""The hub's pages, in sidebar order."""
from __future__ import annotations

from typing import List

from lib.hub.frame import PageSpec
from lib.hub.sidebar import SidebarEntry


def default_pages() -> List[PageSpec]:
    from lib.hub.pages.about import AboutPage
    from lib.hub.pages.account import AccountPage
    from lib.hub.pages.fortnite import FortnitePage
    from lib.hub.pages.home import HomePage
    from lib.hub.pages.settings import keybinds_page, settings_page
    from lib.hub.pages.views import discover_page, locker_page, quests_page, social_page

    return [
        PageSpec(SidebarEntry("home", "Home", "home"), HomePage),
        PageSpec(SidebarEntry("fortnite", "Fortnite", "device-gamepad-2", "Play"), FortnitePage),
        PageSpec(SidebarEntry("discover", "Discover", "compass", "Play"), discover_page),
        PageSpec(SidebarEntry("account", "Epic account", "user", "Account"), AccountPage),
        PageSpec(SidebarEntry("locker", "Locker", "shirt", "Account"), locker_page),
        PageSpec(SidebarEntry("social", "Social", "users", "Account"), social_page),
        PageSpec(SidebarEntry("quests", "Quests and passes", "list-check", "Account"), quests_page),
        PageSpec(SidebarEntry("settings", "Settings", "settings", "FA11y"), settings_page),
        PageSpec(SidebarEntry("keybinds", "Keybinds", "keyboard", "FA11y"), keybinds_page),
        PageSpec(SidebarEntry("about", "About and updates", "info-circle", "FA11y"), AboutPage),
    ]
