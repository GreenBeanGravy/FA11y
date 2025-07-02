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
import win32api
import win32gui

from lib.guis.base_ui import AccessibleUI
from lib.spatial_audio import SpatialAudio
from lib.utilities import force_focus_window, DEFAULT_CONFIG, get_default_config_value_string
from lib.input_handler import VK_KEYS, is_mouse_button

# Initialize logger
logger = logging.getLogger(__name__)

class ConfigGUI(AccessibleUI):
    """Configuration GUI for FA11y settings"""

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
        
        # Mouse position control for keybind capture
        self.original_mouse_pos: Optional[Tuple[int, int]] = None
        self.mouse_constraint_active = False
        self.mouse_constraint_timer = None
        
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
        
        self.root.protocol("WM_DELETE_WINDOW", self.save_and_close)
        
        self.root.after(100, lambda: force_focus_window(
            self.root,
            "Press R to reset the focused setting to its default value. Press Delete to unbind a keybind when focused. Press Escape to save and close, or cancel current edit/keybind capture.",
            self.focus_first_widget
        ))
    
    def create_tabs(self) -> None:
        """Create tabs for different setting categories"""
        self.add_tab("Toggles")
        self.add_tab("Values")
        self.add_tab("Keybinds")
    
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
                elif section == "Keybinds":
                    self.section_tab_mapping["Keybinds"][key] = "Keybinds"
                elif section == "SETTINGS":
                    if value.lower() in ['true', 'false']:
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
        """Create widgets for each configuration section"""
        for section in self.config.config.sections():
            if section == "POI": 
                continue
                
            for key in self.config.config[section]:
                value_string = self.config.config[section][key]
                
                if section == "Toggles":
                    self.create_checkbox("Toggles", key, value_string)
                elif section == "Keybinds":
                    self.create_keybind_entry("Keybinds", key, value_string)
                elif section == "Values":
                    self.create_value_entry("Values", key, value_string)
                elif section == "SETTINGS":
                     val_part, _ = self.extract_value_and_description(value_string)
                     if val_part.lower() in ['true', 'false']:
                         self.create_checkbox("Toggles", key, value_string)
                     else:
                         self.create_value_entry("Values", key, value_string)
                elif section == "SCRIPT KEYBINDS":
                    self.create_keybind_entry("Keybinds", key, value_string)

    
    def create_checkbox(self, tab_name: str, key: str, value_string: str) -> None:
        """Create a checkbox for a boolean setting"""
        value, description = self.extract_value_and_description(value_string)
        bool_value = value.lower() == 'true'
        self.add_checkbox(tab_name, key, bool_value, description)
    
    def create_value_entry(self, tab_name: str, key: str, value_string: str) -> None:
        """Create a text entry field for a value setting"""
        value, description = self.extract_value_and_description(value_string)
        self.add_entry(tab_name, key, value, description)
    
    def create_keybind_entry(self, tab_name: str, key: str, value_string: str) -> None:
        """Create a keybind entry field"""
        value, description = self.extract_value_and_description(value_string)
        self.add_keybind(tab_name, key, value, description) 
    
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
    
    def get_window_center_screen_coords(self) -> Tuple[int, int]:
        """Get the screen coordinates of the window center"""
        try:
            # Get window position and size
            window_x = self.root.winfo_rootx()
            window_y = self.root.winfo_rooty()
            window_width = self.root.winfo_width()
            window_height = self.root.winfo_height()
            
            # Calculate center coordinates
            center_x = window_x + window_width // 2
            center_y = window_y + window_height // 2
            
            return (center_x, center_y)
        except Exception as e:
            logger.error(f"Error getting window center coordinates: {e}")
            return (500, 400)  # Fallback coordinates
    
    def get_widget_screen_coords(self, widget: tk.Widget) -> Tuple[int, int]:
        """Get screen coordinates of a widget's center"""
        try:
            # Get widget position relative to root
            widget_x = widget.winfo_rootx()
            widget_y = widget.winfo_rooty()
            widget_width = widget.winfo_width()
            widget_height = widget.winfo_height()
            
            # Calculate center coordinates
            center_x = widget_x + widget_width // 2
            center_y = widget_y + widget_height // 2
            
            return (center_x, center_y)
        except Exception as e:
            logger.error(f"Error getting widget coordinates: {e}")
            return self.get_window_center_screen_coords()
    
    def constrain_mouse_to_window(self) -> None:
        """Constrain mouse cursor to the window center and keep it there"""
        if not self.mouse_constraint_active:
            return
            
        try:
            # Get current window center
            center_x, center_y = self.get_window_center_screen_coords()
            
            # Get current mouse position
            current_x, current_y = win32api.GetCursorPos()
            
            # Calculate distance from center
            distance = abs(current_x - center_x) + abs(current_y - center_y)
            
            # If mouse has moved significantly from center, snap it back
            if distance > 5:  # Allow small movement tolerance
                win32api.SetCursorPos((center_x, center_y))
            
            # Schedule next check
            if self.mouse_constraint_active:
                self.mouse_constraint_timer = self.root.after(10, self.constrain_mouse_to_window)
                
        except Exception as e:
            logger.error(f"Error constraining mouse: {e}")
    
    def start_mouse_constraint(self, widget: tk.Widget) -> None:
        """Start constraining mouse to window center"""
        try:
            # Store original mouse position
            self.original_mouse_pos = win32api.GetCursorPos()
            
            # Get target position (widget center or window center)
            target_x, target_y = self.get_widget_screen_coords(widget)
            
            # Move mouse to target position
            win32api.SetCursorPos((target_x, target_y))
            
            # Start constraint system
            self.mouse_constraint_active = True
            self.constrain_mouse_to_window()
            
            logger.debug(f"Mouse constraint started, moved to ({target_x}, {target_y})")
            
        except Exception as e:
            logger.error(f"Error starting mouse constraint: {e}")
    
    def stop_mouse_constraint(self) -> None:
        """Stop constraining mouse and restore original position"""
        try:
            # Stop constraint system
            self.mouse_constraint_active = False
            if self.mouse_constraint_timer:
                self.root.after_cancel(self.mouse_constraint_timer)
                self.mouse_constraint_timer = None
            
            # Restore original mouse position if we have it
            if self.original_mouse_pos:
                win32api.SetCursorPos(self.original_mouse_pos)
                logger.debug(f"Mouse position restored to {self.original_mouse_pos}")
                self.original_mouse_pos = None
                
        except Exception as e:
            logger.error(f"Error stopping mouse constraint: {e}")
    
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
            
        # Get action name from label widget
        if hasattr(current_widget, 'master') and current_widget.master.winfo_children():
            label_widget = current_widget.master.winfo_children()[0]
            if isinstance(label_widget, ttk.Label):
                action_name = label_widget.cget('text')
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
            if hasattr(current_widget, 'master') and current_widget.master.winfo_children():
                label_widget = current_widget.master.winfo_children()[0]
                if isinstance(label_widget, ttk.Label):
                    setting_key = label_widget.cget('text')
        
        if setting_key:
            self.reset_to_default(current_tab_name, setting_key, current_widget)
            return "break"
        return None
    
    def reset_to_default(self, tab_name: str, key: str, widget: Any) -> None:
        """Reset any setting to its default value"""
        default_full_value = get_default_config_value_string(tab_name, key)
                    
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
                
                if key in ["MinimumPOIVolume", "MaximumPOIVolume"]:
                    self.play_poi_sound_at_volume(key, default_value_part)

        elif isinstance(widget, ttk.Combobox):
             var = self.variables[tab_name][key] 
             var.set(default_value_part)
                
        self.speak(f"{key} reset to default value: {default_value_part if default_value_part else 'blank'}")

    def update_conflicting_keybind_widget(self, action_to_clear: str, new_key_value: str, speak_message: str) -> None:
        """Updates the widget for an action whose keybind was taken"""
        for widget_in_tab in self.widgets.get("Keybinds", []):
            if isinstance(widget_in_tab, ttk.Entry):
                label_widget = widget_in_tab.master.winfo_children()[0]
                if isinstance(label_widget, ttk.Label) and label_widget.cget('text') == action_to_clear:
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
        key_label_widget = widget.master.winfo_children()[0]
        key = key_label_widget.cget('text')
        
        current_tab = self.notebook.tab(self.notebook.select(), "text")
        if key in self.variables[current_tab]:
            self.variables[current_tab][key].set(new_value)
            self.speak(f"{key} set to {new_value}")
        else:
            self.speak(f"Value for {key} updated to {new_value} but not linked to a variable.")

        if key in ["MinimumPOIVolume", "MaximumPOIVolume"]:
            self.play_poi_sound_at_volume(key, new_value)
    
    def play_poi_sound_at_volume(self, key: str, value_str: str) -> None:
        """Play POI sound at the specified volume"""
        try:
            volume = float(value_str)
            volume = max(0.0, min(volume, 1.0))  
            
            sound_path = os.path.join('sounds', 'poi.ogg') 
            if not os.path.exists(sound_path):
                logger.warning(f"POI sound file not found: {sound_path}")
                return

            spatial_poi_player = SpatialAudio(sound_path) 
            spatial_poi_player.play_audio(left_weight=1.0, right_weight=1.0, volume=volume)
        except ValueError:
            logger.error(f"Invalid volume value '{value_str}' for {key}")
        except Exception as e:
            logger.error(f"Error playing POI sound: {e}")
    
    def focus_first_widget(self) -> None:
        """Focus the first widget in the current tab"""
        current_tab_name = self.notebook.tab(self.notebook.select(), "text")
        
        if self.widgets.get(current_tab_name):
            first_widget = self.widgets[current_tab_name][0]
            first_widget.focus_set()
            self.speak(f"{current_tab_name} tab.") 
            widget_info = self.get_widget_info(first_widget) 
            if widget_info:
                self.speak(widget_info)
    
    def save_and_close(self) -> None:
        """Save configuration and close the GUI"""
        try:
            # Stop mouse constraint if active
            self.stop_mouse_constraint()
            
            config_parser_instance = self.config.config 

            for section_name in ["Toggles", "Values", "Keybinds", "POI"]:
                if not config_parser_instance.has_section(section_name):
                    config_parser_instance.add_section(section_name)

            for tab_name in self.tabs.keys(): 
                if tab_name not in self.variables: continue 

                for setting_key, tk_var in self.variables[tab_name].items():
                    description = ""
                    for widget_candidate in self.widgets[tab_name]:
                        widget_label = ""
                        if isinstance(widget_candidate, ttk.Checkbutton):
                            widget_label = widget_candidate.cget('text')
                        elif hasattr(widget_candidate, 'master') and widget_candidate.master.winfo_children():
                            label_widget = widget_candidate.master.winfo_children()[0]
                            if isinstance(label_widget, ttk.Label):
                                widget_label = label_widget.cget('text')
                        
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
                    config_parser_instance.set(tab_name, setting_key, value_string_to_save)

            self.update_callback(config_parser_instance) 
            self.speak("Configuration saved and applied.")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            self.speak("Error saving configuration.")
        finally:
            if self.root and self.root.winfo_exists():
                self.root.destroy()
    
    def on_escape(self, event) -> str:
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
            
            # Stop mouse constraint
            self.stop_mouse_constraint()
            
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
            setting_key_label = widget.master.winfo_children()[0].cget('text')
            current_tab = self.notebook.tab(self.notebook.select(), "text")
            self.variables[current_tab][setting_key_label].set(self.previous_value)
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
        
        # Start mouse constraint to keep cursor in window
        self.start_mouse_constraint(widget)
        
        self.speak("Press any key or mouse button to set the keybind. Press Escape to cancel. Mouse is locked to window.")
        
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
        
        action_label_widget = widget.master.winfo_children()[0] 
        action_name = action_label_widget.cget('text')
        
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
            
            # Stop mouse constraint
            self.stop_mouse_constraint()
            
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
        
        # Stop mouse constraint
        self.stop_mouse_constraint()
        
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