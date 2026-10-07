"""Screen-only, observed-state Discovery automation. Never starts matchmaking."""
import logging
import os
import re
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)
_selection_lock = threading.Lock()


def normalize(text):
    return re.sub(r"[^a-z0-9]", "", str(text).casefold())


def one_ocr_error(value, needle):
    """Allow one recognition error in a label of at least six characters."""
    if value == needle:
        return True
    if min(len(value),len(needle)) < 6 or abs(len(value)-len(needle)) > 1:
        return False
    if len(value) == len(needle):
        return sum(a != b for a,b in zip(value,needle)) <= 1
    longer, shorter = (value,needle) if len(value)>len(needle) else (needle,value)
    return any(longer[:i]+longer[i+1:] == shorter for i in range(len(longer)))


def find_text(rows, text, region=(0, 0, 1, 1), exact=False, fuzzy=False, cursor=False):
    """Return one unambiguous OCR label within normalized client bounds."""
    needle = normalize(text)
    matches = []
    for label, x, y, confidence in rows:
        value = normalize(label)
        if confidence < .35 or not needle:
            continue
        matches_text = value == needle if exact else needle in value
        if fuzzy:
            matches_text = matches_text or one_ocr_error(value,needle)
            if cursor and len(value) == len(needle)+1 and value[-1:] in ('l','i','1'):
                matches_text = matches_text or one_ocr_error(value[:-1],needle)
        if matches_text:
            if region[0] <= x <= region[2] and region[1] <= y <= region[3]:
                matches.append((label, x, y, confidence))
    return matches[0] if len(matches) == 1 else None


def edit_distance(a, b):
    previous = list(range(len(b)+1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j]+1, current[j-1]+1, previous[j-1]+(ca != cb)))
        previous = current
    return previous[-1]


def title_close_enough(seen, expected):
    """Whether OCR text shows the expected title.

    Creative titles are often long, so OCR misreads a few characters, and the details view cuts
    them off with an ellipsis. One recognition error is allowed per ten characters, so short
    titles still need an exact match or a single error.
    """
    value, needle = normalize(seen), normalize(expected)
    if not value or not needle:
        return False
    if value == needle or one_ocr_error(value, needle):
        return True
    if len(value) >= 8 and str(seen).rstrip().endswith(("...", "\u2026")) and len(value) < len(needle):
        return edit_distance(value, needle[:len(value)]) <= len(value)//10
    return edit_distance(value, needle) <= len(needle)//10


def find_title(rows, expected, region=(0, 0, 1, 1)):
    """The label showing the expected title, joining a title OCR split into several labels."""
    rows = [r for r in rows if r[3] >= .35 and region[0] <= r[1] <= region[2] and region[1] <= r[2] <= region[3]]
    # Left to right, then top to bottom, the way the title reads.
    rows.sort(key=lambda r: (round(r[2]*40), r[1]))
    for size in range(1, min(len(rows), 6)+1):
        for start in range(len(rows)-size+1):
            part = rows[start:start+size]
            text = " ".join(str(r[0]) for r in part)
            if title_close_enough(text, expected):
                return text, part[0][1], part[0][2], min(r[3] for r in part)
    return None


