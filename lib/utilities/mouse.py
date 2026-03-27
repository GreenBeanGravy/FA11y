import ctypes
import ctypes.wintypes
import time
import threading
from lib.utilities.utilities import get_config_int, get_config_float, read_config
from lib.mouse_passthrough import faker_input as _fi

# Global configuration
config = read_config()

# Mouse movement synchronization
_movement_lock = threading.Lock()
_current_movement_thread = None

# Expose FakerInput state from the passthrough module (single source of truth)
@property
def _fakerinput_available():
    return _fi.FAKERINPUT_AVAILABLE

@property
def _fakerinput_initialized():
    return _fi._initialized

# For external consumers that check these directly (e.g. exit_match logging)
def _get_available():
    return _fi.FAKERINPUT_AVAILABLE

def _get_initialized():
    return _fi._initialized

# Keep module-level names so existing `from lib.utilities.mouse import FAKERINPUT_AVAILABLE` still works,
# but make them dynamic via a property trick isn't possible at module level.
# Instead, we define them as functions and also set initial values that get checked at call time.
FAKERINPUT_AVAILABLE = _fi.FAKERINPUT_AVAILABLE  # snapshot at import; functions below re-check live

def _ensure_init():
    """Ensure the passthrough module's FakerInput is initialized. Returns True if ready."""
    if _fi._initialized:
        return True
    if not _fi.FAKERINPUT_AVAILABLE:
        return False
    # Initialize with a reasonable cache range
    return _fi.initialize_fakerinput(cache_range=100)

def _send_mouse_button(button_name, is_down):
    """Send mouse button events through the passthrough module's FakerInput."""
    if not _ensure_init():
        print(f"[mouse.py] FakerInput not available for button {button_name}")
        return False

    try:
        method_name = "ButtonDown" if is_down else "ButtonUp"
        button_method = _fi._RelativeMouseReportType.GetMethod(method_name)

        if button_method:
            button_enum = _fi._System.Enum.Parse(_fi._MouseButtonType, button_name)
            args_array = _fi._System.Array[_fi._System.Object]([button_enum])
            button_method.Invoke(_fi._mouse_report, args_array)

            update_args = _fi._System.Array[_fi._System.Object]([_fi._mouse_report])
            _fi._update_method.Invoke(_fi._faker_input, update_args)
            return True
    except Exception as e:
        print(f"[mouse.py] Mouse button {button_name} {'down' if is_down else 'up'} error: {e}")

    return False

