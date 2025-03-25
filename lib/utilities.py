import os
import time
import ctypes
import configparser
from typing import Dict, Tuple, Optional, Any, Union

import pywintypes
import win32gui
import win32con
import win32com.client
import win32api
import win32process
from accessible_output2.outputs.auto import Auto

speaker = Auto()
CONFIG_FILE = 'config.txt'

# Modified DEFAULT_CONFIG to use new section format
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
AnnounceSpectatingStatus = true "Toggles announcements when spectating status changes."
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
PathfindingCheckInterval = 0.3 "The interval in seconds between pathfinding position checks."
PathfindingPointRadius = 10 "The radius in meters within which a pathfinding point is considered reached."
MinimumMovementDistance = 1 "The minimum distance the player must move in meters within a second while pathfinding to avoid pressing the spacebar."
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
Toggle Pathfinding = p "Toggles pathfinding for the current selected POI or position."
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

# Mapping for where settings should go in new format
SETTINGS_MAPPING = {
    'MouseKeys': 'Toggles',
    'ResetSensitivity': 'Toggles',
    'AnnounceWeaponAttachments': 'Toggles',
    'AnnounceAmmo': 'Toggles',
    'AutoUpdates': 'Toggles',
    'CreateDesktopShortcut': 'Toggles',
    'AutoTurn': 'Toggles',
    'PerformFacingCheck': 'Toggles',
    # All other settings go to Values by default
}

def get_config_value(config: configparser.ConfigParser, key: str, fallback: Any = None) -> Tuple[str, str]:
    """Get a configuration value from any section.
    
    Args:
        config: The configuration parser object
        key: The key to look for
        fallback: The fallback value if key is not found
        
    Returns:
        tuple: (value, description)
    """
    for section in ['Toggles', 'Values', 'Keybinds', 'SETTINGS', 'SCRIPT KEYBINDS']:
        if section in config and key in config[section]:
            value = config[section][key]
            parts = value.split('"')
            if len(parts) > 1:
                return parts[0].strip(), parts[1]
            return parts[0].strip(), ""
    return fallback, ""

def get_config_section_for_key(key: str, value: str) -> str:
    """Determine which section a key should be in based on its value and mapping.
    
    Args:
        key: The configuration key
        value: The value associated with the key
        
    Returns:
        str: The appropriate section name
    """
    if key in SETTINGS_MAPPING:
        return SETTINGS_MAPPING[key]
    if value.lower() in ['true', 'false']:
        return 'Toggles'
    return 'Values'

def migrate_config_to_new_format(config: configparser.ConfigParser) -> configparser.ConfigParser:
    """Migrate an old format config to the new format.
    
    Args:
        config: The old configuration parser object
        
    Returns:
        ConfigParser: The new format configuration
    """
    new_config = configparser.ConfigParser(interpolation=None)
    new_config.optionxform = str
    
    # Initialize new sections
    new_config.add_section('Toggles')
    new_config.add_section('Values')
    new_config.add_section('Keybinds')
    
    # Migrate settings
    if 'SETTINGS' in config:
        for key, value in config['SETTINGS'].items():
            target_section = get_config_section_for_key(key, value.split('"')[0].strip())
            new_config[target_section][key] = value
            
    # Migrate keybinds
    if 'SCRIPT KEYBINDS' in config:
        for key, value in config['SCRIPT KEYBINDS'].items():
            new_config['Keybinds'][key] = value
            
    # Preserve POI section
    if 'POI' in config:
        new_config.add_section('POI')
        for key, value in config['POI'].items():
            new_config['POI'][key] = value
            
    return new_config

def read_config() -> configparser.ConfigParser:
    """Read and parse the configuration file, converting to new format if needed.
    
    Returns:
        ConfigParser: The configuration parser object
    """
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str

    try:
        if os.path.exists(CONFIG_FILE):
            config.read(CONFIG_FILE)
            if not config.sections():
                raise configparser.MissingSectionHeaderError(CONFIG_FILE, 1, "File contains no section headers.")
        else:
            raise FileNotFoundError

        # Check if config needs migration
        if 'SETTINGS' in config.sections() or 'SCRIPT KEYBINDS' in config.sections():
            print("Converting config to new format...")
            config = migrate_config_to_new_format(config)
            
        config = update_config(config)
        
        # Save the migrated config
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
            
    except (configparser.MissingSectionHeaderError, FileNotFoundError):
        print(f"Config file is corrupted or missing. Creating a new one with default values.")
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
        config.read_string(DEFAULT_CONFIG)
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
        print(f"Created new config file: {CONFIG_FILE}")

    return config

