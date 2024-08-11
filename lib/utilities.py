import win32gui
import win32con
from accessible_output2.outputs.auto import Auto

speaker = Auto()

def force_focus_window(window, speak_text=None, focus_widget=None):
    window.deiconify()  # Ensure the window is not minimized
    window.attributes('-topmost', True)  # Set the window to be topmost
    window.update()  # Update the window
    window.lift()  # Raise the window to the top
    
    # Use win32gui to force focus
    hwnd = win32gui.GetParent(window.winfo_id())
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, 
                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
    win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, 
                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
    win32gui.SetForegroundWindow(hwnd)

    if speak_text:
        speaker.speak(speak_text)
    
    if focus_widget:
        if callable(focus_widget):
            window.after(100, focus_widget)
        else:
            window.after(100, focus_widget.focus_set)