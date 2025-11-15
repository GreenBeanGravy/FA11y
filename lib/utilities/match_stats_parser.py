"""
Real-time Fortnite Log File Parser
Monitors log files for match events and provides accessibility announcements
"""
import os
import re
import time
import logging
import threading
from pathlib import Path
from typing import Optional, Callable
from accessible_output2.outputs.auto import Auto

logger = logging.getLogger(__name__)
speaker = Auto()


def safe_speak(text: str):
    """Safely speak text, catching COM errors that can occur with SAPI5"""
    try:
        speaker.speak(text)
    except Exception as e:
        logger.debug(f"TTS error (non-critical): {e}")


class MatchStatsParser:
    """Real-time parser for Fortnite log files to track match stats"""

    # Log event patterns
    KILL_PATTERN = re.compile(r'LogFort: FORT-\d+ AFortPlayerStateAthena::OnRep_Kills\(\) \(KillScore = (\d+)\)')
    PREDICTION_KEY_PATTERN = re.compile(r'LogPredictionKey:')

    def __init__(self):
        self.log_file_path: Optional[Path] = None
        self.parser_thread: Optional[threading.Thread] = None
        self.running = False
        self.paused = True  # Start paused

        # Match stats
        self.current_kills = 0
        self.last_kill_count = 0
        self.in_match = False

        # Track prediction key events (indicates player's own actions)
        self.last_prediction_key_time = 0.0

        # Find log file
        self._find_log_file()

    def _find_log_file(self) -> bool:
        """
        Find the Fortnite log file

        Returns:
            True if found, False otherwise
        """
        try:
            # Typical Fortnite log location
            local_appdata = os.environ.get('LOCALAPPDATA')
            if not local_appdata:
                logger.error("LOCALAPPDATA environment variable not found")
                return False

            log_path = Path(local_appdata) / "FortniteGame" / "Saved" / "Logs" / "FortniteGame.log"

            if log_path.exists():
                self.log_file_path = log_path
                logger.info(f"Found Fortnite log file: {log_path}")
                return True
            else:
                logger.warning(f"Fortnite log file not found at: {log_path}")
                return False

        except Exception as e:
            logger.error(f"Error finding log file: {e}")
            return False

    def _reset_match_stats(self):
        """Reset stats for new match"""
        self.current_kills = 0
        self.last_kill_count = 0
        self.in_match = True
        logger.info("Match stats reset - new match started")

    def _process_line(self, line: str):
        """
        Process a single log line for events

        Args:
            line: Log line to process
        """
        if not line or self.paused:
            return

        # Track LogPredictionKey events (indicates player's own actions)
        if self.PREDICTION_KEY_PATTERN.search(line):
            self.last_prediction_key_time = time.time()
            logger.debug("Detected LogPredictionKey - player action predicted")

        # Check for kill events
        kill_match = self.KILL_PATTERN.search(line)
        if kill_match:
            kill_score = int(kill_match.group(1))
            current_time = time.time()

            # Check if there was a LogPredictionKey event within the last 2 seconds
            # LogPredictionKey appears only for the LOCAL PLAYER'S actions (client-side prediction)
            time_since_prediction = current_time - self.last_prediction_key_time
            is_player_kill = time_since_prediction < 2.0

            logger.debug(f"Kill event: KillScore={kill_score}, TimeSincePrediction={time_since_prediction:.2f}s, IsPlayerKill={is_player_kill}")

            # Only announce if it's the player's kill
            if is_player_kill:
                self.current_kills = kill_score
                self.last_kill_count = kill_score
                self.in_match = True

                # Announce the kill
                announcement = f"Kill! Total: {kill_score}"
                logger.info(announcement)
                safe_speak(announcement)

    def _tail_log_file(self):
        """
        Tail the log file and process new lines in real-time
        """
        if not self.log_file_path or not self.log_file_path.exists():
            logger.error("Cannot tail log file - file not found")
            return

        logger.info(f"Starting log file tail: {self.log_file_path}")

        try:
            with open(self.log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # Seek to end of file
                f.seek(0, 2)

                while self.running:
                    line = f.readline()

                    if line:
                        # Process the line
                        self._process_line(line)
                    else:
                        # No new lines, sleep briefly
                        time.sleep(0.1)

        except Exception as e:
            logger.error(f"Error tailing log file: {e}")

    def start(self):
        """Start the log parser in background thread"""
        if self.running:
            logger.warning("Parser already running")
            return

        if not self.log_file_path:
            logger.error("Cannot start parser - log file not found")
            safe_speak("Error: Fortnite log file not found")
            return

        self.running = True
        self.parser_thread = threading.Thread(target=self._tail_log_file, daemon=True)
        self.parser_thread.start()
        logger.info("Match stats parser started")

    def stop(self):
        """Stop the log parser"""
        if not self.running:
            return

        self.running = False
        if self.parser_thread:
            self.parser_thread.join(timeout=2.0)
        logger.info("Match stats parser stopped")

    def pause(self):
        """Pause announcements (still parses, but doesn't announce)"""
        self.paused = True
        logger.info("Match stats announcements paused")

    def resume(self):
        """Resume announcements"""
        self.paused = False
        logger.info("Match stats announcements resumed")

    def toggle(self):
        """Toggle pause/resume"""
        if self.paused:
            self.resume()
            safe_speak("Match stats enabled")
        else:
            self.pause()
            safe_speak("Match stats disabled")

    def get_current_stats(self) -> dict:
        """
        Get current match statistics

        Returns:
            Dict with current stats
        """
        return {
            'kills': self.current_kills,
            'in_match': self.in_match
        }

    def announce_stats(self):
        """Announce current match stats on demand"""
        if self.in_match:
            stats_text = f"Current kills: {self.current_kills}"
        else:
            stats_text = "Not in a match"

        logger.info(f"Stats announcement: {stats_text}")
        safe_speak(stats_text)


# Global instance
_match_stats_parser: Optional[MatchStatsParser] = None


def get_match_stats_parser() -> MatchStatsParser:
    """Get or create the global match stats parser instance"""
    global _match_stats_parser
    if _match_stats_parser is None:
        _match_stats_parser = MatchStatsParser()
    return _match_stats_parser
