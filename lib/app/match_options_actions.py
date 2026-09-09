"""Hotkey entry point for the accessible match-options dialog."""
import logging
import threading
from lib.app import state

_open=threading.Event()
logger=logging.getLogger(__name__)


def open_match_options():
    from lib.guis.gui_utilities import launch_gui_thread_safe
    from lib.utilities.window_utils import focus_window
    from lib.guis.match_options_gui import MatchOptionsDialog, TITLE
    from lib.detection.match_options import focus_and_read
    def launch():
        if _open.is_set():
            focus_window(TITLE)
            return
        _open.set()
        dialog=None
        try:
            state.match_options_busy.set()
            current=focus_and_read()
            dialog=MatchOptionsDialog(current)
            state.match_options_busy.clear()
            state.speaker.speak('Match options. '+current.summary())
            dialog.ShowModal()
        except Exception as error:
            logger.exception('Could not open match options')
            state.speaker.speak(str(error))
        finally:
            if dialog is not None:
                dialog.Destroy()
            state.match_options_busy.clear()
            _open.clear()
    launch_gui_thread_safe(launch)
