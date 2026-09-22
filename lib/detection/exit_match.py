"""Leave a match using the September 2026 Fortnite sidebar layout."""
import logging
from functools import lru_cache
from pathlib import Path
import threading
import time

import cv2
import numpy as np
from PIL import ImageGrab
from accessible_output2.outputs.auto import Auto
from lib.utilities.mouse import instant_click, press_key
from lib.utilities.window_utils import get_active_window_title

speaker = Auto()
logger = logging.getLogger(__name__)
_ASSETS = Path(__file__).resolve().parents[2] / "assets" / "exit_match"
_action_lock = threading.Lock()
# Reference coordinates are for the observed 1920 x 1080 fullscreen layout.
_REGIONS = {
    "menu_tab": (1635, 35, 1780, 110),
    "settings_tab": (1515, 35, 1680, 110),
    "return_to_lobby": (1380, 130, 1740, 210),
}


@lru_cache(maxsize=3)
def _template(name):
    image = cv2.imread(str(_ASSETS / (name + ".png")), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise RuntimeError("Missing leave-match reference: " + name)
    return image


def _find(frame, name):
    """Match a control in its own region, including inverted hover/selected colors."""
    x1, y1, x2, y2 = _REGIONS[name]
    template = _template(name)
    scores = cv2.matchTemplate(frame[y1:y2, x1:x2], template, cv2.TM_CCOEFF_NORMED)
    _, score, _, location = cv2.minMaxLoc(np.abs(scores))
    if score < .85:
        return None
    return (x1 + location[0] + template.shape[1] // 2,
            y1 + location[1] + template.shape[0] // 2)


def _sidebar(frame):
    return bool(_sidebar_controls(frame))


def _sidebar_controls(frame):
    menu = _find(frame, "menu_tab")
    settings = _find(frame, "settings_tab")
    return (menu, settings) if menu is not None and settings is not None else None


def _require_fortnite():
    if get_active_window_title().strip().lower() != "fortnite":
        raise RuntimeError("Fortnite must be the active window to leave a match.")


def _capture():
    _require_fortnite()
    image = ImageGrab.grab()
    width, height = image.size
    if abs(width / height - 16 / 9) > .02:
        raise RuntimeError("Leave match requires Fortnite fullscreen at a 16 by 9 resolution.")
    gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    return cv2.resize(gray, (1920, 1080)), (width / 1920, height / 1080)


def _wait_for(predicate, timeout=3., stable=False):
    deadline = time.monotonic() + timeout
    previous = None
    while True:
        frame, scale = _capture()
        result = predicate(frame)
        if result and (not stable or result == previous):
            return result, scale
        previous = result
        if time.monotonic() >= deadline:
            return None
        time.sleep(.1)


def _click(point, scale):
    _require_fortnite()
    instant_click(round(point[0] * scale[0]), round(point[1] * scale[1]))


def exit_match():
    """Open the sidebar if needed, select Menu, then Return to lobby once.

    Each click requires a recognized control. The current flow has no final
    confirmation button; never send the obsolete third click into the lobby.
    """
    if not _action_lock.acquire(blocking=False):
        return False
    try:
        frame, scale = _capture()
        if not _sidebar(frame):
            _require_fortnite()
            press_key("escape")
        # The sidebar slides horizontally while opening. Recognize the icons at
        # the same positions in consecutive frames before targeting a control.
        if not _wait_for(_sidebar_controls, stable=True):
            speaker.speak("Could not find the Fortnite sidebar. Match was not left.")
            return False
        frame, scale = _capture()
        target = _find(frame, "return_to_lobby")
        if target is None:
            menu = _find(frame, "menu_tab")
            if menu is None:
                speaker.speak("Could not find the sidebar menu tab. Match was not left.")
                return False
            _click(menu, scale)
            result = _wait_for(lambda frame: _find(frame, "return_to_lobby"), stable=True)
            if result is None:
                speaker.speak("Return to lobby was not found. You may already be in the lobby.")
                return False
            target, scale = result
        _click(target, scale)
        if _wait_for(lambda frame: not _sidebar(frame)):
            speaker.speak("Returning to lobby.")
            return True
        speaker.speak("Return to lobby was selected, but the menu is still open. Please check the game.")
        return False
    except Exception as error:
        logger.exception("Could not leave match")
        speaker.speak(str(error))
        return False
    finally:
        _action_lock.release()
