import os
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'
import sys
import configparser
import threading
import time
from lib.utilities.mouse import pixel as _pixel
import subprocess
import win32com.client
import requests
import json
import numpy as np
import warnings
import signal
import atexit
import gc
import ctypes
import ctypes.wintypes
import logging
import wx
from typing import List, Tuple, Optional, Dict, Any, Union
from lib.mouse_passthrough import get_mouse_passthrough
from lib.mouse_passthrough import faker_input as _faker_input
from lib.config.config_manager import config_manager

# Kick off the FakerInput .NET CoreCLR load on a daemon thread the
# moment imports are done. Loading the DLL takes 3-5 s; doing it in
# the background lets the rest of FA11y startup proceed in parallel,
# and any caller that actually needs FakerInput will join the thread
# via ``ensure_loaded()``.
_faker_input.preload_async()

# Suppress pkg_resources deprecation warnings from external libraries
warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*", category=UserWarning)

# Check Python version requirement
if sys.version_info < (3, 8):
    print("Error: Python 3.8 or higher is required.")
    input("Press Enter to exit...")
    sys.exit(1)

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import pygame
import win32api
import win32con
import winshell

# Set the command window title
os.system("title FA11y")

# Check Python version and create mock imp if necessary
if sys.version_info >= (3, 12):
    class MockImp:
        __name__ = 'imp'

        @staticmethod
        def is_frozen(arg=None):
            if arg == "__main__":
                return hasattr(sys, "frozen") or '__compiled__' in globals()
            return hasattr(sys, 'frozen') or hasattr(sys, 'importers') or getattr(sys, 'frozen', False)

    sys.modules['imp'] = MockImp()

from accessible_output2.outputs.auto import Auto

try:
    import PyQt6
    PYQT6_AVAILABLE = True
except ImportError:
    PYQT6_AVAILABLE = False
    print("Warning: PyQt6 not available")

# Import from reorganized lib structure
from lib.detection.hsr import (
    check_health_shields,
    check_rarity,
)
from lib.utilities.mouse import (
    smooth_move_mouse,
    left_mouse_down,
    left_mouse_up,
    right_mouse_down,
    right_mouse_up,
    mouse_scroll,
)

# New imports from reorganized structure
from lib.monitors.height_monitor import start_height_monitor
from lib.monitors.background_monitor import monitor
from lib.monitors.material_monitor import material_monitor
from lib.monitors.resource_monitor import resource_monitor
# from lib.monitors.dynamic_object_monitor import dynamic_object_monitor
from lib.monitors.storm_monitor import storm_monitor
from lib.monitors.bloom_monitor import bloom_monitor
from lib.monitors.match_event_monitor import match_event_monitor
from lib.monitors.fa11y_ow_announcer import announcer as fa11y_ow_announcer
from lib.utilities.fa11y_ow_client import client as fa11y_ow_client
from lib.utilities.fa11y_ow_calibration import calibrate_fa11y_ow_position

from lib.managers.game_object_manager import game_object_manager
from lib.utilities.window_utils import get_active_window_title, focus_window
from lib.detection.match_tracker import match_tracker
from lib.managers.social_manager import get_social_manager

from lib.utilities.input import (
    is_key_pressed, get_pressed_key, is_numlock_on, VK_KEYS,
    is_key_combination_pressed, parse_key_combination, get_pressed_key_combination, is_key_combination_pressed_ignore_extra_mods
)

from lib.managers.poi_data_manager import POIData
from lib.detection.exit_match import exit_match
from lib.detection.lobby_reader import (
    read_mode_status,
    toggle_lobby_fill,
    set_team_size,
    toggle_ranked,
    toggle_build_mode,
)
from lib.detection.player_position import (
    announce_current_direction as speak_minimap_direction, 
    start_icon_detection, 
    check_for_pixel,
    ROI_START_ORIG,
    ROI_END_ORIG,
    get_quadrant,
    get_position_in_quadrant,
    cleanup_object_detection,
    find_player_position,
    find_player_icon_location,
    ContinuousPOIPinger,
    handle_poi_selection
)
from lib.managers.hotbar_manager import (
    initialize_hotbar_detection,
    detect_hotbar_item,
    announce_ammo_manually,
)
from lib.managers.inventory_manager import inventory_manager
from lib.utilities.utilities import (
    get_config_int,
    get_config_float,
    get_config_value,
    get_config_boolean,
    read_config,
    Config,
    get_default_config_value_string,
    # get_dynamic_object_configs,
    clear_config_cache,
    save_config,
    calculate_distance,
    get_game_objects_config_order,
    ensure_config_dir,
    migrate_config_files
)
from lib.managers.custom_poi_manager import load_custom_pois

