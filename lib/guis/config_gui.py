"""
Configuration GUI for FA11y
Provides interface for user configuration of settings, values, and keybinds
"""
import os
import logging
import time
import configparser
from typing import Callable, Dict, Optional, List, Any, Tuple

import wx
import wx.lib.scrolledpanel as scrolled
from accessible_output2.outputs.auto import Auto

from FA11y import Config
from lib.guis.gui_utilities import (
    AccessibleDialog, BoxSizerHelper, ButtonHelper, 
    messageBox, force_focus_window, ensure_window_focus_and_center_mouse,
    BORDER_FOR_DIALOGS
)
from lib.utilities.spatial_audio import SpatialAudio
from lib.utilities.utilities import (
    DEFAULT_CONFIG, get_default_config_value_string, 
    get_available_sounds, is_audio_setting, is_game_objects_setting, 
    get_maps_with_game_objects, is_map_specific_game_object_setting,
    get_game_objects_config_order
)
from lib.utilities.input import (
    VK_KEYS, is_mouse_button, get_pressed_key_combination, parse_key_combination, 
    validate_key_combination, get_supported_modifiers, is_modifier_key
)

logger = logging.getLogger(__name__)
speaker = Auto()


class DisplayableError(Exception):
    """Error that can be displayed to the user"""
    
    def __init__(self, displayMessage: str, titleMessage: str = "Error"):
        self.displayMessage = displayMessage
        self.titleMessage = titleMessage
    
    def displayError(self, parentWindow=None):
        wx.CallAfter(
            messageBox,
            message=self.displayMessage,
            caption=self.titleMessage,
            style=wx.OK | wx.ICON_ERROR,
            parent=parentWindow
        )


