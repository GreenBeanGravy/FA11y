import numpy as np
import soundfile as sf
import pyaudio
import threading
from scipy import signal
import time
import os
from typing import Tuple, Optional

class SpatialAudio:
    def __init__(self, audio_file, chunk_size=4096):
        self.audio_file = audio_file
        self.chunk_size = chunk_size
        self.volume = 1.0
        self.audio_data = None
        self.sample_rate = None
        self.pyaudio_instance = None
        self.original_audio_data = None
        
        self.is_playing = False
        self.stop_playback = threading.Event()
        self.playback_lock = threading.Lock()
        self.current_left_weight = 0.5
        self.current_right_weight = 0.5
        self.current_volume = 1.0
        self.playback_thread = None
        
        self.audio_initialized = False
        self.initialization_attempted = False
        
        # Volume management
        self.master_volume = 1.0
        self.individual_volume = 1.0
        
        self.load_audio()
        self.initialize_audio()

    def initialize_audio(self):
        """Initialize PyAudio with robust error handling"""
        if self.initialization_attempted:
            return
            
        self.initialization_attempted = True
        
        try:
            self.pyaudio_instance = pyaudio.PyAudio()
            self.audio_initialized = True
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
        """Open a PyAudio stream with enhanced error handling"""
        if not self.audio_initialized or self.pyaudio_instance is None:
            return None
            
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                stream = self.pyaudio_instance.open(
                    format=pyaudio.paInt16, 
                    channels=2, 
                    rate=int(self.sample_rate), 
                    output=True, 
                    frames_per_buffer=self.chunk_size,
                    stream_callback=None
                )
                return stream
                
            except Exception:
                if attempt == max_attempts - 1:
                    return None
                time.sleep(0.01)
        
        return None

    def set_volume(self, volume):
        """Set the global volume"""
        self.volume = max(0.0, min(1.0, volume))
        with self.playback_lock:
            self.current_volume = self.volume

    def set_master_volume(self, volume):
        """Set the master volume"""
        self.master_volume = max(0.0, min(1.0, volume))

    def set_individual_volume(self, volume):
        """Set the individual volume for this sound"""
        self.individual_volume = max(0.0, min(1.0, volume))

    def apply_pitch_shift(self, factor):
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

    def update_panning(self, left_weight, right_weight, volume=None):
        """Update panning parameters while audio is playing"""
        with self.playback_lock:
            self.current_left_weight = max(0.0, min(1.0, left_weight))
            self.current_right_weight = max(0.0, min(1.0, right_weight))
            if volume is not None:
                self.current_volume = max(0.0, min(1.0, volume))

    def update_spatial_position(self, distance: float, relative_angle: float, volume: float = 1.0):
        """Update spatial position using distance and relative angle"""
        left_weight, right_weight = self.calculate_stereo_weights(relative_angle)
        final_volume = volume * self.master_volume * self.individual_volume
        self.update_panning(left_weight, right_weight, final_volume)
            
    def play_audio_with_live_panning(self):
        """Play audio with continuously updated panning parameters"""
        if self.audio_data is None or len(self.audio_data) == 0:
            return
        
        stream = self.open_audio_stream()
        if stream is None:
            return
        
        try:
            audio_int16 = (self.audio_data * 12000).astype(np.int16)
            total_frames = len(audio_int16)
            frame_index = 0
            
            while frame_index < total_frames and not self.stop_playback.is_set():
                try:
                    chunk_size = min(self.chunk_size, total_frames - frame_index)
                    audio_chunk = audio_int16[frame_index:frame_index + chunk_size]
                    
                    with self.playback_lock:
                        left_weight = self.current_left_weight
                        right_weight = self.current_right_weight
                        volume = self.current_volume * self.master_volume * self.individual_volume
                    
                    left_channel = (audio_chunk[:, 0] * left_weight * volume).astype(np.int16)
                    right_channel = (audio_chunk[:, 1] * right_weight * volume).astype(np.int16)
                    stereo_chunk = np.column_stack((left_channel, right_channel))
                    
                    stream.write(stereo_chunk.tobytes(), exception_on_underflow=False)
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

    def play_audio(self, left_weight=None, right_weight=None, volume=1.0, pitch_shift=None, 
                  distance=None, relative_angle=None):
        """Play audio with either legacy weights or new spatial parameters"""
        if self.is_playing:
            self.stop()
            time.sleep(0.02)
            
        if self.audio_data is None or not self.audio_initialized:
            return

        # Handle new spatial parameters
        if distance is not None and relative_angle is not None:
            left_weight, right_weight = self.calculate_stereo_weights(relative_angle)
            
            # Check if sound is behind and should play twice
            if self.is_behind(relative_angle):
                self.play_behind_sound(distance, relative_angle, volume, pitch_shift)
                return
        
        # Use legacy parameters if spatial ones not provided
        if left_weight is None or right_weight is None:
            left_weight = right_weight = 0.5

        def audio_playback_worker():
            try:
                with self.playback_lock:
                    self.is_playing = True
                    self.stop_playback.clear()
                
                if pitch_shift is not None and pitch_shift != 1.0:
                    self.apply_pitch_shift(pitch_shift)
                else:
                    if self.original_audio_data is not None:
                        self.audio_data = np.copy(self.original_audio_data)

                final_volume = volume * self.master_volume * self.individual_volume
                with self.playback_lock:
                    self.current_left_weight = max(0.0, min(1.0, left_weight))
                    self.current_right_weight = max(0.0, min(1.0, right_weight))
                    self.current_volume = max(0.0, min(1.0, final_volume))
                
                self.play_audio_with_live_panning()

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

    def play_behind_sound(self, distance: float, relative_angle: float, volume: float, pitch_shift=None):
        """Play sound twice with delay to indicate it's behind"""
        def behind_audio_worker():
            try:
                # Prepare audio data
                left_weight, right_weight = self.calculate_stereo_weights(relative_angle)
                final_volume = volume * self.master_volume * self.individual_volume
                
                with self.playback_lock:
                    self.is_playing = True
                    self.stop_playback.clear()
                
                if pitch_shift is not None and pitch_shift != 1.0:
                    self.apply_pitch_shift(pitch_shift)
                else:
                    if self.original_audio_data is not None:
                        self.audio_data = np.copy(self.original_audio_data)
    
                with self.playback_lock:
                    self.current_left_weight = max(0.0, min(1.0, left_weight))
                    self.current_right_weight = max(0.0, min(1.0, right_weight))
                    self.current_volume = max(0.0, min(1.0, final_volume))
                
                # Start first sound in a separate thread
                first_sound_thread = threading.Thread(target=self.play_audio_with_live_panning, daemon=True)
                first_sound_thread.start()
                
                # Wait 0.15 seconds then start second sound
                time.sleep(0.15)
                
                # Start second sound if not stopped
                if not self.stop_playback.is_set():
                    second_sound_thread = threading.Thread(target=self.play_audio_with_live_panning, daemon=True)
                    second_sound_thread.start()
                    
                    # Wait for both threads to complete
                    first_sound_thread.join()
                    second_sound_thread.join()
                else:
                    first_sound_thread.join()
    
            except Exception:
                pass
            finally:
                with self.playback_lock:
                    self.is_playing = False
    
        if self.playback_thread and self.playback_thread.is_alive():
            self.stop_playback.set()
            self.playback_thread.join(timeout=0.1)
            
        self.playback_thread = threading.Thread(target=behind_audio_worker, daemon=True)
        self.playback_thread.start()
    
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

    @staticmethod
    def calculate_spatial_panning(player_position: Tuple[int, int], 
                                player_angle: float, 
                                target_position: Tuple[int, int]) -> Tuple[float, float]:
        """
        Calculate stereo panning weights for spatial audio based on player and target positions.
        
        Args:
            player_position: Player's current position (x, y)
            player_angle: Player's facing direction in degrees
            target_position: Target object's position (x, y)
            
        Returns:
            Tuple of (left_weight, right_weight) for stereo panning
        """
        try:
            # Calculate vector from player to target
            target_vector = np.array(target_position) - np.array(player_position)
            
            # Calculate target angle in world coordinates
            target_angle = (90 - np.degrees(np.arctan2(-target_vector[1], target_vector[0]))) % 360
            
            # Calculate relative angle between player facing direction and target
            relative_angle = (target_angle - player_angle + 180) % 360 - 180
            
            return SpatialAudio.calculate_stereo_weights(relative_angle)
            
        except Exception:
            # Fallback to center panning on error
            return 0.5, 0.5

    @staticmethod
    def calculate_distance_and_angle(player_position: Tuple[int, int], 
                                   player_angle: float, 
                                   target_position: Tuple[int, int]) -> Tuple[float, float]:
        """
        Calculate distance and relative angle from player to target.
        
        Args:
            player_position: Player's current position (x, y)
            player_angle: Player's facing direction in degrees
            target_position: Target object's position (x, y)
            
        Returns:
            Tuple of (distance, relative_angle) where relative_angle is in degrees
        """
        try:
            # Calculate vector from player to target
            target_vector = np.array(target_position) - np.array(player_position)
            
            # Calculate distance (using the same scale factor as the game)
            distance = np.linalg.norm(target_vector) * 2.65
            
            # Calculate target angle in world coordinates
            target_angle = (90 - np.degrees(np.arctan2(-target_vector[1], target_vector[0]))) % 360
            
            # Calculate relative angle between player facing direction and target
            relative_angle = (target_angle - player_angle + 180) % 360 - 180
            
            return distance, relative_angle
            
        except Exception:
            return 0.0, 0.0

    @staticmethod
    def calculate_stereo_weights(relative_angle: float) -> Tuple[float, float]:
        """
        Calculate stereo weights based on relative angle.
        
        Args:
            relative_angle: Angle relative to player facing direction (-180 to 180)
            
        Returns:
            Tuple of (left_weight, right_weight)
        """
        # More accurate panning calculation
        # Use a smoother curve for better directional accuracy
        angle_rad = np.radians(relative_angle)
        
        # Enhanced panning formula for better front/back distinction
        # Use sin for left/right and adjust for front/back positioning
        pan_factor = np.sin(angle_rad)
        
        # Apply non-linear curve for better spatial accuracy
        if abs(pan_factor) > 0.1:
            pan_factor = np.sign(pan_factor) * (abs(pan_factor) ** 0.7)
        
        # Convert to stereo weights
        left_weight = np.clip((1 - pan_factor) / 2, 0.1, 0.9)
        right_weight = np.clip((1 + pan_factor) / 2, 0.1, 0.9)
        
        return left_weight, right_weight

    @staticmethod
    def is_behind(relative_angle: float) -> bool:
        """
        Check if the sound source is behind the player.
        
        Args:
            relative_angle: Angle relative to player facing direction (-180 to 180)
            
        Returns:
            True if the source is behind the player
        """
        # Consider sounds between 90 and 270 degrees (135 to 225 for stricter behind)
        return abs(relative_angle) > 90

    @staticmethod
    def get_volume_from_config(config, volume_key: str, master_key: str = 'MasterVolume', 
                             fallback: float = 1.0) -> Tuple[float, float]:
        """
        Get master and individual volume from config.
        
        Args:
            config: Configuration object
            volume_key: Key for individual volume setting
            master_key: Key for master volume setting
            fallback: Fallback volume value
            
        Returns:
            Tuple of (master_volume, individual_volume)
        """
        try:
            from lib.utilities.utilities import get_config_float
            master_volume = get_config_float(config, master_key, 1.0)
            individual_volume = get_config_float(config, volume_key, fallback)
            return master_volume, individual_volume
        except Exception:
            return 1.0, fallback