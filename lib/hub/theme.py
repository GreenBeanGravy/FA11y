"""Colors, fonts and icons for the FA11y hub.

The hub is always dark. wxWidgets 3.3 draws native controls (text fields,
checkboxes, lists, scrollbars) in Windows' dark style once the app opts
in; FA11y draws its own sidebar, buttons, tabs and cards with the colors
here (see lib/hub/controls.py).
"""
from __future__ import annotations

import os
from functools import lru_cache

import wx

# Surfaces, darkest to lightest.
SIDEBAR_BG = wx.Colour(0x17, 0x17, 0x17)
WINDOW_BG = wx.Colour(0x1E, 0x1E, 0x1E)
HOVER_BG = wx.Colour(0x26, 0x26, 0x26)
CARD_BG = wx.Colour(0x25, 0x25, 0x25)
PRESSED_BG = wx.Colour(0x30, 0x30, 0x2E)
CARD_BORDER = wx.Colour(0x2C, 0x2C, 0x2A)
CONTROL_BORDER = wx.Colour(0x5F, 0x5E, 0x5A)

TEXT = wx.Colour(0xE8, 0xE6, 0xDF)
TEXT_SECONDARY = wx.Colour(0xB4, 0xB2, 0xA9)
TEXT_MUTED = wx.Colour(0x88, 0x87, 0x80)
TEXT_DISABLED = wx.Colour(0x5F, 0x5E, 0x5A)

ACCENT = wx.Colour(0x37, 0x8A, 0xDD)
ACCENT_HOVER = wx.Colour(0x52, 0x9C, 0xE4)
ACCENT_PRESSED = wx.Colour(0x18, 0x5F, 0xA5)
SELECTED_BG = wx.Colour(0x0C, 0x44, 0x7C)
SELECTED_TEXT = wx.Colour(0xE6, 0xF1, 0xFB)
FOCUS_RING = wx.Colour(0x85, 0xB7, 0xEB)
SUCCESS = wx.Colour(0x97, 0xC4, 0x59)
WARNING = wx.Colour(0xEF, 0x9F, 0x27)
DANGER = wx.Colour(0xF0, 0x95, 0x95)
DANGER_BORDER = wx.Colour(0x79, 0x1F, 0x1F)

RADIUS = 8
ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "icons")
FONT_FACE = "Segoe UI"
BASE_POINTS = 10


def enable_dark_mode(app: wx.App) -> None:
    """Switch native controls to Windows' dark style. Call before any window exists."""
    try:
        app.MSWEnableDarkMode(wx.App.DarkMode_Always)
    except Exception:
        pass


def base_font() -> wx.Font:
    return wx.Font(wx.FontInfo(BASE_POINTS).FaceName(FONT_FACE))


def style_window(window: wx.Window) -> None:
    """Give a hub-owned window the dark background and light text."""
    window.SetBackgroundColour(WINDOW_BG)
    window.SetForegroundColour(TEXT)


def style_tree(window: wx.Window, background: wx.Colour = WINDOW_BG) -> None:
    """Give window and every panel inside it the hub background.

    Native dark mode paints plain panels a slightly different grey, which
    shows as boxes inside FA11y's pages and popups. Windows that draw their
    own background (cards) set keep_background = True and are skipped.
    """
    pending = [window]
    while pending:
        current = pending.pop()
        if getattr(current, "keep_background", False):
            continue
        if isinstance(current, (wx.Panel, wx.ScrolledWindow, wx.BookCtrlBase, wx.Dialog, wx.Frame)):
            if current.GetBackgroundColour() != background:
                current.SetBackgroundColour(background)
                current.SetForegroundColour(TEXT)
                current.Refresh()
        pending.extend(current.GetChildren())


def heading_font(window: wx.Window, extra_points: int = 5) -> wx.Font:
    font = window.GetFont()
    font.SetPointSize(font.GetPointSize() + extra_points)
    font.SetWeight(wx.FONTWEIGHT_SEMIBOLD)
    return font


def small_font(window: wx.Window) -> wx.Font:
    font = window.GetFont()
    font.SetPointSize(max(font.GetPointSize() - 1, 7))
    return font


def blend(a: wx.Colour, b: wx.Colour, amount: float) -> wx.Colour:
    """Mix colour b into a; amount 0 gives a, 1 gives b."""
    return wx.Colour(*(int(x + (y - x) * amount) for x, y in
                       zip((a.Red(), a.Green(), a.Blue()), (b.Red(), b.Green(), b.Blue()))))


@lru_cache(maxsize=None)
def _svg_source(name: str) -> bytes:
    with open(os.path.join(ICON_DIR, f"{name}.svg"), "rb") as f:
        return f.read()


def icon(name: str, size: int = 18, colour: wx.Colour = TEXT_SECONDARY) -> wx.BitmapBundle:
    """Load a Tabler outline icon from assets/icons, tinted to colour."""
    try:
        svg = _svg_source(name).replace(b"currentColor", colour.GetAsString(wx.C2S_HTML_SYNTAX).encode())
        return wx.BitmapBundle.FromSVG(svg, wx.Size(size, size))
    except Exception:
        return wx.BitmapBundle()


_bitmaps: dict = {}


def icon_bitmap(name: str, size: int, colour: wx.Colour, window: wx.Window) -> wx.Bitmap:
    """Icon rendered for window's DPI, cached so repaints never re-parse SVG."""
    scale = window.GetDPIScaleFactor() if window else 1.0
    key = (name, size, colour.GetRGB(), scale)
    bitmap = _bitmaps.get(key)
    if bitmap is None:
        bundle = icon(name, size, colour)
        bitmap = bundle.GetBitmap(wx.Size(round(size * scale), round(size * scale))) if bundle.IsOk() else wx.NullBitmap
        _bitmaps[key] = bitmap
    return bitmap
