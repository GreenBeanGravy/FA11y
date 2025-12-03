#!/usr/bin/env python3
"""
Mouse Passthrough Service
Captures mouse input from one physical mouse and relays it through FakerInput driver.
Useful for bypassing input restrictions or using specific mice with games/applications.
"""

import sys
import ctypes
import ctypes.wintypes
from ctypes import wintypes, Structure, POINTER, byref, windll, c_void_p
import threading
import time
import signal
import os
import traceback
from typing import Optional
from dataclasses import dataclass, asdict
from collections import deque
from lib.config.config_manager import config_manager

DEFAULT_CONFIG = {
    "DPI": 1600,
    "BUFFER_SIZE": 256,
    "HEARTBEAT_ENABLED": True,
    "HEARTBEAT_INTERVAL": 0.3,
    "HEARTBEAT_DISTANCE": 2,
    "PERFORMANCE_LOG_INTERVAL": 1.0,
    "PERFORMANCE_DISPLAY_ENABLED": True,
    "MAX_RECENT_MOVEMENTS": 100,
    "MAX_RECENT_OUTPUTS": 50,
    "CACHE_INT16_RANGE": 100,
    "DETECTION_TIMEOUT": 10.0
}

HC_ACTION = 0
WH_MOUSE_LL = 14
LLMHF_INJECTED = 1
WM_QUIT = 0x0012

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A

WM_INPUT = 0x00FF
RIM_TYPEMOUSE = 0
RIDEV_INPUTSINK = 0x00000100
RIDEV_REMOVE = 0x00000001
RIDI_DEVICENAME = 0x20000007
PM_REMOVE = 0x0001

MOUSE_MOVE_RELATIVE = 0

LPVOID = ctypes.c_void_p
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
LRESULT = ctypes.c_int64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_int32

HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

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

def get_cached_int16(value):
    if value not in _net_int16_cache:
        _net_int16_cache[value] = _System.Int16(value)
    return _net_int16_cache[value]

try:
    print("[INFO] Loading FakerInput...")
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

def initialize_fakerinput(cache_range):
    global _faker_input, _mouse_report, _initialized, _System, FAKERINPUT_AVAILABLE
    global _FakerInputType, _RelativeMouseReportType, _update_method, _reset_method
    global _mouseX_property, _mouseY_property

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
            print("[INFO] FakerInput connected")
            
            for i in range(-cache_range, cache_range + 1):
                get_cached_int16(i)
            
            return True
        else:
            return False
            
    except Exception as e:
        print(f"[ERROR] FakerInput initialization: {e}")
        return False

def send_mouse_move(dx, dy, cache_range):
    global _faker_input, _mouse_report, _initialized, _update_method, _reset_method
    global _mouseX_property, _mouseY_property, _System
    
    if not _initialized:
        if not initialize_fakerinput(cache_range):
            return False
    
    try:
        MOUSE_MIN, MOUSE_MAX = -32767, 32767
        clamped_x = max(MOUSE_MIN, min(MOUSE_MAX, dx))
        clamped_y = max(MOUSE_MIN, min(MOUSE_MAX, dy))
        
        net_x = get_cached_int16(clamped_x) if abs(clamped_x) <= cache_range else _System.Int16(clamped_x)
        net_y = get_cached_int16(clamped_y) if abs(clamped_y) <= cache_range else _System.Int16(clamped_y)
        
        _mouseX_property.SetValue(_mouse_report, net_x)
        _mouseY_property.SetValue(_mouse_report, net_y)
        
        args = _System.Array[_System.Object]([_mouse_report])
        _update_method.Invoke(_faker_input, args)
        
        _reset_method.Invoke(_mouse_report, None)
        
        return True
    except Exception:
        return False

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

@dataclass
class MouseDevice:
    vendor_id: str
    product_id: str
    friendly_name: str
    device_path: str = ""
    handle_value: int = 0
    dpi: int = 1600

    def __post_init__(self):
        self.update_dpi_scale()

    def update_dpi_scale(self):
        self._dpi_scale = self.dpi / 800.0

    @property
    def handle(self) -> wintypes.HANDLE:
        return ctypes.c_void_p(self.handle_value)
    
    def matches(self, vid: str, pid: str) -> bool:
        return self.vendor_id == vid and self.product_id == pid

