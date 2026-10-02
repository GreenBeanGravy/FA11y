"""Small building blocks shared by hub pages.

Everything here is made of native wx controls (StaticText, Button, Gauge),
so screen readers see ordinary labels and buttons. Painting is limited to
backgrounds, borders and the look of buttons.
"""
from __future__ import annotations

from typing import Optional

import wx

from lib.hub import theme
from lib.hub.controls import StyledButton

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


def heading(parent: wx.Window, text: str) -> wx.StaticText:
    return label(parent, text, font=theme.heading_font(parent))


def subheading(parent: wx.Window, text: str) -> wx.StaticText:
    return label(parent, text, font=theme.heading_font(parent, 1))


def button(parent: wx.Window, text: str, icon_name: str = "", variant: str = "secondary") -> StyledButton:
    return StyledButton(parent, label=text, icon=icon_name, variant=variant)


class StatusCard(Card):
    """Home page card: muted title, value, coloured detail line.

    The card's text is also set as its accessible name, so tabbing or
    reviewing reads "Fortnite, 34.2, Ready" as one line.
    """

    def __init__(self, parent: wx.Window, title: str):
        super().__init__(parent, name=title)
        self._title = label(self, title, theme.TEXT_SECONDARY, theme.small_font(self))
        self._value = label(self, "…", font=theme.heading_font(self, 2))
        self._detail = label(self, "", theme.TEXT_MUTED, theme.small_font(self))
        self.body.Add(self._title)
        self.body.Add(self._value, 0, wx.TOP, 2)
        self.body.Add(self._detail, 0, wx.TOP, 2)

    def set(self, value: str, detail: str = "", colour: wx.Colour = theme.TEXT_MUTED) -> None:
        self._value.SetLabel(value)
        self._detail.SetLabel(detail)
        self._detail.SetForegroundColour(colour)
        self.SetName(", ".join(p for p in (self._title.GetLabel(), value, detail) if p))
        self.Layout()
