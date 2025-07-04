"""
Configuration GUI for FA11y
Provides interface for user configuration of settings, values, and keybinds with multi-column layout
"""
import os
import logging
import tkinter as tk
from tkinter import ttk, messagebox
import configparser
from typing import Callable, Dict, Optional, List, Any, Tuple, Set
import time
import win32api
import win32gui
import math

from lib.guis.base_ui import AccessibleUI
from lib.spatial_audio import SpatialAudio
from lib.utilities import force_focus_window, DEFAULT_CONFIG, get_default_config_value_string, get_available_sounds, is_audio_setting
from lib.input_handler import VK_KEYS, is_mouse_button

# Initialize logger
logger = logging.getLogger(__name__)

class ConfigGUI(AccessibleUI):
    """Configuration GUI for FA11y settings with multi-column layout"""

    def __init__(self, config, 
                 update_callback: Callable,
                 default_config_str = None): 
        """Initialize the configuration GUI
        
        Args:
            config: Current configuration (Config object from utilities.py)
            update_callback: Callback function to update main configuration (expects ConfigParser)
            default_config_str: Optional default configuration string for reset functionality
        """
        super().__init__(title="FA11y Configuration")
        
        self.config = config 
        self.update_callback = update_callback
        self.default_config_str = default_config_str if default_config_str else DEFAULT_CONFIG
        
        self.section_tab_mapping = {
            "Toggles": {},
            "Values": {},
            "Audio": {},
            "Keybinds": {},
        }
        
        self.key_to_action: Dict[str, str] = {}
        self.action_to_key: Dict[str, str] = {}
        
        self.last_keybind_time = 0
        self.keybind_cooldown = 0.2

        self.capturing_keybind_for_widget: Optional[ttk.Entry] = None
        self.original_keybind_value: str = ""
        self.key_binding_id = None
        self.mouse_binding_ids = []
        
        # Multi-column layout settings
        self.columns_per_row = 3  # Number of columns per row
        self.current_row = 0
        self.current_column = 0
        
        # Grid management for each tab
        self.grid_positions = {}  # tab_name -> (row, col)
        
        # Audio instances for volume testing
        self.test_audio_instances = {}
        
        # Track widgets for proper tab order
        self.tab_order_widgets = {}  # tab_name -> list of widgets in order
        
        self.setup()
    
    def setup(self) -> None:
        """Set up the configuration GUI"""
        self.create_tabs()
        self.analyze_config()
        self.create_widgets()
        
        # Bind keys for configuration actions
        self.root.bind_all('<r>', self.on_r_key)
        self.root.bind_all('<R>', self.on_r_key) 
        self.root.bind_all('<Delete>', self.on_delete_key)
        self.root.bind_all('<t>', self.on_t_key)  # Test volume
        self.root.bind_all('<T>', self.on_t_key)
        self.root.bind_all('<Return>', self.on_enter)  # Override Enter key handling
        self.root.bind_all('<Escape>', self.on_escape)  # Override Escape key handling
        
        self.root.protocol("WM_DELETE_WINDOW", self.save_and_close)
        
        self.root.after(100, lambda: force_focus_window(
            self.root,
            "Press R to reset the focused setting to its default value. Press Delete to unbind a keybind when focused. Press T to test audio settings. Press Escape to save and close, or cancel current edit/keybind capture.",
            self.focus_first_widget
        ))
    
    def create_tabs(self) -> None:
        """Create tabs for different setting categories"""
        self.add_tab("Toggles")
        self.add_tab("Values")
        self.add_tab("Audio")
        self.add_tab("Keybinds")
        
        # Initialize grid positions for each tab
        for tab_name in ["Toggles", "Values", "Audio", "Keybinds"]:
            self.grid_positions[tab_name] = [0, 0]  # [row, col]
            self.tab_order_widgets[tab_name] = []
    
    def get_next_grid_position(self, tab_name: str) -> Tuple[int, int]:
        """Get the next grid position for a widget in the specified tab"""
        if tab_name not in self.grid_positions:
            self.grid_positions[tab_name] = [0, 0]
        
        row, col = self.grid_positions[tab_name]
        current_row, current_col = row, col
        
        # Move to next position
        col += 1
        if col >= self.columns_per_row:
            col = 0
            row += 1
        
        self.grid_positions[tab_name] = [row, col]
        return current_row, current_col
    
    def analyze_config(self) -> None:
        """Analyze configuration to determine appropriate tab mappings"""
        self.build_key_binding_maps()
        
        for section in self.config.config.sections():
            if section == "POI": 
                continue
                
            for key in self.config.config[section]:
                value_string = self.config.config[section][key]
                value, _ = self.extract_value_and_description(value_string)

                if section == "Toggles":
                    self.section_tab_mapping["Toggles"][key] = "Toggles"
                elif section == "Values":
                    self.section_tab_mapping["Values"][key] = "Values"
                elif section == "Audio":
                    self.section_tab_mapping["Audio"][key] = "Audio"
                elif section == "Keybinds":
                    self.section_tab_mapping["Keybinds"][key] = "Keybinds"
                elif section == "SETTINGS":
                    # Handle legacy SETTINGS section
                    if is_audio_setting(key):
                        self.section_tab_mapping["Audio"][key] = "Audio"
                    elif value.lower() in ['true', 'false']:
                        self.section_tab_mapping["Toggles"][key] = "Toggles"
                    else:
                        self.section_tab_mapping["Values"][key] = "Values"
                elif section == "SCRIPT KEYBINDS":
                    self.section_tab_mapping["Keybinds"][key] = "Keybinds"
    
    def build_key_binding_maps(self) -> None:
        """Build maps of keys to actions and actions to keys for conflict detection"""
        self.key_to_action.clear()
        self.action_to_key.clear()
        
        if self.config.config.has_section("Keybinds"):
            for action in self.config.config["Keybinds"]:
                value_string = self.config.config["Keybinds"][action]
                key, _ = self.extract_value_and_description(value_string)
                
                if key and key.strip(): 
                    key_lower = key.lower()
                    self.key_to_action[key_lower] = action
                    self.action_to_key[action] = key_lower 
    
    def create_widgets(self) -> None:
        """Create widgets for each configuration section with multi-column layout"""
        for section in self.config.config.sections():
            if section == "POI": 
                continue
                
            for key in self.config.config[section]:
                value_string = self.config.config[section][key]
                
                if section == "Toggles":
                    self.create_checkbox_grid("Toggles", key, value_string)
                elif section == "Values":
                    self.create_value_entry_grid("Values", key, value_string)
                elif section == "Audio":
                    # Determine widget type based on key
                    value, _ = self.extract_value_and_description(value_string)
                    if value.lower() in ['true', 'false']:
                        self.create_audio_checkbox_grid("Audio", key, value_string)
                    elif key.endswith('Volume') or key == 'MasterVolume':
                        self.create_volume_entry_grid("Audio", key, value_string)
                    else:
                        self.create_audio_value_entry_grid("Audio", key, value_string)
                elif section == "Keybinds":
                    self.create_keybind_entry_grid("Keybinds", key, value_string)
                elif section == "SETTINGS":
                    # Handle legacy SETTINGS section
                    val_part, _ = self.extract_value_and_description(value_string)
                    if is_audio_setting(key):
                        if val_part.lower() in ['true', 'false']:
                            self.create_audio_checkbox_grid("Audio", key, value_string)
                        elif key.endswith('Volume') or key == 'MasterVolume':
                            self.create_volume_entry_grid("Audio", key, value_string)
                        else:
                            self.create_audio_value_entry_grid("Audio", key, value_string)
                    elif val_part.lower() in ['true', 'false']:
                        self.create_checkbox_grid("Toggles", key, value_string)
                    else:
                        self.create_value_entry_grid("Values", key, value_string)
                elif section == "SCRIPT KEYBINDS":
                    self.create_keybind_entry_grid("Keybinds", key, value_string)
    
    def create_checkbox_grid(self, tab_name: str, key: str, value_string: str) -> None:
        """Create a checkbox for a boolean setting in grid layout"""
        value, description = self.extract_value_and_description(value_string)
        bool_value = value.lower() == 'true'
        
        row, col = self.get_next_grid_position(tab_name)
        self.add_checkbox_grid(tab_name, key, bool_value, description, row, col)
    
    def create_audio_checkbox_grid(self, tab_name: str, key: str, value_string: str) -> None:
        """Create a checkbox for an audio boolean setting in grid layout"""
        value, description = self.extract_value_and_description(value_string)
        bool_value = value.lower() == 'true'
        
        row, col = self.get_next_grid_position(tab_name)
        self.add_checkbox_grid(tab_name, key, bool_value, description, row, col)
    
    def create_value_entry_grid(self, tab_name: str, key: str, value_string: str) -> None:
        """Create a text entry field for a value setting in grid layout"""
        value, description = self.extract_value_and_description(value_string)
        
        row, col = self.get_next_grid_position(tab_name)
        self.add_entry_grid(tab_name, key, value, description, row, col)
    
    def create_audio_value_entry_grid(self, tab_name: str, key: str, value_string: str) -> None:
        """Create a text entry field for an audio value setting in grid layout"""
        value, description = self.extract_value_and_description(value_string)
        
        row, col = self.get_next_grid_position(tab_name)
        self.add_entry_grid(tab_name, key, value, description, row, col)
    
    def create_volume_entry_grid(self, tab_name: str, key: str, value_string: str) -> None:
        """Create a volume entry field with test button in grid layout"""
        value, description = self.extract_value_and_description(value_string)
        
        row, col = self.get_next_grid_position(tab_name)
        self.add_volume_entry_grid(tab_name, key, value, description, row, col)
    
    def create_keybind_entry_grid(self, tab_name: str, key: str, value_string: str) -> None:
        """Create a keybind entry field in grid layout"""
        value, description = self.extract_value_and_description(value_string)
        
        row, col = self.get_next_grid_position(tab_name)
        self.add_keybind_grid(tab_name, key, value, description, row, col)
    
    def add_checkbox_grid(self, tab_name: str, key: str, value: bool, description: str, row: int, col: int) -> None:
        """Add a checkbox widget in grid layout"""
        if tab_name not in self.tabs:
            return
        
        frame = self.tabs[tab_name]
        
        # Create a container frame for this checkbox
        container = ttk.Frame(frame)
        container.grid(row=row, column=col, padx=5, pady=2, sticky='ew')
        
        # Configure column weight for the container's parent
        frame.grid_columnconfigure(col, weight=1)
        
        var = tk.BooleanVar(value=value)
        
        checkbox = ttk.Checkbutton(
            container,
            text=key,
            variable=var
        )
        checkbox.pack(fill='x')
        checkbox.description = description
        
        if tab_name not in self.variables:
            self.variables[tab_name] = {}
        if tab_name not in self.widgets:
            self.widgets[tab_name] = []
            
        self.variables[tab_name][key] = var
        self.widgets[tab_name].append(checkbox)
        self.tab_order_widgets[tab_name].append(checkbox)
    
    def add_entry_grid(self, tab_name: str, key: str, value: str, description: str, row: int, col: int) -> None:
        """Add an entry widget in grid layout"""
        if tab_name not in self.tabs:
            return
        
        frame = self.tabs[tab_name]
        
        # Create a container frame for this entry
        container = ttk.Frame(frame)
        container.grid(row=row, column=col, padx=5, pady=2, sticky='ew')
        
        # Configure column weight
        frame.grid_columnconfigure(col, weight=1)
        
        # Label
        label = ttk.Label(container, text=key)
        label.pack(anchor='w')
        
        # Entry
        var = tk.StringVar(value=value)
        entry = ttk.Entry(container, textvariable=var, state='readonly')
        entry.pack(fill='x')
        entry.description = description
        
        # Bind events
        entry.bind('<Button-1>', lambda e: self.start_editing(entry))
        
        if tab_name not in self.variables:
            self.variables[tab_name] = {}
        if tab_name not in self.widgets:
            self.widgets[tab_name] = []
            
        self.variables[tab_name][key] = var
        self.widgets[tab_name].append(entry)
        self.tab_order_widgets[tab_name].append(entry)
    
    def add_volume_entry_grid(self, tab_name: str, key: str, value: str, description: str, row: int, col: int) -> None:
        """Add a volume entry widget with test button in grid layout"""
        if tab_name not in self.tabs:
            return
        
        frame = self.tabs[tab_name]
        
        # Create a container frame for this volume entry
        container = ttk.Frame(frame)
        container.grid(row=row, column=col, padx=5, pady=2, sticky='ew')
        
        # Configure column weight
        frame.grid_columnconfigure(col, weight=1)
        
        # Label
        label = ttk.Label(container, text=key)
        label.pack(anchor='w')
        
        # Entry frame to hold entry and test button
        entry_frame = ttk.Frame(container)
        entry_frame.pack(fill='x')
        
        # Entry
        var = tk.StringVar(value=value)
        entry = ttk.Entry(entry_frame, textvariable=var, state='readonly')
        entry.pack(side='left', fill='x', expand=True)
        entry.description = description
        
        # Test button
        test_button = ttk.Button(
            entry_frame, 
            text="Test", 
            width=6,
            command=lambda: self.test_volume(key, var.get())
        )
        test_button.pack(side='right', padx=(2, 0))
        
        # Bind events
        entry.bind('<Button-1>', lambda e: self.start_editing(entry))
        
        if tab_name not in self.variables:
            self.variables[tab_name] = {}
        if tab_name not in self.widgets:
            self.widgets[tab_name] = []
            
        self.variables[tab_name][key] = var
        self.widgets[tab_name].append(entry)
        self.widgets[tab_name].append(test_button)
        
        # Add to tab order - entry first, then test button
        self.tab_order_widgets[tab_name].append(entry)
        self.tab_order_widgets[tab_name].append(test_button)
    
    def add_keybind_grid(self, tab_name: str, key: str, value: str, description: str, row: int, col: int) -> None:
        """Add a keybind widget in grid layout"""
        if tab_name not in self.tabs:
            return
        
        frame = self.tabs[tab_name]
        
        # Create a container frame for this keybind
        container = ttk.Frame(frame)
        container.grid(row=row, column=col, padx=5, pady=2, sticky='ew')
        
        # Configure column weight
        frame.grid_columnconfigure(col, weight=1)
        
        # Label
        label = ttk.Label(container, text=key)
        label.pack(anchor='w')
        
        # Entry
        var = tk.StringVar(value=value)
        entry = ttk.Entry(container, textvariable=var, state='readonly')
        entry.pack(fill='x')
        entry.description = description
        
        # Mark as keybind entry - this is crucial!
        entry.is_keybind = True
        
        # Bind events
        entry.bind('<Button-1>', lambda e: self.capture_keybind(entry))
        
        if tab_name not in self.variables:
            self.variables[tab_name] = {}
        if tab_name not in self.widgets:
            self.widgets[tab_name] = []
            
        self.variables[tab_name][key] = var
        self.widgets[tab_name].append(entry)
        self.tab_order_widgets[tab_name].append(entry)
    
    def find_widget_label(self, widget: tk.Widget) -> Optional[str]:
        """Find the label text for a widget, checking parent containers
        
        Args:
            widget: Widget to find label for
            
        Returns:
            str or None: Label text or None if not found
        """
        # First check immediate parent for label
        try:
            for child in widget.master.winfo_children():
                if isinstance(child, ttk.Label):
                    return child.cget('text')
        except (tk.TclError, AttributeError):
            pass
        
        # If not found, check grandparent (for volume entries where entry is in entry_frame)
        try:
            for child in widget.master.master.winfo_children():
                if isinstance(child, ttk.Label):
                    return child.cget('text')
        except (tk.TclError, AttributeError):
            pass
        
        return None
    
    def test_volume(self, volume_key: str, volume_value: str) -> None:
        """Test a volume setting by playing an appropriate sound"""
        try:
            volume = float(volume_value)
            volume = max(0.0, min(volume, 1.0))
            
            # Determine which sound to play based on the volume key
            sound_file = None
            if volume_key == 'MasterVolume':
                sound_file = 'sounds/poi.ogg'  # Use POI sound for master volume
            elif volume_key == 'POIVolume':
                sound_file = 'sounds/poi.ogg'
            elif volume_key == 'StormVolume':
                sound_file = 'sounds/storm.ogg'
            elif volume_key == 'GameObjectVolume':
                sound_file = 'sounds/gameobject.ogg'
            else:
                # For individual object sounds, try to find the corresponding file
                clean_key = volume_key.replace('Volume', '').lower()
                for sound_name in get_available_sounds():
                    if clean_key in sound_name.lower():
                        sound_file = f'sounds/{sound_name}.ogg'
                        break
                
                # Fallback to a default sound
                if not sound_file:
                    sound_file = 'sounds/poi.ogg'
            
            if not os.path.exists(sound_file):
                self.speak(f"Sound file not found for {volume_key}")
                return
            
            # Create or get audio instance
            if volume_key not in self.test_audio_instances:
                self.test_audio_instances[volume_key] = SpatialAudio(sound_file)
            
            audio_instance = self.test_audio_instances[volume_key]
            
            # Set up volume management
            if volume_key == 'MasterVolume':
                # For master volume, set both master and individual to the test value
                audio_instance.set_master_volume(volume)
                audio_instance.set_individual_volume(1.0)
            else:
                # For individual volumes, use current master volume
                master_vol = 1.0
                if 'MasterVolume' in self.variables.get("Audio", {}):
                    try:
                        master_vol = float(self.variables["Audio"]['MasterVolume'].get())
                    except:
                        master_vol = 1.0
                
                audio_instance.set_master_volume(master_vol)
                audio_instance.set_individual_volume(volume)
            
            # Play the sound in center (no spatial positioning for testing)
            audio_instance.play_audio(left_weight=0.5, right_weight=0.5, volume=1.0)
            
            self.speak(f"Testing {volume_key} at {volume:.1f}")
            
        except ValueError:
            self.speak(f"Invalid volume value: {volume_value}")
        except Exception as e:
            logger.error(f"Error testing volume: {e}")
            self.speak(f"Error testing volume for {volume_key}")
    
    def on_t_key(self, event) -> Optional[str]:
        """Handle T key press to test audio settings"""
        if self.capturing_keybind_for_widget or self.currently_editing:
            self.speak("Cannot test audio while editing or capturing keybind.")
            return "break"

        current_widget = self.root.focus_get()
        current_tab_name = self.notebook.tab(self.notebook.select(), "text")
        
        # Only process in Audio tab with entry widget focused
        if current_tab_name != "Audio" or not isinstance(current_widget, ttk.Entry):
            return None
        
        # Get audio setting name using the helper method
        audio_key = self.find_widget_label(current_widget)
        if audio_key and (audio_key.endswith('Volume') or audio_key == 'MasterVolume'):
            audio_value = current_widget.get()
            self.test_volume(audio_key, audio_value)
            return "break"
                    
        return None
    
    def extract_value_and_description(self, value_string: str) -> tuple:
        """Extract value and description from a config string"""
        value_string = value_string.strip()
        if '"' in value_string:
            quote_pos = value_string.find('"')
            value = value_string[:quote_pos].strip()
            description = value_string[quote_pos+1:] 
            if description.endswith('"'):
                description = description[:-1]
            return value, description
        return value_string, ""
    
    def on_delete_key(self, event) -> Optional[str]:
        """Handle Delete key press to unbind keybinds"""
        if self.capturing_keybind_for_widget or self.currently_editing:
            self.speak("Cannot unbind while editing or capturing keybind.")
            return "break"

        current_widget = self.root.focus_get()
        current_tab_name = self.notebook.tab(self.notebook.select(), "text")
        
        # Only process in Keybinds tab with entry widget focused
        if current_tab_name != "Keybinds" or not isinstance(current_widget, ttk.Entry):
            return None
        
        # Get action name using the helper method
        action_name = self.find_widget_label(current_widget)
        if action_name:
            self.unbind_keybind(action_name, current_widget)
            return "break"
                    
        return None

    def unbind_keybind(self, action_name: str, widget: ttk.Entry) -> None:
        """Unbind a keybind by setting it to an empty string"""
        current_key = widget.get().lower()
        
        # Remove from mappings
        if current_key and current_key in self.key_to_action:
            self.key_to_action.pop(current_key, None)
        
        if action_name in self.action_to_key:
            self.action_to_key.pop(action_name, None)
            
        # Update widget and variable
        widget.config(state='normal')
        widget.delete(0, tk.END)
        widget.config(state='readonly')
        
        if action_name in self.variables["Keybinds"]:
            self.variables["Keybinds"][action_name].set("")
            
        self.speak(f"Keybind for {action_name} unbinded.")
    
    def on_r_key(self, event) -> Optional[str]:
        """Handle R key press events for resetting to default"""
        if self.capturing_keybind_for_widget or self.currently_editing:
             self.speak("Cannot reset while editing or capturing keybind.")
             return "break"

        current_widget = self.root.focus_get()
        current_tab_name = self.notebook.tab(self.notebook.select(), "text")
        
        setting_key = None
        if isinstance(current_widget, ttk.Checkbutton):
            setting_key = current_widget.cget('text')
        elif isinstance(current_widget, ttk.Entry) or isinstance(current_widget, ttk.Combobox):
            setting_key = self.find_widget_label(current_widget)
        
        if setting_key:
            self.reset_to_default(current_tab_name, setting_key, current_widget)
            return "break"
        return None
    
    def reset_to_default(self, tab_name: str, key: str, widget: Any) -> None:
        """Reset any setting to its default value"""
        # For audio settings, always look in Audio section for defaults
        lookup_tab = tab_name
        if tab_name == "Audio":
            lookup_tab = "Audio"
            
        default_full_value = get_default_config_value_string(lookup_tab, key)
                    
        if not default_full_value:
            self.speak(f"No default value found for {key}")
            return
            
        default_value_part, _ = self.extract_value_and_description(default_full_value)
        
        if isinstance(widget, ttk.Checkbutton):
            bool_value = default_value_part.lower() == 'true'
            var = self.variables[tab_name][key] 
            var.set(bool_value)
        elif isinstance(widget, ttk.Entry):
            if tab_name == "Keybinds":
                action_being_reset = key 
                current_bound_key_var = self.variables[tab_name].get(action_being_reset)
                current_bound_key = current_bound_key_var.get().lower() if current_bound_key_var else ""
                
                if current_bound_key and self.key_to_action.get(current_bound_key) == action_being_reset:
                    self.key_to_action.pop(current_bound_key, None)
                
                new_default_key_lower = default_value_part.lower()
                if new_default_key_lower and new_default_key_lower in self.key_to_action:
                    conflicting_action = self.key_to_action[new_default_key_lower]
                    if conflicting_action != action_being_reset: 
                        self.key_to_action.pop(new_default_key_lower, None) 
                        self.action_to_key.pop(conflicting_action, None)
                        self.update_conflicting_keybind_widget(conflicting_action, "", f"Key {new_default_key_lower} now used by {action_being_reset}")
                
                widget.config(state='normal')
                widget.delete(0, tk.END)
                widget.insert(0, default_value_part)
                widget.config(state='readonly')
                if current_bound_key_var: 
                    current_bound_key_var.set(default_value_part)

                self.action_to_key[action_being_reset] = new_default_key_lower
                if new_default_key_lower: 
                    self.key_to_action[new_default_key_lower] = action_being_reset

            else: 
                widget.config(state='normal')
                widget.delete(0, tk.END)
                widget.insert(0, default_value_part)
                widget.config(state='readonly')
                self.variables[tab_name][key].set(default_value_part) 
                
                if tab_name == "Audio" and (key.endswith('Volume') or key == 'MasterVolume'):
                    self.test_volume(key, default_value_part)

        elif isinstance(widget, ttk.Combobox):
             var = self.variables[tab_name][key] 
             var.set(default_value_part)
                
        self.speak(f"{key} reset to default value: {default_value_part if default_value_part else 'blank'}")

    def update_conflicting_keybind_widget(self, action_to_clear: str, new_key_value: str, speak_message: str) -> None:
        """Updates the widget for an action whose keybind was taken"""
        for widget_in_tab in self.widgets.get("Keybinds", []):
            if isinstance(widget_in_tab, ttk.Entry):
                widget_label = self.find_widget_label(widget_in_tab)
                if widget_label == action_to_clear:
                    widget_in_tab.config(state='normal')
                    widget_in_tab.delete(0, tk.END)
                    widget_in_tab.insert(0, new_key_value)
                    widget_in_tab.config(state='readonly')
                    if action_to_clear in self.variables["Keybinds"]:
                        self.variables["Keybinds"][action_to_clear].set(new_key_value)
                    break
    
    def finish_editing(self, widget: ttk.Entry) -> None:
        """Complete editing of a text entry widget"""
        if not widget.winfo_exists():
            self.currently_editing = None
            return

        self.currently_editing = None
        widget.config(state='readonly')
        new_value = widget.get()
        
        # Find the key using the helper method
        key = self.find_widget_label(widget)
        
        if not key:
            self.speak("Could not determine setting name")
            return
        
        current_tab = self.notebook.tab(self.notebook.select(), "text")
        if key in self.variables[current_tab]:
            self.variables[current_tab][key].set(new_value)
            self.speak(f"{key} set to {new_value}")
        else:
            self.speak(f"Value for {key} updated to {new_value} but not linked to a variable.")

        if current_tab == "Audio" and (key.endswith('Volume') or key == 'MasterVolume'):
            self.test_volume(key, new_value)
    
    def focus_first_widget(self) -> None:
        """Focus the first widget in the current tab"""
        current_tab_name = self.notebook.tab(self.notebook.select(), "text")
        
        if self.tab_order_widgets.get(current_tab_name):
            first_widget = self.tab_order_widgets[current_tab_name][0]
            first_widget.focus_set()
            self.speak(f"{current_tab_name} tab.") 
            widget_info = self.get_widget_info(first_widget) 
            if widget_info:
                self.speak(widget_info)
    
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
            key = self.find_widget_label(widget)
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
            key = self.find_widget_label(widget)
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
    
    def save_and_close(self) -> None:
        """Save configuration and close the GUI"""
        try:
            # Clean up test audio instances
            for audio_instance in self.test_audio_instances.values():
                try:
                    audio_instance.cleanup()
                except Exception:
                    pass
            self.test_audio_instances.clear()
            
            config_parser_instance = self.config.config 

            for section_name in ["Toggles", "Values", "Audio", "Keybinds", "POI"]:
                if not config_parser_instance.has_section(section_name):
                    config_parser_instance.add_section(section_name)

            for tab_name in self.tabs.keys(): 
                if tab_name not in self.variables: 
                    continue 

                for setting_key, tk_var in self.variables[tab_name].items():
                    description = ""
                    for widget_candidate in self.widgets[tab_name]:
                        widget_label = ""
                        if isinstance(widget_candidate, ttk.Checkbutton):
                            widget_label = widget_candidate.cget('text')
                        elif isinstance(widget_candidate, ttk.Entry):
                            widget_label = self.find_widget_label(widget_candidate)
                        
                        if widget_label == setting_key:
                            description = getattr(widget_candidate, 'description', '')
                            break
                    
                    if isinstance(tk_var, tk.BooleanVar):
                        value_to_save = 'true' if tk_var.get() else 'false'
                    else: 
                        value_to_save = tk_var.get()
                        if tab_name == "Keybinds" and value_to_save.strip() and not self.is_valid_key(value_to_save):
                            self.speak(f"Warning: Invalid key '{value_to_save}' for {setting_key}. Saving as blank.")
                            value_to_save = "" 
                    
                    value_string_to_save = f"{value_to_save} \"{description}\"" if description else str(value_to_save)
                    
                    # Determine target section based on tab
                    target_section = tab_name
                    
                    config_parser_instance.set(target_section, setting_key, value_string_to_save)

            self.update_callback(config_parser_instance) 
            self.speak("Configuration saved and applied.")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            self.speak("Error saving configuration.")
        finally:
            if self.root and self.root.winfo_exists():
                self.root.destroy()
    
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
        """Handle Escape key press globally for the ConfigGUI window"""
        if self.capturing_keybind_for_widget:
            self._cancel_keybind_capture()
        elif self.currently_editing:
            self._cancel_value_edit()
        else:
            self.save_and_close()
        return "break"

    def _cancel_keybind_capture(self):
        """Cancel ongoing keybind capture"""
        if self.capturing_keybind_for_widget:
            widget = self.capturing_keybind_for_widget
            widget.delete(0, tk.END)
            widget.insert(0, self.original_keybind_value)
            widget.config(state='readonly')
            self.speak("Keybind capture cancelled.")
            
            # Clean up all bindings
            if self.key_binding_id:
                self.root.unbind('<Key>', self.key_binding_id)
                self.key_binding_id = None
            
            for binding_id in self.mouse_binding_ids:
                try:
                    self.root.unbind('<Button>', binding_id)
                except:
                    pass
            self.mouse_binding_ids.clear()
            
            self.capturing_keybind_for_widget = None
            self.original_keybind_value = ""
            widget.focus_set()
            self.speak(self.get_widget_info(widget))

    def _cancel_value_edit(self):
        """Cancel ongoing value editing"""
        if self.currently_editing:
            widget = self.currently_editing
            widget.config(state='readonly')
            
            # Find setting key using helper method
            setting_key = self.find_widget_label(widget)
            
            if setting_key:
                current_tab = self.notebook.tab(self.notebook.select(), "text")
                self.variables[current_tab][setting_key].set(self.previous_value)
                widget.delete(0, tk.END)
                widget.insert(0, self.previous_value)
            
            self.currently_editing = None
            self.speak("Cancelled editing, value restored to previous.")
            widget.focus_set()
            self.speak(self.get_widget_info(widget))
    
    def capture_keybind(self, widget: ttk.Entry) -> None:
        """Start capturing a new keybind (keyboard keys or mouse buttons)"""
        current_time = time.time()
        if current_time - self.last_keybind_time < self.keybind_cooldown:
            self.speak("Please wait a moment before capturing another keybind.")
            return
            
        self.last_keybind_time = current_time
        
        self.capturing_keybind_for_widget = widget 
        self.original_keybind_value = widget.get() 

        widget.config(state='normal') 
        widget.delete(0, tk.END)
        
        self.speak("Press any key or mouse button to set the keybind. Press Escape to cancel.")
        
        key_name_mapping = {"Control_L": "lctrl", "Control_R": "rctrl",
                            "Shift_L": "lshift", "Shift_R": "rshift",
                            "Alt_L": "lalt", "Alt_R": "ralt",
                            "KP_0": "num 0", "KP_1": "num 1", "KP_2": "num 2", "KP_3": "num 3",
                            "KP_4": "num 4", "KP_5": "num 5", "KP_6": "num 6", "KP_7": "num 7",
                            "KP_8": "num 8", "KP_9": "num 9", "KP_Decimal": "num period",
                            "KP_Add": "num +", "KP_Subtract": "num -",
                            "KP_Multiply": "num *", "KP_Divide": "num /",
                            "bracketleft": "bracketleft", "bracketright": "bracketright",
                            "apostrophe": "apostrophe", "grave": "grave",
                            "backslash": "backslash", "semicolon": "semicolon",
                            "period": "period", "comma": "comma", "minus": "minus", "equal": "equals", 
                            "slash": "slash", "BackSpace": "backspace", "Caps_Lock": "capslock",
                            "Delete": "delete", "End": "end", 
                            "Execute": "enter", 
                            "F1":"f1", "F2":"f2", "F3":"f3", "F4":"f4", "F5":"f5", "F6":"f6",
                            "F7":"f7", "F8":"f8", "F9":"f9", "F10":"f10", "F11":"f11", "F12":"f12",
                            "Home":"home", "Insert":"insert", "Num_Lock":"numlock",
                            "Pause":"pause", "Print":"printscreen", "Scroll_Lock":"scrolllock",
                            "space":"space", "Tab":"tab", "Up":"up", "Down":"down", "Left":"left", "Right":"right",
                            "Return":"enter"}
        
        # Mouse button number to name mapping
        mouse_button_mapping = {
            2: "middle mouse",  # Middle button
            4: "mouse 4",       # X button 1 (back button)
            5: "mouse 5"        # X button 2 (forward button)
        }
        
        # Find action name using helper method
        action_name = self.find_widget_label(widget)
        
        if not action_name:
            return
        
        old_key_for_action = self.action_to_key.get(action_name, "")

        def _capture_key_event_handler(event):
            key_sym = event.keysym

            # Let the global on_escape handle escape key
            if key_sym.lower() == 'escape':
                if self.key_binding_id:
                    self.root.unbind('<Key>', self.key_binding_id)
                    self.key_binding_id = None
                return 

            final_key_str = key_sym 
            if key_sym in key_name_mapping:
                final_key_str = key_name_mapping[key_sym]
            elif len(key_sym) == 1 and key_sym.isalnum(): 
                final_key_str = key_sym.lower()
            
            if final_key_str.lower() == 'tab': 
                return "break"
            
            return self._process_captured_input(final_key_str, action_name, old_key_for_action, widget)

        def _capture_mouse_event_handler(event):
            # Get mouse button number
            button_num = event.num
            
            # Map button number to our naming convention
            if button_num in mouse_button_mapping:
                final_key_str = mouse_button_mapping[button_num]
                return self._process_captured_input(final_key_str, action_name, old_key_for_action, widget)
            else:
                # Unknown mouse button - ignore
                return "break"
            
        # Clean up any existing bindings
        if self.key_binding_id: 
            self.root.unbind('<Key>', self.key_binding_id)
        for binding_id in self.mouse_binding_ids:
            try:
                self.root.unbind('<Button>', binding_id)
            except:
                pass
        self.mouse_binding_ids.clear()
        
        # Set up new bindings
        self.key_binding_id = self.root.bind('<Key>', _capture_key_event_handler)
        
        # Bind mouse button events
        for button_num in mouse_button_mapping.keys():
            binding_id = self.root.bind(f'<Button-{button_num}>', _capture_mouse_event_handler)
            self.mouse_binding_ids.append(binding_id)
    
    def _process_captured_input(self, final_key_str: str, action_name: str, old_key_for_action: str, widget: ttk.Entry) -> str:
        """Process captured keyboard key or mouse button input"""
        if final_key_str and not self.is_valid_key(final_key_str):
            self.speak(f"Key or button '{final_key_str}' is not a valid FA11y input. Restoring original.")
            widget.delete(0, tk.END)
            widget.insert(0, self.original_keybind_value) 
            widget.config(state='readonly')
            
            # Clean up bindings
            if self.key_binding_id:
                self.root.unbind('<Key>', self.key_binding_id)
                self.key_binding_id = None
            for binding_id in self.mouse_binding_ids:
                try:
                    self.root.unbind('<Button>', binding_id)
                except:
                    pass
            self.mouse_binding_ids.clear()
            
            self.capturing_keybind_for_widget = None 
            return "break"

        widget.delete(0, tk.END)
        widget.insert(0, final_key_str) 
        
        self.variables["Keybinds"][action_name].set(final_key_str)
        
        new_key_lower = final_key_str.lower()

        if old_key_for_action and self.key_to_action.get(old_key_for_action) == action_name:
            self.key_to_action.pop(old_key_for_action, None)
        self.action_to_key.pop(action_name, None)

        if new_key_lower and new_key_lower in self.key_to_action:
            conflicting_action = self.key_to_action[new_key_lower]
            if conflicting_action != action_name: 
                self.speak(f"Warning: Key {new_key_lower} was bound to {conflicting_action}. That binding is now cleared.")
                self.action_to_key.pop(conflicting_action, None) 
                self.update_conflicting_keybind_widget(conflicting_action, "", "") 

        if new_key_lower: 
            self.key_to_action[new_key_lower] = action_name
        self.action_to_key[action_name] = new_key_lower
        
        if final_key_str: 
            input_type = "button" if is_mouse_button(final_key_str) else "key"
            self.speak(f"Keybind for {action_name} set to {input_type} {final_key_str}.")
        
        widget.config(state='readonly')
        
        # Clean up bindings
        if self.key_binding_id:
            self.root.unbind('<Key>', self.key_binding_id)
            self.key_binding_id = None
        for binding_id in self.mouse_binding_ids:
            try:
                self.root.unbind('<Button>', binding_id)
            except:
                pass
        self.mouse_binding_ids.clear()
        
        self.capturing_keybind_for_widget = None 
        return "break"
    
    def is_valid_key(self, key: str) -> bool:
        """Check if a key is valid for the input system"""
        if not key or not key.strip():  
            return True
            
        key_lower = key.lower()
        
        if key_lower in VK_KEYS:
            return True
        
        if len(key_lower) == 1 and key_lower.isalnum():
            return True
            
        return False
    
    def get_default_keybind(self, action: str) -> str:
        """Get the default keybind for an action"""
        default_full_value = get_default_config_value_string("Keybinds", action)
        if default_full_value:
            default_key_part, _ = self.extract_value_and_description(default_full_value)
            return default_key_part
        return "" 


def launch_config_gui(config_obj: 'Config', 
                     update_callback: Callable[[configparser.ConfigParser], None], 
                     default_config_str: Optional[str] = None) -> None:
    """Launch the configuration GUI"""
    try:
        gui = ConfigGUI(config_obj, update_callback, default_config_str)
        gui.run()
    except Exception as e:
        logger.error(f"Error launching configuration GUI: {e}")