class RawInputCapture:
    def __init__(self, target_device, movement_callback, buffer_size):
        self.target_device = target_device
        self.movement_callback = movement_callback
        self.running = False
        self.window_handle = None
        self.capture_thread = None
        self._wndproc = None
        
        self.buffer_size = buffer_size
        self.raw_buffer = ctypes.create_string_buffer(self.buffer_size)
        self.size_holder = wintypes.UINT(self.buffer_size)
        
    def window_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_INPUT and self.running:
                self.size_holder.value = self.buffer_size
                hraw = wintypes.HANDLE(lparam)
                
                result = user32.GetRawInputData(
                    hraw, 0x10000003, self.raw_buffer, 
                    byref(self.size_holder), ctypes.sizeof(RAWINPUTHEADER)
                )
                
                if result > 0:
                    raw_input = ctypes.cast(self.raw_buffer, POINTER(RAWINPUT)).contents
                    if raw_input.header.dwType == RIM_TYPEMOUSE:
                        current_handle = int(ctypes.cast(raw_input.header.hDevice, ctypes.c_void_p).value or 0)
                        if current_handle == self.target_device.handle_value:
                            if raw_input.mouse.usFlags == MOUSE_MOVE_RELATIVE:
                                raw_dx = raw_input.mouse.lLastX
                                raw_dy = raw_input.mouse.lLastY
                                
                                if raw_dx != 0 or raw_dy != 0:
                                    self.movement_callback(raw_dx, raw_dy)
        except:
            pass
        
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
    
    def start_capture(self):
        if self.running:
            return True
            
        self.running = True
        self.capture_thread = threading.Thread(target=self._capture_worker, daemon=True)
        self.capture_thread.start()
        time.sleep(0.05)
        return self.window_handle is not None
    
    def _capture_worker(self):
        try:
            wndclass = WNDCLASSW()
            self._wndproc = WNDPROC(self.window_proc)
            wndclass.lpfnWndProc = self._wndproc
            wndclass.lpszClassName = "RawInputCapture"
            wndclass.hInstance = kernel32.GetModuleHandleW(None)

            if not user32.RegisterClassW(byref(wndclass)):
                if kernel32.GetLastError() != 1410:
                    return

            self.window_handle = user32.CreateWindowExW(
                0, "RawInputCapture", "Capture", 0, 0, 0, 0, 0,
                None, None, wndclass.hInstance, None
            )
            
            if not self.window_handle:
                return

            rid = RAWINPUTDEVICE()
            rid.usUsagePage = 0x01
            rid.usUsage = 0x02
            rid.dwFlags = RIDEV_INPUTSINK
            rid.hwndTarget = self.window_handle

            if not user32.RegisterRawInputDevices(byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE)):
                return

            print("[INFO] Raw input capture active")

            msg = MSG()
            while self.running:
                bRet = user32.GetMessageW(byref(msg), self.window_handle, 0, 0)
                if bRet <= 0:
                    break
                user32.TranslateMessage(byref(msg))
                user32.DispatchMessageW(byref(msg))

        except Exception as e:
            print(f"[ERROR] Capture worker: {e}")
        finally:
            self._cleanup()

    def _cleanup(self):
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
            user32.UnregisterClassW("RawInputCapture", kernel32.GetModuleHandleW(None))
        except:
            pass

    def stop_capture(self):
        if not self.running:
            return
            
        self.running = False
        if self.window_handle:
            user32.PostMessageW(self.window_handle, WM_QUIT, 0, 0)
        
        if self.capture_thread:
            self.capture_thread.join(timeout=1.0)

