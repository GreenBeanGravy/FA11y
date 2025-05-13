import os
import time
import ctypes
import configparser
from typing import Dict, Tuple, Optional, Any, Union, List

import pywintypes 
import win32gui
import win32con
import win32com.client
import win32api
import win32process
from accessible_output2.outputs.auto import Auto

speaker = Auto()
CONFIG_FILE = 'config.txt'

# Default configuration with all options and descriptions
DEFAULT_CONFIG = """[Toggles]
SimplifySpeechOutput = false "Toggles simplifying speech for various FA11y announcements."
MouseKeys = true "Toggles the keybinds used to look around, left click, and right click."
ResetSensitivity = false "Toggles between two sensitivity values for certain mouse movements, like recentering the camera. Do not change this if you are a new player."
AnnounceWeaponAttachments = true "Toggles the announcements of weapon attachments when equipping weapons."
AnnounceAmmo = true "Toggles the announcements of ammo count when equipping weapons."
AutoUpdates = true "Toggles automatic updates of FA11y."
CreateDesktopShortcut = true "Toggles the creation of a desktop shortcut for FA11y on launch."
AutoTurn = true "Toggles the automatic turning feature when navigating to a position. When toggled on, your player will automatically turn towards your selected location when getting navigation info."
PerformFacingCheck = true "Toggles whether to check if the player is facing the next point. When enabled, it affects audio feedback by playing a distinct sound when facing the next point. This setting does not affect AutoTurn."
PlayPOISound = true "Toggles spatial audio feedback when using PPI to get directions to a POI."
AnnounceMapStatus = true "Toggles announcements when the map is opened or closed."
AnnounceInventoryStatus = true "Toggles announcements when the inventory is opened or closed."

[Values]
TurnSensitivity = 75 "The sensitivity used for primary turning left, primary turning right, looking up, and looking down when MouseKeys is enabled."
SecondaryTurnSensitivity = 50 "The sensitivity used for secondary turning left and right when MouseKeys is enabled."
TurnAroundSensitivity = 1158 "The sensitivity used when turning the player around. Only adjust this if you are having issues."
ScrollSensitivity = 120 "The sensitivity used for the scroll up and down actions."
RecenterDelay = 0.01 "The delay, in seconds, for certain values used when recentering the player camera. Only adjust this if you are having issues."
TurnDelay = 0.01 "The delay, in seconds, between each TurnStep when turning the camera left, right, up, or down."
TurnSteps = 5 "The number of steps to use when turning left, right, up, or down."
RecenterSteps = 20 "The number of steps to use when recentering the camera."
RecenterStepDelay = 2 "The delay, in milliseconds, between each RecenterStep."
RecenterStepSpeed = 0 "The speed, in milliseconds, in how long it should take for the mouse to move when recentering the camera."
RecenterLookDown = 1500 "The sensitivity used when moving the camera down when recentering the camera."
RecenterLookUp = -820 "The sensitivity used when moving the camera up when recentering the camera."
ResetRecenterLookDown = 1500 "The sensitivity used when moving the camera down when recentering the camera on the ResetSensitivity."
ResetRecenterLookUp = -580 "The sensitivity used when moving the camera down when recentering the camera on the ResetSensitivity."
PingVolumeMaxDistance = 100 "The maximum distance in meters at which the ping sound becomes inaudible. Affects how quickly the volume falls off with distance."
PingFrequency = 0.5 "The frequency in seconds at which the navigation ping sound plays."
FacingPointAngleThreshold = 30 "The maximum angle difference in degrees between the player's facing direction and the direction to the next point for it to be considered 'facing' the point."
MinimumPOIVolume = 0.05 "The minimum volume for the P O I sound when the P O I is farthest."
MaximumPOIVolume = 1.0 "The maximum volume for the P O I sound when the P O I is closest."

[Keybinds]
Toggle Keybinds = f8 "Toggles the use of all other FA11y keybinds when pressed, other than itself."
Fire = lctrl "Invokes a left click for firing or using your currently held item."
Target = rctrl "Invokes a right click for aiming your currently held item."
Turn Left = num 1 "Turns the player camera left by moving the mouse using the TurnSensitivity sensitivity."
Turn Right = num 3 "Turns the player camera right by moving the mouse using the TurnSensitivity sensitivity."
Secondary Turn Left = num 4 "Turns the player camera left by moving the mouse using the SecondaryTurnSensitivity sensitivity."
Secondary Turn Right = num 6 "Turns the player camera right by moving the mouse using the SecondaryTurnSensitivity sensitivity."
Look Up = num 8 "Turns the player camera up by moving the mouse using the TurnSensitivity sensitivity."
Look Down = num 2 "Turns the player camera down by moving the mouse using the TurnSensitivity sensitivity."
Turn Around = num 0 "Turns the player camera around 180 degrees by moving the mouse using the TurnAroundSensitivity sensitivity."
Recenter = num 5 "Recenters the player camera using many configurable sensitivity values."
Scroll Up = num 7 "Scrolls up on the current mouse position using the ScrollSensitivity sensitivity."
Scroll Down = num 9 "Scrolls down on the current mouse position using the ScrollSensitivity sensitivity."
Cycle Map =  "Cycles through available maps. Hold Shift to cycle in reverse."
Cycle POI =  "Cycles through POIs in the current map. Hold Shift to cycle in reverse."
Toggle Closest POI =  "Toggles between 'closest' and 'closest landmark' POIs. Hold Shift to toggle in reverse."
Start Navigation = grave "Starts the player navigation process based on the players selected P O I, Game Object, or location."
Check Health Shields = h "Announces the players Health and Shield values."
Announce Direction Faced = semicolon "Announces the direction the player is facing using information from the minimap."
Announce Ammo = j "Announces the current ammo in the mag and reserves."
Check Rarity = bracketleft "Announces the rarity of a selected item when the player is in the in-game inventory."
Open P O I Selector = bracketright "Opens the P O I selector menu, used for choosing where you want to go."
Create Custom P O I = backslash "Creates a custom P O I at the players current position while the full-screen map is open, and prompts the user for a name."
Open Gamemode Selector = apostrophe "Opens the Gamemode Selector GUI, used for selecting which gamemode the user wants to play."
Open Configuration Menu = f9 "Opens the FA11y configuration menu for changing these settings."
Exit Match = f12 "Exits the current match while the in-game quick-menu is open."
Detect Hotbar 1 = 1 "Announces details about the item the player is currently holding in slot 1."
Detect Hotbar 2 = 2 "Announces details about the item the player is currently holding in slot 2."
Detect Hotbar 3 = 3 "Announces details about the item the player is currently holding in slot 3."
Detect Hotbar 4 = 4 "Announces details about the item the player is currently holding in slot 4."
Detect Hotbar 5 = 5 "Announces details about the item the player is currently holding in slot 5."

[POI]
selected_poi = closest, 0, 0
current_map = main"""

