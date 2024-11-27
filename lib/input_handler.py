import win32api
import win32con

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
    'middle mouse': 0x04,
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
    'printscreen': win32con.VK_PRINT,
    'scrolllock': win32con.VK_SCROLL,
    'pause': win32con.VK_PAUSE,
    'numlock': win32con.VK_NUMLOCK,
    'bracketleft': 0xDB,
    'bracketright': 0xDD,
    'apostrophe': 0xDE,
    'grave': 0xC0,
    'backslash': 0xDC,
    'semicolon': 0xBA,
    'period': 0xBE,
}

def is_key_pressed(key):
    key_lower = key.lower()
    if key_lower in VK_KEYS:
        vk_code = VK_KEYS[key_lower]
    else:
        try:
            vk_code = ord(key.upper())
        except (TypeError, ValueError):
            print(f"Unrecognized key: {key}. Skipping...")
            return False
    return win32api.GetAsyncKeyState(vk_code) & 0x8000 != 0

def get_pressed_key():
    # Check middle mouse first
    if is_key_pressed('middle mouse'):
        return 'middle mouse'
    
    # Then check all other keys
    for key in list(VK_KEYS.keys()) + [chr(i) for i in range(65, 91)]:
        if key != 'middle mouse' and is_key_pressed(key):
            return key
    return None

def is_numlock_on():
    return win32api.GetKeyState(win32con.VK_NUMLOCK) & 1 != 0
