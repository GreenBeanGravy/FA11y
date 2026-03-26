import ctypes
import time
import threading
from typing import Tuple
from lib.utilities.utilities import get_config_int, get_config_float, read_config
from lib.mouse_passthrough.faker_input import (
    send_mouse_move as _fi_send_mouse_move,
    send_mouse_button as _fi_send_mouse_button,
    send_mouse_scroll as _fi_send_mouse_scroll,
    is_available as _fi_is_available,
    is_initialized as _fi_is_initialized,
    initialize_fakerinput as _fi_initialize,
    FAKERINPUT_AVAILABLE,
)

# Global configuration
config = read_config()

# Mouse movement synchronization
_movement_lock = threading.Lock()
_current_movement_thread = None

# Default cache range matching mouse_passthrough config default
_CACHE_RANGE = 100


def _ensure_initialized():
    """Ensure FakerInput is initialized via the shared connection."""
    if not _fi_is_initialized():
        return _fi_initialize(_CACHE_RANGE)
    return True


def _send_mouse_button(button_name, is_down):
    """Internal function to send mouse button events via shared FakerInput."""
    return _fi_send_mouse_button(button_name, is_down, _CACHE_RANGE)


def smooth_move_mouse(dx: int, dy: int, step_delay: float = 0.01, steps: int = None, step_speed: int = None, second_dy: int = None, recenter_delay: float = None):
    """Move mouse smoothly with steps using shared FakerInput."""
    global _current_movement_thread

    if steps is None:
        steps = get_config_int(config, 'TurnSteps', 5)
    if step_speed is None:
        step_speed = get_config_int(config, 'RecenterStepSpeed', 0)

    step_speed_seconds = step_speed / 1000.0

    if not _fi_is_available():
        return False
    if not _fi_is_initialized():
        if not _fi_initialize(_CACHE_RANGE):
            return False

    def move():
        with _movement_lock:
            try:
                if steps <= 1:
                    _fi_send_mouse_move(dx, dy, _CACHE_RANGE)
                    return

                step_x = dx / steps
                step_y = dy / steps

                for i in range(steps):
                    start_time = time.perf_counter()

                    if i == steps - 1:
                        final_x = dx - int(step_x * i)
                        final_y = dy - int(step_y * i)
                        _fi_send_mouse_move(final_x, final_y, _CACHE_RANGE)
                    else:
                        _fi_send_mouse_move(int(step_x), int(step_y), _CACHE_RANGE)

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
                            _fi_send_mouse_move(0, final_y, _CACHE_RANGE)
                        else:
                            _fi_send_mouse_move(0, step_dy, _CACHE_RANGE)

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
                print(f"Mouse movement error: {e}")

    if _current_movement_thread and _current_movement_thread.is_alive():
        _current_movement_thread.join(timeout=0.1)

    _current_movement_thread = threading.Thread(target=move, daemon=True)
    _current_movement_thread.start()


def mouse_scroll(amount: int):
    """Scroll mouse wheel via shared FakerInput."""
    return _fi_send_mouse_scroll(amount, _CACHE_RANGE)


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
