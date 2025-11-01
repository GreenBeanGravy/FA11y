"""
Visited Objects GUI for FA11y
Provides interface for viewing visited objects and searching objects by ID
"""
import os
import logging
import json
import re
import threading
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Union, Set, Any, Callable

import wx
import wx.lib.scrolledpanel as scrolled
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import (
    AccessibleDialog, BoxSizerHelper, ButtonHelper, 
    messageBox, force_focus_window, ensure_window_focus_and_center_mouse,
    BORDER_FOR_DIALOGS
)
from lib.utilities.utilities import read_config, Config, clear_config_cache, save_config, calculate_distance
from lib.detection.player_position import ROI_START_ORIG, ROI_END_ORIG, get_quadrant, get_position_in_quadrant
from lib.managers.custom_poi_manager import load_custom_pois
from lib.managers.game_object_manager import game_object_manager
from lib.detection.match_tracker import match_tracker

logger = logging.getLogger(__name__)
speaker = Auto()

CONFIG_FILE = 'config.txt'
OBJECT_TYPE = Union[Tuple[str, str, str, str], str]

_objects_lock = threading.RLock()

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


class ObjectData:
    """Object data manager for visited objects with ID support"""
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ObjectData, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not ObjectData._initialized:
            self.visited_objects = []
            self.all_objects = []
            self.current_map = 'main'
            self.last_match_id = None
            ObjectData._initialized = True
    
    def _get_spatial_id_for_object(self, obj_name: str, obj_type: str, coordinates: Tuple[float, float], 
                                   current_map: str) -> str:
        try:
            all_objects_of_type = game_object_manager.get_objects_of_type(current_map, obj_type)
            
            if not all_objects_of_type:
                return "1"
            
            for i, (name, x_str, y_str) in enumerate(all_objects_of_type, 1):
                try:
                    obj_x, obj_y = float(x_str), float(y_str)
                    if (abs(obj_x - coordinates[0]) < 5 and abs(obj_y - coordinates[1]) < 5):
                        return str(i)
                except (ValueError, TypeError):
                    continue
            
            return "1"
            
        except Exception as e:
            logger.error(f"Error getting spatial ID for object: {e}")
            return "1"
    
    def _generate_object_with_id(self, obj_name: str, obj_type: str, x: str, y: str, current_map: str) -> Tuple[str, str, str, str]:
        try:
            coordinates = (float(x), float(y))
            spatial_id = self._get_spatial_id_for_object(obj_name, obj_type, coordinates, current_map)
            return (obj_name, x, y, spatial_id)
        except (ValueError, TypeError) as e:
            logger.error(f"Error generating object with ID: {e}")
            return (obj_name, x, y, "1")
    
    def _load_visited_objects(self, current_map: str) -> List[Tuple[str, str, str, str]]:
        objects = []
        try:
            stats = match_tracker.get_current_match_stats()
            if stats and stats.get('visited_object_types'):
                for obj_type in stats['visited_object_types']:
                    visited_objects = match_tracker.get_visited_objects_of_type(obj_type)
                    
                    for visited_obj in visited_objects:
                        obj_with_id = self._generate_object_with_id(
                            visited_obj.name, 
                            obj_type,
                            str(int(visited_obj.coordinates[0])), 
                            str(int(visited_obj.coordinates[1])),
                            current_map
                        )
                        objects.append(obj_with_id)
        except Exception as e:
            logger.error(f"Error loading visited objects: {e}")
        return objects
    
    def _load_all_objects(self, current_map: str) -> List[Tuple[str, str, str, str]]:
        objects = []
        try:
            game_objects = game_object_manager.get_game_objects_for_map(current_map)
            
            if game_objects:
                sorted_types = sorted(game_objects.keys())
                
                for obj_type in sorted_types:
                    object_list = game_objects[obj_type]
                    for i, (obj_name, x, y) in enumerate(object_list, 1):
                        obj_id = str(i)
                        objects.append((obj_name, str(int(float(x))), str(int(float(y))), obj_id))
        except Exception as e:
            logger.error(f"Error loading all objects: {e}")
        return objects
    
    def get_current_map(self):
        try:
            config = read_config()
            return config.get('POI', 'current_map', fallback='main')
        except Exception as e:
            logger.error(f"Error getting current map: {e}")
            return 'main'
    
    def should_invalidate_cache(self) -> bool:
        try:
            stats = match_tracker.get_current_match_stats()
            if not stats:
                return False
            
            current_match_id = stats.get('match_id')
            if current_match_id != self.last_match_id:
                self.last_match_id = current_match_id
                logger.info(f"Match change detected: {self.last_match_id} -> {current_match_id}")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error checking match change: {e}")
            return False
    
    def clear_cache(self):
        with _objects_lock:
            self.visited_objects = []
            self.all_objects = []
            self.last_match_id = None
            logger.info("Visited objects cache cleared")