def update_config(config: configparser.ConfigParser) -> configparser.ConfigParser:
    """Update the configuration file with default values if necessary.
    
    Args:
        config: The configuration parser object
        
    Returns:
        ConfigParser: The updated configuration
    """
    default_config = configparser.ConfigParser(interpolation=None)
    default_config.optionxform = str
    default_config.read_string(DEFAULT_CONFIG)

    updated = False

    # Ensure all sections exist
    for section in default_config.sections():
        if not config.has_section(section):
            config.add_section(section)
            updated = True

    # Update all sections
    for section in default_config.sections():
        if section == 'POI':
            continue  # Skip POI section as it's user-specific
            
        new_section = {}
        existing_keys = {k.lower(): (k, config[section][k]) for k in config[section]}

        for key, value in default_config.items(section):
            lower_key = key.lower()
            default_value, default_description = get_config_value(default_config, key)

            if lower_key in existing_keys:
                original_key, existing_value = existing_keys[lower_key]
                existing_value, existing_description = get_config_value(config, original_key)

                if original_key != key:
                    updated = True

                new_value = f"{existing_value}"
                if existing_description:
                    new_value += f' "{existing_description}"'
                elif default_description:
                    new_value += f' "{default_description}"'
                    updated = True

                new_section[key] = new_value
            else:
                new_section[key] = value
                updated = True

        config[section] = new_section

    if updated:
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
        print(f"Updated config file: {CONFIG_FILE}")

    return config

def get_config_int(config: configparser.ConfigParser, key: str, fallback: Optional[int] = None) -> Optional[int]:
    """Get an integer configuration value from any section.
    
    Args:
        config: The configuration parser object
        key: The key to look for
        fallback: The fallback value if key is not found or invalid
        
    Returns:
        int or None: The integer value or fallback
    """
    value, _ = get_config_value(config, key, fallback)
    try:
        return int(value)
    except (ValueError, TypeError):
        return fallback

def get_config_float(config: configparser.ConfigParser, key: str, fallback: Optional[float] = None) -> Optional[float]:
    """Get a float configuration value from any section.
    
    Args:
        config: The configuration parser object
        key: The key to look for
        fallback: The fallback value if key is not found or invalid
        
    Returns:
        float or None: The float value or fallback
    """
    value, _ = get_config_value(config, key, fallback)
    try:
        return float(value)
    except (ValueError, TypeError):
        return fallback

def get_config_boolean(config: configparser.ConfigParser, key: str, fallback: bool = False) -> bool:
    """Get a boolean configuration value from any section.
    
    Args:
        config: The configuration parser object
        key: The key to look for
        fallback: The fallback value if key is not found or invalid
        
    Returns:
        bool: The boolean value or fallback
    """
    value, _ = get_config_value(config, key, str(fallback))
    return value.lower() in ('true', 'yes', 'on', '1')

def force_focus_window(window, speak_text: Optional[str] = None, focus_widget: Optional[Union[callable, Any]] = None) -> None:
    """Force focus on a given window, with optional speech and widget focus.

    Args:
        window: The window to focus
        speak_text: Text to speak after focusing
        focus_widget: Widget to focus after window is focused
    """
    window.deiconify()
    window.attributes('-topmost', True)
    window.update()
    window.lift()

    hwnd = win32gui.GetParent(window.winfo_id())

    # Ensure window is not minimized
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    shell = win32com.client.Dispatch("WScript.Shell")

    # Release mouse capture from other windows
    ctypes.windll.user32.ReleaseCapture()

    # Try to allow the process to set the foreground window
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(ctypes.windll.kernel32.GetCurrentProcessId())
    except Exception as e:
        print(f"AllowSetForegroundWindow failed: {e}")

    # Initialize foreground_thread_id to None
    foreground_thread_id = None

    # Attach input threads
    try:
        current_thread_id = win32api.GetCurrentThreadId()
        foreground_window = win32gui.GetForegroundWindow()
        if foreground_window != hwnd:
            foreground_thread_id = win32process.GetWindowThreadProcessId(foreground_window)[0]
            ctypes.windll.user32.AttachThreadInput(foreground_thread_id, current_thread_id, True)
    except Exception as e:
        print(f"AttachThreadInput failed: {e}")

    # Try multiple methods to bring the window to the foreground
    for _ in range(15):
        try:
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetFocus(hwnd)
            win32gui.SetActiveWindow(hwnd)

            if win32gui.GetForegroundWindow() == hwnd:
                break

            # Alternative methods
            shell.SendKeys('%')
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.BringWindowToTop(hwnd)
            ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
            ctypes.windll.user32.SetFocus(hwnd)
            ctypes.windll.user32.SetActiveWindow(hwnd)

            if win32gui.GetForegroundWindow() == hwnd:
                break
        except pywintypes.error:
            pass

        time.sleep(0.1)
    else:
        print("Failed to set window focus after multiple attempts")

    # Detach input threads
    try:
        if foreground_thread_id is not None:
            ctypes.windll.user32.AttachThreadInput(foreground_thread_id, current_thread_id, False)
    except Exception as e:
        print(f"DetachThreadInput failed: {e}")

    if speak_text:
        speaker.speak(speak_text)

    if focus_widget:
        if callable(focus_widget):
            window.after(100, focus_widget)
        else:
            window.after(100, focus_widget.focus_set)

    # Final check and fallback using SetWindowPos
    if win32gui.GetForegroundWindow() != hwnd:
        try:
            current_pos = win32gui.GetWindowRect(hwnd)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST,
                                current_pos[0], current_pos[1],
                                current_pos[2] - current_pos[0], current_pos[3] - current_pos[1],
                                win32con.SWP_SHOWWINDOW)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST,
                                current_pos[0], current_pos[1],
                                current_pos[2] - current_pos[0], current_pos[3] - current_pos[1],
                                win32con.SWP_SHOWWINDOW)
        except Exception as e:
            print(f"Failed to force focus using SetWindowPos: {e}")

    # Attempt to move mouse cursor to the center of the window
    try:
        rect = win32gui.GetWindowRect(hwnd)
        center_x = (rect[0] + rect[2]) // 2
        center_y = (rect[1] + rect[3]) // 2
        ctypes.windll.user32.SetCursorPos(center_x, center_y)
    except Exception as e:
        print(f"Failed to move cursor to window center: {e}")

