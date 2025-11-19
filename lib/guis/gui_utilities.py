"""
GUI utilities for FA11y based on NVDA
"""
import wx
import ctypes
import ctypes.wintypes
import time
from typing import Optional, Union, Any, Callable

# Constants from NVDA's guiHelper
BORDER_FOR_DIALOGS = 10
SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS = 10
SPACE_BETWEEN_BUTTONS_HORIZONTAL = 7
SPACE_BETWEEN_BUTTONS_VERTICAL = 5
SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL = 10
SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL = 3


class ButtonHelper:
    """Helper for managing groups of buttons with proper spacing"""
    
    def __init__(self, orientation):
        self._firstButton = True
        self._sizer = wx.BoxSizer(orientation)
        self._space = (
            SPACE_BETWEEN_BUTTONS_HORIZONTAL
            if orientation == wx.HORIZONTAL
            else SPACE_BETWEEN_BUTTONS_VERTICAL
        )
    
    @property
    def sizer(self):
        return self._sizer
    
    def addButton(self, *args, **kwargs):
        """Add a button to the group with automatic spacing"""
        wxButton = wx.Button(*args, **kwargs)
        if not self._firstButton:
            self._sizer.AddSpacer(self._space)
        self._sizer.Add(wxButton)
        self._firstButton = False
        return wxButton


class BoxSizerHelper:
    """Helper for managing wx.BoxSizer with automatic spacing"""
    
    def __init__(self, parent, orientation=None, sizer=None):
        self._parent = parent
        self.hasFirstItemBeenAdded = False
        
        if orientation and sizer:
            raise ValueError("Supply either orientation OR sizer, not both")
        
        if orientation:
            self.sizer = wx.BoxSizer(orientation)
        elif sizer:
            self.sizer = sizer
        else:
            raise ValueError("Either orientation or sizer must be supplied")
        
        self.dialogDismissButtonsAdded = False
    
    def addItem(self, item, **keywordArgs):
        """Add an item with automatic spacing"""
        toAdd = item
        shouldAddSpacer = self.hasFirstItemBeenAdded
        
        if isinstance(item, ButtonHelper):
            toAdd = item.sizer
            buttonBorderAmount = 5
            keywordArgs["border"] = buttonBorderAmount
            keywordArgs["flag"] = keywordArgs.get("flag", 0) | wx.ALL
            shouldAddSpacer = False
        elif isinstance(item, BoxSizerHelper):
            toAdd = item.sizer
        elif isinstance(item, wx.CheckBox):
            if self.sizer.GetOrientation() == wx.HORIZONTAL:
                keywordArgs["flag"] = keywordArgs.get("flag", 0) | wx.EXPAND
        
        if isinstance(toAdd, wx.StaticBoxSizer):
            keywordArgs["flag"] = keywordArgs.get("flag", 0) | wx.EXPAND
        
        if shouldAddSpacer:
            self.sizer.AddSpacer(SPACE_BETWEEN_VERTICAL_DIALOG_ITEMS)
        
        self.sizer.Add(toAdd, **keywordArgs)
        self.hasFirstItemBeenAdded = True
        return item
    
    def addLabeledControl(self, labelText, wxCtrlClass, **kwargs):
        """Create a labeled control with automatic association"""
        label = wx.StaticText(self._parent, label=labelText)
        
        # Add required styles for specific controls
        if wxCtrlClass == wx.TextCtrl and 'style' not in kwargs:
            kwargs['style'] = wx.TE_PROCESS_ENTER
        
        control = wxCtrlClass(self._parent, **kwargs)
        
        # Add navigation event handlers for text controls
        if wxCtrlClass == wx.TextCtrl:
            control.Bind(wx.EVT_CHAR_HOOK, self._onTextControlCharHook)
        elif wxCtrlClass in (wx.CheckBox, wx.Button):
            control.Bind(wx.EVT_CHAR_HOOK, self._onControlCharHook)
        
        # Simple horizontal layout for most controls
        if wxCtrlClass in (wx.TextCtrl, wx.Choice, wx.ComboBox, wx.SpinCtrl):
            sizer = wx.BoxSizer(wx.HORIZONTAL)
            sizer.Add(label, flag=wx.ALIGN_CENTER_VERTICAL)
            sizer.AddSpacer(SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL)
            sizer.Add(control)
        elif wxCtrlClass in (wx.ListCtrl, wx.ListBox, wx.TreeCtrl):
            # Vertical layout for list controls
            sizer = wx.BoxSizer(wx.VERTICAL)
            sizer.Add(label)
            sizer.AddSpacer(SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL)
            sizer.Add(control, flag=wx.EXPAND, proportion=1)
        else:
            # Default horizontal layout
            sizer = wx.BoxSizer(wx.HORIZONTAL)
            sizer.Add(label, flag=wx.ALIGN_CENTER_VERTICAL)
            sizer.AddSpacer(SPACE_BETWEEN_ASSOCIATED_CONTROL_HORIZONTAL)
            sizer.Add(control)
        
        if wxCtrlClass in (wx.ListCtrl, wx.ListBox, wx.TreeCtrl):
            self.addItem(sizer, flag=wx.EXPAND, proportion=1)
        else:
            self.addItem(sizer)
        
        return control
    
    def _onTextControlCharHook(self, event):
        """Handle char events for text controls"""
        key_code = event.GetKeyCode()
        
        # Allow TAB for navigation between areas
        if key_code == wx.WXK_TAB:
            event.Skip()
            return
        
        # Block up/down arrow keys from moving cursor, allow left/right
        if key_code in [wx.WXK_UP, wx.WXK_DOWN]:
            return  # Don't skip - block the event
        
        # Allow all other keys
        event.Skip()
    
    def _onControlCharHook(self, event):
        """Handle char events for controls to disable arrow navigation"""
        key_code = event.GetKeyCode()
        
        # Allow TAB for navigation between areas
        if key_code == wx.WXK_TAB:
            event.Skip()
            return
        
        # Block arrow keys from navigating between controls
        if key_code in [wx.WXK_UP, wx.WXK_DOWN, wx.WXK_LEFT, wx.WXK_RIGHT]:
            return  # Don't skip - block the event
        
        # Allow all other keys
        event.Skip()
    
    def addDialogDismissButtons(self, buttons, separated=False):
        """Add dialog dismiss buttons (OK/Cancel etc.) - DEPRECATED"""
        # This method is now deprecated and does nothing
        # All GUIs should handle their own closing logic
        pass


