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
    AccessibleDialog, BoxSizerHelper, ButtonHelper, DisplayableError,
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


# Keys routed to the "Advanced" tab regardless of source section.
ADVANCED_KEYS = frozenset({
    "SimplifySpeechOutput",
    "IgnoreNumlock",
    "ResetSensitivity",
    "TurnAroundSensitivity",
    "RecenterDelay",
    "TurnDelay",
    "RecenterStepDelay",
    "RecenterStepSpeed",
    "RecenterLookDown",
    "RecenterLookUp",
    "ResetRecenterLookDown",
    "ResetRecenterLookUp",
    "StormPingInterval",
    "ContinuousPingMinInterval",
    "ContinuousPingMaxInterval",
    "ContinuousPingDistanceExponent",
    "PositionUpdateInterval",
    "MaxInstancesForGameObjectPositioning",
    # Onboarding wizard re-run toggle.
    "FirstRunComplete",
})


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

        # Polling timer picks up mouse buttons (EVT_CHAR_HOOK can't see them).
        self._capture_timer: Optional[wx.Timer] = None
        # Arms after a no-keys-pressed tick so the capture activator
        # (Enter/Space/click) isn't sampled as the user's binding.
        self._capture_armed = False

        self.setupDialog()

        # Set a proper size so the dialog isn't tiny before deferred widgets load
        display = wx.Display(wx.Display.GetFromWindow(self) if self.GetParent() else 0)
        screen_rect = display.GetClientArea()
        width = min(700, int(screen_rect.GetWidth() * 0.6))
        height = min(600, int(screen_rect.GetHeight() * 0.7))
        self.SetSize(width, height)
        self.SetMinSize((400, 350))
        self.CentreOnScreen()

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
        """Populate active tab now; queue rest for background build."""
        try:
            self.analyze_config()

            self._tab_built = {tab_name: False for tab_name in self.tabs}
            self._prebuild_queue: List[str] = []

            active_idx = self.notebook.GetSelection()
            if active_idx == wx.NOT_FOUND or active_idx >= self.notebook.GetPageCount():
                active_idx = 0
            active_tab = self.notebook.GetPageText(active_idx)

            self._build_tab(active_tab)
            self.Layout()

            self._prebuild_queue = [
                t for t in self.tabs if t != active_tab and not self._tab_built.get(t, False)
            ]
            if self._prebuild_queue:
                wx.CallLater(50, self._prebuild_next)
        except Exception as e:
            logger.error(f"Error populating widgets: {e}")
            speaker.speak("Error loading configuration")

    def _prebuild_next(self) -> None:
        """Build the next queued tab, then reschedule."""
        try:
            if self.IsBeingDeleted() or not self.IsShown():
                return
        except Exception:
            return
        if not getattr(self, '_prebuild_queue', None):
            return

        tab_name = self._prebuild_queue.pop(0)
        if not self._tab_built.get(tab_name, False):
            try:
                self._build_tab(tab_name)
            except Exception as e:
                logger.error(f"Error pre-building tab {tab_name!r}: {e}")

        if self._prebuild_queue:
            wx.CallLater(50, self._prebuild_next)

    def _build_tab(self, tab_name: str) -> None:
        """Construct widgets for a single tab. Idempotent; cheap to call again."""
        if tab_name not in self.tabs:
            return
        if self._tab_built.get(tab_name):
            return

        panel = self.tabs[tab_name]
        panel.Freeze()
        try:
            self.create_widgets(target_tab=tab_name)
            self.build_tab_control_lists(target_tab=tab_name)
        finally:
            panel.Thaw()
        panel.Layout()
        self._tab_built[tab_name] = True

    def build_tab_control_lists(self, target_tab: Optional[str] = None):
        """Rebuild focusable-widget lists. ``target_tab=None`` does all tabs."""
        if target_tab is not None:
            if target_tab not in self.tabs:
                return
            self.tab_control_widgets[target_tab] = []
            self._collect_focusable_widgets(
                self.tabs[target_tab], self.tab_control_widgets[target_tab]
            )
            return
        for tab_name, panel in self.tabs.items():
            self.tab_control_widgets[tab_name] = []
            self._collect_focusable_widgets(panel, self.tab_control_widgets[tab_name])
    
    def _collect_focusable_widgets(self, parent, widget_list):
        """Recursively collect focusable widgets in tab order. Skip hidden subtrees."""
        for child in parent.GetChildren():
            try:
                if not child.IsShown():
                    continue
            except Exception:
                pass
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
        """Handle notebook page change, build tab lazily, announce."""
        page_index = event.GetSelection()
        if page_index >= 0 and page_index < self.notebook.GetPageCount():
            tab_text = self.notebook.GetPageText(page_index)
            # Build this tab on first visit so opening the dialog stays
            # snappy when the user only ever touches one or two tabs.
            if hasattr(self, '_tab_built') and not self._tab_built.get(tab_text, False):
                self._build_tab(tab_text)
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

        # Per-map GameObjects sections aren't separate tabs anymore — they
        # render inside the GameObjects tab via a Map dropdown.
        tab_names = ["Toggles", "Values", "Audio", "GameObjects", "Keybinds", "Advanced"]

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
    
    def create_widgets(self, target_tab: Optional[str] = None):
        """Create widgets. ``target_tab`` filters to one tab; ADVANCED_KEYS divert to "Advanced"."""
        # GameObjects gets a special map-dropdown layout; route there.
        if target_tab == "GameObjects":
            self._build_gameobjects_tab_layout()
            return

        if target_tab is None:
            self._build_gameobjects_tab_layout()
            panels_to_reset = [(n, p) for n, p in self.tabs.items() if n != "GameObjects"]
        else:
            if target_tab not in self.tabs:
                return
            panels_to_reset = [(target_tab, self.tabs[target_tab])]
        for tab_name, panel in panels_to_reset:
            panel.DestroyChildren()
            panel.sizer = wx.BoxSizer(wx.VERTICAL)
            panel.SetSizer(panel.sizer)

        def _matches(actual_tab: str) -> bool:
            return target_tab is None or actual_tab == target_tab

        def _resolve(natural_tab: str, key_name: str) -> str:
            return "Advanced" if key_name in ADVANCED_KEYS else natural_tab

        for section in self.config.config.sections():
            if section == "POI":
                continue

            for key in self.config.config[section]:
                value_string = self.config.config[section][key]

                if section == "Toggles":
                    actual_tab = _resolve("Toggles", key)
                    if _matches(actual_tab):
                        self.create_checkbox(actual_tab, key, value_string)
                elif section == "Values":
                    actual_tab = _resolve("Values", key)
                    if _matches(actual_tab):
                        self.create_value_entry(actual_tab, key, value_string)
                elif section == "Audio":
                    actual_tab = _resolve("Audio", key)
                    if _matches(actual_tab):
                        value, _ = self.extract_value_and_description(value_string)
                        if value.lower() in ['true', 'false']:
                            self.create_checkbox(actual_tab, key, value_string)
                        elif key.endswith('Volume') or key == 'MasterVolume':
                            self.create_volume_entry(actual_tab, key, value_string)
                        else:
                            self.create_value_entry(actual_tab, key, value_string)
                elif section == "GameObjects":
                    # Universal [GameObjects] keys are rendered by
                    # _build_gameobjects_tab_layout; only the advanced-
                    # routed ones need standard handling.
                    actual_tab = _resolve("GameObjects", key)
                    if actual_tab == "GameObjects":
                        continue
                    if _matches(actual_tab):
                        value, _ = self.extract_value_and_description(value_string)
                        if value.lower() in ['true', 'false']:
                            self.create_checkbox(actual_tab, key, value_string)
                        else:
                            self.create_value_entry(actual_tab, key, value_string)
                elif section.endswith("GameObjects"):
                    # Per-map sections live entirely inside the
                    # GameObjects tab's map sub-panels.
                    continue
                elif section == "Keybinds":
                    # Keybinds aren't candidates for Advanced — they're
                    # all user-facing customisation by definition.
                    if _matches("Keybinds"):
                        self.create_keybind_entry("Keybinds", key, value_string)
                elif section == "Setup":
                    # [Setup] keys are wizard-related toggles; route via
                    # ADVANCED_KEYS so they live on the Advanced tab.
                    actual_tab = _resolve("Advanced", key)
                    if _matches(actual_tab):
                        value, _ = self.extract_value_and_description(value_string)
                        if value.lower() in ['true', 'false']:
                            self.create_checkbox(actual_tab, key, value_string)
                        else:
                            self.create_value_entry(actual_tab, key, value_string)
                elif section == "SETTINGS":
                    val_part, _ = self.extract_value_and_description(value_string)
                    if is_audio_setting(key):
                        actual_tab = _resolve("Audio", key)
                        if not _matches(actual_tab):
                            continue
                        if val_part.lower() in ['true', 'false']:
                            self.create_checkbox(actual_tab, key, value_string)
                        elif key.endswith('Volume') or key == 'MasterVolume':
                            self.create_volume_entry(actual_tab, key, value_string)
                        else:
                            self.create_value_entry(actual_tab, key, value_string)
                    elif is_game_objects_setting(key):
                        actual_tab = _resolve("GameObjects", key)
                        if not _matches(actual_tab):
                            continue
                        if val_part.lower() in ['true', 'false']:
                            self.create_checkbox(actual_tab, key, value_string)
                        else:
                            self.create_value_entry(actual_tab, key, value_string)
                    elif is_map_specific_game_object_setting(key):
                        legacy_target = "MainGameObjects"
                        for map_name in self.maps_with_objects.keys():
                            if map_name == 'main':
                                legacy_target = f"{map_name.title()}GameObjects"
                                break
                        actual_tab = _resolve(legacy_target, key)
                        if not _matches(actual_tab):
                            continue
                        if val_part.lower() in ['true', 'false']:
                            self.create_checkbox(actual_tab, key, value_string)
                        else:
                            self.create_value_entry(actual_tab, key, value_string)
                    elif val_part.lower() in ['true', 'false']:
                        actual_tab = _resolve("Toggles", key)
                        if _matches(actual_tab):
                            self.create_checkbox(actual_tab, key, value_string)
                    else:
                        actual_tab = _resolve("Values", key)
                        if _matches(actual_tab):
                            self.create_value_entry(actual_tab, key, value_string)
                elif section == "SCRIPT KEYBINDS":
                    if _matches("Keybinds"):
                        self.create_keybind_entry("Keybinds", key, value_string)

        for _tab_name, panel in panels_to_reset:
            panel.SetupScrolling(scroll_x=False, scroll_y=True)

    # ------------------------------------------------------------------
    # GameObjects tab — universal settings + map dropdown + per-map
    # sub-panels (replaces the old per-map notebook tabs).
    # ------------------------------------------------------------------

    def _build_gameobjects_tab_layout(self) -> None:
        """Lay out the GameObjects tab: universal section, map picker, per-map host."""
        panel = self.tabs.get("GameObjects")
        if panel is None:
            return

        panel.DestroyChildren()
        panel.sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(panel.sizer)

        # Reset trackers — Advanced-routed keys keep their existing entries.
        self.tab_widgets["GameObjects"] = []
        self.tab_variables["GameObjects"] = {}

        # 1. Universal [GameObjects] settings (skip ADVANCED_KEYS — those go on Advanced).
        if self.config.config.has_section("GameObjects"):
            for key in self.config.config["GameObjects"]:
                if key in ADVANCED_KEYS:
                    continue
                value_string = self.config.config["GameObjects"][key]
                value, _ = self.extract_value_and_description(value_string)
                if value.lower() in ['true', 'false']:
                    self.create_checkbox("GameObjects", key, value_string)
                else:
                    self.create_value_entry("GameObjects", key, value_string)

        # 2. Map dropdown row.
        available_maps = sorted(self.maps_with_objects.keys()) if self.maps_with_objects else []
        if 'main' in available_maps:
            available_maps.remove('main')
            available_maps.insert(0, 'main')

        if available_maps:
            chooser_row = wx.BoxSizer(wx.HORIZONTAL)
            chooser_row.Add(wx.StaticText(panel, label="Map:"),
                            flag=wx.ALIGN_CENTER_VERTICAL | wx.ALL, border=5)
            self._gameobjects_map_keys = available_maps
            self._gameobjects_map_choice = wx.Choice(
                panel, choices=[m.replace('_', ' ').title() for m in available_maps],
            )
            self._gameobjects_map_choice.SetSelection(0)
            self._gameobjects_map_choice.description = (
                "Pick which map's per-object tracking settings to view and edit."
            )
            self._gameobjects_map_choice.Bind(wx.EVT_SET_FOCUS, self.onWidgetFocus)
            self._gameobjects_map_choice.Bind(wx.EVT_CHOICE, self._on_gameobjects_map_changed)
            chooser_row.Add(self._gameobjects_map_choice, flag=wx.ALL, border=5)
            panel.sizer.Add(chooser_row, flag=wx.ALL, border=2)

        # 3. Sub-panel host. Each map's settings live in its own panel,
        # built lazily on first show, then hidden / shown as the
        # dropdown changes. Keeps state across switches.
        self._gameobjects_subpanel_host = wx.Panel(panel)
        host_sizer = wx.BoxSizer(wx.VERTICAL)
        self._gameobjects_subpanel_host.SetSizer(host_sizer)
        panel.sizer.Add(self._gameobjects_subpanel_host, proportion=1,
                        flag=wx.EXPAND | wx.ALL, border=2)

        self._gameobjects_subpanels = {}  # map_name -> wx.Panel

        if available_maps:
            self._show_gameobjects_map(available_maps[0])

        try:
            panel.SetupScrolling(scroll_x=False, scroll_y=True)
        except Exception:
            pass

    def _on_gameobjects_map_changed(self, event):
        idx = self._gameobjects_map_choice.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        try:
            map_name = self._gameobjects_map_keys[idx]
        except (IndexError, AttributeError):
            return
        self._show_gameobjects_map(map_name)

    def _show_gameobjects_map(self, map_name: str) -> None:
        """Hide every map sub-panel, build / show the requested one."""
        host = getattr(self, "_gameobjects_subpanel_host", None)
        if host is None:
            return

        # Hide all currently visible.
        for sub in self._gameobjects_subpanels.values():
            sub.Hide()

        # Build on first request.
        if map_name not in self._gameobjects_subpanels:
            sub = wx.Panel(host)
            sub_sizer = wx.BoxSizer(wx.VERTICAL)
            sub.SetSizer(sub_sizer)
            self._build_per_map_widgets(sub, map_name)
            self._gameobjects_subpanels[map_name] = sub
            host.GetSizer().Add(sub, proportion=1, flag=wx.EXPAND)

        self._gameobjects_subpanels[map_name].Show()
        host.Layout()
        host.GetParent().Layout()
        # Refresh tab-order list so Tab navigation skips the hidden maps.
        self.build_tab_control_lists(target_tab="GameObjects")

    def _build_per_map_widgets(self, parent_panel, map_name: str) -> None:
        """Build per-object widgets for ``map_name`` onto ``parent_panel``.

        Widgets are tracked under the ``<MapName>GameObjects`` key in
        ``tab_variables`` so the existing save logic still routes each
        value back to its real config section.
        """
        section_name = f"{map_name.title()}GameObjects"
        if not self.config.config.has_section(section_name):
            return

        # Reset trackers for this section (we may rebuild on reset).
        self.tab_widgets[section_name] = []
        self.tab_variables[section_name] = {}

        for key in self.config.config[section_name]:
            if key in ADVANCED_KEYS:
                continue  # would render on Advanced, not here
            value_string = self.config.config[section_name][key]
            value, _ = self.extract_value_and_description(value_string)
            if value.lower() in ['true', 'false']:
                self.create_checkbox(section_name, key, value_string,
                                     parent_override=parent_panel)
            else:
                self.create_value_entry(section_name, key, value_string,
                                        parent_override=parent_panel)

    def _resolve_widget_parent(self, tab_name: str, parent_override=None):
        """Pick the wx parent for a widget. ``parent_override`` lets the
        GameObjects map sub-panels host widgets that are still tracked
        under a per-map ``tab_name`` key in ``tab_variables``."""
        if parent_override is not None:
            return parent_override
        return self.tabs.get(tab_name)

    def _ensure_tracking(self, tab_name: str) -> None:
        """Make sure ``tab_widgets`` / ``tab_variables`` have entries for a
        non-notebook tracking key (e.g. ``MainGameObjects``)."""
        if tab_name not in self.tab_widgets:
            self.tab_widgets[tab_name] = []
        if tab_name not in self.tab_variables:
            self.tab_variables[tab_name] = {}

    def create_checkbox(self, tab_name: str, key: str, value_string: str, parent_override=None):
        """Create a checkbox for a boolean setting."""
        panel = self._resolve_widget_parent(tab_name, parent_override)
        if panel is None:
            return

        value, description = self.extract_value_and_description(value_string)
        bool_value = value.lower() == 'true'

        checkbox = wx.CheckBox(panel, label=key)
        checkbox.SetValue(bool_value)
        checkbox.description = description

        checkbox.Bind(wx.EVT_SET_FOCUS, self.onWidgetFocus)
        checkbox.Bind(wx.EVT_CHAR_HOOK, self.onControlCharHook)

        self._ensure_tracking(tab_name)
        self.tab_widgets[tab_name].append(checkbox)
        self.tab_variables[tab_name][key] = checkbox

        if not hasattr(panel, 'sizer') or panel.GetSizer() is None:
            panel.sizer = wx.BoxSizer(wx.VERTICAL)
            panel.SetSizer(panel.sizer)
        elif not hasattr(panel, 'sizer'):
            panel.sizer = panel.GetSizer()

        panel.sizer.Add(checkbox, flag=wx.ALL, border=5)

    def create_value_entry(self, tab_name: str, key: str, value_string: str, parent_override=None):
        """Create a text entry field or spin control for a value setting."""
        panel = self._resolve_widget_parent(tab_name, parent_override)
        if panel is None:
            return

        value, description = self.extract_value_and_description(value_string)

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

        self._ensure_tracking(tab_name)
        self.tab_widgets[tab_name].extend([label, entry])
        self.tab_variables[tab_name][key] = entry

        if not hasattr(panel, 'sizer') or panel.GetSizer() is None:
            panel.sizer = wx.BoxSizer(wx.VERTICAL)
            panel.SetSizer(panel.sizer)
        elif not hasattr(panel, 'sizer'):
            panel.sizer = panel.GetSizer()

        panel.sizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=2)

    def create_volume_entry(self, tab_name: str, key: str, value_string: str, parent_override=None):
        """Create a volume entry field with test button."""
        panel = self._resolve_widget_parent(tab_name, parent_override)
        if panel is None:
            return

        value, description = self.extract_value_and_description(value_string)
        
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

        self._ensure_tracking(tab_name)
        self.tab_widgets[tab_name].extend([label, entry, test_button])
        self.tab_variables[tab_name][key] = entry

        if not hasattr(panel, 'sizer') or panel.GetSizer() is None:
            panel.sizer = wx.BoxSizer(wx.VERTICAL)
            panel.SetSizer(panel.sizer)
        elif not hasattr(panel, 'sizer'):
            panel.sizer = panel.GetSizer()

        panel.sizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=2)

    def create_keybind_entry(self, tab_name: str, key: str, value_string: str, parent_override=None):
        """Create a keybind button that shows current bind and captures new ones."""
        panel = self._resolve_widget_parent(tab_name, parent_override)
        if panel is None:
            return

        value, description = self.extract_value_and_description(value_string)
        
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

        self._ensure_tracking(tab_name)
        self.tab_widgets[tab_name].extend([label, keybind_button])
        self.tab_variables[tab_name][key] = keybind_button

        if not hasattr(panel, 'sizer') or panel.GetSizer() is None:
            panel.sizer = wx.BoxSizer(wx.VERTICAL)
            panel.SetSizer(panel.sizer)
        elif not hasattr(panel, 'sizer'):
            panel.sizer = panel.GetSizer()

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
                sound_file = 'assets/sounds/poi.ogg'
            elif volume_key == 'POIVolume':
                sound_file = 'assets/sounds/poi.ogg'
            elif volume_key == 'StormVolume':
                sound_file = 'assets/sounds/storm.ogg'
            elif volume_key == 'DynamicObjectVolume':
                sound_file = 'assets/sounds/dynamicobject.ogg'
            else:
                clean_key = volume_key.replace('Volume', '').lower()
                for sound_name in get_available_sounds():
                    if clean_key in sound_name.lower():
                        sound_file = f'assets/sounds/{sound_name}.ogg'
                        break

                if not sound_file:
                    sound_file = 'assets/sounds/poi.ogg'
            
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

        # Mouse-click activation: nothing is held, so arm immediately and
        # let the first EVT_CHAR_HOOK keypress be captured (otherwise a
        # quick tap finishes between polling ticks and is silently lost).
        # Keyboard activation (Enter/Space still down): leave disarmed so
        # the activator key isn't captured as the binding.
        self._capture_armed = (get_pressed_key_combination() == "")
        self._start_capture_polling()

    def _start_capture_polling(self):
        """Start a wx.Timer that polls global key state during keybind capture."""
        if self._capture_timer is None:
            self._capture_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._on_capture_timer, self._capture_timer)
        if not self._capture_timer.IsRunning():
            self._capture_timer.Start(30)

    def _stop_capture_polling(self):
        """Stop the capture polling timer if it's running."""
        if self._capture_timer is not None and self._capture_timer.IsRunning():
            self._capture_timer.Stop()

    def _on_capture_timer(self, _event):
        """Timer tick — try to capture a keybind from current global key state."""
        if not self.capturing_key:
            self._stop_capture_polling()
            return
        self.handle_key_capture()

    def _cancel_capture(self):
        """Restore the captured button's label and exit capture mode."""
        if self.capture_widget is not None and self.capture_action is not None:
            if self.original_capture_value:
                self.capture_widget.SetLabel(
                    f"{self.capture_action}: {self.original_capture_value}"
                )
            else:
                self.capture_widget.SetLabel(f"{self.capture_action}: Unbound")
        self.capturing_key = False
        self.capture_widget = None
        self.capture_action = None
        self._stop_capture_polling()

    def handle_key_capture(self):
        """Handle key capture using input utilities"""
        if not self.capturing_key:
            return

        # Wait for a no-keys-pressed tick before sampling.
        if not self._capture_armed:
            if get_pressed_key_combination() == "":
                self._capture_armed = True
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
            self._stop_capture_polling()
    
    def onKeyEvent(self, event):
        """Handle key events for shortcuts and capture"""
        key_code = event.GetKeyCode()
        focused = self.FindFocus()

        if self.capturing_key:
            if key_code == wx.WXK_ESCAPE:
                self._cancel_capture()
                return
            else:
                self.handle_key_capture()
                return

        # Ctrl+F → setting search. Handled before single-letter shortcuts so
        # the F doesn't fall through to anything else.
        if event.ControlDown() and key_code in (ord('F'), ord('f')):
            self._open_search_dialog()
            return

        if key_code == wx.WXK_TAB:
            if self.handle_tab_navigation(event):
                return

        # The single-letter shortcuts below should NOT fire when a modifier
        # is held — Ctrl+R / Ctrl+T would otherwise hijack browser-style
        # combos and trigger reset/test unexpectedly.
        modifier_held = (event.ControlDown() or event.AltDown() or event.MetaDown())

        if not modifier_held and key_code in (ord('R'), ord('r')):
            if focused:
                self.reset_focused_setting(focused)
                return
        elif key_code == wx.WXK_DELETE:
            if focused and self.is_keybind_button(focused):
                self.unbind_keybind(focused)
                return
        elif not modifier_held and key_code in (ord('T'), ord('t')):
            if focused and self.is_volume_entry(focused):
                self.test_focused_volume(focused)
                return
        elif key_code == wx.WXK_ESCAPE:
            self.save_and_close()
            return

        event.Skip()

    # ------------------------------------------------------------------
    # Ctrl+F search
    # ------------------------------------------------------------------

    def _open_search_dialog(self) -> None:
        """Show the search popup; navigate to the chosen setting on accept."""
        try:
            self._ensure_all_settings_built()
            entries = self._build_search_index()
        except Exception as e:
            logger.error(f"Error building search index: {e}")
            speaker.speak("Search unavailable.")
            return

        if not entries:
            speaker.speak("No settings to search.")
            return

        speaker.speak("Search settings.")
        dlg = _SettingSearchDialog(self, entries)
        try:
            if dlg.ShowModal() == wx.ID_OK and dlg.result is not None:
                tab_internal, key = dlg.result
                self._navigate_to_setting(tab_internal, key)
        finally:
            dlg.Destroy()

    def _ensure_all_settings_built(self) -> None:
        """Build every notebook tab and every per-map GameObjects sub-panel
        so ``self.tab_variables`` covers the full setting space."""
        if not hasattr(self, "_tab_built"):
            return

        # 1. Force-build any deferred notebook tabs.
        for tab_name in list(self.tabs.keys()):
            if not self._tab_built.get(tab_name, False):
                try:
                    self._build_tab(tab_name)
                except Exception as e:
                    logger.error(f"Error pre-building tab {tab_name!r}: {e}")

        # 2. Force-build per-map GameObjects sub-panels (they're lazy-built
        #    by the Map dropdown, so non-default maps may have no widgets yet).
        host = getattr(self, "_gameobjects_subpanel_host", None)
        map_keys = getattr(self, "_gameobjects_map_keys", None)
        subpanels = getattr(self, "_gameobjects_subpanels", None)
        if host is None or not map_keys or subpanels is None:
            return
        for map_name in map_keys:
            if map_name in subpanels:
                continue
            try:
                sub = wx.Panel(host)
                sub.SetSizer(wx.BoxSizer(wx.VERTICAL))
                self._build_per_map_widgets(sub, map_name)
                sub.Hide()
                subpanels[map_name] = sub
                host.GetSizer().Add(sub, proportion=1, flag=wx.EXPAND)
            except Exception as e:
                logger.error(f"Error pre-building per-map widgets for {map_name!r}: {e}")

    def _build_search_index(self):
        """Return ``[(tab_display, tab_internal, key, description), ...]`` for
        every setting widget tracked in ``tab_variables``."""
        entries: List[Tuple[str, str, str, str]] = []
        for tab_internal, widgets in self.tab_variables.items():
            if not widgets:
                continue
            # Per-map sections like "MainGameObjects" render inside the
            # GameObjects tab via the Map dropdown — show that in the label.
            if (tab_internal.endswith("GameObjects")
                    and tab_internal != "GameObjects"):
                map_token = tab_internal[:-len("GameObjects")]
                # Convert "Main" / "Reload_Oasis" → human text.
                map_display = map_token.replace('_', ' ').strip()
                tab_display = f"GameObjects ({map_display})"
            else:
                tab_display = tab_internal
            for key, widget in widgets.items():
                description = ""
                try:
                    description = getattr(widget, "description", "") or ""
                except Exception:
                    description = ""
                entries.append((tab_display, tab_internal, key, description))
        # Stable order: by tab, then key.
        entries.sort(key=lambda e: (e[0].lower(), e[2].lower()))
        return entries

    def _navigate_to_setting(self, tab_internal: str, key: str) -> None:
        """Switch notebook (and per-map dropdown if needed), then focus widget."""
        is_per_map = (tab_internal.endswith("GameObjects")
                      and tab_internal != "GameObjects")
        target_tab = "GameObjects" if is_per_map else tab_internal

        # Switch notebook page.
        for idx in range(self.notebook.GetPageCount()):
            if self.notebook.GetPageText(idx) == target_tab:
                if self.notebook.GetSelection() != idx:
                    self.notebook.SetSelection(idx)
                # Lazy-built tabs also need explicit build before focusing.
                if hasattr(self, "_tab_built") and not self._tab_built.get(target_tab, False):
                    try:
                        self._build_tab(target_tab)
                    except Exception:
                        pass
                break

        # If per-map, point the dropdown at the right map and reveal its panel.
        if is_per_map:
            map_token = tab_internal[:-len("GameObjects")]
            map_name = map_token.lower()
            choice = getattr(self, "_gameobjects_map_choice", None)
            map_keys = getattr(self, "_gameobjects_map_keys", None)
            if choice is not None and map_keys:
                try:
                    map_idx = map_keys.index(map_name)
                    choice.SetSelection(map_idx)
                    self._show_gameobjects_map(map_name)
                except (ValueError, AttributeError) as e:
                    logger.error(f"Could not switch to map {map_name!r}: {e}")

        widget = self.tab_variables.get(tab_internal, {}).get(key)
        if widget is not None:
            wx.CallAfter(widget.SetFocus)
            speaker.speak(f"{key} on {target_tab} tab")
        else:
            speaker.speak(f"Could not focus {key}")
    
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
                    elif tab_name == "Advanced":
                        lookup_section = self._default_section_for_key(key) or tab_name

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

    def _default_section_for_key(self, key: str) -> Optional[str]:
        """Return the default-config section that owns ``key`` (cached parser)."""
        from lib.utilities.utilities import (
            DEFAULT_CONFIG,
            _create_config_parser_with_case_preserved,
        )
        parser = getattr(self, "_default_section_parser", None)
        if parser is None:
            parser = _create_config_parser_with_case_preserved()
            parser.read_string(DEFAULT_CONFIG)
            self._default_section_parser = parser
        for section in parser.sections():
            if parser.has_option(section, key):
                return section
        return None
    
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

            required_sections = ["Toggles", "Values", "Audio", "GameObjects", "Keybinds", "POI", "Setup"]
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

                    # Advanced widgets save back to their real section.
                    if tab_name == "Advanced":
                        target_section = None
                        for sec in config_parser_instance.sections():
                            if config_parser_instance.has_option(sec, setting_key):
                                target_section = sec
                                break
                        if target_section is None:
                            target_section = self._default_section_for_key(setting_key)
                        if target_section is None:
                            logger.warning(
                                f"save_and_close: no section found for advanced key {setting_key!r}, skipping"
                            )
                            continue
                    elif tab_name.endswith("GameObjects"):
                        target_section = tab_name
                    else:
                        target_section = tab_name

                    if not config_parser_instance.has_section(target_section):
                        config_parser_instance.add_section(target_section)
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


