"""
FA11y Audio Engine - Adapted from FortniteAudioGame's SteamAudioEngine

Centralized audio mixer with:
- Steam Audio HRTF binaural spatialization (via phonon.dll)
- Fast stereo panning fallback when HRTF unavailable
- Windows IAudioClient3 low-latency backend (~3ms)
- PyAudio fallback for compatibility
- Per-source air absorption, distance attenuation, fade-in/out
- Soft-knee tanh limiter
"""

import os
import math
import threading
import time
import logging
from typing import Dict, Optional, Tuple
from ctypes import *
from dataclasses import dataclass, field

import numpy as np
import pyaudio
import soundfile as sf

logger = logging.getLogger(__name__)

# Low-latency audio backend (Windows 10+)
LOW_LATENCY_AVAILABLE = False
LowLatencyAudioBackend = None
try:
    import sys
    if sys.platform == 'win32':
        from lib.audio.low_latency_backend import LowLatencyAudioBackend, is_available
        LOW_LATENCY_AVAILABLE = is_available()
except ImportError:
    pass

logger.info(f"Low-latency backend available: {LOW_LATENCY_AVAILABLE}")

# ============================================================================
# Steam Audio C API Type Definitions
# ============================================================================

IPLContext = c_void_p
IPLHRTF = c_void_p
IPLBinauralEffect = c_void_p
IPLint32 = c_int32
IPLfloat32 = c_float
IPLuint32 = c_uint32


class IPLVector3(Structure):
    _fields_ = [("x", IPLfloat32), ("y", IPLfloat32), ("z", IPLfloat32)]


class IPLContextSettings(Structure):
    _fields_ = [
        ("version", c_uint32),
        ("logCallback", c_void_p),
        ("allocateCallback", c_void_p),
        ("freeCallback", c_void_p),
        ("simdLevel", c_int)
    ]


class IPLAudioSettings(Structure):
    _fields_ = [("samplingRate", c_int32), ("frameSize", c_int32)]


class IPLHRTFSettings(Structure):
    _fields_ = [
        ("type", c_int),
        ("sofaFileName", c_char_p),
        ("volume", IPLfloat32),
        ("normType", c_int),
    ]


class IPLBinauralEffectSettings(Structure):
    _fields_ = [("hrtf", IPLHRTF)]


class IPLBinauralEffectParams(Structure):
    _fields_ = [
        ("direction", IPLVector3),
        ("interpolation", c_int),
        ("spatialBlend", IPLfloat32),
        ("hrtf", IPLHRTF),
        ("peakDelays", POINTER(IPLfloat32))
    ]


class IPLAudioBuffer(Structure):
    _fields_ = [
        ("numChannels", c_int32),
        ("numSamples", c_int32),
        ("data", POINTER(POINTER(c_float)))
    ]


IPL_STATUS_SUCCESS = 0
IPL_HRTFINTERPOLATION_BILINEAR = 1


# ============================================================================
# Audio Source State
# ============================================================================

@dataclass
class AudioSource:
    """Represents a playing sound source"""
    source_id: int
    sound_id: str
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    volume: float = 1.0
    pitch: float = 1.0
    loop: bool = False
    is_3d: bool = True

    sample_offset: int = 0
    samples: Optional[np.ndarray] = None
    sample_rate: int = 48000
    is_playing: bool = True

    fading_in: bool = True
    fade_in_samples_remaining: int = 0
    fade_in_samples_total: int = 0

    fading_out: bool = False
    fade_samples_remaining: int = 0
    fade_samples_total: int = 0

    binaural_effect: IPLBinauralEffect = None

    min_distance: float = 1.0
    max_distance: float = 100.0
    min_volume: float = 0.0

    lpf_prior: float = 0.0


# ============================================================================
# Audio Ring Buffer
# ============================================================================

class AudioRingBuffer:
    """Thread-safe ring buffer for audio samples"""

    def __init__(self, capacity_frames: int, channels: int = 2):
        self.capacity = capacity_frames
        self.channels = channels
        self.buffer_size = capacity_frames * channels
        self.buffer = np.zeros(self.buffer_size, dtype=np.float32)
        self.write_pos = 0
        self.read_pos = 0
        self.frames_available = 0
        self.lock = threading.Lock()

    def write(self, samples):
        """Write interleaved samples to buffer. Returns False if full."""
        count = len(samples)
        frames = count // self.channels

        with self.lock:
            if self.frames_available + frames > self.capacity:
                return False

            end_pos = self.write_pos + count

            if end_pos <= self.buffer_size:
                self.buffer[self.write_pos:end_pos] = samples
            else:
                first_chunk = self.buffer_size - self.write_pos
                self.buffer[self.write_pos:] = samples[:first_chunk]
                self.buffer[:end_pos - self.buffer_size] = samples[first_chunk:]

            self.write_pos = (self.write_pos + count) % self.buffer_size
            self.frames_available += frames
            return True

    def read(self, num_frames: int):
        """Read frames from buffer. Returns silence if empty."""
        num_samples = num_frames * self.channels

        with self.lock:
            if self.frames_available < num_frames:
                return np.zeros(num_samples, dtype=np.float32)

            end_pos = self.read_pos + num_samples

            if end_pos <= self.buffer_size:
                data = self.buffer[self.read_pos:end_pos].copy()
            else:
                first_chunk = self.buffer_size - self.read_pos
                second_chunk = end_pos - self.buffer_size
                data = np.concatenate([
                    self.buffer[self.read_pos:],
                    self.buffer[:second_chunk]
                ])

            self.read_pos = (self.read_pos + num_samples) % self.buffer_size
            self.frames_available -= num_frames
            return data


