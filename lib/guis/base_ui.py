"""
Base UI framework for FA11y
Provides a consistent, accessible UI foundation for all GUIs
"""
import os
import sys
import logging
import threading
import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Callable, Optional, Any, Union, Tuple

# Initialize logger
logger = logging.getLogger(__name__)

class AccessibleUI:
    """Base class for accessible GUIs"""
    
    def __init__(self, title: str = "FA11y", icon_path: Optional[str] = None):
        """Initialize the accessible UI
        
        Args:
            title: Window title
            icon_path: Path to window icon
        """
        self.title = title
        self.icon_path = icon_path
        
        # Speech output
        self.speaker = None
        self._init_speech()
        
        # UI components
        self.root = None
        self.notebook = None
        self.tabs = {}
        self.widgets = {}
        self.variables = {}
        
        # State tracking
        self.currently_editing = None
        self.previous_value = ''
        
        # Thread control
        self.ui_thread = None
        self.stop_event = threading.Event()
        
        # Flag to track if UI is set up
        self._ui_setup = False
    
    def _init_speech(self) -> None:
        """Initialize speech output"""
        try:
            from accessible_output2.outputs.auto import Auto
            self.speaker = Auto()
            logger.info("Speech output initialized for UI")
        except ImportError:
            logger.warning("accessible_output2 module not found, speech output disabled")
            self.speaker = None
        except Exception as e:
            logger.error(f"Error initializing speech output: {e}")
            self.speaker = None
    
    def speak(self, text: str) -> None:
        """Speak text using screen reader
        
        Args:
            text: Text to speak
        """
        if self.speaker:
            try:
                self.speaker.speak(text)
                logger.debug(f"Speaking: {text}")
            except Exception as e:
                logger.error(f"Error speaking text: {e}")
    
    def setup_ui(self) -> None:
        """Set up the UI components"""
        # Check if already set up
        if self._ui_setup:
            return
        
        # Reset closing flag if it exists
        if hasattr(self, '_closing'):
            self._closing = False
            
        # Create root window
        self.root = tk.Tk()
        self.root.withdraw()  # Hide window until fully set up
        self.root.title(self.title)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        
        # Set window icon if provided
        if self.icon_path and os.path.exists(self.icon_path):
            try:
                icon = tk.PhotoImage(file=self.icon_path)
                self.root.iconphoto(True, icon)
            except Exception as e:
                logger.error(f"Error setting window icon: {e}")
        
        # Create notebook (tabbed interface)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill='both')
        
        # Set up key bindings
        self.setup_bindings()
        
        # Mark as set up
        self._ui_setup = True
        
        # Schedule showing the window after all pending events
        self.root.after(10, self.root.deiconify)
    
    def setup_bindings(self) -> None:
        """Set up key bindings"""
        # Navigation bindings
        self.root.bind_all('<Up>', self.navigate)
        self.root.bind_all('<Down>', self.navigate)
        self.root.bind_all('<Return>', self.on_enter)
        self.root.bind_all('<Escape>', self.on_escape)
        
        # Tab navigation
        self.root.bind('<Tab>', self.change_tab)
        self.root.bind('<Shift-Tab>', self.change_tab)
        
        # Notebook tab change event
        if self.notebook:
            self.notebook.bind('<<NotebookTabChanged>>', self.on_tab_change)
    
    def add_tab(self, name: str) -> ttk.Frame:
        """Add a new tab to the interface
        
        Args:
            name: Tab name
            
        Returns:
            ttk.Frame: Tab frame
        """
        # Ensure UI is set up before adding tabs
        if not self._ui_setup:
            self.setup_ui()
            
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=name)
        self.tabs[name] = tab
        self.widgets[name] = []
        self.variables[name] = {}
        return tab
    
    def add_button(self, tab_name: str, text: str, command: Callable[[], None], 
                  custom_speech: Optional[str] = None) -> ttk.Button:
        """Add a button to a tab
        
        Args:
            tab_name: Name of tab to add to
            text: Button text
            command: Button command
            custom_speech: Custom speech for button
            
        Returns:
            ttk.Button: Created button
        """
        button = ttk.Button(self.tabs[tab_name], text=text, command=command)
        button.pack(fill='x', padx=5, pady=5)
        
        if custom_speech is not None:
            def on_focus(event):
                self.speak(custom_speech)
                return "break"
            button.bind('<FocusIn>', on_focus)
            button.custom_speech = custom_speech
        
        self.widgets[tab_name].append(button)
        return button
    
    def add_checkbox(self, tab_name: str, text: str, initial_value: bool = False,
                    description: str = "") -> ttk.Checkbutton:
        """Add a checkbox to a tab
        
        Args:
            tab_name: Name of tab to add to
            text: Checkbox text
            initial_value: Initial checkbox state
            description: Description for screen readers
            
        Returns:
            ttk.Checkbutton: Created checkbox
        """
        var = tk.BooleanVar(value=initial_value)
        checkbox = ttk.Checkbutton(self.tabs[tab_name], text=text, variable=var)
        checkbox.pack(fill='x', padx=5, pady=5)
        self.widgets[tab_name].append(checkbox)
        self.variables[tab_name][text] = var
        checkbox.description = description
        return checkbox
    
    def add_entry(self, tab_name: str, text: str, initial_value: str = "",
                 description: str = "") -> ttk.Entry:
        """Add a text entry field to a tab
        
        Args:
            tab_name: Name of tab to add to
            text: Label text
            initial_value: Initial value
            description: Description for screen readers
            
        Returns:
            ttk.Entry: Created entry field
        """
        frame = ttk.Frame(self.tabs[tab_name])
        frame.pack(fill='x', padx=5, pady=5)

        label = ttk.Label(frame, text=text)
        label.pack(side='left')

        var = tk.StringVar(value=initial_value)
        entry = ttk.Entry(frame, textvariable=var, state='readonly')
        entry.pack(side='right', expand=True, fill='x')

        self.widgets[tab_name].append(entry)
        self.variables[tab_name][text] = var
        entry.description = description
        return entry
    
    def add_keybind(self, tab_name: str, text: str, initial_value: str = "",
                   description: str = "") -> ttk.Entry:
        """Add a keybind entry to a tab
        
        Args:
            tab_name: Name of tab to add to
            text: Label text
            initial_value: Initial value
            description: Description for screen readers
            
        Returns:
            ttk.Entry: Created keybind entry
        """
        entry = self.add_entry(tab_name, text, initial_value, description)
        entry.bind('<FocusIn>', lambda e: None)
        entry.is_keybind = True
        return entry
    
    def add_combobox(self, tab_name: str, text: str, values: List[str], 
                    initial_value: Optional[str] = None,
                    description: str = "") -> ttk.Combobox:
        """Add a dropdown combobox to a tab
        
        Args:
            tab_name: Name of tab to add to
            text: Label text
            values: List of dropdown values
            initial_value: Initial selected value
            description: Description for screen readers
            
        Returns:
            ttk.Combobox: Created combobox
        """
        frame = ttk.Frame(self.tabs[tab_name])
        frame.pack(fill='x', padx=5, pady=5)

        label = ttk.Label(frame, text=text)
        label.pack(side='left')

        var = tk.StringVar()
        if initial_value is not None and initial_value in values:
            var.set(initial_value)
        elif values:
            var.set(values[0])
            
        combo = ttk.Combobox(frame, textvariable=var, values=values, state="readonly")
        combo.pack(side='right', expand=True, fill='x')

        self.widgets[tab_name].append(combo)
        self.variables[tab_name][text] = var
        combo.description = description
        return combo
    
    def add_listbox(self, tab_name: str, values: List[str], height: int = 5,
                   description: str = "") -> tk.Listbox:
        """Add a listbox to a tab
        
        Args:
            tab_name: Name of tab to add to
            values: List of items
            height: Number of visible items
            description: Description for screen readers
            
        Returns:
            tk.Listbox: Created listbox
        """
        frame = ttk.Frame(self.tabs[tab_name])
        frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        var = tk.StringVar(value=values)
        listbox = tk.Listbox(
            frame, 
            listvariable=var,
            height=height,
            selectmode=tk.SINGLE,
            yscrollcommand=scrollbar.set
        )
        listbox.pack(side=tk.LEFT, fill='both', expand=True)
        scrollbar.config(command=listbox.yview)

        self.widgets[tab_name].append(listbox)
        self.variables[tab_name]["listbox"] = var
        listbox.description = description
        
        # Add custom handling for listbox navigation
        def on_listbox_key(event):
            if event.keysym in ('Up', 'Down'):
                # Let the listbox handle these
                return
            elif event.keysym == 'Return':
                # Handle selection
                if listbox.curselection():
                    selected = listbox.get(listbox.curselection())
                    self.speak(f"Selected {selected}")
                return "break"
                
        listbox.bind('<Key>', on_listbox_key)
        
        # Announce selection changes
        def on_selection_change(event):
            if listbox.curselection():
                selected = listbox.get(listbox.curselection())
                self.speak(selected)
                
        listbox.bind('<<ListboxSelect>>', on_selection_change)
        
        return listbox
    
    def add_label(self, tab_name: str, text: str) -> ttk.Label:
        """Add a label to a tab
        
        Args:
            tab_name: Name of tab to add to
            text: Label text
            
        Returns:
            ttk.Label: Created label
        """
        label = ttk.Label(self.tabs[tab_name], text=text)
        label.pack(fill='x', padx=5, pady=5)
        return label
    
    def add_separator(self, tab_name: str) -> ttk.Separator:
        """Add a horizontal separator to a tab
        
        Args:
            tab_name: Name of tab to add to
            
        Returns:
            ttk.Separator: Created separator
        """
        separator = ttk.Separator(self.tabs[tab_name], orient='horizontal')
        separator.pack(fill='x', padx=5, pady=10)
        return separator
    
    def navigate(self, event) -> str:
        """Handle up/down navigation between widgets
        
        Args:
            event: Key event
            
        Returns:
            str: "break" to prevent default handling
        """
        if self.currently_editing:
            return "break"

        current_widget = self.root.focus_get()
        current_tab = self.notebook.tab(self.notebook.select(), "text")
        current_tab_widgets = self.widgets[current_tab]

        try:
            current_index = current_tab_widgets.index(current_widget)
        except ValueError:
            current_index = -1

        if event.keysym == 'Down':
            next_index = (current_index + 1) % len(current_tab_widgets)
        else:  # Up
            next_index = (current_index - 1) % len(current_tab_widgets)

        next_widget = current_tab_widgets[next_index]
        next_widget.focus_set()

        # Announce widget info
        widget_info = self.get_widget_info(next_widget)
        if widget_info:
            self.speak(widget_info)
            
        return "break"
    
    def on_tab_change(self, event) -> None:
        """Handle tab change events
        
        Args:
            event: Notebook tab changed event
        """
        tab = event.widget.tab('current')['text']
        self.speak(f"Switched to {tab} tab")
        
        # Focus first widget in tab
        if self.widgets[tab]:
            first_widget = self.widgets[tab][0]
            first_widget.focus_set()
            
            # Announce widget info
            widget_info = self.get_widget_info(first_widget)
            if widget_info:
                self.speak(widget_info)
    
    def change_tab(self, event) -> str:
        """Handle tab switching
        
        Args:
            event: Key event
            
        Returns:
            str: "break" to prevent default handling
        """
        if self.currently_editing:
            self.speak("Please finish editing before changing tabs")
            return "break"
            
        current = self.notebook.index(self.notebook.select())
        if event.state & 1:  # Shift is pressed
            next_tab = (current - 1) % self.notebook.index('end')
        else:
            next_tab = (current + 1) % self.notebook.index('end')
            
        self.notebook.select(next_tab)
        return "break"
    
    def on_enter(self, event) -> str:
        """Handle Enter key press
        
        Args:
            event: Key event
            
        Returns:
            str: "break" to prevent default handling
        """
        current_widget = self.root.focus_get()
        
        if isinstance(current_widget, ttk.Checkbutton):
            current_widget.invoke()
            self.speak(f"{current_widget.cget('text')} {'checked' if current_widget.instate(['selected']) else 'unchecked'}")
            
        elif isinstance(current_widget, ttk.Entry):
            if self.currently_editing == current_widget:
                self.finish_editing(current_widget)
            else:
                if getattr(current_widget, 'is_keybind', False):
                    self.capture_keybind(current_widget)
                else:
                    self.start_editing(current_widget)
                    
        elif isinstance(current_widget, ttk.Button):
            current_widget.invoke()
            
        elif isinstance(current_widget, ttk.Combobox):
            current_widget.event_generate('<Down>')
            
        return "break"
    
    def on_escape(self, event) -> str:
            """Handle Escape key press
            
            Args:
                event: Key event
                
            Returns:
                str: "break" to prevent default handling
            """
            if self.currently_editing:
                widget = self.currently_editing
                widget.config(state='readonly')
                widget.delete(0, tk.END)
                widget.insert(0, self.previous_value)
                self.currently_editing = None
                self.speak("Cancelled editing, value restored to previous.")
            else:
                # If we have save_and_close, use it, otherwise just close the window
                if hasattr(self, 'save_and_close') and callable(self.save_and_close):
                    self.save_and_close()
                else:
                    # Just close the window without saving
                    self.close()
                
            return "break"
    
    def get_widget_info(self, widget: tk.Widget) -> str:
        """Get speaking information for a widget
        
        Args:
            widget: Widget to get info for
            
        Returns:
            str: Widget information for speech
        """
        if isinstance(widget, ttk.Button):
            if hasattr(widget, 'custom_speech'):
                return widget.custom_speech
            return f"{widget.cget('text')}, button"
            
        elif isinstance(widget, ttk.Checkbutton):
            description = getattr(widget, 'description', '')
            info = f"{widget.cget('text')}, {'checked' if widget.instate(['selected']) else 'unchecked'}, press Enter to toggle"
            if description:
                info += f". {description}"
            return info
            
        elif isinstance(widget, ttk.Entry):
            key = widget.master.winfo_children()[0].cget('text')
            description = getattr(widget, 'description', '')
            is_keybind = getattr(widget, 'is_keybind', False)
            
            info = f"{key}, current value: {widget.get() or 'No value set'}"
            
            if is_keybind:
                info += ", press Enter to capture new keybind"
            else:
                info += ", press Enter to edit"
                
            if description:
                info += f". {description}"
                
            return info
            
        elif isinstance(widget, ttk.Combobox):
            key = widget.master.winfo_children()[0].cget('text')
            description = getattr(widget, 'description', '')
            
            info = f"{key}, current value: {widget.get() or 'No value set'}, press Enter to open dropdown"
            
            if description:
                info += f". {description}"
                
            return info
            
        elif isinstance(widget, tk.Listbox):
            description = getattr(widget, 'description', '')
            selection = widget.curselection()
            
            if selection:
                selected_item = widget.get(selection[0])
                info = f"Listbox, selected: {selected_item}"
            else:
                info = "Listbox, no selection"
                
            if description:
                info += f". {description}"
                
            return info
            
        return "Unknown widget"
    
    def start_editing(self, widget: ttk.Entry) -> None:
        """Start editing a text entry widget
        
        Args:
            widget: Entry widget to edit
        """
        self.currently_editing = widget
        self.previous_value = widget.get()
        widget.config(state='normal')
        widget.delete(0, tk.END)
        self.speak(f"Editing {widget.master.winfo_children()[0].cget('text')}. "
                   f"Enter new value and press Enter when done.")
    
    def finish_editing(self, widget: ttk.Entry) -> None:
        """Complete editing of a text entry widget
        
        Args:
            widget: Entry widget being edited
        """
        self.currently_editing = None
        widget.config(state='readonly')
        new_value = widget.get()
        key = widget.master.winfo_children()[0].cget('text')
        
        if new_value == '':
            # Handle empty value by reverting to previous
            widget.delete(0, tk.END)
            widget.insert(0, self.previous_value)
            self.speak(f"No value entered. {key} reset to previous value.")
        else:
            # Update variable
            current_tab = self.notebook.tab(self.notebook.select(), "text")
            self.variables[current_tab][key].set(new_value)
            self.speak(f"{key} set to {new_value}")
    
    def capture_keybind(self, widget: ttk.Entry) -> None:
        """Start capturing a new keybind
        
        Args:
            widget: Entry widget for keybind
        """
        widget.config(state='normal')
        widget.delete(0, tk.END)
        self.speak("Press any key to set the keybind. Press Escape to cancel.")
        
        # Store the key handler
        def capture_key(event):
            # Skip tab, escape, shift+tab, and return keys
            if event.keysym.lower() in ['tab', 'escape', 'return']:
                return "break"
                
            # Use the key
            key = event.keysym
            
            # Update entry and variable
            widget.delete(0, tk.END)
            widget.insert(0, key)
            
            # Update variable
            current_tab = self.notebook.tab(self.notebook.select(), "text")
            key_name = widget.master.winfo_children()[0].cget('text')
            self.variables[current_tab][key_name].set(key)
            
            # Speak confirmation
            self.speak(f"Keybind for {key_name} set to {key}")
            
            # Switch back to readonly
            widget.config(state='readonly')
            
            # Remove the binding
            self.root.unbind('<Key>', self.key_binding_id)
            
            return "break"
            
        # Add the binding
        self.key_binding_id = self.root.bind('<Key>', capture_key)
    
    def run(self) -> None:
        """Run the UI event loop in the current thread"""
        # Ensure UI is set up
        if not self._ui_setup:
            self.setup_ui()
        
        # Prevent multiple mainloop calls
        if hasattr(self, '_mainloop_running') and self._mainloop_running:
            logger.warning("UI mainloop already running")
            return
            
        self._mainloop_running = True
        
        try:
            # Make sure we're not in a closing state
            if hasattr(self, '_closing') and self._closing:
                logger.warning("UI is closing, cannot run mainloop")
                return
                
            # Clear stop event
            self.stop_event.clear()
            
            # Run the mainloop
            logger.debug(f"Starting UI mainloop for {self.title}")
            self.root.mainloop()
        except Exception as e:
            logger.error(f"Error in UI mainloop: {e}")
        finally:
            self._mainloop_running = False
    
    def start(self) -> None:
        """Start the UI in a separate thread"""
        if self.ui_thread and self.ui_thread.is_alive():
            logger.warning("UI already running")
            return
            
        def run_ui():
            """Run UI in thread"""
            try:
                if not self._ui_setup:
                    self.setup_ui()
                    
                while not self.stop_event.is_set():
                    self.root.update()
                    self.root.update_idletasks()
                    # Short sleep to prevent high CPU usage
                    self.stop_event.wait(0.01)
            except tk.TclError:
                # Window was closed
                pass
            except Exception as e:
                logger.error(f"Error in UI thread: {e}")
            finally:
                # Ensure root is destroyed
                try:
                    if self.root:
                        self.root.destroy()
                except:
                    pass
        
        self.stop_event.clear()
        self.ui_thread = threading.Thread(target=run_ui)
        self.ui_thread.daemon = True
        self.ui_thread.start()
    
    def close(self) -> None:
        """Close the UI"""
        # Add more detailed logging
        import traceback
        logger.info(f"Closing UI: {self.title}")
        
        # Prevent multiple close calls
        if hasattr(self, '_closing') and self._closing:
            logger.debug("UI is already closing, ignoring duplicate close request")
            return
            
        self._closing = True
        self.stop_event.set()
        
        # Give UI time to clean up if needed
        if self.root:
            try:
                # Safety check - make sure the UI exists before destroying
                if self.root.winfo_exists():
                    # If in another thread, schedule destruction via after
                    if threading.current_thread() is threading.main_thread():
                        # Small delay to allow pending events to process
                        self.root.after(100, self._destroy_root)
                    else:
                        # Need to be more careful in threaded context
                        self.root.after(100, self._destroy_root)
            except tk.TclError as e:
                logger.error(f"TclError when closing UI: {e}")
            except Exception as e:
                logger.error(f"Unexpected error closing UI: {e}")
                logger.error(traceback.format_exc())
    
    def _destroy_root(self):
        """Safely destroy the root window"""
        try:
            if self.root and self.root.winfo_exists():
                self.root.destroy()
        except Exception as e:
            logger.error(f"Error destroying root window: {e}")
