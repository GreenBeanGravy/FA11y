"""
In-match action handlers — match stats, bad-object marking, hotspot check,
visited-objects GUI launcher.

Each handler speaks via ``state.speaker`` and reads config through
``read_config()`` directly rather than the old FA11y module global.
"""
from __future__ import annotations

import os

from lib.app import state
from lib.detection.match_tracker import match_tracker
from lib.managers.game_object_manager import game_object_manager
from lib.utilities.mouse import pixel as _pixel
from lib.utilities.utilities import read_config
from lib.utilities.window_utils import focus_window


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


def mark_last_reached_object_as_bad() -> None:
    """Mark the last reached game object as bad and remove from the map."""
    speaker = state.speaker
    try:
        stats = match_tracker.get_current_match_stats()
        if not stats or not stats.get('visited_object_types'):
            speaker.speak("No game objects have been reached yet")
            return

        last_visited = None
        latest_time = 0
        last_visited_type = None
        for obj_type in stats['visited_object_types']:
            visited_objects = match_tracker.get_visited_objects_of_type(obj_type)
            for visited_obj in visited_objects:
                if visited_obj.visit_time > latest_time:
                    latest_time = visited_obj.visit_time
                    last_visited = visited_obj
                    last_visited_type = obj_type

        if not last_visited:
            speaker.speak("No game objects have been reached yet")
            return

        config = read_config()
        current_map = config.get('POI', 'current_map', fallback='main')

        from lib.utilities.map_rotation import normalize_map_slug
        slug = normalize_map_slug(current_map)
        source_file = os.path.join('data', 'maps', f'map_{slug}_gameobjects.txt')
        bad_file = os.path.join('data', 'maps', f'map_{slug}_badgameobject.txt')

        if not os.path.exists(source_file):
            speaker.speak(f"Game objects file not found for {current_map} map")
            return

        from lib.managers.game_object_manager import (
            MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT,
            SCREEN_BOUNDS_X1, SCREEN_BOUNDS_Y1,
            SCREEN_BOUNDS_X2, SCREEN_BOUNDS_Y2,
        )
        screen_width = SCREEN_BOUNDS_X2 - SCREEN_BOUNDS_X1
        screen_height = SCREEN_BOUNDS_Y2 - SCREEN_BOUNDS_Y1
        screen_x = last_visited.coordinates[0] - SCREEN_BOUNDS_X1
        screen_y = last_visited.coordinates[1] - SCREEN_BOUNDS_Y1
        image_x = (screen_x / screen_width) * MAP_IMAGE_WIDTH
        image_y = (screen_y / screen_height) * MAP_IMAGE_HEIGHT

        line_removed = None
        updated_lines = []
        with open(source_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith('#'):
                updated_lines.append(line)
                continue
            try:
                parts = line_stripped.split(',')
                if len(parts) == 3:
                    obj_type = parts[0].strip()
                    file_x = float(parts[1].strip())
                    file_y = float(parts[2].strip())
                    if (obj_type == last_visited_type
                            and abs(file_x - image_x) <= 5
                            and abs(file_y - image_y) <= 5):
                        line_removed = line_stripped
                        continue
                updated_lines.append(line)
            except (ValueError, IndexError):
                updated_lines.append(line)

        if not line_removed:
            speaker.speak("Could not find matching game object in file")
            return

        with open(source_file, 'w', encoding='utf-8') as f:
            f.writelines(updated_lines)

        os.makedirs(os.path.join('data', 'maps'), exist_ok=True)
        bad_lines = []
        if os.path.exists(bad_file):
            with open(bad_file, 'r', encoding='utf-8') as f:
                bad_lines = f.readlines()
        if not bad_lines:
            bad_lines = [
                f"# Bad game objects for {current_map} map\n",
                "# Format: ObjectType,X,Y (coordinates relative to map image)\n",
                "#\n",
            ]
        while bad_lines and not bad_lines[-1].strip():
            bad_lines.pop()
        bad_lines.append(line_removed + '\n')

        with open(bad_file, 'w', encoding='utf-8') as f:
            f.writelines(bad_lines)

        game_object_manager.reload_map_data(current_map)

        if last_visited_type in match_tracker.current_match.visited_objects:
            visited_list = match_tracker.current_match.visited_objects[last_visited_type]
            match_tracker.current_match.visited_objects[last_visited_type] = [
                obj for obj in visited_list
                if obj.coordinates != last_visited.coordinates
            ]
            if not match_tracker.current_match.visited_objects[last_visited_type]:
                del match_tracker.current_match.visited_objects[last_visited_type]

        speaker.speak(f"Marked {last_visited_type} as bad and removed from map")

    except Exception as e:
        print(f"Error marking object as bad: {e}")
        speaker.speak("Error marking last reached object as bad")


# Hotspot pixels on the full-screen map — these are the fixed on-map glyph
# locations; match them against non-white / non-black to find active hotspots.
_HOTSPOT_PIXELS = [
    (683, 303), (955, 311), (1210, 245), (782, 405), (904, 417),
    (1031, 461), (654, 511), (555, 618), (725, 641), (894, 625),
    (1078, 639), (1232, 607), (585, 894), (957, 846), (1190, 876),
    (764, 830), (1265, 776),
]


def check_hotspots() -> None:
    """Check for hotspot POIs on the map."""
    speaker = state.speaker
    try:
        hotspot_coordinates = []
        for x, y in _HOTSPOT_PIXELS:
            try:
                pixel_color = _pixel(x, y)
                r, g, b = pixel_color
                is_white = (250 <= r <= 255) and (250 <= g <= 255) and (250 <= b <= 255)
                is_black = (0 <= r <= 5) and (0 <= g <= 5) and (0 <= b <= 5)
                if not is_white and not is_black:
                    hotspot_coordinates.append((x, y))
            except Exception as e:
                print(f"Error checking pixel at {x},{y}: {e}")
                continue

        if not hotspot_coordinates:
            speaker.speak("No hotspots detected")
            return
        if len(hotspot_coordinates) > 2:
            speaker.speak(
                f"Error: {len(hotspot_coordinates)} hotspots detected, "
                "expected maximum 2"
            )
            return

        hotspot_pois = []
        poi_data = state.get_poi_data()
        config = read_config()
        current_map = config.get('POI', 'current_map', fallback='main')

        if current_map == 'main':
            poi_data._ensure_api_data_loaded()
            available_pois = poi_data.main_pois
        elif current_map in poi_data.maps:
            poi_data._ensure_map_data_loaded(current_map)
            available_pois = poi_data.maps[current_map].pois
        else:
            speaker.speak("No POI data available for current map")
            return

        for hotspot_x, hotspot_y in hotspot_coordinates:
            closest_poi = None
            min_distance = float('inf')
            for poi_name, poi_x_str, poi_y_str in available_pois:
                try:
                    poi_x = int(float(poi_x_str))
                    poi_y = int(float(poi_y_str))
                    distance = ((hotspot_x - poi_x) ** 2
                                + (hotspot_y - poi_y) ** 2) ** 0.5
                    if distance < min_distance:
                        min_distance = distance
                        closest_poi = poi_name
                except (ValueError, TypeError):
                    continue
            if closest_poi:
                hotspot_pois.append(closest_poi)

        if len(hotspot_pois) == 1:
            speaker.speak(f"{hotspot_pois[0]} is a hot spot")
        elif len(hotspot_pois) == 2:
            speaker.speak(
                f"{hotspot_pois[0]} and {hotspot_pois[1]} are hot spots"
            )
        else:
            speaker.speak("No POIs found near hotspots")
    except Exception as e:
        print(f"Error checking hotspots: {e}")
        speaker.speak("Error checking hotspots")


def open_visited_objects() -> None:
    """Open the visited objects manager GUI."""
    speaker = state.speaker
    from lib.guis.gui_utilities import launch_gui_thread_safe

    if state.visited_objects_gui_open.is_set():
        speaker.speak("Visited objects manager is already open")
        focus_window("Visited Objects Manager")
        return

    def _do_open_visited_objects():
        state.visited_objects_gui_open.set()
        try:
            from lib.guis.visited_objects_gui import launch_visited_objects_gui
            launch_visited_objects_gui()
        except Exception as e:
            print(f"Error opening visited objects GUI: {e}")
            speaker.speak("Error opening visited objects manager")
        finally:
            state.visited_objects_gui_open.clear()

    launch_gui_thread_safe(_do_open_visited_objects)
