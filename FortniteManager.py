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

from lib.guis.base_ui import AccessibleUI, message_box, ask_yes_no

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Hide console window on Windows
if sys.platform.startswith('win'):
    try:
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass


class FortniteManager(AccessibleUI):
    """
    Fortnite Manager GUI using the AccessibleUI base class.

    Provides an accessible interface for managing Fortnite installation
    and configuration using Legendary launcher.
    """

    def __init__(self):
        """Initialize the Fortnite Manager GUI."""
        super().__init__(title="Fortnite Manager", width=700, height=500)

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

        # Set up the UI
        self.setup()

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

    def setup(self):
        """Set up the main UI elements."""
        # Add main tab
        self.add_tab("Main")

        # Add information label
        self.add_label(
            "Main",
            "Fortnite Manager - Manage your Fortnite installation",
            font=("Arial", 14, "bold")
        )

        self.add_label("Main", "")  # Spacer

        # Add management buttons
        self.add_button(
            "Main",
            "Install/Update Fortnite",
            self.install_or_update_fortnite,
            "Install or update Fortnite. Press Enter to start."
        )

        self.add_button(
            "Main",
            "Verify Fortnite",
            self.verify_fortnite,
            "Verify Fortnite installation. Press Enter to start verification."
        )

        self.add_button(
            "Main",
            "Uninstall Fortnite",
            self.uninstall_fortnite,
            "Uninstall Fortnite. Press Enter to confirm."
        )

        # Add authentication buttons
        self.add_button(
            "Main",
            "Login to Legendary",
            self.login,
            "Login to Legendary. Press Enter to start login process."
        )

        self.add_button(
            "Main",
            "Logout from Legendary",
            self.logout,
            "Logout from Legendary. Press Enter to logout."
        )

        # Add launch buttons
        self.add_button(
            "Main",
            "Launch Fortnite (DX11)",
            self.launch_fortnite_dx11,
            "Launch Fortnite in DirectX 11 mode. Press Enter to launch."
        )

        self.add_button(
            "Main",
            "Launch Fortnite (Performance Mode)",
            self.launch_fortnite_performance,
            "Launch Fortnite in Performance mode. Press Enter to launch."
        )

        self.add_label("Main", "")  # Spacer

        # Add keybind information
        self.add_label(
            "Main",
            "Keyboard Shortcuts:",
            font=("Arial", 11, "bold")
        )

        keybind_info = [
            "• Escape - Stop current operation",
            "• Spacebar - Pause/Resume progress announcements",
            "• Minus (-) - Decrease progress update interval",
            "• Plus (=) - Increase progress update interval",
            "• P - Repeat last progress update",
            "• H - List all keybinds"
        ]

        for info in keybind_info:
            self.add_label("Main", info, font=("Arial", 9))

        # Bind hotkeys
        self.root.bind('<Escape>', lambda e: self.stop_installation())
        self.root.bind('<space>', lambda e: self.toggle_pause())
        self.root.bind('-', lambda e: self.decrease_interval())
        self.root.bind('=', lambda e: self.increase_interval())
        self.root.bind('+', lambda e: self.increase_interval())
        self.root.bind('p', lambda e: self.read_last_progress())
        self.root.bind('P', lambda e: self.read_last_progress())
        self.root.bind('h', lambda e: self.list_keybinds())
        self.root.bind('H', lambda e: self.list_keybinds())

        # Override the default window close behavior
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        """Handle window close event."""
        # Stop any running process
        if self.current_process and self.current_process.poll() is None:
            if ask_yes_no(
                "Process Running",
                "An operation is still running. Are you sure you want to close?"
            ):
                self.stop_installation()
                self.close()
        else:
            self.close()

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
            message_box("Error", "Timeout checking login status", "error")
            return False
        except Exception as e:
            logger.error(f"Error checking login status: {e}")
            self.speak(f"Error checking login status: {str(e)}")
            return False

    def login(self):
        """Start login process to Legendary."""
        self.speak("Opening login process. Please follow the instructions in the console window.")
        logger.info("Starting login process")

        try:
            process = self.run_command([self.legendary_exe, "auth"])
            self.monitor_output(process)

            # Check if login was successful
            if self.check_login_status():
                self.speak("Logged in successfully.")
                message_box("Success", "You have been logged in successfully.", "info")
            else:
                self.speak("Login failed. Please try again.")
                message_box("Login Failed", "Login was not successful. Please try again.", "warning")
        except Exception as e:
            logger.error(f"Error during login: {e}")
            self.speak(f"Error during login: {str(e)}")
            message_box("Error", f"An error occurred during login: {str(e)}", "error")

    def logout(self):
        """Logout from Legendary."""
        if not self.check_login_status():
            self.speak("You are not currently logged in.")
            message_box("Info", "You are not currently logged in.", "info")
            return

        if not ask_yes_no("Confirm Logout", "Are you sure you want to logout?"):
            return

        self.speak("Logging out...")
        logger.info("Logging out")

        try:
            subprocess.run([self.legendary_exe, "auth", "logout"], check=True, timeout=10)
            self.speak("Logged out successfully.")
            message_box("Success", "You have been logged out successfully.", "info")
            logger.info("Logout successful")
        except subprocess.TimeoutExpired:
            logger.error("Timeout during logout")
            message_box("Error", "Logout operation timed out.", "error")
        except Exception as e:
            logger.error(f"Error during logout: {e}")
            self.speak(f"Error during logout: {str(e)}")
            message_box("Error", f"An error occurred during logout: {str(e)}", "error")

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
            self.speak("An operation is already in progress. Please wait or press Escape to cancel.")
            message_box("Info", "An operation is already in progress.", "info")
            return

        # Check login status first
        if not self.check_login_status():
            self.speak("You must be logged in to install or update Fortnite.")
            if ask_yes_no("Login Required", "You must be logged in first. Would you like to login now?"):
                self.login()
            return

        # Determine if installing or updating
        is_installed = self.check_fortnite_installed()

        if is_installed:
            self.speak("Fortnite is already installed. Starting update check...")
            logger.info("Starting Fortnite update")
            process = self.run_command([self.legendary_exe, "update", "fortnite", "--yes", "-y"])
        else:
            self.speak("Starting Fortnite installation. This may take a while...")
            logger.info("Starting Fortnite installation")
            process = self.run_command([self.legendary_exe, "install", "fortnite", "--yes", "--skip-sdl", "-y"])

        # Start monitoring in background thread
        threading.Thread(target=self.monitor_output, args=(process,), daemon=True).start()

        self.speak("Operation started. Press Escape to cancel at any time, or H to hear all keybinds.")

    def verify_fortnite(self):
        """Verify Fortnite installation."""
        if not self.check_fortnite_installed():
            self.speak("Fortnite is not installed.")
            message_box("Error", "Fortnite is not installed. Please install it first.", "error")
            return

        if self.current_process is not None and self.current_process.poll() is None:
            self.speak("An operation is already in progress.")
            message_box("Info", "An operation is already in progress.", "info")
            return

        self.speak("Starting Fortnite verification. This may take a while...")
        logger.info("Starting Fortnite verification")

        process = self.run_command([self.legendary_exe, "verify", "fortnite"])
        threading.Thread(target=self.monitor_output, args=(process,), daemon=True).start()

    def uninstall_fortnite(self):
        """Uninstall Fortnite with confirmation."""
        if not self.check_fortnite_installed():
            self.speak("Fortnite is not installed.")
            message_box("Info", "Fortnite is not currently installed.", "info")
            return

        if not ask_yes_no(
            "Confirm Uninstall",
            "Are you sure you want to uninstall Fortnite? This cannot be undone."
        ):
            self.speak("Uninstall cancelled.")
            return

        if self.current_process is not None and self.current_process.poll() is None:
            self.speak("An operation is already in progress.")
            message_box("Info", "An operation is already in progress.", "info")
            return

        self.speak("Uninstalling Fortnite...")
        logger.info("Starting Fortnite uninstall")

        process = self.run_command([self.legendary_exe, "uninstall", "fortnite", "--yes"])
        threading.Thread(target=self.monitor_output, args=(process,), daemon=True).start()

    def launch_fortnite_dx11(self):
        """Launch Fortnite in DirectX 11 mode."""
        if not self.check_fortnite_installed():
            self.speak("Fortnite is not installed.")
            message_box("Error", "Fortnite is not installed. Please install it first.", "error")
            return

        self.speak("Launching Fortnite in DirectX 11 mode...")
        logger.info("Launching Fortnite in DX11 mode")

        try:
            subprocess.Popen(
                [self.legendary_exe, "launch", "fortnite", "--dx11"],
                startupinfo=subprocess.STARTUPINFO()
            )
            self.speak("Fortnite is launching.")
            message_box("Success", "Fortnite is launching in DirectX 11 mode.", "info")
        except Exception as e:
            logger.error(f"Error launching Fortnite: {e}")
            self.speak(f"Error launching Fortnite: {str(e)}")
            message_box("Error", f"Failed to launch Fortnite: {str(e)}", "error")

    def launch_fortnite_performance(self):
        """Launch Fortnite in Performance mode."""
        if not self.check_fortnite_installed():
            self.speak("Fortnite is not installed.")
            message_box("Error", "Fortnite is not installed. Please install it first.", "error")
            return

        self.speak("Launching Fortnite in Performance mode...")
        logger.info("Launching Fortnite in Performance mode")

        try:
            subprocess.Popen(
                [self.legendary_exe, "launch", "Fortnite", "-FeatureLevelES31"],
                startupinfo=subprocess.STARTUPINFO()
            )
            self.speak("Fortnite is launching.")
            message_box("Success", "Fortnite is launching in Performance mode.", "info")
        except Exception as e:
            logger.error(f"Error launching Fortnite: {e}")
            self.speak(f"Error launching Fortnite: {str(e)}")
            message_box("Error", f"Failed to launch Fortnite: {str(e)}", "error")

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

        self.speak(
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
                    self.speak("Operation completed successfully.")
                    logger.info("Operation completed successfully")
                    break

            # Wait for process to finish
            process.stdout.close()
            return_code = process.wait()

            if return_code != 0 and not self.installation_stopped:
                logger.warning(f"Process ended with return code {return_code}")
                self.speak("The process ended with errors. Please check the logs for details.")
                message_box(
                    "Operation Complete",
                    "The operation completed but may have encountered errors. Check the logs for details.",
                    "warning"
                )

        except Exception as e:
            logger.error(f"Error monitoring output: {e}")
            self.speak(f"Error monitoring process: {str(e)}")

        finally:
            with self.process_lock:
                self.current_process = None
            self.installation_stopped = False

    def toggle_pause(self):
        """Toggle pause state of progress announcements."""
        if self.current_process is None or self.current_process.poll() is not None:
            self.speak("No process is currently running to pause.")
            return

        self.is_paused = not self.is_paused
        self.speak("Progress announcements paused." if self.is_paused else "Progress announcements resumed.")
        logger.info(f"Progress announcements {'paused' if self.is_paused else 'resumed'}")

    def stop_installation(self):
        """Stop the current process."""
        with self.process_lock:
            if self.current_process is None or self.current_process.poll() is not None:
                self.speak("No process is currently running to stop.")
                return

            self.speak("Stopping the current process...")
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
            self.speak("Process stopped successfully.")

    def decrease_interval(self):
        """Decrease progress update interval."""
        if self.progress_interval > 1:
            self.progress_interval -= 1
            self.speak(f"Progress update interval set to {self.progress_interval} seconds")
            logger.info(f"Progress interval decreased to {self.progress_interval}")
        else:
            self.speak("Already at minimum update interval of 1 second")

    def increase_interval(self):
        """Increase progress update interval."""
        if self.progress_interval < 30:
            self.progress_interval += 1
            self.speak(f"Progress update interval set to {self.progress_interval} seconds")
            logger.info(f"Progress interval increased to {self.progress_interval}")
        else:
            self.speak("Already at maximum update interval of 30 seconds")

    def read_last_progress(self):
        """Read the last progress update."""
        if self.last_progress_state:
            self.speak("Reading last progress update:")
            self.update_progress_state((
                self.last_progress_state['progress'],
                self.last_progress_state['elapsed'],
                self.last_progress_state['eta']
            ))
        else:
            self.speak("No progress update available yet")

    def list_keybinds(self):
        """Announce available keybinds."""
        self.speak(
            "Available keyboard shortcuts: "
            "Press Escape to stop the current operation. "
            "Press Spacebar to pause or resume progress announcements. "
            "Press Minus to decrease progress update interval. "
            "Press Plus or Equals to increase it. "
            "Press P to repeat the last progress update. "
            "Press H to hear this list again."
        )

    def run(self):
        """Run the application."""
        # Check login status on startup
        if not self.check_login_status():
            self.speak("You are not logged in to Legendary. Please login before installing or updating Fortnite.")
            logger.info("User not logged in on startup")

        # Start the main loop
        super().run()


def main():
    """Main function to start the application."""
    try:
        app = FortniteManager()
        app.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"Error starting Fortnite Manager: {e}")
        input("Press Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    main()
