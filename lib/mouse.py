import ctypes
import time
import threading
from typing import Tuple
import configparser
from lib.utilities import get_config_int, get_config_float, get_config_value, get_config_boolean, read_config
from lib.input_handler import is_numlock_on

# Constants
INPUT_MOUSE, MOUSEEVENTF_MOVE, MOUSEEVENTF_WHEEL = 0, 0x0001, 0x0800
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MOVE_NOCOALESCE = 0x2000

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

# Global configuration
config = read_config()

# Mouse movement synchronization
_movement_lock = threading.Lock()
_current_movement_thread = None

def smooth_move_mouse(dx: int, dy: int, step_delay: float, steps: int = None, step_speed: int = None, second_dy: int = None, recenter_delay: float = None):
    global _current_movement_thread
    
    print(f"Smooth moving mouse by dx: {dx}, dy: {dy} MICKEYS, step_delay: {step_delay}, steps: {steps}, step_speed: {step_speed}, second_dy: {second_dy}")
    
    if steps is None:
        steps = get_config_int(config, 'TurnSteps', 5)
    if step_speed is None:
        step_speed = get_config_int(config, 'RecenterStepSpeed', 0)
    
    # Convert milliseconds to seconds for any step_speed value
    step_speed_seconds = step_speed / 1000.0
    
    def move():
        with _movement_lock:
            step_dx, step_dy = dx // steps, dy // steps
            
            for i in range(steps):
                start_time = time.perf_counter()
                
                x = INPUT(type=INPUT_MOUSE, 
                          ii=MOUSEINPUT(dx=step_dx, dy=step_dy, 
                                        mouseData=0, 
                                        dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_MOVE_NOCOALESCE, 
                                        time=0, 
                                        dwExtraInfo=None))
                send_input(1, ctypes.byref(x), ctypes.sizeof(x))
                
                # Use step_delay for normal movements, step_speed for recentering
                if step_speed > 0:
                    elapsed_time = time.perf_counter() - start_time
                    remaining_time = max(0, step_speed_seconds - elapsed_time)
                    if remaining_time > 0:
                        time.sleep(remaining_time)
                else:
                    if step_delay > 0:
                        elapsed_time = time.perf_counter() - start_time
                        remaining_time = max(0, step_delay - elapsed_time)
                        if remaining_time > 0:
                            time.sleep(remaining_time)
                
                print(f"Step {i+1}: Moved by dx: {step_dx}, dy: {step_dy} MICKEYS, duration: {step_speed_seconds:.3f}s")

            if second_dy is not None and recenter_delay is not None:
                if recenter_delay > 0:
                    time.sleep(recenter_delay)
                    
                step_dy = second_dy // steps
                for i in range(steps):
                    start_time = time.perf_counter()
                    
                    x = INPUT(type=INPUT_MOUSE, 
                              ii=MOUSEINPUT(dx=0, dy=step_dy, 
                                            mouseData=0, 
                                            dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_MOVE_NOCOALESCE, 
                                            time=0, 
                                            dwExtraInfo=None))
                    send_input(1, ctypes.byref(x), ctypes.sizeof(x))
                    
                    if step_speed > 0:
                        elapsed_time = time.perf_counter() - start_time
                        remaining_time = max(0, step_speed_seconds - elapsed_time)
                        if remaining_time > 0:
                            time.sleep(remaining_time)
                    else:
                        if step_delay > 0:
                            elapsed_time = time.perf_counter() - start_time
                            remaining_time = max(0, step_delay - elapsed_time)
                            if remaining_time > 0:
                                time.sleep(remaining_time)
                    
                    print(f"Step {i+1} (second movement): Moved by dx: 0, dy: {step_dy} MICKEYS, duration: {step_speed_seconds:.3f}s")

    # Wait for any existing movement to complete before starting new one
    if _current_movement_thread and _current_movement_thread.is_alive():
        _current_movement_thread.join(timeout=0.1)
    
    _current_movement_thread = threading.Thread(target=move, daemon=True)
    _current_movement_thread.start()

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