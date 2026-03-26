"""
FakerInput DLL bridge for sending mouse input through the virtual device driver.
"""

import os
import logging

logger = logging.getLogger(__name__)

FAKERINPUT_AVAILABLE = False
_faker_input = None
_mouse_report = None
_initialized = False
_System = None
_FakerInputType = None
_RelativeMouseReportType = None
_MouseButtonType = None

_update_method = None
_reset_method = None
_mouseX_property = None
_mouseY_property = None

_net_int16_cache = {}
_cache_range = 0

def get_cached_int16(value):
    """Get a cached .NET Int16 value. Only caches values within the configured range."""
    if abs(value) <= _cache_range:
        if value not in _net_int16_cache:
            _net_int16_cache[value] = _System.Int16(value)
        return _net_int16_cache[value]
    # Outside cache range — create temporary, don't store
    return _System.Int16(value)


def _load_fakerinput_dll():
    """Load the FakerInput DLL at module import time."""
    global FAKERINPUT_AVAILABLE, _System, _FakerInputType, _RelativeMouseReportType, _MouseButtonType

    try:
        print("[INFO] Loading FakerInput...")
        import pythonnet
        from pythonnet import set_runtime
        set_runtime("coreclr")
        import clr
        import System
        _System = System

        # DLL is at the project root
        dll_path = os.path.join(os.path.dirname(__file__), "..", "..", "FakerInputWrapper.dll")
        dll_path = os.path.normpath(dll_path)

        if os.path.exists(dll_path):
            try:
                import subprocess
                subprocess.run(['powershell', '-Command', f'Unblock-File -Path "{dll_path}"'],
                              capture_output=True, timeout=5)
            except:
                pass

            try:
                _assembly = System.Reflection.Assembly.LoadFrom(dll_path)
                _FakerInputType = _assembly.GetType('FakerInputWrapper.FakerInput')
                _RelativeMouseReportType = _assembly.GetType('FakerInputWrapper.RelativeMouseReport')
                _MouseButtonType = _assembly.GetType('FakerInputWrapper.MouseButton')

                if _FakerInputType and _RelativeMouseReportType and _MouseButtonType:
                    FAKERINPUT_AVAILABLE = True
                    print("[INFO] FakerInput loaded")
                else:
                    print("[ERROR] Failed to get FakerInput types")
            except Exception as e:
                print(f"[ERROR] Error loading FakerInput: {e}")
        else:
            print(f"[ERROR] FakerInputWrapper.dll not found at {dll_path}")

    except ImportError:
        print("[ERROR] pythonnet not available. Install with: pip install pythonnet")
    except Exception as e:
        print(f"[ERROR] FakerInput setup error: {e}")


# Load DLL on import
_load_fakerinput_dll()


def initialize_fakerinput(cache_range):
    """Initialize FakerInput connection and pre-populate Int16 cache."""
    global _faker_input, _mouse_report, _initialized, _System, FAKERINPUT_AVAILABLE
    global _FakerInputType, _RelativeMouseReportType, _update_method, _reset_method
    global _mouseX_property, _mouseY_property, _cache_range

    if not FAKERINPUT_AVAILABLE or not _System or _FakerInputType is None:
        return False

    if _initialized:
        return True

    try:
        _faker_input = _System.Activator.CreateInstance(_FakerInputType)
        _mouse_report = _System.Activator.CreateInstance(_RelativeMouseReportType)

        if _faker_input is None or _mouse_report is None:
            return False

        _update_method = _FakerInputType.GetMethod("UpdateRelativeMouse")
        _reset_method = _RelativeMouseReportType.GetMethod("ResetMousePos")
        _mouseX_property = _RelativeMouseReportType.GetProperty("MouseX")
        _mouseY_property = _RelativeMouseReportType.GetProperty("MouseY")

        connect_method = _FakerInputType.GetMethod("Connect")
        connect_result = connect_method.Invoke(_faker_input, None)

        if connect_result:
            _initialized = True
            _cache_range = cache_range
            print("[INFO] FakerInput connected")

            # Pre-populate cache for the configured range
            for i in range(-cache_range, cache_range + 1):
                get_cached_int16(i)

            return True
        else:
            return False

    except Exception as e:
        print(f"[ERROR] FakerInput initialization: {e}")
        return False


def send_mouse_move(dx, dy, cache_range):
    """Send a relative mouse movement through FakerInput."""
    global _faker_input, _mouse_report, _initialized, _update_method, _reset_method
    global _mouseX_property, _mouseY_property, _System

    if not _initialized:
        if not initialize_fakerinput(cache_range):
            return False

    try:
        MOUSE_MIN, MOUSE_MAX = -32767, 32767
        clamped_x = max(MOUSE_MIN, min(MOUSE_MAX, dx))
        clamped_y = max(MOUSE_MIN, min(MOUSE_MAX, dy))

        net_x = get_cached_int16(clamped_x)
        net_y = get_cached_int16(clamped_y)

        _mouseX_property.SetValue(_mouse_report, net_x)
        _mouseY_property.SetValue(_mouse_report, net_y)

        args = _System.Array[_System.Object]([_mouse_report])
        _update_method.Invoke(_faker_input, args)

        _reset_method.Invoke(_mouse_report, None)

        return True
    except Exception:
        return False


def is_available():
    """Check if FakerInput is available and loaded."""
    return FAKERINPUT_AVAILABLE
