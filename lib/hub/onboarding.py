"""First-run setup, shown inside the hub window.

Steps: welcome, Epic sign-in, Fortnite, startup options, speech, audio,
mouse, done. Settings are written to the config when the user finishes
or skips; the Fortnite choice (take over an Epic Games Launcher install,
or sync with it) runs on the Fortnite page afterwards so its progress
bar is visible.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List, Optional

import wx
from lib.hub.controls import StyledButton

from lib.app import state
from lib.guis.welcome_wizard import AudioTestPage, MousePage, SpeechPage, WizardPage
from lib.hub import settings, sounds, theme
from lib.hub.widgets import button, label

logger = logging.getLogger(__name__)

FIRST_RUN_DESCRIPTION = ('Set to true after the first-run setup finishes. '
                         'While false, FA11y shows setup when it starts.')


class WelcomeStep(WizardPage):
    title = "Welcome to FA11y"
    intro = ("FA11y makes Fortnite playable with a screen reader. This short setup signs you in, "
             "finds Fortnite, and sets a few preferences. Press Tab to move between controls, "
             "and Next to continue. You can skip setup at any time.")


class SignInStep(WizardPage):
    title = "Sign in to Epic Games"
    intro = ("Your Epic account is used for your locker, friends and party, quests, and for "
             "downloading and updating Fortnite. You can also sign in later on the Epic account page.")

    def _build(self) -> None:
        super()._build()
        self.status = wx.StaticText(self, label="")
        self.signin_button = StyledButton(self, label="&Sign in", variant="primary")
        self.signin_button.Bind(wx.EVT_BUTTON, self._sign_in)
        self.content_sizer.Add(self.status, flag=wx.ALL, border=5)
        self.content_sizer.Add(self.signin_button, flag=wx.ALL, border=5)

    def on_enter(self) -> None:
        self._refresh()
        super().on_enter()

    def _refresh(self) -> None:
        from lib.utilities.epic_auth import get_epic_auth_instance
        auth = get_epic_auth_instance()
        if auth and auth.access_token and auth.is_valid:
            self.status.SetLabel(f"Signed in as {auth.display_name}.")
            self.signin_button.SetLabel("&Sign in with a different account")
        else:
            self.status.SetLabel("Not signed in.")
            self.signin_button.SetLabel("&Sign in")
        self.Layout()

    def _sign_in(self, _event) -> None:
        from lib.app.auth_actions import on_auth_success
        from lib.guis.epic_login_dialog import LoginDialog
        from lib.utilities.epic_auth import get_epic_auth_instance
        dialog = LoginDialog(self, get_epic_auth_instance())
        dialog.ShowModal()
        authenticated = dialog.authenticated
        dialog.Destroy()
        if authenticated:
            auth = get_epic_auth_instance()
            on_auth_success(auth)
            sounds.ui("done")

            def legendary_login():
                try:
                    from lib.fortnite import get_manager
                    get_manager().login_with_exchange_code(auth.get_exchange_code())
                except Exception:
                    pass
            threading.Thread(target=legendary_login, name="LegendaryLogin", daemon=True).start()
        self._refresh()
        self.signin_button.SetFocus()


class FortniteStep(WizardPage):
    title = "Fortnite"

    def _build(self) -> None:
        super()._build()
        self.message = wx.StaticText(self, label="Looking for Fortnite on this computer…")
        self.content_sizer.Add(self.message, flag=wx.ALL, border=5)
        self.choice = wx.RadioBox(
            self, label="How should Fortnite be managed?",
            choices=["Let FA11y manage it (recommended). Faster launches and updates from FA11y, no redownload.",
                     "Keep using the Epic Games Launcher. FA11y syncs with it so both see the same install."],
            majorDimension=1, style=wx.RA_SPECIFY_COLS)
        self.choice.Hide()
        self.content_sizer.Add(self.choice, flag=wx.EXPAND | wx.ALL, border=5)
        self.status = None
        threading.Thread(target=self._check, name="OnboardingFortnite", daemon=True).start()

    def _check(self) -> None:
        try:
            from lib.fortnite import get_manager
            st = get_manager().status()
        except Exception:
            st = None
        wx.CallAfter(self._checked, st)

    def _checked(self, st) -> None:
        if not self:
            return
        self.status = st
        if st is None:
            text = "FA11y couldn't check for Fortnite. You can set it up on the Fortnite page later."
        elif st.installed:
            text = f"Fortnite is installed at {st.install_path} and ready to play from FA11y."
        elif st.egl_install_path:
            text = f"Fortnite is installed through the Epic Games Launcher at {st.egl_install_path}."
            self.choice.Show()
        else:
            text = ("Fortnite isn't installed. After setup, open the Fortnite page to install it. "
                    "It needs about 100 GB.")
        self.message.SetLabel(text)
        self.message.Wrap(560)
        self.Layout()
        if self.IsShown():
            state.speaker.speak(text)

    def on_enter(self) -> None:
        state.speaker.speak(f"{self.title}. {self.message.GetLabel()}")

    def egl_choice(self) -> Optional[str]:
        """'manage', 'sync', or None when there's no Epic Games Launcher install to decide on."""
        if self.status is None or self.status.installed or not self.status.egl_install_path:
            return None
        return "manage" if self.choice.GetSelection() == 0 else "sync"