class VisitedObjectsGUI(AccessibleDialog):
    """Visited objects GUI with instant opening via deferred loading"""
    
    def __init__(self, parent):
        super().__init__(parent, title="Visited Objects Manager", helpId="VisitedObjectsManager")
        
        self.object_data = ObjectData()
        
        config = read_config()
        self.current_map = config.get('POI', 'current_map', fallback='main')
        
        self.original_config_state = {
            'selected_poi': config.get('POI', 'selected_poi', fallback='closest, 0, 0'),
            'current_map': config.get('POI', 'current_map', fallback='main')
        }
        
        self.config_modified = False
        self.tab_control_widgets = {}
        self.search_results = []
        
        # Initialize caches as None - defer loading
        self.cached_visited = None
        self.cached_all = None
        self.cache_time = 0
        self.cache_timeout = 3.0
        
        # Store references for deferred population
        self.visited_panel = None
        self.search_panel = None
        
        self.setupDialog()
    
    def makeSettings(self, settingsSizer: BoxSizerHelper):
        """Create dialog structure immediately without data"""
        self.notebook = wx.Notebook(self)
        settingsSizer.addItem(self.notebook, flag=wx.EXPAND, proportion=1)
        
        # Create empty tabs
        self.visited_panel = scrolled.ScrolledPanel(self.notebook)
        self.visited_panel.SetupScrolling(scroll_x=False, scroll_y=True)
        self.notebook.AddPage(self.visited_panel, "Visited Objects")
        
        # Add loading indicator
        loading_sizer = wx.BoxSizer(wx.VERTICAL)
        loading_text = wx.StaticText(self.visited_panel, label="Loading visited objects...")
        loading_sizer.Add(loading_text, flag=wx.ALL, border=10)
        self.visited_panel.SetSizer(loading_sizer)
        
        self.search_panel = wx.Panel(self.notebook)
        self.notebook.AddPage(self.search_panel, "Search")
        
        # Defer data loading
        wx.CallAfter(self._loadAndPopulate)
        
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.onPageChanged)
    
    def _loadAndPopulate(self):
        """Load data and populate tabs after dialog is shown"""
        try:
            object_sets = self.get_object_sets()
            
            # Populate visited objects tab
            self.visited_panel.DestroyChildren()
            self.setup_visited_objects_tab(self.visited_panel, object_sets[0][1])
            
            # Populate search tab
            self.setup_search_tab(self.search_panel, object_sets[1][1])
            
            # Build tab control lists
            self.build_tab_control_lists()
            
        except Exception as e:
            logger.error(f"Error loading objects: {e}")
            speaker.speak("Error loading objects")
    
    def build_tab_control_lists(self):
        for i in range(self.notebook.GetPageCount()):
            page = self.notebook.GetPage(i)
            tab_name = self.notebook.GetPageText(i)
            self.tab_control_widgets[tab_name] = []
            self._collect_focusable_widgets(page, self.tab_control_widgets[tab_name])
    
    def _collect_focusable_widgets(self, parent, widget_list):
        for child in parent.GetChildren():
            if isinstance(child, (wx.Button, wx.TextCtrl, wx.CheckBox, wx.SpinCtrl, wx.Choice, wx.ComboBox, wx.ListCtrl)):
                widget_list.append(child)
            elif hasattr(child, 'GetChildren'):
                self._collect_focusable_widgets(child, widget_list)
    
    def get_current_tab_name(self):
        selection = self.notebook.GetSelection()
        if selection != wx.NOT_FOUND:
            return self.notebook.GetPageText(selection)
        return None
    
    def is_last_widget_in_tab(self, widget):
        current_tab = self.get_current_tab_name()
        if not current_tab or current_tab not in self.tab_control_widgets:
            return False
        
        widgets = self.tab_control_widgets[current_tab]
        return widgets and widget == widgets[-1]
    
    def handle_tab_navigation(self, event):
        try:
            if not event.ShiftDown():
                focused_widget = self.FindFocus()
                if focused_widget and self.is_last_widget_in_tab(focused_widget):
                    self.notebook.SetFocus()
                    return True
        except Exception as e:
            logger.error(f"Error in tab navigation: {e}")
        
        return False
    
    def postInit(self):
        wx.CallAfter(self._postInitFocus)
    
    def _postInitFocus(self):
        ensure_window_focus_and_center_mouse(self)
        self.setFocusToFirstControl()
    
    def onPageChanged(self, event):
        page_index = event.GetSelection()
        if page_index >= 0 and page_index < self.notebook.GetPageCount():
            tab_text = self.notebook.GetPageText(page_index)
            speaker.speak(f"{tab_text} tab")
        event.Skip()
    
    def setFocusToFirstControl(self):
        try:
            current_tab = self.get_current_tab_name()
            if current_tab and current_tab in self.tab_control_widgets:
                widgets = self.tab_control_widgets[current_tab]
                valid_widgets = [w for w in widgets if w and not w.IsBeingDeleted()]
                if valid_widgets:
                    valid_widgets[0].SetFocus()
                    return
            
            self.notebook.SetFocus()
        except Exception as e:
            logger.error(f"Error setting focus to first control: {e}")
            try:
                self.notebook.SetFocus()
            except:
                pass
    
    def onNoObjectsClick(self, event):
        speaker.speak("No visited objects available. Visit some objects in the game first, then return to this menu.")
    
    def onNoResultsClick(self, event):
        speaker.speak("No matching objects found. Try different search terms or check spelling.")
        if hasattr(self, 'search_entry'):
            self.search_entry.SetFocus()
    
    def onHelpClick(self, event):
        speaker.speak(f"Search help. Type in the search box above to find objects by name or ID. {len(self.all_objects)} total objects available.")
        if hasattr(self, 'search_entry'):
            self.search_entry.SetFocus()
    
    def get_object_sets(self) -> List[Tuple[str, List[OBJECT_TYPE]]]:
        current_time = time.time()
        
        try:
            if self.object_data.should_invalidate_cache():
                self.cached_visited = None
                self.cached_all = None
                self.cache_time = 0
                logger.info("Cache invalidated due to match change")
        except Exception as e:
            logger.error(f"Error checking cache invalidation: {e}")
        
        if (self.cached_visited is not None and self.cached_all is not None and 
            current_time - self.cache_time < self.cache_timeout):
            visited_objects = self.cached_visited
            all_objects = self.cached_all
        else:
            try:
                visited_objects = self.object_data._load_visited_objects(self.current_map)
            except Exception as e:
                logger.error(f"Error loading visited objects: {e}")
                visited_objects = []
            
            try:
                all_objects = self.object_data._load_all_objects(self.current_map)
            except Exception as e:
                logger.error(f"Error loading all objects: {e}")
                all_objects = []
            
            self.cached_visited = visited_objects
            self.cached_all = all_objects
            self.cache_time = current_time
            logger.info(f"Loaded {len(visited_objects)} visited objects and {len(all_objects)} total objects")
        
        return [
            ("Visited Objects", visited_objects),
            ("Search", all_objects)
        ]
    
    def setup_visited_objects_tab(self, panel, objects):
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        if not objects:
            no_objects_button = wx.Button(panel, label="No visited objects available")
            no_objects_button.SetToolTip("No objects have been visited in the current match")
            no_objects_button.Bind(wx.EVT_BUTTON, self.onNoObjectsClick)
            no_objects_button.Bind(wx.EVT_CHAR_HOOK, self.onButtonCharHook)
            no_objects_button.obj_data = None
            
            sizer.Add(no_objects_button, flag=wx.EXPAND | wx.ALL, border=10)
        else:
            header_text = wx.StaticText(panel, label=f"Visited objects from current match ({len(objects)} total):")
            font = header_text.GetFont()
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            header_text.SetFont(font)
            sizer.Add(header_text, flag=wx.ALL, border=10)
            
            for obj in objects:
                if len(obj) >= 4:
                    button_text = f"{obj[0]} (ID: {obj[3]})"
                    speech_text = self.get_object_speech_info(obj)
                else:
                    button_text = obj[0] if isinstance(obj, tuple) else str(obj)
                    speech_text = "No position information available"
                
                button = wx.Button(panel, label=button_text)
                button.Bind(wx.EVT_BUTTON, lambda evt, o=obj: self.select_object(o))
                button.speech_text = speech_text
                button.Bind(wx.EVT_CHAR_HOOK, self.onButtonCharHook)
                button.Bind(wx.EVT_SET_FOCUS, self.onButtonFocus)
                button.obj_data = obj
                
                sizer.Add(button, flag=wx.EXPAND | wx.ALL, border=2)
        
        panel.SetSizer(sizer)
    
    def setup_search_tab(self, panel, all_objects):
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        search_label = wx.StaticText(panel, label="Search by object name or ID:")
        sizer.Add(search_label, flag=wx.ALL, border=5)
        
        self.search_entry = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.search_entry.Bind(wx.EVT_TEXT, self.onSearchChange)
        self.search_entry.Bind(wx.EVT_TEXT_ENTER, self.onSearchEnter)
        self.search_entry.Bind(wx.EVT_CHAR_HOOK, self.onSearchCharHook)
        
        sizer.Add(self.search_entry, flag=wx.EXPAND | wx.ALL, border=5)
        
        self.search_results_panel = scrolled.ScrolledPanel(panel)
        self.search_results_panel.SetupScrolling(scroll_x=False, scroll_y=True)
        sizer.Add(self.search_results_panel, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)
        
        self.all_objects = all_objects
        
        panel.SetSizer(sizer)
        
        self.update_search_results([])
    
    def onSearchCharHook(self, event):
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_TAB and event.ControlDown():
            current_tab = self.notebook.GetSelection()
            tab_count = self.notebook.GetPageCount()
            if event.ShiftDown():
                new_tab = (current_tab - 1) % tab_count
            else:
                new_tab = (current_tab + 1) % tab_count
            self.notebook.SetSelection(new_tab)
            return
        
        elif key_code == wx.WXK_TAB and not event.ControlDown():
            if self.handle_tab_navigation(event):
                return
            event.Skip()
            return
        
        elif key_code in [wx.WXK_UP, wx.WXK_DOWN]:
            return
        
        event.Skip()
    
    def onButtonCharHook(self, event):
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_TAB and event.ControlDown():
            current_tab = self.notebook.GetSelection()
            tab_count = self.notebook.GetPageCount()
            if event.ShiftDown():
                new_tab = (current_tab - 1) % tab_count
            else:
                new_tab = (current_tab + 1) % tab_count
            self.notebook.SetSelection(new_tab)
            return
        
        elif key_code == wx.WXK_TAB and not event.ControlDown():
            if self.handle_tab_navigation(event):
                return
            event.Skip()
            return
        
        elif key_code in [wx.WXK_UP, wx.WXK_DOWN, wx.WXK_LEFT, wx.WXK_RIGHT]:
            return
        
        event.Skip()
    
    def onButtonFocus(self, event):
        button = event.GetEventObject()
        wx.CallAfter(self.announceDescription, button)
        event.Skip()
    
    def announceDescription(self, button):
        try:
            if hasattr(button, 'speech_text'):
                wx.CallLater(150, lambda: speaker.speak(button.speech_text))
        except Exception as e:
            logger.error(f"Error announcing description: {e}")
    
    def get_object_speech_info(self, obj: Tuple[str, str, str, str]) -> str:
        try:
            obj_name, x_str, y_str, obj_id = obj
            coordinates = (float(x_str), float(y_str))
            
            try:
                from lib.guis.poi_selector_gui import POIData
                poi_data = POIData()
                
                if self.current_map == 'main':
                    poi_data._ensure_api_data_loaded()
                    pois = poi_data.main_pois
                elif self.current_map in poi_data.maps:
                    poi_data._ensure_map_data_loaded(self.current_map)
                    pois = poi_data.maps[self.current_map].pois
                else:
                    pois = []
            except Exception as e:
                logger.debug(f"Could not load POI data: {e}")
                pois = []
            
            if not pois:
                return f"{obj_id}, coordinates {coordinates[0]:.0f}, {coordinates[1]:.0f}"
            
            closest_poi = None
            min_distance = float('inf')
            closest_poi_coords = None
            
            for poi_name, poi_x_str, poi_y_str in pois:
                try:
                    poi_coords = (float(poi_x_str), float(poi_y_str))
                    distance = calculate_distance(coordinates, poi_coords)
                    
                    if distance < min_distance:
                        min_distance = distance
                        closest_poi = poi_name
                        closest_poi_coords = poi_coords
                        
                except (ValueError, TypeError):
                    continue
            
            if closest_poi and min_distance < 1000:
                poi_x, poi_y = closest_poi_coords
                dx = coordinates[0] - poi_x
                dy = coordinates[1] - poi_y
                
                angle = np.arctan2(dy, dx) * 180 / np.pi
                angle = (angle + 360) % 360
                
                if angle < 22.5 or angle >= 337.5:
                    direction = "east"
                elif angle < 67.5:
                    direction = "southeast"
                elif angle < 112.5:
                    direction = "south"
                elif angle < 157.5:
                    direction = "southwest"
                elif angle < 202.5:
                    direction = "west"
                elif angle < 247.5:
                    direction = "northwest"
                elif angle < 292.5:
                    direction = "north"
                else:
                    direction = "northeast"
                
                return f"{min_distance:.0f} meters {direction} of {closest_poi}"
            else:
                return f"coordinates {coordinates[0]:.0f}, {coordinates[1]:.0f}"
                
        except Exception as e:
            logger.error(f"Error getting object speech info: {e}")
            return f"{obj[3] if len(obj) > 3 else 'Unknown'}"
    
    def onSearchChange(self, event):
        search_term = self.search_entry.GetValue().lower().strip()
        
        if not search_term:
            self.update_search_results([])
            return
        
        matching_objects = []
        for obj in self.all_objects:
            if len(obj) >= 4:
                obj_name, x, y, obj_id = obj
                
                search_targets = [
                    f"{obj_name}{obj_id}".lower(),
                    f"{obj_name} {obj_id}".lower(),
                    obj_id.lower(),
                    obj_name.lower(),
                ]
                
                if any(search_term in target for target in search_targets):
                    matching_objects.append(obj)
        
        self.search_results = matching_objects[:10]
        self.update_search_results(self.search_results)
    
    def onSearchEnter(self, event):
        self.onSearchChange(event)
    
    def update_search_results(self, results):
        self.search_results_panel.DestroyChildren()
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        if not results:
            if self.search_entry.GetValue().strip():
                no_results_text = wx.StaticText(self.search_results_panel, label="No matching objects found")
                sizer.Add(no_results_text, flag=wx.ALL, border=10)
            else:
                help_text = wx.StaticText(self.search_results_panel, 
                    label=f"Enter search terms above to find objects (Total: {len(self.all_objects)})")
                sizer.Add(help_text, flag=wx.ALL, border=10)
        else:
            results_info = wx.StaticText(self.search_results_panel, 
                label=f"Showing {len(results)} result{'s' if len(results) != 1 else ''}:")
            font = results_info.GetFont()
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            results_info.SetFont(font)
            sizer.Add(results_info, flag=wx.ALL, border=5)
            
            for obj in results:
                button_text = f"{obj[0]} (ID: {obj[3]})"
                speech_text = self.get_object_speech_info(obj)
                
                button = wx.Button(self.search_results_panel, label=button_text)
                button.Bind(wx.EVT_BUTTON, lambda evt, o=obj: self.select_object(o))
                button.speech_text = speech_text
                button.obj_data = obj
                
                button.Bind(wx.EVT_CHAR_HOOK, self.onButtonCharHook)
                button.Bind(wx.EVT_SET_FOCUS, self.onButtonFocus)
                
                sizer.Add(button, flag=wx.EXPAND | wx.ALL, border=2)
        
        self.search_results_panel.SetSizer(sizer)
        self.search_results_panel.FitInside()
        
        self.build_tab_control_lists()
    
    def onKeyEvent(self, event):
        key_code = event.GetKeyCode()
        focused = self.FindFocus()
        
        if key_code == wx.WXK_DELETE:
            if self.notebook.GetSelection() == 0:
                if isinstance(focused, wx.Button) and hasattr(focused, 'obj_data'):
                    self.unmark_visited_object(focused.obj_data)
            return
        
        if key_code == wx.WXK_TAB:
            if self.handle_tab_navigation(event):
                return
        
        if key_code == wx.WXK_ESCAPE:
            if (self.notebook.GetSelection() == 1 and 
                hasattr(self, 'search_entry') and 
                self.search_entry.GetValue().strip()):
                self.search_entry.SetValue("")
                self.search_entry.SetFocus()
            else:
                self.EndModal(wx.ID_CANCEL)
            return
        
        event.Skip()
    
    def select_object(self, obj: Union[Tuple[str, str, str, str], str]):
        try:
            if isinstance(obj, tuple) and len(obj) >= 4:
                obj_name, x, y, obj_id = obj
                poi_name = f"{obj_name}{obj_id}"
                success = self.safe_update_config(poi_name, x, y)
                if success:
                    self.EndModal(wx.ID_OK)
            else:
                speaker.speak("Invalid object data")
                    
        except Exception as e:
            logger.error(f"Error in object selection: {e}")
            speaker.speak("Error selecting object")
    
    def safe_update_config(self, obj_name: str, x: str, y: str) -> bool:
        try:
            config_adapter = Config()
            config_adapter.set_poi(obj_name, x, y)
            config_adapter.set_current_map(self.current_map)
            
            success = config_adapter.save()
            if success:
                self.config_modified = True
                return True
            else:
                logger.error("Failed to save config")
                return False
                
        except Exception as e:
            logger.error(f"Error updating config: {e}")
            return False
    
    def unmark_visited_object(self, obj_data):
        try:
            if len(obj_data) >= 4:
                obj_name, x, y, obj_id = obj_data
            else:
                obj_name = obj_data[0] if isinstance(obj_data, tuple) else str(obj_data)
                obj_id = "Unknown"
            
            result = messageBox(
                f"Remove '{obj_name}' (ID: {obj_id}) from visited objects?",
                "Confirm Removal",
                wx.YES_NO | wx.ICON_QUESTION,
                self
            )
            
            if result != wx.YES:
                return
            
            removed = False
            try:
                stats = match_tracker.get_current_match_stats()
                if stats and stats.get('visited_object_types'):
                    for obj_type in stats['visited_object_types']:
                        if obj_type in match_tracker.current_match.visited_objects:
                            visited_list = match_tracker.current_match.visited_objects[obj_type]
                            
                            for i, visited_obj in enumerate(visited_list):
                                if (visited_obj.name == obj_name and
                                    abs(visited_obj.coordinates[0] - float(x)) < 5 and
                                    abs(visited_obj.coordinates[1] - float(y)) < 5):
                                    
                                    visited_list.pop(i)
                                    removed = True
                                    
                                    if not visited_list:
                                        del match_tracker.current_match.visited_objects[obj_type]
                                    
                                    break
                        
                        if removed:
                            break
            except Exception as e:
                logger.error(f"Error removing from match tracker: {e}")
            
            if removed:
                self.refresh_tabs()
                speaker.speak(f"Removed {obj_name} from visited objects")
            else:
                speaker.speak("Object not found in visited list")
            
        except Exception as e:
            logger.error(f"Error unmarking object: {e}")
            speaker.speak("Error removing object from visited list")
    
    def refresh_tabs(self):
        try:
            self.cached_visited = None
            self.cached_all = None
            self.cache_time = 0
            
            current_tab = self.notebook.GetSelection()
            focused_widget = self.FindFocus()
            focused_widget_type = type(focused_widget).__name__ if focused_widget else None
            
            try:
                object_sets = self.get_object_sets()
            except Exception as e:
                logger.error(f"Error getting object sets during refresh: {e}")
                return
            
            try:
                visited_page = self.notebook.GetPage(0)
                if visited_page and not visited_page.IsBeingDeleted():
                    visited_page.DestroyChildren()
                    self.setup_visited_objects_tab(visited_page, object_sets[0][1])
            except Exception as e:
                logger.error(f"Error refreshing visited objects tab: {e}")
            
            try:
                self.all_objects = object_sets[1][1]
            except Exception as e:
                logger.error(f"Error updating all objects: {e}")
            
            try:
                if hasattr(self, 'search_entry') and self.search_entry.GetValue().strip():
                    wx.CallAfter(lambda: self.onSearchChange(None))
            except Exception as e:
                logger.error(f"Error refreshing search: {e}")
            
            wx.CallAfter(self.build_tab_control_lists)
            
            try:
                if current_tab == 0:
                    wx.CallAfter(self.setFocusToFirstControl)
                else:
                    if hasattr(self, 'search_entry') and not self.search_entry.IsBeingDeleted():
                        wx.CallAfter(lambda: self.search_entry.SetFocus())
                    else:
                        wx.CallAfter(self.setFocusToFirstControl)
            except Exception as e:
                logger.error(f"Error restoring focus: {e}")
                wx.CallAfter(self.setFocusToFirstControl)
            
            wx.CallAfter(self.Layout)
            
        except Exception as e:
            logger.error(f"Error refreshing tabs: {e}")
            wx.CallAfter(self.build_tab_control_lists)


def launch_visited_objects_gui() -> None:
    try:
        config = read_config()
        current_map = config.get('POI', 'current_map', fallback='main')
        
        game_objects = game_object_manager.get_game_objects_for_map(current_map)
        if not game_objects:
            speaker.speak(f"No game objects available on {current_map} map")
            return
        
        app = wx.GetApp()
        if app is None:
            app = wx.App(False)
        
        dlg = VisitedObjectsGUI(None)
        
        ensure_window_focus_and_center_mouse(dlg)
        
        result = dlg.ShowModal()
        dlg.Destroy()
        
    except Exception as e:
        logger.error(f"Error launching visited objects GUI: {e}")
        error = DisplayableError(
            f"Error launching visited objects GUI: {str(e)}",
            "Application Error"
        )
        error.displayError()
        speaker.speak("Error opening visited objects manager")