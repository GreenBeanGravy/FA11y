"""First-run setup wizard."""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional

import wx
from accessible_output2.outputs.auto import Auto

from lib.app import state
from lib.guis.gui_utilities import (
    AccessibleDialog,
    BoxSizerHelper,
    BORDER_FOR_DIALOGS,
    SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS,
    ensure_window_focus_and_center_mouse,
    messageBox,
)
from lib.utilities.spatial_audio import SpatialAudio
from lib.utilities.utilities import (
    Config,
    read_config,
    save_config,
    get_config_value,
)

logger = logging.getLogger(__name__)
speaker = Auto()


# ---------------------------------------------------------------------------
# Page base
# ---------------------------------------------------------------------------


class WizardPage(wx.Panel):
    """One step of the wizard.

    Subclasses populate ``content_sizer`` with the controls they need
    and override ``on_enter()`` / ``collect()``. ``collect()`` returns
    a dict of (section, key) -> value pairs that will be written to
    config when the wizard finishes.
    """

    title: str = ""
    intro: str = ""

    def __init__(self, parent):
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        outer = wx.BoxSizer(wx.VERTICAL)

        title_label = wx.StaticText(self, label=self.title)
        font = title_label.GetFont()
        font.PointSize += 4
        font = font.Bold()
        title_label.SetFont(font)
        outer.Add(title_label, flag=wx.ALL, border=BORDER_FOR_DIALOGS)

        if self.intro:
            intro_label = wx.StaticText(self, label=self.intro)
            intro_label.Wrap(520)
            outer.Add(intro_label, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=BORDER_FOR_DIALOGS)

        self.content_sizer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self.content_sizer, proportion=1, flag=wx.EXPAND | wx.ALL, border=BORDER_FOR_DIALOGS)

        self.SetSizer(outer)

    def on_enter(self) -> None:
        """Called every time this page becomes visible. Speak the page."""
        announcement = self.title
        if self.intro:
            announcement = f"{self.title}. {self.intro}"
        speaker.speak(announcement)

    def collect(self) -> Dict[tuple, Any]:
        """Return ``{(section, key): value}`` to write to config on finish."""
        return {}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


class WelcomePage(WizardPage):
    title = "Welcome to FA11y"
    intro = (
        "FA11y is a screen-reader-friendly companion for Fortnite. "
        "This setup takes about a minute and walks you through audio, "
        "speech, and mouse settings. Press Tab to move between controls "
        "and Enter or click Next to continue. You can press Escape at any "
        "time to skip the wizard."
    )


class SpeechPage(WizardPage):
    title = "Speech preferences"
    intro = (
        "FA11y narrates events through your screen reader. Choose how "
        "talkative you want it to be. You can change this later in the "
        "configuration menu."
    )

    def _build(self) -> None:
        super()._build()
        self.choice = wx.RadioBox(
            self,
            label="Speech style",
            choices=[
                "Verbose — full sentences, more context (recommended for new users)",
                "Simplified — shorter, terser announcements",
            ],
            majorDimension=1,
            style=wx.RA_SPECIFY_COLS,
        )
        self.choice.SetSelection(0)
        self.content_sizer.Add(self.choice, flag=wx.EXPAND | wx.ALL, border=5)
        self.Layout()

    def collect(self) -> Dict[tuple, Any]:
        simplified = self.choice.GetSelection() == 1
        return {("Toggles", "SimplifySpeechOutput"): "true" if simplified else "false"}


class AudioTestPage(WizardPage):
    title = "Audio check"
    intro = (
        "FA11y plays spatial audio cues for storms, points of interest, "
        "and dynamic objects. Use the Test button to play a sound at the "
        "current master volume — adjust the slider until it's comfortable, "
        "then continue."
    )

    def _build(self) -> None:
        super()._build()

        row = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(self, label="Master volume:")
        row.Add(label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=10)

        self.volume_spin = wx.SpinCtrl(self, min=0, max=100, initial=100)
        self.volume_spin.SetToolTip("Master volume, 0 to 100 percent.")
        row.Add(self.volume_spin, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=10)

        self.test_btn = wx.Button(self, label="&Test sound")
        self.test_btn.Bind(wx.EVT_BUTTON, self._on_test)
        row.Add(self.test_btn, flag=wx.ALIGN_CENTER_VERTICAL)

        self.content_sizer.Add(row, flag=wx.ALL, border=5)

        self._audio: Optional[SpatialAudio] = None
        self.Layout()

    def _on_test(self, _event):
        try:
            sound_path = os.path.join("assets", "sounds", "poi.ogg")
            if not os.path.exists(sound_path):
                speaker.speak("Test sound file is missing.")
                return
            if self._audio is None:
                self._audio = SpatialAudio(sound_path)
            volume = max(0.0, min(self.volume_spin.GetValue() / 100.0, 1.0))
            self._audio.set_master_volume(volume)
            self._audio.set_individual_volume(1.0)
            self._audio.play_audio(left_weight=0.5, right_weight=0.5, volume=1.0)
        except Exception as e:
            logger.error(f"Wizard audio test failed: {e}")
            speaker.speak("Audio test failed.")

    def cleanup(self) -> None:
        if self._audio is not None:
            try:
                self._audio.cleanup()
            except Exception:
                pass
            self._audio = None

    def collect(self) -> Dict[tuple, Any]:
        return {("Audio", "MasterVolume"): str(self.volume_spin.GetValue() / 100.0)}