# New additions for supporting the updated UI system

def resolve_path(relative_path):
    """
    Resolve a relative path to an absolute path.
    
    Args:
        relative_path: Relative path to resolve
        
    Returns:
        str: Absolute path
    """
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))  # lib directory
    root_dir = os.path.dirname(script_dir)  # root directory (where FA11y.py is)
    return os.path.join(root_dir, relative_path)

class Config:
    """
    Config adapter class that bridges between FA11y's existing config system
    and what the new UI components expect.
    """
    def __init__(self, config_file='config.txt'):
        """
        Initialize with a ConfigParser instance or create a new one.
        
        Args:
            config_file: Path to config file
        """
        self.config_file = config_file
        self.config = read_config()  # Use existing read_config function
        
    def get_value(self, key, section=None, fallback=None):
        """
        Get a value from the configuration.
        
        Args:
            key: Configuration key
            section: Optional section name (will search all sections if None)
            fallback: Default value if not found
            
        Returns:
            The configuration value
        """
        if section:
            if section in self.config.sections() and key in self.config[section]:
                value_string = self.config[section][key]
                # Extract just the value part (before any description in quotes)
                if '"' in value_string:
                    return value_string.split('"')[0].strip()
                return value_string
            return fallback
        else:
            return get_config_value(self.config, key, fallback)[0]
    
    def get_boolean(self, key, section=None, fallback=False):
        """Get a boolean value from configuration."""
        if section:
            value = self.get_value(key, section, str(fallback))
            return value.lower() in ('true', 'yes', 'on', '1')
        else:
            return get_config_boolean(self.config, key, fallback)
    
    def get_int(self, key, section=None, fallback=0):
        """Get an integer value from configuration."""
        if section:
            value = self.get_value(key, section, fallback)
            try:
                return int(value)
            except (ValueError, TypeError):
                return fallback
        else:
            return get_config_int(self.config, key, fallback)
    
    def get_float(self, key, section=None, fallback=0.0):
        """Get a float value from configuration."""
        if section:
            value = self.get_value(key, section, fallback)
            try:
                return float(value)
            except (ValueError, TypeError):
                return fallback
        else:
            return get_config_float(self.config, key, fallback)
    
    def set_value(self, key, value, section):
        """
        Set a configuration value.
        
        Args:
            key: Configuration key
            value: Value to set
            section: Section name
        """
        if section not in self.config.sections():
            self.config.add_section(section)
            
        # Preserve any existing description
        current = self.config[section].get(key, "")
        description = ""
        if current and '"' in current:
            description = current.split('"', 1)[1].strip()
            description = f' "{description}"'
            
        self.config[section][key] = f"{value}{description}"
    
    def set_poi(self, name, x, y):
        """
        Set the selected POI.
        
        Args:
            name: POI name
            x: X coordinate
            y: Y coordinate
        """
        self.set_value('selected_poi', f"{name}, {x}, {y}", 'POI')
    
    def set_current_map(self, map_name):
        """
        Set the current map.
        
        Args:
            map_name: Map name
        """
        self.set_value('current_map', map_name, 'POI')
    
    def save(self):
        """Save configuration to file."""
        with open(self.config_file, 'w') as f:
            self.config.write(f)