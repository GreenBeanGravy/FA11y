"""
Window utilities for FA11y
"""
import logging
import win32gui
import win32process
import psutil

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

def focus_window_by_process(process_name: str) -> bool:
    """
    Focus a window by finding its process name.
    More reliable for games like Fortnite that may have protected window titles.

    Args:
        process_name: Process name to search for (e.g., 'FortniteClient-Win64-Shipping.exe')

    Returns:
        bool: True if window found and focused, False otherwise
    """
    try:
        # Find all processes matching the name
        target_pids = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and process_name.lower() in proc.info['name'].lower():
                    target_pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not target_pids:
            logger.debug(f"No process found matching '{process_name}'")
            return False

        # Find windows belonging to these processes
        def callback(hwnd, found_windows):
            if win32gui.IsWindowVisible(hwnd):
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid in target_pids:
                        # Only add windows with non-empty titles (main windows)
                        title = win32gui.GetWindowText(hwnd)
                        if title:
                            found_windows.append(hwnd)
                except Exception:
                    pass
            return True

        found_windows = []
        win32gui.EnumWindows(callback, found_windows)

        if found_windows:
            # Use the first match (main window)
            hwnd = found_windows[0]

            # Restore if minimized
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE

            # Bring to front
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                # Try trick with Alt key
                try:
                    import win32com.client
                    shell = win32com.client.Dispatch("WScript.Shell")
                    shell.SendKeys('%')
                    win32gui.SetForegroundWindow(hwnd)
                except Exception:
                    pass

            logger.info(f"Focused window for process '{process_name}'")
            return True

        logger.debug(f"No visible windows found for process '{process_name}'")
        return False

    except Exception as e:
        logger.debug(f"Error focusing window by process '{process_name}': {e}")
        return False


def focus_fortnite() -> bool:
    """
    Focus the Fortnite window using multiple methods.

    Returns:
        bool: True if successfully focused, False otherwise
    """
    # Try by process name first (most reliable for Fortnite)
    if focus_window_by_process("FortniteClient-Win64-Shipping"):
        return True

    # Fallback to title search
    if focus_window("Fortnite"):
        return True

    logger.warning("Could not focus Fortnite window")
    return False


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
