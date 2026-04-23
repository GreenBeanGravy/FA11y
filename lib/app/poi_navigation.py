"""
POI categorization + selection cycling.

Handles the big POI-navigation keybind cluster that was previously
spaghettied through ``FA11y.py``:

* ``get_poi_category`` — which bucket does a POI name belong in?
* ``get_pois_by_category`` — list POIs in a given category for the
  current map
* ``get_display_poi_name`` — strip the ``"Closest "`` prefix for speech
* ``sort_pois_by_position`` — quadrant + position ordering
* ``get_poi_position_description`` — "top-left of top-right quadrant"
* ``get_poi_categories`` — which categories are non-empty for this map
* ``cycle_poi_category`` / ``cycle_poi`` / ``cycle_map`` — the three
  keybind handlers

State access goes through ``lib.app.state`` — no module-level globals.
``speaker`` is reached via ``state.speaker`` (set by FA11y at startup).
"""
from __future__ import annotations

import json
import os
from typing import List, Tuple

from lib.app import state
from lib.app.constants import (
    POI_CATEGORY_CUSTOM,
    POI_CATEGORY_FAVORITE,
    POI_CATEGORY_GAMEOBJECT,
    POI_CATEGORY_LANDMARK,
    POI_CATEGORY_REGULAR,
    POI_CATEGORY_SPECIAL,
    SPECIAL_POI_CLOSEST,
    SPECIAL_POI_CLOSEST_LANDMARK,
    SPECIAL_POI_SAFEZONE,
)
from lib.detection.player_position import (
    ROI_END_ORIG,
    ROI_START_ORIG,
    get_position_in_quadrant,
    get_quadrant,
)
from lib.managers.custom_poi_manager import load_custom_pois
from lib.managers.game_object_manager import game_object_manager
from lib.managers.poi_data_manager import POIData
from lib.utilities.utilities import (
    Config,
    clear_config_cache,
    read_config,
)


# ---------------------------------------------------------------------------
# Categorization + listing
# ---------------------------------------------------------------------------


def get_poi_category(poi_name: str) -> str:
    """Determine which category a POI belongs to."""
    config = read_config()
    current_map = config.get('POI', 'current_map', fallback='main')

    n = (poi_name or '').strip().lower()
    if n.startswith('closest '):
        try:
            types = {t.lower() for t in
                     game_object_manager.get_available_object_types(current_map)}
            if n.replace('closest ', '', 1).strip() in types:
                return POI_CATEGORY_GAMEOBJECT
        except Exception:
            pass

    if poi_name.lower() == SPECIAL_POI_CLOSEST.lower():
        return POI_CATEGORY_SPECIAL
    if poi_name.lower() == SPECIAL_POI_SAFEZONE.lower():
        return POI_CATEGORY_SPECIAL
    if (poi_name.lower() == SPECIAL_POI_CLOSEST_LANDMARK.lower()
            and current_map == 'main'):
        return POI_CATEGORY_SPECIAL

    favorites_file = 'config/FAVORITE_POIS.txt'
    if os.path.exists(favorites_file):
        try:
            with open(favorites_file, 'r') as f:
                favorites_data = json.load(f)
                if any(f['name'].lower() == poi_name.lower()
                       for f in favorites_data):
                    return POI_CATEGORY_FAVORITE
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    custom_pois = load_custom_pois(current_map)
    if any(poi[0].lower() == poi_name.lower() for poi in custom_pois):
        return POI_CATEGORY_CUSTOM

    game_object_types = game_object_manager.get_available_object_types(current_map)
    for obj_type in game_object_types:
        objects = game_object_manager.get_objects_of_type(current_map, obj_type)
        if any(obj[0].lower() == poi_name.lower() for obj in objects):
            return POI_CATEGORY_GAMEOBJECT

    if current_map == 'main':
        poi_data = state.get_poi_data()
        poi_data._ensure_api_data_loaded()
        if any(poi[0].lower() == poi_name.lower() for poi in poi_data.landmarks):
            return POI_CATEGORY_LANDMARK

    return POI_CATEGORY_REGULAR


