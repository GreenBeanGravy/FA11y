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
        from lib.utilities.discovery_ops import get_api
        return DiscoveryView(host, get_api())

    return ViewPage(parent, hub, "Discover", make, identity=state.get_discovery_api, after_login=True)


def locker_page(parent, hub) -> ViewPage:
    def load():
        # Everything slow happens here, on a worker thread: the cosmetics
        # list, and which of them the signed-in account owns.
        from lib.utilities.epic_auth import get_or_create_cosmetics_cache
        cosmetics = get_or_create_cosmetics_cache(force_refresh=False, owned_only=False)
        if cosmetics is None:
            return None
        auth = _epic_auth()
        owned = None
        if auth and auth.display_name:
            try:
                owned = auth.fetch_owned_cosmetics()
            except Exception:
                owned = None
        return cosmetics, owned

    def make(host, data):
        from lib.guis.locker_gui import LockerView
        cosmetics, owned = data
        auth = _epic_auth()
        return LockerView(host, cosmetics, auth_instance=auth,
                          owned_only=bool(auth and auth.display_name), fetched_owned=owned)

    return ViewPage(parent, hub, "Locker", make, load=load, loading_text="Loading cosmetics…",
                    identity=_epic_auth, after_login=True,
                    unavailable_text="Couldn't load cosmetics. Check your internet connection, "
                                     "then open this page again.")


def social_page(parent, hub) -> ViewPage:
    def make(host):
        manager = state.get_social_manager()
        if manager is None:
            return None
        from lib.guis.social_gui import SocialView
        return SocialView(host, manager)

    return ViewPage(parent, hub, "Social", make, identity=state.get_social_manager, after_login=True,
                    unavailable_text="Sign in on the Epic account page to see your friends, "
                                     "requests and party.")


def quests_page(parent, hub) -> ViewPage:
    def make(host):
        auth = _epic_auth()
        if not _signed_in(auth):
            return None
        from lib.guis.quest_gui import QuestView
        return QuestView(host, auth)

    return ViewPage(parent, hub, "Quests and passes", make, identity=_epic_auth, after_login=True,
                    unavailable_text="Sign in on the Epic account page to see your quests.")