class ConfigGUI(AccessibleDialog):
    """Configuration GUI with instant opening via deferred widget creation"""

    def __init__(self, parent, config, update_callback: Callable, default_config_str=None):
        super().__init__(parent, title="FA11y Configuration", helpId="ConfigurationSettings")
        
        self.config = config 
        self.update_callback = update_callback
        self.default_config_str = default_config_str if default_config_str else DEFAULT_CONFIG
        
        # Quick initialization
        self.maps_with_objects = get_maps_with_game_objects()
        self.key_to_action: Dict[str, str] = {}
        self.action_to_key: Dict[str, str] = {}
        self.test_audio_instances = {}
        self.tab_widgets = {}
        self.tab_variables = {}
        self.capturing_key = False
        self.capture_widget = None
        self.capture_action = None
        self.tab_control_widgets = {}
        
        # Show dialog immediately
        self.setupDialog()
        
    def makeSettings(self, settingsSizer: BoxSizerHelper):
        """Create dialog structure with minimal content"""
        self.notebook = wx.Notebook(self)
        settingsSizer.addItem(self.notebook, flag=wx.EXPAND, proportion=1)
        
        # Create empty tabs
        self.create_tabs()
        
        # Defer heavy operations
        wx.CallAfter(self._populateWidgets)
        
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.onPageChanged)
    
    def _populateWidgets(self):
        """Populate widgets after dialog is shown"""
        try:
            self.analyze_config()
            self.create_widgets()
            self.build_tab_control_lists()
        except Exception as e:
            logger.error(f"Error populating widgets: {e}")
            speaker.speak("Error loading configuration")
    
    def build_tab_control_lists(self):
        """Build ordered lists of focusable controls for each tab"""
        for tab_name, panel in self.tabs.items():
            self.tab_control_widgets[tab_name] = []
            self._collect_focusable_widgets(panel, self.tab_control_widgets[tab_name])
    
    def _collect_focusable_widgets(self, parent, widget_list):
        """Recursively collect focusable widgets in tab order"""
        for child in parent.GetChildren():
            if isinstance(child, (wx.Button, wx.TextCtrl, wx.CheckBox, wx.SpinCtrl, wx.Choice, wx.ComboBox, wx.ListCtrl)):
                widget_list.append(child)
            elif hasattr(child, 'GetChildren'):
                self._collect_focusable_widgets(child, widget_list)
    
    def get_current_tab_name(self):
        """Get the name of the currently selected tab"""
        selection = self.notebook.GetSelection()
        if selection != wx.NOT_FOUND:
            return self.notebook.GetPageText(selection)
        return None
    
    def is_last_widget_in_tab(self, widget):
        """Check if the widget is the last focusable widget in its tab"""
        current_tab = self.get_current_tab_name()
        if not current_tab or current_tab not in self.tab_control_widgets:
            return False
        
        widgets = self.tab_control_widgets[current_tab]
        return widgets and widget == widgets[-1]
    
    def handle_tab_navigation(self, event):
        """Handle custom tab navigation logic"""
        if not event.ShiftDown():
            focused_widget = self.FindFocus()
            if focused_widget and self.is_last_widget_in_tab(focused_widget):
                self.notebook.SetFocus()
                return True
        
        return False
    
    def postInit(self):
        """Post-initialization setup"""
        wx.CallAfter(self._postInitFocus)
    
    def _postInitFocus(self):
        """Delayed post-init focus handling"""
        ensure_window_focus_and_center_mouse(self)
        self.setFocusToFirstControl()
    
    def onPageChanged(self, event):
        """Handle notebook page change and announce tab"""
        page_index = event.GetSelection()
        if page_index >= 0 and page_index < self.notebook.GetPageCount():
            tab_text = self.notebook.GetPageText(page_index)
            speaker.speak(f"{tab_text} tab")
        event.Skip()
    
    def onWidgetFocus(self, event):
        """Handle widget focus events to announce descriptions"""
        widget = event.GetEventObject()
        wx.CallAfter(self.announceDescription, widget)
        event.Skip()
    
    def announceDescription(self, widget):
        """Announce only the description part after NVDA finishes"""
        try:
            description = getattr(widget, 'description', '')
            if description:
                wx.CallLater(150, lambda: speaker.speak(description))
        except Exception as e:
            logger.error(f"Error announcing description: {e}")
    
    def findWidgetKey(self, widget):
        """Find the setting key for a widget by looking at its parent's label"""
        try:
            parent = widget.GetParent()
            if parent:
                for child in parent.GetChildren():
                    if isinstance(child, wx.StaticText):
                        return child.GetLabel()
        except:
            pass
        return "Unknown setting"
    
    def create_tabs(self):
        """Create empty tab structure"""
        self.tabs = {}
        
        tab_names = ["Toggles", "Values", "Audio", "GameObjects", "Keybinds"]
        
        for map_name in sorted(self.maps_with_objects.keys()):
            display_name = f"{map_name.title()}GameObjects"
            tab_names.append(display_name)
        
        for tab_name in tab_names:
            panel = scrolled.ScrolledPanel(self.notebook)
            panel.SetupScrolling(scroll_x=False, scroll_y=True)
            
            self.notebook.AddPage(panel, tab_name)
            self.tabs[tab_name] = panel
            self.tab_widgets[tab_name] = []
            self.tab_variables[tab_name] = {}
            
            # Add loading indicator
            sizer = wx.BoxSizer(wx.VERTICAL)
            loading_text = wx.StaticText(panel, label="Loading settings...")
            sizer.Add(loading_text, flag=wx.ALL, border=10)
            panel.SetSizer(sizer)
    
    def analyze_config(self):
        """Analyze configuration to determine appropriate tab mappings"""
        self.build_key_binding_maps()
        
        self.section_tab_mapping = {
            "Toggles": {},
            "Values": {},
            "Audio": {},
            "GameObjects": {},
            "Keybinds": {},
        }
        
        for map_name in sorted(self.maps_with_objects.keys()):
            display_name = f"{map_name.title()}GameObjects"
            self.section_tab_mapping[display_name] = {}
        
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
                elif section == "GameObjects":
                    self.section_tab_mapping["GameObjects"][key] = "GameObjects"
                elif section == "Keybinds":
                    self.section_tab_mapping["Keybinds"][key] = "Keybinds"
                elif section.endswith("GameObjects"):
                    tab_name = section
                    if tab_name not in self.section_tab_mapping:
                        self.section_tab_mapping[tab_name] = {}
                    self.section_tab_mapping[tab_name][key] = tab_name
                elif section == "SETTINGS":
                    if is_audio_setting(key):
                        self.section_tab_mapping["Audio"][key] = "Audio"
                    elif is_game_objects_setting(key):
                        self.section_tab_mapping["GameObjects"][key] = "GameObjects"
                    elif is_map_specific_game_object_setting(key):
                        for map_name in self.maps_with_objects.keys():
                            if map_name == 'main':
                                map_tab = f"{map_name.title()}GameObjects"
                                if map_tab not in self.section_tab_mapping:
                                    self.section_tab_mapping[map_tab] = {}
                                self.section_tab_mapping[map_tab][key] = map_tab
                                break
                    elif value.lower() in ['true', 'false']:
                        self.section_tab_mapping["Toggles"][key] = "Toggles"
                    else:
                        self.section_tab_mapping["Values"][key] = "Values"
                elif section == "SCRIPT KEYBINDS":
                    self.section_tab_mapping["Keybinds"][key] = "Keybinds"
    
    def build_key_binding_maps(self):
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
    
    def create_widgets(self):
        """Create widgets for each configuration section"""
        # Clear loading indicators from all panels
        for tab_name, panel in self.tabs.items():
            panel.DestroyChildren()
            panel.sizer = wx.BoxSizer(wx.VERTICAL)
            panel.SetSizer(panel.sizer)
        
        for section in self.config.config.sections():
            if section == "POI": 
                continue
                
            for key in self.config.config[section]:
                value_string = self.config.config[section][key]
                
                if section == "Toggles":
                    self.create_checkbox("Toggles", key, value_string)
                elif section == "Values":
                    self.create_value_entry("Values", key, value_string)
                elif section == "Audio":
                    value, _ = self.extract_value_and_description(value_string)
                    if value.lower() in ['true', 'false']:
                        self.create_checkbox("Audio", key, value_string)
                    elif key.endswith('Volume') or key == 'MasterVolume':
                        self.create_volume_entry("Audio", key, value_string)
                    else:
                        self.create_value_entry("Audio", key, value_string)
                elif section == "GameObjects":
                    value, _ = self.extract_value_and_description(value_string)
                    if value.lower() in ['true', 'false']:
                        self.create_checkbox("GameObjects", key, value_string)
                    else:
                        self.create_value_entry("GameObjects", key, value_string)
                elif section.endswith("GameObjects"):
                    tab_name = section
                    value, _ = self.extract_value_and_description(value_string)
                    if value.lower() in ['true', 'false']:
                        self.create_checkbox(tab_name, key, value_string)
                    else:
                        self.create_value_entry(tab_name, key, value_string)
                elif section == "Keybinds":
                    self.create_keybind_entry("Keybinds", key, value_string)
                elif section == "SETTINGS":
                    val_part, _ = self.extract_value_and_description(value_string)
                    if is_audio_setting(key):
                        if val_part.lower() in ['true', 'false']:
                            self.create_checkbox("Audio", key, value_string)
                        elif key.endswith('Volume') or key == 'MasterVolume':
                            self.create_volume_entry("Audio", key, value_string)
                        else:
                            self.create_value_entry("Audio", key, value_string)
                    elif is_game_objects_setting(key):
                        if val_part.lower() in ['true', 'false']:
                            self.create_checkbox("GameObjects", key, value_string)
                        else:
                            self.create_value_entry("GameObjects", key, value_string)
                    elif is_map_specific_game_object_setting(key):
                        target_tab = "MainGameObjects"
                        for map_name in self.maps_with_objects.keys():
                            if map_name == 'main':
                                target_tab = f"{map_name.title()}GameObjects"
                                break
                        
                        if val_part.lower() in ['true', 'false']:
                            self.create_checkbox(target_tab, key, value_string)
                        else:
                            self.create_value_entry(target_tab, key, value_string)
                    elif val_part.lower() in ['true', 'false']:
                        self.create_checkbox("Toggles", key, value_string)
                    else:
                        self.create_value_entry("Values", key, value_string)
                elif section == "SCRIPT KEYBINDS":
                    self.create_keybind_entry("Keybinds", key, value_string)
        
        # Refresh all panels
        for panel in self.tabs.values():
            panel.SetupScrolling(scroll_x=False, scroll_y=True)
    
    def create_checkbox(self, tab_name: str, key: str, value_string: str):
        """Create a checkbox for a boolean setting"""
        if tab_name not in self.tabs:
            return
            
        value, description = self.extract_value_and_description(value_string)
        bool_value = value.lower() == 'true'
        
        panel = self.tabs[tab_name]
        checkbox = wx.CheckBox(panel, label=key)
        checkbox.SetValue(bool_value)
        checkbox.description = description
        
        checkbox.Bind(wx.EVT_SET_FOCUS, self.onWidgetFocus)
        checkbox.Bind(wx.EVT_CHAR_HOOK, self.onControlCharHook)
        
        self.tab_widgets[tab_name].append(checkbox)
        self.tab_variables[tab_name][key] = checkbox
        
        if not hasattr(panel, 'sizer'):
            panel.sizer = wx.BoxSizer(wx.VERTICAL)
            panel.SetSizer(panel.sizer)
        
        panel.sizer.Add(checkbox, flag=wx.ALL, border=5)
    
    def create_value_entry(self, tab_name: str, key: str, value_string: str):
        """Create a text entry field or spin control for a value setting"""
        if tab_name not in self.tabs:
            return
            
        value, description = self.extract_value_and_description(value_string)
        
        panel = self.tabs[tab_name]
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        label = wx.StaticText(panel, label=key)
        
        is_numeric = self.is_numeric_setting(key, value)
        
        if is_numeric:
            try:
                numeric_value = int(float(value))
            except (ValueError, TypeError):
                numeric_value = 0
            
            min_val, max_val = self.get_value_range(key)
            
            entry = wx.SpinCtrl(panel, value=str(numeric_value), min=min_val, max=max_val)
            entry.SetValue(numeric_value)
        else:
            entry = wx.TextCtrl(panel, value=value, style=wx.TE_PROCESS_ENTER)
            entry.Bind(wx.EVT_CHAR_HOOK, self.onTextCharHook)
        
        entry.description = description
        
        entry.Bind(wx.EVT_SET_FOCUS, self.onWidgetFocus)
        
        sizer.Add(label, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=3)
        sizer.Add(entry, proportion=1, flag=wx.EXPAND | wx.ALL, border=3)
        
        self.tab_widgets[tab_name].extend([label, entry])
        self.tab_variables[tab_name][key] = entry
        
        if not hasattr(panel, 'sizer'):
            panel.sizer = wx.BoxSizer(wx.VERTICAL)
            panel.SetSizer(panel.sizer)
        
        panel.sizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=2)
    
    def create_volume_entry(self, tab_name: str, key: str, value_string: str):
        """Create a volume entry field with test button"""
        if tab_name not in self.tabs:
            return
            
        value, description = self.extract_value_and_description(value_string)
        
        panel = self.tabs[tab_name]
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        label = wx.StaticText(panel, label=key)
        
        try:
            volume_value = float(value)
            scaled_value = int(volume_value * 100)
        except (ValueError, TypeError):
            scaled_value = 100
        
        entry = wx.SpinCtrl(panel, value=str(scaled_value), min=0, max=100)
        entry.SetValue(scaled_value)
        entry.description = description
        
        test_button = wx.Button(panel, label="Test")
        test_button.description = f"Test {key} volume setting"
        
        entry.Bind(wx.EVT_SET_FOCUS, self.onWidgetFocus)
        test_button.Bind(wx.EVT_SET_FOCUS, self.onWidgetFocus)
        
        test_button.Bind(wx.EVT_BUTTON, lambda evt: self.test_volume(key, str(entry.GetValue() / 100.0)))
        
        sizer.Add(label, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=3)
        sizer.Add(entry, proportion=1, flag=wx.EXPAND | wx.ALL, border=3)
        sizer.Add(test_button, flag=wx.ALL, border=3)
        
        self.tab_widgets[tab_name].extend([label, entry, test_button])
        self.tab_variables[tab_name][key] = entry
        
        if not hasattr(panel, 'sizer'):
            panel.sizer = wx.BoxSizer(wx.VERTICAL)
            panel.SetSizer(panel.sizer)
        
        panel.sizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=2)
    
    def create_keybind_entry(self, tab_name: str, key: str, value_string: str):
        """Create a keybind button that shows current bind and captures new ones"""
        if tab_name not in self.tabs:
            return
            
        value, description = self.extract_value_and_description(value_string)
        
        panel = self.tabs[tab_name]
        
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        label = wx.StaticText(panel, label=key)
        
        button_text = f"{key}: {value}" if value else f"{key}: Unbound"
        keybind_button = wx.Button(panel, label=button_text)
        keybind_button.description = description
        
        keybind_button.Bind(wx.EVT_SET_FOCUS, self.onWidgetFocus)
        keybind_button.Bind(wx.EVT_CHAR_HOOK, self.onControlCharHook)
        keybind_button.Bind(wx.EVT_BUTTON, lambda evt: self.capture_keybind(key, keybind_button))
        
        sizer.Add(label, flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=3)
        sizer.Add(keybind_button, proportion=1, flag=wx.EXPAND | wx.ALL, border=3)
        
        self.tab_widgets[tab_name].extend([label, keybind_button])
        self.tab_variables[tab_name][key] = keybind_button
        
        if not hasattr(panel, 'sizer'):
            panel.sizer = wx.BoxSizer(wx.VERTICAL)
            panel.SetSizer(panel.sizer)
        
        panel.sizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=2)
    
    def onControlCharHook(self, event):
        """Handle char events for controls to disable arrow navigation"""
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_TAB:
            if self.handle_tab_navigation(event):
                return
            event.Skip()
            return
        
        if key_code in [wx.WXK_UP, wx.WXK_DOWN, wx.WXK_LEFT, wx.WXK_RIGHT]:
            return
        
        event.Skip()
    
    def onTextCharHook(self, event):
        """Handle char events for text controls"""
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_TAB:
            if self.handle_tab_navigation(event):
                return
            event.Skip()
            return
        
        if key_code in [wx.WXK_UP, wx.WXK_DOWN]:
            return
        
        event.Skip()
    
    def is_numeric_setting(self, key: str, value: str) -> bool:
        """Determine if a setting should use a spin control"""
        try:
            float(value)
            numeric = True
        except (ValueError, TypeError):
            numeric = False
        
        numeric_keywords = ['sensitivity', 'delay', 'steps', 'speed', 'volume', 'distance', 'radius']
        is_numeric_key = any(keyword in key.lower() for keyword in numeric_keywords)
        
        return numeric and is_numeric_key
    
    def get_value_range(self, key: str) -> tuple:
        """Get reasonable min/max values for numeric settings"""
        key_lower = key.lower()
        
        if 'volume' in key_lower:
            return (0, 1000)
        elif 'sensitivity' in key_lower:
            return (1, 50000)
        elif 'delay' in key_lower:
            return (0, 10000)
        elif 'steps' in key_lower:
            return (1, 10000)
        elif 'speed' in key_lower:
            return (0, 10000)
        elif 'distance' in key_lower or 'radius' in key_lower:
            return (1, 10000)
        else:
            return (-10000, 10000)
    
    def test_volume(self, volume_key: str, volume_value: str):
        """Test a volume setting by playing an appropriate sound"""
        try:
            volume = float(volume_value)
            volume = max(0.0, min(volume, 1.0))
            
            sound_file = None
            if volume_key == 'MasterVolume':
                sound_file = 'sounds/poi.ogg'
            elif volume_key == 'POIVolume':
                sound_file = 'sounds/poi.ogg'
            elif volume_key == 'StormVolume':
                sound_file = 'sounds/storm.ogg'
            elif volume_key == 'DynamicObjectVolume':
                sound_file = 'sounds/dynamicobject.ogg'
            else:
                clean_key = volume_key.replace('Volume', '').lower()
                for sound_name in get_available_sounds():
                    if clean_key in sound_name.lower():
                        sound_file = f'sounds/{sound_name}.ogg'
                        break
                
                if not sound_file:
                    sound_file = 'sounds/poi.ogg'
            
            if not os.path.exists(sound_file):
                return
            
            if volume_key not in self.test_audio_instances:
                self.test_audio_instances[volume_key] = SpatialAudio(sound_file)
            
            audio_instance = self.test_audio_instances[volume_key]
            
            if volume_key == 'MasterVolume':
                audio_instance.set_master_volume(volume)
                audio_instance.set_individual_volume(1.0)
            else:
                master_vol = 1.0
                if 'MasterVolume' in self.tab_variables.get("Audio", {}):
                    try:
                        master_vol = float(self.tab_variables["Audio"]['MasterVolume'].GetValue()) / 100.0
                    except:
                        master_vol = 1.0
                
                audio_instance.set_master_volume(master_vol)
                audio_instance.set_individual_volume(volume)
            
            audio_instance.play_audio(left_weight=0.5, right_weight=0.5, volume=1.0)
            
        except ValueError:
            pass
        except Exception as e:
            logger.error(f"Error testing volume: {e}")
    
    def capture_keybind(self, action_name: str, button_widget: wx.Button):
        """Start capturing a new keybind"""
        original_text = button_widget.GetLabel()
        button_widget.SetLabel(f"{action_name}: Press any key...")
        
        self.capturing_key = True
        self.capture_widget = button_widget
        self.capture_action = action_name
        
        original_value = ""
        if self.config.config.has_section("Keybinds") and action_name in self.config.config["Keybinds"]:
            original_value, _ = self.extract_value_and_description(self.config.config["Keybinds"][action_name])
        
        self.original_capture_value = original_value
    
    def handle_key_capture(self):
        """Handle key capture using input utilities"""
        if not self.capturing_key:
            return
            
        new_key = get_pressed_key_combination()
        
        if new_key:
            if validate_key_combination(new_key):
                new_key_lower = new_key.lower()
                old_key_for_action = self.action_to_key.get(self.capture_action, "")
                
                if old_key_for_action and self.key_to_action.get(old_key_for_action) == self.capture_action:
                    self.key_to_action.pop(old_key_for_action, None)
                self.action_to_key.pop(self.capture_action, None)
                
                if new_key_lower and new_key_lower in self.key_to_action:
                    conflicting_action = self.key_to_action[new_key_lower]
                    if conflicting_action != self.capture_action:
                        self.action_to_key.pop(conflicting_action, None)
                        for tab_vars in self.tab_variables.values():
                            if conflicting_action in tab_vars:
                                tab_vars[conflicting_action].SetLabel(f"{conflicting_action}: Unbound")
                                break
                
                if new_key_lower:
                    self.key_to_action[new_key_lower] = self.capture_action
                self.action_to_key[self.capture_action] = new_key_lower
                
                self.capture_widget.SetLabel(f"{self.capture_action}: {new_key}")
            else:
                if self.original_capture_value:
                    self.capture_widget.SetLabel(f"{self.capture_action}: {self.original_capture_value}")
                else:
                    self.capture_widget.SetLabel(f"{self.capture_action}: Unbound")
            
            self.capturing_key = False
            self.capture_widget = None
            self.capture_action = None
    
    def onKeyEvent(self, event):
        """Handle key events for shortcuts and capture"""
        key_code = event.GetKeyCode()
        focused = self.FindFocus()
        
        if self.capturing_key:
            if key_code == wx.WXK_ESCAPE:
                if self.original_capture_value:
                    self.capture_widget.SetLabel(f"{self.capture_action}: {self.original_capture_value}")
                else:
                    self.capture_widget.SetLabel(f"{self.capture_action}: Unbound")
                self.capturing_key = False
                self.capture_widget = None
                self.capture_action = None
                return
            else:
                self.handle_key_capture()
                return
        
        if key_code == wx.WXK_TAB:
            if self.handle_tab_navigation(event):
                return
        
        if key_code == ord('R') or key_code == ord('r'):
            if focused:
                self.reset_focused_setting(focused)
                return
        elif key_code == wx.WXK_DELETE:
            if focused and self.is_keybind_button(focused):
                self.unbind_keybind(focused)
                return
        elif key_code == ord('T') or key_code == ord('t'):
            if focused and self.is_volume_entry(focused):
                self.test_focused_volume(focused)
                return
        elif key_code == wx.WXK_ESCAPE:
            self.save_and_close()
            return
        
        event.Skip()
    
    def is_keybind_button(self, widget):
        """Check if widget is a keybind button"""
        for tab_name in self.tab_variables:
            if tab_name == "Keybinds":
                for key, button in self.tab_variables[tab_name].items():
                    if button == widget and isinstance(widget, wx.Button):
                        return True
        return False
    
    def is_volume_entry(self, widget):
        """Check if widget is a volume entry"""
        for tab_name in self.tab_variables:
            for key, entry in self.tab_variables[tab_name].items():
                if entry == widget and (key.endswith('Volume') or key == 'MasterVolume'):
                    return True
        return False
    
    def test_focused_volume(self, widget):
        """Test volume for focused widget"""
        for tab_name in self.tab_variables:
            for key, entry in self.tab_variables[tab_name].items():
                if entry == widget:
                    if isinstance(entry, wx.SpinCtrl):
                        volume_value = str(entry.GetValue() / 100.0)
                    else:
                        volume_value = entry.GetValue()
                    self.test_volume(key, volume_value)
                    return
    
    def unbind_keybind(self, widget):
        """Unbind a keybind by setting it to empty"""
        for tab_name in self.tab_variables:
            if tab_name == "Keybinds":
                for action_name, button in self.tab_variables[tab_name].items():
                    if button == widget:
                        old_key = self.action_to_key.get(action_name, "")
                        if old_key and old_key in self.key_to_action:
                            self.key_to_action.pop(old_key, None)
                        
                        if action_name in self.action_to_key:
                            self.action_to_key.pop(action_name, None)
                        
                        button.SetLabel(f"{action_name}: Unbound")
                        return
    
    def reset_focused_setting(self, widget):
        """Reset focused setting to default value"""
        for tab_name in self.tab_variables:
            for key, stored_widget in self.tab_variables[tab_name].items():
                if stored_widget == widget:
                    lookup_section = tab_name
                    if tab_name.endswith("GameObjects"):
                        lookup_section = tab_name
                    elif tab_name == "Audio":
                        lookup_section = "Audio"
                    elif tab_name == "GameObjects":
                        lookup_section = "GameObjects"
                    
                    default_full_value = get_default_config_value_string(lookup_section, key)
                    
                    if not default_full_value:
                        return
                    
                    default_value_part, _ = self.extract_value_and_description(default_full_value)
                    
                    if isinstance(widget, wx.CheckBox):
                        bool_value = default_value_part.lower() == 'true'
                        widget.SetValue(bool_value)
                        speaker.speak(f"{key} reset to default: {'checked' if bool_value else 'unchecked'}")
                    elif isinstance(widget, wx.SpinCtrl):
                        if key.endswith('Volume') or key == 'MasterVolume':
                            try:
                                volume_value = float(default_value_part)
                                scaled_value = int(volume_value * 100)
                                widget.SetValue(scaled_value)
                                speaker.speak(f"{key} reset to default: {scaled_value}%")
                            except (ValueError, TypeError):
                                widget.SetValue(100)
                                speaker.speak(f"{key} reset to default: 100%")
                        else:
                            try:
                                numeric_value = int(float(default_value_part))
                                widget.SetValue(numeric_value)
                                speaker.speak(f"{key} reset to default: {numeric_value}")
                            except (ValueError, TypeError):
                                widget.SetValue(0)
                                speaker.speak(f"{key} reset to default: 0")
                    elif isinstance(widget, wx.TextCtrl):
                        widget.SetValue(default_value_part)
                        speaker.speak(f"{key} reset to default: {default_value_part}")
                    elif isinstance(widget, wx.Button) and tab_name == "Keybinds":
                        action_being_reset = key
                        
                        old_key = self.action_to_key.get(action_being_reset, "")
                        if old_key and self.key_to_action.get(old_key) == action_being_reset:
                            self.key_to_action.pop(old_key, None)
                        
                        new_default_key_lower = default_value_part.lower()
                        if new_default_key_lower and new_default_key_lower in self.key_to_action:
                            conflicting_action = self.key_to_action[new_default_key_lower]
                            if conflicting_action != action_being_reset:
                                self.key_to_action.pop(new_default_key_lower, None)
                                self.action_to_key.pop(conflicting_action, None)
                                for other_tab_vars in self.tab_variables.values():
                                    if conflicting_action in other_tab_vars:
                                        other_tab_vars[conflicting_action].SetLabel(f"{conflicting_action}: Unbound")
                                        break
                        
                        widget.SetLabel(f"{key}: {default_value_part}")
                        self.action_to_key[action_being_reset] = new_default_key_lower
                        if new_default_key_lower:
                            self.key_to_action[new_default_key_lower] = action_being_reset
                        
                        speaker.speak(f"{key} keybind reset to default: {default_value_part}")
                    
                    return
    
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
    
    def save_and_close(self):
        """Save configuration and close"""
        try:
            for audio_instance in self.test_audio_instances.values():
                try:
                    audio_instance.cleanup()
                except Exception:
                    pass
            self.test_audio_instances.clear()
            
            config_parser_instance = self.config.config

            required_sections = ["Toggles", "Values", "Audio", "GameObjects", "Keybinds", "POI"]
            for map_name in self.maps_with_objects.keys():
                required_sections.append(f"{map_name.title()}GameObjects")

            for section_name in required_sections:
                if not config_parser_instance.has_section(section_name):
                    config_parser_instance.add_section(section_name)

            for tab_name in self.tab_variables:
                for setting_key, widget in self.tab_variables[tab_name].items():
                    description = getattr(widget, 'description', '')
                    
                    if isinstance(widget, wx.CheckBox):
                        value_to_save = 'true' if widget.GetValue() else 'false'
                    elif isinstance(widget, wx.SpinCtrl):
                        if setting_key.endswith('Volume') or setting_key == 'MasterVolume':
                            value_to_save = str(widget.GetValue() / 100.0)
                        else:
                            value_to_save = str(widget.GetValue())
                    elif isinstance(widget, wx.Button) and tab_name == "Keybinds":
                        button_text = widget.GetLabel()
                        if ": " in button_text:
                            value_to_save = button_text.split(": ", 1)[1]
                            if value_to_save == "Unbound":
                                value_to_save = ""
                        else:
                            value_to_save = ""
                            
                        if value_to_save.strip() and not validate_key_combination(value_to_save):
                            value_to_save = ""
                    else:
                        value_to_save = widget.GetValue()
                    
                    value_string_to_save = f"{value_to_save} \"{description}\"" if description else str(value_to_save)
                    
                    if tab_name.endswith("GameObjects"):
                        target_section = tab_name
                    else:
                        target_section = tab_name
                    
                    config_parser_instance.set(target_section, setting_key, value_string_to_save)

            self.update_callback(config_parser_instance)
            speaker.speak("Configuration saved and applied.")
            
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            error = DisplayableError(
                f"Error saving configuration: {str(e)}",
                "Configuration Error"
            )
            error.displayError(self)
            return
            
        self.EndModal(wx.ID_OK)


def launch_config_gui(config_obj: 'Config', 
                     update_callback: Callable[[configparser.ConfigParser], None], 
                     default_config_str: Optional[str] = None) -> None:
    """Launch the configuration GUI"""
    try:
        app = wx.GetApp()
        if app is None:
            app = wx.App(False)
        
        dlg = ConfigGUI(None, config_obj, update_callback, default_config_str)
        
        ensure_window_focus_and_center_mouse(dlg)
        
        result = dlg.ShowModal()
        dlg.Destroy()
        
    except Exception as e:
        logger.error(f"Error launching configuration GUI: {e}")
        error = DisplayableError(
            f"Error launching configuration GUI: {str(e)}",
            "Application Error"
        )
        error.displayError()