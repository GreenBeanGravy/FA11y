import win32api
import win32con
from typing import List, Tuple, Optional, Set

# Define OEM VK codes if not present in win32con, common values are used.
# These might vary slightly by Windows version/locale but are generally standard.
VK_OEM_1 = getattr(win32con, 'VK_OEM_1', 0xBA)  # ';:' for US
VK_OEM_PLUS = getattr(win32con, 'VK_OEM_PLUS', 0xBB)  # '=+'
VK_OEM_COMMA = getattr(win32con, 'VK_OEM_COMMA', 0xBC)  # ',<'
VK_OEM_MINUS = getattr(win32con, 'VK_OEM_MINUS', 0xBD)  # '-_'
VK_OEM_PERIOD = getattr(win32con, 'VK_OEM_PERIOD', 0xBE)  # '.>'
VK_OEM_2 = getattr(win32con, 'VK_OEM_2', 0xBF)  # '/?'
VK_OEM_3 = getattr(win32con, 'VK_OEM_3', 0xC0)  # '`~'
VK_OEM_4 = getattr(win32con, 'VK_OEM_4', 0xDB)  # '[{'
VK_OEM_5 = getattr(win32con, 'VK_OEM_5', 0xDC)  # '\|'
VK_OEM_6 = getattr(win32con, 'VK_OEM_6', 0xDD)  # ']}'
VK_OEM_7 = getattr(win32con, 'VK_OEM_7', 0xDE)  # ''"'

# Additional mouse button VK codes
VK_XBUTTON1 = getattr(win32con, 'VK_XBUTTON1', 0x05)  # Mouse button 4 (back)
VK_XBUTTON2 = getattr(win32con, 'VK_XBUTTON2', 0x06)  # Mouse button 5 (forward)

# Additional standard VK codes that might be missing from win32con
VK_LWIN = getattr(win32con, 'VK_LWIN', 0x5B)
VK_RWIN = getattr(win32con, 'VK_RWIN', 0x5C)
VK_APPS = getattr(win32con, 'VK_APPS', 0x5D) # Context menu key
VK_SLEEP = getattr(win32con, 'VK_SLEEP', 0x5F)

# Media keys
VK_MEDIA_NEXT_TRACK = getattr(win32con, 'VK_MEDIA_NEXT_TRACK', 0xB0)
VK_MEDIA_PREV_TRACK = getattr(win32con, 'VK_MEDIA_PREV_TRACK', 0xB1)
VK_MEDIA_STOP = getattr(win32con, 'VK_MEDIA_STOP', 0xB2)
VK_MEDIA_PLAY_PAUSE = getattr(win32con, 'VK_MEDIA_PLAY_PAUSE', 0xB3)
VK_VOLUME_MUTE = getattr(win32con, 'VK_VOLUME_MUTE', 0xAD)
VK_VOLUME_DOWN = getattr(win32con, 'VK_VOLUME_DOWN', 0xAE)
VK_VOLUME_UP = getattr(win32con, 'VK_VOLUME_UP', 0xAF)

