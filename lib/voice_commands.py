import sys
import os
import threading
import time
from difflib import SequenceMatcher

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from accessible_output2.outputs.auto import Auto
from lib.utilities import read_config
from lib.ppi import find_player_position
from lib.icon import start_icon_detection
from lib.minimap_direction import speak_minimap_direction
from lib.hsr import check_health_shields
from lib.hotbar_detection import announce_ammo_manually
from lib.exit_match import exit_match
from lib.guis.poi_selector_gui import POIData

def fuzzy_match_poi(input_str: str, poi_data: POIData) -> tuple[str, float] | None:
    """
    Find the best matching POI name with a minimum similarity threshold of 0.7.
    
    Args:
        input_str: The input string to match against POI names
        poi_data: Instance of POIData containing POI information
    
    Returns:
        Tuple of (matched POI name, similarity score) or None if no match found
    """
    input_str = input_str.lower().strip()
    best_match = None
    best_ratio = 0.0
    
    # Get current map's POIs
    if poi_data.current_map == "main":
        pois = poi_data.main_pois + poi_data.landmarks
    else:
        pois = poi_data.maps[poi_data.current_map].pois
    
    # Create a list of all POI names
    poi_names = [poi[0].lower() for poi in pois]
    
    for name in poi_names:
        ratio = SequenceMatcher(None, input_str, name).ratio()
        if ratio > best_ratio and ratio >= 0.7:
            best_match = name
            best_ratio = ratio
    
    return (best_match, best_ratio) if best_match else None

def fuzzy_match_map(input_str: str, poi_data: POIData) -> tuple[str, float] | None:
    """
    Find the best matching map name with a minimum similarity threshold of 0.7.
    
    Args:
        input_str: The input string to match against map names
        poi_data: Instance of POIData containing map information
    
    Returns:
        Tuple of (matched map name, similarity score) or None if no match found
    """
    input_str = input_str.lower().strip()
    best_match = None
    best_ratio = 0.0
    
    # Get all available maps
    map_names = [name.replace('_', ' ').lower() for name in poi_data.maps.keys()]
    
    for name in map_names:
        ratio = SequenceMatcher(None, input_str, name).ratio()
        if ratio > best_ratio and ratio >= 0.7:
            best_match = name
            best_ratio = ratio
            
    if best_match:
        # Convert back to original map format with underscore if needed
        original_map = next(
            (m for m in poi_data.maps.keys() 
             if m.replace('_', ' ').lower() == best_match),
            None
        )
        return (original_map, best_ratio) if original_map else None
    
    return None

def fuzzy_match_trigger(input_str: str, trigger_word: str) -> tuple[str, float] | None:
    """
    Find if the input matches the trigger word with a minimum similarity threshold of 0.7.
    
    Args:
        input_str: The input string to check
        trigger_word: The trigger word to match against
        
    Returns:
        Tuple of (matched word, similarity score) or None if no match found
    """
    input_str = input_str.lower().strip()
    ratio = SequenceMatcher(None, input_str, trigger_word).ratio()
    
    if ratio >= 0.7:
        return (trigger_word, ratio)
    return None