def smooth_move_mouse(dx: int, dy: int, step_delay: float = 0.01, steps: int = None, step_speed: int = None, second_dy: int = None, recenter_delay: float = None):
    """Move mouse smoothly with steps using FakerInput"""
    global _current_movement_thread

    if steps is None:
        steps = get_config_int(config, 'TurnSteps', 5)
    if step_speed is None:
        step_speed = get_config_int(config, 'RecenterStepSpeed', 0)

    step_speed_seconds = step_speed / 1000.0

    if not _ensure_init():
        print("[mouse.py] FakerInput not available for smooth_move_mouse")
        return False

    def move():
        with _movement_lock:
            try:
                if steps <= 1:
                    _fi._mouseX_property.SetValue(_fi._mouse_report, _fi.get_cached_int16(dx))
                    _fi._mouseY_property.SetValue(_fi._mouse_report, _fi.get_cached_int16(dy))
                    args = _fi._System.Array[_fi._System.Object]([_fi._mouse_report])
                    _fi._update_method.Invoke(_fi._faker_input, args)
                    _fi._reset_method.Invoke(_fi._mouse_report, None)
                    return

                step_x = dx / steps
                step_y = dy / steps

                for i in range(steps):
                    start_time = time.perf_counter()

                    if i == steps - 1:
                        final_x = dx - int(step_x * i)
                        final_y = dy - int(step_y * i)
                        _fi._mouseX_property.SetValue(_fi._mouse_report, _fi.get_cached_int16(final_x))
                        _fi._mouseY_property.SetValue(_fi._mouse_report, _fi.get_cached_int16(final_y))
                    else:
                        _fi._mouseX_property.SetValue(_fi._mouse_report, _fi.get_cached_int16(int(step_x)))
                        _fi._mouseY_property.SetValue(_fi._mouse_report, _fi.get_cached_int16(int(step_y)))

                    args = _fi._System.Array[_fi._System.Object]([_fi._mouse_report])
                    _fi._update_method.Invoke(_fi._faker_input, args)
                    _fi._reset_method.Invoke(_fi._mouse_report, None)

                    if step_speed > 0:
                        elapsed_time = time.perf_counter() - start_time
                        remaining_time = max(0, step_speed_seconds - elapsed_time)
                        if remaining_time > 0:
                            time.sleep(remaining_time)
                    elif step_delay > 0:
                        elapsed_time = time.perf_counter() - start_time
                        remaining_time = max(0, step_delay - elapsed_time)
                        if remaining_time > 0:
                            time.sleep(remaining_time)

                if second_dy is not None and recenter_delay is not None:
                    if recenter_delay > 0:
                        time.sleep(recenter_delay)

                    step_dy = second_dy // steps
                    for i in range(steps):
                        start_time = time.perf_counter()

                        if i == steps - 1:
                            final_y = second_dy - (step_dy * i)
                            _fi._mouseX_property.SetValue(_fi._mouse_report, _fi.get_cached_int16(0))
                            _fi._mouseY_property.SetValue(_fi._mouse_report, _fi.get_cached_int16(final_y))
                        else:
                            _fi._mouseX_property.SetValue(_fi._mouse_report, _fi.get_cached_int16(0))
                            _fi._mouseY_property.SetValue(_fi._mouse_report, _fi.get_cached_int16(step_dy))

                        args = _fi._System.Array[_fi._System.Object]([_fi._mouse_report])
                        _fi._update_method.Invoke(_fi._faker_input, args)
                        _fi._reset_method.Invoke(_fi._mouse_report, None)

                        if step_speed > 0:
                            elapsed_time = time.perf_counter() - start_time
                            remaining_time = max(0, step_speed_seconds - elapsed_time)
                            if remaining_time > 0:
                                time.sleep(remaining_time)
                        elif step_delay > 0:
                            elapsed_time = time.perf_counter() - start_time
                            remaining_time = max(0, step_delay - elapsed_time)
                            if remaining_time > 0:
                                time.sleep(remaining_time)

            except Exception as e:
                print(f"[mouse.py] Mouse movement error: {e}")

    if _current_movement_thread and _current_movement_thread.is_alive():
        _current_movement_thread.join(timeout=0.1)

    _current_movement_thread = threading.Thread(target=move, daemon=True)
    _current_movement_thread.start()

def mouse_scroll(amount: int):
    """Scroll mouse wheel"""
    if not _ensure_init():
        return False

    try:
        wheel_property = _fi._RelativeMouseReportType.GetProperty("WheelPosition")

        # Clamp the value to the signed byte range first
        wheel_value = max(-127, min(127, amount))

        # Convert the signed value to its unsigned 8-bit equivalent if it's negative
        if wheel_value < 0:
            wheel_value += 256  # e.g., -1 becomes 255, -120 becomes 136

        # Set the value using the correct System.Byte type
        wheel_property.SetValue(_fi._mouse_report, _fi._System.Byte(wheel_value))

        args = _fi._System.Array[_fi._System.Object]([_fi._mouse_report])
        _fi._update_method.Invoke(_fi._faker_input, args)

        # Reset wheel position back to 0 using the correct type
        wheel_property.SetValue(_fi._mouse_report, _fi._System.Byte(0))
        return True
    except Exception as e:
        print(f"[mouse.py] Mouse scroll error: {e}")
        return False

# Core mouse button functions
def left_mouse_down():
    """Press and hold left mouse button"""
    return _send_mouse_button("LeftButton", True)

def left_mouse_up():
    """Release left mouse button"""
    return _send_mouse_button("LeftButton", False)

def right_mouse_down():
    """Press and hold right mouse button"""
    return _send_mouse_button("RightButton", True)

def right_mouse_up():
    """Release right mouse button"""
    return _send_mouse_button("RightButton", False)

def hold_left_button():
    """Hold left mouse button"""
    return left_mouse_down()

def release_left_button():
    """Release left mouse button"""
    return left_mouse_up()

