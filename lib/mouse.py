import ctypes
import time
import threading
from typing import Tuple, Dict, Callable

# Constants
VK_NUMLOCK = 0x90
VK_LCONTROL, VK_RCONTROL = 0xA2, 0xA3
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
VK_NUMPAD1, VK_NUMPAD3, VK_NUMPAD5, VK_NUMPAD7, VK_NUMPAD9 = 0x61, 0x63, 0x65, 0x67, 0x69
VK_NUMPAD2, VK_NUMPAD8, VK_NUMPAD0, VK_NUMPAD4, VK_NUMPAD6 = 0x62, 0x68, 0x60, 0x64, 0x66
INPUT_MOUSE, MOUSEEVENTF_MOVE, MOUSEEVENTF_WHEEL = 0, 0x0001, 0x0800
MOUSE_SENSITIVITY = 30
TURN_AROUND_MOVE = 1158
SMOOTH_MOVE_DURATION = 0.01

# Structures for input simulation
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("ii", MOUSEINPUT)]

# Predefine commonly used functions
send_input = ctypes.windll.user32.SendInput
get_async_key_state = ctypes.windll.user32.GetAsyncKeyState
get_key_state = ctypes.windll.user32.GetKeyState

def smooth_move_mouse(dx: int, dy: int, duration: float):
    def move():
        steps = 5
        step_dx, step_dy = dx // steps, dy // steps
        step_duration = duration / steps
        x = INPUT(type=INPUT_MOUSE, ii=MOUSEINPUT(mouseData=0, dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=None))

        for _ in range(steps):
            x.ii.dx, x.ii.dy = step_dx, step_dy
            send_input(1, ctypes.byref(x), ctypes.sizeof(x))
            time.sleep(step_duration)

    threading.Thread(target=move).start()

def mouse_scroll(amount: int):
    x = INPUT(type=INPUT_MOUSE, ii=MOUSEINPUT(dx=0, dy=0, mouseData=amount, dwFlags=MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=None))
    send_input(1, ctypes.byref(x), ctypes.sizeof(x))

def _mouse_click(down_flag: int, up_flag: int):
    down = INPUT(type=INPUT_MOUSE, ii=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=down_flag, time=0, dwExtraInfo=None))
    up = INPUT(type=INPUT_MOUSE, ii=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=up_flag, time=0, dwExtraInfo=None))
    send_input(1, ctypes.byref(down), ctypes.sizeof(down))
    send_input(1, ctypes.byref(up), ctypes.sizeof(up))

left_mouse_down = lambda: _mouse_click(MOUSEEVENTF_LEFTDOWN, 0)
left_mouse_up = lambda: _mouse_click(0, MOUSEEVENTF_LEFTUP)
right_mouse_down = lambda: _mouse_click(MOUSEEVENTF_RIGHTDOWN, 0)
right_mouse_up = lambda: _mouse_click(0, MOUSEEVENTF_RIGHTUP)

is_numlock_on = lambda: get_key_state(VK_NUMLOCK) & 1 != 0

def mouse_movement():
    numpad_keys = [VK_NUMPAD1, VK_NUMPAD3, VK_NUMPAD5, VK_NUMPAD7, VK_NUMPAD9, VK_NUMPAD2, VK_NUMPAD8, VK_NUMPAD0, VK_NUMPAD4, VK_NUMPAD6]
    control_keys = [VK_LCONTROL, VK_RCONTROL]
    
    numpad_actions: Dict[int, Callable] = {
        VK_NUMPAD1: lambda: smooth_move_mouse(-2 * MOUSE_SENSITIVITY, 0, SMOOTH_MOVE_DURATION),
        VK_NUMPAD3: lambda: smooth_move_mouse(2 * MOUSE_SENSITIVITY, 0, SMOOTH_MOVE_DURATION),
        VK_NUMPAD7: lambda: mouse_scroll(120),
        VK_NUMPAD9: lambda: mouse_scroll(-120),
        VK_NUMPAD5: lambda: (smooth_move_mouse(0, 2000, SMOOTH_MOVE_DURATION), time.sleep(0.1), smooth_move_mouse(0, -580, SMOOTH_MOVE_DURATION)),
        VK_NUMPAD2: lambda: smooth_move_mouse(0, MOUSE_SENSITIVITY, SMOOTH_MOVE_DURATION),
        VK_NUMPAD8: lambda: smooth_move_mouse(0, -MOUSE_SENSITIVITY, SMOOTH_MOVE_DURATION),
        VK_NUMPAD0: lambda: smooth_move_mouse(TURN_AROUND_MOVE, 0, SMOOTH_MOVE_DURATION),
        VK_NUMPAD4: lambda: smooth_move_mouse(-MOUSE_SENSITIVITY, 0, SMOOTH_MOVE_DURATION),
        VK_NUMPAD6: lambda: smooth_move_mouse(MOUSE_SENSITIVITY, 0, SMOOTH_MOVE_DURATION),
    }

    control_actions: Dict[int, Tuple[Callable, Callable]] = {
        VK_LCONTROL: (left_mouse_down, left_mouse_up),
        VK_RCONTROL: (right_mouse_down, right_mouse_up),
    }

    key_states = {key: False for key in numpad_keys + control_keys}

    while True:
        numlock_on = is_numlock_on()

        for key in numpad_keys:
            key_current_state = bool(get_async_key_state(key) & 0x8000)
            if key_current_state and not key_states[key]:
                action = numpad_actions.get(key)
                if action:
                    action()
            key_states[key] = key_current_state

        if numlock_on:
            for key in control_keys:
                key_current_state = bool(get_async_key_state(key) & 0x8000)
                if key_current_state != key_states[key]:
                    down_action, up_action = control_actions.get(key, (None, None))
                    if key_current_state and down_action:
                        down_action()
                    elif not key_current_state and up_action:
                        up_action()
                key_states[key] = key_current_state

if __name__ == "__main__":
    mouse_movement()
