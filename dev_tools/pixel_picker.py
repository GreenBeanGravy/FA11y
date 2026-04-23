"""
FA11y Pixel Picker

Standalone tool for reading pixel colors and screen coordinates the same way
FA11y sees them. Captures the screen via mss (matching FA11y's screenshot
manager) and shows a click-through magnifier overlay that follows the cursor.

Controls:
    F8  - toggle the magnifier overlay on/off
    C   - (while overlay is on) copy current pixel "RGB(r, g, b) @ (x, y)"
          to the clipboard and print it to the console
    ESC - quit

All dependencies (mss, pygame, pynput, cv2, numpy, pywin32, pyperclip) are
either FA11y requirements or already used elsewhere in the project.
"""
import atexit
import ctypes
import threading
import time

import cv2
import numpy as np
import pygame
import pyperclip
import win32con
import win32gui
from mss import mss
from pynput import keyboard, mouse

ctypes.windll.user32.SetProcessDPIAware()

mouse_ctrl = mouse.Controller()
overlay_enabled = False
debug_overlay = None
running = True

_capture_lock = threading.Lock()
_latest_frame = None
_capture_thread = None
_capture_running = False


def _capture_loop():
    """Continuously grab full-screen frames via a thread-local mss instance.

    Stored as BGR numpy arrays so the overlay code path matches the
    dxcam-cpp BGR convention used in the original titan_macro tool.
    """
    global _latest_frame
    sct = mss()
    try:
        monitor = sct.monitors[1]
        while _capture_running:
            try:
                raw = np.array(sct.grab(monitor))  # BGRA
                bgr = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
                with _capture_lock:
                    _latest_frame = bgr
            except Exception:
                time.sleep(0.01)
                continue
            time.sleep(1.0 / 60.0)
    finally:
        try:
            sct.close()
        except Exception:
            pass


def start_capture():
    global _capture_thread, _capture_running
    if _capture_running:
        return
    _capture_running = True
    _capture_thread = threading.Thread(target=_capture_loop, daemon=True)
    _capture_thread.start()


def stop_capture():
    global _capture_running
    _capture_running = False


def get_frame():
    with _capture_lock:
        return _latest_frame


def _cleanup():
    global debug_overlay
    if debug_overlay:
        debug_overlay.stop()
        debug_overlay = None
    stop_capture()


atexit.register(_cleanup)


