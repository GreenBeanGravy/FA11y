import subprocess
import sys
import time
import re
import signal
import os
import psutil
import threading
import tkinter as tk
from tkinter import ttk
import webbrowser

if sys.platform.startswith('win'):
    import ctypes

    # Hide console window
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

# Check Python version and create mock imp if necessary
if sys.version_info >= (3, 12):
    class MockImp:
        @staticmethod
        def is_frozen(arg=None):
            if arg == "__main__":
                return hasattr(sys, "frozen") or '__compiled__' in globals()
            return hasattr(sys, 'frozen') or hasattr(sys, 'importers') or getattr(sys, 'frozen', False)
    sys.modules['imp'] = MockImp()

import accessible_output2.outputs.auto

# Initialize speech output
speaker = accessible_output2.outputs.auto.Auto()

# Global variables
window = None
progress_bar = None
is_focused = False
last_progress_state = {
    'progress': None,
    'elapsed': None,
    'eta': None,
    'installed_size': None,
    'total_size': None,
    'download_speed': None,
    'write_speed': None
}
last_progress_time = 0
is_installing = False
progress_interval = 10
first_progress_message = True
is_paused = False
current_process = None
installation_stopped = False

def speak(text):
    print(text)
    speaker.output(text)

def run_command(command):
    global current_process
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    current_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, encoding='utf-8', bufsize=1, startupinfo=startupinfo)
    return current_process

def check_login_status():
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    result = subprocess.run(["legendary.exe", "status"], capture_output=True, text=True, encoding='utf-8', startupinfo=startupinfo)
    return "Epic account: <not logged in>" not in result.stdout

def login():
    speak("You are not logged in. Please log in to continue.")
    process = run_command(["legendary.exe", "auth"])
    read_output(process)
    if not check_login_status():
        speak("Login failed. Please try running the script again.")
        sys.exit(1)

def read_output(process):
    global installation_stopped
    def read_stream(stream):
        while True:
            line = stream.readline()
            if not line:
                break
            line = line.strip()
            window.after(0, handle_line, line)
            if installation_stopped:
                break

    stdout_thread = threading.Thread(target=read_stream, args=(process.stdout,))
    stderr_thread = threading.Thread(target=read_stream, args=(process.stderr,))

    stdout_thread.start()
    stderr_thread.start()

    stdout_thread.join()
    stderr_thread.join()

    process.wait()

def handle_line(line):
    global last_progress_state, last_progress_time, is_installing, first_progress_message
    if "Login successful" in line:
        speak_if_unfocused("Login successful.")
    elif "Preparing download" in line:
        is_installing = True
        speak("Fortnite is now installing...")
    elif "Could not find" in line and "Fortnite" in line:
        speak("You don't own Fortnite. Please purchase it from the Epic Games Store.")
        speak("Opening the Fortnite store page in 5 seconds.")
        window.after(5000, lambda: webbrowser.open("https://store.epicgames.com/en-US/p/fortnite"))
        window.after(5500, window.quit)
    elif "Finished installation process" in line:
        speak("Fortnite installation completed successfully. Closing in 5 seconds..")
        window.after(5000, window.quit)  # Close the window after a delay
    result = parse_progress(line)
    if result is not None:
        update_progress_state(result)
        current_time = time.time()
        if is_focused and not is_paused and (first_progress_message or current_time - last_progress_time >= progress_interval):
            speak_progress(last_progress_state)
            last_progress_time = current_time
            first_progress_message = False

def update_progress_state(result):
    global last_progress_state
    if isinstance(result, tuple):
        if len(result) == 3:  # Progress update
            progress, elapsed, eta = result
            last_progress_state['progress'] = progress
            last_progress_state['elapsed'] = elapsed
            last_progress_state['eta'] = eta
            last_progress_state['installed_size'] = last_progress_state['total_size'] * (progress / 100) if last_progress_state['total_size'] else None
            if progress_bar:
                progress_bar['value'] = progress
        elif len(result) == 2:  # Download speed update
            last_progress_state['download_speed'] = result[0]
    elif isinstance(result, float):  # Write speed update
        last_progress_state['write_speed'] = result

def format_time(time_str):
    hours, minutes, seconds = map(int, time_str.split(':'))
    if hours > 0:
        return f"{hours} hours, {minutes} minutes, and {seconds} seconds"
    elif minutes > 0:
        return f"{minutes} minutes and {seconds} seconds"
    else:
        return f"{seconds} seconds"

def format_size(size_mb):
    if size_mb is None:
        return "Unknown size"
    if size_mb >= 1024:
        return f"{size_mb / 1024:.2f} gigabytes"
    else:
        return f"{size_mb:.2f} megabytes"

def speak_progress(state):
    if state['progress'] is not None:
        speak(f"Progress: {state['progress']:.2f} percent")
    if state['elapsed'] is not None:
        speak(f"Time Elapsed: {format_time(state['elapsed'])}")
    if state['eta'] is not None:
        speak(f"Time remaining: {format_time(state['eta'])}")
    if state['installed_size'] is not None and state['total_size'] is not None:
        speak(f"Installed: {format_size(state['installed_size'])} out of {format_size(state['total_size'])}")
    if state['download_speed'] is not None:
        speak(f"Download speed: {state['download_speed']:.2f} megabytes per second")
    if state['write_speed'] is not None:
        speak(f"Write speed: {state['write_speed']:.2f} megabytes per second")

