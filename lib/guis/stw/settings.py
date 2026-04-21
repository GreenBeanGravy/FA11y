"""
STW manager settings sub-dialog.

Exposes the background alert monitor's config: enabled flag, poll interval,
reward triggers, founder override.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

import wx

from lib.config.config_manager import config_manager
from lib.guis.stw.base import StwSubDialog, speak_later

logger = logging.getLogger(__name__)


FOUNDER_CHOICES = [
    ("auto", "Auto-detect (recommended)"),
    ("founder", "Always Founder (V-Bucks)"),
    ("non_founder", "Always Non-Founder (X-Ray Tickets)"),
]


class STWSettingsDialog(StwSubDialog):
    """Edit stw_settings.json via a friendly form."""

    def __init__(self, parent, stw_api):
        self._enabled_cb: Optional[wx.CheckBox] = None
        self._poll_spin: Optional[wx.SpinCtrl] = None
        self._vbuck_cb: Optional[wx.CheckBox] = None
        self._xray_cb: Optional[wx.CheckBox] = None
        self._legendary_cb: Optional[wx.CheckBox] = None
        self._evo_cb: Optional[wx.CheckBox] = None
        self._perkup_cb: Optional[wx.CheckBox] = None
        self._founder_choice: Optional[wx.Choice] = None
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Settings",
            help_id="SaveTheWorldSettings",
            default_size=(620, 540),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        intro = wx.StaticText(
            self,
            label=(
                "Configure the background mission-alert poller. Settings save "
                "to config/stw_settings.json and apply on the next poll."
            ),
        )
        sizer.Add(intro, 0, wx.ALL | wx.EXPAND, 5)

        self._enabled_cb = wx.CheckBox(
            self, label="Enable background mission-alert announcements"
        )
        sizer.Add(self._enabled_cb, 0, wx.ALL, 5)

        poll_row = wx.BoxSizer(wx.HORIZONTAL)
        poll_row.Add(wx.StaticText(self, label="Poll interval (seconds):"),
                     0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self._poll_spin = wx.SpinCtrl(self, min=15, max=3600, initial=60)
        poll_row.Add(self._poll_spin)
        sizer.Add(poll_row, 0, wx.ALL | wx.EXPAND, 5)

        triggers_box = wx.StaticBox(self, label="Alert triggers")
        triggers_sizer = wx.StaticBoxSizer(triggers_box, wx.VERTICAL)
        self._vbuck_cb = wx.CheckBox(
            self, label="V-Buck missions (Founders)"
        )
        self._xray_cb = wx.CheckBox(
            self, label="X-Ray Ticket missions (Non-Founders)"
        )
        self._legendary_cb = wx.CheckBox(
            self, label="Legendary / Mythic survivor rewards"
        )
        self._evo_cb = wx.CheckBox(
            self, label="Evolution materials on 4-player missions"
        )
        self._perkup_cb = wx.CheckBox(
            self, label="PERK-UPs on 4-player missions"
        )
        for cb in (
            self._vbuck_cb,
            self._xray_cb,
            self._legendary_cb,
            self._evo_cb,
            self._perkup_cb,
        ):
            triggers_sizer.Add(cb, 0, wx.ALL, 3)
        sizer.Add(triggers_sizer, 0, wx.EXPAND | wx.ALL, 5)

        founder_row = wx.BoxSizer(wx.HORIZONTAL)
        founder_row.Add(wx.StaticText(self, label="Founder mode:"),
                        0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self._founder_choice = wx.Choice(
            self, choices=[label for _key, label in FOUNDER_CHOICES]
        )
        founder_row.Add(self._founder_choice)
        sizer.Add(founder_row, 0, wx.ALL | wx.EXPAND, 5)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        save_btn = wx.Button(self, label="&Save Settings")
        save_btn.Bind(wx.EVT_BUTTON, self._on_save)
        sizer.Add(save_btn, 0, wx.ALL, 5)

    def _populate(self) -> None:
        # Ensure config exists (alert monitor registers on import; double-
        # register is safe / idempotent).
        try:
            from lib.monitors.stw_alert_monitor import _register_config
            _register_config()
        except Exception:
            pass
        data = config_manager.get("stw_settings") or {}
        self._enabled_cb.SetValue(bool(data.get("background_alerts_enabled", True)))
        self._poll_spin.SetValue(int(data.get("poll_seconds", 60) or 60))
        triggers = dict(data.get("triggers") or {})
        self._vbuck_cb.SetValue(bool(triggers.get("vbucks", True)))
        self._xray_cb.SetValue(bool(triggers.get("xray", True)))
        self._legendary_cb.SetValue(bool(triggers.get("legendary_survivor", True)))
        self._evo_cb.SetValue(bool(triggers.get("evo_mat_four_player", True)))
        self._perkup_cb.SetValue(bool(triggers.get("perkup_four_player", True)))
        founder_mode = str(data.get("founder_override", "auto") or "auto")
        sel_idx = 0
        for idx, (key, _) in enumerate(FOUNDER_CHOICES):
            if key == founder_mode:
                sel_idx = idx
                break
        self._founder_choice.SetSelection(sel_idx)

    def _on_save(self, _evt: wx.CommandEvent) -> None:
        founder_key = FOUNDER_CHOICES[self._founder_choice.GetSelection()][0]
        data = {
            "background_alerts_enabled": self._enabled_cb.IsChecked(),
            "poll_seconds": int(self._poll_spin.GetValue()),
            "triggers": {
                "vbucks": self._vbuck_cb.IsChecked(),
                "xray": self._xray_cb.IsChecked(),
                "legendary_survivor": self._legendary_cb.IsChecked(),
                "evo_mat_four_player": self._evo_cb.IsChecked(),
                "perkup_four_player": self._perkup_cb.IsChecked(),
            },
            "founder_override": founder_key,
        }
        ok = config_manager.set("stw_settings", data=data)
        if ok:
            speak_later("Save the World settings saved.")
            self.show_info("Settings saved.")
        else:
            self.show_error("Could not save settings.")