class MouseHook:
    def __init__(self, config):
        self.config = config
        self.target_device: Optional[MouseDevice] = None
        self.raw_input_capture = None
        
        self.total_movements = 0
        self.recent_movements = deque(maxlen=config["MAX_RECENT_MOVEMENTS"])
        self.recent_outputs = deque(maxlen=config["MAX_RECENT_OUTPUTS"])
        
        self.last_perf_time = time.perf_counter()
        self.movements_since_last = 0
        
        initialize_fakerinput(config["CACHE_INT16_RANGE"])
        
    def process_movement(self, raw_dx, raw_dy):
        if not self.target_device:
            return
            
        scaled_dx = int(raw_dx * self.target_device._dpi_scale)
        scaled_dy = int(raw_dy * self.target_device._dpi_scale)
        
        if scaled_dx != 0 or scaled_dy != 0:
            if send_mouse_move(scaled_dx, scaled_dy, self.config["CACHE_INT16_RANGE"]):
                self.total_movements += 1
                self.movements_since_last += 1
                
                if len(self.recent_movements) < self.config["MAX_RECENT_MOVEMENTS"] // 2:
                    self.recent_movements.append((raw_dx, raw_dy, scaled_dx, scaled_dy))
                
                if len(self.recent_outputs) < self.config["MAX_RECENT_OUTPUTS"] // 2:
                    self.recent_outputs.append(f"M({scaled_dx},{scaled_dy})")
    
    def start_hook(self):
        if not self.target_device:
            return False
        
        print("[INFO] Starting capture...")
        
        self.raw_input_capture = RawInputCapture(
            self.target_device, 
            self.process_movement,
            self.config["BUFFER_SIZE"]
        )
        
        if self.raw_input_capture.start_capture():
            print("[INFO] Capture started")
            return True
        else:
            return False
    
    def stop_hook(self):
        if self.raw_input_capture:
            self.raw_input_capture.stop_capture()
            self.raw_input_capture = None
    
    def get_performance_stats(self):
        current_time = time.perf_counter()
        elapsed = current_time - self.last_perf_time
        
        if elapsed >= self.config["PERFORMANCE_LOG_INTERVAL"]:
            movements_per_sec = self.movements_since_last / elapsed
            self.movements_since_last = 0
            self.last_perf_time = current_time
            return movements_per_sec
        return 0

