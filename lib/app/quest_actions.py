"""Open the accessible account and match quest browser."""
import threading

from lib.app import state

_open = threading.Event()


def open_quest_browser():
    from lib.guis.gui_utilities import launch_gui_thread_safe
    def show():
        if _open.is_set():
            from lib.utilities.window_utils import focus_window
            focus_window('Fortnite Quests')
            return
        _open.set()
        try:
            from lib.utilities.epic_auth import get_epic_auth_instance
            from lib.guis.quest_gui import show_quest_gui
            show_quest_gui(get_epic_auth_instance())
        finally:
            _open.clear()
    launch_gui_thread_safe(show)