def _create_config_parser_with_case_preserved() -> configparser.ConfigParser:
    """Create a ConfigParser that preserves case for keys"""
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # Preserve case for keys
    return parser

def get_default_config_order() -> Dict[str, List[str]]:
    """Get the order of sections and keys in the default config"""
    default_config_parser = _create_config_parser_with_case_preserved()
    default_config_parser.read_string(DEFAULT_CONFIG)
    
    order = {}
    for section in default_config_parser.sections():
        order[section] = list(default_config_parser.options(section))
    
    return order

def reorganize_config(config: configparser.ConfigParser) -> configparser.ConfigParser:
    """Reorganize config according to the default order"""
    default_order = get_default_config_order()
    reorganized_config = _create_config_parser_with_case_preserved()
    
    # First add all sections in the default order
    for section in default_order:
        if not reorganized_config.has_section(section):
            reorganized_config.add_section(section)
        
        # Add keys in default order, preserving values from current config
        for key in default_order[section]:
            if config.has_section(section) and config.has_option(section, key):
                reorganized_config.set(section, key, config.get(section, key))
    
    # Add any sections/keys not in default config
    for section in config.sections():
        if section not in default_order:
            if not reorganized_config.has_section(section):
                reorganized_config.add_section(section)
        
        for key, value in config.items(section):
            if not reorganized_config.has_option(section, key):
                reorganized_config.set(section, key, value)
    
    return reorganized_config

