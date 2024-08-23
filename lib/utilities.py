import win32gui
import win32con
from accessible_output2.outputs.auto import Auto
import time
import pywintypes

speaker = Auto()

def force_focus_window(window, speak_text=None, focus_widget=None):
    window.deiconify()
    window.attributes('-topmost', True)
    window.update()
    window.lift()
    
    hwnd = win32gui.GetParent(window.winfo_id())
    
    # Add retry mechanism
    for _ in range(5):  # Try up to 5 times
        try:
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, 
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, 
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetForegroundWindow(hwnd)
            break
        except pywintypes.error:
            time.sleep(0.1)  # Wait a bit before retrying
    else:
        print("Failed to set window focus after multiple attempts")

    if speak_text:
        speaker.speak(speak_text)
    
    if focus_widget:
        if callable(focus_widget):
            window.after(100, focus_widget)
        else:
            window.after(100, focus_widget.focus_set)
