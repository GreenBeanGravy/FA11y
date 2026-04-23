"""
Keybind toggle actions.

Covers the keybind-toggle family:

* ``toggle_keybinds``       — F8 hotkey; enables/disables FA11y response
* ``toggle_continuous_ping`` — Alt+P; starts/stops the POI pinger
* ``toggle_favorite_poi``   — Alt+Shift+F; adds/removes current POI from favorites
* ``_refresh_poi_selector_after_favorite_toggle`` — helper

All state access goes through ``lib.app.state`` — no module-level globals.
"""
from __future__ import annotations

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
    ContinuousPOIPinger,
    find_player_position,
    handle_poi_selection,
)
from lib.utilities.utilities import read_config, save_config


def toggle_keybinds() -> None:
    """Toggle keybinds on/off."""
    new_enabled = not state.are_keybinds_enabled()
    state.set_keybinds_enabled(new_enabled)
    label = 'enabled' if new_enabled else 'disabled'
    state.speaker.speak(f"FA11y {label}")
    print(f"FA11y has been {label}.")


def toggle_continuous_ping() -> None:
    """Toggle continuous pinging for the selected POI."""
    speaker = state.speaker
    active = state.get_active_pinger()
    if active:
        active.stop()
        state.set_active_pinger(None)
        speaker.speak("Continuous ping disabled.")
        return

    config = read_config()
    selected_poi_str = config.get('POI', 'selected_poi', fallback='none,0,0')
    parts = selected_poi_str.split(',')
    if len(parts) < 3 or parts[0].strip().lower() == 'none':
        speaker.speak("No POI selected.")
        return

    poi_name = parts[0].strip()
    player_pos = find_player_position()
    if not player_pos:
        speaker.speak("Cannot start ping, player position unknown.")
        return

    poi_data = handle_poi_selection(poi_name, player_pos)
    if not poi_data or not poi_data[1]:
        speaker.speak(f"Location for {poi_name} not found.")
        return

    poi_coords = (int(float(poi_data[1][0])), int(float(poi_data[1][1])))
    pinger = ContinuousPOIPinger(poi_coords)
    pinger.start()
    state.set_active_pinger(pinger)
    speaker.speak(f"Continuous ping enabled for {poi_name}.")


def _refresh_poi_selector_after_favorite_toggle(
    was_added: bool, poi_name: str,
) -> None:
    """After adding/removing a favorite, reload favorites and ensure the
    selector's currently-selected POI is still valid."""
    from lib.app.poi_navigation import get_pois_by_category

    try:
        from lib.managers.poi_data_manager import get_favorites_manager
        favorites_manager = get_favorites_manager()
        favorites_manager.load_favorites()

        config = read_config()
        current_map = config.get('POI', 'current_map', fallback='main')
        favorites = favorites_manager.get_favorites_as_tuples(map_name=current_map)
        state.logger.info(
            f"Favorites refreshed: {len(favorites)} favorites "
            f"for map '{current_map}'"
        )

        current_cat = state.get_current_poi_category()

        if (not was_added and not favorites
                and current_cat == POI_CATEGORY_FAVORITE):
            state.logger.info(
                "Last favorite removed, switching to special category"
            )
            state.set_current_poi_category(POI_CATEGORY_SPECIAL)
            special_pois = get_pois_by_category(POI_CATEGORY_SPECIAL)
            if special_pois:
                first_poi = special_pois[0]
                config.set(
                    'POI', 'selected_poi',
                    f"{first_poi[0]}, {first_poi[1]}, {first_poi[2]}",
                )
                save_config(config)
            return

        if was_added and current_cat == POI_CATEGORY_FAVORITE:
            state.logger.info(
                f"Added {poi_name} to favorites, keeping current selection"
            )
            return

        if not was_added and current_cat == POI_CATEGORY_FAVORITE:
            selected_poi_str = config.get('POI', 'selected_poi',
                                          fallback='none,0,0')
            selected_poi_name = selected_poi_str.split(',')[0].strip()
            favorite_names = [f[0] for f in favorites]

            if selected_poi_name not in favorite_names and favorites:
                first_fav = favorites[0]
                config.set(
                    'POI', 'selected_poi',
                    f"{first_fav[0]}, {first_fav[1]}, {first_fav[2]}",
                )
                save_config(config)
                state.logger.info(
                    f"Updated selection to first favorite: {first_fav[0]}"
                )
            return

        if was_added and current_cat != POI_CATEGORY_FAVORITE:
            state.logger.info(
                f"Added {poi_name} to favorites while in {current_cat} category"
            )

    except Exception as e:
        state.logger.error(
            f"Error refreshing POI selector after favorite toggle: {e}"
        )


def toggle_favorite_poi() -> None:
    """Toggle the currently selected POI as a favorite."""
    speaker = state.speaker
    try:
        config = read_config()
        selected_poi_str = config.get('POI', 'selected_poi', fallback='none,0,0')
        parts = selected_poi_str.split(',')
        if len(parts) < 3 or parts[0].strip().lower() == 'none':
            speaker.speak("No POI selected.")
            return

        poi_name = parts[0].strip()
        poi_x = parts[1].strip()
        poi_y = parts[2].strip()

        if poi_name.lower() in (SPECIAL_POI_CLOSEST.lower(),
                                SPECIAL_POI_SAFEZONE.lower(),
                                SPECIAL_POI_CLOSEST_LANDMARK.lower()):
            speaker.speak("Cannot favorite special POIs.")
            return

        current_cat = state.get_current_poi_category()
        if current_cat == POI_CATEGORY_GAMEOBJECT:
            speaker.speak("Cannot favorite game object locators.")
            return

        state.get_poi_data()  # ensure lazy init

        from lib.managers.poi_data_manager import get_favorites_manager
        favorites_manager = get_favorites_manager()

        source_tab_map = {
            POI_CATEGORY_REGULAR: "regular",
            POI_CATEGORY_LANDMARK: "landmark",
            POI_CATEGORY_CUSTOM: "custom",
            POI_CATEGORY_FAVORITE: "favorite",
        }
        source_tab = source_tab_map.get(current_cat, "regular")

        current_map = config.get('POI', 'current_map', fallback='main')
        poi_tuple = (poi_name, poi_x, poi_y)
        was_added = favorites_manager.toggle_favorite(
            poi_tuple, source_tab, current_map,
        )
        _refresh_poi_selector_after_favorite_toggle(was_added, poi_name)

        if was_added:
            speaker.speak(f"Added {poi_name} to favorites.")
        else:
            speaker.speak(f"Removed {poi_name} from favorites.")

    except Exception as e:
        state.logger.error(f"Error toggling favorite POI: {e}")
        speaker.speak("Error toggling favorite status.")
