"""
Low-Latency Audio Backend using IAudioClient3

Provides ~3ms latency in shared mode on Windows 10+ with compatible drivers.
Falls back gracefully if not supported.

Usage:
    backend = LowLatencyAudioBackend()
    if backend.initialize(sample_rate=48000, channels=2):
        backend.start(audio_callback)  # callback(num_frames) -> bytes
"""

import sys
import time
import threading
import logging
from ctypes import *
from typing import Optional, Callable, Dict, Any

if sys.platform != 'win32':
    raise ImportError("LowLatencyAudioBackend only works on Windows")

from ctypes.wintypes import HANDLE, DWORD, BOOL
HRESULT = c_long

logger = logging.getLogger(__name__)


# ============================================================================
# COM Definitions
# ============================================================================

class GUID(Structure):
    _fields_ = [
        ("Data1", c_ulong),
        ("Data2", c_ushort),
        ("Data3", c_ushort),
        ("Data4", c_ubyte * 8)
    ]

    def __init__(self, s=None):
        super().__init__()
        if s:
            parts = s.strip('{}').split('-')
            self.Data1 = int(parts[0], 16)
            self.Data2 = int(parts[1], 16)
            self.Data3 = int(parts[2], 16)
            d4 = parts[3] + parts[4]
            self.Data4 = (c_ubyte * 8)(*[int(d4[i:i+2], 16) for i in range(0, 16, 2)])


# GUIDs
CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
IID_IMMDeviceEnumerator = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
IID_IAudioClient = GUID("{1CB9AD4C-DBFA-4c32-B178-C2F568A703B2}")
IID_IAudioClient3 = GUID("{7ED4EE07-8E67-4CD4-8C1A-2B7A5987AD42}")
IID_IAudioRenderClient = GUID("{F294ACFC-3146-4483-A7BF-ADDCA7C260E2}")

KSDATAFORMAT_SUBTYPE_IEEE_FLOAT = GUID("{00000003-0000-0010-8000-00aa00389b71}")


class WAVEFORMATEX(Structure):
    _fields_ = [
        ("wFormatTag", c_ushort),
        ("nChannels", c_ushort),
        ("nSamplesPerSec", c_ulong),
        ("nAvgBytesPerSec", c_ulong),
        ("nBlockAlign", c_ushort),
        ("wBitsPerSample", c_ushort),
        ("cbSize", c_ushort),
    ]


# Constants
CLSCTX_ALL = 0x17
COINIT_MULTITHREADED = 0x0
eRender = 0
eConsole = 0
AUDCLNT_SHAREMODE_SHARED = 0
AUDCLNT_STREAMFLAGS_EVENTCALLBACK = 0x00040000
AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY = 0x08000000

# Windows API
ole32 = windll.ole32
ole32.CoInitializeEx.argtypes = [c_void_p, DWORD]
ole32.CoInitializeEx.restype = HRESULT
ole32.CoCreateInstance.argtypes = [POINTER(GUID), c_void_p, DWORD, POINTER(GUID), POINTER(c_void_p)]
ole32.CoCreateInstance.restype = HRESULT
ole32.CoTaskMemFree.argtypes = [c_void_p]
ole32.CoTaskMemFree.restype = None

kernel32 = windll.kernel32
kernel32.CreateEventW.argtypes = [c_void_p, BOOL, BOOL, c_wchar_p]
kernel32.CreateEventW.restype = HANDLE
kernel32.WaitForSingleObject.argtypes = [HANDLE, DWORD]
kernel32.WaitForSingleObject.restype = DWORD
kernel32.CloseHandle.argtypes = [HANDLE]
kernel32.CloseHandle.restype = BOOL
kernel32.QueryPerformanceFrequency.argtypes = [POINTER(c_longlong)]
kernel32.QueryPerformanceCounter.argtypes = [POINTER(c_longlong)]

_qpc_freq = c_longlong()
kernel32.QueryPerformanceFrequency(byref(_qpc_freq))
QPC_FREQ = _qpc_freq.value


def _time_ms() -> float:
    counter = c_longlong()
    kernel32.QueryPerformanceCounter(byref(counter))
    return (counter.value * 1000.0) / QPC_FREQ