class StartupStep(WizardPage):
    title = "Starting FA11y"
    intro = ("FA11y opens this window when it starts, and its keybinds work in the background "
             "while it runs. Choose how the window behaves.")

    def _build(self) -> None:
        super()._build()
        self.auto_launch = wx.CheckBox(self, label="Start &Fortnite when FA11y opens")
        self.hide_on_launch = wx.CheckBox(self, label="&Hide this window when Fortnite starts")
        self.hide_on_launch.SetValue(True)
        self.nav_sounds = wx.CheckBox(self, label="Play &navigation sounds in this window")
        self.nav_sounds.SetValue(True)
        self.close_action = wx.RadioBox(
            self, label="When I close the FA11y window",
            choices=["Ask me", "Keep running in the tray", "Quit FA11y"],
            majorDimension=1, style=wx.RA_SPECIFY_COLS)
        for ctrl in (self.auto_launch, self.hide_on_launch, self.nav_sounds, self.close_action):
            self.content_sizer.Add(ctrl, flag=wx.ALL, border=5)

    def collect(self) -> Dict[tuple, Any]:
        actions = (settings.CLOSE_ASK, settings.CLOSE_TRAY, settings.CLOSE_QUIT)
        return {
            ("Toggles", "StartFortniteOnLaunch"): _bool(self.auto_launch.GetValue()),
            ("Toggles", "HideHubWhenFortniteStarts"): _bool(self.hide_on_launch.GetValue()),
            ("Toggles", "NavigationSounds"): _bool(self.nav_sounds.GetValue()),
            ("Hub", "CloseAction"): actions[self.close_action.GetSelection()],
        }


class DoneStep(WizardPage):
    title = "All set"
    intro = ("Setup is complete. Press Finish to start using FA11y. You can run setup again "
             "from the Settings page, and change any setting there.")


def _bool(value: bool) -> str:
    return "true" if value else "false"