# Virtual Key Codes for NUMPAD, Special Keys, and Mouse Buttons
VK_KEYS = {
    # Numpad - Standardized to use symbols
    'num 0': win32con.VK_NUMPAD0,
    'num 1': win32con.VK_NUMPAD1,
    'num 2': win32con.VK_NUMPAD2,
    'num 3': win32con.VK_NUMPAD3,
    'num 4': win32con.VK_NUMPAD4,
    'num 5': win32con.VK_NUMPAD5,
    'num 6': win32con.VK_NUMPAD6,
    'num 7': win32con.VK_NUMPAD7,
    'num 8': win32con.VK_NUMPAD8,
    'num 9': win32con.VK_NUMPAD9,
    'num .': win32con.VK_DECIMAL,
    'num +': win32con.VK_ADD,
    'num -': win32con.VK_SUBTRACT,
    'num *': win32con.VK_MULTIPLY,
    'num /': win32con.VK_DIVIDE,
    
    # Control keys
    'lctrl': win32con.VK_LCONTROL,
    'rctrl': win32con.VK_RCONTROL,
    'lshift': win32con.VK_LSHIFT,
    'rshift': win32con.VK_RSHIFT,
    'lalt': win32con.VK_LMENU,
    'ralt': win32con.VK_RMENU,
    'lwin': VK_LWIN,
    'rwin': VK_RWIN,
    'apps': VK_APPS, # Context menu key
    
    # Mouse buttons
    'middle mouse': getattr(win32con, 'VK_MBUTTON', 0x04),
    'mouse 4': VK_XBUTTON1,
    'mouse 5': VK_XBUTTON2,
    
    # Function keys
    'f1': win32con.VK_F1,
    'f2': win32con.VK_F2,
    'f3': win32con.VK_F3,
    'f4': win32con.VK_F4,
    'f5': win32con.VK_F5,
    'f6': win32con.VK_F6,
    'f7': win32con.VK_F7,
    'f8': win32con.VK_F8,
    'f9': win32con.VK_F9,
    'f10': win32con.VK_F10,
    'f11': win32con.VK_F11,
    'f12': win32con.VK_F12,
    
    # Main keyboard keys
    'tab': win32con.VK_TAB,
    'capslock': win32con.VK_CAPITAL,
    'space': win32con.VK_SPACE,
    'backspace': win32con.VK_BACK,
    'enter': win32con.VK_RETURN,
    'esc': win32con.VK_ESCAPE,
    
    # Navigation keys
    'insert': win32con.VK_INSERT,
    'delete': win32con.VK_DELETE,
    'home': win32con.VK_HOME,
    'end': win32con.VK_END,
    'pageup': win32con.VK_PRIOR,
    'pagedown': win32con.VK_NEXT,
    'up': win32con.VK_UP,
    'down': win32con.VK_DOWN,
    'left': win32con.VK_LEFT,
    'right': win32con.VK_RIGHT,
    
    # System keys
    'printscreen': win32con.VK_SNAPSHOT,
    'scrolllock': win32con.VK_SCROLL,
    # 'pause' key is intentionally omitted to ignore it completely
    'numlock': win32con.VK_NUMLOCK,
    'sleep': VK_SLEEP,
    
    # OEM keys (symbols)
    'bracketleft': VK_OEM_4,  # For '['
    'bracketright': VK_OEM_6,  # For ']'
    'apostrophe': VK_OEM_7,  # For "'"
    'grave': VK_OEM_3,  # For '`'
    'backslash': VK_OEM_5,  # For '\'
    'semicolon': VK_OEM_1,  # For ';'
    'period': VK_OEM_PERIOD,  # For '.'
    'comma': VK_OEM_COMMA,  # For ','
    'minus': VK_OEM_MINUS,  # For '-' (main keyboard)
    'equals': VK_OEM_PLUS,  # For '=' (main keyboard)
    'slash': VK_OEM_2,  # For '/' (main keyboard)
    
    # Media keys
    'mediaplay': VK_MEDIA_PLAY_PAUSE,
    'mediastop': VK_MEDIA_STOP,
    'medianext': VK_MEDIA_NEXT_TRACK,
    'mediaprev': VK_MEDIA_PREV_TRACK,
    'volumeup': VK_VOLUME_UP,
    'volumedown': VK_VOLUME_DOWN,
    'volumemute': VK_VOLUME_MUTE,
}

# Supported modifier keys (lctrl and rctrl are NOT modifiers, but can be used as individual keys)
MODIFIER_KEYS = {
    'lshift': win32con.VK_LSHIFT,
    'rshift': win32con.VK_RSHIFT,
    'lalt': win32con.VK_LMENU,
    'ralt': win32con.VK_RMENU,
}

