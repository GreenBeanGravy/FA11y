"""FA11y's own drawn controls: buttons, the sidebar list, and tabs.

Buttons are native Windows buttons that FA11y repaints, so everything
but their look stays native. The sidebar and tabs are drawn from scratch
and report themselves to screen readers through MSAA (wx.Accessible)
exactly like the native controls they replace: the sidebar is a list of
list items, tabs are page tabs. Their keys also match (arrows, Home, End
and type-ahead move; Ctrl+Tab switches tabs).
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Callable, List, Optional

import wx

from lib.hub import theme

ACC_OK = wx.ACC_OK
STATE_FOCUSABLE = wx.ACC_STATE_SYSTEM_FOCUSABLE
STATE_FOCUSED = wx.ACC_STATE_SYSTEM_FOCUSED
STATE_SELECTABLE = wx.ACC_STATE_SYSTEM_SELECTABLE
STATE_SELECTED = wx.ACC_STATE_SYSTEM_SELECTED


def strip_mnemonic(label: str) -> str:
    return label.replace("&&", "\0").replace("&", "").replace("\0", "&")



def _gc(dc: wx.DC) -> wx.GraphicsContext:
    gc = wx.GraphicsContext.Create(dc)
    gc.SetAntialiasMode(wx.ANTIALIAS_DEFAULT)
    return gc


def _clear(dc: wx.DC, window: wx.Window) -> None:
    dc.SetBackground(wx.Brush(window.GetParent().GetBackgroundColour()))
    dc.Clear()


# ---------------------------------------------------------------------------
# Button
# ---------------------------------------------------------------------------

BM_GETSTATE = 0x00F2
BST_PUSHED = 0x0004
BST_HOT = 0x0200
_send_message = ctypes.windll.user32.SendMessageW
_send_message.restype = ctypes.c_ssize_t
_send_message.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]


class StyledButton(wx.Button):
    """A native Windows button, repainted in the hub's style.

    Only painting changes: focus, Space/Enter, Alt shortcuts, default and
    cancel buttons, and what screen readers report all stay native. Takes
    wx.Button's arguments plus variant ("primary", "secondary", "danger",
    "ghost") and icon (a name from assets/icons).
    """

    def __init__(self, *args, variant: str = "secondary", icon: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self.variant = variant
        # Text to draw instead of the label, which screen readers still read
        # (keybind buttons draw "Left Ctrl" but are named "Fire: Left Ctrl").
        self.display_text = ""
        self._hover = False
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_hover)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_hover)
        for event in (wx.EVT_SET_FOCUS, wx.EVT_KILL_FOCUS, wx.EVT_LEFT_DOWN, wx.EVT_LEFT_UP,
                      wx.EVT_KEY_DOWN, wx.EVT_KEY_UP):
            self.Bind(event, self._refresh_and_skip)
        self._fixed_size = kwargs.get("size", wx.DefaultSize)
        if len(args) > 4:
            self._fixed_size = args[4]
        self._icon = icon
        self._fit()

    def SetIcon(self, name: str) -> None:
        """Show an icon before the label."""
        self._icon = name
        self._fit()
        self.Refresh()

    def SetLabel(self, label: str) -> None:
        super().SetLabel(label)
        self._fit()
        self.Refresh()

    def _fit(self) -> None:
        """Size for the label and icon with comfortable padding, unless a size was given."""
        fixed = wx.Size(self._fixed_size)
        if fixed.width > 0 and fixed.height > 0:
            return
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        tw, th = dc.GetTextExtent(self.GetLabelText() or "M")
        if self._icon:
            tw += self.FromDIP(16 + (7 if self.GetLabelText() else 0))
        size = wx.Size(max(tw + self.FromDIP(32), self.FromDIP(72)), max(th + self.FromDIP(16), self.FromDIP(32)))
        if fixed.width > 0:
            size.width = fixed.width
        if fixed.height > 0:
            size.height = fixed.height
        self.SetMinSize(size)
        self.SetSize(size)
        if self.GetContainingSizer() is not None:
            self.GetParent().Layout()

    def _refresh_and_skip(self, event: wx.Event) -> None:
        self.Refresh()
        event.Skip()

    def _on_hover(self, event: wx.MouseEvent) -> None:
        self._hover = event.Entering()
        self.Refresh()
        event.Skip()

    def _colours(self):
        state = _send_message(self.GetHandle(), BM_GETSTATE, 0, 0)
        down = bool(state & BST_PUSHED)
        hover = self._hover or bool(state & BST_HOT)
        enabled = self.IsEnabled()
        if self.variant == "primary":
            if not enabled:
                return theme.PRESSED_BG, None, theme.TEXT_DISABLED
            return (theme.ACCENT_PRESSED if down else theme.ACCENT_HOVER if hover else theme.ACCENT), None, wx.WHITE
        if self.variant == "danger":
            fg, border = theme.DANGER, theme.DANGER_BORDER
        elif self.variant == "ghost":
            fg, border = theme.TEXT, None
        else:
            fg, border = theme.TEXT, theme.CONTROL_BORDER
        bg = theme.PRESSED_BG if down else theme.HOVER_BG if hover else theme.CARD_BG
        if self.variant == "ghost" and not (down or hover):
            bg = None
        return bg, (border if enabled else theme.CARD_BORDER), (fg if enabled else theme.TEXT_DISABLED)

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.BufferedPaintDC(self)
        _clear(dc, self)
        gc = _gc(dc)
        w, h = self.GetClientSize()
        radius = self.FromDIP(theme.RADIUS)
        bg, border, fg = self._colours()
        inset = self.FromDIP(2)  # room for the focus ring
        if bg is not None or border is not None:
            gc.SetBrush(wx.Brush(bg) if bg is not None else wx.TRANSPARENT_BRUSH)
            gc.SetPen(wx.Pen(border, 1) if border is not None else wx.TRANSPARENT_PEN)
            gc.DrawRoundedRectangle(inset + 0.5, inset + 0.5, w - 2 * inset - 1, h - 2 * inset - 1, radius)
        if self.HasFocus():
            gc.SetBrush(wx.TRANSPARENT_BRUSH)
            gc.SetPen(wx.Pen(theme.FOCUS_RING, self.FromDIP(2)))
            gc.DrawRoundedRectangle(1, 1, w - 2, h - 2, radius + 1)

        text = self.display_text or self.GetLabelText()
        gc.SetFont(self.GetFont(), fg)
        tw, th = gc.GetTextExtent(text) if text else (0, 0)
        icon_size = self.FromDIP(16)
        gap = self.FromDIP(7) if text else 0
        content = tw + (icon_size + gap if self._icon else 0)
        x = (w - content) / 2
        if self._icon:
            bitmap = theme.icon_bitmap(self._icon, 16, fg, self)
            if bitmap.IsOk():
                gc.DrawBitmap(bitmap, x, (h - icon_size) / 2, icon_size, icon_size)
            x += icon_size + gap
        if text:
            gc.DrawText(text, x, (h - th) / 2)


# ---------------------------------------------------------------------------
# Readable text
# ---------------------------------------------------------------------------

@dataclass
class TextLine:
    """One paragraph of a ReadableText, with its own font and colour."""
    text: str
    font: Optional[wx.Font] = None
    colour: Optional[wx.Colour] = None
    gap: int = 0  # DIP of space above, when a line comes before it


class _TextAccessible(wx.Accessible):
    """MSAA for ReadableText: a focusable, read-only static text named by its text."""

    def __init__(self, control: "ReadableText"):
        super().__init__(control)
        self.control = control

    def GetChildCount(self):
        return (ACC_OK, 0)

    def GetChild(self, childId):
        return (ACC_OK, None)

    def GetParent(self):
        return (wx.ACC_NOT_IMPLEMENTED, None)

    def GetName(self, childId):
        return (ACC_OK, self.control.accessible_text())

    def GetDescription(self, childId):
        return (ACC_OK, "")

    def GetRole(self, childId):
        return (ACC_OK, wx.ROLE_SYSTEM_STATICTEXT)

    def GetState(self, childId):
        state = STATE_FOCUSABLE | wx.ACC_STATE_SYSTEM_READONLY
        if self.control.HasFocus():
            state |= STATE_FOCUSED
        return (ACC_OK, state)

    def GetFocus(self):
        return (ACC_OK, 0, None)

    def GetLocation(self, elementId):
        return (ACC_OK, self.control.GetScreenRect())


class ReadableText(wx.Control):
    """Text that keyboard and screen reader users can Tab to.

    wx.StaticText is skipped by Tab, and NVDA has no browse mode in
    desktop windows, so status and explanations written as static text
    are only reachable through object navigation. This control draws its
    text like a label but is a tab stop that NVDA reads as one line
    ("Fortnite, 34.2, Ready"). Ctrl+C copies the text. Empty text is not
    a tab stop.
    """

    PADDING = 3  # DIP, room for the focus ring
    separator = " "

    def __init__(self, parent: wx.Window, text: str = "", colour: Optional[wx.Colour] = None,
                 font: Optional[wx.Font] = None, wrap: int = 0, name: str = "text"):
        super().__init__(parent, style=wx.BORDER_NONE, name=name)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetFont(font or parent.GetFont())
        self.SetForegroundColour(colour or theme.TEXT)
        self._wrap = wrap
        self._lines: List[TextLine] = [TextLine(text)]
        self._rows: List[tuple] = []
        self._relayout_pending = False
        self.SetAccessible(_TextAccessible(self))
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SET_FOCUS, self._on_focus_change)
        self.Bind(wx.EVT_KILL_FOCUS, self._on_focus_change)
        self.Bind(wx.EVT_SIZE, lambda e: (self.Refresh(), e.Skip()))
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self._fit()

    # StaticText-like API ---------------------------------------------------

    def SetLabel(self, text: str) -> None:
        self.set_lines([TextLine(text)])

    def GetLabel(self) -> str:
        return self.accessible_text()

    def GetLabelText(self) -> str:
        return self.accessible_text()

    def Wrap(self, width: int) -> None:
        if width != self._wrap:
            self._wrap = width
            self._fit()

    def SetForegroundColour(self, colour: wx.Colour) -> bool:
        changed = super().SetForegroundColour(colour)
        self.Refresh()
        return changed

    # -------------------------------------------------------------------------

    def set_lines(self, lines: List[TextLine]) -> None:
        old = self.accessible_text()
        self._lines = lines
        self._fit()
        self.Refresh()
        if self.accessible_text() != old:
            wx.Accessible.NotifyEvent(wx.ACC_EVENT_OBJECT_NAMECHANGE, self, wx.OBJID_CLIENT, 0)

    def accessible_text(self) -> str:
        return self.separator.join(line.text for line in self._lines if line.text)

    def AcceptsFocus(self) -> bool:
        return self.IsShown() and bool(self.accessible_text())

    def AcceptsFocusFromKeyboard(self) -> bool:
        return self.AcceptsFocus()

    def _padding(self) -> int:
        return self.FromDIP(self.PADDING)

    def _fit(self) -> None:
        from wx.lib.wordwrap import wordwrap
        dc = wx.ClientDC(self)
        pad = self._padding()
        rows = []
        y = pad
        width = 0
        for line in self._lines:
            if not line.text:
                continue
            font = line.font or self.GetFont()
            dc.SetFont(font)
            text = wordwrap(line.text, self._wrap, dc) if self._wrap else line.text
            if rows:
                y += self.FromDIP(line.gap)
            for part in text.rstrip("\n").split("\n"):
                w, h = dc.GetTextExtent(part or " ")
                rows.append((part, font, line.colour, y))
                y += h
                width = max(width, w)
        self._rows = rows
        size = wx.Size(width + 2 * pad, y + pad if rows else 0)
        if size != self.GetMinSize():
            self.SetMinSize(size)
            self.SetSize(wx.Size(max(size.width, self.GetSize().width), size.height))
            self._schedule_relayout()

    def _schedule_relayout(self) -> None:
        # The new size has to reach the page's sizers, which StaticText
        # leaves to the caller; do it once per batch of changes.
        if not self._relayout_pending:
            self._relayout_pending = True
            wx.CallAfter(self._relayout)

    def _relayout(self) -> None:
        if not self:
            return
        self._relayout_pending = False
        window = self.GetParent()
        while window is not None and not window.IsTopLevel():
            window.Layout()
            if isinstance(window, wx.ScrolledWindow):
                window.FitInside()
                break
            window = window.GetParent()

    def _on_focus_change(self, event: wx.FocusEvent) -> None:
        self.Refresh()
        event.Skip()

    def _on_key_down(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == ord("C") and event.GetModifiers() == wx.MOD_CONTROL:
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(self.accessible_text()))
                wx.TheClipboard.Close()
            return
        event.Skip()

    def _paint_background(self, gc: wx.GraphicsContext, w: int, h: int) -> None:
        if self.HasFocus():
            gc.SetBrush(wx.TRANSPARENT_BRUSH)
            gc.SetPen(wx.Pen(theme.FOCUS_RING, self.FromDIP(2)))
            gc.DrawRoundedRectangle(1, 1, w - 2, h - 2, self.FromDIP(4))

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        _clear(dc, self)
        gc = _gc(dc)
        w, h = self.GetClientSize()
        self._paint_background(gc, w, h)
        pad = self._padding()
        for text, font, colour, y in self._rows:
            gc.SetFont(font, colour or self.GetForegroundColour())
            gc.DrawText(text, pad, y)


# ---------------------------------------------------------------------------
# Selectable item lists (sidebar and tabs share the accessibility plumbing)
# ---------------------------------------------------------------------------

class _ItemsAccessible(wx.Accessible):
    """MSAA for a control with selectable items; children are numbered from 1."""

    def __init__(self, control: "_ItemsControl", role: int, item_role: int):
        super().__init__(control)
        self.control = control
        self.role = role
        self.item_role = item_role

    def GetChildCount(self):
        return (ACC_OK, self.control.item_count())

    def GetChild(self, childId):
        return (ACC_OK, None)

    def GetParent(self):
        return (wx.ACC_NOT_IMPLEMENTED, None)

    def GetName(self, childId):
        if childId == 0:
            return (ACC_OK, self.control.GetName())
        return (ACC_OK, self.control.item_label(childId - 1))

    def GetDescription(self, childId):
        return (ACC_OK, self.control.item_description(childId - 1) if childId else "")

    def GetRole(self, childId):
        return (ACC_OK, self.role if childId == 0 else self.item_role)

    def GetState(self, childId):
        focused = self.control.HasFocus()
        if childId == 0:
            return (ACC_OK, STATE_FOCUSABLE | (STATE_FOCUSED if focused else 0))
        state = STATE_SELECTABLE | STATE_FOCUSABLE
        if childId - 1 == self.control.selection:
            state |= STATE_SELECTED | (STATE_FOCUSED if focused else 0)
        return (ACC_OK, state)

    def GetFocus(self):
        if not self.control.HasFocus():
            return (ACC_OK, 0, None)
        return (ACC_OK, self.control.selection + 1 if self.control.selection >= 0 else 0, None)

    def GetSelections(self):
        return (ACC_OK, self.control.selection + 1 if self.control.selection >= 0 else 0)

    def GetLocation(self, elementId):
        if elementId == 0:
            return (ACC_OK, self.control.GetScreenRect())
        rect = self.control.item_rect(elementId - 1)
        origin = self.control.ClientToScreen(rect.GetPosition())
        return (ACC_OK, wx.Rect(origin, rect.GetSize()))

    def GetDefaultAction(self, childId):
        return (ACC_OK, "Select" if childId else "")

    def DoDefaultAction(self, childId):
        if childId:
            wx.CallAfter(self.control.set_selection, childId - 1, True)
        return ACC_OK

    def HitTest(self, pt):
        index = self.control.item_at(self.control.ScreenToClient(pt))
        if index is None:
            return (ACC_OK, 0, None)
        return (ACC_OK, index + 1, None)


class _ItemsControl(wx.Control):
    """Shared keyboard, mouse and accessibility behaviour for the sidebar and tab bar."""

    horizontal = False

    def __init__(self, parent: wx.Window, name: str, role: int, item_role: int):
        super().__init__(parent, style=wx.BORDER_NONE | wx.WANTS_CHARS, name=name)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.selection = -1
        self._hover = -1
        self.on_select: Optional[Callable[[int], None]] = None
        self.SetAccessible(_ItemsAccessible(self, role, item_role))
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_click)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, lambda e: self._set_hover(-1))
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self.Bind(wx.EVT_SET_FOCUS, self._on_focus_change)
        self.Bind(wx.EVT_KILL_FOCUS, self._on_focus_change)

    # Subclasses provide these.
    def item_count(self) -> int:
        raise NotImplementedError

    def item_label(self, index: int) -> str:
        raise NotImplementedError

    def item_description(self, index: int) -> str:
        return ""

    def item_rect(self, index: int) -> wx.Rect:
        raise NotImplementedError

    def _paint(self, gc: wx.GraphicsContext) -> None:
        raise NotImplementedError

    # Behaviour -----------------------------------------------------------

    def AcceptsFocus(self) -> bool:
        return self.IsShown() and self.item_count() > 0

    def AcceptsFocusFromKeyboard(self) -> bool:
        return self.AcceptsFocus()

    def item_at(self, pos: wx.Point) -> Optional[int]:
        for index in range(self.item_count()):
            if self.item_rect(index).Contains(pos):
                return index
        return None

    def set_selection(self, index: int, notify: bool = False) -> None:
        if not 0 <= index < self.item_count():
            return
        if index == self.selection:
            return
        self.selection = index
        self.ensure_visible(index)
        self.Refresh()
        if self.HasFocus():
            wx.Accessible.NotifyEvent(wx.ACC_EVENT_OBJECT_FOCUS, self, wx.OBJID_CLIENT, index + 1)
        wx.Accessible.NotifyEvent(wx.ACC_EVENT_OBJECT_SELECTION, self, wx.OBJID_CLIENT, index + 1)
        if notify and self.on_select is not None:
            self.on_select(index)

    def ensure_visible(self, index: int) -> None:
        """Scrolling hook for subclasses."""

    def _set_hover(self, index: int) -> None:
        if index != self._hover:
            self._hover = index
            self.Refresh()

    def _on_motion(self, event: wx.MouseEvent) -> None:
        index = self.item_at(event.GetPosition())
        self._set_hover(-1 if index is None else index)

    def _on_click(self, event: wx.MouseEvent) -> None:
        index = self.item_at(event.GetPosition())
        self.SetFocus()
        if index is not None:
            self.set_selection(index, notify=True)

    def _on_focus_change(self, event: wx.FocusEvent) -> None:
        self.Refresh()
        if event.GetEventType() == wx.wxEVT_SET_FOCUS and self.selection >= 0:
            # The window got focus; tell screen readers which item has it.
            wx.CallAfter(self._notify_focus)
        event.Skip()

    def _notify_focus(self) -> None:
        if self and self.HasFocus() and self.selection >= 0:
            wx.Accessible.NotifyEvent(wx.ACC_EVENT_OBJECT_FOCUS, self, wx.OBJID_CLIENT, self.selection + 1)

    def _step_keys(self):
        if self.horizontal:
            return wx.WXK_LEFT, wx.WXK_RIGHT
        return wx.WXK_UP, wx.WXK_DOWN

    def _on_key_down(self, event: wx.KeyEvent) -> None:
        key = event.GetKeyCode()
        back, forward = self._step_keys()
        count = self.item_count()
        if event.HasAnyModifiers() and key != wx.WXK_TAB:
            if (self.horizontal and event.GetModifiers() == wx.MOD_CONTROL
                    and key in (wx.WXK_PAGEUP, wx.WXK_PAGEDOWN)):
                self.Navigate(wx.NavigationKeyEvent.WinChange | (
                    wx.NavigationKeyEvent.IsForward if key == wx.WXK_PAGEDOWN else wx.NavigationKeyEvent.IsBackward))
                return
            event.Skip()
            return
        if key == back:
            self.set_selection(max(self.selection - 1, 0), notify=True)
        elif key == forward:
            self.set_selection(min(self.selection + 1, count - 1), notify=True)
        elif key == wx.WXK_HOME:
            self.set_selection(0, notify=True)
        elif key == wx.WXK_END:
            self.set_selection(count - 1, notify=True)
        elif key == wx.WXK_TAB:
            flags = wx.NavigationKeyEvent.IsBackward if event.ShiftDown() else wx.NavigationKeyEvent.IsForward
            if event.ControlDown():
                flags |= wx.NavigationKeyEvent.WinChange
            self.Navigate(flags)
        elif 32 < key < 127 and chr(key).isalnum():
            self._type_ahead(chr(key).lower())
        else:
            event.Skip()

    def _type_ahead(self, letter: str) -> None:
        count = self.item_count()
        for step in range(1, count + 1):
            index = (self.selection + step) % count
            if self.item_label(index).lower().startswith(letter):
                self.set_selection(index, notify=True)
                return

    def _background(self) -> wx.Colour:
        return self.GetBackgroundColour()

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self._background()))
        dc.Clear()
        self._paint(_gc(dc))


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

@dataclass
class NavItem:
    key: str
    label: str
    icon: str
    group: str = ""


class NavList(_ItemsControl):
    """The hub's page list: icons, section headings, and a rounded selection."""

    ROW = 36
    HEADING = 30
    PAD = 8
    ICON = 18

    def __init__(self, parent: wx.Window, items: List[NavItem], name: str = "Pages"):
        super().__init__(parent, name, wx.ROLE_SYSTEM_LIST, wx.ROLE_SYSTEM_LISTITEM)
        self.SetBackgroundColour(theme.SIDEBAR_BG)
        self.items = items
        self._scroll = 0
        self._rects: List[wx.Rect] = []
        self._headings: List[tuple] = []
        self.on_activate: Optional[Callable[[], None]] = None
        self._layout()
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_wheel)

    def item_count(self) -> int:
        return len(self.items)

    def item_label(self, index: int) -> str:
        return self.items[index].label

    def item_description(self, index: int) -> str:
        return self.items[index].group

    def item_rect(self, index: int) -> wx.Rect:
        rect = wx.Rect(self._rects[index])
        rect.y -= self._scroll
        return rect

    def DoGetBestClientSize(self) -> wx.Size:
        return wx.Size(self.FromDIP(210), self._content_height())

    def _layout(self) -> None:
        self._rects, self._headings = [], []
        pad, row, heading = self.FromDIP(self.PAD), self.FromDIP(self.ROW), self.FromDIP(self.HEADING)
        width = self.GetClientSize().width - 2 * pad
        y = pad
        group = None
        for item in self.items:
            if item.group != group:
                group = item.group
                if group:
                    self._headings.append((group, y + self.FromDIP(6)))
                    y += heading
            self._rects.append(wx.Rect(pad, y, max(width, 1), row))
            y += row + self.FromDIP(2)
        self._height = y + pad

    def _on_size(self, event: wx.SizeEvent) -> None:
        self._layout()
        self._scroll = min(self._scroll, max(self._height - self.GetClientSize().height, 0))
        if self.selection >= 0:
            self.ensure_visible(self.selection)
        self.Refresh()
        event.Skip()

    def _content_height(self) -> int:
        self._layout()
        return self._height

    def ensure_visible(self, index: int) -> None:
        rect = self._rects[index] if index < len(self._rects) else None
        if rect is None:
            return
        view = self.GetClientSize().height
        if view <= 0:
            return
        if rect.y - self._scroll < 0:
            self._scroll = max(rect.y - self.FromDIP(self.HEADING), 0)
        elif rect.GetBottom() - self._scroll > view:
            self._scroll = rect.GetBottom() - view + self.FromDIP(self.PAD)

    def _on_wheel(self, event: wx.MouseEvent) -> None:
        view = self.GetClientSize().height
        limit = max(self._height - view, 0)
        self._scroll = min(max(self._scroll - event.GetWheelRotation() // 2, 0), limit)
        self.Refresh()

    def _on_key_down(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_RIGHT) and not event.HasAnyModifiers():
            if self.on_activate is not None:
                self.on_activate()
            return
        super()._on_key_down(event)

    def _paint(self, gc: wx.GraphicsContext) -> None:
        font = self.GetFont()
        heading_font = wx.Font(font)
        heading_font.SetPointSize(max(font.GetPointSize() - 1, 7))
        heading_font.SetWeight(wx.FONTWEIGHT_SEMIBOLD)
        gc.SetFont(heading_font, theme.TEXT_MUTED)
        pad = self.FromDIP(self.PAD)
        for text, y in self._headings:
            gc.DrawText(text, pad + self.FromDIP(10), y - self._scroll)

        radius = self.FromDIP(6)
        icon = self.FromDIP(self.ICON)
        focused = self.HasFocus()
        for index, item in enumerate(self.items):
            rect = self.item_rect(index)
            selected = index == self.selection
            if selected:
                gc.SetBrush(wx.Brush(theme.SELECTED_BG))
                gc.SetPen(wx.Pen(theme.FOCUS_RING, self.FromDIP(1)) if focused else wx.TRANSPARENT_PEN)
                gc.DrawRoundedRectangle(rect.x + 0.5, rect.y + 0.5, rect.width - 1, rect.height - 1, radius)
            elif index == self._hover:
                gc.SetBrush(wx.Brush(theme.HOVER_BG))
                gc.SetPen(wx.TRANSPARENT_PEN)
                gc.DrawRoundedRectangle(rect.x, rect.y, rect.width, rect.height, radius)
            colour = theme.SELECTED_TEXT if selected else theme.TEXT_SECONDARY
            bitmap = theme.icon_bitmap(item.icon, self.ICON, colour, self)
            x = rect.x + self.FromDIP(10)
            if bitmap.IsOk():
                gc.DrawBitmap(bitmap, x, rect.y + (rect.height - icon) / 2, icon, icon)
            gc.SetFont(font, theme.SELECTED_TEXT if selected else theme.TEXT)
            tw, th = gc.GetTextExtent(item.label)
            gc.DrawText(item.label, x + icon + self.FromDIP(10), rect.y + (rect.height - th) / 2)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

class TabBar(_ItemsControl):
    """Row of pill-shaped tabs."""

    horizontal = True
    GAP = 4
    PAD_X = 12
    HEIGHT = 30

    def __init__(self, parent: wx.Window, name: str = "Tabs"):
        super().__init__(parent, name, wx.ROLE_SYSTEM_PAGETABLIST, wx.ROLE_SYSTEM_PAGETAB)
        self.labels: List[str] = []
        self._rects: List[wx.Rect] = []

    def item_count(self) -> int:
        return len(self.labels)

    def _background(self) -> wx.Colour:
        return self.GetParent().GetBackgroundColour()

    def item_label(self, index: int) -> str:
        return strip_mnemonic(self.labels[index])

    def item_rect(self, index: int) -> wx.Rect:
        return self._rects[index]

    def set_labels(self, labels: List[str]) -> None:
        self.labels = list(labels)
        self._layout()
        self.InvalidateBestSize()
        self.SetInitialSize()
        self.Refresh()
        wx.Accessible.NotifyEvent(wx.ACC_EVENT_OBJECT_REORDER, self, wx.OBJID_CLIENT, 0)

    def _layout(self) -> None:
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        x, height = 0, self.FromDIP(self.HEIGHT)
        self._rects = []
        for label in self.labels:
            w = dc.GetTextExtent(strip_mnemonic(label))[0] + 2 * self.FromDIP(self.PAD_X)
            self._rects.append(wx.Rect(x, 0, w, height))
            x += w + self.FromDIP(self.GAP)
        self._width = max(x - self.FromDIP(self.GAP), 0)

    def DoGetBestClientSize(self) -> wx.Size:
        self._layout()
        return wx.Size(self._width + 2, self.FromDIP(self.HEIGHT) + 2)

    def _paint(self, gc: wx.GraphicsContext) -> None:
        radius = self.FromDIP(theme.RADIUS)
        focused = self.HasFocus()
        for index, label in enumerate(self.labels):
            rect = self._rects[index]
            selected = index == self.selection
            if selected:
                gc.SetBrush(wx.Brush(theme.SELECTED_BG))
                gc.SetPen(wx.Pen(theme.FOCUS_RING, self.FromDIP(1)) if focused else wx.Pen(theme.SELECTED_BG))
            else:
                gc.SetBrush(wx.Brush(theme.HOVER_BG if index == self._hover else self._background()))
                gc.SetPen(wx.Pen(theme.CARD_BORDER))
            gc.DrawRoundedRectangle(rect.x + 0.5, rect.y + 0.5, rect.width - 1, rect.height - 1, radius)
            gc.SetFont(self.GetFont(), theme.SELECTED_TEXT if selected else theme.TEXT_SECONDARY)
            text = strip_mnemonic(label)
            tw, th = gc.GetTextExtent(text)
            gc.DrawText(text, rect.x + (rect.width - tw) / 2, rect.y + (rect.height - th) / 2)


class PageStack(wx.Panel):
    """Holds pages and shows one at a time, without moving focus.

    wx.Simplebook moves focus into each page it shows. When the user is
    arrowing through a list of pages (the sidebar or a row of tabs), that
    throws them out of the list and makes screen readers announce a control
    in the page instead of the next page's name.
    """

    def __init__(self, parent: wx.Window):
        super().__init__(parent, style=wx.TAB_TRAVERSAL)
        self.SetBackgroundColour(parent.GetBackgroundColour())
        self._sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self._sizer)
        self._pages: List[wx.Window] = []
        self._selection = -1

    def AddPage(self, page: wx.Window, _text: str = "") -> bool:
        if page.GetParent() is not self:
            page.Reparent(self)
        page.Hide()
        self._sizer.Add(page, 1, wx.EXPAND)
        self._pages.append(page)
        return True

    def RemovePage(self, index: int) -> wx.Window:
        page = self._pages.pop(index)
        self._sizer.Detach(page)
        if self._selection == index:
            self._selection = -1
        elif self._selection > index:
            self._selection -= 1
        return page

    def GetPageCount(self) -> int:
        return len(self._pages)

    def GetPage(self, index: int) -> wx.Window:
        return self._pages[index]

    def GetSelection(self) -> int:
        return self._selection

    def GetCurrentPage(self) -> Optional[wx.Window]:
        return self._pages[self._selection] if self._selection >= 0 else None

    def ChangeSelection(self, index: int) -> int:
        old = self._selection
        if not 0 <= index < len(self._pages) or index == old:
            return old
        previous = self.GetCurrentPage()
        self.Freeze()
        try:
            self._pages[index].Show()
            if previous is not None:
                previous.Hide()
            self._selection = index
            self.Layout()
        finally:
            self.Thaw()
        return old


class TabbedBook(wx.Panel):
    """Drop-in replacement for the parts of wx.Notebook FA11y uses, drawn as pill tabs.

    Pages may be created with the TabbedBook as their parent; AddPage moves
    them into the page area. Sends EVT_NOTEBOOK_PAGE_CHANGED like wx.Notebook.
    Pages live in a PageStack, so switching tabs never moves focus off the
    tabs.
    """

    def __init__(self, parent: wx.Window, id: int = wx.ID_ANY, name: str = "Tabs", **_kwargs):
        super().__init__(parent, id, style=wx.TAB_TRAVERSAL, name=name)
        self.SetBackgroundColour(parent.GetBackgroundColour())
        self.SetForegroundColour(theme.TEXT)
        self.tabs = TabBar(self, name)
        self.book = PageStack(self)
        self.tabs.on_select = self._on_tab_selected
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.tabs, 0, wx.BOTTOM, self.FromDIP(10))
        sizer.Add(self.book, 1, wx.EXPAND)
        self.SetSizer(sizer)
        self._texts: List[str] = []
        self.Bind(wx.EVT_NAVIGATION_KEY, self._on_navigation_key)

    # wx.Notebook API ------------------------------------------------------

    def AddPage(self, page: wx.Window, text: str, select: bool = False, imageId: int = -1) -> bool:
        page.SetBackgroundColour(self.GetBackgroundColour())
        self.book.AddPage(page)
        self._texts.append(text)
        self.tabs.set_labels(self._texts)
        if select or self.GetSelection() < 0:
            self.ChangeSelection(self.GetPageCount() - 1)
        return True

    def DeletePage(self, index: int) -> bool:
        if not 0 <= index < self.GetPageCount():
            return False
        self.book.RemovePage(index).Destroy()
        del self._texts[index]
        if self.GetSelection() < 0 and self.GetPageCount():
            self.ChangeSelection(min(index, self.GetPageCount() - 1))
        self.tabs.selection = self.GetSelection()
        self.tabs.set_labels(self._texts)
        return True

    def DeleteAllPages(self) -> bool:
        while self.GetPageCount():
            self.DeletePage(self.GetPageCount() - 1)
        return True

    def GetPageCount(self) -> int:
        return self.book.GetPageCount()

    def GetPage(self, index: int) -> wx.Window:
        return self.book.GetPage(index)

    def GetCurrentPage(self) -> Optional[wx.Window]:
        return self.book.GetCurrentPage()

    def GetPageText(self, index: int) -> str:
        return self._texts[index]

    def SetPageText(self, index: int, text: str) -> bool:
        self._texts[index] = text
        self.tabs.set_labels(self._texts)
        return True

    def GetSelection(self) -> int:
        return self.book.GetSelection()

    def ChangeSelection(self, index: int) -> int:
        old = self.book.ChangeSelection(index)
        self.tabs.set_selection(index)
        return old

    def SetSelection(self, index: int) -> int:
        old = self.ChangeSelection(index)
        if old != index:
            self._send_changed(index, old)
        return old

    def AdvanceSelection(self, forward: bool = True) -> None:
        count = self.GetPageCount()
        if count:
            self.SetSelection((self.GetSelection() + (1 if forward else -1)) % count)

    def SetFocus(self) -> None:
        self.tabs.SetFocus()

    # -------------------------------------------------------------------------

    def _on_tab_selected(self, index: int) -> None:
        old = self.book.ChangeSelection(index)
        if old != index:
            self._send_changed(index, old)

    def _send_changed(self, index: int, old: int) -> None:
        event = wx.BookCtrlEvent(wx.wxEVT_NOTEBOOK_PAGE_CHANGED, self.GetId(), index, old)
        event.SetEventObject(self)
        self.GetEventHandler().ProcessEvent(event)

    def _on_navigation_key(self, event: wx.NavigationKeyEvent) -> None:
        # Ctrl+Tab and Ctrl+Shift+Tab arrive here as "window change"
        # navigation, as they would for wx.Notebook. Like the native
        # notebook, focus stays on the tabs if they had it, otherwise it
        # moves into the new page.
        if not event.IsWindowChange() or not self.GetPageCount():
            event.Skip()
            return
        tabs_focused = self.tabs.HasFocus()
        self.AdvanceSelection(event.GetDirection())
        page = self.GetCurrentPage()
        if tabs_focused or page is None:
            self.tabs.SetFocus()
        else:
            page.SetFocus()