def configs_have_different_values(config1: configparser.ConfigParser, config2: configparser.ConfigParser) -> bool:
    """
    Compare two config parsers for value differences.
    Returns True if any actual values differ (ignoring organization and whitespace).
    """
    # Check all sections in config1
    for section in config1.sections():
        if not config2.has_section(section):
            return True  # Section missing in config2
        
        # Check all options in this section of config1
        for option in config1.options(section):
            if not config2.has_option(section, option):
                return True  # Option missing in config2
            
            # Extract just the value part (before any description in quotes)
            value1 = config1.get(section, option).split('"')[0].strip()
            value2 = config2.get(section, option).split('"')[0].strip()
            
            if value1 != value2:
                return True  # Values differ
    
    # Check for sections in config2 that aren't in config1
    for section in config2.sections():
        if not config1.has_section(section):
            return True  # Section in config2 that's not in config1
        
        # Check for options in config2's section that aren't in config1
        for option in config2.options(section):
            if not config1.has_option(section, option):
                return True  # Option in config2 that's not in config1
    
    # If we get here, the configs have equivalent values
    return False

def configs_differ_structurally(config1: configparser.ConfigParser, config2: configparser.ConfigParser) -> bool:
    """
    Check if configs differ in structure (sections and options).
    This ignores the values and only checks the organization.
    """
    # Check if sections are different
    sections1 = set(config1.sections())
    sections2 = set(config2.sections())
    if sections1 != sections2:
        return True
    
    # Check if options in each section are different
    for section in sections1:
        options1 = set(config1.options(section))
        options2 = set(config2.options(section))
        if options1 != options2:
            return True
    
    # Otherwise, they have the same structure
    return False

def get_config_value(config: configparser.ConfigParser, key: str, fallback: Any = None) -> Tuple[str, str]:
    """Get a config value from any section with its description"""
    for section in ['Toggles', 'Values', 'Keybinds', 'SETTINGS', 'SCRIPT KEYBINDS', 'POI']: 
        if config.has_section(section) and config.has_option(section, key): 
            value = config.get(section, key) 
            parts = value.split('"')
            if len(parts) > 1: 
                return parts[0].strip(), parts[1]
            return parts[0].strip(), "" 
    return str(fallback) if fallback is not None else "", ""

def get_config_section_for_key(key: str, value: str) -> str:
    """Determine which section a key belongs in"""
    toggles_keys = [
        'SimplifySpeechOutput', 'MouseKeys', 'ResetSensitivity', 
        'AnnounceWeaponAttachments', 'AnnounceAmmo', 'AutoUpdates', 
        'CreateDesktopShortcut', 'AutoTurn', 'PerformFacingCheck', 
        'PlayPOISound', 'AnnounceMapStatus', 'AnnounceInventoryStatus'
    ]
    if key in toggles_keys:
        return 'Toggles'
    
    default_parser = _create_config_parser_with_case_preserved()
    default_parser.read_string(DEFAULT_CONFIG)
    if default_parser.has_option('Keybinds', key): 
        return 'Keybinds'

    if value.lower() in ['true', 'false'] and key not in toggles_keys: 
        return 'Toggles'
        
    return 'Values'

def migrate_config_to_new_format(config: configparser.ConfigParser) -> configparser.ConfigParser:
    """Migrate old config format to new format, preserving case"""
    new_config = _create_config_parser_with_case_preserved()
            
    for section_name in ['Toggles', 'Values', 'Keybinds', 'POI']:
        if not new_config.has_section(section_name):
            new_config.add_section(section_name)
            
    if config.has_section('SETTINGS'):
        for key, value_with_desc in config.items('SETTINGS'): 
            value_part = value_with_desc.split('"')[0].strip() 
            target_section = get_config_section_for_key(key, value_part)
            new_config.set(target_section, key, value_with_desc) 
            
    if config.has_section('SCRIPT KEYBINDS'):
        for key, value_with_desc in config.items('SCRIPT KEYBINDS'):
            new_config.set('Keybinds', key, value_with_desc)
            
    if config.has_section('POI'):
        for key, value in config.items('POI'):
            new_config.set('POI', key, value) 
            
    # Reorganize the config according to default order
    new_config = reorganize_config(new_config)
    
    return new_config

def read_config() -> configparser.ConfigParser:
    """Read and parse config file, handling migration and default values"""
    config = _create_config_parser_with_case_preserved()

    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config.read_file(f) 
            if not config.sections(): 
                raise configparser.Error("File contains no section headers or is empty.")
        else:
            raise FileNotFoundError(f"{CONFIG_FILE} not found.")

        is_old_format = config.has_section('SETTINGS') or config.has_section('SCRIPT KEYBINDS')
        
        if is_old_format:
            print("Old config format detected. Migrating to new format...")
            migrated_config = migrate_config_to_new_format(config)
            config = migrated_config 
            with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                config.write(configfile)
            print("Config migrated and saved. Now ensuring all default values are present.")
        
        config = update_config(config) 
            
    except (configparser.Error, FileNotFoundError) as e: 
        print(f"Config file error: {e}. Creating a new one with default values.")
        if os.path.exists(CONFIG_FILE):
            try:
                os.remove(CONFIG_FILE) 
            except OSError as oe:
                print(f"Could not remove existing config file: {oe}")

        config = _create_config_parser_with_case_preserved()
        config.read_string(DEFAULT_CONFIG)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
        print(f"Created new config file: {CONFIG_FILE}")

    return config

