"""
Configuration GUI for FA11y
Provides interface for user configuration of settings, values, and keybinds
"""
import os
import logging
import tkinter as tk
from tkinter import ttk, messagebox
import configparser
from typing import Callable, Dict, Optional, List, Any, Tuple, Set
import time

from lib.guis.base_ui import AccessibleUI
from lib.spatial_audio import SpatialAudio
from lib.utilities import force_focus_window, DEFAULT_CONFIG

# Initialize logger
logger = logging.getLogger(__name__)

class ConfigGUI(AccessibleUI):
    """Configuration GUI for FA11y settings"""

    def __init__(self, config, 
                 update_callback: Callable,
                 default_config = None):
        """Initialize the configuration GUI
        
        Args:
            config: Current configuration
            update_callback: Callback function to update main configuration
            default_config: Optional default configuration for reset functionality
        """
        super().__init__(title="FA11y Configuration")
        
        self.config = config
        self.update_callback = update_callback
        self.default_config = default_config
        
        # Section to tab mapping for configuration organization
        self.section_tab_mapping = {
            "Toggles": {},     # All toggle settings
            "Values": {},      # All value settings
            "Keybinds": {},    # All keybind settings
        }
        
        # Key binding tracking for conflict detection
        self.key_to_action = {}  # Maps keys to their actions
        self.action_to_key = {}  # Maps actions to their keys
        
        # Performance optimization
        self.last_keybind_time = 0
        self.keybind_cooldown = 0.2  # seconds
        
        # Setup and run the UI
        self.setup()
    
    def setup(self) -> None:
        """Set up the configuration GUI"""
        # Create tabs
        self.create_tabs()
        
        # Analyze configuration to determine appropriate tab mappings
        self.analyze_config()
        
        # Create widgets for each section
        self.create_widgets()
        
        # Add 'R' key binding for reset functionality
        self.root.bind_all('<r>', self.on_key)
        self.root.bind_all('<R>', self.on_key)
        
        # Override the default close behavior
        self.root.protocol("WM_DELETE_WINDOW", self.save_and_close)
        
        # Focus the first widget with help info
        self.root.after(100, lambda: force_focus_window(
            self.root,
            "Press R to reset to defaults",
            self.focus_first_widget
        ))
    
    def create_tabs(self) -> None:
        """Create tabs for different setting categories"""
        self.add_tab("Toggles")
        self.add_tab("Values")
        self.add_tab("Keybinds")
    
    def analyze_config(self) -> None:
        """Analyze configuration to determine appropriate tab mappings"""
        # Build key binding maps
        self.build_key_binding_maps()
        
        for section in self.config.config.sections():
            if section == "POI":  # Skip POI section
                continue
                
            for key in self.config.config[section]:
                value_string = self.config.config[section][key]
                value, _ = self.extract_value_and_description(value_string)

                # Map items based on their section
                if section == "Toggles":
                    self.section_tab_mapping["Toggles"][key] = "Toggles"
                elif section == "Values":
                    self.section_tab_mapping["Values"][key] = "Values"
                elif section == "Keybinds":
                    self.section_tab_mapping["Keybinds"][key] = "Keybinds"
                # Handle legacy format if needed
                elif section == "SETTINGS":
                    if value.lower() in ['true', 'false']:
                        self.section_tab_mapping["Toggles"][key] = "Toggles"
                    else:
                        self.section_tab_mapping["Values"][key] = "Values"
                elif section == "SCRIPT KEYBINDS":
                    self.section_tab_mapping["Keybinds"][key] = "Keybinds"
    
    def build_key_binding_maps(self) -> None:
        """Build maps of keys to actions and actions to keys for conflict detection"""
        self.key_to_action = {}
        self.action_to_key = {}
        
        if "Keybinds" in self.config.config.sections():
            for action in self.config.config["Keybinds"]:
                value_string = self.config.config["Keybinds"][action]
                key, _ = self.extract_value_and_description(value_string)
                
                if key:
                    key = key.lower()
                    self.key_to_action[key] = action
                    self.action_to_key[action] = key
    
    def create_widgets(self) -> None:
        """Create widgets for each configuration section"""
        for section in self.config.config.sections():
            if section == "POI":  # Skip POI section
                continue
                
            for key in self.config.config[section]:
                value_string = self.config.config[section][key]
                
                # Determine tab based on section
                if section == "Toggles" or (section == "SETTINGS" and 
                                         (value_string.lower().startswith('true') or 
                                          value_string.lower().startswith('false'))):
                    self.create_checkbox("Toggles", key, value_string)
                elif section == "Keybinds" or section == "SCRIPT KEYBINDS":
                    self.create_keybind_entry("Keybinds", key, value_string)
                elif section == "Values" or section == "SETTINGS":
                    self.create_value_entry("Values", key, value_string)
    
    def create_checkbox(self, tab_name: str, key: str, value_string: str) -> None:
        """Create a checkbox for a boolean setting
        
        Args:
            tab_name: Tab to add the checkbox to
            key: Setting key
            value_string: Value string from config
        """
        value, description = self.extract_value_and_description(value_string)
        bool_value = value.lower() == 'true'
        self.add_checkbox(tab_name, key, bool_value, description)
    
    def create_value_entry(self, tab_name: str, key: str, value_string: str) -> None:
        """Create a text entry field for a value setting
        
        Args:
            tab_name: Tab to add the entry to
            key: Setting key
            value_string: Value string from config
        """
        value, description = self.extract_value_and_description(value_string)
        self.add_entry(tab_name, key, value, description)
    
    def create_keybind_entry(self, tab_name: str, key: str, value_string: str) -> None:
        """Create a keybind entry field
        
        Args:
            tab_name: Tab to add the entry to
            key: Setting key
            value_string: Value string from config
        """
        value, description = self.extract_value_and_description(value_string)
        entry = self.add_keybind(tab_name, key, value, description)
    
    def extract_value_and_description(self, value_string: str) -> tuple:
        """Extract value and description from a config string
        
        Args:
            value_string: Raw config value string
            
        Returns:
            tuple: (value, description)
        """
        value_string = value_string.strip()
        if '"' in value_string:
            quote_pos = value_string.find('"')
            value = value_string[:quote_pos].strip()
            description = value_string[quote_pos+1:].rstrip('"')
            return value, description
        return value_string, ""
    
    def on_key(self, event) -> Optional[str]:
        """Handle key press events
        
        Args:
            event: Key event
            
        Returns:
            str or None: "break" to prevent default handling or None
        """
        if event.keysym.lower() == 'r':
            current_widget = self.root.focus_get()
            current_tab = self.notebook.tab(self.notebook.select(), "text")
            
            if isinstance(current_widget, ttk.Checkbutton):
                key = current_widget.cget('text')
                self.reset_to_default(current_tab, key, current_widget)
                return "break"
            elif isinstance(current_widget, ttk.Entry):
                key = current_widget.master.winfo_children()[0].cget('text')
                
                # Handle keybind entry reset
                if current_tab == "Keybinds":
                    self.reset_keybind_to_default(key, current_widget)
                else:
                    # Regular value entry reset
                    self.reset_to_default(current_tab, key, current_widget)
                return "break"
        return None
    
    def reset_to_default(self, tab_name: str, key: str, widget: Any) -> None:
        """Reset any setting to its default value
        
        Args:
            tab_name: Tab name
            key: Setting key
            widget: Widget to update
        """
        # Parse DEFAULT_CONFIG string directly to get default values
        default_config = configparser.ConfigParser(interpolation=None)
        default_config.optionxform = str  # Preserve case sensitivity
        default_config.read_string(DEFAULT_CONFIG)
        
        # Get default value
        default_value_string = ""
        for section in default_config.sections():
            if section.lower() == tab_name.lower():
                if key in default_config[section]:
                    default_value_string = default_config[section][key]
                    break
                    
        if not default_value_string:
            self.speak(f"No default value found for {key}")
            return
            
        default_value, _ = self.extract_value_and_description(default_value_string)
        
        # Update widget based on type
        if isinstance(widget, ttk.Checkbutton):
            bool_value = default_value.lower() == 'true'
            var = self.variables[tab_name][key]
            var.set(bool_value)
        elif isinstance(widget, ttk.Entry):
            widget.config(state='normal')
            widget.delete(0, tk.END)
            widget.insert(0, default_value)
            widget.config(state='readonly')
            var = self.variables[tab_name][key]
            var.set(default_value)
            
            # Play POI sound for volume settings
            if key in ["MinimumPOIVolume", "MaximumPOIVolume"]:
                self.play_poi_sound_at_volume(key, default_value)
                
        self.speak(f"{key} reset to default value: {default_value}")
    
    def reset_keybind_to_default(self, action: str, widget: ttk.Entry) -> None:
        """Reset a keybind to its default value, handling conflicts
        
        Args:
            action: Action name
            widget: Entry widget
        """
        # Get the current key bound to this action
        current_key = self.variables["Keybinds"][action].get().lower() if action in self.variables["Keybinds"] else ""
        
        # Get the default key for this action
        default_value = self.get_default_keybind(action)
        
        # Check for conflicts with the default key
        if default_value and default_value.lower() in self.key_to_action:
            conflicting_action = self.key_to_action[default_value.lower()]
            
            # Only handle conflict if it's not the same action
            if conflicting_action != action:
                # Update key mappings
                self.key_to_action.pop(default_value.lower(), None)
                self.action_to_key.pop(conflicting_action, None)
                
                # Update the conflicting action's entry if it exists
                self.update_conflicting_keybind(conflicting_action, "", f"Key {default_value} taken by {action}")
                
        # Update the entry and variable
        widget.config(state='normal')
        widget.delete(0, tk.END)
        widget.insert(0, default_value)
        widget.config(state='readonly')
        
        # Update action-key mappings
        if current_key and self.key_to_action.get(current_key) == action:
            self.key_to_action.pop(current_key, None)
        if default_value:
            self.key_to_action[default_value.lower()] = action
            self.action_to_key[action] = default_value.lower()
        
        # Update variables
        self.variables["Keybinds"][action].set(default_value)
        
        # Speak feedback
        if not default_value:
            self.speak(f"Keybind for {action} reset to default: blank (disabled)")
        else:
            self.speak(f"Keybind for {action} reset to default: {default_value}")
    
    def update_conflicting_keybind(self, action: str, new_key: str, message: str) -> None:
        """Update a keybind after a conflict is detected
        
        Args:
            action: Action name to update
            new_key: New key to assign (empty string to clear)
            message: Message to speak
        """
        # Find the widget for this action
        for widget in self.widgets["Keybinds"]:
            if (isinstance(widget, ttk.Entry) and 
                hasattr(widget, 'master') and 
                widget.master.winfo_children() and 
                widget.master.winfo_children()[0].cget('text') == action):
                
                # Update the widget
                widget.config(state='normal')
                widget.delete(0, tk.END)
                widget.insert(0, new_key)
                widget.config(state='readonly')
                
                # Update the variable
                self.variables["Keybinds"][action].set(new_key)
                
                # Speak feedback
                self.speak(message)
                break
    
    def finish_editing(self, widget: ttk.Entry) -> None:
        """Complete editing of a text entry widget
        
        Args:
            widget: Entry widget being edited
        """
        super().finish_editing(widget)
        
        # Play POI sound at the volume set for specific keys
        key = widget.master.winfo_children()[0].cget('text')
        if key in ["MinimumPOIVolume", "MaximumPOIVolume"]:
            new_value = widget.get()
            self.play_poi_sound_at_volume(key, new_value)
    
    def play_poi_sound_at_volume(self, key: str, value_str: str) -> None:
        """Play POI sound at the specified volume
        
        Args:
            key: Setting key
            value_str: Volume value as string
        """
        try:
            volume = float(value_str)
            volume = max(0.0, min(volume, 1.0))  # Ensure volume is between 0.0 and 1.0
            
            # Create a sound path that works with FA11y's directory structure
            sound_path = 'sounds/poi.ogg'
            
            # Play the POI sound at this volume
            spatial_poi = SpatialAudio(sound_path)
            spatial_poi.play_audio(left_weight=1.0, right_weight=1.0, volume=volume)
        except Exception as e:
            logger.error(f"Error playing POI sound: {e}")
    
    def focus_first_widget(self) -> None:
        """Focus the first widget in the current tab"""
        current_tab = self.notebook.tab(self.notebook.select(), "text")
        
        if self.widgets[current_tab]:
            first_widget = self.widgets[current_tab][0]
            first_widget.focus_set()
            self.speak(f"{current_tab} tab.")
            widget_info = self.get_widget_info(first_widget)
            if widget_info:
                self.speak(widget_info)
    
    def save_and_close(self) -> None:
        """Save configuration and close the GUI"""
        try:
            # Ensure all sections exist in the underlying ConfigParser
            for section in ["Toggles", "Values", "Keybinds", "POI"]:
                if section not in self.config.config.sections():
                    self.config.config.add_section(section)

            # Save POI section as is if it exists in original config
            if "POI" in self.config.config.sections():
                for key in self.config.config["POI"]:
                    self.config.config["POI"][key] = self.config.config["POI"][key]

            # Save variables to configuration sections
            for tab in ["Toggles", "Values", "Keybinds"]:
                for key, var in self.variables[tab].items():
                    description = ""
                    
                    # Find widget with this key to get its description
                    for widget in self.widgets[tab]:
                        if isinstance(widget, ttk.Checkbutton) and widget.cget('text') == key:
                            description = getattr(widget, 'description', '')
                            break
                        elif hasattr(widget, 'master') and widget.master.winfo_children() and \
                             widget.master.winfo_children()[0].cget('text') == key:
                            description = getattr(widget, 'description', '')
                            break
                    
                    # Format value based on type
                    if isinstance(var, tk.BooleanVar):
                        value = 'true' if var.get() else 'false'
                    else:
                        value = var.get()
                        
                        # Additional validation for keybinds - allow blank values
                        if tab == "Keybinds" and value.strip() and not self.is_valid_key(value):
                            # Replace invalid key with default
                            value = self.get_default_keybind(key)
                            logger.warning(f"Replaced invalid key '{var.get()}' with default '{value}' for {key}")
                    
                    # Save to config with description if available
                    self.config.config[tab][key] = f"{value} \"{description}\"" if description else value

            # Update script configuration using the update_callback
            # Pass the underlying ConfigParser instead of Config object
            self.update_callback(self.config.config)
            self.speak("Configuration saved and applied")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            self.speak("Error saving configuration")
        finally:
            self.root.destroy()
    
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
            # Save configuration before closing
            self.save_and_close()
            
        return "break"
    
    def capture_keybind(self, widget: ttk.Entry) -> None:
        """Start capturing a new keybind
        
        Args:
            widget: Entry widget for keybind
        """
        # Check for cooldown to prevent lag in GUI
        current_time = time.time()
        if current_time - self.last_keybind_time < self.keybind_cooldown:
            self.speak("Please wait a moment before capturing another keybind")
            return
            
        self.last_keybind_time = current_time
            
        widget.config(state='normal')
        widget.delete(0, tk.END)
        self.speak("Press any key to set the keybind. Press Escape to cancel. Press Enter to disable.")
        
        # Map of Tkinter key names to expected input system key names
        key_name_mapping = {
            "Control_L": "lctrl",
            "Control_R": "rctrl",
            "Shift_L": "lshift", 
            "Shift_R": "rshift",
            "Alt_L": "lalt",
            "Alt_R": "ralt"
        }
        
        # Get the action this keybind is for
        action = widget.master.winfo_children()[0].cget('text')
        old_key = self.variables["Keybinds"][action].get().lower() if action in self.variables["Keybinds"] else ""
        
        # Remove old key from mapping if it's currently mapped to this action
        if old_key and self.key_to_action.get(old_key) == action:
            self.key_to_action.pop(old_key, None)
        
        # Store the key handler
        def capture_key(event):
            # Skip tab keys
            if event.keysym.lower() in ['tab']:
                return "break"
                
            # Handle escape key for cancelling
            if event.keysym.lower() == 'escape':
                widget.delete(0, tk.END)
                widget.insert(0, old_key or "")
                widget.config(state='readonly')
                self.speak("Keybind capture cancelled")
                self.root.unbind('<Key>', self.key_binding_id)
                return "break"
                
            # For return key, allow setting blank keybind
            if event.keysym.lower() == 'return':
                # Set empty keybind (treated as disabled)
                widget.delete(0, tk.END)
                current_tab = self.notebook.tab(self.notebook.select(), "text")
                key_name = widget.master.winfo_children()[0].cget('text')
                self.variables[current_tab][key_name].set("")
                widget.config(state='readonly')
                self.speak(f"Keybind for {key_name} disabled (blank)")
                self.root.unbind('<Key>', self.key_binding_id)
                return "break"
                
            # Use the key
            key = event.keysym
            
            # Map special keys to their input system names
            if key in key_name_mapping:
                key = key_name_mapping[key]
            
            # Check if this key is valid in the input system
            valid_key = self.is_valid_key(key)
            
            # Handle invalid keys
            if not valid_key:
                self.speak(f"Key {key} is not valid. Cancelling keybind capture.")
                widget.delete(0, tk.END)
                widget.insert(0, old_key or "")
                widget.config(state='readonly')
                self.root.unbind('<Key>', self.key_binding_id)
                return "break"
                
            # Check for conflicts
            key_lower = key.lower()
            conflicting_action = None
            
            if key_lower in self.key_to_action:
                conflicting_action = self.key_to_action[key_lower]
                
                # No conflict if binding to same action
                if conflicting_action == action:
                    conflicting_action = None
            
            # Update entry with new key
            widget.delete(0, tk.END)
            widget.insert(0, key)
            
            # Update variable
            current_tab = self.notebook.tab(self.notebook.select(), "text")
            key_name = widget.master.winfo_children()[0].cget('text')
            self.variables[current_tab][key_name].set(key)
            
            # Handle conflict if found
            if conflicting_action:
                # Remove the old binding from the conflicting action
                self.action_to_key.pop(conflicting_action, None)
                
                # Update the conflicting action's entry
                self.update_conflicting_keybind(
                    conflicting_action, "", 
                    f"Key {key} now bound to {action}"
                )
                
                # Speak warning about conflict - only speak one message
                self.speak(f"Warning: Key {key} was already bound to {conflicting_action}. Removed that binding.")
            else:
                # Speak confirmation
                self.speak(f"Keybind for {key_name} set to {key}")
            
            # Update key mappings AFTER resolving conflicts
            self.action_to_key[action] = key_lower
            self.key_to_action[key_lower] = action
            
            # Switch back to readonly
            widget.config(state='readonly')
            
            # Remove the binding
            self.root.unbind('<Key>', self.key_binding_id)
            
            return "break"
            
        # Add the binding
        self.key_binding_id = self.root.bind('<Key>', capture_key)
    
    def is_valid_key(self, key: str) -> bool:
        """Check if a key is valid for the input system
        
        Args:
            key: Key name to check
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not key or not key.strip():  # Empty/blank keys are valid (treated as disabled)
            return True
            
        # This should match the keys in VK_KEYS dict in input.py
        valid_keys = {
            'num 0', 'num 1', 'num 2', 'num 3', 'num 4', 'num 5', 'num 6', 'num 7', 'num 8', 'num 9',
            'num period', 'num .', 'num +', 'num -', 'num *', 'num /',
            'lctrl', 'rctrl', 'lshift', 'rshift', 'lalt', 'ralt',
            'middle mouse',
            'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12',
            'tab', 'capslock', 'space', 'backspace', 'enter', 'esc',
            'insert', 'delete', 'home', 'end', 'pageup', 'pagedown',
            'up', 'down', 'left', 'right',
            'printscreen', 'scrolllock', 'pause', 'numlock',
            'bracketleft', 'bracketright', 'apostrophe', 'grave', 'backslash', 'semicolon', 'period'
        }
        
        # Also allow single letter/number keys
        if len(key) == 1 and key.isalnum():
            return True
            
        return key.lower() in valid_keys
    
    def get_default_keybind(self, action: str) -> str:
        """Get the default keybind for an action
        
        Args:
            action: Action name
            
        Returns:
            str: Default keybind
        """
        # Parse DEFAULT_CONFIG string directly to get default values
        default_config = configparser.ConfigParser(interpolation=None)
        default_config.optionxform = str  # Preserve case sensitivity
        default_config.read_string(DEFAULT_CONFIG)
        
        try:
            if "Keybinds" in default_config.sections():
                if action in default_config["Keybinds"]:
                    value_string = default_config["Keybinds"][action]
                    value, _ = self.extract_value_and_description(value_string)
                    return value
        except Exception as e:
            logger.error(f"Error getting default keybind: {e}")
            
        # If not found or error, use reasonable fallbacks for common actions
        fallbacks = {
            "Toggle Keybinds": "f8",
            "Fire": "lctrl",
            "Target": "rctrl",
            "Turn Left": "num 1",
            "Turn Right": "num 3",
            "Secondary Turn Left": "num 4",
            "Secondary Turn Right": "num 6",
            "Look Up": "num 8",
            "Look Down": "num 2",
            "Turn Around": "num 0",
            "Recenter": "num 5",
            "Scroll Up": "num 7",
            "Scroll Down": "num 9"
        }
        return fallbacks.get(action, "")


def launch_config_gui(config, 
                     update_callback: Callable,
                     default_config = None) -> None:
    """Launch the configuration GUI
    
    Args:
        config: Current configuration (Config object)
        update_callback: Callback function to update main configuration
        default_config: Optional default configuration for reset functionality
    """
    try:
        gui = ConfigGUI(config, update_callback, default_config)
        gui.run()
    except Exception as e:
        logger.error(f"Error launching configuration GUI: {e}")