# Ensure config directory exists and migrate old config files
ensure_config_dir()
migrate_config_files()

# Initialize logging system BEFORE other initializations
from lib.utilities.logging_setup import setup_logging, cleanup_logging
log_file_path = setup_logging()
if log_file_path:
    print(f"Logging to: {log_file_path}")
else:
    print("Warning: Logging system initialization failed")

# Initialize pygame mixer and load sounds
pygame.mixer.init()
update_sound = pygame.mixer.Sound("assets/sounds/update.ogg")

# GitHub URLs and update-check machinery now live in lib/app/updater_check.
from lib.app.updater_check import (
    run_updater as _run_updater_ext,
    check_for_updates as _check_for_updates_ext,
    get_version as _get_version_ext,
    parse_version as _parse_version_ext,
)
from lib.app.auth_watcher import (
    check_auth_expiration as _check_auth_expiration_ext,
    get_legendary_username as _get_legendary_username_ext,
    validate_epic_auth as _validate_epic_auth_ext,
)

from lib.app import state as _app_state

speaker = Auto()
key_state = {}
action_handlers = {}
config = None
key_bindings = {}
key_listener_thread = None

# Aliases for the authoritative Events that live in lib.app.state.
stop_key_listener = _app_state.stop_key_listener
config_gui_open = _app_state.config_gui_open
social_gui_open = _app_state.social_gui_open
discovery_gui_open = _app_state.discovery_gui_open
locker_gui_open = _app_state.locker_gui_open
gamemode_gui_open = _app_state.gamemode_gui_open
visited_objects_gui_open = _app_state.visited_objects_gui_open
custom_poi_gui_open = _app_state.custom_poi_gui_open
_shutdown_requested = _app_state.shutdown_requested
auth_expired = _app_state.auth_expired

keybinds_enabled = True
poi_data_instance = None
active_pinger = None
social_manager = None
discovery_api = None
auth_expiration_announced = False  # Track if we've already announced it

# POI category definitions — constants now live in lib/app/constants.py.
from lib.app.constants import (
    POI_CATEGORY_SPECIAL,
    POI_CATEGORY_REGULAR,
    POI_CATEGORY_LANDMARK,
    POI_CATEGORY_FAVORITE,
    POI_CATEGORY_CUSTOM,
    POI_CATEGORY_GAMEOBJECT,
    SPECIAL_POI_CLOSEST,
    SPECIAL_POI_SAFEZONE,
    SPECIAL_POI_CLOSEST_LANDMARK,
)

# Shared mutable state now lives in lib.app.state. We publish the shared
# speaker/update_sound onto it at startup so extracted action handlers can
# reach them via ``state.speaker``.
from lib.app import state as _app_state

# Legacy aliases for code still reading the module-level name directly.
current_poi_category = POI_CATEGORY_SPECIAL

# Initialize logger
logger = logging.getLogger(__name__)

# Publish shared state for lib.app.* modules.
_app_state.speaker = speaker
_app_state.logger = logger
_app_state.update_sound = update_sound

def signal_handler(signum, frame):
    """Handle CTRL+C and other termination signals for immediate shutdown."""
    print("\nShutdown requested...")
    _shutdown_requested.set()
    
    # Immediate cleanup of critical resources
    try:
        # Stop all monitoring systems without waiting
        monitor.stop_monitoring()
        material_monitor.stop_monitoring()
        resource_monitor.stop_monitoring()
        # dynamic_object_monitor.stop_monitoring()
        storm_monitor.stop_monitoring()
        bloom_monitor.stop_monitoring()
        match_event_monitor.stop_monitoring()
        match_tracker.stop_monitoring()
        fa11y_ow_announcer.stop()
        fa11y_ow_client.stop()

        # Stop social manager
        if social_manager:
            social_manager.stop_monitoring()

        # Stop mouse passthrough
        try:
            get_mouse_passthrough().stop()
        except Exception:
            pass

        # Clean up pygame mixer
        if pygame.mixer.get_init():
            pygame.mixer.quit()

        # Shutdown audio engine
        try:
            from lib.audio import shutdown_engine
            shutdown_engine()
        except Exception:
            pass

        # Set stop event for threads
        stop_key_listener.set()

    except:
        pass  # Ignore cleanup errors during shutdown

    print("FA11y is closing...")
    # Force immediate exit
    os._exit(0)