# ============================================================================
# FA11y Audio Engine
# ============================================================================

class FA11yAudioEngine:
    """Centralized 3D audio engine with Steam Audio HRTF and low-latency output"""

    MAX_SOURCE_ID = 2147483647
    SAMPLE_RATE = 48000
    FRAME_SIZE = 512  # ~10ms at 48kHz
    OUTPUT_CHANNELS = 2

    def __init__(self):
        self.initialized = False
        self.phonon_lib = None
        self.context: IPLContext = None
        self.hrtf: IPLHRTF = None
        self.audio_settings: IPLAudioSettings = None

        self.stream = None
        self.pa = None
        self.mixer_thread = None
        self.running = False
        self.device_lock = threading.Lock()
        self.ring_buffer = None

        self.sounds: Dict[str, dict] = {}
        self.sources: Dict[int, AudioSource] = {}
        self.next_source_id = 1

        self.listener_position = (0.0, 0.0, 0.0)
        self.listener_yaw = 0.0

        self.mono_buffer = None

        self.enable_hrtf = True
        self._hrtf_logged_once = False

        self.low_latency_backend = None
        self.use_low_latency = False

    def initialize(self, use_low_latency: bool = True) -> bool:
        """Initialize the audio engine"""
        self.use_low_latency = use_low_latency and LOW_LATENCY_AVAILABLE

        try:
            # Try to load Steam Audio for HRTF
            if not self._load_steam_audio():
                logger.warning("Steam Audio not available, using stereo panning fallback")
                self.enable_hrtf = False

            if self.enable_hrtf and self.phonon_lib:
                if not self._create_context():
                    self.enable_hrtf = False

                if self.enable_hrtf:
                    self.audio_settings = IPLAudioSettings()
                    self.audio_settings.samplingRate = self.SAMPLE_RATE
                    self.audio_settings.frameSize = self.FRAME_SIZE

                    if not self._create_hrtf():
                        self.enable_hrtf = False

            self.mono_buffer = np.zeros(self.FRAME_SIZE, dtype=np.float32)

            ring_buffer_frames = 2400 if use_low_latency else 1920
            self.ring_buffer = AudioRingBuffer(ring_buffer_frames, self.OUTPUT_CHANNELS)
            self.running = True

            self.mixer_thread = threading.Thread(target=self._mixer_loop, daemon=True, name="FA11yMixer")
            self.mixer_thread.start()

            if self.use_low_latency:
                if not self._init_low_latency_device():
                    logger.warning("Low-latency backend failed, falling back to PyAudio")
                    self.use_low_latency = False
                    if not self._init_audio_device():
                        return False
            else:
                if not self._init_audio_device():
                    return False

            self.initialized = True
            hrtf_status = "HRTF enabled" if self.enable_hrtf else "stereo panning"
            backend_status = "low-latency" if self.use_low_latency else "PyAudio"
            logger.info(f"FA11y audio engine initialized ({hrtf_status}, {backend_status})")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize audio engine: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ========================================================================
    # Steam Audio Setup
    # ========================================================================

    def _load_steam_audio(self) -> bool:
        """Load phonon.dll from lib/audio/"""
        try:
            lib_dir = os.path.dirname(os.path.abspath(__file__))
            lib_path = os.path.join(lib_dir, "phonon.dll")

            if not os.path.exists(lib_path):
                logger.info(f"phonon.dll not found at {lib_path}")
                return False

            self.phonon_lib = CDLL(lib_path)
            self._define_steam_audio_api()
            logger.info(f"Loaded Steam Audio from {lib_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load Steam Audio: {e}")
            return False

    def _define_steam_audio_api(self):
        """Define ctypes signatures for Steam Audio C API"""
        lib = self.phonon_lib

        lib.iplContextCreate.argtypes = [POINTER(IPLContextSettings), POINTER(IPLContext)]
        lib.iplContextCreate.restype = c_int
        lib.iplContextRelease.argtypes = [POINTER(IPLContext)]
        lib.iplContextRelease.restype = None

        lib.iplHRTFCreate.argtypes = [IPLContext, POINTER(IPLAudioSettings), POINTER(IPLHRTFSettings), POINTER(IPLHRTF)]
        lib.iplHRTFCreate.restype = c_int
        lib.iplHRTFRelease.argtypes = [POINTER(IPLHRTF)]
        lib.iplHRTFRelease.restype = None

        lib.iplBinauralEffectCreate.argtypes = [IPLContext, POINTER(IPLAudioSettings), POINTER(IPLBinauralEffectSettings), POINTER(IPLBinauralEffect)]
        lib.iplBinauralEffectCreate.restype = c_int
        lib.iplBinauralEffectApply.argtypes = [IPLBinauralEffect, POINTER(IPLBinauralEffectParams), POINTER(IPLAudioBuffer), POINTER(IPLAudioBuffer)]
        lib.iplBinauralEffectApply.restype = c_int
        lib.iplBinauralEffectRelease.argtypes = [POINTER(IPLBinauralEffect)]
        lib.iplBinauralEffectRelease.restype = None

    def _create_context(self) -> bool:
        """Create Steam Audio context"""
        try:
            settings = IPLContextSettings()
            settings.version = 0x04040000
            settings.logCallback = None
            settings.allocateCallback = None
            settings.freeCallback = None
            settings.simdLevel = 0

            context = IPLContext()
            result = self.phonon_lib.iplContextCreate(byref(settings), byref(context))

            if result != IPL_STATUS_SUCCESS:
                logger.error(f"iplContextCreate failed: {result}")
                return False

            self.context = context
            return True

        except Exception as e:
            logger.error(f"Error creating context: {e}")
            return False

    def _create_hrtf(self) -> bool:
        """Create HRTF for binaural rendering"""
        try:
            hrtf_settings = IPLHRTFSettings()
            hrtf_settings.type = 0  # IPL_HRTFTYPE_DEFAULT
            hrtf_settings.sofaFileName = None
            hrtf_settings.volume = 1.0
            hrtf_settings.normType = 0

            hrtf = IPLHRTF()
            result = self.phonon_lib.iplHRTFCreate(
                self.context,
                byref(self.audio_settings),
                byref(hrtf_settings),
                byref(hrtf)
            )

            if result != IPL_STATUS_SUCCESS:
                logger.error(f"iplHRTFCreate failed: {result}")
                return False

            self.hrtf = hrtf
            logger.info("Steam Audio HRTF created")
            return True

        except Exception as e:
            logger.error(f"Error creating HRTF: {e}")
            return False

    def _create_binaural_effect(self) -> Optional[IPLBinauralEffect]:
        """Create a binaural effect for a sound source"""
        if not self.enable_hrtf or not self.context or not self.hrtf or not self.phonon_lib:
            return None

        try:
            effect_settings = IPLBinauralEffectSettings()
            effect_settings.hrtf = self.hrtf

            effect = IPLBinauralEffect()
            result = self.phonon_lib.iplBinauralEffectCreate(
                self.context,
                byref(self.audio_settings),
                byref(effect_settings),
                byref(effect)
            )

            if result != IPL_STATUS_SUCCESS:
                return None

            return effect

        except Exception:
            return None

    # ========================================================================
    # Audio Device Setup
    # ========================================================================

    def _init_audio_device(self) -> bool:
        """Initialize PyAudio output stream"""
        try:
            self.pa = pyaudio.PyAudio()
            self.stream = self.pa.open(
                format=pyaudio.paFloat32,
                channels=self.OUTPUT_CHANNELS,
                rate=self.SAMPLE_RATE,
                output=True,
                frames_per_buffer=256,
                stream_callback=self._audio_callback
            )
            self.stream.start_stream()
            logger.info(f"PyAudio started at {self.SAMPLE_RATE}Hz")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize PyAudio: {e}")
            return False

    def _init_low_latency_device(self) -> bool:
        """Initialize IAudioClient3 low-latency backend"""
        if not LOW_LATENCY_AVAILABLE or LowLatencyAudioBackend is None:
            return False

        try:
            self.low_latency_backend = LowLatencyAudioBackend()

            if not self.low_latency_backend.initialize(
                sample_rate=self.SAMPLE_RATE,
                channels=self.OUTPUT_CHANNELS,
                use_windows_resampling=True
            ):
                self.low_latency_backend = None
                return False

            info = self.low_latency_backend.get_latency_info()
            mode = "IAudioClient3" if info['using_iac3'] else "Legacy"
            logger.info(f"Low-latency backend initialized ({mode})")
            logger.info(f"  Period: {info['period_ms']:.2f}ms, Stream latency: {info['stream_latency_ms']:.2f}ms")

            if not self.low_latency_backend.start(self._low_latency_callback):
                self.low_latency_backend.close()
                self.low_latency_backend = None
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to initialize low-latency backend: {e}")
            if self.low_latency_backend:
                self.low_latency_backend.close()
                self.low_latency_backend = None
            return False

    def _low_latency_callback(self, num_frames: int) -> bytes:
        """Callback for low-latency backend"""
        try:
            device_channels = self.low_latency_backend.channels if self.low_latency_backend else self.OUTPUT_CHANNELS

            if not self.ring_buffer:
                return b'\x00' * (num_frames * device_channels * 4)

            data = self.ring_buffer.read(num_frames)
            if not isinstance(data, np.ndarray):
                data = np.array(data, dtype=np.float32)

            expected_samples = num_frames * self.OUTPUT_CHANNELS
            if len(data) < expected_samples:
                data = np.pad(data, (0, expected_samples - len(data)))

            stereo_data = data[:expected_samples].reshape(-1, self.OUTPUT_CHANNELS)

            if device_channels > self.OUTPUT_CHANNELS:
                output = np.zeros((num_frames, device_channels), dtype=np.float32)
                output[:, 0] = stereo_data[:, 0]
                output[:, 1] = stereo_data[:, 1]
                return output.tobytes()
            else:
                return stereo_data.tobytes()

        except Exception:
            device_channels = self.low_latency_backend.channels if self.low_latency_backend else self.OUTPUT_CHANNELS
            return b'\x00' * (num_frames * device_channels * 4)

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback"""
        try:
            if self.ring_buffer:
                data = self.ring_buffer.read(frame_count)
                if isinstance(data, np.ndarray):
                    expected = frame_count * self.OUTPUT_CHANNELS
                    if len(data) < expected:
                        data = np.pad(data, (0, expected - len(data)))
                    return (data.astype(np.float32).tobytes(), pyaudio.paContinue)

            silence = np.zeros(frame_count * self.OUTPUT_CHANNELS, dtype=np.float32)
            return (silence.tobytes(), pyaudio.paContinue)
        except Exception:
            silence = np.zeros(frame_count * self.OUTPUT_CHANNELS, dtype=np.float32)
            return (silence.tobytes(), pyaudio.paContinue)

    # ========================================================================
    # Mixer
    # ========================================================================

    def _mixer_loop(self):
        """Background thread that mixes audio into the ring buffer"""
        chunk_size = self.FRAME_SIZE

        while self.running:
            try:
                if not self.ring_buffer:
                    time.sleep(0.005)
                    continue

                space_available = self.ring_buffer.capacity - self.ring_buffer.frames_available
                if space_available < chunk_size:
                    time.sleep(0.001)
                    continue

                mixed_data = self._mix_audio_chunk(chunk_size)
                if not self.ring_buffer.write(mixed_data):
                    time.sleep(0.0005)

            except Exception as e:
                logger.error(f"Mixer loop error: {e}")
                time.sleep(0.05)

    def _mix_audio_chunk(self, num_frames: int):
        """Mix all active sources into a stereo output chunk"""
        output = np.zeros(num_frames * 2, dtype=np.float32)

        with self.device_lock:
            sources_to_remove = []

            active_sources = [(sid, src) for sid, src in self.sources.items()
                              if src.is_playing and src.samples is not None]

            for source_id, source in active_sources:
                samples_len = len(source.samples)
                if source.sample_offset >= samples_len:
                    if source.loop:
                        source.sample_offset = source.sample_offset % samples_len
                    else:
                        sources_to_remove.append(source_id)
                        continue

                # Early cull: skip inaudible 3D sounds
                if source.is_3d:
                    dx = source.position[0] - self.listener_position[0]
                    dy = source.position[1] - self.listener_position[1]
                    dz = source.position[2] - self.listener_position[2]
                    distance_sq = dx*dx + dy*dy + dz*dz
                    max_dist_sq = source.max_distance * source.max_distance

                    if distance_sq > max_dist_sq and source.min_volume <= 0:
                        source.sample_offset += num_frames
                        if source.sample_offset >= samples_len and not source.loop:
                            sources_to_remove.append(source_id)
                        continue

                # Get samples with pitch
                pitch = source.pitch if source.pitch > 0.01 else 1.0

                if pitch == 1.0:
                    samples_needed = num_frames
                else:
                    samples_needed = int(num_frames * pitch) + 1

                if source.loop and source.sample_offset + samples_needed > samples_len:
                    first_part = source.samples[source.sample_offset:]
                    remaining = samples_needed - len(first_part)
                    second_part = source.samples[:remaining]
                    raw_samples = np.concatenate([first_part, second_part])
                    end_offset = remaining
                else:
                    end_offset = min(source.sample_offset + samples_needed, samples_len)
                    raw_samples = source.samples[source.sample_offset:end_offset]

                if pitch != 1.0 and len(raw_samples) > 0:
                    frame_samples = self._apply_pitch_fast(raw_samples, pitch, num_frames)
                else:
                    frame_samples = raw_samples
                    if len(frame_samples) < num_frames:
                        frame_samples = np.pad(frame_samples, (0, num_frames - len(frame_samples)))

                source.sample_offset = end_offset

                # 3D spatialization
                if source.is_3d:
                    dx = source.position[0] - self.listener_position[0]
                    dy = source.position[1] - self.listener_position[1]
                    dz = source.position[2] - self.listener_position[2]
                    distance = math.sqrt(dx*dx + dy*dy + dz*dz)

                    # Air absorption (low-pass filter)
                    if distance > source.min_distance:
                        filter_range = max(1.0, source.max_distance - source.min_distance)
                        dist_factor = (distance - source.min_distance) / filter_range
                        lpf_intensity = max(0.0, min(1.0, dist_factor))

                        frame_samples, new_prior = self._apply_lowpass_mono(
                            frame_samples, lpf_intensity, source.lpf_prior
                        )
                        source.lpf_prior = new_prior

                    # Spatialization (HRTF or fast panning)
                    use_hrtf = False
                    if self.enable_hrtf and source.binaural_effect:
                        try:
                            stereo_out = self._apply_binaural(source, frame_samples)
                            if stereo_out is not None and len(stereo_out) > 0:
                                if len(stereo_out) < num_frames * 2:
                                    stereo_out = np.concatenate([stereo_out, np.zeros(num_frames * 2 - len(stereo_out), dtype=np.float32)])
                                elif len(stereo_out) > num_frames * 2:
                                    stereo_out = stereo_out[:num_frames * 2]
                                use_hrtf = True
                        except Exception:
                            pass

                    if not use_hrtf:
                        stereo_out = self._apply_binaural_fast(source, frame_samples, num_frames)

                    # Distance attenuation
                    if distance <= source.min_distance:
                        attenuation = 1.0
                    elif distance >= source.max_distance:
                        attenuation = source.min_volume
                    else:
                        attenuation = (source.min_distance / distance) ** 1.5
                        attenuation = max(source.min_volume, attenuation)
                else:
                    # 2D sound: duplicate mono to stereo
                    stereo_out = np.repeat(frame_samples[:num_frames], 2)
                    attenuation = 1.0

                # Fade-in
                fade_mult = 1.0
                if source.fading_in and source.fade_in_samples_remaining > 0:
                    samples_to_fade = min(source.fade_in_samples_remaining, num_frames)
                    fade_progress = 1.0 - (source.fade_in_samples_remaining / source.fade_in_samples_total)
                    fade_mult = min(1.0, fade_progress + (samples_to_fade / source.fade_in_samples_total))
                    source.fade_in_samples_remaining -= samples_to_fade
                    if source.fade_in_samples_remaining <= 0:
                        source.fading_in = False

                # Fade-out
                if source.fading_out and source.fade_samples_remaining > 0:
                    samples_to_fade = min(source.fade_samples_remaining, num_frames)
                    fade_progress = source.fade_samples_remaining / source.fade_samples_total
                    fade_mult *= fade_progress
                    source.fade_samples_remaining -= samples_to_fade
                    if source.fade_samples_remaining <= 0:
                        sources_to_remove.append(source_id)
                        continue

                # Mix into output
                vol = source.volume * attenuation * fade_mult
                if not isinstance(stereo_out, np.ndarray):
                    stereo_out = np.array(stereo_out, dtype=np.float32)
                mix_len = min(len(stereo_out), len(output))
                output[:mix_len] += stereo_out[:mix_len] * vol

            for source_id in sources_to_remove:
                self._remove_source(source_id)

        # Master volume headroom
        output *= 0.5

        # Soft-knee tanh limiter
        threshold = 0.7
        above_threshold = np.abs(output) > threshold
        if np.any(above_threshold):
            sign = np.sign(output)
            abs_output = np.abs(output)
            compressed = threshold + (1.0 - threshold) * np.tanh((abs_output - threshold) / (1.0 - threshold))
            output = np.where(above_threshold, sign * compressed, output)
        np.clip(output, -1.0, 1.0, out=output)

        return output

    # ========================================================================
    # Audio Processing
    # ========================================================================

    def _apply_pitch_fast(self, samples, pitch: float, num_frames: int):
        """Apply pitch via linear interpolation resampling"""
        if pitch == 1.0:
            return samples

        if not isinstance(samples, np.ndarray):
            samples = np.array(samples, dtype=np.float32)

        positions = np.arange(num_frames) * pitch
        indices = positions.astype(np.int32)
        fracs = positions - indices

        max_idx = len(samples) - 1
        indices = np.clip(indices, 0, max_idx)
        indices_next = np.clip(indices + 1, 0, max_idx)

        output = samples[indices] * (1.0 - fracs) + samples[indices_next] * fracs
        return output.astype(np.float32)

    def _apply_binaural_fast(self, source: AudioSource, mono_samples, num_frames: int):
        """Fast stereo panning using equal-power law"""
        dx = source.position[0] - self.listener_position[0]
        dy = source.position[1] - self.listener_position[1]

        cos_yaw = math.cos(-self.listener_yaw)
        sin_yaw = math.sin(-self.listener_yaw)
        rx = dx * cos_yaw - dy * sin_yaw
        ry = dx * sin_yaw + dy * cos_yaw

        dist_2d = math.sqrt(rx*rx + ry*ry)
        if dist_2d > 0.001:
            pan = max(-1.0, min(1.0, -ry / dist_2d))
        else:
            pan = 0.0

        angle = (pan + 1.0) * 0.25 * math.pi
        left_gain = math.cos(angle)
        right_gain = math.sin(angle)

        if not isinstance(mono_samples, np.ndarray):
            mono = np.array(mono_samples, dtype=np.float32)
        else:
            mono = mono_samples

        actual_frames = min(num_frames, len(mono))
        stereo_out = np.zeros(num_frames * 2, dtype=np.float32)
        stereo_out[0:actual_frames*2:2] = mono[:actual_frames] * left_gain
        stereo_out[1:actual_frames*2:2] = mono[:actual_frames] * right_gain
        return stereo_out

    def _apply_binaural(self, source: AudioSource, mono_samples):
        """Apply Steam Audio HRTF binaural effect"""
        try:
            if not self.phonon_lib or not self.hrtf or not source.binaural_effect:
                return None

            frame_size = self.FRAME_SIZE
            num_samples = len(mono_samples)
            if num_samples == 0:
                return None

            if isinstance(mono_samples, np.ndarray):
                if mono_samples.dtype != np.float32:
                    mono_samples = mono_samples.astype(np.float32)
            else:
                mono_samples = np.array(mono_samples, dtype=np.float32)

            if num_samples < frame_size:
                mono_chunk = np.zeros(frame_size, dtype=np.float32)
                mono_chunk[:num_samples] = mono_samples
            elif num_samples > frame_size:
                mono_chunk = mono_samples[:frame_size].copy()
            else:
                mono_chunk = mono_samples.copy()

            mono_chunk = np.ascontiguousarray(mono_chunk, dtype=np.float32)

            # Calculate direction from listener to source
            dx = source.position[0] - self.listener_position[0]
            dy = source.position[1] - self.listener_position[1]
            dz = source.position[2] - self.listener_position[2]

            # Rotate by listener yaw
            cos_yaw = math.cos(-self.listener_yaw)
            sin_yaw = math.sin(-self.listener_yaw)
            rx = dx * cos_yaw - dy * sin_yaw
            ry = dx * sin_yaw + dy * cos_yaw
            rz = dz

            # Normalize
            dist = math.sqrt(rx*rx + ry*ry + rz*rz)
            if dist > 0.001:
                rx /= dist
                ry /= dist
                rz /= dist
            else:
                rx, ry, rz = 1.0, 0.0, 0.0

            # Map to Steam Audio coordinates
            # Game: +X Forward, +Y Left, +Z Up
            # Steam Audio: +X Right, +Y Up, -Z Forward
            sx = -ry
            sy = rz
            sz = -rx

            params = IPLBinauralEffectParams()
            params.direction = IPLVector3(sx, sy, sz)
            params.interpolation = IPL_HRTFINTERPOLATION_BILINEAR
            params.spatialBlend = 1.0
            params.hrtf = self.hrtf
            params.peakDelays = None

            in_buffer = IPLAudioBuffer()
            in_buffer.numChannels = 1
            in_buffer.numSamples = frame_size

            out_buffer = IPLAudioBuffer()
            out_buffer.numChannels = 2
            out_buffer.numSamples = frame_size

            out_l = np.zeros(frame_size, dtype=np.float32)
            out_r = np.zeros(frame_size, dtype=np.float32)

            p_mono = mono_chunk.ctypes.data_as(POINTER(c_float))
            in_ptrs = (POINTER(c_float) * 1)()
            in_ptrs[0] = p_mono
            in_buffer.data = in_ptrs

            p_out_l = out_l.ctypes.data_as(POINTER(c_float))
            p_out_r = out_r.ctypes.data_as(POINTER(c_float))
            out_ptrs = (POINTER(c_float) * 2)()
            out_ptrs[0] = p_out_l
            out_ptrs[1] = p_out_r
            out_buffer.data = out_ptrs

            result = self.phonon_lib.iplBinauralEffectApply(
                source.binaural_effect,
                byref(params),
                byref(in_buffer),
                byref(out_buffer)
            )

            if result != IPL_STATUS_SUCCESS:
                return None

            actual_samples = min(num_samples, frame_size)
            stereo_out = np.empty(actual_samples * 2, dtype=np.float32)
            stereo_out[0::2] = out_l[:actual_samples]
            stereo_out[1::2] = out_r[:actual_samples]
            return stereo_out

        except Exception as e:
            logger.warning(f"HRTF processing error: {e}")
            return None

    def _apply_lowpass_mono(self, samples, intensity: float, prior: float):
        """1-pole IIR lowpass filter for air absorption"""
        if intensity <= 0.01:
            return samples, 0.0

        alpha = 1.0 - (0.9 * intensity)

        if isinstance(samples, np.ndarray):
            sample_list = samples.tolist()
        else:
            sample_list = list(samples)

        output = []
        prev = prior
        one_minus_alpha = 1.0 - alpha

        for s in sample_list:
            val = alpha * s + one_minus_alpha * prev
            output.append(val)
            prev = val

        return np.array(output, dtype=np.float32), prev

    def _remove_source(self, source_id: int):
        """Remove a source and clean up its binaural effect"""
        if source_id in self.sources:
            source = self.sources[source_id]
            if source.binaural_effect and self.phonon_lib:
                try:
                    effect = IPLBinauralEffect(source.binaural_effect)
                    self.phonon_lib.iplBinauralEffectRelease(byref(effect))
                except Exception:
                    pass
            del self.sources[source_id]

    # ========================================================================
    # Sound Loading
    # ========================================================================

    def load_sound(self, sound_id: str, filepath: str) -> bool:
        """Load and cache a sound file"""
        if sound_id in self.sounds:
            return True

        try:
            if not os.path.exists(filepath):
                base, ext = os.path.splitext(filepath)
                for try_ext in ['.ogg', '.wav', '.flac']:
                    try_path = base + try_ext
                    if os.path.exists(try_path):
                        filepath = try_path
                        break
                else:
                    logger.warning(f"Sound file not found: {filepath}")
                    return False

            self.sounds[sound_id] = {
                'filepath': filepath,
                'samples': None,
                'sample_rate': self.SAMPLE_RATE,
            }

            # Eager decode
            self._decode_sound(sound_id)
            return True

        except Exception as e:
            logger.error(f"Failed to load sound {sound_id}: {e}")
            return False

    def _decode_sound(self, sound_id: str):
        """Decode a sound file to mono float32 samples at engine sample rate"""
        if sound_id not in self.sounds:
            return None

        sound_data = self.sounds[sound_id]
        if sound_data['samples'] is not None:
            return sound_data['samples']

        try:
            filepath = sound_data['filepath']

            # Use soundfile for loading (handles WAV, OGG, FLAC)
            data, samplerate = sf.read(filepath, dtype='float32')

            # Convert to mono if needed
            if data.ndim > 1:
                samples = data.mean(axis=1)
            else:
                samples = data

            samples = samples.astype(np.float32)

            # Resample if needed
            if samplerate != self.SAMPLE_RATE:
                samples = self._resample(samples, samplerate, self.SAMPLE_RATE)

            # Trim trailing artifacts
            samples = self._trim_trailing_artifacts(samples, self.SAMPLE_RATE)

            # Micro-fade to prevent clicks (2ms)
            fade_samples = int(self.SAMPLE_RATE * 2 / 1000)
            if fade_samples > 0 and len(samples) > fade_samples:
                fade_env = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
                samples[-fade_samples:] *= fade_env

            sound_data['samples'] = samples
            sound_data['sample_rate'] = self.SAMPLE_RATE
            return samples

        except Exception as e:
            logger.error(f"Failed to decode sound {sound_id}: {e}")
            return None

    def _trim_trailing_artifacts(self, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        """Detect and trim trailing pops/artifacts"""
        if len(samples) < sample_rate * 0.5:
            return samples

        threshold = 0.01
        min_silence_samples = int(sample_rate * 20 / 1000)

        active_indices = np.where(np.abs(samples) >= threshold)[0]
        if len(active_indices) == 0:
            return samples

        last_index = active_indices[-1]
        ind_diff = np.diff(active_indices)
        large_gaps = np.where(ind_diff > min_silence_samples)[0]

        if len(large_gaps) > 0:
            last_gap_idx = large_gaps[-1]
            pop_start_idx = active_indices[last_gap_idx + 1]
            half_second_samples = int(sample_rate * 0.5)
            dist_from_end = len(samples) - pop_start_idx

            if dist_from_end <= half_second_samples:
                cut_point = active_indices[last_gap_idx] + 1
                return samples[:cut_point]

        return samples[:last_index + 1]

    def _resample(self, samples, from_rate: int, to_rate: int):
        """Resample audio using linear interpolation"""
        if from_rate == to_rate:
            return samples

        if not isinstance(samples, np.ndarray):
            samples = np.array(samples, dtype=np.float32)

        ratio = to_rate / from_rate
        new_length = int(len(samples) * ratio)
        if new_length == 0:
            return np.array([], dtype=np.float32)

        old_positions = np.arange(len(samples))
        new_positions = np.linspace(0, len(samples) - 1, new_length)
        output = np.interp(new_positions, old_positions, samples)
        return output.astype(np.float32)

    # ========================================================================
    # Public API
    # ========================================================================

    def play_sound(self, sound_id: str, x: float, y: float, z: float = 0.0,
                   volume: float = 1.0, pitch: float = 1.0, loop: bool = False,
                   min_distance: float = 1.0, max_distance: float = 100.0,
                   min_volume: float = 0.0) -> Optional[int]:
        """Play a 3D positioned sound. Returns source_id or None."""
        if not self.initialized or sound_id not in self.sounds:
            return None

        try:
            samples = self._decode_sound(sound_id)
            if samples is None:
                return None

            source_id = self.next_source_id
            self.next_source_id += 1
            if self.next_source_id > self.MAX_SOURCE_ID:
                self.next_source_id = 1

            binaural_effect = self._create_binaural_effect()

            fade_in_samples = int(self.SAMPLE_RATE * 10 / 1000)  # 10ms fade-in

            source = AudioSource(
                source_id=source_id,
                sound_id=sound_id,
                position=(x, y, z),
                volume=volume,
                pitch=pitch,
                loop=loop,
                is_3d=True,
                samples=samples.copy(),
                sample_rate=self.SAMPLE_RATE,
                is_playing=True,
                binaural_effect=binaural_effect,
                min_distance=min_distance,
                max_distance=max_distance,
                min_volume=min_volume,
                fading_in=True,
                fade_in_samples_remaining=fade_in_samples,
                fade_in_samples_total=fade_in_samples,
            )

            with self.device_lock:
                self.sources[source_id] = source

            return source_id

        except Exception as e:
            logger.error(f"Error playing sound {sound_id}: {e}")
            return None

    def stop_sound(self, source_id: int):
        """Stop a playing sound with a micro-fade to prevent pops"""
        with self.device_lock:
            if source_id in self.sources:
                source = self.sources[source_id]
                source.fading_out = True
                source.fade_samples_remaining = int(self.SAMPLE_RATE * 15 / 1000)  # 15ms fade
                source.fade_samples_total = source.fade_samples_remaining

    def update_source_position(self, source_id: int, x: float, y: float, z: float = 0.0,
                               volume: float = None):
        """Update a source's position and optionally volume"""
        with self.device_lock:
            if source_id in self.sources:
                self.sources[source_id].position = (x, y, z)
                if volume is not None:
                    self.sources[source_id].volume = max(0.0, min(1.0, volume))

    def is_sound_playing(self, source_id: int) -> bool:
        """Check if a source is still playing"""
        with self.device_lock:
            if source_id not in self.sources:
                return False
            source = self.sources[source_id]
            return source.is_playing and not source.fading_out

    def set_listener(self, x: float, y: float, z: float, yaw: float):
        """Update listener position and yaw (radians)"""
        self.listener_position = (x, y, z)
        self.listener_yaw = yaw

    # ========================================================================
    # Shutdown
    # ========================================================================

    def shutdown(self):
        """Shutdown the audio engine and release all resources"""
        if not self.initialized:
            return

        try:
            self.running = False
            self.initialized = False

            if self.mixer_thread and self.mixer_thread.is_alive():
                try:
                    self.mixer_thread.join(timeout=1.0)
                except Exception:
                    pass
            self.mixer_thread = None
            self.ring_buffer = None

            if self.stream:
                try:
                    self.stream.stop_stream()
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None

            if self.pa:
                try:
                    self.pa.terminate()
                except Exception:
                    pass
                self.pa = None

            if self.low_latency_backend:
                try:
                    self.low_latency_backend.close()
                except Exception:
                    pass
                self.low_latency_backend = None

            for source_id in list(self.sources.keys()):
                source = self.sources.get(source_id)
                if source and source.binaural_effect and self.phonon_lib:
                    try:
                        effect_ptr = c_void_p(source.binaural_effect)
                        self.phonon_lib.iplBinauralEffectRelease(byref(effect_ptr))
                    except Exception:
                        pass
            self.sources.clear()

            if self.phonon_lib and self.hrtf:
                try:
                    hrtf_ptr = c_void_p(self.hrtf)
                    self.phonon_lib.iplHRTFRelease(byref(hrtf_ptr))
                except Exception:
                    pass
                self.hrtf = None

            if self.context and self.phonon_lib:
                try:
                    context_ptr = c_void_p(self.context)
                    self.phonon_lib.iplContextRelease(byref(context_ptr))
                except Exception:
                    pass
                self.context = None

            self.sounds.clear()
            logger.info("FA11y audio engine shut down")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