class AccessibleDialog(wx.Dialog):
    """Base dialog class with accessibility helpers"""

    def __init__(self, parent, title="", helpId=""):
        super().__init__(parent, title=title)
        self.helpId = helpId

        # Make dialog resizable by default
        style = self.GetWindowStyleFlag() | wx.RESIZE_BORDER
        self.SetWindowStyleFlag(style)
    
    def makeSettings(self):
        """Override in subclasses to create dialog content"""
        pass
    
    def postInit(self):
        """Override in subclasses for post-initialization setup"""
        pass
    
    def setupDialog(self):
        """Standard dialog setup following NVDA patterns"""
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        settingsSizer = BoxSizerHelper(self, orientation=wx.VERTICAL)
        
        # Let subclass populate the dialog
        self.makeSettings(settingsSizer)
        
        mainSizer.Add(
            settingsSizer.sizer,
            border=BORDER_FOR_DIALOGS,
            flag=wx.ALL | wx.EXPAND,
            proportion=1
        )
        
        self.SetSizer(mainSizer)
        mainSizer.Fit(self)
        
        # Center on screen and ensure proper sizing
        self.CentreOnScreen()
        
        # Force focus and center mouse
        wx.CallAfter(self._finalizeDialog)
        
        # Post-initialization
        self.postInit()
    
    def _finalizeDialog(self):
        """Finalize dialog setup with focus and mouse positioning"""
        # Force window to front and focus
        force_focus_window(self)
        
        # Center mouse in dialog
        center_mouse_in_window(self)
        
        # Set focus to first control
        self.setFocusToFirstControl()
    
    def setFocusToFirstControl(self):
        """Set focus to the first suitable control"""
        def findFirstControl(parent):
            for child in parent.GetChildren():
                if isinstance(child, (wx.Button, wx.TextCtrl, wx.Choice, wx.CheckBox, wx.ListCtrl, wx.SpinCtrl, wx.Notebook)):
                    return child
                # Recursively search in sizers
                if hasattr(child, 'GetChildren'):
                    result = findFirstControl(child)
                    if result:
                        return result
            return None

        firstControl = findFirstControl(self)
        if firstControl:
            firstControl.SetFocus()


