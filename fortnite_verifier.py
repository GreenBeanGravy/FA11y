import subprocess
import sys
import time
import re
import os
import psutil
import threading
import tkinter as tk
from tkinter import ttk

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
current_process = None
is_installing = False
installation_stopped = False
is_focused = False
is_paused = False
progress_interval = 5
last_progress_state = {}
last_speech_time = 0

def speak(text):
    print(text)  # Log to console
    speaker.speak(text)

def check_login_status():
    try:
        result = subprocess.run(['legendary', 'auth', 'status'], capture_output=True, text=True)
        return "Logged in" in result.stdout
    except Exception as e:
        speak(f"Error checking login status: {str(e)}")
        return False

def login():
    speak("Logging in...")
    subprocess.run(['legendary', 'auth', 'login'], check=True)
    speak("Logged in successfully.")

def format_size(size_in_bytes):
    try:
        size_in_mib = size_in_bytes / (1024 * 1024)
        return f"{size_in_mib:.2f} MiB"
    except Exception as e:
        return "Unknown size"

def kill_legendary_processes():
    for proc in psutil.process_iter(['pid', 'name']):
        if 'legendary' in proc.info['name']:
            proc.kill()

def update_progress(progress_data):
    file_index = progress_data.get('file_index', 0)
    total_files = progress_data.get('total_files', 0)
    percentage = progress_data.get('percentage', 0.0)
    elapsed_time = progress_data.get('elapsed_time', "0 seconds")
    remaining_time = progress_data.get('remaining_time', "0 seconds")
    speed = progress_data.get('speed', 0.0)

    speak(f"File {file_index} of {total_files}, Progress: {percentage:.2f} percent, Time Elapsed: {elapsed_time}, Time remaining: {remaining_time}, Download speed: {speed:.2f} megabytes per second")

def parse_progress_line(line):
    match = re.search(r'Verification progress: (\d+)/(\d+) \((\d+\.\d+)%\) \[([\d.]+) MiB/s\]', line, re.IGNORECASE)
    if match:
        file_index = int(match.group(1))
        total_files = int(match.group(2))
        percentage = float(match.group(3))
        speed = float(match.group(4))
        elapsed_time = "0 seconds"  # Default value, replace as needed
        remaining_time = "0 seconds"  # Default value, replace as needed
        return {
            'file_index': file_index,
            'total_files': total_files,
            'percentage': percentage,
            'elapsed_time': elapsed_time,
            'remaining_time': remaining_time,
            'speed': speed,
        }
    return None

def parse_final_progress_line(line):
    match = re.search(r'= Progress: (\d+\.\d+)% \((\d+)/(\d+)\), Running for (.+), ETA: (.+)', line, re.IGNORECASE)
    if match:
        percentage = float(match.group(1))
        file_index = int(match.group(2))
        total_files = int(match.group(3))
        elapsed_time = match.group(4)
        remaining_time = match.group(5)
        return {
            'file_index': file_index,
            'total_files': total_files,
            'percentage': percentage,
            'elapsed_time': elapsed_time,
            'remaining_time': remaining_time,
            'speed': 0.0,  # Default value, replace as needed
        }
    return None

def repair_fortnite():
    try:
        speak("Repairing Fortnite...")
        result = subprocess.Popen(['legendary', 'repair', 'fortnite', '--yes'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        current_process = result

        for line in result.stdout:
            print(line.strip())
            if installation_stopped:
                result.terminate()
                break

            progress_data = parse_progress_line(line)
            if progress_data:
                last_progress_state = progress_data
                current_time = time.time()
                if not is_paused and current_time - last_speech_time >= progress_interval:
                    update_progress(progress_data)
                    last_speech_time = current_time

            final_progress_data = parse_final_progress_line(line)
            if final_progress_data:
                last_progress_state = final_progress_data
                update_progress(final_progress_data)

            if "Finished installation process" in line:
                speak("Fortnite repair completed. Closing in 5 seconds.")
                window.after(5000, window.quit)
                break

        result.stdout.close()
        result.wait()
    except Exception as e:
        speak(f"An error occurred during repair: {str(e)}")

def verify_fortnite():
    global last_progress_state, installation_stopped, last_speech_time
    try:
        result = subprocess.Popen(['legendary', 'verify', 'fortnite'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        current_process = result

        for line in result.stdout:
            print(line.strip())
            if installation_stopped:
                result.terminate()
                break

            progress_data = parse_progress_line(line)
            if progress_data:
                last_progress_state = progress_data
                current_time = time.time()
                if not is_paused and current_time - last_speech_time >= progress_interval:
                    update_progress(progress_data)
                    last_speech_time = current_time

            if "Verification finished successfully" in line:
                speak("Fortnite verification completed. Closing in 5 seconds.")
                window.after(5000, window.quit)
                break
            elif "Verification failed" in line:
                repair_fortnite()
                break

        result.stdout.close()
        result.wait()
    except Exception as e:
        speak(f"An error occurred during verification: {str(e)}")

def create_window():
    global window
    window = tk.Tk()
    window.title("Fortnite Verifier")
    window.geometry("300x200")

    style = ttk.Style()
    style.configure("TLabel", padding=6, font=("Helvetica", 12))
    style.configure("TButton", padding=6, font=("Helvetica", 12))
    
    label = ttk.Label(window, text="Fortnite Verifier is running...")
    label.pack(pady=20)
    
    stop_button = ttk.Button(window, text="Stop Verification", command=stop_installation)
    stop_button.pack(pady=10)

    def on_focus(event):
        global is_focused
        is_focused = True
    
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
        update_progress(last_progress_state)
    else:
        speak("No progress update available yet")

def stop_installation():
    global current_process, is_installing, installation_stopped
    speak("Stopping the verification process...")
    installation_stopped = True
    if current_process:
        current_process.terminate()
    kill_legendary_processes()
    is_installing = False
    speak("Verification process stopped.")

def main():
    create_window()
    
    def run_verification():
        global installation_stopped
        try:
            speak("Checking login status...")
            if not check_login_status():
                login()
            
            if not installation_stopped:
                verify_fortnite()
            
            if not installation_stopped:
                total_size = format_size(last_progress_state.get('total_size', 0))
                speak_if_unfocused(f"Process completed. Total size: {total_size}. Thank you for using the Legendary Fortnite Verifier.")
            window.after(0, lambda: window.quit() if installation_stopped else None)
        except Exception as e:
            speak(f"An error occurred: {str(e)}")
            window.after(0, window.quit)

    threading.Thread(target=run_verification, daemon=True).start()
    window.mainloop()

if __name__ == "__main__":
    main()
