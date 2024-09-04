import numpy as np
from scipy import signal
import pygame
import os

# Initialize pygame mixer
pygame.mixer.init()

# Global variables
NORTH_SOUND_FILE = 'sounds/north.ogg'
north_volume = 1.0
play_north_sound = True
pitch_shift_factor = 0.5

# Load the north sound
try:
    north_sound = pygame.mixer.Sound(NORTH_SOUND_FILE)
except pygame.error as e:
    print(f"Error loading sound file: {e}")
    north_sound = None

def set_north_volume(volume):
    global north_volume
    north_volume = max(0.0, min(1.0, volume))
    print(f"North volume set to: {north_volume}")

def set_play_north_sound(play):
    global play_north_sound
    play_north_sound = play
    print(f"Play north sound set to: {play_north_sound}")

def set_pitch_shift_factor(factor):
    global pitch_shift_factor
    pitch_shift_factor = max(0.1, min(1.0, factor))
    print(f"Pitch shift factor set to: {pitch_shift_factor}")

def pitch_shift(sound, factor):
    # Get the sound array
    array = pygame.sndarray.array(sound)
    
    # Perform the pitch shift
    shifted = signal.resample(array, int(len(array) / factor))
    
    # Convert back to a Sound object
    return pygame.sndarray.make_sound(shifted.astype(np.int16))

def calculate_volumes(angle):
    rad_angle = np.radians((angle + 90) % 360)
    right_volume = np.clip((1 + np.cos(rad_angle)) / 2, 0, 1) * north_volume
    left_volume = np.clip((1 - np.cos(rad_angle)) / 2, 0, 1) * north_volume
    return left_volume, right_volume

def is_behind(angle):
    return 90 <= angle <= 270

def play_north_audio(angle):
    global north_sound
    
    if not play_north_sound or north_sound is None:
        print("North sound is disabled or not loaded.")
        return

    try:
        print(f"Received angle: {angle}")
        
        left_volume, right_volume = calculate_volumes(angle)
        print(f"Left volume: {left_volume}, Right volume: {right_volume}")
        
        sound_behind = is_behind(angle)
        
        if sound_behind:
            pitched_sound = pitch_shift(north_sound, pitch_shift_factor)
            pitched_sound.set_volume(left_volume, right_volume)
            pitched_sound.play()
            print(f"Playing pitched sound: {pitch_shift_factor}, Angle: {angle}")
        else:
            north_sound.set_volume(left_volume, right_volume)
            north_sound.play()
            print(f"Playing normal sound, Angle: {angle}")
    
    except Exception as e:
        print(f"Error playing north audio: {e}")

# Test function
def test_north_sound():
    print("Testing north sound...")
    for angle in range(0, 360, 45):
        print(f"\nTesting angle: {angle}")
        play_north_audio(angle)
        pygame.time.wait(1000)  # Wait for 1 second between sounds

if __name__ == "__main__":
    if os.path.exists(NORTH_SOUND_FILE):
        print("North sound file found.")
        test_north_sound()
    else:
        print(f"Error: North sound file not found at {NORTH_SOUND_FILE}")