def is_key_pressed(key: str) -> bool:
    """
    Checks if a specific key is currently pressed.
    Args:
        key: The string representation of the key (e.g., 'a', 'num 5', 'lctrl', 'middle mouse').
    Returns:
        True if the key is pressed, False otherwise or if the key is unrecognized.
    """
    if not key:
        return False
        
    key_lower = key.lower()
    vk_code = 0

    if key_lower in VK_KEYS:
        vk_code = VK_KEYS[key_lower]
    else:
        # Try to map single characters
        if len(key_lower) == 1:
            try:
                vk_code = ord(key_lower.upper())
            except TypeError: 
                return False 
        else:
            return False 
    
    if vk_code == 0: 
        return False

    return win32api.GetAsyncKeyState(vk_code) & 0x8000 != 0

def parse_key_combination(key_combo: str) -> Tuple[List[str], str]:
    """
    Parse a key combination string into modifiers and main key.
    
    Args:
        key_combo: String like "lshift+a" or "ralt+lshift+f1" or just "a"
    
    Returns:
        Tuple of (modifier_list, main_key)
    """
    if not key_combo:
        return [], ""
    
    parts = [part.strip().lower() for part in key_combo.split('+')]
    if not parts:
        return [], ""
    
    # Last part is the main key, others are modifiers
    main_key = parts[-1]
    modifiers = parts[:-1]
    
    # Validate modifiers
    valid_modifiers = []
    for modifier in modifiers:
        if modifier in MODIFIER_KEYS:
            valid_modifiers.append(modifier)
        else:
            # Invalid modifier, treat entire combination as invalid
            return [], key_combo
    
    return valid_modifiers, main_key

def is_key_combination_pressed(key_combo: str) -> bool:
    """
    Check if a key combination is currently pressed.
    
    Args:
        key_combo: String like "lshift+a" or "ralt+lshift+f1" or just "a"
    
    Returns:
        True if the combination is pressed, False otherwise
    """
    if not key_combo:
        return False
    
    modifiers, main_key = parse_key_combination(key_combo)
    
    # If parsing failed (invalid modifiers), return False
    if not modifiers and '+' in key_combo:
        return False
    
    # Check if main key is pressed
    if not is_key_pressed(main_key):
        return False
    
    # Check if all required modifiers are pressed
    for modifier in modifiers:
        if not is_key_pressed(modifier):
            return False
    
    # Check that ONLY the required modifiers are pressed (not extra ones)
    all_modifiers = set(MODIFIER_KEYS.keys())
    required_modifiers = set(modifiers)
    
    for modifier in all_modifiers - required_modifiers:
        if is_key_pressed(modifier):
            return False  # Extra modifier is pressed
    
    return True

def is_key_combination_pressed_ignore_extra_mods(key_combo: str) -> bool:
    """
    Check if a key combination is currently pressed, ignoring any additional
    modifier keys that may also be held down.
    
    Args:
        key_combo: String like "lshift+a" or just "a"
    
    Returns:
        True if the base combination is pressed, False otherwise
    """
    if not key_combo:
        return False
    
    modifiers, main_key = parse_key_combination(key_combo)
    
    # If parsing failed (invalid modifiers), return False
    if not modifiers and '+' in key_combo:
        return False
    
    # Check if main key is pressed
    if not is_key_pressed(main_key):
        return False
    
    # Check if all required modifiers are pressed
    for modifier in modifiers:
        if not is_key_pressed(modifier):
            return False
    
    # The key difference: we DO NOT check for extra modifiers.
    # As long as the main key and its required modifiers are down, we return True.
    return True

