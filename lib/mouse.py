import ctypes
import time
import threading
from typing import Tuple, Dict, Callable
import configparser

# Constants
VK_NUMLOCK = 0x90
VK_LCONTROL, VK_RCONTROL = 0xA2, 0xA3
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
VK_NUMPAD1, VK_NUMPAD3, VK_NUMPAD5, VK_NUMPAD7, VK_NUMPAD9 = 0x61, 0x63, 0x65, 0x67, 0x69
VK_NUMPAD2, VK_NUMPAD8, VK_NUMPAD0, VK_NUMPAD4, VK_NUMPAD6 = 0x62, 0x68, 0x60, 0x64, 0x66
INPUT_MOUSE, MOUSEEVENTF_MOVE, MOUSEEVENTF_WHEEL = 0, 0x0001, 0x0800
MOUSEEVENTF_MOVE_NOCOALESCE = 0x2000  # New flag for MICKEY movement

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

# Global configuration
config = configparser.ConfigParser()
config.read('config.txt')

def smooth_move_mouse(dx: int, dy: int, duration: float):
    print(f"Smooth moving mouse by dx: {dx}, dy: {dy} MICKEYS, duration: {duration}")
    def move():
        steps = 5
        step_dx, step_dy = dx // steps, dy // steps
        step_duration = duration / steps
        x = INPUT(type=INPUT_MOUSE, 
                  ii=MOUSEINPUT(mouseData=0, 
                                dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_MOVE_NOCOALESCE, 
                                time=0, 
                                dwExtraInfo=None))

        for i in range(steps):
            x.ii.dx, x.ii.dy = step_dx, step_dy
            send_input(1, ctypes.byref(x), ctypes.sizeof(x))
            time.sleep(step_duration)
            print(f"Step {i+1}: Moved by dx: {step_dx}, dy: {step_dy} MICKEYS")

    threading.Thread(target=move).start()

def mouse_scroll(amount: int):
    print(f"Scrolling mouse by amount: {amount}")
    x = INPUT(type=INPUT_MOUSE, ii=MOUSEINPUT(dx=0, dy=0, mouseData=amount, dwFlags=MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=None))
    send_input(1, ctypes.byref(x), ctypes.sizeof(x))

def _mouse_click(down_flag: int, up_flag: int):
    print(f"Mouse click: down_flag: {down_flag}, up_flag: {up_flag}")
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
    print("Starting mouse movement function")
    numpad_keys = [VK_NUMPAD1, VK_NUMPAD3, VK_NUMPAD5, VK_NUMPAD7, VK_NUMPAD9, VK_NUMPAD2, VK_NUMPAD8, VK_NUMPAD0, VK_NUMPAD4, VK_NUMPAD6]
    control_keys = [VK_LCONTROL, VK_RCONTROL]
    
    turn_sensitivity = config.getint('SETTINGS', 'TurnSensitivity', fallback=100)
    secondary_turn_sensitivity = config.getint('SETTINGS', 'SecondaryTurnSensitivity', fallback=50)
    turn_around_sensitivity = config.getint('SETTINGS', 'TurnAroundSensitivity', fallback=1158)
    scroll_amount = config.getint('SETTINGS', 'ScrollAmount', fallback=120)
    recenter_vertical_move = config.getint('SETTINGS', 'RecenterVerticalMove', fallback=2000)
    recenter_vertical_move_back = config.getint('SETTINGS', 'RecenterVerticalMoveBack', fallback=-820)
    secondary_recenter_vertical_move = config.getint('SETTINGS', 'SecondaryRecenterVerticalMove', fallback=2000)
    secondary_recenter_vertical_move_back = config.getint('SETTINGS', 'SecondaryRecenterVerticalMoveBack', fallback=-580)
    smooth_move_duration = config.getfloat('SETTINGS', 'SmoothMoveDuration', fallback=0.01)
    
    numpad_actions: Dict[int, Callable] = {
        VK_NUMPAD1: lambda: smooth_move_mouse(-2 * turn_sensitivity, 0, smooth_move_duration),
        VK_NUMPAD3: lambda: smooth_move_mouse(2 * turn_sensitivity, 0, smooth_move_duration),
        VK_NUMPAD7: lambda: mouse_scroll(scroll_amount),
        VK_NUMPAD9: lambda: mouse_scroll(-scroll_amount),
        VK_NUMPAD5: lambda: (smooth_move_mouse(0, recenter_vertical_move, smooth_move_duration), 
                             time.sleep(0.1), 
                             smooth_move_mouse(0, recenter_vertical_move_back, smooth_move_duration)),
        VK_NUMPAD2: lambda: smooth_move_mouse(0, turn_sensitivity, smooth_move_duration),
        VK_NUMPAD8: lambda: smooth_move_mouse(0, -turn_sensitivity, smooth_move_duration),
        VK_NUMPAD0: lambda: smooth_move_mouse(turn_around_sensitivity, 0, smooth_move_duration),
        VK_NUMPAD4: lambda: smooth_move_mouse(-secondary_turn_sensitivity, 0, smooth_move_duration),
        VK_NUMPAD6: lambda: smooth_move_mouse(secondary_turn_sensitivity, 0, smooth_move_duration),
    }

    control_actions: Dict[int, Tuple[Callable, Callable]] = {
        VK_LCONTROL: (left_mouse_down, left_mouse_up),
        VK_RCONTROL: (right_mouse_down, right_mouse_up),
    }

    key_states = {key: False for key in numpad_keys + control_keys}

    while True:
        numlock_on = is_numlock_on()
        if numlock_on:
            print("Numlock is on")
        else:
            print("Numlock is off")

        for key in numpad_keys:
            key_current_state = bool(get_async_key_state(key) & 0x8000)
            if key_current_state and not key_states[key]:
                print(f"Numpad key pressed: {key}")
                action = numpad_actions.get(key)
                if action:
                    action()
            key_states[key] = key_current_state

        if numlock_on:
            for key in control_keys:
                key_current_state = bool(get_async_key_state(key) & 0x8000)
                if key_current_state != key_states[key]:
                    print(f"Control key state changed: {key}")
                    down_action, up_action = control_actions.get(key, (None, None))
                    if key_current_state and down_action:
                        down_action()
                    elif not key_current_state and up_action:
                        up_action()
                key_states[key] = key_current_state

        time.sleep(0.01)

if __name__ == "__main__":
    print("Starting mouse movement")
    mouse_movement()