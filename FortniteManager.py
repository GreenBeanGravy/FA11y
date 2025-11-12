"""
Fortnite Manager for FA11y

Provides a GUI interface for managing Fortnite installation and launches
using the Legendary launcher. Features include:
- Installing and updating Fortnite
- Verifying game files
- Uninstalling Fortnite
- Logging in/out of Epic Games
- Launching Fortnite in different modes (DX11, Performance)
- Real-time progress monitoring
"""

import subprocess
import sys
import os
import time
import re
import threading
import logging
from typing import Optional, Tuple
import ctypes

# Check Python version and create mock imp if necessary
if sys.version_info >= (3, 12):
    class MockImp:
        __name__ = 'imp'

        @staticmethod
        def is_frozen(arg=None):
            if arg == "__main__":
                return hasattr(sys, "frozen") or '__compiled__' in globals()
            return hasattr(sys, 'frozen') or hasattr(sys, 'importers') or getattr(sys, 'frozen', False)

    sys.modules['imp'] = MockImp()

import wx
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import (
    AccessibleDialog, BoxSizerHelper, ButtonHelper,
    messageBox, force_focus_window, ensure_window_focus_and_center_mouse,
    BORDER_FOR_DIALOGS
)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

speaker = Auto()

# Hide console window on Windows
if sys.platform.startswith('win'):
    try:
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass


