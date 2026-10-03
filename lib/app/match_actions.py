"""
In-match action handlers - match stats.

Each handler speaks via ``state.speaker``.
"""
from __future__ import annotations

from lib.app import state
from lib.detection.match_tracker import match_tracker


def get_match_stats() -> None:
    """Announce current match statistics."""
    speaker = state.speaker
    try:
        stats = match_tracker.get_current_match_stats()
        if not stats:
            speaker.speak("No active match data available")
            return

        duration_minutes = int(stats['duration'] // 60)
        duration_seconds = int(stats['duration'] % 60)

        message = (
            f"Match active for {duration_minutes} minutes "
            f"{duration_seconds} seconds. "
        )
        message += f"Total visits: {stats['total_visits']}. "
        if stats['visited_object_types']:
            message += "Visited: " + ", ".join(stats['visited_object_types'])

        speaker.speak(message)
        print(f"Match Stats: {stats}")
    except Exception as e:
        print(f"Error getting match stats: {e}")
        speaker.speak("Error getting match statistics")