def get_pressed_key():
    """Get the currently pressed key or mouse button."""
    # Check mouse buttons first (including new ones)
    mouse_buttons = ['middle mouse', 'mouse 4', 'mouse 5']
    for button_name in mouse_buttons:
        if is_key_pressed(button_name):
            return button_name
    
    # Check other special keys
    for key_name, vk_code in VK_KEYS.items():
        if key_name not in mouse_buttons and (win32api.GetAsyncKeyState(vk_code) & 0x8000 != 0):
            return key_name
            
    # Check A-Z
    for i in range(ord('A'), ord('Z') + 1):
        if win32api.GetAsyncKeyState(i) & 0x8000 != 0:
            return chr(i).lower() 
            
    # Check 0-9 (top row numbers, not numpad)
    for i in range(ord('0'), ord('9') + 1):
        if win32api.GetAsyncKeyState(i) & 0x8000 != 0:
            return chr(i)
            
    return None

def get_pressed_key_combination() -> str:
    """
    Get the currently pressed key combination including modifiers.
    
    Returns:
        String representation like "lshift+a" or just "a" if no modifiers
    """
    # Get currently pressed modifiers
    pressed_modifiers = []
    for modifier, vk_code in MODIFIER_KEYS.items():
        if win32api.GetAsyncKeyState(vk_code) & 0x8000 != 0:
            pressed_modifiers.append(modifier)
    
    # Get main key
    main_key = None
    
    # Check mouse buttons first
    mouse_buttons = ['middle mouse', 'mouse 4', 'mouse 5']
    for button_name in mouse_buttons:
        if is_key_pressed(button_name):
            main_key = button_name
            break
    
    if not main_key:
        # Check special keys (excluding modifiers)
        for key_name, vk_code in VK_KEYS.items():
            if key_name not in mouse_buttons and key_name not in MODIFIER_KEYS:
                if win32api.GetAsyncKeyState(vk_code) & 0x8000 != 0:
                    main_key = key_name
                    break
    
    if not main_key:
        # Check A-Z
        for i in range(ord('A'), ord('Z') + 1):
            if win32api.GetAsyncKeyState(i) & 0x8000 != 0:
                main_key = chr(i).lower()
                break
    
    if not main_key:
        # Check 0-9
        for i in range(ord('0'), ord('9') + 1):
            if win32api.GetAsyncKeyState(i) & 0x8000 != 0:
                main_key = chr(i)
                break
    
    if not main_key:
        return ""
    
    # Combine modifiers and main key
    if pressed_modifiers:
        # Sort modifiers for consistency
        pressed_modifiers.sort()
        return "+".join(pressed_modifiers + [main_key])
    else:
        return main_key

def is_numlock_on():
    """Check if Num Lock is currently on."""
    return win32api.GetKeyState(win32con.VK_NUMLOCK) & 1 != 0

def is_mouse_button(key: str) -> bool:
    """
    Check if a key string represents a mouse button.
    Args:
        key: The key string to check
    Returns:
        True if the key is a mouse button, False otherwise
    """
    mouse_button_keys = ['middle mouse', 'mouse 4', 'mouse 5']
    return key.lower() in mouse_button_keys

def is_modifier_key(key: str) -> bool:
    """
    Check if a key string represents a modifier key.
    Args:
        key: The key string to check
    Returns:
        True if the key is a modifier, False otherwise
    """
    return key.lower() in MODIFIER_KEYS

def get_supported_modifiers() -> List[str]:
    """Get list of supported modifier keys"""
    return list(MODIFIER_KEYS.keys())

def validate_key_combination(key_combo: str) -> bool:
    """
    Validate if a key combination string is valid.
    
    Args:
        key_combo: Key combination string to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not key_combo:
        return False
    
    modifiers, main_key = parse_key_combination(key_combo)
    
    # Check if modifiers are valid
    if '+' in key_combo and not modifiers:
        if '+' in main_key:
            return False

    # Check if main key is valid
    if not main_key:
        return False
    
    # Validate main key exists
    main_key_lower = main_key.lower()
    if main_key_lower in VK_KEYS:
        return True
    elif len(main_key_lower) == 1 and main_key_lower.isalnum():
        return True
    else:
        return False