def messageBox(message, caption="", style=wx.OK, parent=None):
    """Simple message box wrapper"""
    if parent is None:
        parent = wx.GetActiveWindow()
    
    return wx.MessageBox(message, caption, style, parent)


def center_mouse_in_window(window):
    """Center the mouse cursor in the given window"""
    try:
        if not window:
            return

        # Check if we're on the main thread - if not, schedule on main thread
        if not wx.IsMainThread():
            wx.CallAfter(center_mouse_in_window, window)
            return

        # Get window position and size
        pos = window.GetPosition()
        size = window.GetSize()

        # Calculate center point
        center_x = pos.x + size.width // 2
        center_y = pos.y + size.height // 2

        # Move mouse to center using Windows API for precision
        ctypes.windll.user32.SetCursorPos(center_x, center_y)

    except Exception as e:
        print(f"Error centering mouse: {e}")


def force_focus_window(window, speak_text: Optional[str] = None, focus_widget: Optional[Union[Callable, Any]] = None):
    """Force focus on a window - robust version based on NVDA patterns"""
    try:
        if not window:
            return

        # Check if we're on the main thread - if not, schedule on main thread
        if not wx.IsMainThread():
            wx.CallAfter(force_focus_window, window, speak_text, focus_widget)
            return

        # Get window handle
        hwnd = window.GetHandle()
        
        # Ensure window is shown first
        window.Show(True)
        
        # Multiple attempts at forcing focus with increasing aggression
        for attempt in range(8):
            try:
                # Progressive focus methods
                if attempt == 0:
                    # Gentle approach
                    window.Raise()
                    window.SetFocus()
                elif attempt == 1:
                    # More aggressive
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                elif attempt == 2:
                    # Even more aggressive
                    ctypes.windll.user32.BringWindowToTop(hwnd)
                    ctypes.windll.user32.SetActiveWindow(hwnd)
                elif attempt == 3:
                    # Force with AttachThreadInput
                    foreground_hwnd = ctypes.windll.user32.GetForegroundWindow()
                    if foreground_hwnd != hwnd:
                        foreground_thread = ctypes.windll.user32.GetWindowThreadProcessId(foreground_hwnd, None)
                        our_thread = ctypes.windll.kernel32.GetCurrentThreadId()
                        if foreground_thread != our_thread:
                            ctypes.windll.user32.AttachThreadInput(our_thread, foreground_thread, True)
                            ctypes.windll.user32.SetForegroundWindow(hwnd)
                            ctypes.windll.user32.AttachThreadInput(our_thread, foreground_thread, False)
                else:
                    # Nuclear option - use SetWindowPos with TOPMOST
                    HWND_TOPMOST = -1
                    HWND_NOTOPMOST = -2
                    SWP_NOMOVE = 0x0002
                    SWP_NOSIZE = 0x0001
                    SWP_SHOWWINDOW = 0x0040
                    
                    # Set topmost temporarily
                    ctypes.windll.user32.SetWindowPos(
                        hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
                    )
                    
                    # Then remove topmost but keep on top
                    ctypes.windll.user32.SetWindowPos(
                        hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
                    )
                    
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                    ctypes.windll.user32.SetFocus(hwnd)
                
                # Also use wx methods
                window.Raise()
                window.SetFocus()
                
                # Check if we succeeded
                current_foreground = ctypes.windll.user32.GetForegroundWindow()
                if current_foreground == hwnd:
                    break
                    
                # Progressive delay
                time.sleep(0.02 * (attempt + 1))
                
            except Exception as e:
                print(f"Focus attempt {attempt + 1} failed: {e}")
                if attempt < 7:  # Don't sleep on last attempt
                    time.sleep(0.05)
        
        # Ensure window style allows proper interaction
        style = window.GetWindowStyleFlag()
        if not (style & wx.STAY_ON_TOP):
            window.SetWindowStyleFlag(style | wx.STAY_ON_TOP)
            
        # Remove stay on top after focus is established
        wx.CallLater(200, lambda: _remove_stay_on_top(window))
        
        # Force refresh
        window.Refresh()
        window.Update()
        
        if speak_text:
            # In a real implementation, you'd use your speech system here
            pass
        
        if focus_widget:
            if callable(focus_widget):
                wx.CallAfter(focus_widget)
            else:
                wx.CallAfter(focus_widget.SetFocus)
                
    except Exception as e:
        print(f"Error focusing window: {e}")