def register_shutdown_handlers():
    """Register signal handlers for clean shutdown."""
    signal.signal(signal.SIGINT, signal_handler)   # CTRL+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination request
    
    # Register cleanup function for normal exit
    atexit.register(cleanup_on_exit)

def cleanup_on_exit():
    """Cleanup function called on normal exit."""
    try:
        if pygame.mixer.get_init():
            pygame.mixer.quit()
        # Shutdown audio engine
        try:
            from lib.audio import shutdown_engine
            shutdown_engine()
        except Exception:
            pass
        # Cleanup logging system
        cleanup_logging()
    except:
        pass

from lib.app.movement_actions import (
    handle_movement as _handle_movement_ext,
    handle_scroll as _handle_scroll_ext,
)


def handle_movement(action: str, reset_sensitivity: bool) -> None:
    _handle_movement_ext(action, reset_sensitivity, speaker)


def handle_scroll(action: str) -> None:
    _handle_scroll_ext(action)

def reload_config() -> None:
    """Reload configuration and update action handlers with thread safety"""
    global config, action_handlers, key_bindings, poi_data_instance, current_poi_category
    
    try:
        # Use thread-safe config reading with cache clearing to ensure fresh read
        clear_config_cache()
        config = read_config(use_cache=False)

        # Initialize POI data if not already done and ensure data is loaded
        if poi_data_instance is None:
            poi_data_instance = POIData()
        
        # Ensure POI data is loaded for the current map
        current_map = config.get('POI', 'current_map', fallback='main')
        if current_map == 'main':
            poi_data_instance._ensure_api_data_loaded()
        else:
            poi_data_instance._ensure_map_data_loaded(current_map)

        # Initialize or update current_poi_category based on selected POI
        selected_poi_str = config.get('POI', 'selected_poi', fallback='closest, 0, 0')
        selected_poi_parts = selected_poi_str.split(',')
        selected_poi_name = selected_poi_parts[0].strip()
        current_poi_category = get_poi_category(selected_poi_name)

        # Validate keybinds and reset if necessary - now supports modifier keys
        config_updated = False
        temp_key_bindings_from_config = {key.lower(): get_config_value(config, key)[0].lower()
                                         for key in config['Keybinds'] if get_config_value(config, key)[0]}

        validated_key_bindings = {}
        for action, key_str in temp_key_bindings_from_config.items():
            if not key_str: # Allow empty keybinds (disabled)
                validated_key_bindings[action] = key_str
                continue

            if is_valid_key_or_combination(key_str):
                validated_key_bindings[action] = key_str
            else:
                speaker.speak(f"Unrecognized key combination '{key_str}' for action '{action}'. Resetting to default.")
                print(f"Warning: Unrecognized key combination '{key_str}' for action '{action}'. Resetting to default.")
                
                default_value_string = get_default_config_value_string('Keybinds', action)
                if default_value_string is not None:
                    config['Keybinds'][action] = default_value_string
                    default_key_part = default_value_string.split('"')[0].strip()
                    validated_key_bindings[action] = default_key_part.lower()
                else:
                    config['Keybinds'][action] = f" \"{get_config_value(config, action)[1]}\"" # Keep description
                    validated_key_bindings[action] = ""
                config_updated = True

        if config_updated:
            # Use thread-safe config saving
            success = save_config(config)
            if success:
                print("Configuration updated with default values for invalid keys.")
            else:
                print("Warning: Could not save updated configuration")

        key_bindings = validated_key_bindings

        mouse_keys_enabled = get_config_boolean(config, 'MouseKeys', True)
        reset_sensitivity = get_config_boolean(config, 'ResetSensitivity', False)

        action_handlers.clear()

        action_handlers['start navigation'] = lambda: start_icon_detection(use_ppi=check_for_pixel())

        if mouse_keys_enabled:
            action_handlers.update({
                'fire': left_mouse_down,
                'target': right_mouse_down,
                'turn left': lambda: handle_movement('turn left', reset_sensitivity),
                'turn right': lambda: handle_movement('turn right', reset_sensitivity),
                'secondary turn left': lambda: handle_movement('secondary turn left', reset_sensitivity),
                'secondary turn right': lambda: handle_movement('secondary turn right', reset_sensitivity),
                'look up': lambda: handle_movement('look up', reset_sensitivity),
                'look down': lambda: handle_movement('look down', reset_sensitivity),
                'turn around': lambda: handle_movement('turn around', reset_sensitivity),
                'recenter': lambda: handle_movement('recenter', reset_sensitivity),
                'scroll up': lambda: handle_scroll('scroll up'),
                'scroll down': lambda: handle_scroll('scroll down')
            })

        action_handlers.update({
            'announce direction faced': speak_minimap_direction,
            'check health shields': check_health_shields,
            'check rarity': check_rarity,
            'open gamemode selector': open_gamemode_selector,
            'open locker selector': open_locker_selector,
            'open locker viewer': open_locker_viewer,
            'announce reload map rotation': announce_reload_map_rotation,
            'sync current map to reload rotation': sync_current_map_to_reload_rotation,
            'open configuration menu': open_config_gui,
            'exit match': exit_match,
            'create custom p o i': handle_custom_poi_gui,
            'announce ammo': announce_ammo_manually,
            'toggle keybinds': toggle_keybinds,
            'toggle continuous ping': toggle_continuous_ping,
            'toggle poi favorite': toggle_favorite_poi,
            'mark bad game object': mark_last_reached_object_as_bad,
            'cycle map': lambda: cycle_map("forwards"),
            'cycle map backwards': lambda: cycle_map("backwards"),
            'cycle poi': lambda: cycle_poi("forwards"),
            'cycle poi backwards': lambda: cycle_poi("backwards"),
            'cycle poi category': lambda: cycle_poi_category("forwards"),
            'cycle poi category backwards': lambda: cycle_poi_category("backwards"),
            'get match stats': get_match_stats,
            'check hotspots': check_hotspots,
            'open visited objects': open_visited_objects,
            'open social menu': open_social_menu,
            'open discovery gui': open_discovery_gui,
            'open authentication': open_authentication,
            'open browser login': open_browser_login,
            'accept notification': accept_notification,
            'decline notification': decline_notification,
            'recapture mouse': lambda: get_mouse_passthrough().recapture_mouse(),
            'toggle mouse passthrough': lambda: get_mouse_passthrough().toggle(),
            'calibrate fa11y-ow position': calibrate_fa11y_ow_position,
            'read mode status': read_mode_status,
            'toggle fill': toggle_lobby_fill,
            'toggle ranked': toggle_ranked,
            'toggle build mode': toggle_build_mode,
            'set team solo': lambda: set_team_size('Solo'),
            'set team duo': lambda: set_team_size('Duo'),
            'set team trio': lambda: set_team_size('Trio'),
            'set team squad': lambda: set_team_size('Squad'),
            'set team 6-stack': lambda: set_team_size('6-Stack'),
        })

        for i in range(1, 6):
            action_handlers[f'detect hotbar {i}'] = lambda slot=i-1: detect_hotbar_item(slot)

        # Sync mouse passthrough DPI from main config
        try:
            mp = get_mouse_passthrough()
            dpi_str, _ = get_config_value(config, 'MousePassthroughDPI', '800')
            new_dpi = int(float(dpi_str))
            if mp.target_device and new_dpi != mp.target_device.dpi:
                mp.update_dpi(new_dpi)
                mp._save_device_to_config()
        except Exception:
            pass

    except Exception as e:
        print(f"Error reloading config: {e}")
        speaker.speak("Error reloading configuration")

