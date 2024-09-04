import numpy as np
from scipy import signal
import simpleaudio as sa
import soundfile as sf
import os
import threading

# Global variables
NORTH_SOUND_FILE = 'sounds/north.ogg'
north_volume = 1.0
play_north_sound = True
pitch_shift_factor = 0.5

# Load and pre-process the north sound
try:
    north_audio_data, sample_rate = sf.read(NORTH_SOUND_FILE)
    north_audio_data = north_audio_data.astype(np.float32)
    if north_audio_data.ndim == 2:
        north_audio_data = north_audio_data.mean(axis=1)  # Convert stereo to mono
    north_audio_data = north_audio_data / np.max(np.abs(north_audio_data))  # Normalize
    
    # Pre-compute pitched version
    pitched_audio_data = signal.resample(north_audio_data, int(len(north_audio_data) / pitch_shift_factor))
except Exception as e:
    print(f"Error loading audio: {e}")
    north_audio_data = None
    pitched_audio_data = None
    sample_rate = None

# Pre-allocate play objects
normal_play_obj = None
pitched_play_obj = None

def set_north_volume(volume):
    global north_volume
    north_volume = max(0.0, min(1.0, volume))
    print(f"North volume set to: {north_volume}")

def set_play_north_sound(play):
    global play_north_sound
    play_north_sound = play
    print(f"Play north sound set to: {play_north_sound}")

def set_pitch_shift_factor(factor):
    global pitch_shift_factor, pitched_audio_data
    pitch_shift_factor = max(0.1, min(1.0, factor))
    pitched_audio_data = signal.resample(north_audio_data, int(len(north_audio_data) / pitch_shift_factor))
    print(f"Pitch shift factor set to: {pitch_shift_factor}")

def calculate_volumes(angle):
    rad_angle = np.radians((angle + 90) % 360)
    right_volume = np.clip((1 + np.cos(rad_angle)) / 2, 0, 1) * north_volume
    left_volume = np.clip((1 - np.cos(rad_angle)) / 2, 0, 1) * north_volume
    return left_volume, right_volume

def is_behind(angle):
    return 90 <= angle <= 270

def play_audio_thread(audio_data, left_volume, right_volume):
    global sample_rate
    left_channel = (audio_data * left_volume).astype(np.float32)
    right_channel = (audio_data * right_volume).astype(np.float32)
    stereo_data = np.column_stack((left_channel, right_channel))
    stereo_data = (stereo_data * 32767).astype(np.int16)
    sa.play_buffer(stereo_data, 2, 2, sample_rate)

def play_north_audio(angle):
    global north_audio_data, pitched_audio_data, normal_play_obj, pitched_play_obj
    
    if not play_north_sound or north_audio_data is None:
        print("North sound is disabled or not loaded.")
        return

    try:
        print(f"Received angle: {angle}")
        
        left_volume, right_volume = calculate_volumes(angle)
        print(f"Left volume: {left_volume}, Right volume: {right_volume}")
        
        sound_behind = is_behind(angle)
        
        # Stop any currently playing sounds
        if normal_play_obj and normal_play_obj.is_playing():
            normal_play_obj.stop()
        if pitched_play_obj and pitched_play_obj.is_playing():
            pitched_play_obj.stop()
        
        if sound_behind:
            print(f"Playing pitched sound: {pitch_shift_factor}, Angle: {angle}")
            threading.Thread(target=play_audio_thread, args=(pitched_audio_data, left_volume, right_volume)).start()
        else:
            print(f"Playing normal sound, Angle: {angle}")
            threading.Thread(target=play_audio_thread, args=(north_audio_data, left_volume, right_volume)).start()
    
    except Exception as e:
        print(f"Error playing north audio: {e}")
