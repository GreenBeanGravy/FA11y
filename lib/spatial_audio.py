import numpy as np
import soundfile as sf
import pyaudio
import threading
from scipy import signal
import time

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
                        volume = self.current_volume * self.volume
                    
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

    def play_audio(self, left_weight, right_weight, volume=1.0, pitch_shift=None):
        """Play audio asynchronously with stereo weights and optional pitch shift"""
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
                
                if pitch_shift is not None and pitch_shift != 1.0:
                    self.apply_pitch_shift(pitch_shift)
                else:
                    if self.original_audio_data is not None:
                        self.audio_data = np.copy(self.original_audio_data)

                with self.playback_lock:
                    self.current_left_weight = max(0.0, min(1.0, left_weight))
                    self.current_right_weight = max(0.0, min(1.0, right_weight))
                    self.current_volume = max(0.0, min(1.0, volume))
                
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