def is_valid_key_or_combination(key_combo: str) -> bool:
    """Check if a key combination is valid"""
    if not key_combo:
        return False
    
    from lib.utilities.input import validate_key_combination
    return validate_key_combination(key_combo)

from lib.app.match_actions import (
    get_match_stats,
    mark_last_reached_object_as_bad,
    check_hotspots,
    open_visited_objects,
)

# Auth expiration handling
from lib.app.auth_actions import (
    handle_auth_expiration,
    on_auth_success as _on_auth_success,
    open_authentication,
    open_browser_login,
)

from lib.app.social_actions import (
    open_social_menu,
    open_discovery_gui,
    accept_notification,
    decline_notification,
)


from lib.app.keybind_actions import (
    toggle_keybinds,
    toggle_continuous_ping,
    _refresh_poi_selector_after_favorite_toggle,
    toggle_favorite_poi,
)


def key_listener() -> None:
    """Listen for and handle key presses with modifier key support and fast shutdown response."""
    global key_bindings, key_state, action_handlers, stop_key_listener, config_gui_open, keybinds_enabled, config
    
    # Define the set of actions that should ignore extra modifiers
    mouse_key_actions = {
        'fire', 'target', 'turn left', 'turn right',
        'secondary turn left', 'secondary turn right',
        'look up', 'look down', 'turn around', 'recenter',
        'scroll up', 'scroll down'
    }

    # Actions that are allowed even when a GUI is focused
    allowed_gui_actions = {
        'accept notification',
        'decline notification',
        'toggle keybinds' # Always allowed
    }

    # Cache config booleans outside the inner loop — refresh once per cycle, not per keybind
    _cached_config_ref = None
    _cached_mouse_keys = True
    _cached_ignore_numlock = False
    # Cache GUI titles tuple (immutable, allocated once)
    gui_titles = ("Social Menu", "Discovery GUI", "FA11y Configuration", "Locker", "Gamemode Selector", "Create Custom POI", "Visited Objects Manager", "Epic Games Login")

    while not stop_key_listener.is_set() and not _shutdown_requested.is_set():
        # Quick exit check at start of loop
        if _shutdown_requested.is_set():
            break

        if _app_state.wizard_open.is_set():
            time.sleep(0.05)
            continue

        # Check active window for GUI focus management
        active_title = get_active_window_title()
        is_gui_focused = any(title in active_title for title in gui_titles)

        numlock_on = is_numlock_on()
        if config is None:
            time.sleep(0.01) # Reduced sleep for faster response
            continue

        # Refresh cached config booleans only when config object changes
        if config is not _cached_config_ref:
            _cached_config_ref = config
            _cached_mouse_keys = get_config_boolean(config, 'MouseKeys', True)
            _cached_ignore_numlock = get_config_boolean(config, 'IgnoreNumlock', False)

        for action, key_combo in key_bindings.items():
            if not key_combo:
                continue

            # Quick exit check in inner loop
            if _shutdown_requested.is_set():
                return

            action_lower = action.lower()

            if action_lower not in action_handlers:
                continue

            if not keybinds_enabled and action_lower != 'toggle keybinds':
                continue

            if not _cached_mouse_keys and action_lower in mouse_key_actions:
                continue

            if action_lower in ['fire', 'target'] and not (_cached_ignore_numlock or numlock_on):
                continue

            # Check if we should block this action due to GUI focus
            if is_gui_focused and action_lower not in allowed_gui_actions:
                # Block!
                # logger.debug(f"Blocked action '{action_lower}' because GUI is focused") # Uncomment for debugging
                continue

            # Movement is lenient on extra modifiers; everything else is strict.
            if action_lower in mouse_key_actions:
                key_pressed = is_key_combination_pressed_ignore_extra_mods(key_combo)
            else:
                key_pressed = is_key_combination_pressed(key_combo)

            key_state_key = key_combo

            if key_pressed != key_state.get(key_state_key, False):
                key_state[key_state_key] = key_pressed
                if key_pressed:
                    action_handler = action_handlers.get(action_lower)
                    if action_handler:
                        try:
                            action_handler()
                        except Exception as e:
                            print(f"Error executing action {action_lower}: {e}")
                else:
                    # Handle key release for fire/target actions
                    if action_lower in ['fire', 'target']:
                        # Parse the combination to get the main key
                        modifiers, main_key = parse_key_combination(key_combo)
                        if main_key in ['lctrl', 'rctrl']:  # Only for ctrl keys
                            (left_mouse_up if action_lower == 'fire' else right_mouse_up)()
        
        # Reduced sleep time for faster shutdown response
        time.sleep(0.005)