# ---------------------------------------------------------------------------
# Settings group
# ---------------------------------------------------------------------------

class SettingsGroup(wx.StaticBox):
    """A native group box drawn as a card with a heading.

    Controls go inside it as children (use with wx.StaticBoxSizer), so
    screen readers announce the group's name when focus moves into it,
    e.g. "Announcements grouping".
    """

    keep_background = True

    def __init__(self, parent: wx.Window, label: str):
        super().__init__(parent, label=label)
        self.SetBackgroundColour(theme.CARD_BG)
        self.SetForegroundColour(theme.TEXT)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)
        self.Bind(wx.EVT_SIZE, lambda e: (self.Refresh(), e.Skip()))

    def heading_font(self) -> wx.Font:
        return wx.Font(wx.FontInfo(theme.BASE_POINTS + 1).FaceName(theme.FONT_FACE).Bold())

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.BufferedPaintDC(self)
        _clear(dc, self)
        gc = _gc(dc)
        w, h = self.GetClientSize()
        gc.SetBrush(wx.Brush(theme.CARD_BG))
        gc.SetPen(wx.Pen(theme.CARD_BORDER, 1))
        gc.DrawRoundedRectangle(0.5, 0.5, w - 1, h - 1, self.FromDIP(theme.RADIUS))
        gc.SetFont(self.heading_font(), theme.TEXT)
        gc.DrawText(self.GetLabelText(), self.FromDIP(16), self.FromDIP(10))
