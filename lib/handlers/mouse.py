import ctypes
import time
import threading
import os
from typing import Tuple
from lib.utils.utilities import get_config_int, get_config_float, read_config

# Global configuration
config = read_config()

# Mouse movement synchronization
_movement_lock = threading.Lock()
_current_movement_thread = None

# FakerInput globals
FAKERINPUT_AVAILABLE = False
_faker_input = None
_mouse_report = None
_initialized = False
_System = None

# Load FakerInput
try:
    import pythonnet
    from pythonnet import set_runtime
    set_runtime("coreclr")
    import clr
    import System
    _System = System
    
    dll_path = os.path.abspath("FakerInputWrapper.dll")
    if os.path.exists(dll_path):
        try:
            import subprocess
            subprocess.run(['powershell', '-Command', f'Unblock-File -Path "{dll_path}"'], 
                          capture_output=True)
        except:
            pass
        
        _assembly = System.Reflection.Assembly.LoadFrom(dll_path)
        _FakerInputType = _assembly.GetType('FakerInputWrapper.FakerInput')
        _RelativeMouseReportType = _assembly.GetType('FakerInputWrapper.RelativeMouseReport')
        _MouseButtonType = _assembly.GetType('FakerInputWrapper.MouseButton')
        
        if _FakerInputType and _RelativeMouseReportType and _MouseButtonType:
            FAKERINPUT_AVAILABLE = True
except Exception:
    pass

def initialize_fakerinput():
    """Initialize FakerInput"""
    global _faker_input, _mouse_report, _initialized
    
    if not FAKERINPUT_AVAILABLE or _initialized:
        return _initialized
    
    try:
        _faker_input = _System.Activator.CreateInstance(_FakerInputType)
        _mouse_report = _System.Activator.CreateInstance(_RelativeMouseReportType)
        
        connect_method = _FakerInputType.GetMethod("Connect")
        if connect_method.Invoke(_faker_input, None):
            _initialized = True
            print("FakerInput connected successfully")
    except Exception as e:
        print(f"FakerInput initialization failed: {e}")
    
    return _initialized

def _send_mouse_button(button_name, is_down):
    """Internal function to send mouse button events"""
    if not _initialized and not initialize_fakerinput():
        return False
    
    try:
        method_name = "ButtonDown" if is_down else "ButtonUp"
        button_method = _RelativeMouseReportType.GetMethod(method_name)
        
        if button_method:
            button_enum = _System.Enum.Parse(_MouseButtonType, button_name)
            args_array = _System.Array[_System.Object]([button_enum])
            button_method.Invoke(_mouse_report, args_array)
            
            update_method = _FakerInputType.GetMethod("UpdateRelativeMouse")
            update_args = _System.Array[_System.Object]([_mouse_report])
            update_method.Invoke(_faker_input, update_args)
            return True
    except Exception as e:
        print(f"Mouse button {button_name} {method_name} error: {e}")
    
    return False

def smooth_move_mouse(dx: int, dy: int, step_delay: float = 0.01, steps: int = None, step_speed: int = None, second_dy: int = None, recenter_delay: float = None):
    """Move mouse smoothly with steps using FakerInput"""
    global _current_movement_thread
    
    if steps is None:
        steps = get_config_int(config, 'TurnSteps', 5)
    if step_speed is None:
        step_speed = get_config_int(config, 'RecenterStepSpeed', 0)
    
    step_speed_seconds = step_speed / 1000.0
    
    if not FAKERINPUT_AVAILABLE or not (_initialized or initialize_fakerinput()):
        return False
    
    def move():
        with _movement_lock:
            try:
                mousex_property = _RelativeMouseReportType.GetProperty("MouseX")
                mousey_property = _RelativeMouseReportType.GetProperty("MouseY")
                update_method = _FakerInputType.GetMethod("UpdateRelativeMouse")
                
                if steps <= 1:
                    mousex_property.SetValue(_mouse_report, _System.Int16(dx))
                    mousey_property.SetValue(_mouse_report, _System.Int16(dy))
                    args = _System.Array[_System.Object]([_mouse_report])
                    update_method.Invoke(_faker_input, args)
                    return
                
                step_x = dx / steps
                step_y = dy / steps
                
                for i in range(steps):
                    start_time = time.perf_counter()
                    
                    if i == steps - 1:
                        final_x = dx - int(step_x * i)
                        final_y = dy - int(step_y * i)
                        mousex_property.SetValue(_mouse_report, _System.Int16(final_x))
                        mousey_property.SetValue(_mouse_report, _System.Int16(final_y))
                    else:
                        mousex_property.SetValue(_mouse_report, _System.Int16(int(step_x)))
                        mousey_property.SetValue(_mouse_report, _System.Int16(int(step_y)))
                    
                    args = _System.Array[_System.Object]([_mouse_report])
                    update_method.Invoke(_faker_input, args)
                    
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
                            mousex_property.SetValue(_mouse_report, _System.Int16(0))
                            mousey_property.SetValue(_mouse_report, _System.Int16(final_y))
                        else:
                            mousex_property.SetValue(_mouse_report, _System.Int16(0))
                            mousey_property.SetValue(_mouse_report, _System.Int16(step_dy))
                        
                        args = _System.Array[_System.Object]([_mouse_report])
                        update_method.Invoke(_faker_input, args)
                        
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
    """Scroll mouse wheel"""
    if not _initialized and not initialize_fakerinput():
        return False
    
    try:
        wheel_property = _RelativeMouseReportType.GetProperty("WheelPosition")
        update_method = _FakerInputType.GetMethod("UpdateRelativeMouse")
        
        wheel_value = max(-127, min(127, amount))
        wheel_property.SetValue(_mouse_report, _System.SByte(wheel_value))
        
        args = _System.Array[_System.Object]([_mouse_report])
        update_method.Invoke(_faker_input, args)
        
        # Reset wheel position
        wheel_property.SetValue(_mouse_report, _System.SByte(0))
        return True
    except Exception as e:
        print(f"Mouse scroll error: {e}")
        return False

# Core mouse button functions
_BUTTON_MAP = {
    'left': 'LeftButton',
    'right': 'RightButton',
    'middle': 'MiddleButton'
}


def mouse_button_down(button: str = 'left') -> bool:
    """Press and hold a mouse button."""
    btn = _BUTTON_MAP.get(button.lower())
    if not btn:
        raise ValueError(f"Unsupported mouse button: {button}")
    return _send_mouse_button(btn, True)


def mouse_button_up(button: str = 'left') -> bool:
    """Release a mouse button."""
    btn = _BUTTON_MAP.get(button.lower())
    if not btn:
        raise ValueError(f"Unsupported mouse button: {button}")
    return _send_mouse_button(btn, False)


def click_mouse(button: str = 'left') -> None:
    """Click mouse button with brief delay."""
    mouse_button_down(button)
    time.sleep(0.01)
    mouse_button_up(button)


def hold_mouse_button(button: str = 'left') -> bool:
    """Hold down mouse button."""
    return mouse_button_down(button)


def release_mouse_button(button: str = 'left') -> bool:
    """Release mouse button."""
    return mouse_button_up(button)


# Compatibility aliases
left_mouse_down = lambda: mouse_button_down('left')
left_mouse_up = lambda: mouse_button_up('left')
right_mouse_down = lambda: mouse_button_down('right')
right_mouse_up = lambda: mouse_button_up('right')
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
