import tkinter as tk
from tkinter import ttk
from accessible_output2.outputs.auto import Auto
from typing import Dict, List, Callable, Optional, Union
import configparser
import os
import re
from lib.input_handler import is_key_pressed, get_pressed_key, VK_KEYS

from lib.spatial_audio import SpatialAudio

class AccessibleUIBackend:
    def __init__(self, title: str = "Accessible Menu", config_file: Optional[str] = None, 
                 default_config: Optional[configparser.ConfigParser] = None):
        self.root = tk.Tk()
        self.root.title(title)
        self.root.attributes('-topmost', True)

        self.speaker = Auto()
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill='both')

        self.tabs: Dict[str, ttk.Frame] = {}
        self.widgets: Dict[str, List[tk.Widget]] = {}
        self.variables: Dict[str, Dict[str, tk.Variable]] = {}
        self.keybind_map: Dict[str, str] = {}
        self.currently_editing: Optional[tk.Widget] = None
        self.capturing_keybind = False
        self.config_file = config_file
        self.config = self.load_config()
        self.default_config = default_config
        self.previous_value = ''

        self.root.bind_all('<Up>', self.navigate)
        self.root.bind_all('<Down>', self.navigate)
        self.root.bind_all('<Return>', self.on_enter)
        self.root.bind_all('<Escape>', self.on_escape)
        self.root.bind('<Tab>', self.change_tab)
        self.root.bind('<Shift-Tab>', self.change_tab)
        self.root.bind_all('<Key>', self.on_key)

        self.notebook.bind('<<NotebookTabChanged>>', self.on_tab_change)

    def speak(self, text: str) -> None:
        """Speak text using the screen reader."""
        self.speaker.speak(text)

    def load_config(self) -> configparser.ConfigParser:
        """Load configuration from file."""
        config = configparser.ConfigParser()
        config.optionxform = str  # Preserve case
        if self.config_file and os.path.exists(self.config_file):
            config.read(self.config_file)
        return config

    def save_config(self) -> None:
        """Save configuration to file."""
        if self.config_file:
            with open(self.config_file, 'w', encoding='utf-8') as configfile:
                self.config.write(configfile)

    def extract_value_and_description(self, value_string: str) -> tuple:
        """Extract value and description from a config string."""
        value_string = value_string.strip()
        if '"' in value_string:
            quote_pos = value_string.find('"')
            value = value_string[:quote_pos].strip()
            description = value_string[quote_pos+1:].rstrip('"')
        else:
            value = value_string
            description = ''
        return value, description

    def add_tab(self, name: str) -> None:
        """Add a new tab to the interface."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=name)
        self.tabs[name] = tab
        self.widgets[name] = []
        self.variables[name] = {}
        if name not in self.config.sections():
            self.config.add_section(name)

    def add_button(self, tab_name: str, text: str, command: Callable[[], None], 
                  custom_speech: Optional[str] = None) -> None:
        """Add a button with optional custom speech handling."""
        button = ttk.Button(self.tabs[tab_name], text=text, command=command)
        button.pack(fill='x', padx=5, pady=5)
        
        if custom_speech is not None:
            def on_focus(event):
                self.speak(custom_speech)
                return "break"
            button.bind('<FocusIn>', on_focus)
            button.custom_speech = custom_speech
        
        self.widgets[tab_name].append(button)

    def add_checkbox(self, tab_name: str, text: str, initial_value: str = "false") -> None:
        """Add a checkbox to the interface."""
        value, description = self.extract_value_and_description(initial_value)
        bool_value = value.lower() == 'true'
        var = tk.BooleanVar(value=bool_value)
        checkbox = ttk.Checkbutton(self.tabs[tab_name], text=text, variable=var)
        checkbox.pack(fill='x', padx=5, pady=5)
        self.widgets[tab_name].append(checkbox)
        self.variables[tab_name][text] = var
        checkbox.description = description

    def add_entry(self, tab_name: str, text: str, initial_value: str = "") -> None:
        """Add a text entry field to the interface."""
        frame = ttk.Frame(self.tabs[tab_name])
        frame.pack(fill='x', padx=5, pady=5)

        label = ttk.Label(frame, text=text)
        label.pack(side='left')

        value, description = self.extract_value_and_description(initial_value)
        var = tk.StringVar(value=value)
        entry = ttk.Entry(frame, textvariable=var, state='readonly')
        entry.pack(side='right', expand=True, fill='x')

        self.widgets[tab_name].append(entry)
        self.variables[tab_name][text] = var
        entry.description = description

    def add_keybind(self, tab_name: str, text: str, initial_value: str = "") -> None:
        """Add a keybind entry to the interface."""
        value, description = self.extract_value_and_description(initial_value)
        self.add_entry(tab_name, text, initial_value)
        entry = self.widgets[tab_name][-1]
        entry.bind('<FocusIn>', lambda e: None)
        entry.is_keybind = True
        
        if value:
            self.keybind_map[value.lower()] = text
        entry.description = description

    def navigate(self, event) -> str:
        """Handle up/down navigation between widgets."""
        if self.capturing_keybind or self.currently_editing:
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

        widget_info = self.get_widget_info(next_widget)
        if widget_info:
            self.speak(widget_info)
            
        return "break"

    def on_tab_change(self, event) -> None:
        """Handle tab change events."""
        tab = event.widget.tab('current')['text']
        self.speak(f"Switched to {tab} tab")
        if self.widgets[tab]:
            self.widgets[tab][0].focus_set()
            widget_info = self.get_widget_info(self.widgets[tab][0])
            if widget_info:
                self.speak(widget_info)

    def change_tab(self, event) -> str:
        """Handle tab switching."""
        if self.capturing_keybind or self.currently_editing:
            self.speak("Please finish editing before changing tabs")
            return "break"
        current = self.notebook.index(self.notebook.select())
        if event.state & 1:  # Shift is pressed
            next_tab = (current - 1) % self.notebook.index('end')
        else:
            next_tab = (current + 1) % self.notebook.index('end')
        self.notebook.select(next_tab)
        return "break"

    def get_widget_info(self, widget: tk.Widget) -> str:
        """Get speaking information for a widget."""
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
        return "Unknown widget"

    def handle_keybind_capture(self, widget: ttk.Entry, key: str) -> None:
        """Handle keybind capture process."""
        if not self.capturing_keybind:
            return

        action_name = widget.master.winfo_children()[0].cget('text')

        # Prevent capturing of system keys
        if key.lower() in ['tab', 'shift+tab', 'return', 'escape']:
            self.speak("This key cannot be bound")
            return

        if key.lower() == 'backspace':
            widget.delete(0, tk.END)
            self.variables[self.notebook.tab(self.notebook.select(), "text")][action_name].set('')
            self.speak(f"Keybind for {action_name} disabled")
            self.keybind_map = {k: v for k, v in self.keybind_map.items() if v != action_name}
        else:
            if key.lower() in self.keybind_map and self.keybind_map[key.lower()] != action_name:
                old_action = self.keybind_map[key.lower()]
                self.speak(f"Warning: {key} was previously bound to {old_action}. That keybind has been removed.")
                for tab_name, tab_widgets in self.widgets.items():
                    for w in tab_widgets:
                        if isinstance(w, ttk.Entry) and getattr(w, 'is_keybind', False):
                            key_label = w.master.winfo_children()[0].cget('text')
                            if key_label == old_action:
                                w.config(state='normal')
                                w.delete(0, tk.END)
                                w.config(state='readonly')
                                self.variables[tab_name][old_action].set('')
                                break
                del self.keybind_map[key.lower()]
            
            self.keybind_map[key.lower()] = action_name
            widget.delete(0, tk.END)
            widget.insert(0, key)
            self.variables[self.notebook.tab(self.notebook.select(), "text")][action_name].set(key)
            self.speak(f"Keybind for {action_name} set to {key}")

        self.capturing_keybind = False
        widget.config(state='readonly')

    def on_enter(self, event) -> str:
        """Handle Enter key press."""
        current_widget = self.root.focus_get()
        if isinstance(current_widget, ttk.Checkbutton):
            current_widget.invoke()
            self.speak(f"{current_widget.cget('text')} {'checked' if current_widget.instate(['selected']) else 'unchecked'}")
        elif isinstance(current_widget, ttk.Entry):
            if self.capturing_keybind:
                return "break"
            elif self.currently_editing == current_widget:
                self.finish_editing(current_widget)
            else:
                if getattr(current_widget, 'is_keybind', False):
                    self.capture_keybind(current_widget)
                else:
                    self.start_editing(current_widget)
        elif isinstance(current_widget, ttk.Button):
            current_widget.invoke()
        return "break"

    def on_escape(self, event) -> str:
        """Handle Escape key press."""
        if self.capturing_keybind:
            self.capturing_keybind = False
            current_widget = self.root.focus_get()
            if isinstance(current_widget, ttk.Entry):
                current_widget.config(state='readonly')
            self.speak("Keybind capture cancelled")
        elif self.currently_editing:
            widget = self.currently_editing
            key = widget.master.winfo_children()[0].cget('text')
            current_tab = self.notebook.tab(self.notebook.select(), "text")
            widget.config(state='readonly')
            widget.delete(0, tk.END)
            widget.insert(0, self.previous_value)
            variable = self.variables[current_tab][key]
            variable.set(self.previous_value)
            self.currently_editing = None
            self.speak("Cancelled editing, value restored to previous.")
        else:
            self.save_and_close()
        return "break"

    def on_key(self, event) -> Optional[str]:
        """Handle general key press events."""
        if self.capturing_keybind:
            return "break"
        if event.keysym.lower() == 'r' and self.default_config:
            current_widget = self.root.focus_get()
            current_tab = self.notebook.tab(self.notebook.select(), "text")
            
            if isinstance(current_widget, ttk.Checkbutton):
                key = current_widget.cget('text')
                default_value_string = self.default_config.get(current_tab, key, fallback='')
                default_value, _ = self.extract_value_and_description(default_value_string)
                bool_value = default_value.lower() == 'true'
                var = self.variables[current_tab][key]
                var.set(bool_value)
                self.speak(f"{key} reset to default value.")
            elif isinstance(current_widget, ttk.Entry):
                key = current_widget.master.winfo_children()[0].cget('text')
                default_value_string = self.default_config.get(current_tab, key, fallback='')
                default_value, _ = self.extract_value_and_description(default_value_string)
                current_widget.config(state='normal')
                current_widget.delete(0, tk.END)
                current_widget.insert(0, default_value)
                current_widget.config(state='readonly')
                var = self.variables[current_tab][key]
                var.set(default_value)
                self.speak(f"{key} reset to default value.")
        return None

    def capture_key(self, widget: ttk.Entry) -> None:
        """Capture keyboard input for keybind setting."""
        if not self.capturing_keybind:
            return

        key = get_pressed_key()
        if key:
            if key.lower() == 'enter':
                # Skip Enter key and continue capturing
                self.root.after(50, self.capture_key, widget)
            elif key.lower() == 'escape':
                self.capturing_keybind = False
                widget.config(state='readonly')
                self.speak("Keybind capture cancelled")
            else:
                self.handle_keybind_capture(widget, key)
        else:
            self.root.after(50, self.capture_key, widget)

    def start_editing(self, widget: ttk.Entry) -> None:
        """Start editing a text entry widget."""
        if self.capturing_keybind or self.currently_editing:
            return
            
        self.currently_editing = widget
        self.previous_value = widget.get()
        widget.config(state='normal')
        widget.delete(0, tk.END)
        self.speak(f"Editing {widget.master.winfo_children()[0].cget('text')}. Enter new value and press Enter when done.")

    def finish_editing(self, widget: ttk.Entry) -> None:
        """Complete editing of a text entry widget."""
        if not self.currently_editing:
            return
            
        self.currently_editing = None
        widget.config(state='readonly')
        new_value = widget.get()
        key = widget.master.winfo_children()[0].cget('text')
        current_tab = self.notebook.tab(self.notebook.select(), "text")
        
        if new_value == '':
            # Handle empty value by reverting to default or previous
            default_value_string = self.default_config.get(current_tab, key, fallback=self.previous_value) \
                if self.default_config else self.previous_value
            default_value, _ = self.extract_value_and_description(default_value_string)
            widget.delete(0, tk.END)
            widget.insert(0, default_value)
            self.variables[current_tab][key].set(default_value)
            self.speak(f"No value entered. {key} reset to default value.")
        else:
            self.variables[current_tab][key].set(new_value)
            self.speak(f"{key} set to {new_value}")

        # Play POI sound at the volume set for specific keys
        if key in ["MinimumPOIVolume", "MaximumPOIVolume"]:
            try:
                volume = float(new_value)
                volume = max(0.0, min(volume, 1.0))  # Ensure volume is between 0.0 and 1.0
                # Play the POI sound at this volume
                spatial_poi = SpatialAudio('sounds/poi.ogg')
                spatial_poi.play_audio(left_weight=1.0, right_weight=1.0, volume=volume)
            except Exception as e:
                print(f"Error playing POI sound: {e}")

    def capture_keybind(self, widget: ttk.Entry) -> None:
        """Start capturing a new keybind."""
        if self.capturing_keybind or self.currently_editing:
            return
            
        self.capturing_keybind = True
        widget.config(state='normal')
        widget.delete(0, tk.END)
        self.speak("Press any key to set the keybind. Press Backspace to disable this keybind. Press Escape to cancel.")
        self.root.after(50, self.capture_key, widget)

    def save_and_close(self) -> None:
        """Save configuration and close the UI window."""
        try:
            # Save all sections
            for tab_name in self.tabs:
                if tab_name not in self.config.sections():
                    self.config.add_section(tab_name)
    
                # Save all variables in each section
                for key, var in self.variables[tab_name].items():
                    widget = None
                    # Find the corresponding widget
                    for w in self.widgets[tab_name]:
                        if isinstance(w, ttk.Checkbutton) and w.cget('text') == key:
                            widget = w
                            break
                        elif hasattr(w, 'master') and w.master.winfo_children() and \
                             w.master.winfo_children()[0].cget('text') == key:
                            widget = w
                            break
    
                    description = getattr(widget, 'description', '') if widget else ''
                    
                    if isinstance(var, tk.BooleanVar):
                        value = 'true' if var.get() else 'false'
                    else:
                        value = var.get()
    
                    self.config[tab_name][key] = f"{value} \"{description}\"" if description else value
    
            # Save configuration to file if specified
            if self.config_file:
                self.save_config()
    
            self.speak("Closing..")
            
        except Exception as e:
            print(f"Error saving configuration: {e}")
            self.speak("Error saving configuration")
        finally:
            # Clean up variables before destroying window
            for tab_vars in self.variables.values():
                for var in tab_vars.values():
                    if hasattr(var, '_name'):
                        try:
                            var._root = None
                        except Exception:
                            pass
    
            # Destroy all widgets explicitly
            for tab_name, widgets in self.widgets.items():
                for widget in widgets:
                    try:
                        widget.destroy()
                    except Exception:
                        pass
    
            # Clear references
            self.widgets.clear()
            self.variables.clear()
            
            # Finally destroy the root window
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass

    def run(self) -> None:
        """Start the UI event loop."""
        self.root.mainloop()
