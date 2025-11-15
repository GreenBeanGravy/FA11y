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
    LOCAL_PLAYER_PATTERN = re.compile(r'Local Player (\w+)')

    def __init__(self):
        self.log_file_path: Optional[Path] = None
        self.parser_thread: Optional[threading.Thread] = None
        self.running = False
        self.paused = True  # Start paused

        # Match stats
        self.current_kills = 0
        self.last_kill_count = 0
        self.in_match = False

        # Track local player username
        self.local_player_username = None

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

        # Extract local player username if we haven't found it yet
        if not self.local_player_username:
            player_match = self.LOCAL_PLAYER_PATTERN.search(line)
            if player_match:
                self.local_player_username = player_match.group(1)
                logger.info(f"Detected local player: {self.local_player_username}")

        # Check for kill events
        kill_match = self.KILL_PATTERN.search(line)
        if kill_match:
            kill_score = int(kill_match.group(1))

            # Strategy: Track the LOWEST sequential sequence
            # Player's match kills are typically 0-50, other players might show 400+ (career stats)
            #
            # If we haven't started tracking yet (current_kills = 0):
            #   - Accept kills < 100 as potential player baseline
            #   - Ignore very high numbers (likely other players' career stats)
            #
            # Once tracking:
            #   - Only accept sequential +1 increments
            #   - If we see a much higher number, ignore it (other player)

            if self.current_kills == 0:
                # Not tracking yet - accept low numbers as baseline, or exact +1
                if kill_score == 1:
                    # First kill of match
                    self.current_kills = 1
                    self.last_kill_count = 1
                    self.in_match = True
                    announcement = f"Kill! Total: {kill_score}"
                    logger.info(f"Player kill detected (first): {announcement}")
                    safe_speak(announcement)
                elif kill_score < 100:
                    # Mid-match start - accept as baseline but don't announce yet
                    # Wait for next +1 to confirm
                    self.current_kills = kill_score
                    logger.info(f"Potential player baseline: {kill_score} kills")
                else:
                    # Very high number - likely other player's career stats
                    logger.debug(f"Ignoring high kill count (likely other player): {kill_score}")
            else:
                # Already tracking - only accept sequential +1
                if kill_score == self.current_kills + 1:
                    self.current_kills = kill_score
                    self.last_kill_count = kill_score
                    self.in_match = True

                    # Announce the kill
                    announcement = f"Kill! Total: {kill_score}"
                    logger.info(f"Player kill detected: {announcement}")
                    safe_speak(announcement)
                else:
                    # Non-sequential - likely other player
                    logger.debug(f"Non-sequential kill (likely other player): KillScore={kill_score}, Player current={self.current_kills}")

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