class MousePassthrough:
    def __init__(self):
        config_manager.register(
            'mouse_passthrough',
            'config/mouse_passthrough.json',
            format='json',
            default=DEFAULT_CONFIG.copy()
        )
        
        self.config = config_manager.get('mouse_passthrough')
        
        final_config = DEFAULT_CONFIG.copy()
        for key in DEFAULT_CONFIG:
            if key in self.config:
                final_config[key] = self.config[key]
        self.config = final_config
        
        self.target_device: Optional[MouseDevice] = None
        self.running = False
        self.mouse_hook = MouseHook(self.config)
        self.log_thread = None
        self.heartbeat_thread = None
        self.last_log_time = time.perf_counter()
        
        if is_admin():
            print("[INFO] Running with Administrator privileges")
        else:
            print("[INFO] NOT running as Administrator - may have issues")
        
        self.load_device_from_config()

    def load_device_from_config(self):
        try:
            device_data = config_manager.get('mouse_passthrough', 'device')
            
            if device_data and isinstance(device_data, dict):
                if device_data.get("vendor_id") and device_data.get("product_id"):
                    if "dpi" not in device_data:
                        device_data["dpi"] = self.config["DPI"]
                    
                    self.target_device = MouseDevice(**device_data)
                    self.mouse_hook.target_device = self.target_device
                    print(f"[INFO] Loaded: {self.target_device.friendly_name} @ {self.target_device.dpi} DPI")
                    
                    self.config["DPI"] = self.target_device.dpi
        except Exception:
            pass

    def save_device_to_config(self):
        if not self.target_device:
            return
            
        try:
            device_dict = asdict(self.target_device)
            if '_dpi_scale' in device_dict:
                del device_dict['_dpi_scale']
            
            config_manager.set('mouse_passthrough', 'device', device_dict)
        except Exception as e:
            print(f"[ERROR] Failed to save device: {e}")
    
    def save_config(self):
        try:
            config_manager.set('mouse_passthrough', data=self.config)
        except Exception as e:
            print(f"[ERROR] Failed to save config: {e}")

    def get_device_name(self, device_handle) -> Optional[str]:
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

    def parse_device_path(self, device_path: str) -> tuple:
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
        vid, pid = self.parse_device_path(device_path)
        brands = {
            "1532": "Razer",
            "046D": "Logitech",
            "1B1C": "Corsair",
            "1038": "SteelSeries",
            "3938": "ZOWIE",
            "24AE": "Glorious"
        }
        brand = brands.get(vid, "Gaming" if vid != "0000" else "Generic")
        return f"{brand} Mouse ({vid}:{pid})"

    def detect_mouse(self) -> Optional[MouseDevice]:
        print(f"[INFO] Move your mouse to detect (timeout: {self.config['DETECTION_TIMEOUT']}s)")

        detected_device = None
        detection_complete = threading.Event()

        def window_proc(hwnd, msg, wparam, lparam):
            nonlocal detected_device
            try:
                if msg == WM_INPUT:
                    size = wintypes.UINT(48)
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
                                    vendor_id=vid,
                                    product_id=pid,
                                    friendly_name=friendly_name,
                                    device_path=device_path,
                                    handle_value=handle_value,
                                    dpi=self.config["DPI"]
                                )
                                print(f"[INFO] Detected: {friendly_name}")
                                detection_complete.set()
            except Exception:
                pass
            
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        det_wndproc = WNDPROC(window_proc)
        
        wndclass = WNDCLASSW()
        wndclass.lpfnWndProc = det_wndproc
        wndclass.lpszClassName = "MouseDetector"
        wndclass.hInstance = kernel32.GetModuleHandleW(None)

        hwnd = None
        try:
            if not user32.RegisterClassW(byref(wndclass)):
                if kernel32.GetLastError() != 1410:
                    return None

            hwnd = user32.CreateWindowExW(
                0, wndclass.lpszClassName, "Detector", 0, 0, 0, 0, 0,
                None, None, wndclass.hInstance, None
            )
            if not hwnd:
                return None

            rid = RAWINPUTDEVICE()
            rid.usUsagePage = 0x01
            rid.usUsage = 0x02
            rid.dwFlags = RIDEV_INPUTSINK
            rid.hwndTarget = hwnd

            if not user32.RegisterRawInputDevices(byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE)):
                return None

            msg = MSG()
            while user32.PeekMessageW(byref(msg), hwnd, WM_INPUT, WM_INPUT, PM_REMOVE):
                pass

            start_time = time.perf_counter()
            while not detection_complete.is_set():
                if time.perf_counter() - start_time >= self.config["DETECTION_TIMEOUT"]:
                    break
                
                if user32.PeekMessageW(byref(msg), hwnd, 0, 0, PM_REMOVE):
                    user32.TranslateMessage(byref(msg))
                    user32.DispatchMessageW(byref(msg))
                else:
                    time.sleep(0.001)

            return detected_device

        except Exception as e:
            print(f"[ERROR] Detection failed: {e}")
            return None
        finally:
            if hwnd:
                rid = RAWINPUTDEVICE()
                rid.usUsagePage = 0x01
                rid.usUsage = 0x02
                rid.dwFlags = RIDEV_REMOVE
                rid.hwndTarget = None
                user32.RegisterRawInputDevices(byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE))
                user32.DestroyWindow(hwnd)
            
            try:
                user32.UnregisterClassW(wndclass.lpszClassName, wndclass.hInstance)
            except:
                pass

    def configure_dpi(self):
        if not self.target_device:
            print("[ERROR] No mouse configured")
            return
        
        print(f"\n[INFO] Current DPI: {self.target_device.dpi}")
        try:
            dpi_input = input("Enter new DPI (50-50000): ").strip()
            if not dpi_input:
                return
                
            new_dpi = int(dpi_input)
            if 50 <= new_dpi <= 50000:
                self.target_device.dpi = new_dpi
                self.target_device.update_dpi_scale()
                self.mouse_hook.target_device = self.target_device
                
                self.config["DPI"] = new_dpi
                config_manager.set('mouse_passthrough', 'DPI', new_dpi)
                self.save_device_to_config()
                
                print(f"[INFO] DPI set to {new_dpi}")
            else:
                print("[ERROR] DPI must be between 50 and 50000")
        except ValueError:
            print("[ERROR] Invalid DPI value")
        except KeyboardInterrupt:
            pass

    def configure_advanced(self):
        while True:
            print("\n=== Advanced Configuration ===")
            print(f"[1] Heartbeat: {'Enabled' if self.config['HEARTBEAT_ENABLED'] else 'Disabled'}")
            print(f"[2] Heartbeat Interval: {self.config['HEARTBEAT_INTERVAL']}s")
            print(f"[3] Heartbeat Distance: {self.config['HEARTBEAT_DISTANCE']} pixels")
            print(f"[4] Performance Display: {'Enabled' if self.config['PERFORMANCE_DISPLAY_ENABLED'] else 'Disabled'}")
            print(f"[5] Performance Log Interval: {self.config['PERFORMANCE_LOG_INTERVAL']}s")
            print(f"[6] Buffer Size: {self.config['BUFFER_SIZE']} bytes")
            print(f"[7] Detection Timeout: {self.config['DETECTION_TIMEOUT']}s")
            print("[8] Back to main menu")
            
            try:
                choice = input("\nChoice: ").strip()
            except (KeyboardInterrupt, EOFError):
                break
            
            if choice == "1":
                self.config["HEARTBEAT_ENABLED"] = not self.config["HEARTBEAT_ENABLED"]
                config_manager.set('mouse_passthrough', 'HEARTBEAT_ENABLED', self.config["HEARTBEAT_ENABLED"])
                print(f"[INFO] Heartbeat {'enabled' if self.config['HEARTBEAT_ENABLED'] else 'disabled'}")
            
            elif choice == "2":
                try:
                    val = float(input("Interval (0.1-10.0s): "))
                    if 0.1 <= val <= 10.0:
                        self.config["HEARTBEAT_INTERVAL"] = val
                        config_manager.set('mouse_passthrough', 'HEARTBEAT_INTERVAL', val)
                    else:
                        print("[ERROR] Value out of range")
                except ValueError:
                    print("[ERROR] Invalid value")
            
            elif choice == "3":
                try:
                    val = int(input("Distance (1-20 pixels): "))
                    if 1 <= val <= 20:
                        self.config["HEARTBEAT_DISTANCE"] = val
                        config_manager.set('mouse_passthrough', 'HEARTBEAT_DISTANCE', val)
                    else:
                        print("[ERROR] Value out of range")
                except ValueError:
                    print("[ERROR] Invalid value")
            
            elif choice == "4":
                self.config["PERFORMANCE_DISPLAY_ENABLED"] = not self.config["PERFORMANCE_DISPLAY_ENABLED"]
                config_manager.set('mouse_passthrough', 'PERFORMANCE_DISPLAY_ENABLED', self.config["PERFORMANCE_DISPLAY_ENABLED"])
                print(f"[INFO] Performance display {'enabled' if self.config['PERFORMANCE_DISPLAY_ENABLED'] else 'disabled'}")
            
            elif choice == "5":
                try:
                    val = float(input("Interval (0.5-10.0s): "))
                    if 0.5 <= val <= 10.0:
                        self.config["PERFORMANCE_LOG_INTERVAL"] = val
                        config_manager.set('mouse_passthrough', 'PERFORMANCE_LOG_INTERVAL', val)
                    else:
                        print("[ERROR] Value out of range")
                except ValueError:
                    print("[ERROR] Invalid value")
            
            elif choice == "6":
                try:
                    val = int(input("Size (128-2048 bytes): "))
                    if 128 <= val <= 2048:
                        self.config["BUFFER_SIZE"] = val
                        config_manager.set('mouse_passthrough', 'BUFFER_SIZE', val)
                        print("[INFO] Restart passthrough for change to take effect")
                    else:
                        print("[ERROR] Value out of range")
                except ValueError:
                    print("[ERROR] Invalid value")
            
            elif choice == "7":
                try:
                    val = float(input("Timeout (1-60s): "))
                    if 1 <= val <= 60:
                        self.config["DETECTION_TIMEOUT"] = val
                        config_manager.set('mouse_passthrough', 'DETECTION_TIMEOUT', val)
                    else:
                        print("[ERROR] Value out of range")
                except ValueError:
                    print("[ERROR] Invalid value")
            
            elif choice == "8":
                break

    def log_worker(self):
        while self.running:
            try:
                time.sleep(self.config["PERFORMANCE_LOG_INTERVAL"])
                
                if self.running and self.config["PERFORMANCE_DISPLAY_ENABLED"]:
                    current_time = time.perf_counter()
                    elapsed = current_time - self.last_log_time
                    
                    if elapsed >= self.config["PERFORMANCE_LOG_INTERVAL"]:
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
        while self.running:
            time.sleep(self.config["HEARTBEAT_INTERVAL"])
            if not self.running:
                break

            if not self.config["HEARTBEAT_ENABLED"]:
                continue

            try:
                steps = self.config["HEARTBEAT_DISTANCE"]
                pixels_per_step = 1
                duration_s = 0.002
                sleep_between_steps = duration_s / steps

                for _ in range(steps):
                    if not self.running:
                        break
                    send_mouse_move(pixels_per_step, 0, self.config["CACHE_INT16_RANGE"])
                    time.sleep(sleep_between_steps)

                if not self.running:
                    break

                for _ in range(steps):
                    if not self.running:
                        break
                    send_mouse_move(-pixels_per_step, 0, self.config["CACHE_INT16_RANGE"])
                    time.sleep(sleep_between_steps)

            except Exception as e:
                print(f"[ERROR] Heartbeat failed: {e}")

    def start_passthrough(self):
        if not self.target_device:
            print("[ERROR] No mouse configured - detect mouse first")
            return False

        try:
            self.mouse_hook.target_device = self.target_device
            
            if not self.mouse_hook.start_hook():
                print("[ERROR] Failed to start capture")
                return False

            border = "=" * 50
            print(f"\n{border}")
            print("          Mouse Passthrough Active")
            print(border)
            print(f"[CONFIG] Mouse: {self.target_device.friendly_name}")
            print(f"[CONFIG] DPI: {self.target_device.dpi} (Scale: {self.target_device._dpi_scale:.3f})")
            print(f"[CONFIG] Heartbeat: {'Enabled' if self.config['HEARTBEAT_ENABLED'] else 'Disabled'}")
            print(f"[CONFIG] Performance Display: {'Enabled' if self.config['PERFORMANCE_DISPLAY_ENABLED'] else 'Disabled'}")
            print(border)
            print("[INFO] Press Ctrl+C to stop")
            print(border)

            self.running = True

            self.mouse_hook.total_movements = 0
            self.mouse_hook.movements_since_last = 0
            self.last_log_time = time.perf_counter()
            self.mouse_hook.recent_movements.clear()
            self.mouse_hook.recent_outputs.clear()

            if self.config["PERFORMANCE_DISPLAY_ENABLED"]:
                self.log_thread = threading.Thread(target=self.log_worker, daemon=True)
                self.log_thread.start()

            if self.config["HEARTBEAT_ENABLED"]:
                self.heartbeat_thread = threading.Thread(target=self.heartbeat_worker, daemon=True)
                self.heartbeat_thread.start()

            try:
                while self.running:
                    time.sleep(0.01)
            except KeyboardInterrupt:
                print("\n[INFO] Stopping...")

            self.stop()
            return True

        except Exception as e:
            print(f"[ERROR] Passthrough failed: {e}")
            return False

    def stop(self):
        self.running = False
        self.mouse_hook.stop_hook()

    def show_config(self):
        if self.target_device:
            print(f"\n=== Current Configuration ===")
            print(f"Mouse: {self.target_device.friendly_name}")
            print(f"VID:PID: {self.target_device.vendor_id}:{self.target_device.product_id}")
            print(f"DPI: {self.target_device.dpi} (Scale: {self.target_device._dpi_scale:.3f})")
            print(f"Heartbeat: {'Enabled' if self.config['HEARTBEAT_ENABLED'] else 'Disabled'}")
            print(f"Performance Display: {'Enabled' if self.config['PERFORMANCE_DISPLAY_ENABLED'] else 'Disabled'}")
        else:
            print("\n[INFO] No mouse configured")

    def run(self):
        while True:
            print("\n" + "=" * 50)
            print("          Mouse Passthrough Service")
            print("=" * 50)
            
            if self.target_device:
                print(f"[READY] {self.target_device.friendly_name} @ {self.target_device.dpi} DPI")
            else:
                print("[INFO] No mouse configured")

            print("\n[1] Detect mouse")
            print("[2] Start passthrough")
            print("[3] Configure DPI")
            print("[4] Advanced settings")
            print("[5] Show configuration")
            print("[6] Exit")

            try:
                choice = input("\nChoice: ").strip()
            except (KeyboardInterrupt, EOFError):
                break

            if choice == "1":
                device = self.detect_mouse()
                if device:
                    if self.target_device and self.target_device.matches(device.vendor_id, device.product_id):
                        device.dpi = self.target_device.dpi
                        device.update_dpi_scale()
                    
                    self.target_device = device
                    self.mouse_hook.target_device = device
                    self.save_device_to_config()
                    print(f"[INFO] Mouse ready: {device.friendly_name}")
                else:
                    print("[ERROR] No mouse detected")

            elif choice == "2":
                if self.target_device:
                    self.start_passthrough()
                else:
                    print("[ERROR] Detect mouse first")

            elif choice == "3":
                self.configure_dpi()

            elif choice == "4":
                self.configure_advanced()

            elif choice == "5":
                self.show_config()

            elif choice == "6":
                break

def main():
    if sys.platform != "win32":
        print("[ERROR] Windows required")
        return 1

    service = MousePassthrough()

    def signal_handler(signum, frame):
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        service.run()
        return 0
    except Exception as e:
        print(f"[ERROR] Fatal error: {e}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())