class DebugOverlay:
    WIN_W, WIN_H = 220, 220
    CROP_SIZE = 100
    MAG_SIZE = 150
    OFFSET = 30
    MAGENTA = (255, 0, 255)
    GWL_EXSTYLE = -20
    LWA_COLORKEY = 0x00000001

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        self._thread.join(timeout=2)

    def _run(self):
        pygame.init()
        screen = pygame.display.set_mode(
            (self.WIN_W, self.WIN_H), pygame.NOFRAME
        )
        pygame.display.set_caption("FA11y Pixel Picker")
        hwnd = pygame.display.get_wm_info()["window"]
        self._make_click_through(hwnd)
        font = pygame.font.SysFont("consolas", 14)
        clock = pygame.time.Clock()

        while self.running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    self.running = False

            frame = get_frame()
            if frame is None:
                clock.tick(30)
                continue

            mx, my = mouse_ctrl.position
            h, w = frame.shape[:2]

            ox = mx + self.OFFSET
            oy = my + self.OFFSET
            if ox + self.WIN_W > w:
                ox = mx - self.OFFSET - self.WIN_W
            if oy + self.WIN_H > h:
                oy = my - self.OFFSET - self.WIN_H
            try:
                win32gui.SetWindowPos(
                    hwnd, win32con.HWND_TOPMOST, ox, oy, 0, 0,
                    win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
                )
            except Exception:
                pass

            screen.fill(self.MAGENTA)

            cx = max(self.CROP_SIZE // 2, min(mx, w - self.CROP_SIZE // 2))
            cy = max(self.CROP_SIZE // 2, min(my, h - self.CROP_SIZE // 2))
            x1 = cx - self.CROP_SIZE // 2
            y1 = cy - self.CROP_SIZE // 2
            crop = frame[y1:y1 + self.CROP_SIZE, x1:x1 + self.CROP_SIZE]
            mag = cv2.resize(
                crop, (self.MAG_SIZE, self.MAG_SIZE),
                interpolation=cv2.INTER_NEAREST,
            )
            mag_rgb = mag[:, :, ::-1]
            surf = pygame.surfarray.make_surface(
                np.ascontiguousarray(mag_rgb.transpose(1, 0, 2))
            )
            mag_x = (self.WIN_W - self.MAG_SIZE) // 2
            screen.blit(surf, (mag_x, 5))

            center_x = mag_x + self.MAG_SIZE // 2
            center_y = 5 + self.MAG_SIZE // 2
            pygame.draw.line(
                screen, (0, 255, 0),
                (center_x - 6, center_y), (center_x + 6, center_y), 1,
            )
            pygame.draw.line(
                screen, (0, 255, 0),
                (center_x, center_y - 6), (center_x, center_y + 6), 1,
            )

            px = max(0, min(mx, w - 1))
            py_ = max(0, min(my, h - 1))
            b, g, r = (
                int(frame[py_, px, 0]),
                int(frame[py_, px, 1]),
                int(frame[py_, px, 2]),
            )

            swatch_y = self.MAG_SIZE + 12
            pygame.draw.rect(screen, (r, g, b), (mag_x, swatch_y, 20, 20))
            pygame.draw.rect(
                screen, (200, 200, 200),
                (mag_x, swatch_y, 20, 20), 1,
            )

            txt = f"RGB({r},{g},{b}) @({mx},{my})"
            txt_surf = font.render(txt, True, (0, 255, 0), (0, 0, 0))
            screen.blit(txt_surf, (mag_x + 25, swatch_y + 2))

            pygame.display.flip()
            clock.tick(30)

        pygame.quit()

    def _make_click_through(self, hwnd):
        style = win32gui.GetWindowLong(hwnd, self.GWL_EXSTYLE)
        style |= (
            win32con.WS_EX_LAYERED
            | win32con.WS_EX_TRANSPARENT
            | win32con.WS_EX_TOPMOST
        )
        win32gui.SetWindowLong(hwnd, self.GWL_EXSTYLE, style)
        win32gui.SetLayeredWindowAttributes(
            hwnd, 0x00FF00FF, 0, self.LWA_COLORKEY
        )


def on_press(key):
    global overlay_enabled, debug_overlay, running

    if key == keyboard.Key.f8:
        overlay_enabled = not overlay_enabled
        if overlay_enabled:
            debug_overlay = DebugOverlay()
            debug_overlay.start()
        else:
            if debug_overlay:
                debug_overlay.stop()
                debug_overlay = None
        print(f"Overlay {'ON' if overlay_enabled else 'OFF'}")
        return

    if overlay_enabled and hasattr(key, 'char') and key.char == 'c':
        frame = get_frame()
        if frame is None:
            print("No frame captured yet")
            return
        mx, my = mouse_ctrl.position
        h, w = frame.shape[:2]
        px = max(0, min(mx, w - 1))
        py_ = max(0, min(my, h - 1))
        b, g, r = (
            int(frame[py_, px, 0]),
            int(frame[py_, px, 1]),
            int(frame[py_, px, 2]),
        )
        text = f"RGB({r}, {g}, {b}) @ ({mx}, {my})"
        pyperclip.copy(text)
        print(text)
        return

    if key == keyboard.Key.esc:
        running = False
        return False


def main():
    start_capture()
    print("FA11y Pixel Picker ready (using mss, same as FA11y).")
    print("  F8  - toggle magnified overlay")
    print("  C   - (overlay on) copy current pixel RGB + coordinates")
    print("  ESC - quit")
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    try:
        while running:
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    listener.stop()


if __name__ == "__main__":
    main()