def update_config(current_config: configparser.ConfigParser) -> configparser.ConfigParser:
    """Update config with default values and clean up duplicates"""
    default_config_parser = _create_config_parser_with_case_preserved()
    default_config_parser.read_string(DEFAULT_CONFIG)

    # Track different types of changes
    values_changed = False  # Actual values (settings) changed
    structure_changed = False  # Organization/structure changed

    # Ensure all default sections and keys are present
    for section in default_config_parser.sections():
        if not current_config.has_section(section):
            current_config.add_section(section)
            structure_changed = True
            values_changed = True  # New section with values
        
        for key, default_full_value in default_config_parser.items(section):
            if not current_config.has_option(section, key):
                current_config.set(section, key, default_full_value)
                structure_changed = True
                values_changed = True  # New value added
            else:
                # Ensure description consistency
                current_val_str = current_config.get(section, key)
                has_current_desc = '"' in current_val_str
                has_default_desc = '"' in default_full_value
                if not has_current_desc and has_default_desc:
                    current_value_part_only = current_val_str.strip()
                    _, default_desc_only = default_full_value.split('"', 1)
                    if default_desc_only.endswith('"'):
                        default_desc_only = default_desc_only[:-1]
                    current_config.set(section, key, f'{current_value_part_only} "{default_desc_only}"')
                    structure_changed = True  # Description added/changed

    # Clean up duplicates
    for section in current_config.sections():
        if section == "POI":  # Skip POI section for advanced cleanup
            continue

        options_in_section = current_config.options(section)
        keys_to_remove = []
        
        # Find case duplicates
        options_by_lower = {}
        for opt in options_in_section:
            lower_opt = opt.lower()
            if lower_opt not in options_by_lower:
                options_by_lower[lower_opt] = []
            options_by_lower[lower_opt].append(opt)

        for lower_key, cased_keys in options_by_lower.items():
            if len(cased_keys) > 1:  # Found duplicates
                structure_changed = True
                canonical_key_from_default = None
                
                # Find canonical key from default config
                if default_config_parser.has_section(section):
                    for default_opt_key in default_config_parser.options(section):
                        if default_opt_key.lower() == lower_key:
                            canonical_key_from_default = default_opt_key
                            break
                
                if canonical_key_from_default and canonical_key_from_default in cased_keys:
                    # Keep the correctly cased key from default
                    for k_to_check in cased_keys:
                        if k_to_check != canonical_key_from_default:
                            keys_to_remove.append(k_to_check)
                else:
                    # Prioritize user-modified values
                    default_value_for_key = None
                    if canonical_key_from_default and default_config_parser.has_option(section, canonical_key_from_default):
                         default_value_for_key = default_config_parser.get(section, canonical_key_from_default)

                    kept_key = None
                    if default_value_for_key:
                        for k_in_dups in cased_keys:
                            if current_config.get(section, k_in_dups) != default_value_for_key:
                                kept_key = k_in_dups  # Prioritize user-modified value
                                break
                    
                    if not kept_key:
                        kept_key = sorted(cased_keys)[0]  # Keep first one alphabetically

                    for k_to_remove_dup in cased_keys:
                        if k_to_remove_dup != kept_key:
                            keys_to_remove.append(k_to_remove_dup)
        
        # Remove duplicate keys
        for k_rem in keys_to_remove:
            current_config.remove_option(section, k_rem)
            print(f"Removed duplicate key '{k_rem}' from section '[{section}]'")
            values_changed = True  # Consider removing duplicates a value change

    # Always reorganize the config according to default order
    reorganized_config = reorganize_config(current_config)
    
    # Check if only the structure is different but not the actual values
    if not values_changed and not configs_have_different_values(reorganized_config, current_config):
        # Only the structure differs - use the reorganized version but don't report it as changed
        should_report_update = False
    else:
        # Either values changed or reorganized version has different values
        should_report_update = True
    
    # Always use the reorganized config
    current_config = reorganized_config

    # Save if we have any changes (structural or values)
    if values_changed or structure_changed:
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                current_config.write(configfile)
            if should_report_update:
                print(f"Config file '{CONFIG_FILE}' was updated.")
        except IOError as e:
            print(f"Error writing updated config file: {e}")
            
    return current_config