def get_pois_by_category(category: str) -> List[Tuple[str, str, str]]:
    """Get all POIs in a specific category."""
    config = read_config()
    current_map = config.get('POI', 'current_map', fallback='main')

    if category == POI_CATEGORY_SPECIAL:
        special_pois = [
            (SPECIAL_POI_CLOSEST, "0", "0"),
            (SPECIAL_POI_SAFEZONE, "0", "0"),
        ]
        if current_map == 'main':
            special_pois.append((SPECIAL_POI_CLOSEST_LANDMARK, "0", "0"))
        return special_pois

    if category == POI_CATEGORY_FAVORITE:
        from lib.managers.poi_data_manager import get_favorites_manager
        favorites_manager = get_favorites_manager()
        return favorites_manager.get_favorites_as_tuples(map_name=current_map)

    if category == POI_CATEGORY_CUSTOM:
        return load_custom_pois(current_map)

    if category == POI_CATEGORY_GAMEOBJECT:
        available_types = game_object_manager.get_available_object_types(current_map)
        ordered_types = sorted(available_types)
        return [(f"Closest {t}", "0", "0") for t in ordered_types]

    poi_data = state.get_poi_data()
    if category == POI_CATEGORY_LANDMARK and current_map == 'main':
        poi_data._ensure_api_data_loaded()
        return poi_data.landmarks

    if category == POI_CATEGORY_REGULAR:
        if current_map == 'main':
            poi_data._ensure_api_data_loaded()
            return poi_data.main_pois
        if current_map in poi_data.maps:
            poi_data._ensure_map_data_loaded(current_map)
            return poi_data.maps[current_map].pois

    return []


def get_display_poi_name(poi_name: str) -> str:
    """Strip ``"Closest "`` prefix from game-object names for announcements."""
    poi_category = get_poi_category(poi_name)
    if poi_category == POI_CATEGORY_GAMEOBJECT and poi_name.startswith("Closest "):
        return poi_name[8:]
    return poi_name