def create_desktop_shortcut() -> None:
    """Create a desktop shortcut for FA11y."""
    desktop = winshell.desktop()
    path = os.path.join(desktop, "FA11y.lnk")
    target = os.path.abspath(sys.argv[0])
    wDir = os.path.dirname(target)

    shell = win32com.client.Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(path)
    shortcut.Targetpath = target
    shortcut.WorkingDirectory = wDir
    shortcut.save()

def update_script_config(new_config: configparser.ConfigParser) -> None:
    """Update script configuration and restart key listener with safe operations"""
    global config, key_listener_thread, stop_key_listener
    
    try:
        # Use thread-safe config saving
        clear_config_cache()
        
        # Save the new config
        success = save_config(new_config)
        if not success:
            print("Warning: Could not save updated config")
            speaker.speak("Warning: Could not save configuration")
            return
        
        # Clear cache and reload
        clear_config_cache()
        config = read_config(use_cache=False)
        reload_config()

        # Restart key listener
        if key_listener_thread and key_listener_thread.is_alive():
            stop_key_listener.set()
            key_listener_thread.join()
        
        stop_key_listener.clear()
        key_listener_thread = threading.Thread(target=key_listener, daemon=True)
        key_listener_thread.start()
        
    except Exception as e:
        print(f"Error updating script config: {e}")
        speaker.speak("Error updating configuration")