class FortniteManagerDialog(AccessibleDialog):
    """
    Fortnite Manager GUI using wxPython AccessibleDialog base class.

    Provides an accessible interface for managing Fortnite installation
    and configuration using Legendary launcher.
    """

    def __init__(self, parent=None):
        """Initialize the Fortnite Manager GUI."""
        super().__init__(parent, title="Fortnite Manager", helpId="FortniteManager")

        # Process management
        self.current_process: Optional[subprocess.Popen] = None
        self.process_lock = threading.Lock()
        self.installation_stopped = False
        self.is_paused = False

        # Progress tracking
        self.last_progress_state = {}
        self.progress_interval = 5  # seconds between progress announcements
        self.last_speech_time = 0

        # Legendary executable path
        self.legendary_exe = self._find_legendary_executable()

        logger.info("Fortnite Manager initialized")

        # Set up the dialog
        self.setupDialog()

        # Bind window close event
        self.Bind(wx.EVT_CLOSE, self.onClose)

        # Bind hotkeys
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)

    def _find_legendary_executable(self) -> str:
        """
        Find the Legendary executable.

        Returns:
            Path to legendary executable
        """
        # Check common locations
        possible_paths = [
            "legendary.exe",
            "legendary",
            os.path.join("legendary", "legendary.exe"),
            os.path.join(os.path.expanduser("~"), ".local", "bin", "legendary"),
        ]

        for path in possible_paths:
            if os.path.exists(path) or self._command_exists(path):
                logger.info(f"Found Legendary at: {path}")
                return path

        logger.warning("Legendary executable not found in common locations, using 'legendary.exe'")
        return "legendary.exe"

    def _command_exists(self, command: str) -> bool:
        """
        Check if a command exists in PATH.

        Args:
            command: Command to check

        Returns:
            True if command exists, False otherwise
        """
        try:
            subprocess.run([command, "--version"], capture_output=True, check=False)
            return True
        except FileNotFoundError:
            return False

    def makeSettings(self, settingsSizer: BoxSizerHelper):
        """Create dialog content."""
        # Add title/info label
        titleLabel = wx.StaticText(
            self,
            label="Fortnite Manager - Manage your Fortnite installation",
        )
        font = titleLabel.GetFont()
        font.PointSize += 2
        font = font.Bold()
        titleLabel.SetFont(font)
        settingsSizer.addItem(titleLabel)

        # Add management section
        mgmtBox = wx.StaticBoxSizer(wx.VERTICAL, self, label="Fortnite Management")
        mgmtHelper = BoxSizerHelper(self, sizer=mgmtBox)

        # Install/Update button
        self.installBtn = wx.Button(self, label="Install/Update Fortnite")
        self.installBtn.Bind(wx.EVT_BUTTON, lambda e: self.install_or_update_fortnite())
        mgmtHelper.addItem(self.installBtn)

        # Verify button
        self.verifyBtn = wx.Button(self, label="Verify Fortnite")
        self.verifyBtn.Bind(wx.EVT_BUTTON, lambda e: self.verify_fortnite())
        mgmtHelper.addItem(self.verifyBtn)

        # Uninstall button
        self.uninstallBtn = wx.Button(self, label="Uninstall Fortnite")
        self.uninstallBtn.Bind(wx.EVT_BUTTON, lambda e: self.uninstall_fortnite())
        mgmtHelper.addItem(self.uninstallBtn)

        settingsSizer.addItem(mgmtBox, flag=wx.EXPAND)

        # Add authentication section
        authBox = wx.StaticBoxSizer(wx.VERTICAL, self, label="Authentication")
        authHelper = BoxSizerHelper(self, sizer=authBox)

        # Login button
        self.loginBtn = wx.Button(self, label="Login to Legendary")
        self.loginBtn.Bind(wx.EVT_BUTTON, lambda e: self.login())
        authHelper.addItem(self.loginBtn)

        # Logout button
        self.logoutBtn = wx.Button(self, label="Logout from Legendary")
        self.logoutBtn.Bind(wx.EVT_BUTTON, lambda e: self.logout())
        authHelper.addItem(self.logoutBtn)

        settingsSizer.addItem(authBox, flag=wx.EXPAND)

        # Add launch section
        launchBox = wx.StaticBoxSizer(wx.VERTICAL, self, label="Launch Fortnite")
        launchHelper = BoxSizerHelper(self, sizer=launchBox)

        # DX11 button
        self.dx11Btn = wx.Button(self, label="Launch Fortnite (DX11)")
        self.dx11Btn.Bind(wx.EVT_BUTTON, lambda e: self.launch_fortnite_dx11())
        launchHelper.addItem(self.dx11Btn)

        # Performance mode button
        self.perfBtn = wx.Button(self, label="Launch Fortnite (Performance Mode)")
        self.perfBtn.Bind(wx.EVT_BUTTON, lambda e: self.launch_fortnite_performance())
        launchHelper.addItem(self.perfBtn)

        settingsSizer.addItem(launchBox, flag=wx.EXPAND)

        # Add keybind information
        keybindBox = wx.StaticBoxSizer(wx.VERTICAL, self, label="Keyboard Shortcuts")
        keybindHelper = BoxSizerHelper(self, sizer=keybindBox)

        keybind_info = [
            "Escape - Stop current operation",
            "Spacebar - Pause/Resume progress announcements",
            "Minus (-) - Decrease progress update interval",
            "Plus (=) - Increase progress update interval",
            "P - Repeat last progress update",
            "H - List all keybinds",
        ]

        for info in keybind_info:
            label = wx.StaticText(self, label=info)
            keybindHelper.addItem(label)

        settingsSizer.addItem(keybindBox, flag=wx.EXPAND)

    def onKeyEvent(self, event):
        """Handle keyboard shortcuts."""
        key_code = event.GetKeyCode()

        if key_code == wx.WXK_ESCAPE:
            self.stop_installation()
        elif key_code == wx.WXK_SPACE:
            self.toggle_pause()
        elif key_code == ord('-'):
            self.decrease_interval()
        elif key_code == ord('=') or key_code == ord('+'):
            self.increase_interval()
        elif key_code == ord('p') or key_code == ord('P'):
            self.read_last_progress()
        elif key_code == ord('h') or key_code == ord('H'):
            self.list_keybinds()
        else:
            event.Skip()

    def onClose(self, event):
        """Handle window close event."""
        # Stop any running process
        if self.current_process and self.current_process.poll() is None:
            result = messageBox(
                "An operation is still running. Are you sure you want to close?",
                "Process Running",
                wx.YES_NO | wx.ICON_QUESTION,
                self
            )
            if result == wx.YES:
                self.stop_installation()
                self.Destroy()
            else:
                event.Veto()
        else:
            self.Destroy()

    def run_command(self, command: list) -> subprocess.Popen:
        """
        Run a command and return the process.

        Args:
            command: Command list to run

        Returns:
            Popen process object
        """
        # Create startup info to hide console window
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

        with self.process_lock:
            self.current_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding='utf-8',
                bufsize=1,
                startupinfo=startupinfo
            )

        logger.info(f"Started command: {' '.join(command)}")
        return self.current_process

    def check_login_status(self) -> bool:
        """
        Check if user is logged in to Legendary.

        Returns:
            True if logged in, False otherwise
        """
        try:
            result = subprocess.run(
                [self.legendary_exe, "status"],
                capture_output=True,
                text=True,
                timeout=10
            )
            is_logged_in = "Epic account:" in result.stdout
            logger.info(f"Login status checked: {'logged in' if is_logged_in else 'not logged in'}")
            return is_logged_in
        except subprocess.TimeoutExpired:
            logger.error("Timeout checking login status")
            wx.CallAfter(messageBox, "Timeout checking login status", "Error", wx.OK | wx.ICON_ERROR, self)
            return False
        except Exception as e:
            logger.error(f"Error checking login status: {e}")
            speaker.speak(f"Error checking login status: {str(e)}")
            return False

    def login(self):
        """Start login process to Legendary."""
        speaker.speak("Opening login process. Please follow the instructions in the console window.")
        logger.info("Starting login process")

        try:
            process = self.run_command([self.legendary_exe, "auth"])
            self.monitor_output(process)

            # Check if login was successful
            if self.check_login_status():
                speaker.speak("Logged in successfully.")
                wx.CallAfter(messageBox, "You have been logged in successfully.", "Success", wx.OK | wx.ICON_INFORMATION, self)
            else:
                speaker.speak("Login failed. Please try again.")
                wx.CallAfter(messageBox, "Login was not successful. Please try again.", "Login Failed", wx.OK | wx.ICON_WARNING, self)
        except Exception as e:
            logger.error(f"Error during login: {e}")
            speaker.speak(f"Error during login: {str(e)}")
            wx.CallAfter(messageBox, f"An error occurred during login: {str(e)}", "Error", wx.OK | wx.ICON_ERROR, self)

    def logout(self):
        """Logout from Legendary."""
        if not self.check_login_status():
            speaker.speak("You are not currently logged in.")
            wx.CallAfter(messageBox, "You are not currently logged in.", "Info", wx.OK | wx.ICON_INFORMATION, self)
            return

        result = messageBox(
            "Are you sure you want to logout?",
            "Confirm Logout",
            wx.YES_NO | wx.ICON_QUESTION,
            self
        )

        if result != wx.YES:
            return

        speaker.speak("Logging out...")
        logger.info("Logging out")

        try:
            subprocess.run([self.legendary_exe, "auth", "logout"], check=True, timeout=10)
            speaker.speak("Logged out successfully.")
            wx.CallAfter(messageBox, "You have been logged out successfully.", "Success", wx.OK | wx.ICON_INFORMATION, self)
            logger.info("Logout successful")
        except subprocess.TimeoutExpired:
            logger.error("Timeout during logout")
            wx.CallAfter(messageBox, "Logout operation timed out.", "Error", wx.OK | wx.ICON_ERROR, self)
        except Exception as e:
            logger.error(f"Error during logout: {e}")
            speaker.speak(f"Error during logout: {str(e)}")
            wx.CallAfter(messageBox, f"An error occurred during logout: {str(e)}", "Error", wx.OK | wx.ICON_ERROR, self)

    def check_fortnite_installed(self) -> bool:
        """
        Check if Fortnite is already installed.

        Returns:
            True if installed, False otherwise
        """
        try:
            result = subprocess.run(
                [self.legendary_exe, "list-installed"],
                capture_output=True,
                text=True,
                timeout=10
            )
            is_installed = "* Fortnite" in result.stdout
            logger.info(f"Fortnite installation status: {'installed' if is_installed else 'not installed'}")
            return is_installed
        except subprocess.TimeoutExpired:
            logger.error("Timeout checking Fortnite installation status")
            return False
        except Exception as e:
            logger.error(f"Error checking Fortnite installation: {e}")
            return False

    def install_or_update_fortnite(self):
        """Install or update Fortnite based on current installation status."""
        if self.current_process is not None and self.current_process.poll() is None:
            speaker.speak("An operation is already in progress. Please wait or press Escape to cancel.")
            wx.CallAfter(messageBox, "An operation is already in progress.", "Info", wx.OK | wx.ICON_INFORMATION, self)
            return

        # Check login status first
        if not self.check_login_status():
            speaker.speak("You must be logged in to install or update Fortnite.")
            result = messageBox(
                "You must be logged in first. Would you like to login now?",
                "Login Required",
                wx.YES_NO | wx.ICON_QUESTION,
                self
            )
            if result == wx.YES:
                self.login()
            return

        # Determine if installing or updating
        is_installed = self.check_fortnite_installed()

        if is_installed:
            speaker.speak("Fortnite is already installed. Starting update check...")
            logger.info("Starting Fortnite update")
            process = self.run_command([self.legendary_exe, "update", "fortnite", "--yes", "-y"])
        else:
            speaker.speak("Starting Fortnite installation. This may take a while...")
            logger.info("Starting Fortnite installation")
            process = self.run_command([self.legendary_exe, "install", "fortnite", "--yes", "--skip-sdl", "-y"])

        # Start monitoring in background thread
        threading.Thread(target=self.monitor_output, args=(process,), daemon=True).start()

        speaker.speak("Operation started. Press Escape to cancel at any time, or H to hear all keybinds.")

    def verify_fortnite(self):
        """Verify Fortnite installation."""
        if not self.check_fortnite_installed():
            speaker.speak("Fortnite is not installed.")
            wx.CallAfter(messageBox, "Fortnite is not installed. Please install it first.", "Error", wx.OK | wx.ICON_ERROR, self)
            return

        if self.current_process is not None and self.current_process.poll() is None:
            speaker.speak("An operation is already in progress.")
            wx.CallAfter(messageBox, "An operation is already in progress.", "Info", wx.OK | wx.ICON_INFORMATION, self)
            return

        speaker.speak("Starting Fortnite verification. This may take a while...")
        logger.info("Starting Fortnite verification")

        process = self.run_command([self.legendary_exe, "verify", "fortnite"])
        threading.Thread(target=self.monitor_output, args=(process,), daemon=True).start()

    def uninstall_fortnite(self):
        """Uninstall Fortnite with confirmation."""
        if not self.check_fortnite_installed():
            speaker.speak("Fortnite is not installed.")
            wx.CallAfter(messageBox, "Fortnite is not currently installed.", "Info", wx.OK | wx.ICON_INFORMATION, self)
            return

        result = messageBox(
            "Are you sure you want to uninstall Fortnite? This cannot be undone.",
            "Confirm Uninstall",
            wx.YES_NO | wx.ICON_QUESTION,
            self
        )

        if result != wx.YES:
            speaker.speak("Uninstall cancelled.")
            return

        if self.current_process is not None and self.current_process.poll() is None:
            speaker.speak("An operation is already in progress.")
            wx.CallAfter(messageBox, "An operation is already in progress.", "Info", wx.OK | wx.ICON_INFORMATION, self)
            return

        speaker.speak("Uninstalling Fortnite...")
        logger.info("Starting Fortnite uninstall")

        process = self.run_command([self.legendary_exe, "uninstall", "fortnite", "--yes"])
        threading.Thread(target=self.monitor_output, args=(process,), daemon=True).start()

    def launch_fortnite_dx11(self):
        """Launch Fortnite in DirectX 11 mode."""
        if not self.check_fortnite_installed():
            speaker.speak("Fortnite is not installed.")
            wx.CallAfter(messageBox, "Fortnite is not installed. Please install it first.", "Error", wx.OK | wx.ICON_ERROR, self)
            return

        speaker.speak("Launching Fortnite in DirectX 11 mode...")
        logger.info("Launching Fortnite in DX11 mode")

        try:
            subprocess.Popen(
                [self.legendary_exe, "launch", "fortnite", "--dx11"],
                startupinfo=subprocess.STARTUPINFO()
            )
            speaker.speak("Fortnite is launching.")
            wx.CallAfter(messageBox, "Fortnite is launching in DirectX 11 mode.", "Success", wx.OK | wx.ICON_INFORMATION, self)
        except Exception as e:
            logger.error(f"Error launching Fortnite: {e}")
            speaker.speak(f"Error launching Fortnite: {str(e)}")
            wx.CallAfter(messageBox, f"Failed to launch Fortnite: {str(e)}", "Error", wx.OK | wx.ICON_ERROR, self)

    def launch_fortnite_performance(self):
        """Launch Fortnite in Performance mode."""
        if not self.check_fortnite_installed():
            speaker.speak("Fortnite is not installed.")
            wx.CallAfter(messageBox, "Fortnite is not installed. Please install it first.", "Error", wx.OK | wx.ICON_ERROR, self)
            return

        speaker.speak("Launching Fortnite in Performance mode...")
        logger.info("Launching Fortnite in Performance mode")

        try:
            subprocess.Popen(
                [self.legendary_exe, "launch", "Fortnite", "-FeatureLevelES31"],
                startupinfo=subprocess.STARTUPINFO()
            )
            speaker.speak("Fortnite is launching.")
            wx.CallAfter(messageBox, "Fortnite is launching in Performance mode.", "Success", wx.OK | wx.ICON_INFORMATION, self)
        except Exception as e:
            logger.error(f"Error launching Fortnite: {e}")
            speaker.speak(f"Error launching Fortnite: {str(e)}")
            wx.CallAfter(messageBox, f"Failed to launch Fortnite: {str(e)}", "Error", wx.OK | wx.ICON_ERROR, self)

    def parse_progress(self, line: str) -> Optional[Tuple[float, str, str]]:
        """
        Parse progress information from output lines.

        Args:
            line: Output line to parse

        Returns:
            Tuple of (progress_percent, elapsed_time, eta) or None
        """
        match = re.search(r'Progress: ([\d.]+)%.*Running for ([\d:]+), ETA: ([\d:]+)', line)
        if match:
            progress, elapsed, eta = match.groups()
            return float(progress), elapsed, eta
        return None

    def format_time_for_speech(self, time_str: str) -> str:
        """
        Convert time string (HH:MM:SS or MM:SS) to natural speech format.

        Args:
            time_str: Time string to format

        Returns:
            Natural language time description
        """
        parts = time_str.split(':')

        try:
            if len(parts) == 2:  # MM:SS format
                minutes, seconds = map(int, parts)
                time_parts = []

                if minutes > 0:
                    time_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
                if seconds > 0 or not time_parts:
                    time_parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

                return ", and ".join(time_parts) if len(time_parts) > 1 else time_parts[0]

            else:  # HH:MM:SS format
                hours, minutes, seconds = map(int, parts)
                time_parts = []

                if hours > 0:
                    time_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
                if minutes > 0:
                    time_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
                if seconds > 0 or not time_parts:
                    time_parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

                if len(time_parts) > 1:
                    return f"{', '.join(time_parts[:-1])}, and {time_parts[-1]}"
                return time_parts[0]
        except ValueError:
            return time_str

    def update_progress_state(self, result: Tuple[float, str, str]):
        """
        Update progress state and announce it.

        Args:
            result: Tuple of (progress, elapsed, eta)
        """
        progress, elapsed, eta = result
        self.last_progress_state = {'progress': progress, 'elapsed': elapsed, 'eta': eta}

        elapsed_speech = self.format_time_for_speech(elapsed)
        eta_speech = self.format_time_for_speech(eta)

        speaker.speak(
            f"Progress: {progress:.1f} percent. "
            f"Time Elapsed: {elapsed_speech}. "
            f"Time Remaining: {eta_speech}."
        )

    def monitor_output(self, process: subprocess.Popen):
        """
        Monitor process output and update progress.

        Args:
            process: Process to monitor
        """
        logger.info("Starting output monitoring")

        try:
            while True:
                # Check if paused
                if self.is_paused:
                    time.sleep(0.1)
                    continue

                # Read line
                line = process.stdout.readline()
                if not line:
                    break

                line = line.strip()
                if line:
                    logger.debug(f"Process output: {line}")

                # Check if stopped
                if self.installation_stopped:
                    logger.info("Installation stop requested")
                    process.terminate()
                    break

                # Parse progress
                progress_data = self.parse_progress(line)
                if progress_data:
                    current_time = time.time()
                    if current_time - self.last_speech_time >= self.progress_interval:
                        self.update_progress_state(progress_data)
                        self.last_speech_time = current_time

                # Check for completion
                if "Finished installation process" in line or \
                   "Fortnite update completed" in line or \
                   "Verification complete" in line or \
                   "Uninstall complete" in line:
                    speaker.speak("Operation completed successfully.")
                    logger.info("Operation completed successfully")
                    break

            # Wait for process to finish
            process.stdout.close()
            return_code = process.wait()

            if return_code != 0 and not self.installation_stopped:
                logger.warning(f"Process ended with return code {return_code}")
                speaker.speak("The process ended with errors. Please check the logs for details.")
                wx.CallAfter(
                    messageBox,
                    "The operation completed but may have encountered errors. Check the logs for details.",
                    "Operation Complete",
                    wx.OK | wx.ICON_WARNING,
                    self
                )

        except Exception as e:
            logger.error(f"Error monitoring output: {e}")
            speaker.speak(f"Error monitoring process: {str(e)}")

        finally:
            with self.process_lock:
                self.current_process = None
            self.installation_stopped = False

    def toggle_pause(self):
        """Toggle pause state of progress announcements."""
        if self.current_process is None or self.current_process.poll() is not None:
            speaker.speak("No process is currently running to pause.")
            return

        self.is_paused = not self.is_paused
        speaker.speak("Progress announcements paused." if self.is_paused else "Progress announcements resumed.")
        logger.info(f"Progress announcements {'paused' if self.is_paused else 'resumed'}")

    def stop_installation(self):
        """Stop the current process."""
        with self.process_lock:
            if self.current_process is None or self.current_process.poll() is not None:
                speaker.speak("No process is currently running to stop.")
                return

            speaker.speak("Stopping the current process...")
            logger.info("Stopping current process")
            self.installation_stopped = True

            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Process did not terminate, forcing kill")
                self.current_process.kill()
            except Exception as e:
                logger.error(f"Error stopping process: {e}")

            self.current_process = None
            speaker.speak("Process stopped successfully.")

    def decrease_interval(self):
        """Decrease progress update interval."""
        if self.progress_interval > 1:
            self.progress_interval -= 1
            speaker.speak(f"Progress update interval set to {self.progress_interval} seconds")
            logger.info(f"Progress interval decreased to {self.progress_interval}")
        else:
            speaker.speak("Already at minimum update interval of 1 second")

    def increase_interval(self):
        """Increase progress update interval."""
        if self.progress_interval < 30:
            self.progress_interval += 1
            speaker.speak(f"Progress update interval set to {self.progress_interval} seconds")
            logger.info(f"Progress interval increased to {self.progress_interval}")
        else:
            speaker.speak("Already at maximum update interval of 30 seconds")

    def read_last_progress(self):
        """Read the last progress update."""
        if self.last_progress_state:
            speaker.speak("Reading last progress update:")
            self.update_progress_state((
                self.last_progress_state['progress'],
                self.last_progress_state['elapsed'],
                self.last_progress_state['eta']
            ))
        else:
            speaker.speak("No progress update available yet")

    def list_keybinds(self):
        """Announce available keybinds."""
        speaker.speak(
            "Available keyboard shortcuts: "
            "Press Escape to stop the current operation. "
            "Press Spacebar to pause or resume progress announcements. "
            "Press Minus to decrease progress update interval. "
            "Press Plus or Equals to increase it. "
            "Press P to repeat the last progress update. "
            "Press H to hear this list again."
        )


def main():
    """Main function to start the application."""
    try:
        app = wx.App()
        dialog = FortniteManagerDialog()

        # Check login status on startup
        if not dialog.check_login_status():
            speaker.speak("You are not logged in to Legendary. Please login before installing or updating Fortnite.")
            logger.info("User not logged in on startup")

        dialog.ShowModal()
        dialog.Destroy()
        app.MainLoop()

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"Error starting Fortnite Manager: {e}")
        input("Press Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    main()