class _SettingSearchDialog(wx.Dialog):
    """Ctrl+F search popup for the config GUI.

    Shows a TextCtrl + ListBox. Typing live-filters the entries by
    substring match against ``key + description``. Up/Down from the
    text field move the list selection so the user never has to leave
    the search box. Enter accepts; Esc cancels. ``self.result`` is set
    to ``(tab_internal, key)`` on accept, ``None`` on cancel.
    """

    def __init__(self, parent: wx.Window, entries):
        super().__init__(parent, title="Search settings",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._entries = entries
        self._filtered = list(entries)
        self.result = None

        sizer = wx.BoxSizer(wx.VERTICAL)

        prompt = wx.StaticText(
            self,
            label="Type to filter. Up/Down moves selection. Enter jumps to setting.",
        )
        sizer.Add(prompt, flag=wx.ALL, border=8)

        self._search = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        sizer.Add(self._search, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        self._list = wx.ListBox(self, style=wx.LB_SINGLE)
        sizer.Add(self._list, proportion=1, flag=wx.EXPAND | wx.ALL, border=8)

        self._status = wx.StaticText(self, label="")
        sizer.Add(self._status, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        self.SetSizer(sizer)
        self.SetSize((560, 440))
        self.SetMinSize((400, 320))
        self.CentreOnParent()

        self._search.Bind(wx.EVT_TEXT, self._on_text)
        self._search.Bind(wx.EVT_TEXT_ENTER, self._on_accept)
        self._search.Bind(wx.EVT_CHAR_HOOK, self._on_search_char_hook)
        self._list.Bind(wx.EVT_LISTBOX_DCLICK, self._on_accept)
        self._list.Bind(wx.EVT_CHAR_HOOK, self._on_list_char_hook)

        self._populate_list("")
        # Search field gets focus by default — start typing immediately.
        wx.CallAfter(self._search.SetFocus)

    def _populate_list(self, query: str) -> None:
        q = query.lower().strip()
        if not q:
            self._filtered = list(self._entries)
        else:
            terms = q.split()
            scored = []
            for entry in self._entries:
                _, _, key, description = entry
                key_l = key.lower()
                hay = f"{key_l} {description.lower()}"
                if not all(t in hay for t in terms):
                    continue
                if key_l == q:
                    score = -1000
                elif key_l.startswith(q):
                    score = -500
                elif q in key_l:
                    score = -100
                else:
                    score = 0
                scored.append((score, key_l, entry))
            scored.sort(key=lambda x: (x[0], x[1]))
            self._filtered = [e for _, _, e in scored]

        self._list.Clear()
        for tab_display, _tab_internal, key, _description in self._filtered:
            self._list.Append(f"{key}  —  {tab_display}")
        if self._filtered:
            self._list.SetSelection(0)
        count = len(self._filtered)
        self._status.SetLabel(f"{count} match{'es' if count != 1 else ''}")

    def _on_text(self, _event):
        self._populate_list(self._search.GetValue())

    def _move_selection(self, delta: int) -> None:
        count = self._list.GetCount()
        if count == 0:
            return
        sel = self._list.GetSelection()
        if sel == wx.NOT_FOUND:
            sel = 0
        new = max(0, min(count - 1, sel + delta))
        if new != sel:
            self._list.SetSelection(new)

    def _on_search_char_hook(self, event):
        key_code = event.GetKeyCode()
        if key_code == wx.WXK_DOWN:
            self._move_selection(1)
            return
        if key_code == wx.WXK_UP:
            self._move_selection(-1)
            return
        if key_code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_accept(event)
            return
        if key_code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        event.Skip()

    def _on_list_char_hook(self, event):
        key_code = event.GetKeyCode()
        if key_code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_accept(event)
            return
        if key_code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        event.Skip()

    def _on_accept(self, _event):
        sel = self._list.GetSelection()
        if sel == wx.NOT_FOUND or sel >= len(self._filtered):
            return
        _tab_display, tab_internal, key, _description = self._filtered[sel]
        self.result = (tab_internal, key)
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