def get_default_config_value_string(section_name: str, key_name: str) -> Optional[str]:
    """Get the default value string for a specific key"""
    default_config_parser = _create_config_parser_with_case_preserved()
    default_config_parser.read_string(DEFAULT_CONFIG)
    if default_config_parser.has_option(section_name, key_name):
        return default_config_parser.get(section_name, key_name) 
    print(f"Warning: Default value for [{section_name}] {key_name} not found in DEFAULT_CONFIG.")
    return None

def get_config_int(config: configparser.ConfigParser, key: str, fallback: Optional[int] = None) -> Optional[int]:
    """Get an integer config value from any section"""
    value, _ = get_config_value(config, key, str(fallback) if fallback is not None else None)
    try:
        return int(value)
    except (ValueError, TypeError):
        return fallback

def get_config_float(config: configparser.ConfigParser, key: str, fallback: Optional[float] = None) -> Optional[float]:
    """Get a float config value from any section"""
    value, _ = get_config_value(config, key, str(fallback) if fallback is not None else None)
    try:
        return float(value)
    except (ValueError, TypeError):
        return fallback

def get_config_boolean(config: configparser.ConfigParser, key: str, fallback: bool = False) -> bool:
    """Get a boolean config value from any section"""
    value, _ = get_config_value(config, key, str(fallback))
    return value.lower() in ('true', 'yes', 'on', '1')

def force_focus_window(window, speak_text: Optional[str] = None, focus_widget: Optional[Union[callable, Any]] = None) -> None:
    """Force focus on a given window with optional speech and widget focus"""
    window.deiconify()
    window.attributes('-topmost', True)
    window.update()
    window.lift()

    # Try to get window handle
    hwnd = None
    try:
        hwnd = win32gui.GetParent(window.winfo_id())
        if hwnd == 0: 
            hwnd = window.winfo_id()
    except Exception as e:
        print(f"Error getting window handle: {e}")
        window.focus_force()
        if speak_text: speaker.speak(speak_text)
        if focus_widget:
            if callable(focus_widget): window.after(100, focus_widget)
            else: window.after(100, focus_widget.focus_set)
        return

    if hwnd == 0: 
        print("Invalid window handle. Using Tkinter focus_force.")
        window.focus_force()
        if speak_text: speaker.speak(speak_text)
        if focus_widget:
            if callable(focus_widget): window.after(100, focus_widget)
            else: window.after(100, focus_widget.focus_set)
        return

    # Setup window for focus
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    shell = win32com.client.Dispatch("WScript.Shell")
    ctypes.windll.user32.ReleaseCapture()

    try:
        ctypes.windll.user32.AllowSetForegroundWindow(win32api.GetCurrentProcessId())
    except Exception as e:
        print(f"AllowSetForegroundWindow failed: {e}")

    # Attempt thread attachment for foreground control
    foreground_thread_id = None
    current_thread_id = win32api.GetCurrentThreadId()

    try:
        foreground_window = win32gui.GetForegroundWindow()
        if foreground_window != 0 and foreground_window != hwnd:
            fg_tid, fg_pid = win32process.GetWindowThreadProcessId(foreground_window)
            foreground_thread_id = fg_tid
            if foreground_thread_id != 0 and current_thread_id != 0 and foreground_thread_id != current_thread_id:
                 win32process.AttachThreadInput(foreground_thread_id, current_thread_id, True)
    except Exception as e:
        print(f"AttachThreadInput failed: {e}")

    # Try multiple methods to set focus
    for _ in range(15): 
        try:
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetFocus(hwnd) 

            if win32gui.GetForegroundWindow() == hwnd:
                break

            shell.SendKeys('%') 
            time.sleep(0.05) 
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.BringWindowToTop(hwnd)
            ctypes.windll.user32.SwitchToThisWindow(hwnd, True)

            if win32gui.GetForegroundWindow() == hwnd:
                break
        except pywintypes.error as pye:
            if pye.winerror == 1400: 
                print("Invalid window handle (1400).")
                break
            elif pye.winerror == 5: 
                print("Focus access denied (5).")
            pass 
        except Exception:
            pass
        time.sleep(0.1) 
    else:
        print("Failed to set window focus after multiple attempts.")

    # Cleanup and finalize
    try:
        if foreground_thread_id is not None and foreground_thread_id != 0 and current_thread_id != 0 and foreground_thread_id != current_thread_id:
            win32process.AttachThreadInput(foreground_thread_id, current_thread_id, False)
    except Exception as e:
        print(f"DetachThreadInput failed: {e}")

    window.focus_force()
    window.attributes('-topmost', False) 

    if speak_text:
        speaker.speak(speak_text)

    if focus_widget:
        if callable(focus_widget):
            window.after(100, focus_widget)
        else:
            window.after(100, focus_widget.focus_set)

    # Final attempt with SetWindowPos if needed
    if win32gui.GetForegroundWindow() != hwnd:
        try:
            current_pos = win32gui.GetWindowRect(hwnd)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST,
                                current_pos[0], current_pos[1],
                                current_pos[2] - current_pos[0], current_pos[3] - current_pos[1],
                                win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE) 
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST,
                                current_pos[0], current_pos[1],
                                current_pos[2] - current_pos[0], current_pos[3] - current_pos[1],
                                win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE)
            win32gui.SetForegroundWindow(hwnd) 
        except Exception as e:
            print(f"Failed to force focus using SetWindowPos: {e}")
            
    # Move cursor to window center
    try:
        rect = win32gui.GetWindowRect(hwnd)
        center_x = (rect[0] + rect[2]) // 2
        center_y = (rect[1] + rect[3]) // 2
        ctypes.windll.user32.SetCursorPos(center_x, center_y)
    except Exception as e:
        print(f"Failed to move cursor to window center: {e}")

