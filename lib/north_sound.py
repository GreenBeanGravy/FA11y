import numpy as np
from lib.spatial_audio import SpatialAudio
import os
import threading

# Global variables
NORTH_SOUND_FILE = 'sounds/north.ogg'
north_volume = 1.0
play_north_sound = True
pitch_shift_factor = 0.5

# Initialize SpatialAudio with the audio file
spatial_audio = SpatialAudio(NORTH_SOUND_FILE)

def set_north_volume(volume):
    global north_volume
    north_volume = max(0.0, min(1.0, volume))
    spatial_audio.set_volume(north_volume)  # Set the volume in the SpatialAudio module

def set_play_north_sound(play):
    global play_north_sound
    play_north_sound = play

def set_pitch_shift_factor(factor):
    global pitch_shift_factor
    pitch_shift_factor = max(0.1, min(1.0, factor))

def calculate_volumes(angle):
    """Calculate left and right channel volumes based on angle."""
    rad_angle = np.radians((angle + 90) % 360)
    right_volume = np.clip((1 + np.cos(rad_angle)) / 2, 0, 1)
    left_volume = np.clip((1 - np.cos(rad_angle)) / 2, 0, 1)
    return left_volume, right_volume

def is_behind(angle):
    """Check if the sound is coming from behind the listener."""
    return 90 <= angle <= 270

def play_north_audio(angle):
    """Play north sound with spatial audio."""
    global north_volume, play_north_sound, pitch_shift_factor
    
    if not play_north_sound or not os.path.exists(NORTH_SOUND_FILE):
        print("North sound is disabled or file not found.")
        return

    try:
        print(f"Received angle: {angle}")
        
        left_volume, right_volume = calculate_volumes(angle)
        print(f"Left volume: {left_volume}, Right volume: {right_volume}")
        
        # Determine if the sound is behind and apply pitch shift accordingly
        sound_behind = is_behind(angle)
        current_pitch_shift = pitch_shift_factor if sound_behind else None
        
        print(f"Playing {'pitched' if sound_behind else 'normal'} sound: Pitch shift: {current_pitch_shift}, Angle: {angle}")
        
        # Play audio with stereo weights, volume, and pitch shift
        spatial_audio.play_audio(
            left_weight=left_volume,
            right_weight=right_volume,
            volume=north_volume,
            pitch_shift=current_pitch_shift
        )
    
    except Exception as e:
        print(f"Error playing north audio: {e}")

def cleanup():
    """Cleanup audio resources."""
    spatial_audio.stop()
