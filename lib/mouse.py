import ctypes
import time
import threading

# Constants
VK_NUMLOCK = 0x90
VK_LCONTROL, VK_RCONTROL = 0xA2, 0xA3
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
VK_NUMPAD1, VK_NUMPAD3, VK_NUMPAD5, VK_NUMPAD7, VK_NUMPAD9 = 0x61, 0x63, 0x65, 0x67, 0x69
VK_NUMPAD2, VK_NUMPAD8, VK_NUMPAD0, VK_NUMPAD4, VK_NUMPAD6 = 0x62, 0x68, 0x60, 0x64, 0x66
INPUT_MOUSE, MOUSEEVENTF_MOVE, MOUSEEVENTF_WHEEL = 0, 0x0001, 0x0800
MOUSE_SENSITIVITY = 30
TURN_AROUND_MOVE = 1158
SMOOTH_MOVE_DURATION = 0.01  # Reduced duration for faster movement

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

def smooth_move_mouse(dx, dy, duration):
    def move():
        steps = 5
        step_dx = dx // steps
        step_dy = dy // steps
        step_duration = duration / steps

        for _ in range(steps):
            x = INPUT(type=INPUT_MOUSE, ii=MOUSEINPUT(dx=step_dx, dy=step_dy, mouseData=0, dwFlags=MOUSEEVENTF_MOVE, time=0, dwExtraInfo=None))
            ctypes.windll.user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))
            time.sleep(step_duration)

    threading.Thread(target=move).start()

def mouse_scroll(amount):
    x = INPUT(type=INPUT_MOUSE, ii=MOUSEINPUT(dx=0, dy=0, mouseData=amount, dwFlags=MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=None))
    ctypes.windll.user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))

def left_mouse_down():
    down = INPUT(type=INPUT_MOUSE, ii=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTDOWN, time=0, dwExtraInfo=None))
    ctypes.windll.user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(down))

def left_mouse_up():
    up = INPUT(type=INPUT_MOUSE, ii=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTUP, time=0, dwExtraInfo=None))
    ctypes.windll.user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(up))

def right_mouse_down():
    down = INPUT(type=INPUT_MOUSE, ii=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_RIGHTDOWN, time=0, dwExtraInfo=None))
    ctypes.windll.user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(down))

def right_mouse_up():
    up = INPUT(type=INPUT_MOUSE, ii=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_RIGHTUP, time=0, dwExtraInfo=None))
    ctypes.windll.user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(up))

def is_numlock_on():
    return ctypes.windll.user32.GetKeyState(VK_NUMLOCK) & 1

def mouse_movement():
    numpad_keys_down = {key: False for key in [VK_NUMPAD1, VK_NUMPAD3, VK_NUMPAD5, VK_NUMPAD7, VK_NUMPAD9, VK_NUMPAD2, VK_NUMPAD8, VK_NUMPAD0, VK_NUMPAD4, VK_NUMPAD6]}
    control_keys_down = {key: False for key in [VK_LCONTROL, VK_RCONTROL]}

    while True:
        numlock_on = is_numlock_on()

        for key in numpad_keys_down:
            key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(key))
            if key_current_state and not numpad_keys_down[key]:
                if key == VK_NUMPAD1:
                    smooth_move_mouse(-2 * MOUSE_SENSITIVITY, 0, SMOOTH_MOVE_DURATION)
                elif key == VK_NUMPAD3:
                    smooth_move_mouse(2 * MOUSE_SENSITIVITY, 0, SMOOTH_MOVE_DURATION)
                elif key == VK_NUMPAD7:
                    mouse_scroll(120)  # Scroll up
                elif key == VK_NUMPAD9:
                    mouse_scroll(-120)  # Scroll down
                elif key == VK_NUMPAD5:
                    smooth_move_mouse(0, 2000, SMOOTH_MOVE_DURATION)
                    time.sleep(0.1)
                    smooth_move_mouse(0, -580, SMOOTH_MOVE_DURATION)  # Move 580 up
                elif key == VK_NUMPAD2:
                    smooth_move_mouse(0, MOUSE_SENSITIVITY, SMOOTH_MOVE_DURATION)
                elif key == VK_NUMPAD8:
                    smooth_move_mouse(0, -MOUSE_SENSITIVITY, SMOOTH_MOVE_DURATION)
                elif key == VK_NUMPAD0:
                    smooth_move_mouse(TURN_AROUND_MOVE, 0, SMOOTH_MOVE_DURATION)
                elif key == VK_NUMPAD4:
                    smooth_move_mouse(-MOUSE_SENSITIVITY, 0, SMOOTH_MOVE_DURATION)
                elif key == VK_NUMPAD6:
                    smooth_move_mouse(MOUSE_SENSITIVITY, 0, SMOOTH_MOVE_DURATION)
            numpad_keys_down[key] = key_current_state

        if numlock_on:
            for key in control_keys_down:
                key_current_state = bool(ctypes.windll.user32.GetAsyncKeyState(key))
                if key_current_state != control_keys_down[key]:  # Key state changed
                    if key == VK_LCONTROL:
                        if key_current_state:
                            left_mouse_down()
                        else:
                            left_mouse_up()
                    elif key == VK_RCONTROL:
                        if key_current_state:
                            right_mouse_down()
                        else:
                            right_mouse_up()
                control_keys_down[key] = key_current_state