class Config:
    """Config adapter class for UI components"""
    def __init__(self, config_file=CONFIG_FILE): 
        self.config_file = config_file
        self.config = read_config()  
        
    def get_value(self, key, section=None, fallback=None):
        """Get a config value with optional section"""
        if section:
            if self.config.has_section(section) and self.config.has_option(section, key):
                value_string = self.config.get(section, key) 
                if '"' in value_string:
                    return value_string.split('"')[0].strip()
                return value_string.strip()
            return str(fallback) if fallback is not None else ""
        else:
            for sec_name in ['Toggles', 'Values', 'Keybinds', 'POI']: 
                 if self.config.has_section(sec_name) and self.config.has_option(sec_name, key):
                    value_string = self.config.get(sec_name, key)
                    if '"' in value_string:
                        return value_string.split('"')[0].strip()
                    return value_string.strip()
            return str(fallback) if fallback is not None else ""
    
    def get_boolean(self, key, section=None, fallback=False):
        """Get a boolean config value"""
        value_str = self.get_value(key, section, str(fallback))
        return value_str.lower() in ('true', 'yes', 'on', '1')
    
    def get_int(self, key, section=None, fallback=0):
        """Get an integer config value"""
        value_str = self.get_value(key, section, str(fallback))
        try:
            return int(value_str)
        except (ValueError, TypeError):
            return fallback if isinstance(fallback, int) else 0
    
    def get_float(self, key, section=None, fallback=0.0):
        """Get a float config value"""
        value_str = self.get_value(key, section, str(fallback))
        try:
            return float(value_str)
        except (ValueError, TypeError):
            return fallback if isinstance(fallback, float) else 0.0
    
    def set_value(self, key, value, section):
        """Set a config value, preserving description"""
        if not self.config.has_section(section):
            self.config.add_section(section)
            
        current_full_value = ""
        if self.config.has_option(section, key):
             current_full_value = self.config.get(section, key)
        
        description = ""
        if '"' in current_full_value:
            description = current_full_value.split('"', 1)[1] 
            if description.endswith('"'):
                description = description[:-1] 
            description = f' "{description}"' 
            
        self.config.set(section, key, f"{str(value)}{description}") 
    
    def set_poi(self, name, x, y):
        """Set the selected POI"""
        self.set_value('selected_poi', f"{name}, {x}, {y}", 'POI')
    
    def set_current_map(self, map_name):
        """Set the current map"""
        self.set_value('current_map', map_name, 'POI')
    
    def save(self):
        """Save configuration to file"""
        # Reorganize before saving
        self.config = reorganize_config(self.config)
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                self.config.write(f)
        except IOError as e:
            print(f"Error saving config file {self.config_file}: {e}")
