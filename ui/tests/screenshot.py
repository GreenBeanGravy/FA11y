"""Save a window as a PNG with PrintWindow, for comparing the new window with the wx one.

    python ui/tests/screenshot.py OUT.png --pid 1234
    python ui/tests/screenshot.py OUT.png --title "FA11y - Home"

Works on windows that are behind others. Needs nothing but Python and ctypes.
"""
from __future__ import annotations

import argparse
import ctypes
import struct
import sys
import zlib
from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
PW_RENDERFULLCONTENT = 2


def find_window(pid: int | None, title: str | None) -> int:
    found: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        owner_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if pid is not None and owner_pid.value != pid:
            return True
        if title is not None and not buffer.value.startswith(title):
            return True
        if length == 0:
            return True
        found.append(hwnd)
        return True

    user32.EnumWindows(callback_type(callback), 0)
    if not found:
        raise SystemExit("No matching window.")
    return found[0]


def capture(hwnd: int, from_screen: bool = False) -> tuple[int, int, bytes]:
    """Grab the window. from_screen copies what is on screen (the window must be in front);
    otherwise PrintWindow asks the window to paint itself, which also works behind others."""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    hdc = user32.GetDC(0) if from_screen else user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
    gdi32.SelectObject(mem, bitmap)
    if from_screen:
        gdi32.BitBlt(mem, 0, 0, width, height, hdc, rect.left, rect.top, 0x00CC0020 | 0x40000000)
    else:
        user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    info = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
    pixels = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem, bitmap, 0, height, pixels, ctypes.byref(info), 0)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(0 if from_screen else hwnd, hdc)
    return width, height, pixels.raw


def write_png(path: str, width: int, height: int, bgra: bytes) -> None:
    rows = []
    stride = width * 4
    for y in range(height):
        row = bgra[y * stride:(y + 1) * stride]
        rgb = bytearray(width * 3)
        rgb[0::3] = row[2::4]
        rgb[1::3] = row[1::4]
        rgb[2::3] = row[0::4]
        rows.append(b"\x00" + bytes(rgb))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--pid", type=int)
    parser.add_argument("--title")
    parser.add_argument("--screen", action="store_true", help="copy from the screen instead of PrintWindow")
    args = parser.parse_args()
    ctypes.windll.user32.SetProcessDPIAware()
    hwnd = find_window(args.pid, args.title)
    width, height, data = capture(hwnd, args.screen)
    write_png(args.out, width, height, data)
    print(f"Saved {width}x{height} to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
