"""
In-match action handlers - match stats.

Each handler speaks via ``state.speaker``.
"""
from __future__ import annotations

from lib.app import state
from lib.app.speech import simple
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
        short = (
            f"{duration_minutes} minutes {duration_seconds} seconds, "
            f"{stats['total_visits']} visits. "
        )
        message += f"Total visits: {stats['total_visits']}. "
        if stats['visited_object_types']:
            visited = "Visited: " + ", ".join(stats['visited_object_types'])
            message += visited
            short += visited

        speaker.speak(simple(message, short))
        print(f"Match Stats: {stats}")
    except Exception as e:
        print(f"Error getting match stats: {e}")
        speaker.speak("Error getting match statistics")