def hold_right_button():
    """Hold right mouse button"""
    return right_mouse_down()

def release_right_button():
    """Release right mouse button"""
    return right_mouse_up()

def hold_middle_button():
    """Hold middle mouse button"""
    return _send_mouse_button("MiddleButton", True)

def release_middle_button():
    """Release middle mouse button"""
    return _send_mouse_button("MiddleButton", False)

def click_mouse(button='left'):
    """Click mouse button with brief delay"""
    if button == 'left':
        left_mouse_down()
        time.sleep(0.01)
        left_mouse_up()
    elif button == 'right':
        right_mouse_down()
        time.sleep(0.01)
        right_mouse_up()
    elif button == 'middle':
        hold_middle_button()
        time.sleep(0.01)
        release_middle_button()

def hold_mouse_button(button='left'):
    """Hold down mouse button"""
    if button == 'left':
        return left_mouse_down()
    elif button == 'right':
        return right_mouse_down()
    elif button == 'middle':
        return hold_middle_button()

def release_mouse_button(button='left'):
    """Release mouse button"""
    if button == 'left':
        return left_mouse_up()
    elif button == 'right':
        return right_mouse_up()
    elif button == 'middle':
        return release_middle_button()

# Compatibility aliases
left_click = lambda: click_mouse('left')
right_click = lambda: click_mouse('right')

def move_mouse_relative(dx, dy):
    """Move mouse relative to current position"""
    return smooth_move_mouse(dx, dy, step_delay=0.01, steps=1)

def get_mouse_position():
    """Get current mouse position"""
    user32 = ctypes.windll.user32
    pt = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)

def get_screen_size():
    """Get screen resolution."""
    user32 = ctypes.windll.user32
    return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))

def move_to(target_x, target_y, duration=0.05):
    """Move cursor to absolute screen coordinates using FakerInput relative moves.
    Mirrors pyautogui.moveTo(x, y, duration) — blocks for the duration, then returns.
    """
    global _current_movement_thread
    cur_x, cur_y = get_mouse_position()
    dx = target_x - cur_x
    dy = target_y - cur_y
    if dx != 0 or dy != 0:
        # Calculate steps to spread over the duration (minimum 1 step)
        steps = max(1, int(duration / 0.01))  # ~10ms per step
        step_delay = duration / steps if steps > 1 else 0
        smooth_move_mouse(dx, dy, step_delay=step_delay, steps=steps)
        # Block until the movement thread finishes (mirrors pyautogui blocking behavior)
        if _current_movement_thread and _current_movement_thread.is_alive():
            _current_movement_thread.join(timeout=2.0)

def move_to_and_click(target_x, target_y, button='left', duration=0.05):
    """Mirrors pyautogui.moveTo(x, y, duration) + pyautogui.click().
    Move takes `duration` seconds (blocking), then click fires immediately."""
    move_to(target_x, target_y, duration=duration)
    click_mouse(button)

def instant_click(target_x, target_y, button='left'):
    """Mirrors pyautogui.click(x, y) — instant move + click with no duration."""
    move_to(target_x, target_y, duration=0)
    click_mouse(button)

def move_to_and_right_click(target_x, target_y, duration=0.05):
    """Mirrors pyautogui.moveTo(x, y, duration) + pyautogui.rightClick()."""
    move_to(target_x, target_y, duration=duration)
    click_mouse('right')

# --- Keyboard helpers (SendInput-based, no pyautogui) ---

# SendInput structures
class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _INPUT(ctypes.Structure):
    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("padding", ctypes.c_byte * 24)]
    _fields_ = [("type", ctypes.c_ulong), ("union", _INPUT_UNION)]

_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004
_KEYEVENTF_SCANCODE = 0x0008

import win32api as _win32api
import win32con as _win32con