def sort_pois_by_position(
    pois: List[Tuple[str, str, str]],
) -> List[Tuple[str, str, str]]:
    """Sort POIs by quadrant + position within quadrant.

    Special POIs and game objects (which have 0,0 placeholder coords)
    are returned in their original (config) order.
    """
    def poi_sort_key(poi: Tuple[str, str, str]) -> Tuple[int, int, int, int]:
        name, x_str, y_str = poi
        try:
            x = int(float(x_str)) - ROI_START_ORIG[0]
            y = int(float(y_str)) - ROI_START_ORIG[1]
            width, height = (ROI_END_ORIG[0] - ROI_START_ORIG[0],
                             ROI_END_ORIG[1] - ROI_START_ORIG[1])
            quadrant = get_quadrant(x, y, width, height)
            position = get_position_in_quadrant(x, y, width // 2, height // 2)
            position_values = {
                "top-left": 0, "top": 1, "top-right": 2,
                "left": 3, "center": 4, "right": 5,
                "bottom-left": 6, "bottom": 7, "bottom-right": 8,
            }
            return (quadrant, position_values.get(position, 9), y, x)
        except (ValueError, TypeError):
            return (9, 9, 9, 9)

    if not pois:
        return []

    first = pois[0][0].lower()
    if first in (SPECIAL_POI_CLOSEST.lower(),
                 SPECIAL_POI_SAFEZONE.lower(),
                 SPECIAL_POI_CLOSEST_LANDMARK.lower()):
        return pois

    if all(poi[1] == "0" and poi[2] == "0" for poi in pois):
        return pois  # game-object stubs; preserve config order

    return sorted(pois, key=poi_sort_key)


def get_poi_position_description(poi: Tuple[str, str, str]) -> str:
    """Concise description of a POI's position in quadrant form."""
    try:
        name, x_str, y_str = poi
        x = int(float(x_str))
        y = int(float(y_str))

        x_rel = x - ROI_START_ORIG[0]
        y_rel = y - ROI_START_ORIG[1]
        width = ROI_END_ORIG[0] - ROI_START_ORIG[0]
        height = ROI_END_ORIG[1] - ROI_START_ORIG[1]

        quadrant = get_quadrant(x_rel, y_rel, width, height)
        quadrant_width = width // 2
        quadrant_height = height // 2
        x_in_quad = x_rel % quadrant_width
        y_in_quad = y_rel % quadrant_height
        position = get_position_in_quadrant(
            x_in_quad, y_in_quad, quadrant_width, quadrant_height,
        )
        quadrant_names = ["top left", "top right", "bottom left", "bottom right"]
        quadrant_name = quadrant_names[quadrant]
        if position == "center":
            return f"center of {quadrant_name} quadrant"
        return f"{position} of {quadrant_name} quadrant"
    except (ValueError, TypeError, IndexError):
        return "position unknown"


def get_poi_categories(include_empty: bool = False) -> List[str]:
    """Return the list of non-empty POI categories for the current map."""
    config = read_config()
    categories = [POI_CATEGORY_SPECIAL, POI_CATEGORY_REGULAR]
    current_map = config.get('POI', 'current_map', fallback='main')

    if current_map == 'main':
        categories.append(POI_CATEGORY_LANDMARK)

    if include_empty or get_pois_by_category(POI_CATEGORY_GAMEOBJECT):
        categories.append(POI_CATEGORY_GAMEOBJECT)
    if include_empty or get_pois_by_category(POI_CATEGORY_FAVORITE):
        categories.append(POI_CATEGORY_FAVORITE)
    if include_empty or get_pois_by_category(POI_CATEGORY_CUSTOM):
        categories.append(POI_CATEGORY_CUSTOM)

    return categories


# ---------------------------------------------------------------------------
# Keybind handlers: cycle_*
# ---------------------------------------------------------------------------

CATEGORY_DISPLAY_NAMES = {
    POI_CATEGORY_SPECIAL: "Special",
    POI_CATEGORY_REGULAR: "Regular",
    POI_CATEGORY_LANDMARK: "Landmark",
    POI_CATEGORY_FAVORITE: "Favorite",
    POI_CATEGORY_CUSTOM: "Custom",
    POI_CATEGORY_GAMEOBJECT: "Game Object",
}


def _stop_active_pinger(speaker) -> None:
    pinger = state.get_active_pinger()
    if pinger:
        pinger.stop()
        state.set_active_pinger(None)
        speaker.speak("Continuous ping disabled.")


def cycle_poi_category(direction: str = "forwards") -> None:
    """Cycle between POI categories with safe config handling."""
    speaker = state.speaker
    _stop_active_pinger(speaker)

    try:
        clear_config_cache()
        read_config(use_cache=False)  # re-read to pick up external edits

        state.get_poi_data()  # force lazy init

        categories = get_poi_categories()
        if not categories:
            speaker.speak("No POI categories available")
            return

        try:
            current_index = categories.index(state.get_current_poi_category())
        except ValueError:
            current_index = 0

        if direction == "backwards":
            new_index = (current_index - 1) % len(categories)
        else:
            new_index = (current_index + 1) % len(categories)

        new_category = categories[new_index]
        state.set_current_poi_category(new_category)

        category_pois = get_pois_by_category(new_category)
        sorted_pois = sort_pois_by_position(category_pois)

        if sorted_pois:
            first_poi = sorted_pois[0]
            config_adapter = Config()
            config_adapter.set_poi(first_poi[0], first_poi[1], first_poi[2])
            if config_adapter.save():
                clear_config_cache()
                read_config(use_cache=False)
                display_name = CATEGORY_DISPLAY_NAMES.get(
                    new_category, new_category.title(),
                )
                position_desc = ""
                if (first_poi[0].lower() not in (
                        SPECIAL_POI_CLOSEST.lower(),
                        SPECIAL_POI_SAFEZONE.lower(),
                        SPECIAL_POI_CLOSEST_LANDMARK.lower())
                        and first_poi[1] != "0"
                        and first_poi[2] != "0"):
                    pd = get_poi_position_description(first_poi)
                    if pd:
                        position_desc = f", {pd}"
                display_poi = get_display_poi_name(first_poi[0])
                speaker.speak(
                    f"{display_name} POIs: {display_poi}{position_desc}"
                )
            else:
                speaker.speak("Error saving POI selection")
        else:
            speaker.speak("No POIs available in the selected category")

    except Exception as e:
        print(f"Error cycling POI category: {e}")
        speaker.speak("Error cycling POI categories")


def cycle_poi(direction: str = "forwards") -> None:
    """Cycle through POIs in the current category."""
    speaker = state.speaker
    _stop_active_pinger(speaker)

    try:
        clear_config_cache()
        config = read_config(use_cache=False)
        state.get_poi_data()

        category_pois = get_pois_by_category(state.get_current_poi_category())
        if not category_pois:
            speaker.speak("No POIs available in the current category")
            return

        sorted_pois = sort_pois_by_position(category_pois)

        selected_poi_str = config.get('POI', 'selected_poi', fallback='closest, 0, 0')
        selected_poi_parts = selected_poi_str.split(',')
        selected_poi_name = selected_poi_parts[0].strip()

        current_index = -1
        for i, poi in enumerate(sorted_pois):
            if poi[0].lower() == selected_poi_name.lower():
                current_index = i
                break
        if current_index == -1:
            current_index = 0

        if direction == "backwards":
            new_index = (current_index - 1) % len(sorted_pois)
        else:
            new_index = (current_index + 1) % len(sorted_pois)
        new_poi = sorted_pois[new_index]

        config_adapter = Config()
        config_adapter.set_poi(new_poi[0], new_poi[1], new_poi[2])
        if config_adapter.save():
            clear_config_cache()
            read_config(use_cache=False)

            position_desc = ""
            if (new_poi[0].lower() not in (
                    SPECIAL_POI_CLOSEST.lower(),
                    SPECIAL_POI_SAFEZONE.lower(),
                    SPECIAL_POI_CLOSEST_LANDMARK.lower())
                    and new_poi[1] != "0" and new_poi[2] != "0"):
                pd = get_poi_position_description(new_poi)
                if pd:
                    position_desc = f", {pd}"

            display_poi = get_display_poi_name(new_poi[0])
            speaker.speak(f"{display_poi}{position_desc}")
        else:
            speaker.speak("Error saving POI selection")

    except Exception as e:
        print(f"Error cycling POI: {e}")
        speaker.speak("Error cycling POIs")


def cycle_map(direction: str = "forwards") -> None:
    """Cycle to the next/previous map with safe config handling."""
    speaker = state.speaker
    _stop_active_pinger(speaker)

    try:
        clear_config_cache()
        config = read_config(use_cache=False)
        poi_data = state.get_poi_data()

        current_map = config.get('POI', 'current_map', fallback='main')
        all_maps = sorted(poi_data.maps.keys())

        try:
            current_index = all_maps.index(current_map)
        except ValueError:
            current_index = 0

        if direction == "backwards":
            new_index = (current_index - 1) % len(all_maps)
        else:
            new_index = (current_index + 1) % len(all_maps)
        new_map = all_maps[new_index]

        previous_category = state.get_current_poi_category()
        temp_config = config
        temp_config.set('POI', 'current_map', new_map)
        category_pois = get_pois_by_category(previous_category)

        if not category_pois:
            state.set_current_poi_category(POI_CATEGORY_SPECIAL)
            category_pois = get_pois_by_category(POI_CATEGORY_SPECIAL)

        if category_pois:
            sorted_pois = sort_pois_by_position(category_pois)
            first_poi = sorted_pois[0]
            selected_poi_value = f"{first_poi[0]}, {first_poi[1]}, {first_poi[2]}"
        else:
            selected_poi_value = "closest, 0, 0"

        config_adapter = Config()
        config_adapter.set_current_map(new_map)
        config_adapter.set_poi(*selected_poi_value.split(', '))
        if config_adapter.save():
            clear_config_cache()
            read_config(use_cache=False)
            try:
                display_name = poi_data.maps[new_map].name
            except (KeyError, AttributeError):
                display_name = new_map.replace('_', ' ').title()
            speaker.speak(f"{display_name} map selected")
        else:
            speaker.speak("Error saving map selection")

    except Exception as e:
        print(f"Error cycling map: {e}")
        speaker.speak("Error cycling maps")