class LowLatencyAudioBackend:
    """
    Low-latency audio output backend using Windows IAudioClient3.

    Provides shared-mode audio with minimal latency (~3-10ms depending on driver).
    Other applications continue to play audio normally.
    """

    def __init__(self):
        self._device_enumerator = None
        self._device = None
        self._audio_client = None
        self._render_client = None
        self._event_handle = None
        self._mix_format_ptr = None

        self.sample_rate: int = 48000
        self.channels: int = 2
        self.bits_per_sample: int = 32
        self.buffer_frames: int = 0
        self.period_frames: int = 0

        self.min_period_frames: int = 0
        self.default_period_frames: int = 0
        self.period_latency_ms: float = 0.0
        self.stream_latency_ms: float = 0.0
        self.using_iac3: bool = False

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[int], bytes]] = None
        self._initialized = False

        self.underruns = 0
        self.callbacks = 0

    def _call(self, obj_ptr, vtbl_index, *args) -> int:
        """Call COM method by vtable index"""
        vtbl = cast(obj_ptr, POINTER(c_void_p))[0]
        method_ptr = cast(vtbl, POINTER(c_void_p))[vtbl_index]

        argtypes = [c_void_p]
        for arg in args:
            if isinstance(arg, (c_void_p, type(None))):
                argtypes.append(c_void_p)
            elif hasattr(arg, '_type_'):
                argtypes.append(type(arg))
            elif isinstance(arg, int):
                argtypes.append(c_ulong)
            else:
                argtypes.append(c_void_p)

        func = CFUNCTYPE(HRESULT, *argtypes)(method_ptr)
        return func(obj_ptr, *args)

    def initialize(self, sample_rate: int = 48000, channels: int = 2, use_windows_resampling: bool = False) -> bool:
        """
        Initialize the low-latency audio backend.

        Args:
            sample_rate: Requested sample rate
            channels: Requested channels
            use_windows_resampling: If True, use Windows AUTOCONVERTPCM for format conversion

        Returns:
            True if initialization succeeded
        """
        self._use_windows_resampling = use_windows_resampling
        self._requested_sample_rate = sample_rate
        self._requested_channels = channels
        try:
            logger.info("[LowLatencyBackend] Initializing IAudioClient3...")

            hr = ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
            if hr < 0 and (hr & 0xFFFFFFFF) != 0x80010106:
                logger.error(f"CoInitializeEx failed: 0x{hr & 0xFFFFFFFF:08X}")
                return False

            self._device_enumerator = c_void_p()
            hr = ole32.CoCreateInstance(
                byref(CLSID_MMDeviceEnumerator), None, CLSCTX_ALL,
                byref(IID_IMMDeviceEnumerator), byref(self._device_enumerator)
            )
            if hr < 0:
                logger.error(f"Failed to create device enumerator: 0x{hr & 0xFFFFFFFF:08X}")
                return False

            self._device = c_void_p()
            hr = self._call(self._device_enumerator, 4, c_ulong(eRender), c_ulong(eConsole), byref(self._device))
            if hr < 0:
                logger.error(f"Failed to get default audio endpoint: 0x{hr & 0xFFFFFFFF:08X}")
                return False

            self._audio_client = c_void_p()
            hr = self._call(self._device, 3, byref(IID_IAudioClient3), c_ulong(CLSCTX_ALL), None, byref(self._audio_client))

            if hr < 0:
                logger.info("[LowLatencyBackend] IAudioClient3 not available, using IAudioClient")
                hr = self._call(self._device, 3, byref(IID_IAudioClient), c_ulong(CLSCTX_ALL), None, byref(self._audio_client))
                if hr < 0:
                    logger.error(f"Failed to activate audio client: 0x{hr & 0xFFFFFFFF:08X}")
                    return False
                self.using_iac3 = False
            else:
                self.using_iac3 = True

            self._mix_format_ptr = c_void_p()
            hr = self._call(self._audio_client, 8, byref(self._mix_format_ptr))
            if hr < 0:
                logger.error(f"Failed to get mix format: 0x{hr & 0xFFFFFFFF:08X}")
                return False

            mix_fmt = cast(self._mix_format_ptr, POINTER(WAVEFORMATEX)).contents
            device_sample_rate = mix_fmt.nSamplesPerSec
            device_channels = mix_fmt.nChannels
            device_bits = mix_fmt.wBitsPerSample

            logger.info(f"[LowLatencyBackend] Device format: {device_channels}ch, {device_sample_rate}Hz, {device_bits}bit")

            if self._use_windows_resampling:
                self._custom_format = WAVEFORMATEX()
                self._custom_format.wFormatTag = 3  # WAVE_FORMAT_IEEE_FLOAT
                self._custom_format.nChannels = self._requested_channels
                self._custom_format.nSamplesPerSec = self._requested_sample_rate
                self._custom_format.wBitsPerSample = 32
                self._custom_format.nBlockAlign = self._requested_channels * 4
                self._custom_format.nAvgBytesPerSec = self._requested_sample_rate * self._custom_format.nBlockAlign
                self._custom_format.cbSize = 0

                self.sample_rate = self._requested_sample_rate
                self.channels = self._requested_channels
                self.bits_per_sample = 32

                logger.info(f"[LowLatencyBackend] Using Windows resampling: {self.channels}ch @ {self.sample_rate}Hz")

                stream_flags = (AUDCLNT_STREAMFLAGS_EVENTCALLBACK |
                               AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM |
                               AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY)

                buffer_duration_hns = 50000  # 5ms

                hr = self._call(self._audio_client, 3,
                               c_ulong(AUDCLNT_SHAREMODE_SHARED),
                               c_ulong(stream_flags),
                               c_longlong(buffer_duration_hns),
                               c_longlong(0),
                               byref(self._custom_format),
                               None)

                if hr < 0:
                    logger.error(f"[LowLatencyBackend] Initialize with AUTOCONVERTPCM failed: 0x{hr & 0xFFFFFFFF:08X}")
                    return False

                self.using_iac3 = False
                logger.info("[LowLatencyBackend] Initialized with Windows AUTOCONVERTPCM")

            elif self.using_iac3:
                default_period = c_ulong()
                fundamental_period = c_ulong()
                min_period = c_ulong()
                max_period = c_ulong()

                hr = self._call(self._audio_client, 18,
                               self._mix_format_ptr,
                               byref(default_period), byref(fundamental_period),
                               byref(min_period), byref(max_period))

                if hr >= 0:
                    self.default_period_frames = default_period.value
                    self.min_period_frames = min_period.value
                    self.period_frames = min_period.value

                    default_ms = default_period.value / self.sample_rate * 1000
                    min_ms = min_period.value / self.sample_rate * 1000

                    logger.info(f"[LowLatencyBackend] Engine periods: default={default_ms:.2f}ms, min={min_ms:.2f}ms")

                    stream_flags = AUDCLNT_STREAMFLAGS_EVENTCALLBACK
                    hr = self._call(self._audio_client, 20,
                                   c_ulong(stream_flags),
                                   c_ulong(self.period_frames),
                                   self._mix_format_ptr,
                                   None)

                    if hr >= 0:
                        self.period_latency_ms = self.period_frames / self.sample_rate * 1000
                        logger.info(f"[LowLatencyBackend] IAudioClient3 low-latency mode: {self.period_latency_ms:.2f}ms period")
                    else:
                        logger.warning(f"[LowLatencyBackend] InitializeSharedAudioStream failed: 0x{hr & 0xFFFFFFFF:08X}")
                        self.using_iac3 = False
                else:
                    logger.warning(f"[LowLatencyBackend] GetSharedModeEnginePeriod failed: 0x{hr & 0xFFFFFFFF:08X}")
                    self.using_iac3 = False

            if not self.using_iac3 and not self._use_windows_resampling:
                stream_flags = AUDCLNT_STREAMFLAGS_EVENTCALLBACK
                hr = self._call(self._audio_client, 3,
                               c_ulong(AUDCLNT_SHAREMODE_SHARED),
                               c_ulong(stream_flags),
                               c_longlong(0),
                               c_longlong(0),
                               self._mix_format_ptr,
                               None)
                if hr < 0:
                    logger.error(f"[LowLatencyBackend] Initialize failed: 0x{hr & 0xFFFFFFFF:08X}")
                    return False

            buffer_frames = c_ulong()
            hr = self._call(self._audio_client, 4, byref(buffer_frames))
            if hr < 0:
                logger.error(f"[LowLatencyBackend] GetBufferSize failed: 0x{hr & 0xFFFFFFFF:08X}")
                return False
            self.buffer_frames = buffer_frames.value

            if not self.using_iac3:
                self.period_frames = self.buffer_frames // 2
                self.period_latency_ms = self.period_frames / self.sample_rate * 1000

            latency_hns = c_longlong()
            hr = self._call(self._audio_client, 5, byref(latency_hns))
            if hr >= 0:
                self.stream_latency_ms = latency_hns.value / 10000.0

            self._event_handle = kernel32.CreateEventW(None, False, False, None)
            self._call(self._audio_client, 13, self._event_handle)

            self._render_client = c_void_p()
            hr = self._call(self._audio_client, 14, byref(IID_IAudioRenderClient), byref(self._render_client))
            if hr < 0:
                logger.error(f"[LowLatencyBackend] GetService(RenderClient) failed: 0x{hr & 0xFFFFFFFF:08X}")
                return False

            self._initialized = True

            mode = "IAudioClient3 LOW-LATENCY" if self.using_iac3 else "Legacy shared"
            logger.info(f"[LowLatencyBackend] Initialized ({mode})")
            logger.info(f"[LowLatencyBackend]   Period: {self.period_latency_ms:.2f}ms ({self.period_frames} frames)")
            logger.info(f"[LowLatencyBackend]   Buffer: {self.buffer_frames / self.sample_rate * 1000:.2f}ms ({self.buffer_frames} frames)")
            logger.info(f"[LowLatencyBackend]   Stream latency: {self.stream_latency_ms:.2f}ms")

            return True

        except Exception as e:
            logger.error(f"[LowLatencyBackend] Initialization error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def start(self, callback: Callable[[int], bytes]) -> bool:
        """
        Start audio playback.

        Args:
            callback: Function that takes number of frames and returns audio bytes.
                     Bytes should be interleaved float32 samples matching the device format.

        Returns:
            True if started successfully
        """
        if not self._initialized:
            logger.error("[LowLatencyBackend] Not initialized")
            return False

        self._callback = callback
        self._running = True

        hr = self._call(self._audio_client, 10)  # Start
        if hr < 0:
            logger.error(f"[LowLatencyBackend] Start failed: 0x{hr & 0xFFFFFFFF:08X}")
            return False

        self._thread = threading.Thread(target=self._render_loop, daemon=True, name="LowLatencyAudio")
        self._thread.start()

        logger.info("[LowLatencyBackend] Audio playback started")
        return True

    def _render_loop(self):
        """Background render thread"""
        bytes_per_frame = self.channels * (self.bits_per_sample // 8)

        last_stats_time = time.time()
        stats_interval = 10.0
        period_callbacks = 0
        period_underruns = 0

        while self._running:
            result = kernel32.WaitForSingleObject(self._event_handle, 100)
            if not self._running:
                break
            if result != 0:
                continue

            try:
                self.callbacks += 1

                padding = c_ulong()
                hr = self._call(self._audio_client, 6, byref(padding))
                if hr < 0:
                    continue

                available = self.buffer_frames - padding.value
                if available == 0:
                    continue

                buffer_ptr = c_void_p()
                hr = self._call(self._render_client, 3, c_ulong(available), byref(buffer_ptr))
                if hr < 0:
                    continue

                if self._callback:
                    try:
                        data = self._callback(available)
                        if data and len(data) > 0:
                            copy_bytes = min(len(data), available * bytes_per_frame)
                            memmove(buffer_ptr, data, copy_bytes)
                            period_callbacks += 1
                        else:
                            self.underruns += 1
                            period_underruns += 1
                    except Exception as e:
                        logger.error(f"[LowLatencyBackend] Callback error: {e}")
                        self.underruns += 1
                        period_underruns += 1

                self._call(self._render_client, 4, c_ulong(available), c_ulong(0))

                now = time.time()
                if now - last_stats_time >= stats_interval:
                    elapsed = now - last_stats_time
                    cb_rate = period_callbacks / elapsed if elapsed > 0 else 0
                    underrun_pct = (period_underruns / max(1, period_callbacks)) * 100
                    logger.debug(f"[LowLatencyBackend] Stats: {period_callbacks} callbacks ({cb_rate:.0f}/s), {period_underruns} underruns ({underrun_pct:.1f}%), period={self.period_latency_ms:.1f}ms")

                    last_stats_time = now
                    period_callbacks = 0
                    period_underruns = 0

            except Exception as e:
                logger.error(f"[LowLatencyBackend] Render error: {e}")

    def stop(self):
        """Stop audio playback"""
        self._running = False

        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

        if self._audio_client:
            try:
                self._call(self._audio_client, 11)  # Stop
            except Exception:
                pass

    def close(self):
        """Release all resources"""
        self.stop()

        if self._mix_format_ptr:
            ole32.CoTaskMemFree(self._mix_format_ptr)
            self._mix_format_ptr = None

        for obj in [self._render_client, self._audio_client, self._device, self._device_enumerator]:
            if obj:
                try:
                    self._call(obj, 2)  # Release
                except Exception:
                    pass

        self._render_client = None
        self._audio_client = None
        self._device = None
        self._device_enumerator = None

        if self._event_handle:
            kernel32.CloseHandle(self._event_handle)
            self._event_handle = None

        self._initialized = False

    def get_latency_info(self) -> Dict[str, Any]:
        """Get latency information for logging/display"""
        return {
            'using_iac3': self.using_iac3,
            'period_ms': self.period_latency_ms,
            'stream_latency_ms': self.stream_latency_ms,
            'buffer_ms': self.buffer_frames / self.sample_rate * 1000 if self.sample_rate else 0,
            'sample_rate': self.sample_rate,
            'channels': self.channels,
            'bits_per_sample': self.bits_per_sample,
            'period_frames': self.period_frames,
            'buffer_frames': self.buffer_frames,
        }

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def is_running(self) -> bool:
        return self._running


def is_available() -> bool:
    """Check if low-latency backend is available on this system"""
    return sys.platform == 'win32'
