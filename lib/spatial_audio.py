import numpy as np
import soundfile as sf
import math
import pyaudio
import threading
from scipy import signal
import time

class SpatialAudio:
    def __init__(self, audio_file, chunk_size=1024):
        self.audio_file = audio_file
        self.chunk_size = chunk_size
        self.volume = 1.0
        self.audio_data = None
        self.sample_rate = None
        self.pyaudio_instance = pyaudio.PyAudio()
        self.original_audio_data = None  # Store the original unmodified audio data
        
        # New properties for live panning
        self.is_playing = False
        self.stop_playback = threading.Event()
        self.playback_lock = threading.Lock()
        self.current_left_weight = 0.5
        self.current_right_weight = 0.5
        self.current_volume = 1.0
        self.current_pitch_shift = None
        self.playback_thread = None

        # Load audio when initializing
        self.load_audio()

    def load_audio(self):
        """Load and normalize the audio file."""
        try:
            self.audio_data, self.sample_rate = sf.read(self.audio_file)
            if self.audio_data.ndim == 1:
                # Convert mono to stereo
                self.audio_data = np.column_stack((self.audio_data, self.audio_data))
            self.audio_data = self.audio_data.astype(np.float32)
            self.audio_data /= np.max(np.abs(self.audio_data))  # Normalize
            self.original_audio_data = np.copy(self.audio_data)  # Keep a copy of the original data
        except Exception as e:
            print(f"Error loading audio: {e}")
            self.audio_data = None
            self.sample_rate = None

    def open_audio_stream(self):
        """Open a PyAudio stream for playback."""
        return self.pyaudio_instance.open(
            format=pyaudio.paInt16, 
            channels=2, 
            rate=self.sample_rate, 
            output=True, 
            frames_per_buffer=self.chunk_size
        )

    def set_volume(self, volume):
        """Set the global volume."""
        self.volume = max(0.0, min(1.0, volume))
        # Also update current volume if playing
        if self.is_playing:
            self.current_volume = volume

    def apply_pitch_shift(self, factor):
        """Apply the pitch shift and resample the audio."""
        if factor != 1.0:  # Only apply if pitch shift is different from 1.0 (no shift)
            self.audio_data = signal.resample(self.original_audio_data, int(len(self.original_audio_data) / factor))
        else:
            # Restore the original audio data if pitch shift is not applied
            self.audio_data = np.copy(self.original_audio_data)

    def create_stereo_audio(self, left_weight, right_weight):
        """Apply the stereo weights and create the stereo-balanced audio."""
        left_channel = self.audio_data[:, 0] * left_weight
        right_channel = self.audio_data[:, 1] * right_weight
        return np.column_stack((left_channel, right_channel))

    def update_panning(self, left_weight, right_weight, volume=None):
        """Update panning parameters while audio is playing."""
        with self.playback_lock:
            self.current_left_weight = max(0.0, min(1.0, left_weight))
            self.current_right_weight = max(0.0, min(1.0, right_weight))
            if volume is not None:
                self.current_volume = max(0.0, min(1.0, volume))
            
    def play_audio_with_live_panning(self):
        """Play audio with continuously updated panning parameters."""
        if self.audio_data is None:
            print("Audio not loaded.")
            return
        
        stream = self.open_audio_stream()
        
        # Convert the audio data to 16-bit PCM format
        audio_int16 = (self.audio_data * 32767).astype(np.int16)
        
        # Get the total number of frames
        total_frames = len(audio_int16)
        frame_index = 0
        
        try:
            # Play audio in chunks with updated panning
            while frame_index < total_frames and not self.stop_playback.is_set():
                chunk_size = min(self.chunk_size, total_frames - frame_index)
                
                # Get current chunk of audio
                audio_chunk = audio_int16[frame_index:frame_index + chunk_size]
                
                # Apply current panning parameters
                with self.playback_lock:
                    left_weight = self.current_left_weight
                    right_weight = self.current_right_weight
                    volume = self.current_volume * self.volume
                
                # Apply stereo balance and volume to this chunk
                left_channel = audio_chunk[:, 0] * left_weight * volume
                right_channel = audio_chunk[:, 1] * right_weight * volume
                
                # Combine channels
                stereo_chunk = np.column_stack((left_channel, right_channel)).astype(np.int16)
                
                # Play the chunk
                stream.write(stereo_chunk.tobytes())
                
                # Move to next chunk
                frame_index += chunk_size
                
        except Exception as e:
            print(f"Error during live-panned audio playback: {e}")
        finally:
            stream.stop_stream()
            stream.close()
            self.is_playing = False

    def play_audio(self, left_weight, right_weight, volume=1.0, pitch_shift=None):
        """Play the audio asynchronously based on stereo weights and optional pitch shift."""
        # Stop any currently playing audio
        self.stop_playback.set()
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=0.1)  # Brief wait for current playback to end
        
        self.stop_playback.clear()
        
        if self.audio_data is None:
            print("Audio not loaded.")
            return

        def process_and_play_with_live_panning():
            try:
                self.is_playing = True
                
                # Apply pitch shift if specified
                if pitch_shift is not None:
                    self.current_pitch_shift = pitch_shift
                    self.apply_pitch_shift(pitch_shift)
                else:
                    self.current_pitch_shift = None
                    self.audio_data = np.copy(self.original_audio_data)  # Reset to original

                # Initialize panning parameters
                self.current_left_weight = left_weight
                self.current_right_weight = right_weight
                self.current_volume = volume
                
                # Play audio with live panning
                self.play_audio_with_live_panning()

            except Exception as e:
                print(f"Error during audio playback: {e}")
                import traceback
                print(traceback.format_exc())
            finally:
                self.is_playing = False

        # Start a new playback thread
        self.playback_thread = threading.Thread(target=process_and_play_with_live_panning)
        self.playback_thread.daemon = True
        self.playback_thread.start()

    def stop(self):
        """Stop and clean up the PyAudio resources."""
        self.stop_playback.set()
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=0.5)
        self.pyaudio_instance.terminate()