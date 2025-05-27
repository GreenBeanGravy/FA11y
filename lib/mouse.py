import ctypes
import time
import threading
import os
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

# FakerInput Implementation
# Try to load FakerInput via .NET - minimized output
FAKERINPUT_AVAILABLE = False
_faker_input = None
_mouse_report = None
_initialized = False
_System = None

try:
    # Load .NET with minimal output
    import pythonnet
    from pythonnet import set_runtime
    set_runtime("coreclr")
    import clr
    import System
    _System = System
    
    # Load the DLL silently
    dll_path = os.path.abspath("FakerInputWrapper.dll")
    
    if os.path.exists(dll_path):
        # Unblock the DLL silently
        try:
            import subprocess
            subprocess.run(['powershell', '-Command', f'Unblock-File -Path "{dll_path}"'], 
                          capture_output=True)
        except:
            pass
        
        # Load assembly
        _assembly = System.Reflection.Assembly.LoadFrom(dll_path)
        _FakerInputType = _assembly.GetType('FakerInputWrapper.FakerInput')
        _RelativeMouseReportType = _assembly.GetType('FakerInputWrapper.RelativeMouseReport')
        _MouseButtonType = _assembly.GetType('FakerInputWrapper.MouseButton')
        
        if _FakerInputType and _RelativeMouseReportType and _MouseButtonType:
            FAKERINPUT_AVAILABLE = True
except Exception:
    pass  # Silently fail if FakerInput can't be loaded

def initialize_fakerinput():
    """Initialize FakerInput silently"""
    global _faker_input, _mouse_report, _initialized, _System
    
    if not FAKERINPUT_AVAILABLE or not _System:
        return False
    
    if _initialized:
        return True
    
    try:
        # Create instances with minimal output
        try:
            _faker_input = _System.Activator.CreateInstance(_FakerInputType)
            _mouse_report = _System.Activator.CreateInstance(_RelativeMouseReportType)
        except:
            empty_args = _System.Array[_System.Object]([])
            _faker_input = _System.Activator.CreateInstance(_FakerInputType, empty_args)
            _mouse_report = _System.Activator.CreateInstance(_RelativeMouseReportType, empty_args)
        
        if _faker_input is None or _mouse_report is None:
            return False
        
        # Connect
        connect_method = _FakerInputType.GetMethod("Connect")
        connect_result = connect_method.Invoke(_faker_input, None)
        
        if connect_result:
            _initialized = True
            print("FakerInput connected successfully")
            return True
        else:
            return False
            
    except:
        return False

def send_faker_mouse_move(dx, dy):
    """Send mouse movement using FakerInput silently"""
    global _faker_input, _mouse_report, _System
    
    if not _initialized:
        if not initialize_fakerinput():
            return False
    
    try:
        # Constants from DS4Windows
        MOUSE_MIN = -32767
        MOUSE_MAX = 32767
        
        # Clamp values
        clamped_x = dx if MOUSE_MIN <= dx <= MOUSE_MAX else (MOUSE_MIN if dx < MOUSE_MIN else MOUSE_MAX)
        clamped_y = dy if MOUSE_MIN <= dy <= MOUSE_MAX else (MOUSE_MIN if dy < MOUSE_MIN else MOUSE_MAX)
        
        # Set mouse values
        mouseX_property = _RelativeMouseReportType.GetProperty("MouseX")
        mouseY_property = _RelativeMouseReportType.GetProperty("MouseY")
        
        # Create proper .NET Int16 values
        net_x = _System.Int16(clamped_x)
        net_y = _System.Int16(clamped_y)
        
        mouseX_property.SetValue(_mouse_report, net_x)
        mouseY_property.SetValue(_mouse_report, net_y)
        
        # Update the mouse
        update_method = _FakerInputType.GetMethod("UpdateRelativeMouse")
        args = _System.Array[_System.Object]([_mouse_report])
        update_method.Invoke(_faker_input, args)
        
        # Reset position
        reset_method = _RelativeMouseReportType.GetMethod("ResetMousePos")
        reset_method.Invoke(_mouse_report, None)
        
        return True
    except:
        return False