class MousePage(WizardPage):
    title = "Mouse setup"
    intro = (
        "FA11y reads your mouse DPI to compute correct in-game sensitivity "
        "for its turn and look keys. Enter the DPI your mouse is set to. "
        "If you don't know, 800 is a safe default — you can fine-tune later."
    )

    def _build(self) -> None:
        super()._build()
        row = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(self, label="Mouse DPI:")
        row.Add(label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=10)

        self.dpi_spin = wx.SpinCtrl(self, min=100, max=32000, initial=800)
        self.dpi_spin.SetToolTip("Your mouse's actual DPI. Check your mouse software if unsure.")
        row.Add(self.dpi_spin, flag=wx.ALIGN_CENTER_VERTICAL)

        self.content_sizer.Add(row, flag=wx.ALL, border=5)

        self.passthrough_cb = wx.CheckBox(
            self, label="Enable mouse passthrough (recommended)"
        )
        self.passthrough_cb.SetValue(True)
        self.passthrough_cb.SetToolTip(
            "Routes your mouse through the FakerInput driver so FA11y's "
            "turn / look keys produce smooth in-game movement."
        )
        self.content_sizer.Add(self.passthrough_cb, flag=wx.ALL, border=5)
        self.Layout()

    def collect(self) -> Dict[tuple, Any]:
        return {
            ("Values", "MousePassthroughDPI"): str(self.dpi_spin.GetValue()),
            ("Toggles", "MousePassthrough"): "true" if self.passthrough_cb.GetValue() else "false",
        }


class FinishPage(WizardPage):
    title = "All set"
    intro = (
        "Setup is complete. Press Finish to save your choices and start "
        "FA11y. You can re-run this wizard or change any setting later "
        "from the configuration menu, F9 by default."
    )


# ---------------------------------------------------------------------------
# Wizard dialog
# ---------------------------------------------------------------------------


