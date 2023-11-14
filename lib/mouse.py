import ctypes

# Constants
VK_NUMPAD2, VK_NUMPAD8, VK_NUMPAD0, VK_NUMPAD4, VK_NUMPAD6 = 0x62, 0x68, 0x60, 0x64, 0x66
INPUT_MOUSE, MOUSEEVENTF_MOVE = 0, 0x0001
MOUSE_SENSITIVITY = 40
TURN_AROUND_MOVE = 1158  # Large move to the right for turning around

# Structures for input simulation
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("ii", MOUSEINPUT)]

def move_mouse(dx, dy):
    x = INPUT(type=INPUT_MOUSE, ii=MOUSEINPUT(dx=dx, dy=dy, mouseData=0, dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=None))
    ctypes.windll.user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))

def mouse_movement():
    numpad2_key_down, numpad8_key_down, numpad0_key_down, numpad4_key_down, numpad6_key_down = False, False, False, False, False
    
    while True:
        # Check if the Numpad 2 key is down
        numpad2_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_NUMPAD2))
        if numpad2_key_current_state and not numpad2_key_down:
            move_mouse(0, MOUSE_SENSITIVITY)
        numpad2_key_down = numpad2_key_current_state

        # Check if the Numpad 8 key is down
        numpad8_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_NUMPAD8))
        if numpad8_key_current_state and not numpad8_key_down:
            move_mouse(0, -MOUSE_SENSITIVITY)
        numpad8_key_down = numpad8_key_current_state

        # Check if the Numpad 0 key is down
        numpad0_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_NUMPAD0))
        if numpad0_key_current_state and not numpad0_key_down:
            move_mouse(TURN_AROUND_MOVE, 0)
        numpad0_key_down = numpad0_key_current_state

        # Check if the Numpad 4 key is down
        numpad4_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_NUMPAD4))
        if numpad4_key_current_state and not numpad4_key_down:
            move_mouse(-MOUSE_SENSITIVITY, 0)
        numpad4_key_down = numpad4_key_current_state

        # Check if the Numpad 6 key is down
        numpad6_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_NUMPAD6))
        if numpad6_key_current_state and not numpad6_key_down:
            move_mouse(MOUSE_SENSITIVITY, 0)
        numpad6_key_down = numpad6_key_current_state
