"""Colors, fonts and icons for the FA11y hub.

The hub is always dark. wxWidgets 3.3 draws native controls (buttons, lists,
text fields, scrollbars) in Windows' dark style once the app opts in; the
colors here are for the parts FA11y paints itself, such as the sidebar and
status cards.
"""
from __future__ import annotations

import os
from functools import lru_cache

import wx

# Surfaces, darkest to lightest.
WINDOW_BG = wx.Colour(0x1E, 0x1E, 0x1E)
SIDEBAR_BG = wx.Colour(0x17, 0x17, 0x17)
CARD_BG = wx.Colour(0x25, 0x25, 0x25)
CARD_BORDER = wx.Colour(0x2C, 0x2C, 0x2A)
CONTROL_BORDER = wx.Colour(0x5F, 0x5E, 0x5A)

TEXT = wx.Colour(0xE8, 0xE6, 0xDF)
TEXT_SECONDARY = wx.Colour(0xB4, 0xB2, 0xA9)
TEXT_MUTED = wx.Colour(0x88, 0x87, 0x80)

ACCENT = wx.Colour(0x37, 0x8A, 0xDD)
SELECTED_BG = wx.Colour(0x0C, 0x44, 0x7C)
SELECTED_TEXT = wx.Colour(0xE6, 0xF1, 0xFB)
SUCCESS = wx.Colour(0x97, 0xC4, 0x59)
WARNING = wx.Colour(0xEF, 0x9F, 0x27)
DANGER = wx.Colour(0xF0, 0x95, 0x95)

ICON_DIR = os.path.join("assets", "icons")


def enable_dark_mode(app: wx.App) -> None:
    """Switch native controls to Windows' dark style. Call before any window exists."""
    try:
        app.MSWEnableDarkMode(wx.App.DarkMode_Always)
    except Exception:
        pass


def style_window(window: wx.Window) -> None:
    """Give a hub-owned window the dark background and light text."""
    window.SetBackgroundColour(WINDOW_BG)
    window.SetForegroundColour(TEXT)


def heading_font(window: wx.Window, extra_points: int = 5) -> wx.Font:
    font = window.GetFont()
    font.SetPointSize(font.GetPointSize() + extra_points)
    return font.Bold()


def small_font(window: wx.Window) -> wx.Font:
    font = window.GetFont()
    font.SetPointSize(max(font.GetPointSize() - 1, 7))
    return font


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