from lib.app.menu_actions import (
    handle_custom_poi_gui,
    open_gamemode_selector,
    open_locker_selector,
    open_locker_viewer,
    open_config_gui as _open_config_gui_ext,
)


def open_config_gui() -> None:
    """Open the configuration GUI (delegates to lib.app.menu_actions).

    The extracted version takes ``reload_config`` as a callback so it can
    trigger FA11y's action-handler rewiring after the user saves settings.
    """
    _open_config_gui_ext(reload_config)



from lib.app.reload_rotation_actions import (
    announce_reload_map_rotation as _announce_reload_rotation_ext,
    sync_current_map_to_reload_rotation as _sync_reload_rotation_ext,
)


def announce_reload_map_rotation() -> None:
    _announce_reload_rotation_ext(speaker)


def sync_current_map_to_reload_rotation() -> None:
    _sync_reload_rotation_ext(speaker)


from lib.app.poi_navigation import (
    get_poi_category,
    get_pois_by_category,
    get_display_poi_name,
    sort_pois_by_position,
    get_poi_position_description,
    get_poi_categories,
    cycle_poi_category,
    cycle_poi,
    cycle_map,
)



# Updater + auth-watcher bodies moved to lib/app/. Expose thin wrappers
# so the existing call sites in this file keep working unchanged.

def run_updater() -> bool:
    return _run_updater_ext(speaker)

def get_version() -> Optional[str]:
    return _get_version_ext()

def parse_version(version: str) -> tuple:
    return _parse_version_ext(version)

def check_for_updates() -> None:
    _check_for_updates_ext(speaker, _shutdown_requested, update_sound)

def check_auth_expiration() -> None:
    _check_auth_expiration_ext(_shutdown_requested, _on_auth_success)

def get_legendary_username() -> Optional[str]:
    return _get_legendary_username_ext()

def validate_epic_auth(epic_auth) -> bool:
    return _validate_epic_auth_ext(epic_auth)