_VK_MAP = {
    'escape': _win32con.VK_ESCAPE, 'esc': _win32con.VK_ESCAPE,
    'enter': _win32con.VK_RETURN, 'return': _win32con.VK_RETURN,
    'tab': _win32con.VK_TAB, 'space': _win32con.VK_SPACE,
    'backspace': _win32con.VK_BACK, 'delete': _win32con.VK_DELETE,
    'up': _win32con.VK_UP, 'down': _win32con.VK_DOWN,
    'left': _win32con.VK_LEFT, 'right': _win32con.VK_RIGHT,
    'home': _win32con.VK_HOME, 'end': _win32con.VK_END,
    'pageup': _win32con.VK_PRIOR, 'pagedown': _win32con.VK_NEXT,
    'insert': _win32con.VK_INSERT,
    'shift': _win32con.VK_SHIFT, 'lshift': _win32con.VK_LSHIFT, 'rshift': _win32con.VK_RSHIFT,
    'ctrl': _win32con.VK_CONTROL, 'lctrl': _win32con.VK_LCONTROL, 'rctrl': _win32con.VK_RCONTROL,
    'alt': _win32con.VK_MENU, 'lalt': _win32con.VK_LMENU, 'ralt': _win32con.VK_RMENU,
    'f1': _win32con.VK_F1, 'f2': _win32con.VK_F2, 'f3': _win32con.VK_F3,
    'f4': _win32con.VK_F4, 'f5': _win32con.VK_F5, 'f6': _win32con.VK_F6,
    'f7': _win32con.VK_F7, 'f8': _win32con.VK_F8, 'f9': _win32con.VK_F9,
    'f10': _win32con.VK_F10, 'f11': _win32con.VK_F11, 'f12': _win32con.VK_F12,
    'm': 0x4D, 'a': 0x41,
}

def _get_vk(key_name):
    """Get virtual key code from key name."""
    key_lower = key_name.lower()
    if key_lower in _VK_MAP:
        return _VK_MAP[key_lower]
    if len(key_lower) == 1:
        return _win32api.VkKeyScan(key_lower) & 0xFF
    return 0

def _send_key_event(vk, flags=0):
    """Send a single key event via SendInput."""
    scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
    inp = _INPUT()
    inp.type = _INPUT_KEYBOARD
    inp.union.ki.wVk = vk
    inp.union.ki.wScan = scan
    inp.union.ki.dwFlags = flags
    inp.union.ki.time = 0
    inp.union.ki.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

def key_down(key_name):
    """Press and hold a key."""
    vk = _get_vk(key_name)
    if vk:
        _send_key_event(vk, 0)

def key_up(key_name):
    """Release a key."""
    vk = _get_vk(key_name)
    if vk:
        _send_key_event(vk, _KEYEVENTF_KEYUP)

def press_key(key_name):
    """Press and release a key."""
    key_down(key_name)
    time.sleep(0.01)
    key_up(key_name)

def hotkey(*keys):
    """Press a key combination (e.g. hotkey('ctrl', 'a'))."""
    for k in keys:
        key_down(k)
        time.sleep(0.01)
    for k in reversed(keys):
        key_up(k)
        time.sleep(0.01)

def typewrite(text, interval=0.02):
    """Type text character by character using SendInput unicode events."""
    for char in text:
        inp_down = _INPUT()
        inp_down.type = _INPUT_KEYBOARD
        inp_down.union.ki.wVk = 0
        inp_down.union.ki.wScan = ord(char)
        inp_down.union.ki.dwFlags = _KEYEVENTF_UNICODE
        inp_down.union.ki.time = 0
        inp_down.union.ki.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(_INPUT))

        inp_up = _INPUT()
        inp_up.type = _INPUT_KEYBOARD
        inp_up.union.ki.wVk = 0
        inp_up.union.ki.wScan = ord(char)
        inp_up.union.ki.dwFlags = _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP
        inp_up.union.ki.time = 0
        inp_up.union.ki.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(_INPUT))

        if interval > 0:
            time.sleep(interval)

# --- Pixel / Screenshot helpers (PIL-based, no pyautogui) ---

from PIL import ImageGrab
import numpy as np

def pixel(x, y):
    """Read pixel color at screen coordinates. Returns (r, g, b) tuple."""
    img = ImageGrab.grab(bbox=(x, y, x + 1, y + 1))
    return img.getpixel((0, 0))[:3]

def screenshot(region=None):
    """Capture a screenshot. region=(x, y, w, h) or None for full screen. Returns PIL Image."""
    if region:
        x, y, w, h = region
        return ImageGrab.grab(bbox=(x, y, x + w, y + h))
    return ImageGrab.grab()
