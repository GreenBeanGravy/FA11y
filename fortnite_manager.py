import subprocess
import sys
import os
import time
import re
import threading
from typing import Optional
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
    
from lib.guis.AccessibleUIBackend import AccessibleUIBackend

if sys.platform.startswith('win'):
    # Hide console window
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

class FortniteManager:
    def __init__(self):
        self.ui = AccessibleUIBackend(title="Fortnite Manager")
        self.current_process: Optional[subprocess.Popen] = None
        self.installation_stopped = False
        self.is_paused = False
        self.last_progress_state = {}
        self.progress_interval = 5
        self.last_speech_time = 0
        self.setup_ui()

    def setup_ui(self):
        # Add main tab
        self.ui.add_tab("Main")
        
        # Add buttons with custom speech
        self.ui.add_button("Main", "Install/Update Fortnite", 
                          self.install_or_update_fortnite,
                          "Install or update Fortnite. Press Enter to start.")
        
        self.ui.add_button("Main", "Verify Fortnite", 
                          self.verify_fortnite,
                          "Verify Fortnite installation. Press Enter to start verification.")
        
        self.ui.add_button("Main", "Uninstall Fortnite", 
                          self.uninstall_fortnite,
                          "Uninstall Fortnite. Press Enter to confirm.")
        
        self.ui.add_button("Main", "Login to Legendary", 
                          self.login,
                          "Login to Legendary. Press Enter to start login process.")
        
        self.ui.add_button("Main", "Logout from Legendary", 
                          self.logout,
                          "Logout from Legendary. Press Enter to logout.")
        
        self.ui.add_button("Main", "Launch Fortnite (DX11)", 
                          self.launch_fortnite_dx11,
                          "Launch Fortnite in DirectX 11 mode. Press Enter to launch.")
        
        self.ui.add_button("Main", "Launch Fortnite (Performance Mode)", 
                          self.launch_fortnite_performance,
                          "Launch Fortnite in Performance mode. Press Enter to launch.")

        # Bind hotkeys
        self.ui.root.bind('<Escape>', self.stop_installation)
        self.ui.root.bind('<space>', self.toggle_pause)
        self.ui.root.bind('-', lambda e: self.decrease_interval())
        self.ui.root.bind('=', lambda e: self.increase_interval())
        self.ui.root.bind('p', lambda e: self.read_last_progress())
        self.ui.root.bind('h', lambda e: self.list_keybinds())

        # Prevent spacebar from activating buttons
        for child in self.ui.tabs["Main"].winfo_children():
            child.unbind('<space>')

        # Override the default window close behavior
        self.ui.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        """Handle window close event"""
        if self.current_process and self.current_process.poll() is None:
            self.stop_installation()
        self.ui.root.destroy()

    def run_command(self, command):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        self.current_process = subprocess.Popen(
            command, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            universal_newlines=True, 
            encoding='utf-8', 
            bufsize=1, 
            startupinfo=startupinfo
        )
        return self.current_process

    def check_login_status(self):
        try:
            result = subprocess.run(["legendary.exe", "status"], capture_output=True, text=True)
            return "Epic account:" in result.stdout
        except Exception as e:
            self.ui.speak(f"Error checking login status: {str(e)}")
            return False

    def login(self):
        self.ui.speak("Logging in...")
        process = self.run_command(["legendary.exe", "auth"])
        self.monitor_output(process)
        if self.check_login_status():
            self.ui.speak("Logged in successfully.")
        else:
            self.ui.speak("Login failed. Please try again.")

    def logout(self):
        self.ui.speak("Logging out...")
        subprocess.run(["legendary.exe", "auth", "logout"], check=True)
        self.ui.speak("Logged out successfully.")

    def check_fortnite_installed(self):
        result = subprocess.run(["legendary.exe", "list-installed"], capture_output=True, text=True)
        return "* Fortnite" in result.stdout

    def install_or_update_fortnite(self):
        if self.current_process is not None and self.current_process.poll() is None:
            self.ui.speak("An installation or update is already in progress. Please wait or press 'Escape' to cancel.")
            return

        if self.check_fortnite_installed():
            self.ui.speak("Fortnite is already installed! Proceeding with update...")
            process = self.run_command(["legendary.exe", "update", "fortnite", "--yes", "-y"])
        else:
            self.ui.speak("Starting Fortnite installation...")
            process = self.run_command(["legendary.exe", "install", "fortnite", "--yes", "--skip-sdl", "-y"])

        threading.Thread(target=self.monitor_output, args=(process,), daemon=True).start()
        self.ui.speak("You can press 'Escape' to cancel at any time. Press 'H' to hear all available keybinds.")

    def verify_fortnite(self):
        self.ui.speak("Verifying Fortnite installation...")
        process = self.run_command(["legendary.exe", "verify", "fortnite"])
        threading.Thread(target=self.monitor_output, args=(process,), daemon=True).start()

    def uninstall_fortnite(self):
        self.ui.speak("Are you sure you want to uninstall Fortnite? Press Enter to confirm or Escape to cancel.")
        
        def confirm_uninstall(event):
            if self.current_process is not None and self.current_process.poll() is None:
                self.ui.speak("An operation is already in progress. Please cancel it before proceeding with uninstallation.")
                return
            self.ui.speak("Uninstalling Fortnite...")
            process = self.run_command(["legendary.exe", "uninstall", "fortnite", "--yes"])
            threading.Thread(target=self.monitor_output, args=(process,), daemon=True).start()
            self.ui.root.unbind('<Return>')
            self.ui.root.unbind('<Escape>')

        def cancel_uninstall(event):
            self.ui.speak("Uninstall cancelled.")
            self.ui.root.unbind('<Return>')
            self.ui.root.unbind('<Escape>')

        self.ui.root.bind('<Return>', confirm_uninstall)
        self.ui.root.bind('<Escape>', cancel_uninstall)

    def launch_fortnite_dx11(self):
        self.ui.speak("Launching Fortnite in DirectX 11 mode...")
        subprocess.Popen(["legendary.exe", "launch", "fortnite", "--dx11"], 
                        startupinfo=subprocess.STARTUPINFO())

    def launch_fortnite_performance(self):
        self.ui.speak("Launching Fortnite in Performance mode...")
        subprocess.Popen(["legendary.exe", "launch", "Fortnite", "-FeatureLevelES31"], 
                        startupinfo=subprocess.STARTUPINFO())

    def parse_progress(self, line):
        match = re.search(r'Progress: ([\d.]+)%.*Running for ([\d:]+), ETA: ([\d:]+)', line)
        if match:
            progress, elapsed, eta = match.groups()
            return float(progress), elapsed, eta
        return None

    def format_time_for_speech(self, time_str):
        """Convert time string (HH:MM:SS or MM:SS) to natural speech format."""
        parts = time_str.split(':')
        if len(parts) == 2:  # MM:SS format
            minutes, seconds = map(int, parts)
            time_parts = []
            if minutes > 0:
                time_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
            if seconds > 0 or not time_parts:  # Include seconds if it's the only value
                time_parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
            return f"{', and '.join(time_parts) if len(time_parts) > 1 else time_parts[0]}"
        else:  # HH:MM:SS format
            hours, minutes, seconds = map(int, parts)
            time_parts = []
            if hours > 0:
                time_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
            if minutes > 0:
                time_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
            if seconds > 0 or not time_parts:  # Include seconds if it's the only value
                time_parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
            
            if len(time_parts) > 1:
                return f"{', '.join(time_parts[:-1])}, and {time_parts[-1]}"
            return time_parts[0]

    def update_progress_state(self, result):
        progress, elapsed, eta = result
        self.last_progress_state = {'progress': progress, 'elapsed': elapsed, 'eta': eta}
        
        elapsed_speech = self.format_time_for_speech(elapsed)
        eta_speech = self.format_time_for_speech(eta)
        
        self.ui.speak(
            f"Progress: {progress:.1f}%, "
            f"Time Elapsed: {elapsed_speech}, "
            f"Time Remaining: {eta_speech}"
        )

    def monitor_output(self, process):
        while True:
            if self.is_paused:
                time.sleep(0.1)  # Reduce CPU usage while paused
                continue

            line = process.stdout.readline()
            if not line:
                break
            
            line = line.strip()
            print(line)  # For debugging
            
            if self.installation_stopped:
                process.terminate()
                break
                
            progress_data = self.parse_progress(line)
            if progress_data:
                current_time = time.time()
                if current_time - self.last_speech_time >= self.progress_interval:
                    self.update_progress_state(progress_data)
                    self.last_speech_time = current_time

            if "Finished installation process" in line or "Fortnite update completed" in line:
                self.ui.speak("Fortnite installation or update completed successfully.")
                break

        process.stdout.close()
        process.wait()
        if process.returncode != 0 and not self.installation_stopped:
            self.ui.speak("The process might require additional user input. Please check the console for details.")

    def toggle_pause(self, event=None):
        """Toggle pause state of current process"""
        if self.current_process is None or self.current_process.poll() is not None:
            self.ui.speak("No process is currently running to pause.")
            return "break"
            
        self.is_paused = not self.is_paused
        self.ui.speak("Process paused." if self.is_paused else "Process resumed.")
        return "break"  # Prevent the event from propagating

    def stop_installation(self, event=None):
        """Stop the current process"""
        if self.current_process is None or self.current_process.poll() is not None:
            self.ui.speak("No process is currently running to stop.")
            return "break"
            
        self.ui.speak("Stopping the current process...")
        self.installation_stopped = True
        if self.current_process:
            self.current_process.terminate()
        self.current_process = None
        self.ui.speak("Process stopped successfully.")
        return "break"  # Prevent the event from propagating

    def decrease_interval(self):
        if self.progress_interval > 1:
            self.progress_interval -= 1
            self.ui.speak(f"Progress update interval set to {self.progress_interval} seconds")
        else:
            self.ui.speak("Already at minimum update interval of 1 second")

    def increase_interval(self):
        if self.progress_interval < 15:
            self.progress_interval += 1
            self.ui.speak(f"Progress update interval set to {self.progress_interval} seconds")
        else:
            self.ui.speak("Already at maximum update interval of 15 seconds")

    def read_last_progress(self):
        if any(self.last_progress_state.values()):
            self.ui.speak("Reading last progress update:")
            self.update_progress_state((
                self.last_progress_state['progress'],
                self.last_progress_state['elapsed'],
                self.last_progress_state['eta']
            ))
        else:
            self.ui.speak("No progress update available yet")

    def list_keybinds(self):
        self.ui.speak(
            "Available keybinds: Press 'Escape' to cancel the current process, "
            "'Spacebar' to pause or resume the current process, "
            "'-' to decrease progress update interval, '=' to increase it, "
            "'p' to read the last progress update, and 'h' to hear this list again."
        )

    def run(self):
        if not self.check_login_status():
            self.login()
        self.ui.run()

def main():
    app = FortniteManager()
    app.run()

if __name__ == "__main__":
    main()
