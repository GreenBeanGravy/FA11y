import os
import numpy as np
from scipy import signal
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def check_library(name, import_command):
    try:
        module = __import__(import_command)
        logging.info(f"{name} version: {getattr(module, '__version__', 'unknown')}")
        return module
    except ImportError as e:
        logging.error(f"{name} is not installed. Error: {e}")
        return None

sf = check_library("soundfile", "soundfile")
sa = check_library("simpleaudio", "simpleaudio")

if sa:
    SIMPLEAUDIO_AVAILABLE = True
else:
    SIMPLEAUDIO_AVAILABLE = False
    logging.warning("simpleaudio is not available. Falling back to pygame for audio.")
    pygame = check_library("pygame", "pygame")
    if pygame:
        try:
            pygame.mixer.init()
            logging.info("pygame mixer initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize pygame mixer. Error: {e}")
    else:
        logging.error("Neither simpleaudio nor pygame is available. Please install one of them.")
        exit(1)

# Load the north sound
NORTH_SOUND_FILE = 'sounds/north.ogg'

if not os.path.exists(NORTH_SOUND_FILE):
    logging.error(f"Error: Audio file '{NORTH_SOUND_FILE}' not found.")
    exit(1)

try:
    if SIMPLEAUDIO_AVAILABLE:
        logging.info("Attempting to load audio file with soundfile")
        north_audio_data, sample_rate = sf.read(NORTH_SOUND_FILE)
        logging.info(f"Audio file loaded. Shape: {north_audio_data.shape}, Sample rate: {sample_rate}")
        north_audio_data = north_audio_data.astype(np.float32)
        if north_audio_data.ndim == 2:
            north_audio_data = north_audio_data.mean(axis=1)  # Convert stereo to mono
        north_audio_data = north_audio_data / np.max(np.abs(north_audio_data))  # Normalize
        logging.info("Audio data processed and normalized")
    else:
        logging.info("Attempting to load audio file with pygame")
        north_pygame_sound = pygame.mixer.Sound(NORTH_SOUND_FILE)
        logging.info("Audio file loaded with pygame")
except Exception as e:
    logging.error(f"Error loading audio: {e}")
    exit(1)

# Global variables
north_volume = 1.0
play_north_sound = True
pitch_shift_factor = 0.5  # 50% pitch down by default

def set_north_volume(volume):
    global north_volume
    north_volume = max(0.0, min(1.0, volume))
    logging.info(f"North volume set to: {north_volume}")

def set_play_north_sound(play):
    global play_north_sound
    play_north_sound = play
    logging.info(f"Play north sound set to: {play_north_sound}")

def set_pitch_shift_factor(factor):
    global pitch_shift_factor
    pitch_shift_factor = max(0.1, min(1.0, factor))
    logging.info(f"Pitch shift factor set to: {pitch_shift_factor}")

def pitch_shift(audio, factor):
    logging.debug(f"Applying pitch shift. Factor: {factor}")
    return signal.resample(audio, int(len(audio) / factor))

def is_behind(angle):
    behind = 90 <= angle <= 270
    logging.debug(f"Angle: {angle}, Is behind: {behind}")
    return behind

def calculate_volumes(angle):
    rad_angle = np.radians((angle + 90) % 360)
    right_volume = np.clip((1 + np.cos(rad_angle)) / 2, 0, 1) * north_volume
    left_volume = np.clip((1 - np.cos(rad_angle)) / 2, 0, 1) * north_volume
    logging.debug(f"Calculated volumes. Left: {left_volume}, Right: {right_volume}")
    return left_volume, right_volume

def play_simpleaudio(angle):
    global north_volume, north_audio_data, sample_rate, pitch_shift_factor
    
    logging.info(f"Playing audio with simpleaudio. Angle: {angle}")
    left_volume, right_volume = calculate_volumes(angle)
    sound_behind = is_behind(angle)

    try:
        if sound_behind:
            logging.debug("Applying pitch shift")
            shifted_audio = pitch_shift(north_audio_data, pitch_shift_factor)
        else:
            logging.debug("No pitch shift applied")
            shifted_audio = north_audio_data

        logging.debug("Applying volume to channels")
        left_channel = (shifted_audio * left_volume).astype(np.float32)
        right_channel = (shifted_audio * right_volume).astype(np.float32)
        stereo_data = np.column_stack((left_channel, right_channel))

        logging.debug("Converting to int16")
        stereo_data = (stereo_data * 32767).astype(np.int16)

        logging.debug("Playing audio buffer")
        play_obj = sa.play_buffer(stereo_data, 2, 2, sample_rate)
        logging.info("Audio played successfully using simpleaudio")
    except Exception as e:
        logging.error(f"Error in play_simpleaudio: {e}")
        raise

def play_pygame_sound(angle):
    global north_volume, pitch_shift_factor
    
    logging.info(f"Playing audio with pygame. Angle: {angle}")
    left_volume, right_volume = calculate_volumes(angle)
    sound_behind = is_behind(angle)

    try:
        logging.debug("Setting pygame sound volume")
        north_pygame_sound.set_volume(left_volume, right_volume)

        if sound_behind:
            logging.debug("Applying pitch shift for pygame sound")
            pitched_sound = pygame.sndarray.array(north_pygame_sound)
            pitched_sound = pitch_shift(pitched_sound, pitch_shift_factor)
            pitched_sound = pygame.sndarray.make_sound(pitched_sound.astype(np.int16))
            logging.debug("Playing pitched pygame sound")
            pitched_sound.play()
        else:
            logging.debug("Playing normal pygame sound")
            north_pygame_sound.play()
        
        logging.info("Audio played successfully using pygame")
    except Exception as e:
        logging.error(f"Error in play_pygame_sound: {e}")
        raise

def play_north_audio(angle):
    if not play_north_sound:
        logging.info("North sound is disabled.")
        return

    logging.info(f"Attempting to play north audio. Angle: {angle}")
    try:
        if SIMPLEAUDIO_AVAILABLE:
            play_simpleaudio(angle)
        else:
            play_pygame_sound(angle)
    except Exception as e:
        logging.error(f"Error playing audio: {e}")
        if SIMPLEAUDIO_AVAILABLE:
            logging.info("Falling back to pygame...")
            try:
                pygame = check_library("pygame", "pygame")
                if pygame:
                    pygame.mixer.init()
                    global north_pygame_sound
                    north_pygame_sound = pygame.mixer.Sound(NORTH_SOUND_FILE)
                    play_pygame_sound(angle)
                else:
                    logging.error("Pygame fallback failed: pygame not available")
            except Exception as e:
                logging.error(f"Pygame fallback also failed: {e}")
