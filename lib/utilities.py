import win32gui
import win32con
import win32com.client
import ctypes
import time
import pywintypes
from accessible_output2.outputs.auto import Auto
import configparser
import os

speaker = Auto()
CONFIG_FILE = 'config.txt'

DEFAULT_CONFIG = """[SETTINGS]
MouseKeys = true "Toggles the keybinds used to look around, left click, and right click."
ResetSensitivity = false "Toggles between two sensitivity values for certain mouse movements, like recentering the camera. Do not change this if you are a new player."
AnnounceWeaponAttachments = true "Toggles the announcements of weapon attachments when equipping weapons."
AnnounceAmmo = true "Toggles the announcements of ammo count when equipping weapons."
AutoUpdates = true "Toggles automatic updates of FA11y."
CreateDesktopShortcut = true "Toggles the creation of a desktop shortcut for FA11y on launch."
AutoTurn = true "Toggles the automatic turning feature when navigating to a position. When toggled on, your player will automatically turn towards your selected location when getting navigation info."
PerformFacingCheck = true "Toggles whether to check if the player is facing the next point. When enabled, it affects audio feedback by playing a distinct sound when facing the next point. This setting does not affect AutoTurn."
PlayNorthSound = true "Toggles whether the north direction sound should play when turning."
TurnSensitivity = 100 "The sensitivity used for primary turning left, primary turning right, looking up, and looking down when MouseKeys is enabled."
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
NorthSoundVolume = 0.1 "Controls the volume of the north direction sound (0.0 to 1.0)."
NorthSoundPitchShift = 0.5 "Controls the pitch shift of the north sound when it's behind the player (0.1 to 1.0, where 0.5 is 50 percent lower pitch)."

[SCRIPT KEYBINDS]
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
Get Current Coordinates = c "Gets the players current map coordinates when the full-screen map is open. Useful for relaying to teammates."
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
selected_poi = closest, 0, 0"""

def force_focus_window(window, speak_text=None, focus_widget=None):
    window.deiconify()
    window.attributes('-topmost', True)
    window.update()
    window.lift()
    
    hwnd = win32gui.GetParent(window.winfo_id())
    
    # Ensure window is not minimized
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    
    shell = win32com.client.Dispatch("WScript.Shell")
    
    for _ in range(10):  # Increased retry attempts
        try:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, 
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, 
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetForegroundWindow(hwnd)
            
            # Check if focus was successful
            if win32gui.GetForegroundWindow() == hwnd:
                break
            
            # Alternative focus method
            shell.SendKeys('%')
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            
            # Check again
            if win32gui.GetForegroundWindow() == hwnd:
                break
        except pywintypes.error:
            pass
        
        time.sleep(0.2)  # Increased delay
    else:
        print("Failed to set window focus after multiple attempts")

    if speak_text:
        speaker.speak(speak_text)
    
    if focus_widget:
        if callable(focus_widget):
            window.after(100, focus_widget)
        else:
            window.after(100, focus_widget.focus_set)

    # Final check and fallback
    if win32gui.GetForegroundWindow() != hwnd:
        try:
            ctypes.windll.user32.BlockInput(True)  # Block input to force focus
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            time.sleep(0.1)
            ctypes.windll.user32.BlockInput(False)
        except:
            print("Failed to force focus using ctypes")

def get_config_value(config, section, key, fallback=None):
    try:
        value = config.get(section, key)
        parts = value.split('"')
        if len(parts) > 1:
            return parts[0].strip(), parts[1]
        else:
            return parts[0].strip(), ""
    except configparser.NoOptionError:
        return fallback, ""

def get_config_int(config, section, key, fallback=None):
    value, _ = get_config_value(config, section, key, fallback)
    return int(value) if value is not None else None

def get_config_float(config, section, key, fallback=None):
    value, _ = get_config_value(config, section, key, fallback)
    return float(value) if value is not None else None

def get_config_boolean(config, section, key, fallback=False):
    value, _ = get_config_value(config, section, key, str(fallback))
    return value.lower() in ('true', 'yes', 'on', '1')

def read_config():
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    
    try:
        if os.path.exists(CONFIG_FILE):
            config.read(CONFIG_FILE)
            # Check if the file is empty or missing section headers
            if not config.sections():
                raise configparser.MissingSectionHeaderError(CONFIG_FILE, 1, "File contains no section headers.")
        else:
            raise FileNotFoundError
        
        config = update_config(config)
    except (configparser.MissingSectionHeaderError, FileNotFoundError):
        print(f"Config file is corrupted or missing. Creating a new one with default values.")
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
        config.read_string(DEFAULT_CONFIG)
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
        print(f"Created new config file: {CONFIG_FILE}")
    
    return config

def update_config(config):
    default_config = configparser.ConfigParser(interpolation=None)
    default_config.optionxform = str
    default_config.read_string(DEFAULT_CONFIG)
    
    updated = False
    
    for section in default_config.sections():
        if not config.has_section(section):
            config.add_section(section)
            updated = True
        
        new_section = {}
        existing_keys = {k.lower(): (k, config[section][k]) for k in config[section]}
        
        for key, value in default_config.items(section):
            lower_key = key.lower()
            default_value, default_description = get_config_value(default_config, section, key)
            
            if lower_key in existing_keys:
                original_key, existing_value = existing_keys[lower_key]
                existing_value, existing_description = get_config_value(config, section, original_key)
                
                if original_key != key:
                    updated = True
                
                # Preserve existing value, use default description if no existing description
                new_value = f"{existing_value}"
                if existing_description:
                    new_value += f' "{existing_description}"'
                elif default_description:
                    new_value += f' "{default_description}"'
                    updated = True
                
                new_section[key] = new_value
            else:
                new_section[key] = value  # This includes the default description
                updated = True
        
        config[section] = new_section
    
    # Always rewrite the config file to ensure order is maintained
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)
    
    if updated:
        print(f"Updated config file: {CONFIG_FILE}")
    
    return config

