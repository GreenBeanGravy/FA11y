import ctypes

# Constants
VK_NUMPAD2 = 0x62  # Num2 key
VK_NUMPAD8 = 0x68  # Num8 key
VK_NUMPAD0 = 0x60  # Num0 key
VK_NUMPAD4 = 0x64  # Num4 key
VK_NUMPAD6 = 0x66  # Num6 key
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001

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

def move_mouse_left():
    # Move mouse to the left
    move_mouse(-MOUSE_SENSITIVITY, 0)

def move_mouse_right():
    # Move mouse to the right
    move_mouse(MOUSE_SENSITIVITY, 0)

def move_mouse_up():
    # Move mouse up
    move_mouse(0, -MOUSE_SENSITIVITY)

def move_mouse_down():
    # Move mouse down
    move_mouse(0, MOUSE_SENSITIVITY)

def turn_around():
    # Move mouse a large amount to the right for turning around
    move_mouse(TURN_AROUND_MOVE, 0)

def mouse_movement():
    global numpad2_key_down, numpad8_key_down, numpad0_key_down, numpad4_key_down, numpad6_key_down
    numpad2_key_down = False
    numpad8_key_down = False
    numpad0_key_down = False
    numpad4_key_down = False
    numpad6_key_down = False
    
    while True:
        # Check if the Numpad 2 key is down
        numpad2_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_NUMPAD2))
        if numpad2_key_current_state and not numpad2_key_down:
            move_mouse_down()
        numpad2_key_down = numpad2_key_current_state

        # Check if the Numpad 8 key is down
        numpad8_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_NUMPAD8))
        if numpad8_key_current_state and not numpad8_key_down:
            move_mouse_up()
        numpad8_key_down = numpad8_key_current_state

        # Check if the Numpad 0 key is down
        numpad0_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_NUMPAD0))
        if numpad0_key_current_state and not numpad0_key_down:
            turn_around()
        numpad0_key_down = numpad0_key_current_state

        # Check if the Numpad 4 key is down
        numpad4_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_NUMPAD4))
        if numpad4_key_current_state and not numpad4_key_down:
            move_mouse_left()
        numpad4_key_down = numpad4_key_current_state

        # Check if the Numpad 6 key is down
        numpad6_key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(VK_NUMPAD6))
        if numpad6_key_current_state and not numpad6_key_down:
            move_mouse_right()
        numpad6_key_down = numpad6_key_current_state