class WebRecognitionRunner:
    """
    A helper that starts a PyQt event loop and Selenium-based
    speech recognition in a separate thread.
    """
    def __init__(self, callback):
        self.callback = callback
        self._thread = None
        self._running = False

    def start(self):
        """Start Selenium + PyQt recognition loop in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._runner, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the speech recognition thread/event loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        self._thread = None

    def _runner(self):
        """
        This method runs in a background thread, sets up the PyQt application,
        and listens for final transcripts from the browser.
        """
        app = QApplication(sys.argv)
        self.speech_listener = BrowserSpeechListener(self.callback)
        app.exec()
        self.speech_listener.close()

class BrowserSpeechListener:
    """
    Manages a headless Chrome instance running an HTML page with
    the Web Speech API.
    """
    def __init__(self, callback):
        self.callback = callback

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--use-fake-ui-for-media-stream")
        chrome_options.add_argument("--mute-audio")
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        chrome_options.add_argument("--log-level=3")

        self.driver = webdriver.Chrome(options=chrome_options)

        html_content = """
        <!DOCTYPE html>
        <html>
        <body>
        <div id="transcript"></div>
        <script>
        let recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
        recognition.continuous = true;
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        recognition.lang = 'en-US';

        // Reduce the silence needed to finalize results
        // Values are in milliseconds
        const SILENCE_TIMEOUT = 200;  // Time of silence before considering speech complete (default is 1000-1500)
        let silenceTimer = null;
        let finalTranscript = '';

        recognition.onresult = (event) => {
            clearTimeout(silenceTimer);
            
            const result = event.results[event.results.length - 1];
            const transcript = result[0].transcript;
            
            if (result.isFinal) {
                document.getElementById('transcript').setAttribute('data-final', transcript);
            } else {
                // Start silence timer when we detect a pause
                silenceTimer = setTimeout(() => {
                    if (transcript) {
                        document.getElementById('transcript').setAttribute('data-final', transcript);
                    }
                }, SILENCE_TIMEOUT);
            }
        };

        recognition.onend = () => {
            recognition.start();
        };

        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            // Restart recognition if there's an error
            if (event.error !== 'no-speech') {
                recognition.abort();
                recognition.start();
            }
        };

        // Start recognition
        recognition.start();
        </script>
        </body>
        </html>
        """

        with open("temp_speech.html", "w", encoding="utf-8") as f:
            f.write(html_content)

        self.driver.get("file://" + os.path.abspath("temp_speech.html"))
        os.remove("temp_speech.html")

        self.transcript_element = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_transcript)
        self.timer.start(50)

    def check_transcript(self):
        """Look for new final transcripts and pass them to callback."""
        try:
            if not self.transcript_element:
                self.transcript_element = self.driver.find_element(By.ID, "transcript")

            final_text = self.transcript_element.get_attribute("data-final")
            if final_text:
                final_text = final_text.lower().strip()
                self.driver.execute_script(
                    'document.getElementById("transcript").removeAttribute("data-final");'
                )
                if final_text:
                    self.callback(final_text)

        except Exception:
            self.transcript_element = None

    def close(self):
        """Shutdown the Selenium browser."""
        try:
            self.driver.quit()
        except:
            pass

class VoiceCommandProcessor:
    def __init__(self):
        self.speaker = Auto()
        self.running = False
        self.config = None
        self.waiting_for_command = False
        self.command_timeout = 0.0
        self.poi_data = POIData()

        self.refresh_config()
        self.web_runner = WebRecognitionRunner(callback=self.process_speech)

    def refresh_config(self):
        """Reload config and set trigger_word & commands."""
        self.config = read_config()
        self.trigger_word = self._extract_value_only('TriggerWord', 'fortnite')
        
        self.commands_map = {
            'navigate':   self._extract_value_only('NavigateCommand',   'take me to'),
            'location':   self._extract_value_only('LocationCommand',   'where am i'),
            'switch_map': self._extract_value_only('SwitchMapCommand',  'switch map to'),
            'gamemode':   self._extract_value_only('GamemodeCommand',   'select gamemode'),
            'health':     self._extract_value_only('HealthCommand',     'check health'),
            'ammo':       self._extract_value_only('AmmoCommand',       'check ammo'),
            'direction':  self._extract_value_only('DirectionCommand',  'check direction'),
            'leave':      self._extract_value_only('LeaveCommand',      'leave match'),
        }

    def _extract_value_only(self, key: str, fallback: str) -> str:
        """Extract value from config, ignoring any description."""
        raw_val = self.config.get('VoiceCommands', key, fallback=fallback).strip().lower()
        quote_index = raw_val.find('"')
        if quote_index != -1:
            raw_val = raw_val[:quote_index].strip()
        return raw_val

    def start(self):
        """Start the web-based speech recognition."""
        if not self.running:
            self.running = True
            self.web_runner.start()
            print("Voice command system ready (web-based).")

    def stop(self):
        """Stop the voice command system."""
        if self.running:
            self.running = False
            self.web_runner.stop()
            print("Voice commands stopped.")

    def process_speech(self, text: str):
        """Handle final recognized speech with fuzzy trigger word matching."""
        self.refresh_config()
        print(f"Heard: {text!r}")

        stripped_text = text.rstrip(".?!, ").strip()

        if self.waiting_for_command:
            # If already waiting for a command, check if the new input starts with trigger word
            trigger_match = fuzzy_match_trigger(stripped_text[:len(self.trigger_word)], self.trigger_word)
            if trigger_match:
                stripped_text = stripped_text[len(self.trigger_word):].strip()
            self.handle_command_text(stripped_text)
            return

        # Check for exact match or fuzzy match with trigger word
        trigger_match = fuzzy_match_trigger(stripped_text, self.trigger_word)
        if trigger_match or stripped_text == self.trigger_word:
            self.waiting_for_command = True
            self.command_timeout = time.time() + 8.0
            print("Trigger word detected - waiting for command.")
            self.speaker.speak("Listening")
        elif stripped_text.startswith(self.trigger_word):
            remainder = stripped_text[len(self.trigger_word):].strip()
            if remainder:
                self.handle_command_text(remainder)
            else:
                self.waiting_for_command = True
                self.command_timeout = time.time() + 8.0
                print("Trigger word only. Waiting for follow-up.")
                self.speaker.speak("Listening")
        # Check if the input starts with something similar to trigger word
        elif len(stripped_text) > len(self.trigger_word):
            trigger_match = fuzzy_match_trigger(stripped_text[:len(self.trigger_word)], self.trigger_word)
            if trigger_match:
                remainder = stripped_text[len(self.trigger_word):].strip()
                if remainder:
                    self.handle_command_text(remainder)
                else:
                    self.waiting_for_command = True
                    self.command_timeout = time.time() + 8.0
                    print("Fuzzy trigger word match. Waiting for follow-up.")
                    self.speaker.speak("Listening")
        else:
            print("No trigger match; ignoring speech.")

        if self.waiting_for_command and time.time() > self.command_timeout:
            self.waiting_for_command = False
            print("Command wait timeout.")

    def handle_command_text(self, text: str):
        """Process command text and execute appropriate action."""
        was_waiting = self.waiting_for_command
        self.waiting_for_command = False

        cmd_key, arg = self.detect_command_and_arg(text)
        if cmd_key:
            self.execute_command(cmd_key, arg)
        else:
            if was_waiting:
                print(f"Command not recognized during wait: '{text}'")
            else:
                print(f"No valid command found in: '{text}'")

    def detect_command_and_arg(self, text: str):
        """Detect command and its argument from input text."""
        found_command = ""
        found_arg = ""

        for cmd_key, phrase in self.commands_map.items():
            if text.startswith(phrase):
                found_command = cmd_key
                found_arg = text[len(phrase):].strip()

                if found_command == 'switch_map':
                    if found_arg == 'og':
                        found_arg = 'o g'
                    elif found_arg == 'maine':
                        found_arg = 'main'
                break

        return (found_command, found_arg)

    def execute_command(self, command: str, arg: str):
        """Execute the detected command with its argument."""
        print(f"Executing command: {command!r}, argument: '{arg}'")

        if command == 'navigate':
            self.handle_navigation(arg)
        elif command == 'location':
            self.handle_location()
        elif command == 'switch_map':
            self.handle_switch_map(arg)
        elif command == 'gamemode':
            self.speaker.speak(f"Selecting gamemode {arg}")
        elif command == 'health':
            check_health_shields()
        elif command == 'ammo':
            announce_ammo_manually()
        elif command == 'direction':
            speak_minimap_direction()
        elif command == 'leave':
            exit_match()

    def handle_navigation(self, arg: str):
        """Handle navigation command with fuzzy matching."""
        if not arg or arg.lower() == 'closest':
            self.speaker.speak("Navigating to closest POI")
            self.config['POI']['selected_poi'] = 'Closest, 0, 0'
            with open('config.txt', 'w') as f:
                self.config.write(f)
            start_icon_detection(use_ppi=True)
            return
            
        if arg.lower() in ['safe zone', 'safezone']:
            self.speaker.speak("Navigating to safe zone")
            self.config['POI']['selected_poi'] = 'Safe Zone, 0, 0'
            with open('config.txt', 'w') as f:
                self.config.write(f)
            start_icon_detection(use_ppi=True)
            return
            
        # Try to fuzzy match the POI name
        match_result = fuzzy_match_poi(arg, self.poi_data)
        if match_result:
            poi_name, similarity = match_result
            self.speaker.speak(f"Navigating to {poi_name}")
            
            # Find the full POI data
            if self.poi_data.current_map == "main":
                pois = self.poi_data.main_pois + self.poi_data.landmarks
            else:
                pois = self.poi_data.maps[self.poi_data.current_map].pois
                
            poi_data = next(
                (poi for poi in pois if poi[0].lower() == poi_name.lower()),
                None
            )
            
            if poi_data:
                self.config['POI']['selected_poi'] = f"{poi_data[0]}, {poi_data[1]}, {poi_data[2]}"
                with open('config.txt', 'w') as f:
                    self.config.write(f)
                start_icon_detection(use_ppi=True)
            else:
                self.speaker.speak("Error finding POI coordinates")
        else:
            self.speaker.speak("POI not found")

    def handle_location(self):
        """Announce the player's current location using fuzzy matching."""
        current_pos = find_player_position()
        if current_pos:
            # Get all POIs from current map
            if self.poi_data.current_map == "main":
                all_pois = self.poi_data.main_pois + self.poi_data.landmarks
            else:
                all_pois = self.poi_data.maps[self.poi_data.current_map].pois
                
            # Find closest POI
            closest = min(
                all_pois,
                key=lambda p: ((float(p[1]) - current_pos[0])**2 + (float(p[2]) - current_pos[1])**2)**0.5
            )
            self.speaker.speak(f"You are near {closest[0]}")
        else:
            self.speaker.speak("Could not find your location")
            
    def handle_switch_map(self, arg: str):
        """Handle map switching command with fuzzy matching."""
        match_result = fuzzy_match_map(arg, self.poi_data)
        if match_result:
            map_name, similarity = match_result
            clean_name = map_name.replace('_', '')
            self.config['POI']['current_map'] = clean_name
            with open('config.txt', 'w') as f:
                self.config.write(f)
            nice_map_name = clean_name.replace('_', ' ')
            self.speaker.speak(f"Switched map to {nice_map_name}")
            
            # Also update POIData's current map
            self.poi_data.current_map = map_name
        else:
            self.speaker.speak("Map not found")

# Keep this global object at the end:
voice_processor = VoiceCommandProcessor()