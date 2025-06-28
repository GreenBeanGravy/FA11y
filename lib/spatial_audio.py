import numpy as np
import soundfile as sf
import pyaudio
import threading
import time
import os
from typing import Optional, Tuple, Union
from scipy import signal

# Import spaudiopy components
try:
    import spaudiopy as spa
    SPAUDIOPY_AVAILABLE = True
except ImportError:
    SPAUDIOPY_AVAILABLE = False
    print("Warning: spaudiopy not available, falling back to simple panning")

class SpatialAudioEngine:
    """Centralized spatial audio engine with player direction tracking"""
    
    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        self.current_player_direction = 0.0  # Current player heading in degrees
        self.direction_lock = threading.RLock()
        
        # Initialize HRTF system if available
        self.hrtf_initialized = False
        self.hrirs = None
        
        if SPAUDIOPY_AVAILABLE:
            try:
                self.hrirs = spa.io.load_hrirs(sample_rate)
                self.hrtf_initialized = True
            except Exception as e:
                self.hrtf_initialized = False
        
    def update_player_direction(self, direction_degrees: float):
        """Update the current player direction in degrees"""
        with self.direction_lock:
            self.current_player_direction = direction_degrees % 360
    
    def get_player_direction(self) -> float:
        """Get the current player direction in degrees"""
        with self.direction_lock:
            return self.current_player_direction
    
    def calculate_relative_direction(self, target_azimuth: float) -> float:
        """Calculate relative direction from player to target"""
        with self.direction_lock:
            relative_angle = (target_azimuth - self.current_player_direction + 180) % 360 - 180
            return relative_angle

# Global spatial audio engine instance
_spatial_engine = None

def get_spatial_engine() -> SpatialAudioEngine:
    """Get or create the global spatial audio engine"""
    global _spatial_engine
    if _spatial_engine is None:
        _spatial_engine = SpatialAudioEngine()
    return _spatial_engine

