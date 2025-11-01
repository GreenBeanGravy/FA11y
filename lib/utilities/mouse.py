import ctypes
import time
import threading
import os
from typing import Tuple
from lib.utilities.utilities import get_config_int, get_config_float, read_config

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
        
        # Clamp the value to the signed byte range first
        wheel_value = max(-127, min(127, amount))
        
        # Convert the signed value to its unsigned 8-bit equivalent if it's negative
        if wheel_value < 0:
            wheel_value += 256  # e.g., -1 becomes 255, -120 becomes 136
        
        # Set the value using the correct System.Byte type
        wheel_property.SetValue(_mouse_report, _System.Byte(wheel_value))
        
        args = _System.Array[_System.Object]([_mouse_report])
        update_method.Invoke(_faker_input, args)
        
        # Reset wheel position back to 0 using the correct type
        wheel_property.SetValue(_mouse_report, _System.Byte(0))
        return True
    except Exception as e:
        print(f"Mouse scroll error: {e}")
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