class OnboardingPanel(wx.Panel):
    """Fills the hub window until setup is finished or skipped."""

    def __init__(self, parent: wx.Window, on_done: Callable[[Optional[str]], None]):
        super().__init__(parent)
        theme.style_window(self)
        self._on_done = on_done
        self._index = 0

        self._container = wx.Panel(self)
        theme.style_window(self._container)
        container_sizer = wx.BoxSizer(wx.VERTICAL)
        self._container.SetSizer(container_sizer)
        self.fortnite_step = None
        self._steps: List[WizardPage] = []
        for cls in (WelcomeStep, SignInStep, FortniteStep, StartupStep, SpeechPage, AudioTestPage,
                    MousePage, DoneStep):
            step = cls(self._container)
            theme.style_window(step)
            step.Hide()
            container_sizer.Add(step, 1, wx.EXPAND)
            self._steps.append(step)
            if isinstance(step, FortniteStep):
                self.fortnite_step = step

        self._progress = label(self, "", theme.TEXT_SECONDARY)
        nav = wx.BoxSizer(wx.HORIZONTAL)
        self._skip = button(self, "S&kip setup", variant="ghost")
        self._back = button(self, "&Back")
        self._next = button(self, "&Next", variant="primary")
        self._skip.Bind(wx.EVT_BUTTON, lambda e: self.skip())
        self._back.Bind(wx.EVT_BUTTON, lambda e: self._show(self._index - 1))
        self._next.Bind(wx.EVT_BUTTON, lambda e: self._advance())
        nav.Add(self._skip)
        nav.AddStretchSpacer()
        nav.Add(self._back, 0, wx.RIGHT, 8)
        nav.Add(self._next)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._progress, 0, wx.LEFT | wx.TOP, 24)
        sizer.Add(self._container, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)
        sizer.Add(nav, 0, wx.EXPAND | wx.ALL, 24)
        self.SetSizer(sizer)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

    def begin(self) -> None:
        state.wizard_open.set()
        self._show(0)

    def _show(self, index: int) -> None:
        if not 0 <= index < len(self._steps):
            return
        for i, step in enumerate(self._steps):
            step.Show(i == index)
        if index != self._index:
            sounds.ui("navigate")
        self._index = index
        self._progress.SetLabel(f"Setup: step {index + 1} of {len(self._steps)}")
        self._back.Show(index > 0)
        self._next.SetLabel("&Finish" if index == len(self._steps) - 1 else "&Next")
        self._next.SetDefault()
        self.Layout()
        self._container.Layout()
        step = self._steps[index]
        from lib.guis.view_host import first_focusable
        target = first_focusable(step) or self._next
        wx.CallAfter(target.SetFocus)
        try:
            step.on_enter()
        except Exception as e:
            logger.debug(f"Setup step on_enter failed: {e}")

    def _advance(self) -> None:
        if self._index < len(self._steps) - 1:
            self._show(self._index + 1)
        else:
            self._finish(save_choices=True)

    def skip(self) -> None:
        if wx.MessageBox("Skip setup? FA11y starts with default settings. You can run setup again "
                         "from the Settings page.", "Skip setup", wx.YES_NO | wx.ICON_QUESTION, self) == wx.YES:
            self._finish(save_choices=False)

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_ESCAPE and not event.HasAnyModifiers():
            self.skip()
            return
        event.Skip()

    def _finish(self, save_choices: bool) -> None:
        from lib.utilities.utilities import read_config, save_config
        try:
            config = read_config(use_cache=False)
            values: Dict[tuple, Any] = {}
            if save_choices:
                for step in self._steps:
                    try:
                        values.update(step.collect())
                    except Exception as e:
                        logger.error(f"Setup step {type(step).__name__} collect failed: {e}")
            values[("Setup", "FirstRunComplete")] = "true"
            for (section, key), value in values.items():
                if not config.has_section(section):
                    config.add_section(section)
                existing = config.get(section, key, fallback="")
                description = existing[existing.index('"'):] if '"' in existing else ""
                if key == "FirstRunComplete":
                    description = f'"{FIRST_RUN_DESCRIPTION}"'
                config.set(section, key, f"{value} {description}".strip())
            if not save_config(config):
                state.speaker.speak("Couldn't save your setup choices.")
        except Exception:
            logger.exception("Saving setup failed")
        finally:
            for step in self._steps:
                cleanup = getattr(step, "cleanup", None)
                if callable(cleanup):
                    try:
                        cleanup()
                    except Exception:
                        pass
            state.wizard_open.clear()
        egl_choice = self.fortnite_step.egl_choice() if (save_choices and self.fortnite_step) else None
        sounds.set_enabled(settings.flag("NavigationSounds", True))
        if save_choices:
            sounds.ui("done")
        self._on_done(egl_choice)