class SpatialAudio:
    """Enhanced spatial audio player with HRTF support and intuitive API"""
    
    def __init__(self, audio_file: str, chunk_size: int = 4096):
        self.audio_file = audio_file
        self.chunk_size = chunk_size
        self.volume = 1.5  # Increased default volume by 50%
        self.audio_data = None
        self.sample_rate = None
        self.pyaudio_instance = None
        self.original_audio_data = None
        
        # Playback control
        self.is_playing = False
        self.stop_playback = threading.Event()
        self.playback_lock = threading.RLock()
        self.playback_thread = None
        
        # Spatial audio state
        self.current_azimuth = 0.0      # Target azimuth in degrees
        self.current_elevation = 0.0    # Target elevation in degrees  
        self.current_distance = 1.0     # Distance in meters
        self.current_volume = 1.0
        self.use_player_direction = True # Whether to track player direction
        
        # Audio system initialization
        self.audio_initialized = False
        self.initialization_attempted = False
        
        # Get spatial engine reference
        self.spatial_engine = get_spatial_engine()
        
        self.load_audio()
        self.initialize_audio()

    def initialize_audio(self):
        """Initialize PyAudio with robust error handling and laptop speaker compatibility"""
        if self.initialization_attempted:
            return
            
        self.initialization_attempted = True
        
        try:
            self.pyaudio_instance = pyaudio.PyAudio()
            
            # Test if we can actually create a stream (some laptop speakers are picky)
            try:
                test_stream = self.pyaudio_instance.open(
                    format=pyaudio.paInt16,
                    channels=2,
                    rate=44100,
                    output=True,
                    frames_per_buffer=1024
                )
                test_stream.close()
                self.audio_initialized = True
            except Exception:
                # Try mono output for problematic laptop speakers
                try:
                    test_stream = self.pyaudio_instance.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=44100,
                        output=True,
                        frames_per_buffer=1024
                    )
                    test_stream.close()
                    self.audio_initialized = True
                except Exception:
                    self.pyaudio_instance.terminate()
                    self.pyaudio_instance = None
                    self.audio_initialized = False
                    
        except Exception:
            self.pyaudio_instance = None
            self.audio_initialized = False

    def load_audio(self):
        """Load and normalize the audio file"""
        if not self.audio_file or not sf:
            return
            
        try:
            self.audio_data, self.sample_rate = sf.read(self.audio_file)
            
            if self.audio_data.ndim == 1:
                self.audio_data = np.column_stack((self.audio_data, self.audio_data))
                
            self.audio_data = self.audio_data.astype(np.float32)
            
            max_val = np.max(np.abs(self.audio_data))
            if max_val > 0:
                self.audio_data = self.audio_data / (max_val * 1.2)
                
            self.original_audio_data = np.copy(self.audio_data)
            
        except Exception:
            self.audio_data = None
            self.sample_rate = None

    def open_audio_stream(self):
        """Open a PyAudio stream with enhanced error handling and better laptop speaker compatibility"""
        if not self.audio_initialized or self.pyaudio_instance is None:
            return None
            
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Try different audio configurations for better laptop compatibility
                configs_to_try = [
                    # Primary config
                    {
                        'format': pyaudio.paInt16,
                        'channels': 2,
                        'rate': int(self.sample_rate),
                        'output': True,
                        'frames_per_buffer': self.chunk_size
                    },
                    # Fallback with smaller buffer
                    {
                        'format': pyaudio.paInt16,
                        'channels': 2,
                        'rate': int(self.sample_rate),
                        'output': True,
                        'frames_per_buffer': 1024
                    },
                    # Fallback with different sample rate
                    {
                        'format': pyaudio.paInt16,
                        'channels': 2,
                        'rate': 44100,
                        'output': True,
                        'frames_per_buffer': 1024
                    }
                ]
                
                for config in configs_to_try:
                    try:
                        stream = self.pyaudio_instance.open(**config)
                        return stream
                    except Exception:
                        continue
                        
                return None
                
            except Exception:
                if attempt == max_attempts - 1:
                    return None
                time.sleep(0.01)
        
        return None

    def set_volume(self, volume: float):
        """Set the global volume"""
        self.volume = max(0.0, min(1.0, volume))
        with self.playback_lock:
            self.current_volume = self.volume

    def apply_pitch_shift(self, factor: float):
        """Apply pitch shift and resample the audio"""
        if self.original_audio_data is not None and factor != 1.0:
            try:
                new_length = int(len(self.original_audio_data) / factor)
                self.audio_data = signal.resample(self.original_audio_data, new_length)
            except Exception:
                self.audio_data = np.copy(self.original_audio_data)
        else:
            if self.original_audio_data is not None:
                self.audio_data = np.copy(self.original_audio_data)

    def update_spatial_position(self, azimuth: float, elevation: float = 0.0, 
                              distance: float = 1.0, volume: Optional[float] = None):
        """Update spatial position parameters while audio is playing"""
        with self.playback_lock:
            self.current_azimuth = azimuth % 360
            self.current_elevation = max(-90, min(90, elevation))
            self.current_distance = max(0.1, distance)
            if volume is not None:
                self.current_volume = max(0.0, min(1.0, volume))

    def calculate_hrtf_audio(self, audio_chunk: np.ndarray) -> np.ndarray:
        """Apply HRTF processing to audio chunk"""
        if not self.spatial_engine.hrtf_initialized:
            return self._calculate_simple_panning(audio_chunk)
        
        try:
            # Get current spatial parameters
            with self.playback_lock:
                azimuth = self.current_azimuth
                elevation = self.current_elevation
                distance = self.current_distance
                volume = self.current_volume * self.volume
            
            # Apply player direction if enabled
            if self.use_player_direction:
                relative_angle = self.spatial_engine.calculate_relative_direction(azimuth)
                # Use original azimuth calculation (removed negative)
                azimuth_rad = np.radians(relative_angle)
            else:
                azimuth_rad = np.radians(azimuth)
            
            elevation_rad = np.radians(elevation)
            
            # Convert to spherical coordinates (zenith angle)
            zenith_rad = np.pi/2 - elevation_rad
            
            # Get nearest HRIR
            h_l, h_r = self.spatial_engine.hrirs.nearest_hrirs(azimuth_rad, zenith_rad)
            
            # Apply distance attenuation
            distance_factor = 1.0 / max(distance, 0.1)
            distance_factor = min(distance_factor, 10.0)  # Limit max amplification
            
            # Convert audio to mono for HRTF processing
            if audio_chunk.shape[1] == 2:
                mono_audio = np.mean(audio_chunk, axis=1)
            else:
                mono_audio = audio_chunk[:, 0]
            
            # Apply HRTF convolution
            left_output = np.convolve(mono_audio, h_l, mode='same') * volume * distance_factor
            right_output = np.convolve(mono_audio, h_r, mode='same') * volume * distance_factor
            
            # Combine to stereo
            stereo_output = np.column_stack((left_output, right_output))
            
            return stereo_output.astype(np.int16)
            
        except Exception:
            # Fallback to simple panning
            return self._calculate_simple_panning(audio_chunk)

    def _calculate_simple_panning(self, audio_chunk: np.ndarray) -> np.ndarray:
        """Fallback simple panning calculation"""
        with self.playback_lock:
            azimuth = self.current_azimuth
            volume = self.current_volume * self.volume
            distance = self.current_distance
        
        # Apply player direction if enabled
        if self.use_player_direction:
            relative_angle = self.spatial_engine.calculate_relative_direction(azimuth)
        else:
            relative_angle = azimuth
        
        # Convert to pan (-1 to 1) - Back to original calculation
        pan = np.clip(relative_angle / 90, -1, 1)
        left_weight = np.clip((1 - pan) / 2, 0, 1)
        right_weight = np.clip((1 + pan) / 2, 0, 1)
        
        # Apply much gentler distance attenuation - sounds audible at much greater distances
        max_audible_distance = 600.0  # Increased from 500
        distance_factor = max(0.3, 1.0 - (distance / max_audible_distance))  # Increased minimum from 0.2 to 0.3
        
        final_volume = volume * distance_factor
        
        left_channel = (audio_chunk[:, 0] * left_weight * final_volume).astype(np.int16)
        right_channel = (audio_chunk[:, 1] * right_weight * final_volume).astype(np.int16)
        
        return np.column_stack((left_channel, right_channel))

    def play_audio_with_live_processing(self):
        """Play audio with continuously updated spatial processing"""
        if self.audio_data is None or len(self.audio_data) == 0:
            return
        
        stream = self.open_audio_stream()
        if stream is None:
            return
        
        try:
            # Increased amplitude multiplier for louder output
            audio_int16 = (self.audio_data * 18000).astype(np.int16)  # Increased from 12000
            total_frames = len(audio_int16)
            frame_index = 0
            
            while frame_index < total_frames and not self.stop_playback.is_set():
                try:
                    chunk_size = min(self.chunk_size, total_frames - frame_index)
                    audio_chunk = audio_int16[frame_index:frame_index + chunk_size]
                    
                    # Apply spatial audio processing
                    processed_chunk = self.calculate_hrtf_audio(audio_chunk)
                    
                    stream.write(processed_chunk.tobytes(), exception_on_underflow=False)
                    frame_index += chunk_size
                    
                except Exception:
                    frame_index += self.chunk_size
                    continue
                    
        except Exception:
            pass
        finally:
            try:
                if stream.is_active():
                    stream.stop_stream()
                stream.close()
            except Exception:
                pass
            
            with self.playback_lock:
                self.is_playing = False

    def play_spatial(self, azimuth: float, elevation: float = 0.0, distance: float = 1.0, 
                    volume: float = 1.0, pitch_shift: Optional[float] = None,
                    use_player_direction: bool = True):
        """
        Play audio with spatial positioning
        
        Args:
            azimuth: Direction in degrees (0 = North, 90 = East, 180 = South, 270 = West)
            elevation: Elevation in degrees (-90 to 90, 0 = horizon)
            distance: Distance in meters (affects volume attenuation)
            volume: Volume multiplier (0.0 to 1.0)
            pitch_shift: Pitch shift factor (None for no change)
            use_player_direction: Whether to account for player's facing direction
        """
        if self.is_playing:
            self.stop()
            time.sleep(0.02)
            
        if self.audio_data is None or not self.audio_initialized:
            return

        def audio_playback_worker():
            try:
                with self.playback_lock:
                    self.is_playing = True
                    self.stop_playback.clear()
                    self.use_player_direction = use_player_direction
                
                if pitch_shift is not None and pitch_shift != 1.0:
                    self.apply_pitch_shift(pitch_shift)
                else:
                    if self.original_audio_data is not None:
                        self.audio_data = np.copy(self.original_audio_data)

                # Set initial spatial parameters with increased volume
                self.update_spatial_position(azimuth, elevation, distance, volume * 1.5)  # 50% volume boost
                
                self.play_audio_with_live_processing()

            except Exception:
                pass
            finally:
                with self.playback_lock:
                    self.is_playing = False

        if self.playback_thread and self.playback_thread.is_alive():
            self.stop_playback.set()
            self.playback_thread.join(timeout=0.1)
            
        self.playback_thread = threading.Thread(target=audio_playback_worker, daemon=True)
        self.playback_thread.start()

    def play_audio(self, left_weight: float, right_weight: float, volume: float = 1.0, 
                  pitch_shift: Optional[float] = None):
        """
        Legacy method for backward compatibility
        Converts left/right weights to spatial position
        """
        # Convert weights to azimuth
        pan = (right_weight - left_weight) / max(left_weight + right_weight, 0.001)
        azimuth = pan * 90  # Convert pan to degrees
        
        self.play_spatial(azimuth=azimuth, volume=volume * 1.5, pitch_shift=pitch_shift, 
                         use_player_direction=False)  # 50% volume boost

    def update_panning(self, left_weight: float, right_weight: float, volume: Optional[float] = None):
        """Legacy method for backward compatibility"""
        pan = (right_weight - left_weight) / max(left_weight + right_weight, 0.001)
        azimuth = pan * 90
        if volume is not None:
            volume *= 1.5  # 50% volume boost
        self.update_spatial_position(azimuth=azimuth, volume=volume)

    def stop(self):
        """Stop audio playback"""
        self.stop_playback.set()
        
        with self.playback_lock:
            self.is_playing = False
        
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=0.15)

    def cleanup(self):
        """Clean up PyAudio resources"""
        self.stop()
        
        if self.pyaudio_instance:
            try:
                self.pyaudio_instance.terminate()
            except Exception:
                pass
            finally:
                self.pyaudio_instance = None
                self.audio_initialized = False