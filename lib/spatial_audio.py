import numpy as np
import soundfile as sf
import math
import pyaudio
import threading
from scipy import signal

class SpatialAudio:
    def __init__(self, audio_file, chunk_size=1024):
        self.audio_file = audio_file
        self.chunk_size = chunk_size
        self.volume = 1.0
        self.audio_data = None
        self.sample_rate = None
        self.pyaudio_instance = pyaudio.PyAudio()
        self.original_audio_data = None  # Store the original unmodified audio data

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

    def apply_pitch_shift(self, factor):
        """Apply the pitch shift and resample the audio."""
        if factor != 1.0:  # Only apply if pitch shift is different from 1.0 (no shift)
            self.audio_data = signal.resample(self.original_audio_data, int(len(self.original_audio_data) / factor))
            print(f"Pitch shift applied with factor: {factor}")
        else:
            # Restore the original audio data if pitch shift is not applied
            self.audio_data = np.copy(self.original_audio_data)

    def create_stereo_audio(self, left_weight, right_weight):
        """Apply the stereo weights and create the stereo-balanced audio."""
        left_channel = self.audio_data[:, 0] * left_weight
        right_channel = self.audio_data[:, 1] * right_weight
        return np.column_stack((left_channel, right_channel))

    def play_audio_chunk_by_chunk(self, audio_data):
        """Play the audio in chunks to reduce latency."""
        stream = self.open_audio_stream()

        # Convert the audio data to 16-bit PCM format
        audio_data_int16 = (audio_data * 32767).astype(np.int16)

        # Stream the audio in chunks
        start = 0
        while start < len(audio_data_int16):
            chunk = audio_data_int16[start:start + self.chunk_size]
            stream.write(chunk.tobytes())
            start += self.chunk_size

        stream.stop_stream()
        stream.close()

    def play_audio(self, left_weight, right_weight, volume=1.0, pitch_shift=None):
        """Play the audio asynchronously based on stereo weights and optional pitch shift."""
        if self.audio_data is None:
            print("Audio not loaded.")
            return

        def process_and_play():
            try:
                print(f"Playing audio | Left weight: {left_weight}, Right weight: {right_weight}, Volume: {volume}")

                # Apply pitch shift if specified, otherwise reset to original
                if pitch_shift is not None:
                    self.apply_pitch_shift(pitch_shift)
                else:
                    self.audio_data = np.copy(self.original_audio_data)  # Reset to original if no pitch shift

                # Create stereo-balanced audio
                stereo_data = self.create_stereo_audio(left_weight, right_weight)

                # Apply volume to both channels
                stereo_data *= volume * self.volume

                # Play the audio in chunks to minimize delay
                self.play_audio_chunk_by_chunk(stereo_data)

                print("Audio playback finished.")

            except Exception as e:
                print(f"Error during audio playback: {e}")
                import traceback
                print(traceback.format_exc())

        # Run the playback process in a separate thread to avoid blocking
        threading.Thread(target=process_and_play).start()

    def stop(self):
        """Stop and clean up the PyAudio resources."""
        self.pyaudio_instance.terminate()