def _remove_stay_on_top(window):
    """Helper to remove stay on top flag"""
    try:
        if window and not window.IsBeingDeleted():
            style = window.GetWindowStyleFlag() & ~wx.STAY_ON_TOP
            window.SetWindowStyleFlag(style)
            window.Refresh()
    except:
        pass


def ensure_window_focus_and_center_mouse(window):
    """Comprehensive function to ensure window focus and center mouse"""
    try:
        if not window:
            return

        # Check if we're on the main thread - if not, schedule on main thread
        if not wx.IsMainThread():
            wx.CallAfter(ensure_window_focus_and_center_mouse, window)
            return

        # Force focus first
        force_focus_window(window)

        # Small delay to ensure window is positioned
        wx.CallAfter(lambda: center_mouse_in_window(window))

    except Exception as e:
        print(f"Error ensuring window focus and centering mouse: {e}")


# ============================================================================
# Thread-Safe wx.App Management and GUI Launching
# ============================================================================

import threading
import logging

logger = logging.getLogger(__name__)

# Global wx.App instance (created on main thread)
_global_app = None
_app_lock = threading.Lock()


def initialize_global_wx_app():
    """
    Initialize global wx.App on main thread during FA11y startup.
    MUST be called from the main thread only.

    Returns:
        wx.App instance

    Raises:
        RuntimeError: If called from background thread
    """
    global _global_app

    if not wx.IsMainThread():
        raise RuntimeError("initialize_global_wx_app() must be called from main thread")

    with _app_lock:
        if _global_app is None:
            _global_app = wx.App(False)
            logger.info("Created global wx.App instance on main thread")
        return _global_app


def get_wx_app():
    """
    Thread-safe way to get wx.App instance.
    Returns existing app or creates one if on main thread.

    Returns:
        wx.App instance or None if on background thread and no app exists
    """
    global _global_app

    with _app_lock:
        if _global_app is not None:
            return _global_app

        # Try to get existing app
        app = wx.GetApp()
        if app is not None:
            _global_app = app
            return app

        # Only create new app if on main thread
        if wx.IsMainThread():
            _global_app = wx.App(False)
            logger.info("Created wx.App on main thread")
            return _global_app
        else:
            logger.error("Cannot create wx.App from background thread")
            return None


def run_on_main_thread(func, *args, **kwargs):
    """
    Run a function on the main thread.
    If already on main thread, run immediately.
    If on background thread, schedule with wx.CallAfter().

    Args:
        func: Function to run
        *args, **kwargs: Arguments to pass to function

    Returns:
        Result of function (only if called from main thread, else None)
    """
    if wx.IsMainThread():
        # Already on main thread, run immediately
        logger.debug(f"Running {func.__name__} on main thread (already on main)")
        return func(*args, **kwargs)
    else:
        # On background thread, schedule on main thread
        logger.debug(f"Scheduling {func.__name__} on main thread from background")
        wx.CallAfter(func, *args, **kwargs)
        return None  # Can't return result from async call


def launch_gui_thread_safe(launch_func, *args, **kwargs):
    """
    Thread-safe wrapper for GUI launch functions.
    Ensures GUI operations run on main thread.

    This function can be called from any thread. If called from a background
    thread (e.g., key_listener thread), it will schedule the GUI launch on
    the main thread using wx.CallAfter().

    Args:
        launch_func: The GUI launch function to call
        *args, **kwargs: Arguments to pass to launch function

    Example:
        # From background thread (key_listener):
        launch_gui_thread_safe(launch_config_gui, config_obj, update_callback)
    """
    # Ensure wx.App exists
    app = get_wx_app()
    if app is None:
        logger.error(f"Cannot launch GUI: No wx.App available")
        try:
            from accessible_output2.outputs.auto import Auto
            speaker = Auto()
            speaker.speak("Error: Cannot open GUI")
        except:
            pass
        return

    # Run on main thread
    run_on_main_thread(launch_func, *args, **kwargs)