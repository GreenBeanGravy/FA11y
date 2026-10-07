"""First-run setup without any window code.

Used by the requests the window sends. Setup writes its choices to the
config when it finishes or is skipped.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

FIRST_RUN_DESCRIPTION = ('Set to true after the first-run setup finishes. '
                         'While false, FA11y shows setup when it starts.')

CLOSE_CHOICES = ("ask", "tray", "quit")  # the order of the radio buttons on the startup step


def is_first_run() -> bool:
    """True if first-run setup hasn't been completed yet."""
    from lib.utilities.utilities import read_config
    try:
        config = read_config()
        # [Setup] is queried directly: get_config_value doesn't scan it.
        if config.has_section("Setup") and config.has_option("Setup", "FirstRunComplete"):
            raw = config.get("Setup", "FirstRunComplete")
            value = raw.split('"')[0].strip()
            return value.lower() not in ("true", "yes", "1", "on")
        return True  # No [Setup] yet: never completed.
    except Exception as e:
        logger.warning(f"is_first_run check failed: {e}")
        return False  # Fail closed: don't pester the user on a flaky read.


def _bool(value: Any) -> str:
    return "true" if value else "false"


def collect_values(answers: dict) -> Dict[tuple, Any]:
    """Turn the answers from every step into config values, as each wx step's collect() does."""
    values: Dict[tuple, Any] = {}
    close = answers.get("close_action")
    if close not in CLOSE_CHOICES:
        close = "ask"
    if any(k in answers for k in ("start_fortnite", "hide_on_launch", "nav_sounds", "close_action")):
        values[("Toggles", "StartFortniteOnLaunch")] = _bool(answers.get("start_fortnite", False))
        values[("Toggles", "HideHubWhenFortniteStarts")] = _bool(answers.get("hide_on_launch", True))
        values[("Toggles", "NavigationSounds")] = _bool(answers.get("nav_sounds", True))
        values[("Hub", "CloseAction")] = close
    if "simplified_speech" in answers:
        values[("Toggles", "SimplifySpeechOutput")] = _bool(answers.get("simplified_speech"))
    if answers.get("played_before"):
        # Only players who have played before are asked; a new player keeps the default.
        values[("Toggles", "ResetSensitivity")] = _bool(answers.get("reset_sensitivity"))
    if "volume" in answers:
        volume = clamp_int(answers.get("volume"), 0, 100, 100)
        values[("Audio", "MasterVolume")] = str(volume / 100.0)
    if "dpi" in answers:
        values[("Values", "MousePassthroughDPI")] = str(clamp_int(answers.get("dpi"), 100, 32000, 800))
    if "passthrough" in answers:
        values[("Toggles", "MousePassthrough")] = _bool(answers.get("passthrough"))
    return values


def clamp_int(value: Any, low: int, high: int, default: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def save_setup(values: Dict[tuple, Any], speak=None) -> bool:
    """Write the chosen values and mark setup complete. Returns False when the config couldn't be saved."""
    from lib.utilities.utilities import read_config, save_config
    try:
        config = read_config(use_cache=False)
        values = dict(values)
        values[("Setup", "FirstRunComplete")] = "true"
        for (section, key), value in values.items():
            if not config.has_section(section):
                config.add_section(section)
            existing = config.get(section, key, fallback="")
            description = existing[existing.index('"'):] if '"' in existing else ""
            if key == "FirstRunComplete":
                description = f'"{FIRST_RUN_DESCRIPTION}"'
            config.set(section, key, f"{value} {description}".strip())
        if not save_config(config):
            if speak is not None:
                speak("Couldn't save your setup choices.")
            return False
        return True
    except Exception:
        logger.exception("Saving setup failed")
        return False


def signin_state() -> dict:
    """Who is signed in, for the sign in step."""
    from lib.utilities.epic_auth import get_epic_auth_instance
    auth = get_epic_auth_instance()
    if auth and auth.access_token and auth.is_valid:
        return {"signed_in": True, "text": f"Signed in as {auth.display_name}."}
    return {"signed_in": False, "text": "Not signed in."}


def fortnite_step_state() -> dict:
    """What the Fortnite step says, and whether it offers the Epic Games Launcher choice."""
    try:
        from lib.fortnite import get_manager
        st = get_manager().status()
    except Exception:
        st = None
    if st is None:
        return {"message": "FA11y couldn't check for Fortnite. You can set it up on the Fortnite page later.",
                "offer_choice": False}
    if st.installed:
        return {"message": f"Fortnite is installed at {st.install_path} and ready to play from FA11y.",
                "offer_choice": False}
    if st.egl_install_path:
        return {"message": f"Fortnite is installed through the Epic Games Launcher at {st.egl_install_path}.",
                "offer_choice": True}
    return {"message": "Fortnite isn't installed. After setup, open the Fortnite page to install it. "
                       "It needs about 100 GB.", "offer_choice": False}


class AudioTester:
    """Plays the test sound at a chosen master volume, for the audio step."""

    def __init__(self) -> None:
        self._audio = None

    def play(self, volume_percent: int) -> Optional[str]:
        """Play the sound. Returns a message to say when it can't."""
        try:
            sound_path = os.path.join("assets", "sounds", "poi.ogg")
            if not os.path.exists(sound_path):
                return "Test sound file is missing."
            if self._audio is None:
                from lib.utilities.spatial_audio import SpatialAudio
                self._audio = SpatialAudio(sound_path)
            volume = max(0.0, min(clamp_int(volume_percent, 0, 100, 100) / 100.0, 1.0))
            self._audio.set_master_volume(volume)
            self._audio.set_individual_volume(1.0)
            self._audio.play_audio(left_weight=0.5, right_weight=0.5, volume=1.0)
            return None
        except Exception as e:
            logger.error(f"Setup audio test failed: {e}")
            return "Audio test failed."

    def cleanup(self) -> None:
        if self._audio is not None:
            try:
                self._audio.cleanup()
            except Exception:
                pass
            self._audio = None
