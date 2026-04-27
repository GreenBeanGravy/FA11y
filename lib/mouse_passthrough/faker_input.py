"""
FakerInput DLL bridge for sending mouse input through the virtual device driver.
"""

import os
import logging
import threading

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

# Lazy-load gating. Loading the DLL spins up the .NET CoreCLR runtime
# and can spawn a PowerShell process for Unblock-File — together that's
# multi-second work that used to run at module import and stall every
# FA11y startup. Now the work runs at most once, on demand, and can be
# kicked off from a background thread by ``preload_async``.
_load_lock = threading.Lock()
_load_attempted = False  # True after the first ensure_loaded() call.
_load_event = threading.Event()  # Set once load is finished (success or failure).


def _unblock_marker_path(dll_path: str) -> str:
    return dll_path + ".unblocked"


def _maybe_unblock_dll(dll_path: str) -> None:
    """Run Unblock-File once per install, then never again.

    Spawning PowerShell costs ~1-2 s on Windows. Once Unblock-File has
    succeeded it doesn't need to run again — the NTFS Zone.Identifier
    stream is gone. We track that with a sentinel file next to the DLL.
    """
    marker = _unblock_marker_path(dll_path)
    if os.path.exists(marker):
        return
    try:
        import subprocess
        subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command',
             f'Unblock-File -Path "{dll_path}"'],
            capture_output=True, timeout=5,
        )
        try:
            with open(marker, "w", encoding="utf-8") as f:
                f.write("ok")
        except Exception:
            pass
    except Exception:
        pass


def get_cached_int16(value):
    """Get a cached .NET Int16 value. Only caches values within the configured range."""
    if abs(value) <= _cache_range:
        if value not in _net_int16_cache:
            _net_int16_cache[value] = _System.Int16(value)
        return _net_int16_cache[value]
    return _System.Int16(value)


def _load_fakerinput_dll():
    """Load the FakerInput DLL. Caller holds ``_load_lock``."""
    global FAKERINPUT_AVAILABLE, _System, _FakerInputType, _RelativeMouseReportType, _MouseButtonType

    try:
        print("[INFO] Loading FakerInput...")
        import pythonnet
        from pythonnet import set_runtime
        set_runtime("coreclr")
        import clr  # noqa: F401
        import System
        _System = System

        dll_path = os.path.join(os.path.dirname(__file__), "FakerInputWrapper.dll")
        dll_path = os.path.normpath(dll_path)

        if os.path.exists(dll_path):
            _maybe_unblock_dll(dll_path)

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


def ensure_loaded() -> bool:
    """Load the FakerInput DLL on first call. Idempotent + thread-safe."""
    global _load_attempted
    if _load_event.is_set():
        return FAKERINPUT_AVAILABLE
    with _load_lock:
        if _load_event.is_set():
            return FAKERINPUT_AVAILABLE
        if _load_attempted:
            # Another thread is mid-load — wait for it.
            pass
        else:
            _load_attempted = True
            try:
                _load_fakerinput_dll()
            finally:
                _load_event.set()
            return FAKERINPUT_AVAILABLE
    # Another thread is doing it; wait outside the lock.
    _load_event.wait()
    return FAKERINPUT_AVAILABLE


def preload_async() -> threading.Thread:
    """Kick off DLL load on a daemon thread so import-time stays cheap."""
    t = threading.Thread(target=ensure_loaded, name="FakerInputPreload", daemon=True)
    t.start()
    return t


def initialize_fakerinput(cache_range):
    """Initialize FakerInput connection and pre-populate Int16 cache."""
    global _faker_input, _mouse_report, _initialized, _System, FAKERINPUT_AVAILABLE
    global _FakerInputType, _RelativeMouseReportType, _update_method, _reset_method
    global _mouseX_property, _mouseY_property, _cache_range

    ensure_loaded()

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


def send_mouse_button(button_name, is_down, cache_range=100):
    """Send a mouse button press/release through FakerInput.

    Args:
        button_name: Button name (e.g. "LeftButton", "RightButton", "MiddleButton")
        is_down: True for press, False for release
        cache_range: Cache range for initialization if needed
    """
    global _faker_input, _mouse_report, _initialized, _System

    if not _initialized:
        if not initialize_fakerinput(cache_range):
            return False

    try:
        method_name = "ButtonDown" if is_down else "ButtonUp"
        button_method = _RelativeMouseReportType.GetMethod(method_name)

        if button_method:
            button_enum = _System.Enum.Parse(_MouseButtonType, button_name)
            args_array = _System.Array[_System.Object]([button_enum])
            button_method.Invoke(_mouse_report, args_array)

            args = _System.Array[_System.Object]([_mouse_report])
            _update_method.Invoke(_faker_input, args)
            return True
    except Exception as e:
        print(f"[ERROR] Mouse button {button_name} {'down' if is_down else 'up'}: {e}")

    return False


def send_mouse_scroll(amount, cache_range=100):
    """Send a mouse scroll event through FakerInput.

    Args:
        amount: Scroll amount (-127 to 127, negative = scroll down)
        cache_range: Cache range for initialization if needed
    """
    global _faker_input, _mouse_report, _initialized, _System

    if not _initialized:
        if not initialize_fakerinput(cache_range):
            return False

    try:
        wheel_property = _RelativeMouseReportType.GetProperty("WheelPosition")

        wheel_value = max(-127, min(127, amount))
        if wheel_value < 0:
            wheel_value += 256

        wheel_property.SetValue(_mouse_report, _System.Byte(wheel_value))

        args = _System.Array[_System.Object]([_mouse_report])
        _update_method.Invoke(_faker_input, args)

        wheel_property.SetValue(_mouse_report, _System.Byte(0))
        return True
    except Exception as e:
        print(f"[ERROR] Mouse scroll: {e}")
        return False


def is_available():
    """Check if FakerInput is available and loaded."""
    return FAKERINPUT_AVAILABLE


def is_initialized():
    """Check if FakerInput is initialized and connected."""
    return _initialized
