"""Hub pages that host the existing feature views (Discover, Locker, Social, Quests)."""
from __future__ import annotations

from lib.app import state
from lib.hub.view_page import ViewPage


def _epic_auth():
    from lib.utilities.epic_auth import get_epic_auth_instance
    return get_epic_auth_instance()


def _signed_in(auth) -> bool:
    return bool(auth and auth.access_token and auth.is_valid)


def discover_page(parent, hub) -> ViewPage:
    def make(host):
        from lib.guis.discovery_gui import DiscoveryView
        api = state.get_discovery_api()
        if api is None:
            from lib.utilities.epic_discovery import EpicDiscovery
            auth = _epic_auth()
            api = EpicDiscovery(auth if _signed_in(auth) else None)
            state.set_discovery_api(api)
        return DiscoveryView(host, api)

    return ViewPage(parent, hub, "Discover", make, identity=state.get_discovery_api)


def locker_page(parent, hub) -> ViewPage:
    def load():
        from lib.utilities.epic_auth import get_or_create_cosmetics_cache
        return get_or_create_cosmetics_cache(force_refresh=False, owned_only=False)

    def make(host, cosmetics):
        from lib.guis.locker_gui import LockerView
        auth = _epic_auth()
        return LockerView(host, cosmetics, auth_instance=auth,
                          owned_only=bool(auth and auth.display_name))

    return ViewPage(parent, hub, "Locker", make, load=load, loading_text="Loading cosmetics…",
                    unavailable_text="Couldn't load cosmetics. Check your internet connection, "
                                     "then open this page again.")


def social_page(parent, hub) -> ViewPage:
    def make(host):
        manager = state.get_social_manager()
        if manager is None:
            return None
        from lib.guis.social_gui import SocialView
        return SocialView(host, manager)

    return ViewPage(parent, hub, "Social", make, identity=state.get_social_manager,
                    unavailable_text="Sign in on the Epic account page to see your friends, "
                                     "requests and party.")


def quests_page(parent, hub) -> ViewPage:
    def make(host):
        auth = _epic_auth()
        if not _signed_in(auth):
            return None
        from lib.guis.quest_gui import QuestView
        return QuestView(host, auth)

    return ViewPage(parent, hub, "Quests and passes", make, identity=_epic_auth,
                    unavailable_text="Sign in on the Epic account page to see your quests.")
