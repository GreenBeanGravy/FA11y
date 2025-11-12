"""
Base UI Module for FA11y

Provides accessible UI framework using tkinter for FA11y applications.
Designed to work with screen readers and provide keyboard-accessible interfaces.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Optional, Any
from accessible_output2.outputs.auto import Auto

speaker = Auto()


class AccessibleUI:
    """
    Base class for accessible GUI applications using tkinter.

    Provides a framework for creating tabbed interfaces with accessible controls
    including buttons, labels, and other widgets that work well with screen readers.
    """

    def __init__(self, title: str = "FA11y Application", width: int = 600, height: int = 400):
        """
        Initialize the accessible UI.

        Args:
            title: Window title
            width: Window width in pixels
            height: Window height in pixels
        """
        self.title = title
        self.width = width
        self.height = height

        # Create main window
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry(f"{width}x{height}")

        # Storage for tabs and widgets
        self.tabs: Dict[str, tk.Frame] = {}
        self.notebook: Optional[ttk.Notebook] = None

        # Track widgets for each tab
        self.tab_widgets: Dict[str, list] = {}

    def setup(self):
        """
        Set up the UI. Override this method to create your interface.
        This method should call add_tab, add_button, add_label, etc.
        """
        pass

    def add_tab(self, name: str):
        """
        Add a new tab to the interface.

        Args:
            name: Name of the tab
        """
        if self.notebook is None:
            # Create notebook on first tab
            self.notebook = ttk.Notebook(self.root)
            self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Create frame for this tab
        frame = tk.Frame(self.notebook)
        self.tabs[name] = frame
        self.tab_widgets[name] = []

        # Add to notebook
        self.notebook.add(frame, text=name)

    def add_button(self, tab_name: str, text: str, command: Callable,
                   speech_hint: Optional[str] = None):
        """
        Add a button to the specified tab.

        Args:
            tab_name: Name of the tab to add the button to
            text: Button text
            command: Function to call when button is activated
            speech_hint: Optional hint to speak when button receives focus
        """
        if tab_name not in self.tabs:
            raise ValueError(f"Tab '{tab_name}' does not exist")

        tab_frame = self.tabs[tab_name]

        # Create button
        button = tk.Button(
            tab_frame,
            text=text,
            command=command,
            font=("Arial", 12),
            padx=10,
            pady=5
        )

        # Pack button with some spacing
        button.pack(fill=tk.X, padx=10, pady=5)

        # Add focus event for speech hint
        if speech_hint:
            def on_focus(event):
                self.speak(speech_hint)

            button.bind("<FocusIn>", on_focus)

        # Track widget
        self.tab_widgets[tab_name].append(button)

    def add_label(self, tab_name: str, text: str, **kwargs):
        """
        Add a label to the specified tab.

        Args:
            tab_name: Name of the tab to add the label to
            text: Label text
            **kwargs: Additional keyword arguments for tk.Label
        """
        if tab_name not in self.tabs:
            raise ValueError(f"Tab '{tab_name}' does not exist")

        tab_frame = self.tabs[tab_name]

        # Create label with defaults
        label_kwargs = {
            'font': ("Arial", 10),
            'padx': 10,
            'pady': 5
        }
        label_kwargs.update(kwargs)

        label = tk.Label(tab_frame, text=text, **label_kwargs)
        label.pack(fill=tk.X, padx=10, pady=5)

        # Track widget
        self.tab_widgets[tab_name].append(label)

    def add_entry(self, tab_name: str, label_text: str, **kwargs) -> tk.Entry:
        """
        Add a text entry field to the specified tab.

        Args:
            tab_name: Name of the tab to add the entry to
            label_text: Label text for the entry field
            **kwargs: Additional keyword arguments for tk.Entry

        Returns:
            The created Entry widget
        """
        if tab_name not in self.tabs:
            raise ValueError(f"Tab '{tab_name}' does not exist")

        tab_frame = self.tabs[tab_name]

        # Create container frame
        container = tk.Frame(tab_frame)
        container.pack(fill=tk.X, padx=10, pady=5)

        # Add label
        label = tk.Label(container, text=label_text, font=("Arial", 10))
        label.pack(side=tk.LEFT, padx=(0, 10))

        # Create entry with defaults
        entry_kwargs = {
            'font': ("Arial", 10),
        }
        entry_kwargs.update(kwargs)

        entry = tk.Entry(container, **entry_kwargs)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Track widget
        self.tab_widgets[tab_name].append(container)

        return entry

    def add_text(self, tab_name: str, **kwargs) -> tk.Text:
        """
        Add a multiline text widget to the specified tab.

        Args:
            tab_name: Name of the tab to add the text widget to
            **kwargs: Additional keyword arguments for tk.Text

        Returns:
            The created Text widget
        """
        if tab_name not in self.tabs:
            raise ValueError(f"Tab '{tab_name}' does not exist")

        tab_frame = self.tabs[tab_name]

        # Create text widget with defaults
        text_kwargs = {
            'font': ("Arial", 10),
            'wrap': tk.WORD,
            'height': 10
        }
        text_kwargs.update(kwargs)

        # Create frame with scrollbar
        container = tk.Frame(tab_frame)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        scrollbar = tk.Scrollbar(container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        text = tk.Text(container, yscrollcommand=scrollbar.set, **text_kwargs)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar.config(command=text.yview)

        # Track widget
        self.tab_widgets[tab_name].append(container)

        return text

    def speak(self, message: str):
        """
        Speak a message using text-to-speech.

        Args:
            message: Message to speak
        """
        try:
            speaker.speak(message, interrupt=True)
        except Exception as e:
            print(f"Speech error: {e}")

    def close(self):
        """Close the application window."""
        try:
            self.root.quit()
            self.root.destroy()
        except Exception as e:
            print(f"Error closing window: {e}")

    def run(self):
        """Run the application main loop."""
        # Speak window title on start
        self.speak(f"{self.title} window opened")

        # Start the main loop
        self.root.mainloop()


class AccessibleDialog(AccessibleUI):
    """
    Accessible dialog window.

    Similar to AccessibleUI but designed for dialog-style windows
    with OK/Cancel buttons.
    """

    def __init__(self, title: str = "Dialog", width: int = 500, height: int = 300):
        """
        Initialize the accessible dialog.

        Args:
            title: Dialog title
            width: Dialog width in pixels
            height: Dialog height in pixels
        """
        super().__init__(title, width, height)

        # Make it modal-like
        self.root.transient()
        self.root.grab_set()

        # Result storage
        self.result: Optional[Any] = None

    def add_ok_cancel_buttons(self, tab_name: str = None):
        """
        Add OK and Cancel buttons to the dialog.

        Args:
            tab_name: Name of the tab to add buttons to, or None for main window
        """
        # Create button frame
        if tab_name and tab_name in self.tabs:
            parent = self.tabs[tab_name]
        else:
            parent = self.root

        button_frame = tk.Frame(parent)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)

        # OK button
        ok_button = tk.Button(
            button_frame,
            text="OK",
            command=self.on_ok,
            font=("Arial", 12),
            width=10
        )
        ok_button.pack(side=tk.LEFT, padx=5)

        # Cancel button
        cancel_button = tk.Button(
            button_frame,
            text="Cancel",
            command=self.on_cancel,
            font=("Arial", 12),
            width=10
        )
        cancel_button.pack(side=tk.LEFT, padx=5)

        # Bind Enter and Escape
        self.root.bind('<Return>', lambda e: self.on_ok())
        self.root.bind('<Escape>', lambda e: self.on_cancel())

    def on_ok(self):
        """Handle OK button press. Override to customize behavior."""
        self.result = True
        self.close()

    def on_cancel(self):
        """Handle Cancel button press. Override to customize behavior."""
        self.result = False
        self.close()


def message_box(title: str, message: str, type: str = "info"):
    """
    Show a simple message box.

    Args:
        title: Message box title
        message: Message to display
        type: Type of message box (info, warning, error)
    """
    from tkinter import messagebox

    if type == "info":
        messagebox.showinfo(title, message)
    elif type == "warning":
        messagebox.showwarning(title, message)
    elif type == "error":
        messagebox.showerror(title, message)
    else:
        messagebox.showinfo(title, message)

    # Also speak the message
    speaker.speak(message, interrupt=True)


def ask_yes_no(title: str, question: str) -> bool:
    """
    Ask a yes/no question.

    Args:
        title: Dialog title
        question: Question to ask

    Returns:
        True if user clicked Yes, False otherwise
    """
    from tkinter import messagebox

    result = messagebox.askyesno(title, question)

    # Speak the result
    speaker.speak("Yes" if result else "No", interrupt=True)

    return result
