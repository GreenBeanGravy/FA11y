"""
Shared base class + helpers for STW manager sub-dialogs.

Each sub-dialog is a modal wx.Dialog that:
  - Takes an STWApi instance (already authenticated) via __init__
  - Builds its own UI in `_build_ui`
  - Populates data in `_populate` (also called on refresh)
  - Owns a Refresh button and a Close button
  - Announces useful context via accessible_output2 on open
"""
from __future__ import annotations

import logging
from typing import Optional

import wx
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import (
    AccessibleDialog,
    ensure_window_focus_and_center_mouse,
    messageBox,
)

logger = logging.getLogger(__name__)
speaker = Auto()


def confirm(parent, message: str, caption: str = "Confirm") -> bool:
    """Modal Yes/No confirmation. Returns True on Yes."""
    dlg = wx.MessageDialog(
        parent,
        message,
        caption,
        style=wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
    )
    try:
        return dlg.ShowModal() == wx.ID_YES
    finally:
        dlg.Destroy()


def speak_later(text: str) -> None:
    try:
        speaker.speak(text)
    except Exception as e:
        logger.debug(f"STW dialog speak failed: {e}")


# Known MCP error-code substrings -> user-facing explanations. Used by
# `explain_api_error` so every dialog surfaces consistent wording.
_KNOWN_ERRORS = [
    ("inventory_overflow", "This item is in inventory overflow. Recycle or "
                           "transform items in-game to clear overflow first."),
    ("not unlocked", "That slot or feature isn't unlocked on your account yet."),
    ("purchase_not_allowed", "Epic won't allow this purchase — usually a "
                             "daily/event limit you've already hit."),
    ("catalog_out_of_date", "Prices changed since this offer was loaded. "
                            "Refresh and try again."),
    ("not_enough", "You don't have enough of the required currency."),
    ("insufficient", "You don't have enough of the required currency."),
    ("invalid_parameter", "Epic rejected the request parameters. "
                          "See the details below."),
    ("not_found", "Epic couldn't find the target item. It may have been "
                  "consumed or changed since the profile was last loaded."),
]


def explain_api_error(error_code: str, error_message: str,
                      default: str = "The operation failed.") -> str:
    """Turn an Epic MCP errorCode+message pair into a user-facing string."""
    if not error_code and not error_message:
        return default
    lower = (error_code or "").lower() + " " + (error_message or "").lower()
    for marker, explanation in _KNOWN_ERRORS:
        if marker in lower:
            return f"{explanation}\n\nEpic says: {error_message or error_code}"
    # Fall through: show the raw Epic response.
    return f"{default}\n\nEpic: {error_code}\n{error_message}"


class StwSubDialog(AccessibleDialog):
    """Base class for every STW sub-dialog.

    Subclasses should override `_build_ui(sizer)` and `_populate()`. The
    base class handles: wx.Dialog plumbing, refresh/close buttons, ESC to
    close, standard sizing + centring.
    """

    def __init__(
        self,
        parent: Optional[wx.Window],
        stw_api,
        title: str,
        help_id: str,
        default_size: tuple = (780, 560),
    ) -> None:
        super().__init__(parent, title=title, helpId=help_id)
        self.stw_api = stw_api
        self._default_size = default_size

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        self._content_sizer = wx.BoxSizer(wx.VERTICAL)

        self._build_ui(self._content_sizer)

        main_sizer.Add(self._content_sizer, 1, wx.EXPAND | wx.ALL, 10)

        # Button row: subclass can add more; Refresh + Close always present.
        self._button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._add_extra_buttons(self._button_sizer)

        refresh_btn = wx.Button(self, label="&Refresh")
        refresh_btn.Bind(wx.EVT_BUTTON, self._on_refresh)
        self._button_sizer.Add(refresh_btn, 0, wx.ALL, 5)

        close_btn = wx.Button(self, wx.ID_CLOSE, label="&Close")
        close_btn.Bind(wx.EVT_BUTTON, lambda _evt: self.EndModal(wx.ID_CLOSE))
        self._button_sizer.Add(close_btn, 0, wx.ALL, 5)

        main_sizer.Add(self._button_sizer, 0, wx.ALIGN_RIGHT)
        self.SetSizer(main_sizer)
        self.SetSize(self._default_size)
        self.CentreOnScreen()
        self.SetEscapeId(wx.ID_CLOSE)

        # Populate after the UI is built so controls exist.
        try:
            self._populate()
        except Exception as e:
            logger.error(f"{type(self).__name__}._populate failed: {e}")

    # Subclass hooks ------------------------------------------------------
    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        raise NotImplementedError

    def _populate(self) -> None:
        pass

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        """Override to insert extra action buttons before Refresh/Close."""
        pass

    # Events --------------------------------------------------------------
    def _on_refresh(self, _evt: wx.CommandEvent) -> None:
        speak_later("Refreshing.")
        ok = self.stw_api.query_profile(force=True)
        if not ok:
            speak_later("Refresh failed.")
            return
        try:
            self._populate()
            speak_later("Refreshed.")
        except Exception as e:
            logger.error(f"{type(self).__name__} refresh failed: {e}")
            speak_later("Refresh failed.")

    # Utilities -----------------------------------------------------------
    def focus_now(self) -> None:
        try:
            ensure_window_focus_and_center_mouse(self)
        except Exception:
            pass

    def show_info(self, message: str, caption: str = "Info") -> None:
        messageBox(message, caption, wx.OK | wx.ICON_INFORMATION, parent=self)

    def show_error(self, message: str, caption: str = "Error") -> None:
        messageBox(message, caption, wx.OK | wx.ICON_ERROR, parent=self)

    def confirm(self, message: str, caption: str = "Confirm") -> bool:
        return confirm(self, message, caption)
