import win32api
import win32con

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

# Virtual Key Codes for NUMPAD, Special Keys, and Mouse Buttons
VK_KEYS = {
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
    'num period': win32con.VK_DECIMAL,
    'num .': win32con.VK_DECIMAL,
    'num +': win32con.VK_ADD,
    'num -': win32con.VK_SUBTRACT,
    'num *': win32con.VK_MULTIPLY,
    'num /': win32con.VK_DIVIDE,
    'lctrl': win32con.VK_LCONTROL,
    'rctrl': win32con.VK_RCONTROL,
    'lshift': win32con.VK_LSHIFT,
    'rshift': win32con.VK_RSHIFT,
    'lalt': win32con.VK_LMENU,
    'ralt': win32con.VK_RMENU,
    'middle mouse': getattr(win32con, 'VK_MBUTTON', 0x04),  # VK_MBUTTON
    'mouse 4': VK_XBUTTON1,  # Mouse button 4 (back button)
    'mouse 5': VK_XBUTTON2,  # Mouse button 5 (forward button)
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
    'tab': win32con.VK_TAB,
    'capslock': win32con.VK_CAPITAL,
    'space': win32con.VK_SPACE,
    'backspace': win32con.VK_BACK,
    'enter': win32con.VK_RETURN,
    'esc': win32con.VK_ESCAPE,
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
    'printscreen': win32con.VK_SNAPSHOT,  # VK_SNAPSHOT
    'scrolllock': win32con.VK_SCROLL,
    'pause': win32con.VK_PAUSE,
    'numlock': win32con.VK_NUMLOCK,
    'bracketleft': VK_OEM_4,  # For '['
    'bracketright': VK_OEM_6,  # For ']'
    'apostrophe': VK_OEM_7,  # For "'"
    'grave': VK_OEM_3,  # For '`'
    'backslash': VK_OEM_5,  # For '\'
    'semicolon': VK_OEM_1,  # For ';'
    'period': VK_OEM_PERIOD,  # For '.'
    'comma': VK_OEM_COMMA,  # For ','
    'minus': VK_OEM_MINUS,  # For '-' (main keyboard)
    'equals': VK_OEM_PLUS,  # For '=' (main keyboard, often requires shift for '+')
    'slash': VK_OEM_2  # For '/' (main keyboard)
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

    # Special handling for X buttons (mouse 4 and 5)
    if vk_code in [VK_XBUTTON1, VK_XBUTTON2]:
        return win32api.GetAsyncKeyState(vk_code) & 0x8000 != 0

    return win32api.GetAsyncKeyState(vk_code) & 0x8000 != 0


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