def main() -> None:
    """Main entry point for FA11y with instant shutdown capability."""
    global config, action_handlers, key_bindings, key_listener_thread, stop_key_listener, social_manager, discovery_api
    try:
        print("Starting FA11y...")

        # Register shutdown handlers early
        register_shutdown_handlers()

        # wx.App must exist before the wizard (or any GUI) can show.
        from lib.guis.gui_utilities import initialize_global_wx_app
        try:
            initialize_global_wx_app()
            logger.debug("Global wx.App initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize wx.App: {e}")

        # First-run wizard runs before anything else — nothing speaks,
        # nothing polls, no monitors, no key listener.
        first_run = False
        try:
            from lib.guis.welcome_wizard import is_first_run, run_welcome_wizard
            if is_first_run():
                first_run = True
                logger.info("First-run wizard triggered.")
                # Block until the FakerInput .NET runtime finishes
                # loading so its "[INFO] Loading…/loaded" messages don't
                # interleave with the wizard, and so any input the
                # wizard depends on is ready before the user sees a
                # control.
                _faker_input.ensure_loaded()
                run_welcome_wizard()
                clear_config_cache()
        except Exception as e:
            logger.exception(f"First-run wizard failed to launch: {e}")

        local_username = get_legendary_username()
        if local_username:
            print(f"Welcome back {local_username}!")
            if not first_run:
                speaker.speak(f"Welcome back {local_username}!")
        else:
            print("You are not logged into Legendary.")
            if not first_run:
                speaker.speak("You are not logged into Legendary.")

        # Check startup settings
        temp_config = read_config()
        if get_config_boolean(temp_config, 'AutoUpdates', True):
            if run_updater():
                sys.exit(0)
        if get_config_boolean(temp_config, 'CreateDesktopShortcut', True):
            create_desktop_shortcut()

        # Initialize core systems
        reload_config()

        # Initialize mouse passthrough
        try:
            mouse_passthrough_service = get_mouse_passthrough()
            mouse_passthrough_service.initialize(speaker)
        except Exception as e:
            print(f"Mouse passthrough initialization failed: {e}")
            speaker.speak("Mouse passthrough initialization failed")

        # Start key listener thread as daemon
        stop_key_listener.clear()
        key_listener_thread = threading.Thread(target=key_listener, daemon=True)
        key_listener_thread.start()

        # Start update checker thread as daemon
        update_thread = threading.Thread(target=check_for_updates, daemon=True)
        update_thread.start()

        # Start auth expiration checker thread as daemon
        auth_check_thread = threading.Thread(target=check_auth_expiration, daemon=True)
        auth_check_thread.start()

        # Start auxiliary systems — height_monitor is a BaseMonitor that
        # spawns its own daemon thread, so no outer wrapper needed.
        start_height_monitor()
        
        # Start monitoring systems
        monitor.start_monitoring()
        material_monitor.start_monitoring()
        resource_monitor.start_monitoring()
        # dynamic_object_monitor.start_monitoring()
        storm_monitor.start_monitoring()
        bloom_monitor.start_monitoring()
        match_event_monitor.start_monitoring()

        # FA11y-OW companion-service consumer (passive equip / pickup /
        # teammate-feed announcements). The SSE client is idle when the
        # helper isn't running, so this is safe to start unconditionally.
        fa11y_ow_client.start()
        fa11y_ow_announcer.start()

        # Start new game object system
        match_tracker.start_monitoring()

        # Auto-start a new match
        match_tracker._start_new_match()

        # Initialize hotbar detection
        initialize_hotbar_detection()

        # Initialize Epic authentication and social features
        try:
            from lib.utilities.epic_auth import get_epic_auth_instance
            from lib.guis.epic_login_dialog import LoginDialog

            epic_auth = get_epic_auth_instance()

            # Validate auth token (checks if exists and if valid via API request)
            auth_valid = validate_epic_auth(epic_auth)

            # Try silent WebView authentication before showing GUI
            if not auth_valid and epic_auth:
                print("Attempting silent authentication...")
                if epic_auth.try_silent_webview_auth(timeout=10.0):
                    auth_valid = True
                    print(f"Authenticated as {epic_auth.display_name}")
                    logger.info("Silent WebView authentication succeeded")
                else:
                    logger.debug("Silent WebView authentication failed; will show login dialog")

            # Only show GUI if we couldn't authenticate automatically
            if not auth_valid:
                print("Epic Games authentication required for social features")
                speaker.speak("Epic Games authentication required. Opening login dialog.")

                # Show login dialog (app already initialized in main())
                app = wx.GetApp()
                if app is None:
                    app = wx.App(False)

                login_dialog = LoginDialog(None, epic_auth)
                login_dialog.ShowModal()
                authenticated = login_dialog.authenticated
                success_announced = getattr(login_dialog, "success_announced", False)
                login_dialog.Destroy()
                # Don't destroy app - keep it alive for future GUI usage

                if not authenticated:
                    print("Social features disabled: Authentication cancelled")
                    speaker.speak("Social features disabled")
                    epic_auth = None
                else:
                    # Refresh auth instance after login
                    epic_auth = get_epic_auth_instance()
                    if epic_auth and epic_auth.access_token and not success_announced:
                        speaker.speak(f"Authenticated as {epic_auth.display_name}")
                    auth_valid = True

            # Start social manager, discovery API, and other Epic auth-dependent features
            if epic_auth and epic_auth.access_token:
                from lib.utilities.epic_discovery import EpicDiscovery

                social_manager = get_social_manager(epic_auth)
                social_manager.start_monitoring()

                # Wire MatchEventMonitor's party-id resolver to the social
                # manager's cache so it can turn partial Fortnite-log ids
                # (e.g. "e7571...92503") into display names. Also pass the
                # local account id so the monitor can suppress self-adds.
                match_event_monitor.name_resolver = social_manager.resolve_name_from_partial_id
                match_event_monitor.local_account_id = epic_auth.account_id

                # Initialize discovery API
                discovery_api = EpicDiscovery(epic_auth)
                logger.debug("Discovery API initialized at startup")

                print(f"Social features enabled for {epic_auth.display_name}")
                speaker.speak(f"Social features enabled for {epic_auth.display_name}")
            else:
                print("Social features disabled: Not authenticated")

        except Exception as e:
            print(f"Social features disabled: {e}")
            logger.warning(f"Failed to initialize social features: {e}")

        '''
        # Print available dynamic objects for reference (reduced spam)
        dynamic_objects = get_dynamic_object_configs()
        if dynamic_objects:
            print(f"Dynamic object monitoring configured for {len(dynamic_objects)} object types")
            '''

        # Print game objects info (reduced spam)
        config = read_config()
        current_map = config.get('POI', 'current_map', fallback='main')
        game_object_types = game_object_manager.get_available_object_types(current_map)
        if game_object_types:
            print(f"Game objects available on {current_map} map: {len(game_object_types)} types")

        # Notify user and wait for input with immediate response capability
        speaker.speak("FA11y is now running in the background. Press Enter in this window to stop FA11y.")
        print("FA11y is now running in the background. Press Enter in this window to stop FA11y.")

        # Get wx app to pump events while waiting
        import wx as wx_import
        wx_app = wx_import.GetApp()

        # Use a loop to check for shutdown request while waiting for Enter key
        if sys.platform == 'win32':
            # Windows - use msvcrt for non-blocking input, but only respond to Enter
            import msvcrt
            while not _shutdown_requested.is_set():
                # CRITICAL: Process pending wx events from background threads
                # Without this, wx.CallAfter() calls from key_listener never execute
                if wx_app:
                    try:
                        wx_app.Yield(True)
                    except:
                        pass

                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    # Only exit on Enter key (carriage return)
                    if key == b'\r' or key == b'\n':
                        break
                    # Ignore all other keys (including Escape)
                time.sleep(0.1)
        else:
            # Non-Windows: Use select for non-blocking input
            import select
            while not _shutdown_requested.is_set():
                # CRITICAL: Process pending wx events
                if wx_app:
                    try:
                        wx_app.Yield(True)
                    except:
                        pass

                # Check for input with timeout
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    sys.stdin.readline()
                    break
                time.sleep(0.1)

    except KeyboardInterrupt:
        # Handle CTRL+C gracefully
        _shutdown_requested.set()
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        speaker.speak(f"An error occurred: {str(e)}")
    finally:
        # Set shutdown flag
        _shutdown_requested.set()
        
        # Minimal cleanup - no waiting for threads since they're daemon threads
        stop_key_listener.set()
        
        # Quick resource cleanup
        try:
            # Stop monitoring systems without waiting
            monitor.stop_monitoring()
            material_monitor.stop_monitoring()
            resource_monitor.stop_monitoring()
            # dynamic_object_monitor.stop_monitoring()
            storm_monitor.stop_monitoring()
            match_event_monitor.stop_monitoring()
            match_tracker.stop_monitoring()
            fa11y_ow_announcer.stop()
            fa11y_ow_client.stop()

            # Stop social manager
            if social_manager:
                social_manager.stop_monitoring()

            # Clean up object detection resources
            cleanup_object_detection()
            
            # Clean up pygame mixer
            if pygame.mixer.get_init():
                pygame.mixer.quit()

            # Shutdown audio engine
            try:
                from lib.audio import shutdown_engine
                shutdown_engine()
            except Exception:
                pass
        except:
            pass  # Ignore cleanup errors during shutdown

        print("FA11y is closing...")
        # Use os._exit for immediate termination
        os._exit(0)

if __name__ == "__main__":
    main()