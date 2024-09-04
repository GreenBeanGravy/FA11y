import numpy as np
import soundfile as sf
from scipy import signal

# Try to import simpleaudio, but provide a fallback if it's not available
try:
    import simpleaudio as sa
    SIMPLEAUDIO_AVAILABLE = True
except ImportError:
    SIMPLEAUDIO_AVAILABLE = False
    print("simpleaudio is not available. Falling back to pygame for audio.")
    import pygame
    pygame.mixer.init()

# Load the north sound
NORTH_SOUND_FILE = 'sounds/north.ogg'

if SIMPLEAUDIO_AVAILABLE:
    try:
        north_audio_data, sample_rate = sf.read(NORTH_SOUND_FILE)
        north_audio_data = north_audio_data.astype(np.float32)
        if north_audio_data.ndim == 2:
            north_audio_data = north_audio_data.mean(axis=1)  # Convert stereo to mono
        north_audio_data = north_audio_data / np.max(np.abs(north_audio_data))  # Normalize
    except Exception as e:
        print(f"Error loading audio: {e}")
        north_audio_data = None
        sample_rate = None
else:
    north_pygame_sound = pygame.mixer.Sound(NORTH_SOUND_FILE)

# Global variables
north_volume = 1.0
play_north_sound = True
pitch_shift_factor = 0.5  # 50% pitch down by default

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

def pitch_shift(audio, factor):
    return signal.resample(audio, int(len(audio) / factor))

def play_north_audio(angle):
    if not play_north_sound:
        print("North sound is disabled.")
        return

    print(f"Received angle: {angle}")
    if SIMPLEAUDIO_AVAILABLE:
        play_simpleaudio(angle)
    else:
        play_pygame_sound(angle)

def is_behind(angle):
    # Sound is behind when player faces between 90 (East) and 270 (West)
    behind = 90 <= angle <= 270
    print(f"Angle: {angle}, Is behind: {behind}")
    return behind

def calculate_volumes(angle):
    # Convert angle to radians and shift by 90 degrees (π/2 radians)
    # This ensures that the sound is loudest at 0 degrees (North)
    rad_angle = np.radians((angle + 90) % 360)
    # Swap left and right to correct the positioning
    right_volume = np.clip((1 + np.cos(rad_angle)) / 2, 0, 1) * north_volume
    left_volume = np.clip((1 - np.cos(rad_angle)) / 2, 0, 1) * north_volume
    return left_volume, right_volume

def play_simpleaudio(angle):
    global north_volume, north_audio_data, sample_rate, pitch_shift_factor
    
    left_volume, right_volume = calculate_volumes(angle)
    print(f"Left volume: {left_volume}, Right volume: {right_volume}")

    # Determine if the sound is behind the player
    sound_behind = is_behind(angle)

    # Apply pitch shift if the sound is behind the player
    if sound_behind:
        shifted_audio = pitch_shift(north_audio_data, pitch_shift_factor)
        print(f"Applying pitch shift: {pitch_shift_factor}, Angle: {angle}")
    else:
        shifted_audio = north_audio_data
        print(f"No pitch shift applied, Angle: {angle}")

    # Apply the volume to each channel
    left_channel = (shifted_audio * left_volume).astype(np.float32)
    right_channel = (shifted_audio * right_volume).astype(np.float32)
    stereo_data = np.column_stack((left_channel, right_channel))

    # Convert to int16 for simpleaudio
    stereo_data = (stereo_data * 32767).astype(np.int16)

    # Play the sound
    play_obj = sa.play_buffer(stereo_data, 2, 2, sample_rate)

def play_pygame_sound(angle):
    global north_volume, pitch_shift_factor
    
    left_volume, right_volume = calculate_volumes(angle)
    print(f"Left volume: {left_volume}, Right volume: {right_volume}")

    # Determine if the sound is behind the player
    sound_behind = is_behind(angle)

    # Set the volumes for left and right channels
    north_pygame_sound.set_volume(left_volume, right_volume)

    # Play the sound with pitch shift if behind
    if sound_behind:
        pitched_sound = pygame.sndarray.array(north_pygame_sound)
        pitched_sound = pitch_shift(pitched_sound, pitch_shift_factor)
        pitched_sound = pygame.sndarray.make_sound(pitched_sound.astype(np.int16))
        pitched_sound.play()
        print(f"Playing pitched sound: {pitch_shift_factor}, Angle: {angle}")
    else:
        north_pygame_sound.play()
        print(f"Playing normal sound, Angle: {angle}")

print(f"Audio system initialized. Using {'simpleaudio' if SIMPLEAUDIO_AVAILABLE else 'pygame'}")