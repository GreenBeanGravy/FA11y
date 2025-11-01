#!/usr/bin/env python3
"""
Optimized Mouse Passthrough Service - High Performance 1000Hz
Optimized for minimal latency and maximum throughput at 1000Hz polling
Run as Administrator for best results
"""

import sys
import ctypes
import ctypes.wintypes
from ctypes import wintypes, Structure, POINTER, byref, windll, c_void_p
import threading
import time
import json
import signal
import os
import traceback
from typing import Optional, Callable, Deque
from dataclasses import dataclass, asdict
from collections import deque

# Windows constants
HC_ACTION = 0
WH_MOUSE_LL = 14
LLMHF_INJECTED = 1
WM_QUIT = 0x0012

# Mouse message constants
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A

# Raw Input constants
WM_INPUT = 0x00FF
RIM_TYPEMOUSE = 0
RIDEV_INPUTSINK = 0x00000100
RIDEV_REMOVE = 0x00000001
RIDI_DEVICENAME = 0x20000007
PM_REMOVE = 0x0001

# Raw mouse flags
MOUSE_MOVE_RELATIVE = 0

LPVOID = ctypes.c_void_p
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
LRESULT = ctypes.c_int64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_int32

# Hook procedure type
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

def is_admin():
    """Simple admin check"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

# Optimized FakerInput Implementation
FAKERINPUT_AVAILABLE = False
_faker_input = None
_mouse_report = None
_initialized = False
_System = None
_FakerInputType = None
_RelativeMouseReportType = None
_MouseButtonType = None

# Cache method references for performance
_update_method = None
_reset_method = None
_mouseX_property = None
_mouseY_property = None

# Pre-allocated .NET objects for performance
_net_int16_cache = {}

def get_cached_int16(value):
    """Get cached .NET Int16 to avoid repeated allocations"""
    if value not in _net_int16_cache:
        _net_int16_cache[value] = _System.Int16(value)
    return _net_int16_cache[value]

try:
    print("[INFO] Loading FakerInput components...")
    import pythonnet
    from pythonnet import set_runtime
    set_runtime("coreclr")
    import clr
    import System
    _System = System

    dll_path = os.path.join(os.path.dirname(__file__), "FakerInputWrapper.dll")
    
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
                print("[INFO] FakerInput loaded successfully")
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

def initialize_fakerinput():
    global _faker_input, _mouse_report, _initialized, _System, FAKERINPUT_AVAILABLE
    global _FakerInputType, _RelativeMouseReportType, _update_method, _reset_method
    global _mouseX_property, _mouseY_property

    if not FAKERINPUT_AVAILABLE or not _System or _FakerInputType is None:
        print("[ERROR] FakerInput not available")
        return False
    
    if _initialized:
        return True
    
    try:
        # Create instances
        _faker_input = _System.Activator.CreateInstance(_FakerInputType)
        _mouse_report = _System.Activator.CreateInstance(_RelativeMouseReportType)

        if _faker_input is None or _mouse_report is None:
            print("[ERROR] Failed to create FakerInput instances")
            return False
        
        # Cache method references for performance
        _update_method = _FakerInputType.GetMethod("UpdateRelativeMouse")
        _reset_method = _RelativeMouseReportType.GetMethod("ResetMousePos")
        _mouseX_property = _RelativeMouseReportType.GetProperty("MouseX")
        _mouseY_property = _RelativeMouseReportType.GetProperty("MouseY")
        
        # Connect FakerInput
        connect_method = _FakerInputType.GetMethod("Connect")
        connect_result = connect_method.Invoke(_faker_input, None)
        
        if connect_result:
            _initialized = True
            print("[INFO] FakerInput connected and optimized")
            
            # Pre-cache common values
            for i in range(-100, 101):
                get_cached_int16(i)
            
            return True
        else:
            print("[ERROR] FakerInput connection failed")
            return False
            
    except Exception as e:
        print(f"[ERROR] FakerInput initialization error: {e}")
        return False

def send_faker_mouse_move_optimized(dx, dy):
    """Optimized FakerInput mouse move with minimal allocations"""
    global _faker_input, _mouse_report, _initialized, _update_method, _reset_method
    global _mouseX_property, _mouseY_property, _System
    
    if not _initialized:
        if not initialize_fakerinput():
            return False
    
    try:
        # Fast clamping
        MOUSE_MIN, MOUSE_MAX = -32767, 32767
        clamped_x = max(MOUSE_MIN, min(MOUSE_MAX, dx))
        clamped_y = max(MOUSE_MIN, min(MOUSE_MAX, dy))
        
        # Use cached .NET Int16 objects
        net_x = get_cached_int16(clamped_x) if abs(clamped_x) <= 100 else _System.Int16(clamped_x)
        net_y = get_cached_int16(clamped_y) if abs(clamped_y) <= 100 else _System.Int16(clamped_y)
        
        # Fast property setting
        _mouseX_property.SetValue(_mouse_report, net_x)
        _mouseY_property.SetValue(_mouse_report, net_y)
        
        # Pre-allocated args array
        args = _System.Array[_System.Object]([_mouse_report])
        _update_method.Invoke(_faker_input, args)
        
        # Reset for next use
        _reset_method.Invoke(_mouse_report, None)
        
        return True
    except Exception as e:
        print(f"[ERROR] Optimized mouse move error: {e}")
        return False

# Windows structures
class POINT(Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class MSG(Structure):
    _fields_ = [
        ('hwnd', wintypes.HWND),
        ('message', wintypes.UINT),
        ('wParam', wintypes.WPARAM),
        ('lParam', wintypes.LPARAM),
        ('time', wintypes.DWORD),
        ('pt', POINT)
    ]

class MSLLHOOKSTRUCT(Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.DWORD)
    ]

class RAWINPUTDEVICE(Structure):
    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND)
    ]

class RAWINPUTHEADER(Structure):
    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM)
    ]

class RAWMOUSE(Structure):
    _fields_ = [
        ("usFlags", wintypes.USHORT),
        ("usButtonFlags", wintypes.USHORT),
        ("usButtonData", wintypes.USHORT),
        ("ulRawButtons", wintypes.ULONG),
        ("lLastX", wintypes.LONG),
        ("lLastY", wintypes.LONG),
        ("ulExtraInformation", wintypes.ULONG)
    ]

class RAWINPUT(Structure):
    _fields_ = [
        ("header", RAWINPUTHEADER),
        ("mouse", RAWMOUSE)
    ]

class WNDCLASSW(Structure):
    _fields_ = [
        ('style', wintypes.UINT),
        ('lpfnWndProc', WNDPROC),
        ('cbClsExtra', ctypes.c_int),
        ('cbWndExtra', ctypes.c_int),
        ('hInstance', wintypes.HINSTANCE),
        ('hIcon', wintypes.HICON),
        ('hCursor', wintypes.HANDLE),
        ('hbrBackground', wintypes.HBRUSH),
        ('lpszMenuName', wintypes.LPCWSTR),
        ('lpszClassName', wintypes.LPCWSTR)
    ]

# --- FIX START: Define WinAPI function prototypes for ctypes ---
# This prevents OverflowError on 64-bit systems by explicitly telling ctypes
# the expected argument and return types for each function.
user32 = windll.user32
kernel32 = windll.kernel32

user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

user32.GetRawInputData.restype = wintypes.UINT
user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, LPVOID, POINTER(wintypes.UINT), wintypes.UINT]

user32.GetRawInputDeviceInfoW.restype = wintypes.UINT
user32.GetRawInputDeviceInfoW.argtypes = [wintypes.HANDLE, wintypes.UINT, LPVOID, POINTER(wintypes.UINT)]

user32.RegisterRawInputDevices.restype = wintypes.BOOL
user32.RegisterRawInputDevices.argtypes = [POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]

user32.RegisterClassW.restype = wintypes.ATOM
user32.RegisterClassW.argtypes = [POINTER(WNDCLASSW)]

user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, LPVOID
]

user32.GetMessageW.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]

user32.PeekMessageW.restype = wintypes.BOOL
user32.PeekMessageW.argtypes = [POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]

user32.TranslateMessage.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [POINTER(MSG)]

user32.DispatchMessageW.restype = LRESULT
user32.DispatchMessageW.argtypes = [POINTER(MSG)]

user32.DestroyWindow.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = [wintypes.HWND]

user32.PostMessageW.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

user32.UnregisterClassW.restype = wintypes.BOOL
user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]

kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

kernel32.GetLastError.restype = wintypes.DWORD
kernel32.GetLastError.argtypes = []
# --- FIX END ---


@dataclass
class MouseDevice:
    handle_value: int
    friendly_name: str
    vendor_id: str = "0000"
    product_id: str = "0000" 
    device_path: str = ""
    dpi: int = 1600
    _dpi_scale: float = 1.0  # Cached DPI scale

    def __post_init__(self):
        self.update_dpi_scale()

    def update_dpi_scale(self):
        """Pre-calculate DPI scaling factor"""
        self._dpi_scale = self.dpi / 800.0

    @property
    def handle(self) -> wintypes.HANDLE:
        return ctypes.c_void_p(self.handle_value)

class OptimizedRawInputCapture:
    """High-performance Raw Input capture optimized for 1000Hz"""
    
    def __init__(self, target_device, movement_callback):
        self.target_device = target_device
        self.movement_callback = movement_callback
        self.running = False
        self.window_handle = None
        self.capture_thread = None
        self._wndproc = None
        
        # Pre-allocate buffer for raw input
        self.buffer_size = 256
        self.raw_buffer = ctypes.create_string_buffer(self.buffer_size)
        self.size_holder = wintypes.UINT(self.buffer_size)
        
    def window_proc(self, hwnd, msg, wparam, lparam):
        """Optimized window procedure"""
        try:
            if msg == WM_INPUT and self.running:
                # Fast path - reuse pre-allocated buffer
                self.size_holder.value = self.buffer_size
                hraw = wintypes.HANDLE(lparam)
                
                result = user32.GetRawInputData(
                    hraw, 0x10000003, self.raw_buffer, 
                    byref(self.size_holder), ctypes.sizeof(RAWINPUTHEADER)
                )
                
                if result > 0:
                    raw_input = ctypes.cast(self.raw_buffer, POINTER(RAWINPUT)).contents
                    if raw_input.header.dwType == RIM_TYPEMOUSE:
                        # Fast handle comparison
                        current_handle = int(ctypes.cast(raw_input.header.hDevice, ctypes.c_void_p).value or 0)
                        if current_handle == self.target_device.handle_value:
                            # Process relative movement immediately
                            if raw_input.mouse.usFlags == MOUSE_MOVE_RELATIVE:
                                raw_dx = raw_input.mouse.lLastX
                                raw_dy = raw_input.mouse.lLastY
                                
                                if raw_dx != 0 or raw_dy != 0:
                                    # Immediate processing for lowest latency
                                    self.movement_callback(raw_dx, raw_dy)
        except:
            pass  # Minimize exception handling overhead in hot path
        
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
    
    def start_capture(self):
        """Start high-performance capture"""
        if self.running:
            return True
            
        self.running = True
        self.capture_thread = threading.Thread(target=self._capture_worker, daemon=True)
        self.capture_thread.start()
        time.sleep(0.05)  # Reduced wait time
        return self.window_handle is not None
    
    def _capture_worker(self):
        """Optimized capture worker"""
        try:
            # Create window class
            wndclass = WNDCLASSW()
            self._wndproc = WNDPROC(self.window_proc)
            wndclass.lpfnWndProc = self._wndproc
            wndclass.lpszClassName = "FastRawInput"
            wndclass.hInstance = kernel32.GetModuleHandleW(None)

            if not user32.RegisterClassW(byref(wndclass)):
                if kernel32.GetLastError() != 1410: # ERROR_CLASS_ALREADY_EXISTS
                    return

            # Create window
            self.window_handle = user32.CreateWindowExW(
                0, "FastRawInput", "FastRaw", 0, 0, 0, 0, 0,
                None, None, wndclass.hInstance, None
            )
            
            if not self.window_handle:
                return

            # Register for raw input
            rid = RAWINPUTDEVICE()
            rid.usUsagePage = 0x01
            rid.usUsage = 0x02
            rid.dwFlags = RIDEV_INPUTSINK
            rid.hwndTarget = self.window_handle

            if not user32.RegisterRawInputDevices(byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE)):
                return

            print("[INFO] High-performance raw input capture active")

            # Ultra-fast message loop - no sleep, minimal overhead
            msg = MSG()
            while self.running:
                bRet = user32.GetMessageW(byref(msg), self.window_handle, 0, 0)
                if bRet <= 0:
                    break
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))

        except Exception as e:
            print(f"[ERROR] Capture worker error: {e}")
        finally:
            self._cleanup()

    def _cleanup(self):
        """Fast cleanup"""
        try:
            if self.window_handle:
                rid = RAWINPUTDEVICE()
                rid.usUsagePage = 0x01
                rid.usUsage = 0x02
                rid.dwFlags = RIDEV_REMOVE
                rid.hwndTarget = None
                user32.RegisterRawInputDevices(byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE))
                user32.DestroyWindow(self.window_handle)
                self.window_handle = None
            user32.UnregisterClassW("FastRawInput", kernel32.GetModuleHandleW(None))
        except:
            pass

    def stop_capture(self):
        """Stop capture"""
        if not self.running:
            return
            
        self.running = False
        if self.window_handle:
            user32.PostMessageW(self.window_handle, WM_QUIT, 0, 0)
        
        if self.capture_thread:
            self.capture_thread.join(timeout=1.0)

class HighPerformanceMouseHook:
    """Ultra-optimized mouse hook for 1000Hz performance"""
    
    def __init__(self):
        self.target_device: Optional[MouseDevice] = None
        self.raw_input_capture = None
        
        # High-performance counters
        self.total_movements = 0
        self.total_clicks = 0
        self.total_scrolls = 0
        
        # Use deque for O(1) operations
        self.recent_movements: Deque = deque(maxlen=100)
        self.recent_outputs: Deque = deque(maxlen=50)
        
        # Performance tracking
        self.last_perf_time = time.perf_counter()
        self.movements_since_last = 0
        
        # Initialize optimized FakerInput
        initialize_fakerinput()
        
    def process_raw_mouse_movement(self, raw_dx, raw_dy):
        """Ultra-fast movement processing"""
        if not self.target_device:
            return
            
        # Pre-calculated DPI scaling (no division in hot path)
        scaled_dx = int(raw_dx * self.target_device._dpi_scale)
        scaled_dy = int(raw_dy * self.target_device._dpi_scale)
        
        if scaled_dx != 0 or scaled_dy != 0:
            # Optimized FakerInput call
            if send_faker_mouse_move_optimized(scaled_dx, scaled_dy):
                # Fast counter updates
                self.total_movements += 1
                self.movements_since_last += 1
                
                # Minimal logging data (only store essentials)
                if len(self.recent_movements) < 50:  # Limit to reduce overhead
                    self.recent_movements.append((raw_dx, raw_dy, scaled_dx, scaled_dy))
                
                if len(self.recent_outputs) < 25:
                    self.recent_outputs.append(f"M({scaled_dx},{scaled_dy})")
    
    def start_hook(self):
        """Start optimized hook"""
        if not self.target_device:
            print("[ERROR] No target device")
            return False
        
        print("[INFO] Starting high-performance capture...")
        
        # Create optimized raw input capture
        self.raw_input_capture = OptimizedRawInputCapture(
            self.target_device, 
            self.process_raw_mouse_movement
        )
        
        if self.raw_input_capture.start_capture():
            print("[SUCCESS] High-performance mode active")
            return True
        else:
            print("[ERROR] Failed to start capture")
            return False
    
    def stop_hook(self):
        """Stop hook"""
        if self.raw_input_capture:
            self.raw_input_capture.stop_capture()
            self.raw_input_capture = None
    
    def get_performance_stats(self):
        """Get performance statistics"""
        current_time = time.perf_counter()
        elapsed = current_time - self.last_perf_time
        
        if elapsed >= 1.0:
            movements_per_sec = self.movements_since_last / elapsed
            self.movements_since_last = 0
            self.last_perf_time = current_time
            return movements_per_sec
        return 0

class OptimizedMousePassthrough:
    def __init__(self):
        self.target_device: Optional[MouseDevice] = None
        self.running = False
        self.mouse_hook = HighPerformanceMouseHook()
        self.log_thread = None
        self.heartbeat_thread = None
        self.last_log_time = time.perf_counter()
        
        # Check admin privileges
        if is_admin():
            print("[INFO] Running with Administrator privileges")
        else:
            print("[WARNING] NOT running as Administrator")
        
        # Load config
        self.load_config()
        
    def get_device_name(self, device_handle) -> Optional[str]:
        """Get device name from handle"""
        try:
            size = wintypes.UINT(0)
            user32.GetRawInputDeviceInfoW(device_handle, RIDI_DEVICENAME, None, byref(size))
            if size.value == 0:
                return None
            buf = ctypes.create_unicode_buffer(size.value)
            result = user32.GetRawInputDeviceInfoW(device_handle, RIDI_DEVICENAME, buf, byref(size))
            if result > 0:
                return buf.value
        except:
            pass
        return None

    def parse_device_path(self, device_path: str) -> tuple[str, str]:
        """Parse VID/PID from device path"""
        vid, pid = "0000", "0000"
        try:
            path_upper = device_path.upper()
            if "VID_" in path_upper:
                vid_start = path_upper.find("VID_") + 4
                vid = path_upper[vid_start:vid_start + 4]
            if "PID_" in path_upper:
                pid_start = path_upper.find("PID_") + 4
                pid = path_upper[pid_start:pid_start + 4]
        except:
            pass
        return vid, pid

    def get_friendly_name(self, device_path: str) -> str:
        """Generate friendly name"""
        vid, pid = self.parse_device_path(device_path)
        brands = {"1532": "Razer", "046D": "Logitech", "1B1C": "Corsair", "1038": "SteelSeries"}
        brand = brands.get(vid, "Gaming" if vid != "0000" else "Generic")
        return f"{brand} Mouse ({vid}:{pid})"

    def detect_active_mouse(self) -> Optional[MouseDevice]:
        """Fast and robust mouse detection."""
        print("Move your mouse to detect... (10 sec timeout)")

        detected_device = None
        detection_complete = threading.Event()

        def window_proc(hwnd, msg, wparam, lparam):
            nonlocal detected_device
            try:
                if msg == WM_INPUT:
                    size = wintypes.UINT(48) # Size of RAWINPUT struct
                    buffer = ctypes.create_string_buffer(size.value)
                    hraw = wintypes.HANDLE(lparam)
                    
                    result = user32.GetRawInputData(hraw, 0x10000003, buffer, byref(size), ctypes.sizeof(RAWINPUTHEADER))
                    if result > 0:
                        raw_input = ctypes.cast(buffer, POINTER(RAWINPUT)).contents
                        if raw_input.header.dwType == RIM_TYPEMOUSE:
                            device_handle = raw_input.header.hDevice
                            device_path = self.get_device_name(device_handle)
                            if device_path:
                                vid, pid = self.parse_device_path(device_path)
                                friendly_name = self.get_friendly_name(device_path)
                                handle_value = int(ctypes.cast(device_handle, ctypes.c_void_p).value or 0)
                                detected_device = MouseDevice(
                                    handle_value=handle_value,
                                    friendly_name=friendly_name,
                                    vendor_id=vid,
                                    product_id=pid,
                                    device_path=device_path,
                                    dpi=1600
                                )
                                print(f"Detected: {friendly_name}")
                                detection_complete.set()
            except Exception:
                pass
            
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        # Keep a reference to WNDPROC to prevent garbage collection
        det_wndproc = WNDPROC(window_proc)
        
        wndclass = WNDCLASSW()
        wndclass.lpfnWndProc = det_wndproc
        wndclass.lpszClassName = "MouseDetector"
        wndclass.hInstance = kernel32.GetModuleHandleW(None)

        hwnd = None
        try:
            if not user32.RegisterClassW(byref(wndclass)):
                if kernel32.GetLastError() != 1410: # ERROR_CLASS_ALREADY_EXISTS
                    print("[ERROR] Could not register window class for detection.")
                    return None

            hwnd = user32.CreateWindowExW(
                0, wndclass.lpszClassName, "Detector", 0, 0, 0, 0, 0,
                None, None, wndclass.hInstance, None
            )
            if not hwnd:
                print("[ERROR] Could not create window for detection.")
                return None

            rid = RAWINPUTDEVICE()
            rid.usUsagePage = 0x01
            rid.usUsage = 0x02
            rid.dwFlags = RIDEV_INPUTSINK
            rid.hwndTarget = hwnd

            if not user32.RegisterRawInputDevices(byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE)):
                print("[ERROR] Could not register for raw mouse input.")
                return None

            # --- FIX: Flush any pending mouse input messages before starting ---
            msg = MSG()
            while user32.PeekMessageW(byref(msg), hwnd, WM_INPUT, WM_INPUT, PM_REMOVE):
                pass # Discard old messages

            start_time = time.perf_counter()
            timeout = 10.0
            while not detection_complete.is_set():
                if time.perf_counter() - start_time >= timeout:
                    break
                
                if user32.PeekMessageW(byref(msg), hwnd, 0, 0, PM_REMOVE):
                    user32.TranslateMessage(byref(msg))
                    user32.DispatchMessageW(byref(msg))
                else:
                    time.sleep(0.001)

            return detected_device

        except Exception as e:
            print(f"Detection error: {e}")
            return None
        finally:
            # --- FIX: Guaranteed cleanup to allow repeated calls ---
            if hwnd:
                rid = RAWINPUTDEVICE()
                rid.usUsagePage = 0x01
                rid.usUsage = 0x02
                rid.dwFlags = RIDEV_REMOVE
                rid.hwndTarget = None
                user32.RegisterRawInputDevices(byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE))
                user32.DestroyWindow(hwnd)
            
            user32.UnregisterClassW(wndclass.lpszClassName, wndclass.hInstance)

    def configure_dpi(self):
        """Configure DPI"""
        if not self.target_device:
            print("No mouse configured")
            return
        print(f"Current DPI: {self.target_device.dpi}")
        try:
            new_dpi = int(input("Enter DPI (100-20000): "))
            if 100 <= new_dpi <= 20000:
                self.target_device.dpi = new_dpi
                self.target_device.update_dpi_scale()  # Update cached scale
                self.mouse_hook.target_device = self.target_device
                self.save_config()
                print(f"DPI set to {new_dpi}")
            else:
                print("DPI must be 100-20000")
        except (ValueError, KeyboardInterrupt):
            print("Invalid input")

    def log_worker(self):
        """Optimized logging thread"""
        while self.running:
            try:
                time.sleep(1.0)  # Faster logging for 1000Hz monitoring
                if self.running:
                    current_time = time.perf_counter()
                    elapsed = current_time - self.last_log_time
                    
                    if elapsed >= 1.0:
                        movements = self.mouse_hook.total_movements
                        performance = self.mouse_hook.get_performance_stats()
                        
                        if movements > 0:
                            print(f"[PERF] Movements: {movements} | Rate: {performance:.1f}/sec | "
                                  f"DPI: {self.target_device.dpi if self.target_device else 0}")
                            
                            if self.mouse_hook.recent_movements:
                                last_move = self.mouse_hook.recent_movements[-1]
                                print(f"[LAST] Raw: ({last_move[0]}, {last_move[1]}) -> "
                                      f"Scaled: ({last_move[2]}, {last_move[3]})")
                        
                        self.last_log_time = current_time
            except:
                pass

    def heartbeat_worker(self):
        """Heartbeat thread to move the mouse and return it periodically."""
        while self.running:
            # Wait for 0.3 seconds before the next heartbeat cycle.
            time.sleep(0.3)
            if not self.running:
                break

            try:
                # Define movement parameters
                steps = 5
                pixels_per_step = 1
                duration_s = 0.01
                sleep_between_steps = duration_s / steps  # 0.002s

                # --- Move forward ---
                for _ in range(steps):
                    if not self.running:
                        break
                    send_faker_mouse_move_optimized(pixels_per_step, 0) # Move right
                    time.sleep(sleep_between_steps)

                if not self.running: # Check again before moving back
                    break

                # --- Move back ---
                for _ in range(steps):
                    if not self.running:
                        break
                    send_faker_mouse_move_optimized(-pixels_per_step, 0) # Move left
                    time.sleep(sleep_between_steps)

            except Exception as e:
                # Log error but don't crash the service
                print(f"[ERROR] Heartbeat movement failed: {e}")

    def start_passthrough(self):
        """Start optimized passthrough"""
        if not self.target_device:
            print("No mouse configured")
            return False

        try:
            # Set target device
            self.mouse_hook.target_device = self.target_device
            
            # Start optimized capture
            if not self.mouse_hook.start_hook():
                print("Failed to start capture")
                return False

            print("=== HIGH-PERFORMANCE MOUSE PASSTHROUGH ACTIVE ===")
            print(f"Mouse: {self.target_device.friendly_name}")
            print(f"DPI: {self.target_device.dpi} (Scale: {self.target_device._dpi_scale:.3f})")
            print("Mode: Optimized Raw Input (Ultra-low latency)")
            print("Performance: 1000Hz optimized")
            print("Press Ctrl+C to stop")

            self.running = True

            # Reset counters
            self.mouse_hook.total_movements = 0
            self.mouse_hook.movements_since_last = 0
            self.last_log_time = time.perf_counter()
            self.mouse_hook.recent_movements.clear()
            self.mouse_hook.recent_outputs.clear()

            # Start optimized logging
            self.log_thread = threading.Thread(target=self.log_worker, daemon=True)
            self.log_thread.start()

            # Start heartbeat thread
            self.heartbeat_thread = threading.Thread(target=self.heartbeat_worker, daemon=True)
            self.heartbeat_thread.start()

            # Minimal main loop overhead
            try:
                while self.running:
                    time.sleep(0.01)  # Reduced sleep for responsiveness
            except KeyboardInterrupt:
                print("\nStopping...")

            self.stop()
            return True

        except Exception as e:
            print(f"Error: {e}")
            return False

    def stop(self):
        """Stop passthrough"""
        self.running = False
        self.mouse_hook.stop_hook()

    def save_config(self):
        """Save configuration"""
        config = {}
        if self.target_device:
            config['target_device'] = asdict(self.target_device)
            # Don't save the cached _dpi_scale
            if '_dpi_scale' in config['target_device']:
                del config['target_device']['_dpi_scale']
        
        try:
            with open('mouse_config.json', 'w') as f:
                json.dump(config, f, indent=2)
        except:
            pass

    def load_config(self):
        """Load configuration"""
        try:
            with open('mouse_config.json', 'r') as f:
                config = json.load(f)
            
            td = config.get('target_device')
            if td:
                self.target_device = MouseDevice(**td)
                self.target_device.update_dpi_scale()  # Recalculate cached scale
                self.mouse_hook.target_device = self.target_device
                print(f"Loaded: {self.target_device.friendly_name} (DPI: {self.target_device.dpi})")
            
        except:
            pass

    def show_config(self):
        """Display configuration"""
        if self.target_device:
            print(f"\nMouse: {self.target_device.friendly_name}")
            print(f"VID/PID: {self.target_device.vendor_id}:{self.target_device.product_id}")
            print(f"DPI: {self.target_device.dpi} (Scale: {self.target_device._dpi_scale:.3f})")
            print(f"Handle: {self.target_device.handle_value}")
        else:
            print("\nNo mouse configured")

    def run(self):
        """Main UI loop"""
        while True:
            print("\n=== OPTIMIZED MOUSE PASSTHROUGH (1000Hz) ===")
            if self.target_device:
                print(f"Ready: {self.target_device.friendly_name} @ {self.target_device.dpi} DPI")
            else:
                print("No mouse configured")

            print("1. Detect mouse")
            print("2. Start passthrough")
            print("3. Set DPI")
            print("4. Show config")
            print("5. Exit")

            try:
                choice = input("\nChoice: ").strip()
            except (KeyboardInterrupt, EOFError):
                return

            if choice == "1":
                device = self.detect_active_mouse()
                if device:
                    self.target_device = device
                    self.mouse_hook.target_device = device
                    self.save_config()
                    print(f"Mouse ready: {device.friendly_name}")
                else:
                    print("No mouse detected")

            elif choice == "2":
                if self.target_device:
                    self.start_passthrough()
                else:
                    print("Detect mouse first")

            elif choice == "3":
                self.configure_dpi()

            elif choice == "4":
                self.show_config()

            elif choice == "5":
                break

def main():
    if sys.platform != "win32":
        print("Windows required")
        return 1

    service = OptimizedMousePassthrough()

    def signal_handler(signum, frame):
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        service.run()
        return 0
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())