def smooth_move_mouse(dx: int, dy: int, step_delay: float = 0.01, steps: int = None, step_speed: int = None, second_dy: int = None, recenter_delay: float = None):
    """
    Move mouse smoothly with steps. Tries FakerInput first, falls back to standard input.
    """
    global _current_movement_thread
    
    if steps is None:
        steps = get_config_int(config, 'TurnSteps', 5)
    if step_speed is None:
        step_speed = get_config_int(config, 'RecenterStepSpeed', 0)
    
    # Convert milliseconds to seconds for any step_speed value
    step_speed_seconds = step_speed / 1000.0
    
    # If FakerInput is available and initialized, use it
    if FAKERINPUT_AVAILABLE and (_initialized or initialize_fakerinput()):
        if steps <= 1:
            return send_faker_mouse_move(dx, dy)
        
        # Calculate increments
        step_x = dx / steps
        step_y = dy / steps
        
        success = True
        for i in range(steps):
            # For the last step, use exact remaining distance to avoid rounding errors
            if i == steps - 1:
                final_x = dx - int(step_x * i)
                final_y = dy - int(step_y * i)
                if not send_faker_mouse_move(final_x, final_y):
                    success = False
            else:
                if not send_faker_mouse_move(int(step_x), int(step_y)):
                    success = False
            
            if step_delay > 0:
                time.sleep(step_delay)
        
        # Handle second movement if needed
        if second_dy is not None and recenter_delay is not None:
            if recenter_delay > 0:
                time.sleep(recenter_delay)
                
            step_dy = second_dy // steps
            for i in range(steps):
                if i == steps - 1:
                    final_y = second_dy - (step_dy * i)
                    send_faker_mouse_move(0, final_y)
                else:
                    send_faker_mouse_move(0, step_dy)
                
                if step_delay > 0:
                    time.sleep(step_delay)
        
        return success
    
    # Otherwise use standard Windows input method
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

    # Wait for any existing movement to complete before starting new one
    if _current_movement_thread and _current_movement_thread.is_alive():
        _current_movement_thread.join(timeout=0.1)
    
    _current_movement_thread = threading.Thread(target=move, daemon=True)
    _current_movement_thread.start()

def mouse_scroll(amount: int):
    """Scroll mouse wheel"""
    x = INPUT(type=INPUT_MOUSE, ii=MOUSEINPUT(dx=0, dy=0, mouseData=amount, dwFlags=MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=None))
    send_input(1, ctypes.byref(x), ctypes.sizeof(x))

def _mouse_click(down_flag: int, up_flag: int):
    """Internal mouse click implementation"""
    down = INPUT(type=INPUT_MOUSE, ii=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=down_flag, time=0, dwExtraInfo=None))
    up = INPUT(type=INPUT_MOUSE, ii=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=up_flag, time=0, dwExtraInfo=None))
    send_input(1, ctypes.byref(down), ctypes.sizeof(down))
    send_input(1, ctypes.byref(up), ctypes.sizeof(up))

# Mouse control functions
left_mouse_down = lambda: _mouse_click(MOUSEEVENTF_LEFTDOWN, 0)
left_mouse_up = lambda: _mouse_click(0, MOUSEEVENTF_LEFTUP)
right_mouse_down = lambda: _mouse_click(MOUSEEVENTF_RIGHTDOWN, 0)
right_mouse_up = lambda: _mouse_click(0, MOUSEEVENTF_RIGHTUP)

# Additional mouse functions to maintain compatibility
def move_mouse_relative(dx, dy):
    """Move mouse relative to current position using smooth_move_mouse"""
    return smooth_move_mouse(dx, dy, step_delay=0.01, steps=1)

def get_mouse_position():
    """Get current mouse position"""
    user32 = ctypes.windll.user32
    pt = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)

def click_mouse(button='left'):
    """Click mouse button"""
    if button == 'left':
        _mouse_click(MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
    elif button == 'right':
        _mouse_click(MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)

def hold_mouse_button(button='left'):
    """Hold down mouse button"""
    if button == 'left':
        _mouse_click(MOUSEEVENTF_LEFTDOWN, 0)
    elif button == 'right':
        _mouse_click(MOUSEEVENTF_RIGHTDOWN, 0)

def release_mouse_button(button='left'):
    """Release mouse button"""
    if button == 'left':
        _mouse_click(0, MOUSEEVENTF_LEFTUP)
    elif button == 'right':
        _mouse_click(0, MOUSEEVENTF_RIGHTUP)

# Alias functions
left_click = lambda: click_mouse('left')
right_click = lambda: click_mouse('right')
