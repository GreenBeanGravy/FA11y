"""Small building blocks shared by hub pages.

Headings and field labels are native StaticText. Status and explanations
use ReadableText, which looks like a label but is a tab stop, so screen
reader users reach it with Tab like everything else on the page.
"""
from __future__ import annotations

from typing import Optional

import wx

from lib.hub import theme
from lib.hub.controls import ReadableText, StyledButton, TextLine

PAGE_MARGIN = 20
GAP = 10


class Card(wx.Panel):
    """Rounded, bordered panel. Add children to card.body (a vertical BoxSizer)."""

    RADIUS = 8
    keep_background = True

    def __init__(self, parent: wx.Window, name: str = ""):
        super().__init__(parent, name=name or "card")
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(theme.CARD_BG)
        self.SetForegroundColour(theme.TEXT)
        self.body = wx.BoxSizer(wx.VERTICAL)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self.body, 1, wx.EXPAND | wx.ALL, 12)
        self.SetSizer(outer)
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.GetParent().GetBackgroundColour()))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        if gc:
            w, h = self.GetClientSize()
            gc.SetPen(wx.Pen(theme.CARD_BORDER, 1))
            gc.SetBrush(wx.Brush(theme.CARD_BG))
            gc.DrawRoundedRectangle(0.5, 0.5, w - 1, h - 1, self.RADIUS)


def label(parent: wx.Window, text: str, colour: wx.Colour = theme.TEXT,
          font: Optional[wx.Font] = None, wrap: int = 0) -> wx.StaticText:
    ctrl = wx.StaticText(parent, label=text)
    ctrl.SetForegroundColour(colour)
    if font is not None:
        ctrl.SetFont(font)
    if wrap:
        ctrl.Wrap(wrap)
    return ctrl


def text(parent: wx.Window, value: str = "", colour: wx.Colour = theme.TEXT,
         font: Optional[wx.Font] = None, wrap: int = 0) -> ReadableText:
    """Text the user can Tab to and have read, for status and explanations."""
    return ReadableText(parent, value, colour, font, wrap)


def heading(parent: wx.Window, text: str) -> wx.StaticText:
    return label(parent, text, font=theme.heading_font(parent))


def subheading(parent: wx.Window, text: str) -> wx.StaticText:
    return label(parent, text, font=theme.heading_font(parent, 1))


def button(parent: wx.Window, text: str, icon_name: str = "", variant: str = "secondary") -> StyledButton:
    return StyledButton(parent, label=text, icon=icon_name, variant=variant)


class StatusCard(ReadableText):
    """Home page card: muted title, value, coloured detail line.

    The whole card is one tab stop, read as "Fortnite, 34.2, Ready".
    """

    PADDING = 12
    separator = ", "

    def __init__(self, parent: wx.Window, title: str):
        super().__init__(parent, name=title)
        self._title = title
        self.set("…")

    def set(self, value: str, detail: str = "", colour: wx.Colour = theme.TEXT_MUTED) -> None:
        self.set_lines([
            TextLine(self._title, theme.small_font(self), theme.TEXT_SECONDARY),
            TextLine(value, theme.heading_font(self, 2), theme.TEXT, gap=2),
            TextLine(detail, theme.small_font(self), colour, gap=2),
        ])

    def _paint_background(self, gc: wx.GraphicsContext, w: int, h: int) -> None:
        focused = self.HasFocus()
        width = self.FromDIP(2) if focused else 1
        gc.SetPen(wx.Pen(theme.FOCUS_RING if focused else theme.CARD_BORDER, width))
        gc.SetBrush(wx.Brush(theme.CARD_BG))
        inset = width / 2
        gc.DrawRoundedRectangle(inset, inset, w - width, h - width, Card.RADIUS)
