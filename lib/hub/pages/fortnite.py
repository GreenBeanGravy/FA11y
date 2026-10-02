"""Fortnite page: install, update, verify, move and uninstall through legendary, plus launch options."""
from __future__ import annotations

import os
import shutil
import threading
from typing import Callable, Optional

import wx

from lib.hub import game_watch, sounds, theme
from lib.hub.page import HubPage
from lib.hub.widgets import GAP, Card, button, label, text

API_CHOICES = [("default", "Default"), ("dx11", "DirectX 11"), ("dx12", "DirectX 12"),
               ("performance", "Performance mode")]


def _size_text(size_bytes: int) -> str:
    if size_bytes <= 0:
        return ""
    gb = size_bytes / 1024 ** 3
    return f"{gb:.0f} GB" if gb >= 10 else f"{gb:.1f} GB"


def _free_space_text(path: str) -> str:
    probe = path
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        return f"{shutil.disk_usage(probe).free / 1024 ** 3:.0f} GB free"
    except OSError:
        return ""


class FortnitePage(HubPage):
    title = "Fortnite"

    def build(self) -> None:
        from lib.fortnite import get_manager
        self.manager = get_manager()
        self.status = None
        self._cancel: Optional[threading.Event] = None

        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(label(self, "Fortnite", font=theme.heading_font(self)), 1, wx.ALIGN_CENTER_VERTICAL)
        self.play_button = button(self, "&Play", "player-play", "primary")
        self.play_button.Bind(wx.EVT_BUTTON, lambda e: self.play())
        top.Add(self.play_button, 0, wx.ALIGN_CENTER_VERTICAL)
        self.content.Add(top, 0, wx.EXPAND | wx.BOTTOM, 6)

        self.summary = text(self, "Checking your Fortnite install…", theme.TEXT_SECONDARY)
        self.content.Add(self.summary, 0, wx.BOTTOM, 12)

        # Sign-in notice for legendary, shown when downloads need it.
        self.signin_card = Card(self, "Sign in for downloads")
        self.signin_text = text(self.signin_card, "Downloads, updates and Play need your Epic account.",
                                 wrap=620)
        self.signin_button = button(self.signin_card, "&Sign in with your Epic account", "user", "primary")
        self.signin_button.Bind(wx.EVT_BUTTON, lambda e: self._sign_in())
        self.signin_card.body.Add(self.signin_text)
        self.signin_card.body.Add(self.signin_button, 0, wx.TOP, 8)
        self.content.Add(self.signin_card, 0, wx.EXPAND | wx.BOTTOM, GAP)

        # Shown when the Epic Games Launcher has Fortnite and legendary doesn't.
        self.egl_card = Card(self, "Epic Games Launcher install")
        self.egl_text = text(self.egl_card, "", wrap=620)
        self.egl_manage = button(self.egl_card, "Let FA11y &manage it (recommended)", variant="primary")
        self.egl_keep = button(self.egl_card, "&Keep using the Epic Games Launcher")
        self.egl_manage.Bind(wx.EVT_BUTTON, lambda e: self.take_over_egl_install())
        self.egl_keep.Bind(wx.EVT_BUTTON, lambda e: self.sync_with_egl())
        egl_buttons = wx.BoxSizer(wx.HORIZONTAL)
        egl_buttons.Add(self.egl_manage, 0, wx.RIGHT, 8)
        egl_buttons.Add(self.egl_keep)
        self.egl_card.body.Add(self.egl_text)
        self.egl_card.body.Add(text(self.egl_card,
                                    "Letting FA11y manage it means faster launches and updates from this window, "
                                     "with no redownload. Keeping the Epic Games Launcher syncs it with FA11y so "
                                     "both know about the same install.", theme.TEXT_SECONDARY, wrap=620), 0, wx.TOP, 6)
        self.egl_card.body.Add(egl_buttons, 0, wx.TOP, 10)
        self.content.Add(self.egl_card, 0, wx.EXPAND | wx.BOTTOM, GAP)

        # Install row, for when there's no install at all.
        self.install_row = wx.BoxSizer(wx.HORIZONTAL)
        self.install_button = button(self, "&Install Fortnite", "download", "primary")
        self.install_button.Bind(wx.EVT_BUTTON, lambda e: self._install())
        self.install_row.Add(self.install_button)
        self.content.Add(self.install_row, 0, wx.BOTTOM, GAP)

        # Actions for an installed copy.
        self.actions = wx.WrapSizer(wx.HORIZONTAL)
        self.update_button = button(self, "Check for &updates", "refresh")
        self.verify_button = button(self, "&Verify and repair")
        self.move_button = button(self, "&Move install", "folder")
        self.open_button = button(self, "&Open folder", "folder")
        self.uninstall_button = button(self, "U&ninstall", "trash", "danger")
        for ctrl, handler in ((self.update_button, self._update), (self.verify_button, self._verify),
                              (self.move_button, self._move), (self.open_button, self._open_folder),
                              (self.uninstall_button, self._uninstall)):
            ctrl.Bind(wx.EVT_BUTTON, lambda e, h=handler: h())
            self.actions.Add(ctrl, 0, wx.RIGHT | wx.BOTTOM, 8)
        self.content.Add(self.actions, 0, wx.EXPAND)

        # Progress for long operations. NVDA reads the native progress bar itself.
        self.progress_panel = wx.Panel(self)
        theme.style_window(self.progress_panel)
        progress_sizer = wx.BoxSizer(wx.VERTICAL)
        self.gauge = wx.Gauge(self.progress_panel, range=1000, name="Progress")
        self.progress_text = text(self.progress_panel, "", theme.TEXT_SECONDARY)
        self.cancel_button = button(self.progress_panel, "&Cancel")
        self.cancel_button.Bind(wx.EVT_BUTTON, lambda e: self._cancel_operation())
        progress_sizer.Add(self.gauge, 0, wx.EXPAND)
        progress_sizer.Add(self.progress_text, 0, wx.TOP, 4)
        progress_sizer.Add(self.cancel_button, 0, wx.TOP, 6)
        self.progress_panel.SetSizer(progress_sizer)
        self.progress_panel.Hide()
        self.content.Add(self.progress_panel, 0, wx.EXPAND | wx.TOP, 6)

        # Launch options.
        self.content.Add(label(self, "Launch options", font=theme.heading_font(self, 1)), 0, wx.TOP, 18)
        self.api_box = wx.RadioBox(self, label="&Graphics", choices=[c[1] for c in API_CHOICES],
                                   majorDimension=4, style=wx.RA_SPECIFY_COLS)
        self.skip_splash = wx.CheckBox(self, label="Skip the &splash screen")
        self.extra_label = label(self, "E&xtra arguments")
        self.extra_args = wx.TextCtrl(self, name="Extra arguments")
        self.content.Add(self.api_box, 0, wx.TOP, 6)
        self.content.Add(self.skip_splash, 0, wx.TOP, 8)
        self.content.Add(self.extra_label, 0, wx.TOP, 10)
        self.content.Add(self.extra_args, 0, wx.EXPAND | wx.TOP, 4)
        self._load_launch_options()
        self.api_box.Bind(wx.EVT_RADIOBOX, lambda e: self._save_launch_options())
        self.skip_splash.Bind(wx.EVT_CHECKBOX, lambda e: self._save_launch_options())
        self.extra_args.Bind(wx.EVT_KILL_FOCUS, self._on_extra_blur)

        # Mouse passthrough: FA11y never grabs a mouse by itself; pick one here.
        self.content.Add(label(self, "Mouse passthrough", font=theme.heading_font(self, 1)), 0, wx.TOP, 18)
        self.mouse_text = text(self, "", theme.TEXT_SECONDARY, wrap=620)
        self.content.Add(self.mouse_text, 0, wx.TOP, 6)
        self.content.Add(text(self, "Passthrough lets you use your own mouse in Fortnite while FA11y "
                                    "also moves the camera. Press Detect mouse, then move the mouse "
                                    "you play with.", theme.TEXT_SECONDARY, wrap=620), 0, wx.TOP, 4)
        self.mouse_button = button(self, "&Detect mouse")
        self.mouse_button.Bind(wx.EVT_BUTTON, lambda e: self._detect_mouse())
        self.content.Add(self.mouse_button, 0, wx.TOP, 8)

        self._apply_status(None)

    # Status --------------------------------------------------------------

    def on_show(self) -> None:
        if self._cancel is None:
            self.refresh()
        self._show_mouse()

    # Mouse passthrough ---------------------------------------------------

    def _show_mouse(self) -> None:
        try:
            from lib.mouse_passthrough import get_mouse_passthrough
            service = get_mouse_passthrough()
            self.mouse_text.SetLabel(service.describe())
            self.mouse_button.SetLabel("&Detect mouse again" if service.target_device else "&Detect mouse")
        except Exception as e:
            self.mouse_text.SetLabel(f"Mouse passthrough isn't available: {e}")
            self.mouse_button.Disable()
        self.Layout()

    def _detect_mouse(self) -> None:
        from lib.mouse_passthrough import get_mouse_passthrough
        self.mouse_button.Disable()
        self.mouse_text.SetLabel("Move the mouse you play with now.")

        def done(device):
            wx.CallAfter(self._mouse_detected, device)
        get_mouse_passthrough().recapture_mouse(on_done=done)

    def _mouse_detected(self, device) -> None:
        if not self:
            return
        self.mouse_button.Enable()
        sounds.ui("done" if device else "error")
        self._show_mouse()
        if device is None:
            self.mouse_text.SetLabel("No mouse moved, so nothing changed. " + self.mouse_text.GetLabel())

    def refresh(self, check_updates: bool = False) -> None:
        def work():
            st = self.manager.status(check_updates=check_updates)
            wx.CallAfter(self._apply_status, st)
        threading.Thread(target=work, name="FortniteStatus", daemon=True).start()

    def _apply_status(self, st) -> None:
        if not self:
            return
        self.status = st
        busy = self._cancel is not None
        installed = bool(st and st.installed)
        egl_only = bool(st and not st.installed and st.egl_install_path)
        legendary_ok = bool(st and st.legendary_available)

        if st is None:
            self.summary.SetLabel("Checking your Fortnite install…")
        elif not legendary_ok:
            self.summary.SetLabel(st.error)
        elif installed:
            parts = [_short_version(st.version) or "Installed", "managed by FA11y", st.install_path, _size_text(st.install_size_bytes)]
            if st.update_available:
                parts.append(f"update available ({st.remote_version})")
            elif st.needs_verification:
                parts.append("needs verifying")
            self.summary.SetLabel(" · ".join(p for p in parts if p))
        elif egl_only:
            self.summary.SetLabel("Installed through the Epic Games Launcher.")
        else:
            self.summary.SetLabel("Fortnite isn't installed.")

        self.signin_card.Show(bool(st) and legendary_ok and not st.logged_in)
        self.egl_card.Show(egl_only and not busy)
        if egl_only:
            version = f", version {_short_version(st.egl_version)}" if st.egl_version else ""
            self.egl_text.SetLabel(f"Fortnite is installed through the Epic Games Launcher at {st.egl_install_path}{version}.")
            self.egl_text.Wrap(620)
        self.install_button.Show(bool(st) and legendary_ok and not installed and not egl_only and not busy)
        for ctrl in (self.update_button, self.verify_button, self.move_button,
                     self.open_button, self.uninstall_button):
            ctrl.Show(installed and not busy)
        if installed:
            self.update_button.SetLabel("&Update now" if st.update_available else "Check for &updates")
        running = game_watch.is_fortnite_running()
        self.play_button.SetLabel("Fortnite is &running" if running else "&Play")
        self.Layout()
        self.FitInside()

    # Long operations -----------------------------------------------------

    def _run(self, name: str, operation: Callable, done: Optional[Callable] = None) -> None:
        """Run a manager operation on a worker thread, driving the progress bar."""
        if self._cancel is not None:
            return
        self._cancel = threading.Event()
        cancel = self._cancel
        self.gauge.SetValue(0)
        self.progress_text.SetLabel(f"{name}…")
        self.progress_panel.Show()
        self._apply_status(self.status)
        self.cancel_button.SetFocus()

        def progress(percent, message):
            wx.CallAfter(self._on_progress, percent, message)

        def work():
            result = operation(progress, cancel)
            wx.CallAfter(self._on_finished, result, done)
        threading.Thread(target=work, name=f"Fortnite-{name}", daemon=True).start()

    def _on_progress(self, percent, message: str) -> None:
        if not self:
            return
        if percent is None:
            self.gauge.Pulse()
        else:
            self.gauge.SetValue(int(max(0.0, min(percent, 100.0)) * 10))
        if message:
            self.progress_text.SetLabel(message)

    def _on_finished(self, result, done: Optional[Callable]) -> None:
        if not self:
            return
        self._cancel = None
        self.progress_panel.Hide()
        sounds.ui("done" if result.ok else "error")
        self.hub.services.speak(result.message)
        self.summary.SetLabel(result.message)
        if done is not None:
            done(result)
        self.refresh()
        wx.CallAfter(self._focus_after_operation)

    def _focus_after_operation(self) -> None:
        for ctrl in (self.play_button, self.install_button, self.egl_manage):
            if ctrl.IsShown():
                ctrl.SetFocus()
                return

    def _cancel_operation(self) -> None:
        if self._cancel is not None:
            self._cancel.set()
            self.progress_text.SetLabel("Cancelling…")

    def handle_escape(self) -> bool:
        # Escape doesn't cancel downloads by accident; use the Cancel button.
        return False

    # Actions -------------------------------------------------------------

    def play(self) -> None:
        if not self.built:
            self.ensure_built()
        from lib.hub.play import play_fortnite
        play_fortnite(self.hub, self.manager, self.status,
                      on_failed=lambda message: wx.CallAfter(self._launch_failed, message))

    def _launch_failed(self, message: str) -> None:
        sounds.ui("error")
        self.hub.services.speak(message)
        if self:
            self.summary.SetLabel(message)

    def _sign_in(self) -> None:
        from lib.utilities.epic_auth import get_epic_auth_instance
        auth = get_epic_auth_instance()
        if not auth or not auth.access_token or not auth.is_valid:
            self.hub.services.speak("Sign in to your Epic account first.")
            self.hub.show_page("account", summon=True)
            return
        self.signin_button.Disable()
        self.signin_text.SetLabel("Signing in…")

        def work():
            result = self.manager.login_with_exchange_code(auth.get_exchange_code())
            wx.CallAfter(self._signed_in, result)
        threading.Thread(target=work, name="LegendaryLogin", daemon=True).start()

    def _signed_in(self, result) -> None:
        if not self:
            return
        self.signin_button.Enable()
        self.signin_text.SetLabel("Downloads, updates and Play need your Epic account.")
        sounds.ui("done" if result.ok else "error")
        self.hub.services.speak(result.message)
        self.refresh()

    def _install(self) -> None:
        default = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Epic Games")
        with wx.DirDialog(self, "Choose where to install Fortnite. FA11y adds a Fortnite folder inside it.",
                          defaultPath=default, style=wx.DD_DEFAULT_STYLE) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            base = dialog.GetPath()
        free = _free_space_text(base)
        if wx.MessageBox(f"Install Fortnite in {os.path.join(base, 'Fortnite')}? "
                         f"It needs about 100 GB{' (' + free + ')' if free else ''}.",
                         "Install Fortnite", wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
            return
        self._run("Installing", lambda p, c: self.manager.install(base, p, c))

    def _update(self) -> None:
        if self.status is not None and self.status.update_available:
            self._run("Updating", self.manager.update)
            return
        self.update_button.Disable()
        self.summary.SetLabel("Checking for updates…")

        def work():
            st = self.manager.status(check_updates=True)
            wx.CallAfter(self._checked, st)
        threading.Thread(target=work, name="FortniteUpdateCheck", daemon=True).start()

    def _checked(self, st) -> None:
        if not self:
            return
        self.update_button.Enable()
        self._apply_status(st)
        message = (f"Update available: {st.remote_version}." if st.update_available
                   else (st.error or "Fortnite is up to date."))
        self.hub.services.speak(message)
        self.update_button.SetFocus()

    def _verify(self) -> None:
        self._run("Verifying", self.manager.verify_and_repair)

    def _move(self) -> None:
        with wx.DirDialog(self, "Choose the folder to move Fortnite into.",
                          style=wx.DD_DEFAULT_STYLE) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            target = dialog.GetPath()
        self._run("Moving", lambda p, c: self.manager.move(target, p, c))

    def _open_folder(self) -> None:
        if self.status and self.status.install_path and os.path.isdir(self.status.install_path):
            os.startfile(self.status.install_path)

    def _uninstall(self) -> None:
        if wx.MessageBox("Uninstall Fortnite and delete its files? You'll have to download it again to play.",
                         "Uninstall Fortnite", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self) != wx.YES:
            return
        self._run("Uninstalling", self.manager.uninstall)

    def take_over_egl_install(self) -> None:
        path = self.status.egl_install_path if self.status else ""
        self._run("Setting up", lambda p, c: self.manager.import_egl(path, p, c))

    def sync_with_egl(self) -> None:
        self._run("Syncing", self.manager.egl_sync)

    # Launch options -------------------------------------------------------

    def _load_launch_options(self) -> None:
        from lib.fortnite import load_launch_options
        options = load_launch_options()
        keys = [c[0] for c in API_CHOICES]
        self.api_box.SetSelection(keys.index(options.api) if options.api in keys else 0)
        self.skip_splash.SetValue(options.skip_splash)
        self.extra_args.ChangeValue(options.extra)

    def _save_launch_options(self) -> None:
        from lib.fortnite import LaunchOptions, save_launch_options
        save_launch_options(LaunchOptions(api=API_CHOICES[self.api_box.GetSelection()][0],
                                          skip_splash=self.skip_splash.GetValue(),
                                          extra=self.extra_args.GetValue()))

    def _on_extra_blur(self, event: wx.FocusEvent) -> None:
        self._save_launch_options()
        event.Skip()

    def on_hide(self) -> None:
        if self.built:
            self._save_launch_options()


def apply_setup_choice(hub, egl_choice) -> None:
    """After setup: take over ("manage") or sync with ("sync") the Epic Games Launcher install."""
    if egl_choice not in ("manage", "sync"):
        hub.show_page("home", focus_sidebar=True)
        return
    hub.show_page("fortnite")
    page = hub.page("fortnite")

    def run():
        # Wait for the page's first status check so it knows the install path.
        if page.status is None:
            wx.CallLater(300, run)
        elif egl_choice == "manage":
            page.take_over_egl_install()
        else:
            page.sync_with_egl()
    run()


def _short_version(build: str) -> str:
    """'++Fortnite+Release-42.20-CL-58011042-Windows' -> '42.20'."""
    marker = "Release-"
    if marker in build:
        return build.split(marker, 1)[1].split("-", 1)[0]
    return build
