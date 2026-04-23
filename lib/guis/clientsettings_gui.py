"""
Client Settings Editor GUI for FA11y.

Cloud-only workflow. On open, the editor downloads the authenticated user's
``ClientSettings.Sav`` from Epic's cloud storage and parses that as the
source of truth; saves push the edited buffer straight back to the cloud.
Local ``Saved/Config/ClientSettings.Sav`` is never read or written by this
GUI — on-disk copies can lag behind the cloud (especially after playing on
other devices) and the parser was surfacing stale values.

Uses FA11y's existing EpicAuth session — no separate login.

Layout
------
Notebook with three tabs:
    1. "Settings"  — sensitivity (% display), FOV, audio volumes, region, toggles
    2. "Keybinds"  — per-sub-game binding list; double-click a row to edit
    3. "Cloud"     — metadata readout; "Refresh from cloud" discards edits
                     and re-downloads

Values are edited in-memory on the loaded ClientSettingsFile. "Save to
Cloud" serializes the in-memory buffer and PUT-uploads it.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

import wx
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import (
    AccessibleDialog,
    BoxSizerHelper,
    ButtonHelper,
    BORDER_FOR_DIALOGS,
    SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS,
    launch_gui_thread_safe,
    messageBox,
)
from lib.clientsettings.parser import (
    ClientSettingsFile,
    find_property,
    get_value,
    parse_file,
    serialize_file,
    set_value,
)
from lib.clientsettings.sync import (
    CLIENT_SETTINGS_FILENAME,
    ClientSettingsManager,
)
from lib.clientsettings.cloud import CloudStorageError

logger = logging.getLogger(__name__)
speaker = Auto()


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------

# Fortnite's upgraded mouse sensitivity stores 0.00-0.25 as a float, but the
# in-game UI displays 0-100%. Same linear mapping for the X/Y pair and for
# the targeting/scope sensitivities that use the "upgraded" system.
UPGRADED_SENS_MAX = 0.25


def sens_stored_to_pct(stored: float) -> float:
    if stored is None:
        return 0.0
    return round(float(stored) / UPGRADED_SENS_MAX * 100.0, 1)


def sens_pct_to_stored(pct: float) -> float:
    return round(float(pct) / 100.0 * UPGRADED_SENS_MAX, 6)


REGION_CHOICES = [
    ("NAE", "North America East"),
    ("NAC", "North America Central"),
    ("NAW", "North America West"),
    ("EU", "Europe"),
    ("BR", "Brazil"),
    ("OCE", "Oceania"),
    ("ASIA", "Asia"),
    ("ME", "Middle East"),
]

# Known enum values. For fields like VoiceChatSetting we don't have Epic's
# official enum list, so we offer common values as suggestions but always
# preserve whatever is currently in the file (via an editable ComboBox).
VOICE_CHAT_SETTING_CHOICES = [
    "ESocialCommsPermission::Nobody",
    "ESocialCommsPermission::Friends",
    "ESocialCommsPermission::Teammates",
    "ESocialCommsPermission::Party",
    "ESocialCommsPermission::Everyone",
]

VOICE_CHAT_METHOD_CHOICES = [
    "EFortVoiceChatMethod::OpenMic",
    "EFortVoiceChatMethod::PushToTalk",
    "EFortVoiceChatMethod::Mute",
]

CONTROLLER_PLATFORM_CHOICES = [
    "XboxOne",
    "PS4",
    "PS5",
    "Switch",
    "SteamDeck",
    "Android",
    "iOS",
]


# ---------------------------------------------------------------------------
# Fortnite FKey name mapping
# ---------------------------------------------------------------------------
# When the user presses a key in the capture dialog, we get a wx keycode.
# Fortnite stores keys as UE FKey names like "SpaceBar", "LeftShift",
# "MiddleMouseButton", "NumPadFive", "F1", "W". Map the common ones.

_WX_TO_FORTNITE = {
    wx.WXK_SPACE: "SpaceBar",
    wx.WXK_TAB: "Tab",
    wx.WXK_RETURN: "Enter",
    wx.WXK_NUMPAD_ENTER: "Enter",
    wx.WXK_BACK: "BackSpace",
    wx.WXK_ESCAPE: "Escape",
    wx.WXK_DELETE: "Delete",
    wx.WXK_INSERT: "Insert",
    wx.WXK_HOME: "Home",
    wx.WXK_END: "End",
    wx.WXK_PAGEUP: "PageUp",
    wx.WXK_PAGEDOWN: "PageDown",
    wx.WXK_UP: "Up",
    wx.WXK_DOWN: "Down",
    wx.WXK_LEFT: "Left",
    wx.WXK_RIGHT: "Right",
    wx.WXK_CAPITAL: "CapsLock",
    wx.WXK_NUMLOCK: "NumLock",
    wx.WXK_SCROLL: "ScrollLock",
    wx.WXK_PAUSE: "Pause",

    # Numpad digits
    wx.WXK_NUMPAD0: "NumPadZero",
    wx.WXK_NUMPAD1: "NumPadOne",
    wx.WXK_NUMPAD2: "NumPadTwo",
    wx.WXK_NUMPAD3: "NumPadThree",
    wx.WXK_NUMPAD4: "NumPadFour",
    wx.WXK_NUMPAD5: "NumPadFive",
    wx.WXK_NUMPAD6: "NumPadSix",
    wx.WXK_NUMPAD7: "NumPadSeven",
    wx.WXK_NUMPAD8: "NumPadEight",
    wx.WXK_NUMPAD9: "NumPadNine",
    wx.WXK_ADD: "Add",
    wx.WXK_SUBTRACT: "Subtract",
    wx.WXK_MULTIPLY: "Multiply",
    wx.WXK_DIVIDE: "Divide",
    wx.WXK_DECIMAL: "Decimal",

    # Digit row (number keys)
    ord("0"): "Zero",
    ord("1"): "One",
    ord("2"): "Two",
    ord("3"): "Three",
    ord("4"): "Four",
    ord("5"): "Five",
    ord("6"): "Six",
    ord("7"): "Seven",
    ord("8"): "Eight",
    ord("9"): "Nine",

    # Symbols
    ord("-"): "Hyphen",
    ord("="): "Equals",
    ord("["): "LeftBracket",
    ord("]"): "RightBracket",
    ord("\\"): "Backslash",
    ord(";"): "Semicolon",
    ord("'"): "Apostrophe",
    ord(","): "Comma",
    ord("."): "Period",
    ord("/"): "Slash",
    ord("`"): "Tilde",
}
# F-keys
for _i in range(1, 25):
    _WX_TO_FORTNITE[getattr(wx, f"WXK_F{_i}", -1)] = f"F{_i}"


def wx_key_to_fortnite(key_code: int, raw_key: int = 0) -> str | None:
    """Convert a wxPython key code to Fortnite's FKey name.

    `raw_key` is the wx key code before modifiers; we use it for letters.
    """
    if key_code in _WX_TO_FORTNITE:
        return _WX_TO_FORTNITE[key_code]
    # Letter keys (A-Z come through as uppercase ordinals)
    if ord("A") <= key_code <= ord("Z"):
        return chr(key_code)
    if ord("a") <= key_code <= ord("z"):
        return chr(key_code).upper()
    return None


def capture_mouse_button_fortnite(code: int) -> str | None:
    """wx mouse-button event type code -> Fortnite FKey name."""
    # Using wx.EVT_*_DOWN event type constants; caller passes event.GetEventType().
    if code == wx.wxEVT_LEFT_DOWN:
        return "LeftMouseButton"
    if code == wx.wxEVT_RIGHT_DOWN:
        return "RightMouseButton"
    if code == wx.wxEVT_MIDDLE_DOWN:
        return "MiddleMouseButton"
    if code == wx.wxEVT_AUX1_DOWN:
        return "ThumbMouseButton"
    if code == wx.wxEVT_AUX2_DOWN:
        return "ThumbMouseButton2"
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe(callable_, *args, **kwargs):
    """Run `callable_(*args, **kwargs)`; return (ok, result_or_error)."""
    try:
        return True, callable_(*args, **kwargs)
    except Exception as e:
        logger.exception("clientsettings_gui error")
        return False, e


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------


class ClientSettingsEditorDialog(AccessibleDialog):
    """Main editor dialog. Loads local settings on open."""

    def __init__(self, parent=None):
        super().__init__(parent, title="Client Settings Editor", helpId="ClientSettingsEditor")

        self.SetSize((780, 620))
        self.SetMinSize((640, 520))

        self.manager = ClientSettingsManager()
        self.parsed: Optional[ClientSettingsFile] = None
        self.cloud_info_text: Optional[wx.TextCtrl] = None
        # Remember what we originally populated each control with so we can
        # skip untouched fields on commit (avoids float32-precision drift
        # e.g. 36.287841796875 -> "36.2878" -> 36.2878 on round-trip).
        self._initial_text: dict[int, str] = {}
        self._initial_check: dict[int, bool] = {}
        self._initial_choice: dict[int, int] = {}

        # Download the cloud copy up-front; the GUI is cloud-only so local
        # state is intentionally ignored. Fail soft — setupDialog still
        # runs so the user sees a well-formed (if empty) window plus the
        # explanatory error dialog.
        ok, result = _safe(self.manager.read_cloud)
        if ok:
            self.parsed = result
        else:
            msg = str(result)
            if isinstance(result, CloudStorageError) and "authenticate" in msg.lower():
                hint = ("\n\nOpen the FA11y auth dialog (Alt+Shift+L) "
                        "to sign in to your Epic account, then re-open "
                        "this editor.")
            elif "HTTP 404" in msg:
                hint = ("\n\nYour account doesn't have a cloud "
                        "ClientSettings.Sav yet. Launch Fortnite once and "
                        "let it sync, then re-open this editor.")
            else:
                hint = ""
            wx.CallAfter(
                messageBox,
                message=(
                    f"Could not fetch ClientSettings.Sav from the cloud:\n"
                    f"{msg}{hint}"
                ),
                caption="FA11y — Client Settings",
                style=wx.OK | wx.ICON_ERROR,
                parent=parent,
            )

        self.setupDialog()

    # ---------------------------------------------------------------- layout

    def makeSettings(self, settingsSizer: BoxSizerHelper) -> None:
        self.notebook = wx.Notebook(self)

        self._build_settings_tab(self.notebook)
        self._build_keybinds_tab(self.notebook)
        self._build_cloud_tab(self.notebook)

        settingsSizer.addItem(self.notebook, flag=wx.EXPAND, proportion=1)

        bottom = ButtonHelper(wx.HORIZONTAL)
        self.save_cloud_btn = bottom.addButton(self, label="&Save to Cloud")
        self.save_cloud_btn.Bind(wx.EVT_BUTTON, self.on_save_cloud)

        close_btn = bottom.addButton(self, label="&Close")
        close_btn.Bind(wx.EVT_BUTTON, lambda evt: self.Close())

        settingsSizer.addItem(bottom)

        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

    # --------------------------------------------------------- settings tab

    def _build_settings_tab(self, notebook: wx.Notebook) -> None:
        panel = wx.ScrolledWindow(notebook, style=wx.VSCROLL)
        panel.SetScrollRate(0, 12)
        notebook.AddPage(panel, "Settings")

        outer = wx.BoxSizer(wx.VERTICAL)

        # --- Sensitivity group --------------------------------------------
        sens_box = wx.StaticBox(panel, label="Sensitivity (shown as % — matches the in-game slider)")
        sens_sizer = wx.StaticBoxSizer(sens_box, wx.VERTICAL)

        self.sens_x_slider, self.sens_x_value = self._pct_slider(
            panel, sens_sizer, "Mouse X:",
            sens_stored_to_pct(get_value(self._props, "UpgradedMouseSensitivityX")))
        self.sens_y_slider, self.sens_y_value = self._pct_slider(
            panel, sens_sizer, "Mouse Y:",
            sens_stored_to_pct(get_value(self._props, "UpgradedMouseSensitivityY")))
        outer.Add(sens_sizer, flag=wx.EXPAND | wx.BOTTOM, border=SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)

        # --- Audio group --------------------------------------------------
        audio_box = wx.StaticBox(panel, label="Audio (0–100%)")
        audio_sizer = wx.StaticBoxSizer(audio_box, wx.VERTICAL)

        self.master_slider, self.master_value = self._vol_slider(
            panel, audio_sizer, "Master Volume:",
            _as_float(get_value(self._props, "MasterVolume")))
        self.music_slider, self.music_value = self._vol_slider(
            panel, audio_sizer, "Music Volume:",
            _as_float(get_value(self._props, "MusicVolume")))
        self.chat_slider, self.chat_value = self._vol_slider(
            panel, audio_sizer, "Chat Volume:",
            _as_float(get_value(self._props, "ChatVolume")))
        outer.Add(audio_sizer, flag=wx.EXPAND | wx.BOTTOM, border=SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)

        # --- Region + Voice + Controller ---------------------------------
        pick_box = wx.StaticBox(panel, label="Region, voice chat, controller")
        pick_sizer = wx.StaticBoxSizer(pick_box, wx.VERTICAL)

        # Region: Choice (we're confident on the 8 options)
        self.region_ctrl = self._labeled_choice(
            panel, pick_sizer, "Region:",
            choices=[f"{c[0]} — {c[1]}" for c in REGION_CHOICES],
            values=[c[0] for c in REGION_CHOICES],
            current=(get_value(self._props, "SelectedRegionId") or "NAE"),
        )

        # Voice chat setting — editable combo (preserves unknown values)
        self.voice_setting_ctrl = self._labeled_combo(
            panel, pick_sizer, "Voice chat permission:",
            choices=VOICE_CHAT_SETTING_CHOICES,
            current=get_value(self._props, "VoiceChatSetting") or "",
        )
        # Voice chat method — editable combo
        self.voice_method_ctrl = self._labeled_combo(
            panel, pick_sizer, "Voice chat method:",
            choices=VOICE_CHAT_METHOD_CHOICES,
            current=get_value(self._props, "VoiceChatMethod") or "",
        )
        # Controller platform — editable combo
        self.controller_ctrl = self._labeled_combo(
            panel, pick_sizer, "Controller platform:",
            choices=CONTROLLER_PLATFORM_CHOICES,
            current=get_value(self._props, "ControllerPlatform") or "",
        )
        outer.Add(pick_sizer, flag=wx.EXPAND | wx.BOTTOM, border=SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)

        # --- Toggles ------------------------------------------------------
        toggles_box = wx.StaticBox(panel, label="Gameplay toggles")
        toggles_sizer = wx.StaticBoxSizer(toggles_box, wx.VERTICAL)

        self.toggles: dict[str, wx.CheckBox] = {}
        for key, label in [
            ("bSmartBuildEnabled",                  "Smart Build (auto-rotate building pieces)"),
            ("bUseHoldToSwapPickup",                "Hold to swap pickup"),
            ("bAutoOpenDoorsNonMobile",             "Auto-open doors"),
            ("bAutoPickupWeaponsConsolePC",         "Auto-pickup weapons"),
            ("bSwapFireInputsForDualWieldShotgunSMG", "Swap fire inputs for dual-wield"),
            ("bAutoSortConsumablesToRight",         "Auto-sort consumables to right"),
            ("bNewHitmarkersEnabled",               "New hitmarkers"),
            ("bPlayerOutlinesEnabled",              "Player outlines"),
            ("bDamageFxEnabled",                    "Damage FX"),
            ("bHighQualityFxEnabled",               "High-quality FX"),
            ("bRelevancyZoneVisible",               "Relevancy zone visible"),
            ("bEnableSubtitles",                    "Subtitles"),
            ("bEnableTextToSpeech",                 "Text-to-speech"),
        ]:
            cur = get_value(self._props, key)
            if cur is None:
                continue  # key not present in this file — hide rather than invent
            cb = wx.CheckBox(panel, label=label)
            val = bool(cur)
            cb.SetValue(val)
            self._initial_check[cb.GetId()] = val
            toggles_sizer.Add(cb, flag=wx.ALL, border=3)
            self.toggles[key] = cb
        outer.Add(toggles_sizer, flag=wx.EXPAND)

        panel.SetSizer(outer)
        outer.Fit(panel)

    # --------------------------------------------------------- keybinds tab

    def _build_keybinds_tab(self, notebook: wx.Notebook) -> None:
        panel = wx.Panel(notebook)
        notebook.AddPage(panel, "Keybinds")

        outer = wx.BoxSizer(wx.VERTICAL)

        # sub-game selector
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(panel, label="Sub-game:"), flag=wx.ALIGN_CENTER_VERTICAL)
        row.AddSpacer(10)
        self.sub_game_ctrl = wx.Choice(
            panel,
            choices=["ESubGame::Athena (Battle Royale)",
                     "ESubGame::Campaign (Save the World)",
                     "ESubGame::Invalid (shared)"],
        )
        self.sub_game_ctrl.SetSelection(0)
        self.sub_game_ctrl.Bind(wx.EVT_CHOICE, self._on_subgame_changed)
        row.Add(self.sub_game_ctrl)
        outer.Add(row, flag=wx.EXPAND | wx.ALL, border=4)

        # filter
        row2 = wx.BoxSizer(wx.HORIZONTAL)
        row2.Add(wx.StaticText(panel, label="Filter:"), flag=wx.ALIGN_CENTER_VERTICAL)
        row2.AddSpacer(10)
        self.filter_ctrl = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.filter_ctrl.Bind(wx.EVT_TEXT, lambda _: self._refresh_keybinds())
        row2.Add(self.filter_ctrl, proportion=1, flag=wx.EXPAND)
        self.hide_unbound = wx.CheckBox(panel, label="Hide unbound")
        self.hide_unbound.SetValue(True)
        self.hide_unbound.Bind(wx.EVT_CHECKBOX, lambda _: self._refresh_keybinds())
        row2.AddSpacer(10)
        row2.Add(self.hide_unbound, flag=wx.ALIGN_CENTER_VERTICAL)
        outer.Add(row2, flag=wx.EXPAND | wx.ALL, border=4)

        # list
        self.kb_list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.kb_list.InsertColumn(0, "Action", width=260)
        self.kb_list.InsertColumn(1, "Key 1", width=140)
        self.kb_list.InsertColumn(2, "Key 2", width=140)
        self.kb_list.InsertColumn(3, "Axis?", width=60)
        self.kb_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_edit_keybind)
        outer.Add(self.kb_list, proportion=1, flag=wx.EXPAND | wx.ALL, border=4)

        # edit button
        self.edit_btn = wx.Button(panel, label="&Edit selected binding…")
        self.edit_btn.Bind(wx.EVT_BUTTON, self._on_edit_keybind)
        outer.Add(self.edit_btn, flag=wx.ALL, border=4)

        help_lbl = wx.StaticText(
            panel,
            label=("Double-click a row to edit its key(s). Use UE key names like W, A, S, D, SpaceBar, "
                   "LeftShift, LeftControl, LeftAlt, RightMouseButton, ThumbMouseButton. 'None' unbinds."),
        )
        help_lbl.Wrap(720)
        outer.Add(help_lbl, flag=wx.ALL, border=4)

        panel.SetSizer(outer)
        self._refresh_keybinds()

    def _current_sub_game(self) -> str:
        return ["ESubGame::Athena", "ESubGame::Campaign", "ESubGame::Invalid"][self.sub_game_ctrl.GetSelection()]

    def _on_subgame_changed(self, _evt: wx.CommandEvent) -> None:
        self._refresh_keybinds()

    def _refresh_keybinds(self) -> None:
        self.kb_list.DeleteAllItems()
        if self.parsed is None:
            return
        binds = ClientSettingsManager.get_keybinds(self.parsed, sub_game=self._current_sub_game())
        filt = (self.filter_ctrl.GetValue() or "").lower().strip()
        hide_unbound = self.hide_unbound.GetValue()
        count = 0
        for b in binds:
            if hide_unbound and (b["key1"] in (None, "None")) and (b["key2"] in (None, "None")):
                continue
            if filt and filt not in (b.get("action") or "").lower():
                continue
            idx = self.kb_list.InsertItem(count, b.get("action") or "")
            self.kb_list.SetItem(idx, 1, str(b.get("key1") or ""))
            self.kb_list.SetItem(idx, 2, str(b.get("key2") or ""))
            self.kb_list.SetItem(idx, 3, "yes" if b.get("is_axis") else "")
            count += 1

    def _on_edit_keybind(self, _evt) -> None:
        sel = self.kb_list.GetFirstSelected()
        if sel < 0:
            speaker.speak("No binding selected")
            return
        action = self.kb_list.GetItemText(sel, 0)
        key1 = self.kb_list.GetItemText(sel, 1)
        key2 = self.kb_list.GetItemText(sel, 2)

        dlg = _KeybindEditDialog(self, action=action, key1=key1, key2=key2)
        if dlg.ShowModal() == wx.ID_OK:
            new1, new2 = dlg.get_values()
            hits = ClientSettingsManager.set_keybind(
                self.parsed, action,
                key1=new1, key2=new2,
                sub_game=self._current_sub_game(),
            )
            if hits == 0:
                speaker.speak(f"No binding matched {action}")
            else:
                speaker.speak(f"{action} updated — remember to save")
                self._refresh_keybinds()
        dlg.Destroy()

    # ------------------------------------------------------------- cloud tab

    def _build_cloud_tab(self, notebook: wx.Notebook) -> None:
        panel = wx.Panel(notebook)
        notebook.AddPage(panel, "Cloud")

        outer = wx.BoxSizer(wx.VERTICAL)

        info = wx.StaticText(
            panel,
            label=(
                "The editor reads and writes your ClientSettings.Sav directly "
                "from Epic's cloud storage — the same copy Fortnite syncs on "
                "launch. Local files on this machine are not used.\n\n"
                "Refresh = re-download the cloud file and discard any "
                "unsaved edits in the form."
            ),
        )
        info.Wrap(720)
        outer.Add(info, flag=wx.ALL, border=6)

        self.cloud_info_text = wx.TextCtrl(
            panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
            size=(-1, 260),
        )
        outer.Add(self.cloud_info_text, proportion=1, flag=wx.EXPAND | wx.ALL, border=6)

        btns = ButtonHelper(wx.HORIZONTAL)
        b1 = btns.addButton(panel, label="Refresh cloud &info")
        b1.Bind(wx.EVT_BUTTON, lambda _: self._refresh_cloud_info())

        b2 = btns.addButton(panel, label="&Re-download (discard edits)")
        b2.Bind(wx.EVT_BUTTON, lambda _: self._cloud_action_reload())

        outer.Add(btns.sizer, flag=wx.ALL, border=6)

        panel.SetSizer(outer)
        wx.CallAfter(self._refresh_cloud_info)

    def _log(self, line: str) -> None:
        if self.cloud_info_text is None:
            return
        wx.CallAfter(self.cloud_info_text.AppendText, line + "\n")

    def _refresh_cloud_info(self) -> None:
        self._log("--- refreshing ---")

        def worker():
            try:
                files = self.manager.cloud.list_files()
            except Exception as e:
                self._log(f"ERROR: {e}")
                return
            sav = next(
                (f for f in files if f.unique_filename == CLIENT_SETTINGS_FILENAME),
                None,
            )
            if sav is None:
                self._log("No ClientSettings.Sav on the cloud for this account yet.")
                self._log(
                    "Launch Fortnite once to create the cloud copy, then "
                    "re-open this editor."
                )
                return
            self._log(f"cloud file: {sav.unique_filename}")
            self._log(f"  size:     {sav.length} bytes")
            self._log(f"  uploaded: {sav.uploaded}")
            self._log(f"  hash:     {sav.hash}")

        threading.Thread(target=worker, daemon=True).start()

    def _cloud_action_reload(self) -> None:
        """Discard in-memory edits and re-download the cloud copy."""
        self._log("--- reloading from cloud ---")

        def worker():
            ok, result = _safe(self.manager.read_cloud)
            if not ok:
                self._log(f"RELOAD ERROR: {result}")
                wx.CallAfter(speaker.speak, "Reload failed")
                return
            self.parsed = result
            wx.CallAfter(self._reload_form_from_parsed)
            wx.CallAfter(speaker.speak, "Reloaded from cloud")
            self._log("Cloud copy re-parsed and form refreshed.")

        threading.Thread(target=worker, daemon=True).start()

    # ----------------------------------------------------------------- save

    def on_save_cloud(self, _evt: wx.CommandEvent) -> None:
        """Apply UI edits to the in-memory buffer, serialize, upload to cloud."""
        if self.parsed is None:
            messageBox(
                "No cloud settings loaded — cannot save.",
                style=wx.OK | wx.ICON_ERROR, parent=self,
            )
            return
        ok, err = _safe(self._commit_form_to_parsed)
        if not ok:
            messageBox(
                f"Validation error:\n{err}",
                style=wx.OK | wx.ICON_ERROR, parent=self,
            )
            return

        data = serialize_file(self.parsed)

        def worker():
            try:
                self.manager.cloud.upload(CLIENT_SETTINGS_FILENAME, data)
            except Exception as e:
                self._log(f"SAVE ERROR: {e}")
                wx.CallAfter(
                    messageBox,
                    message=f"Upload to cloud failed:\n{e}",
                    caption="FA11y — Client Settings",
                    style=wx.OK | wx.ICON_ERROR, parent=self,
                )
                wx.CallAfter(speaker.speak, "Save failed")
                return
            self._log(f"Uploaded {len(data)} bytes to cloud.")
            wx.CallAfter(speaker.speak, "Saved to cloud")
            wx.CallAfter(self._refresh_cloud_info)

        threading.Thread(target=worker, daemon=True).start()

    # -------------------------------------------------------------- plumbing

    @property
    def _props(self) -> list:
        return self.parsed.properties if self.parsed is not None else []

    def _labeled_float(self, parent, parent_sizer, label, current) -> wx.TextCtrl:
        ctrl = _add_labeled_float(parent, parent_sizer, label, current)
        self._initial_text[ctrl.GetId()] = ctrl.GetValue()
        return ctrl

    def _pct_slider(self, parent, parent_sizer, label, current_pct) -> tuple[wx.Slider, wx.StaticText]:
        """0-100 % slider with live numeric label."""
        return self._slider(parent, parent_sizer, label, current_pct, lo=0, hi=100, fmt="{:.0f}%")

    def _vol_slider(self, parent, parent_sizer, label, current_0_1) -> tuple[wx.Slider, wx.StaticText]:
        """0.0-1.0 volume slider shown as 0-100% internally."""
        return self._slider(parent, parent_sizer, label, current_0_1 * 100.0, lo=0, hi=100, fmt="{:.0f}%")

    def _slider(self, parent, parent_sizer, label, current, lo, hi, fmt):
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(parent, label=label, size=(180, -1)), flag=wx.ALIGN_CENTER_VERTICAL)

        initial = max(lo, min(hi, int(round(float(current or 0)))))
        slider = wx.Slider(parent, value=initial, minValue=lo, maxValue=hi,
                           style=wx.SL_HORIZONTAL, size=(240, -1))
        value_label = wx.StaticText(parent, label=fmt.format(slider.GetValue()), size=(64, -1))

        def _on_scroll(evt):
            value_label.SetLabel(fmt.format(slider.GetValue()))
            evt.Skip()
        slider.Bind(wx.EVT_SLIDER, _on_scroll)

        row.Add(slider, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL)
        row.AddSpacer(6)
        row.Add(value_label, flag=wx.ALIGN_CENTER_VERTICAL)
        parent_sizer.Add(row, flag=wx.EXPAND | wx.ALL, border=4)

        self._initial_slider_value = getattr(self, "_initial_slider_value", {})
        self._initial_slider_value[slider.GetId()] = initial
        return slider, value_label

    def _labeled_choice(self, parent, parent_sizer, label, choices, values, current) -> wx.Choice:
        """Labeled Choice where `values[i]` is the stored value for display `choices[i]`."""
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(parent, label=label, size=(180, -1)), flag=wx.ALIGN_CENTER_VERTICAL)
        ctrl = wx.Choice(parent, choices=choices)
        try:
            idx = values.index(current)
        except ValueError:
            idx = 0
        ctrl.SetSelection(idx)
        ctrl._fa11y_values = values  # attach for commit
        self._initial_choice[ctrl.GetId()] = idx
        row.Add(ctrl, proportion=1)
        parent_sizer.Add(row, flag=wx.EXPAND | wx.ALL, border=4)
        return ctrl

    def _labeled_combo(self, parent, parent_sizer, label, choices, current) -> wx.ComboBox:
        """Editable ComboBox — preserves unknown current values (they go in the text)."""
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(parent, label=label, size=(180, -1)), flag=wx.ALIGN_CENTER_VERTICAL)
        ctrl = wx.ComboBox(parent, value=str(current or ""), choices=list(choices),
                           style=wx.CB_DROPDOWN)  # editable; not CB_READONLY
        self._initial_text[ctrl.GetId()] = ctrl.GetValue()
        row.Add(ctrl, proportion=1, flag=wx.EXPAND)
        parent_sizer.Add(row, flag=wx.EXPAND | wx.ALL, border=4)
        return ctrl

    def _text_changed(self, ctrl) -> bool:
        """True if a TextCtrl or ComboBox value differs from what we loaded."""
        return ctrl.GetValue() != self._initial_text.get(ctrl.GetId(), "")

    def _check_changed(self, cb: wx.CheckBox) -> bool:
        return cb.GetValue() != self._initial_check.get(cb.GetId(), cb.GetValue())

    def _choice_changed(self, ch: wx.Choice) -> bool:
        return ch.GetSelection() != self._initial_choice.get(ch.GetId(), ch.GetSelection())

    def _slider_changed(self, sl: wx.Slider) -> bool:
        initial = getattr(self, "_initial_slider_value", {}).get(sl.GetId(), sl.GetValue())
        return sl.GetValue() != initial

    def _commit_form_to_parsed(self) -> None:
        """Read UI controls and mutate self.parsed in place.

        Only writes fields the user actually modified, so unchanged values
        keep their original float32 bit pattern (avoids precision drift from
        the display round-trip).
        """
        if self.parsed is None:
            raise RuntimeError("no file loaded")

        # Sensitivity sliders (percent -> stored 0.0-0.25)
        if self._slider_changed(self.sens_x_slider):
            set_value(self._props, "UpgradedMouseSensitivityX",
                      sens_pct_to_stored(self.sens_x_slider.GetValue()))
        if self._slider_changed(self.sens_y_slider):
            set_value(self._props, "UpgradedMouseSensitivityY",
                      sens_pct_to_stored(self.sens_y_slider.GetValue()))

        # Audio sliders (0-100 -> stored 0.0-1.0)
        for slider, key in ((self.master_slider, "MasterVolume"),
                            (self.music_slider, "MusicVolume"),
                            (self.chat_slider, "ChatVolume")):
            if self._slider_changed(slider):
                set_value(self._props, key, slider.GetValue() / 100.0)

        # Region (Choice)
        if self._choice_changed(self.region_ctrl):
            values = getattr(self.region_ctrl, "_fa11y_values", None)
            sel = self.region_ctrl.GetSelection()
            if values and 0 <= sel < len(values):
                set_value(self._props, "SelectedRegionId", values[sel])

        # Voice chat + controller (editable ComboBoxes)
        for ctrl, key in ((self.voice_setting_ctrl, "VoiceChatSetting"),
                          (self.voice_method_ctrl, "VoiceChatMethod"),
                          (self.controller_ctrl, "ControllerPlatform")):
            if self._text_changed(ctrl):
                val = ctrl.GetValue().strip()
                if val:
                    set_value(self._props, key, val)

        # Toggles
        for key, cb in self.toggles.items():
            if self._check_changed(cb):
                set_value(self._props, key, bool(cb.GetValue()))

    def _reload_form_from_parsed(self) -> None:
        if self.parsed is None:
            return

        def set_text(ctrl, text: str) -> None:
            ctrl.SetValue(text)
            self._initial_text[ctrl.GetId()] = text

        def set_slider_pct(slider, label_ctrl, pct: float, fmt="{:.0f}%") -> None:
            v = max(0, min(100, int(round(pct))))
            slider.SetValue(v)
            label_ctrl.SetLabel(fmt.format(v))
            self._initial_slider_value[slider.GetId()] = v

        set_slider_pct(self.sens_x_slider, self.sens_x_value,
                       sens_stored_to_pct(get_value(self._props, "UpgradedMouseSensitivityX")))
        set_slider_pct(self.sens_y_slider, self.sens_y_value,
                       sens_stored_to_pct(get_value(self._props, "UpgradedMouseSensitivityY")))
        set_slider_pct(self.master_slider, self.master_value,
                       _as_float(get_value(self._props, "MasterVolume")) * 100)
        set_slider_pct(self.music_slider, self.music_value,
                       _as_float(get_value(self._props, "MusicVolume")) * 100)
        set_slider_pct(self.chat_slider, self.chat_value,
                       _as_float(get_value(self._props, "ChatVolume")) * 100)

        # Region Choice
        current_region = get_value(self._props, "SelectedRegionId") or "NAE"
        try:
            idx = [c[0] for c in REGION_CHOICES].index(current_region)
            self.region_ctrl.SetSelection(idx)
            self._initial_choice[self.region_ctrl.GetId()] = idx
        except ValueError:
            pass

        # ComboBoxes
        for ctrl, key in ((self.voice_setting_ctrl, "VoiceChatSetting"),
                          (self.voice_method_ctrl, "VoiceChatMethod"),
                          (self.controller_ctrl, "ControllerPlatform")):
            set_text(ctrl, get_value(self._props, key) or "")

        # Toggles
        for key, cb in self.toggles.items():
            val = bool(get_value(self._props, key))
            cb.SetValue(val)
            self._initial_check[cb.GetId()] = val

        self._refresh_keybinds()

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close()
            return
        event.Skip()


# ---------------------------------------------------------------------------
# Keybind edit dialog
# ---------------------------------------------------------------------------


class _KeybindEditDialog(wx.Dialog):
    """Press-to-capture binding editor.

    Matches FA11y's existing config-GUI keybind button flow: user clicks the
    slot they want to rebind ("Press a key..."), then physically presses the
    key / mouse button they want. Escape cancels that slot's capture.
    Delete / Backspace clears the slot (sets to "None").
    """

    def __init__(self, parent, *, action: str, key1: str, key2: str):
        super().__init__(parent, title=f"Edit binding — {action}")
        self.action = action
        self._capturing_slot: int | None = None  # 1 or 2 while capturing

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label=f"Action: {action}"),
                  flag=wx.ALL, border=8)
        sizer.Add(wx.StaticText(
            self,
            label=("Click a slot button, then press the key you want.\n"
                   "Keyboard keys, all five mouse buttons (left, right, middle, "
                   "back=4, forward=5) and the scroll wheel (up/down) are all "
                   "accepted.\n"
                   "Escape = cancel this capture. Delete / Backspace = unbind."),
        ), flag=wx.ALL, border=8)

        g = wx.FlexGridSizer(cols=2, hgap=10, vgap=8)
        g.Add(wx.StaticText(self, label="Key 1 (primary):"), flag=wx.ALIGN_CENTER_VERTICAL)
        self.k1_btn = wx.Button(self, label=key1 or "None")
        self.k1_btn.Bind(wx.EVT_BUTTON, lambda _: self._start_capture(1))
        g.Add(self.k1_btn, flag=wx.EXPAND)

        g.Add(wx.StaticText(self, label="Key 2 (secondary):"), flag=wx.ALIGN_CENTER_VERTICAL)
        self.k2_btn = wx.Button(self, label=key2 or "None")
        self.k2_btn.Bind(wx.EVT_BUTTON, lambda _: self._start_capture(2))
        g.Add(self.k2_btn, flag=wx.EXPAND)
        g.AddGrowableCol(1)
        sizer.Add(g, flag=wx.EXPAND | wx.ALL, border=8)

        btn_sizer = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btn_sizer, flag=wx.EXPAND | wx.ALL, border=8)

        self.SetSizer(sizer)
        self.Fit()

        # Key / mouse capture bindings at the dialog level so they fire
        # regardless of which child has focus while capturing.
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        # One catch-all for mouse events — some wx builds don't expose
        # EVT_AUX1_DOWN / EVT_AUX2_DOWN as binder names.
        self.Bind(wx.EVT_MOUSE_EVENTS, self._on_mouse_event)
        # Scroll wheel is a separate event type.
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_mouse_wheel)

    # ------------------------------------------------------------------

    def _slot_btn(self, slot: int) -> wx.Button:
        return self.k1_btn if slot == 1 else self.k2_btn

    def _start_capture(self, slot: int) -> None:
        self._capturing_slot = slot
        btn = self._slot_btn(slot)
        btn._pre_capture_label = btn.GetLabel()
        btn.SetLabel(f"Press a key for slot {slot}… (Esc cancels, Del unbinds)")
        speaker.speak(f"Press a key for slot {slot}")

    def _finish_capture(self, value: str | None) -> None:
        if self._capturing_slot is None:
            return
        btn = self._slot_btn(self._capturing_slot)
        if value is not None:
            btn.SetLabel(value)
            speaker.speak(f"Bound to {value}")
        else:
            # restore original label
            btn.SetLabel(getattr(btn, "_pre_capture_label", "None"))
        self._capturing_slot = None

    def _on_char_hook(self, evt: wx.KeyEvent) -> None:
        if self._capturing_slot is None:
            evt.Skip()
            return
        code = evt.GetKeyCode()
        if code == wx.WXK_ESCAPE:
            self._finish_capture(None)
            return
        if code in (wx.WXK_DELETE, wx.WXK_BACK):
            self._finish_capture("None")
            return
        # Ignore bare modifier keydowns — they'd be useless as standalone binds
        if code in (wx.WXK_SHIFT, wx.WXK_CONTROL, wx.WXK_ALT,
                    wx.WXK_RAW_CONTROL, wx.WXK_WINDOWS_LEFT, wx.WXK_WINDOWS_RIGHT):
            # But Fortnite does support LeftShift etc. as standalone keys, so
            # use GetRawKeyCode / position to decide left vs right where we can.
            # wx doesn't distinguish left/right reliably here; treat bare
            # modifier as its "Left" variant by default.
            name = {
                wx.WXK_SHIFT: "LeftShift",
                wx.WXK_CONTROL: "LeftControl",
                wx.WXK_ALT: "LeftAlt",
                wx.WXK_RAW_CONTROL: "LeftControl",
                wx.WXK_WINDOWS_LEFT: "LeftCommand",
                wx.WXK_WINDOWS_RIGHT: "RightCommand",
            }.get(code)
            if name:
                self._finish_capture(name)
                return
            evt.Skip()
            return
        name = wx_key_to_fortnite(code)
        if name is None:
            speaker.speak("Unsupported key — try another")
            return
        self._finish_capture(name)

    def _on_mouse_event(self, evt: wx.MouseEvent) -> None:
        if self._capturing_slot is None:
            evt.Skip()
            return
        # Only react on the *_DOWN phase. Up/motion/etc. skip.
        # Mouse button numbering (matches Windows / most gaming mice):
        #   Button 1 = Left,  Button 2 = Right,       Button 3 = Middle,
        #   Button 4 = Back (Aux1),  Button 5 = Forward (Aux2).
        if evt.LeftDown():
            self._finish_capture("LeftMouseButton"); return
        if evt.RightDown():
            self._finish_capture("RightMouseButton"); return
        if evt.MiddleDown():
            self._finish_capture("MiddleMouseButton"); return
        if hasattr(evt, "Aux1Down") and evt.Aux1Down():
            self._finish_capture("ThumbMouseButton"); return
        if hasattr(evt, "Aux2Down") and evt.Aux2Down():
            self._finish_capture("ThumbMouseButton2"); return
        evt.Skip()

    def _on_mouse_wheel(self, evt: wx.MouseEvent) -> None:
        if self._capturing_slot is None:
            evt.Skip()
            return
        rot = evt.GetWheelRotation()
        if rot > 0:
            self._finish_capture("MouseScrollUp")
        elif rot < 0:
            self._finish_capture("MouseScrollDown")
        else:
            evt.Skip()

    def get_values(self) -> tuple[str | None, str | None]:
        v1 = self.k1_btn.GetLabel().strip() or None
        v2 = self.k2_btn.GetLabel().strip() or None
        if v1 and v1.lower() == "none":
            v1 = "None"
        if v2 and v2.lower() == "none":
            v2 = "None"
        # Sanitize accidental "Press a key..." prompt text if user clicks OK mid-capture
        for v in (v1, v2):
            pass
        if v1 and v1.startswith("Press a key"):
            v1 = None
        if v2 and v2.startswith("Press a key"):
            v2 = None
        return v1, v2


# ---------------------------------------------------------------------------
# Small helpers for controls
# ---------------------------------------------------------------------------


def _add_labeled_float(parent: wx.Window, parent_sizer: wx.Sizer,
                       label: str, current: float) -> wx.TextCtrl:
    row = wx.BoxSizer(wx.HORIZONTAL)
    row.Add(wx.StaticText(parent, label=label, size=(200, -1)),
            flag=wx.ALIGN_CENTER_VERTICAL)
    ctrl = wx.TextCtrl(parent, value=_fmt_float(current), size=(120, -1),
                       style=wx.TE_PROCESS_ENTER)
    row.Add(ctrl)
    parent_sizer.Add(row, flag=wx.ALL, border=4)
    return ctrl


def _read_float_ctrl(ctrl: wx.TextCtrl, name: str) -> float:
    raw = (ctrl.GetValue() or "").strip()
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"{name}: expected a number, got {raw!r}")


def _clamp(v: float, lo: float, hi: float, name: str) -> None:
    if not (lo <= v <= hi):
        raise ValueError(f"{name}: value {v} outside range [{lo}, {hi}]")


def _as_float(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _fmt_float(v: float) -> str:
    if v is None:
        return ""
    if float(v).is_integer():
        return str(int(v))
    return f"{v:g}"


# ---------------------------------------------------------------------------
# Public launcher
# ---------------------------------------------------------------------------


def launch_clientsettings_editor() -> None:
    """Create and show the dialog on the main thread."""
    def _do_launch():
        app = wx.GetApp()
        if app is None:
            speaker.speak("GUI unavailable")
            return
        dlg = ClientSettingsEditorDialog(None)
        dlg.ShowModal()
        dlg.Destroy()

    launch_gui_thread_safe(_do_launch)
