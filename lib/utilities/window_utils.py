"""
Window utilities for FA11y
"""
import logging
import win32gui

logger = logging.getLogger(__name__)

def get_active_window_title():
    """
    Get the title of the currently active window
    
    Returns:
        str: Title of the active window, or empty string if failed
    """
    try:
        window = win32gui.GetForegroundWindow()
        return win32gui.GetWindowText(window)
    except Exception as e:
        logger.debug(f"Error getting active window title: {e}")
        return ""

def focus_window(title_substring: str) -> bool:
    """
    Focus a window with a title containing the given substring.
    
    Args:
        title_substring: Substring to search for in window titles
        
    Returns:
        bool: True if window found and focused, False otherwise
    """
    try:
        def callback(hwnd, found_windows):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title_substring.lower() in title.lower():
                    found_windows.append(hwnd)
            return True

        found_windows = []
        win32gui.EnumWindows(callback, found_windows)

        if found_windows:
            # Use the first match
            hwnd = found_windows[0]
            
            # Restore if minimized
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, 9) # SW_RESTORE
            
            # Bring to front
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                # Sometimes SetForegroundWindow fails if we're not in foreground
                # Try a trick with Alt key
                import win32com.client
                shell = win32com.client.Dispatch("WScript.Shell")
                shell.SendKeys('%')
                win32gui.SetForegroundWindow(hwnd)
                
            return True
            
        return False
        
    except Exception as e:
        logger.debug(f"Error focusing window '{title_substring}': {e}")
        return False