class ScreenUI:
    def __init__(self):
        import win32gui
        import ctypes
        from ctypes import wintypes
        import psutil
        from lib.managers.ocr_manager import get_ocr_manager
        from lib.utilities.window_utils import focus_fortnite
        if not focus_fortnite():
            raise RuntimeError("Could not focus Fortnite")
        # Use an explicitly typed, private function binding. Other app modules
        # configure user32 bindings, so shared default ctypes signatures are
        # unsuitable for owner identity checks in the running application.
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        owner = user32.GetWindowThreadProcessId
        owner.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        owner.restype = wintypes.DWORD
        process_id = wintypes.DWORD()
        deadline = time.monotonic()+2
        verified = False
        while time.monotonic() < deadline:
            self.hwnd = win32gui.GetForegroundWindow()
            owner(self.hwnd, ctypes.byref(process_id))
            pid = process_id.value
            if pid:
                try:
                    verified = 'fortniteclient-win64-shipping' in psutil.Process(pid).name().lower()
                except psutil.Error:
                    verified = False
            if verified:
                break
            time.sleep(.05)
        logger.info('[gamemode] foreground hwnd=%s pid=%s verified=%s', self.hwnd, pid,verified)
        if not verified:
            raise RuntimeError("Fortnite did not receive focus")
        self.ocr = get_ocr_manager()
        if not self.ocr.is_ready(timeout=10):
            raise RuntimeError("Screen text recognition is unavailable")
        self.diagnostics = None
        self.frame_number = 0
        if os.environ.get('FA11Y_GAMEMODE_DIAGNOSTICS') == '1':
            self.diagnostics = Path('logs/gamemode_selection') / str(time.time_ns())
            self.diagnostics.mkdir(parents=True, exist_ok=True)

    def bounds(self):
        import win32gui
        if win32gui.GetForegroundWindow() != self.hwnd:
            raise RuntimeError("Selection stopped because Fortnite lost focus")
        left, top = win32gui.ClientToScreen(self.hwnd, (0, 0))
        _, _, width, height = win32gui.GetClientRect(self.hwnd)
        return left, top, width, height

    def observe(self, region=(0, 0, 1, 1)):
        from lib.managers.screenshot_manager import screenshot_manager
        left, top, width, height = self.bounds()
        x0, y0, x1, y1 = region
        crop_x, crop_y = round(width*x0), round(height*y0)
        crop_width, crop_height = round(width*(x1-x0)), round(height*(y1-y0))
        picture = screenshot_manager.capture_region(
            dict(left=left+crop_x, top=top+crop_y, width=crop_width, height=crop_height), 'rgb')
        if picture is None:
            raise RuntimeError("Could not read Fortnite's screen")
        # Bound OCR cost while retaining client-relative text locations.
        import cv2
        self.frame_number += 1
        if self.diagnostics:
            cv2.imwrite(str(self.diagnostics / f'{self.frame_number:03d}.png'), cv2.cvtColor(picture, cv2.COLOR_RGB2BGR))
        started = time.monotonic()
        factor = min(1., 960 / crop_width)
        if factor < 1:
            picture = cv2.resize(picture, None, fx=factor, fy=factor)
        rows = []
        for box, label, confidence in self.ocr.read_text(picture, detail=1):
            x = (sum(float(point[0]) for point in box) / len(box) / factor + crop_x) / width
            y = (sum(float(point[1]) for point in box) / len(box) / factor + crop_y) / height
            rows.append((label, x, y, float(confidence)))
        logger.info("[gamemode] OCR elapsed=%.3f region=%s labels=%s", time.monotonic()-started, region, [(r[0],round(r[1],3),round(r[2],3)) for r in rows])
        self.bounds()  # Reject a capture taken while focus changed.
        return rows

    def click(self, label):
        import pyautogui
        left, top, width, height = self.bounds()
        logger.info("[gamemode] click label=%r client=(%.3f,%.3f) screen=(%d,%d)", label[0],label[1],label[2],round(left+label[1]*width),round(top+label[2]*height))
        x, y = round(left + label[1] * width), round(top + label[2] * height)
        # Menus need an absolute cursor destination. Gameplay's relative HID
        # movement can land elsewhere; do not click before verifying arrival.
        pyautogui.moveTo(x, y)
        actual = tuple(pyautogui.position())
        logger.info('[gamemode] cursor requested=%s actual=%s', (x,y), actual)
        if actual != (x, y):
            raise RuntimeError('Menu cursor did not reach the requested control')
        self.bounds()
        pyautogui.click()

    def scroll(self):
        import pyautogui
        left, top, width, height = self.bounds()
        pyautogui.moveTo(round(left + width * .5), round(top + height * .45))
        pyautogui.scroll(-3)

    def key(self, *keys):
        import pyautogui
        self.bounds()
        pyautogui.hotkey(*keys)

    def type(self, text):
        import pyautogui
        self.bounds()
        pyautogui.write(text)


def wait_for(ui, predicate, stage, timeout=8, region=(0, 0, 1, 1), stable=False):
    deadline = time.monotonic() + timeout
    started = time.monotonic()
    previous = None
    while time.monotonic() < deadline:
        rows = ui.observe(region)
        found = predicate(rows)
        if stable and found:
            if previous is None or abs(found[1]-previous[1]) > .002 or abs(found[2]-previous[2]) > .002:
                previous = found
                time.sleep(.15)
                continue
        if found:
            logger.info("[gamemode] verified=%s elapsed=%.3f", stage, time.monotonic()-started)
            return rows, found
        time.sleep(.15)
    raise RuntimeError(f"Could not verify {stage}; selection stopped")


