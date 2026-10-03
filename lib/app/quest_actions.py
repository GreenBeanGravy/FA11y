"""Open the quest browser: the Quests and passes page of the FA11y window."""
from lib.hub import get_hub


def open_quest_browser():
    hub = get_hub()
    if hub is not None:
        hub.show_page('quests', summon=True)