class WelcomeWizard(AccessibleDialog):
    """Multi-page first-run setup wizard."""

    def __init__(self, parent=None):
        super().__init__(parent, title="FA11y Setup Wizard", helpId="WelcomeWizard")

        self._pages: List[WizardPage] = []
        self._page_index: int = 0
        self.completed: bool = False
        self.skipped: bool = False

        self.setupDialog()
        self.SetSize((620, 460))
        self.SetMinSize((520, 380))
        self.CentreOnScreen()

    # ----- dialog construction -----

    def makeSettings(self, sizer: BoxSizerHelper) -> None:
        # Stack of pages — only one is visible at a time.
        self._page_container = wx.Panel(self)
        self._page_sizer = wx.BoxSizer(wx.VERTICAL)
        self._page_container.SetSizer(self._page_sizer)
        sizer.addItem(self._page_container, flag=wx.EXPAND, proportion=1)

        # Build pages.
        for page_cls in (WelcomePage, SpeechPage, AudioTestPage, MousePage, FinishPage):
            page = page_cls(self._page_container)
            page.Hide()
            self._pages.append(page)
            self._page_sizer.Add(page, proportion=1, flag=wx.EXPAND)

        # Navigation row.
        nav = wx.BoxSizer(wx.HORIZONTAL)

        self._skip_btn = wx.Button(self, label="S&kip wizard")
        self._skip_btn.SetToolTip("Skip the wizard and use defaults. You can re-run it later.")
        self._skip_btn.Bind(wx.EVT_BUTTON, self._on_skip)
        nav.Add(self._skip_btn)

        nav.AddStretchSpacer()

        self._back_btn = wx.Button(self, label="< &Back")
        self._back_btn.Bind(wx.EVT_BUTTON, self._on_back)
        nav.Add(self._back_btn, flag=wx.RIGHT, border=5)

        self._next_btn = wx.Button(self, label="&Next >")
        self._next_btn.Bind(wx.EVT_BUTTON, self._on_next)
        # Make Enter / default button activation hit Next.
        self._next_btn.SetDefault()
        nav.Add(self._next_btn)

        sizer.addItem(nav, flag=wx.EXPAND | wx.TOP, proportion=0)

        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        # Show the first page.
        wx.CallAfter(self._show_page, 0)

    # ----- page navigation -----

    def _show_page(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._pages):
            return
        for i, page in enumerate(self._pages):
            page.Show(i == idx)
        self._page_index = idx
        self._page_container.Layout()

        # Button labels track position.
        self._back_btn.Enable(idx > 0)
        if idx == len(self._pages) - 1:
            self._next_btn.SetLabel("&Finish")
        else:
            self._next_btn.SetLabel("&Next >")
        self._next_btn.SetDefault()

        page = self._pages[idx]
        wx.CallAfter(page.SetFocus)
        try:
            page.on_enter()
        except Exception as e:
            logger.debug(f"Wizard page on_enter failed: {e}")

    def _on_back(self, _event):
        if self._page_index > 0:
            self._show_page(self._page_index - 1)

    def _on_next(self, _event):
        if self._page_index < len(self._pages) - 1:
            self._show_page(self._page_index + 1)
        else:
            self._finish()

    def _on_skip(self, _event):
        confirm = messageBox(
            "Skip the setup wizard?\n\nFA11y will start with default settings. "
            "You can re-run the wizard or adjust settings later from the "
            "configuration menu.",
            "Skip wizard",
            wx.YES_NO | wx.ICON_QUESTION,
            self,
        )
        if confirm == wx.YES:
            self.skipped = True
            self._mark_setup_complete()
            self._cleanup_pages()
            self.EndModal(wx.ID_CANCEL)

    def _on_char_hook(self, event):
        key_code = event.GetKeyCode()
        if key_code == wx.WXK_ESCAPE:
            self._on_skip(event)
            return
        event.Skip()

    def _on_close(self, _event):
        self.skipped = True
        self._mark_setup_complete()
        self._cleanup_pages()
        self.EndModal(wx.ID_CANCEL)

    def _mark_setup_complete(self) -> None:
        """Flip ``FirstRunComplete`` so the wizard doesn't reopen."""
        try:
            config = read_config()
            if not config.has_section("Setup"):
                config.add_section("Setup")
            config.set(
                "Setup",
                "FirstRunComplete",
                'true "Set to true after the first-run setup wizard finishes. '
                'While false, FA11y launches the wizard before normal startup."',
            )
            save_config(config)
        except Exception as e:
            logger.warning(f"_mark_setup_complete failed: {e}")

    # ----- finish -----

    def _finish(self) -> None:
        """Collect every page's settings and write them to config."""
        try:
            config = read_config()
            applied: Dict[str, Dict[str, str]] = {}
            for page in self._pages:
                try:
                    for (section, key), value in page.collect().items():
                        if not config.has_section(section):
                            config.add_section(section)
                        # Preserve existing description.
                        existing = config.get(section, key, fallback="") if config.has_option(section, key) else ""
                        _, description = self._extract_description(existing)
                        if description:
                            config.set(section, key, f'{value} "{description}"')
                        else:
                            config.set(section, key, str(value))
                        applied.setdefault(section, {})[key] = str(value)
                except Exception as e:
                    logger.error(f"Wizard page {type(page).__name__} collect failed: {e}")

            # Mark setup complete so we don't run again.
            if not config.has_section("Setup"):
                config.add_section("Setup")
            config.set(
                "Setup",
                "FirstRunComplete",
                'true "Set to true after the first-run setup wizard finishes. '
                'While false, FA11y launches the wizard before normal startup."',
            )

            if not save_config(config):
                logger.error("Wizard finish: save_config returned False")
                speaker.speak("Failed to save setup. Please try again.")
                return

            self.completed = True
            speaker.speak("Setup complete. Starting FA11y.")
            logger.info(f"First-run wizard applied: {applied}")
        except Exception as e:
            logger.exception("Wizard finish failed")
            speaker.speak(f"Setup failed: {e}")
            return
        finally:
            self._cleanup_pages()

        self.EndModal(wx.ID_OK)

    @staticmethod
    def _extract_description(value_string: str) -> tuple:
        s = value_string.strip()
        if '"' in s:
            quote_pos = s.find('"')
            value = s[:quote_pos].strip()
            description = s[quote_pos + 1:]
            if description.endswith('"'):
                description = description[:-1]
            return value, description
        return s, ""

    def _cleanup_pages(self) -> None:
        for page in self._pages:
            cleanup = getattr(page, "cleanup", None)
            if callable(cleanup):
                try:
                    cleanup()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def is_first_run() -> bool:
    """Return True if the setup wizard hasn't been completed yet."""
    try:
        config = read_config()
        # Query [Setup] directly — get_config_value only scans
        # Toggles/Values/Audio/GameObjects/Keybinds/POI/SETTINGS/SCRIPT
        # KEYBINDS, so it can't see [Setup] at all.
        if config.has_section("Setup") and config.has_option("Setup", "FirstRunComplete"):
            raw = config.get("Setup", "FirstRunComplete")
            value = raw.split('"')[0].strip()
            return value.lower() not in ("true", "yes", "1", "on")
        return True  # No [Setup] yet → never completed.
    except Exception as e:
        logger.warning(f"is_first_run check failed: {e}")
        return False  # Fail closed — don't pester the user on a flaky read.


def run_welcome_wizard() -> bool:
    """Show the wizard modally. Returns True if completed, False if skipped.

    While the wizard is open, ``state.wizard_open`` is set so the FA11y
    key listener is muted — no in-game keybinds fire during setup.
    """
    state.wizard_open.set()
    try:
        app = wx.GetApp()
        if app is None:
            app = wx.App(False)

        dlg = WelcomeWizard(None)
        try:
            ensure_window_focus_and_center_mouse(dlg)
            dlg.ShowModal()
            return bool(dlg.completed)
        finally:
            dlg.Destroy()
    except Exception as e:
        logger.exception("run_welcome_wizard failed")
        return False
    finally:
        state.wizard_open.clear()