def select_gamemode(search_text, expected_title=None, ui=None):
    """Select through visible menus, with bounded waits and no blind recovery."""
    if not _selection_lock.acquire(blocking=False):
        return False, "Another game-mode selection is already running"
    try:
        search_text = str(search_text).strip()
        if not search_text or len(search_text) > 100 or not search_text.isascii():
            return False, "Enter an ASCII island code or game-mode name"
        ui = ui or ScreenUI()
        logger.info("[gamemode] begin search=%r expected=%r", search_text, expected_title)
        rows = ui.observe((.035,.135,.47,.22))
        search = find_text(rows, 'Search Discover', (0, .1, .5, .3))
        if not search:
            rows += ui.observe((.47,.135,.69,.22))
        if not search and find_text(rows, 'Discover', (.45, .1, .65, .3), True) and find_text(rows, 'Following', (.55, .1, .7, .3), True):
            # A previous query replaces the placeholder, but the observed
            # Discovery navigation still proves the search-field layout.
            search = ('Search', .25, .175, 1)
        if not search:
            rows += ui.observe((.035,.035,.12,.09))
            play = find_text(rows, 'Play', (0, 0, .15, .12), True)
            if not play:
                raise RuntimeError("Start selection from the lobby or Discovery screen")
            ui.click(play)
            for _ in range(5):
                ui.scroll()
                try:
                    rows, search = wait_for(ui, lambda r: find_text(r, 'Search Discover', (0, .1, .5, .3)), 'Discovery search', timeout=1.5, region=(.035,.135,.47,.22))
                    break
                except RuntimeError as exc:
                    if 'Could not verify' not in str(exc):
                        raise
            if not search:
                raise RuntimeError("Could not locate Discovery search")
        ui.click(search)
        ui.key('ctrl', 'a')
        ui.type(search_text)
        wait_for(ui, lambda r: find_text(r, search_text, (0, .1, .5, .3), True, fuzzy=True,cursor=True), 'the entered search text', region=(.035,.135,.43,.22))
        ui.key('enter')
        wait_for(ui, lambda r: find_text(r, 'Islands Results', (0, .25, .4, .42)), 'search results', region=(.025,.31,.32,.39))
        # This is the observed first-result cell, expressed in client fractions.
        # Its identity is checked in the details view before SELECT is pressed.
        ui.click(('', .135, .49, 1))
        # Depending on current input focus, one click either focuses the card
        # or opens details. Never click twice after details have already opened:
        # the second click would open the artwork preview.
        select_predicate = lambda r: find_text(r, 'Select', (0, .7, .3, .95), True)
        try:
            rows, select = wait_for(ui, select_predicate, 'the mode details Select button', timeout=1.5, region=(.035,.8,.215,.89))
        except RuntimeError as exc:
            if 'Could not verify' not in str(exc):
                raise
            wait_for(ui, lambda r: find_text(r, 'Islands Results', (0,.25,.4,.42)), 'the still-open result grid', timeout=2, region=(.025,.31,.32,.39))
            ui.click(('', .135, .49, 1))
            rows, select = wait_for(ui, select_predicate, 'the mode details Select button', region=(.035,.8,.215,.89))
        rows = ui.observe((.025,.07,.65,.14))
        logger.info("[gamemode] details title labels=%s expected=%r", [r[0] for r in rows], expected_title)
        titles = [r for r in rows if .02 <= r[1] <= .6 and .07 <= r[2] <= .14 and r[3] >= .35]
        if expected_title and not normalize(expected_title):
            # A title with no Latin letters or digits can't be compared with OCR text. Such a
            # search can only be by island code (search text must be ASCII), which finds only that island.
            title = None
        elif expected_title:
            title = find_title(titles, expected_title)
            if title is None:
                raise RuntimeError("The result's title could not be verified; no mode was selected")
        else:
            title = titles[0] if len(titles) == 1 else None
            if title is None:
                raise RuntimeError("The result's title could not be verified; no mode was selected")
        ui.click(select)
        if title is None:
            # Without a readable title, a lobby change can't be confirmed by its text either.
            time.sleep(1)
            logger.info("[gamemode] completed search=%r selected by code", search_text)
            return True, None
        # Reload's map-rotation banner places its title below BR/Horde titles. The lobby
        # can shorten a long title, so it's compared the same tolerant way.
        wait_for(ui, lambda r: find_text(r, title[0], (0, .4, .3, .72), True,fuzzy=True) or find_title(r, expected_title or title[0], (0, .4, .3, .72)), 'the selected lobby mode', region=(.035,.48,.225,.7))
        logger.info("[gamemode] completed search=%r selected=%r", search_text,title[0])
        return True, None
    except Exception as exc:
        logger.warning("Screen game-mode selection stopped: %s", exc)
        return False, str(exc)
    finally:
        _selection_lock.release()
