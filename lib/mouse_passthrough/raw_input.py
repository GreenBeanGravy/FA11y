"""
Raw Input capture and mouse device detection via Win32 API.
"""

import ctypes
import ctypes.wintypes
from ctypes import wintypes, Structure, POINTER, byref, windll
import threading
import time
from typing import Optional
from dataclasses import dataclass, asdict

# Win32 constants
WM_QUIT = 0x0012
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

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


# --- Win32 Structures ---

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


# --- Win32 Function Prototypes ---

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


# --- Data Classes ---

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


# --- Raw Input Capture ---

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


# --- Device Detection ---

def _get_device_name(device_handle) -> Optional[str]:
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


def _parse_device_path(device_path: str) -> tuple:
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


def _get_friendly_name(device_path: str) -> str:
    vid, pid = _parse_device_path(device_path)
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


def detect_mouse_device(dpi: int = 1600, timeout: float = 10.0) -> Optional[MouseDevice]:
    """Detect a mouse device by waiting for raw input movement.

    Args:
        dpi: DPI value to assign to the detected device
        timeout: How long to wait for detection in seconds

    Returns:
        MouseDevice if detected, None if timed out
    """
    print(f"[INFO] Move your mouse to detect (timeout: {timeout}s)")

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
                        device_path = _get_device_name(device_handle)
                        if device_path:
                            vid, pid = _parse_device_path(device_path)
                            friendly_name = _get_friendly_name(device_path)
                            handle_value = int(ctypes.cast(device_handle, ctypes.c_void_p).value or 0)

                            detected_device = MouseDevice(
                                vendor_id=vid,
                                product_id=pid,
                                friendly_name=friendly_name,
                                device_path=device_path,
                                handle_value=handle_value,
                                dpi=dpi
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
            if time.perf_counter() - start_time >= timeout:
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