def kill_legendary_processes():
    killed = False
    for proc in psutil.process_iter(['name']):
        try:
            if proc.name() == 'legendary.exe':
                proc.terminate()
                killed = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return killed

def check_fortnite_installed():
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    result = subprocess.run(["legendary.exe", "list-installed"], capture_output=True, text=True, encoding='utf-8', startupinfo=startupinfo)
    return "* Fortnite" in result.stdout

def install_or_update_fortnite():
    global is_installing, first_progress_message, installation_stopped
    
    if check_fortnite_installed():
        speak("Fortnite is already installed! Closing in 5 seconds.")
        window.after(5000, window.quit)
        return

    speak_if_unfocused("Starting Fortnite installation or update...")
    if kill_legendary_processes():
        speak_if_unfocused("Existing legendary processes have been terminated.")
    else:
        speak_if_unfocused("No existing legendary processes found.")
    
    install_command = ["legendary.exe", "install", "fortnite", "--yes", "--skip-sdl"]
    process = run_command(install_command)
    first_progress_message = True
    read_output(process)
    is_installing = False
    if not installation_stopped:
        speak_if_unfocused("Fortnite installation or update completed.")

def parse_progress(line):
    global last_progress_state
    progress_match = re.search(r'Progress: ([\d.]+)%.*Running for ([\d:]+), ETA: ([\d:]+)', line)
    if progress_match:
        progress, elapsed, eta = progress_match.groups()
        return float(progress), elapsed, eta
    
    download_match = re.search(r'Download.*?([\d.]+) MiB/s.*?([\d.]+) MiB/s', line)
    if download_match:
        download_speed, _ = map(float, download_match.groups())
        return download_speed, _
    
    disk_match = re.search(r'Disk.*?([\d.]+) MiB/s \(write\)', line)
    if disk_match:
        write_speed = disk_match.group(1)
        return float(write_speed)
    
    size_match = re.search(r'Install size: ([\d.]+) MiB', line)
    if size_match:
        last_progress_state['total_size'] = float(size_match.group(1))
    
    return None

def create_window():
    global window, progress_bar, is_focused
    window = tk.Tk()
    window.title("Fortnite Installer")
    window.geometry("300x150")
    window.attributes('-topmost', True)
    
    label = ttk.Label(window, text="Fortnite Installer Running")
    label.pack(pady=10)

    progress_bar = ttk.Progressbar(window, orient="horizontal", length=200, mode="determinate")
    progress_bar.pack(pady=10)
    
    def on_focus(event):
        global is_focused
        is_focused = True
        if is_installing:
            window.after(50, lambda: speak("Installing Fortnite..."))

    def on_unfocus(event):
        global is_focused
        is_focused = False
    
    window.bind("<FocusIn>", on_focus)
    window.bind("<FocusOut>", on_unfocus)
    window.bind("-", lambda e: window.after(0, decrease_interval))
    window.bind("=", lambda e: window.after(0, increase_interval))
    window.bind("<space>", lambda e: window.after(0, toggle_pause))
    window.bind("p", lambda e: window.after(0, read_last_progress))
    window.bind("<Escape>", lambda e: window.after(0, stop_installation))
    
    # Force focus
    window.focus_force()
    window.update()
    window.after(100, lambda: window.focus_force())

def speak_if_unfocused(text):
    if not is_focused:
        speak(text)

def decrease_interval():
    global progress_interval
    if progress_interval > 1:
        progress_interval -= 1
        speak(f"Progress update interval set to {progress_interval} seconds")
    else:
        speak("Already at minimum update interval of 1 second")

def increase_interval():
    global progress_interval
    if progress_interval < 15:
        progress_interval += 1
        speak(f"Progress update interval set to {progress_interval} seconds")
    else:
        speak("Already at maximum update interval of 15 seconds")

def toggle_pause():
    global is_paused
    is_paused = not is_paused
    if is_paused:
        speak("Progress updates paused")
    else:
        speak("Progress updates resumed")

def read_last_progress():
    if any(last_progress_state.values()):
        speak("Reading last progress update:")
        speak_progress(last_progress_state)
    else:
        speak("No progress update available yet")

def stop_installation():
    global current_process, is_installing, installation_stopped
    speak("Stopping the installation process...")
    installation_stopped = True
    if current_process:
        current_process.terminate()
    kill_legendary_processes()
    is_installing = False
    speak("Installation stopped. All Legendary processes have been terminated.")
    window.after(1000, window.quit)

def main():
    create_window()
    
    def run_installation():
        global installation_stopped
        try:
            speak("Checking login status...")
            if not check_login_status():
                login()
            
            if not installation_stopped:
                install_or_update_fortnite()
            
            if not installation_stopped:
                total_size = format_size(last_progress_state['total_size'])
                speak_if_unfocused(f"Process completed. Total size: {total_size}. Thank you for using the Legendary Fortnite Installer/Updater.")
            window.after(0, lambda: window.quit() if installation_stopped else None)
        except Exception as e:
            speak(f"An error occurred: {str(e)}")
            window.after(0, window.quit)

    threading.Thread(target=run_installation, daemon=True).start()
    window.mainloop()

if __name__ == "__main__":
    main()
