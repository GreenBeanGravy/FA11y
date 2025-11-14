"""
POI selector GUI for FA11y
Provides interface for selecting points of interest for navigation
"""
import os
import logging
import json
import re
import requests
import numpy as np
import threading
import time
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

logger = logging.getLogger(__name__)
speaker = Auto()

CONFIG_FILE = 'config.txt'
POI_TYPE = Union[Tuple[str, str, str], str]

_favorites_lock = threading.RLock()

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


class CoordinateSystem:
    """Handles coordinate transformation between world and screen coordinates"""
    def __init__(self, poi_file="pois.txt"):
        self.poi_file = poi_file
        self.REFERENCE_PAIRS = self._load_reference_pairs()
        self.transform_matrix = self._calculate_transformation_matrix()

    def _load_reference_pairs(self) -> dict:
        reference_pairs = {}
        try:
            with open(self.poi_file, 'r') as f:
                for line in f:
                    if not line.strip() or line.strip().startswith('#'):
                        continue
                    
                    parts = line.strip().split('|')
                    if len(parts) == 3:
                        name = parts[0].strip()
                        screen_x, screen_y = map(int, parts[1].strip().split(','))
                        world_x, world_y = map(float, parts[2].strip().split(','))
                        reference_pairs[(world_x, world_y)] = (screen_x, screen_y)
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Error loading POI data: {e}")
        
        return reference_pairs

    def _calculate_transformation_matrix(self) -> np.ndarray:
        if not self.REFERENCE_PAIRS:
            return np.array([[1, 0, 0], [0, 1, 0]])
            
        world_coords = np.array([(x, y) for x, y in self.REFERENCE_PAIRS.keys()])
        screen_coords = np.array([coord for coord in self.REFERENCE_PAIRS.values()])
        world_coords_homogeneous = np.column_stack([world_coords, np.ones(len(world_coords))])
        transform_matrix, _, _, _ = np.linalg.lstsq(world_coords_homogeneous, screen_coords, rcond=None)
        return transform_matrix

    def world_to_screen(self, world_x: float, world_y: float) -> Tuple[int, int]:
        world_coord = np.array([world_x, world_y, 1])
        screen_coord = np.dot(world_coord, self.transform_matrix)
        return (int(round(screen_coord[0])), int(round(screen_coord[1])))


class MapData:
    """Map data container"""
    def __init__(self, name, pois):
        self.name = name
        self.pois = pois


class POIData:
    """POI data manager with background loading for instant GUI opening"""
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(POIData, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not POIData._initialized:
            self.main_pois = []
            self.landmarks = []
            self.maps = {}
            self.current_map = 'main'
            self.coordinate_system = None
            self._api_loaded = False
            self._loading_lock = threading.Lock()
            self._loading_thread = None
            
            # Immediately discover maps (fast)
            self._discover_available_maps()
            
            # Start background loading for API data (slow)
            self._start_background_loading()
            
            POIData._initialized = True
    
    def _start_background_loading(self):
        """Start loading API data in background thread"""
        if self._loading_thread is None or not self._loading_thread.is_alive():
            self._loading_thread = threading.Thread(
                target=self._background_load_api_data,
                daemon=True
            )
            self._loading_thread.start()
    
    def _background_load_api_data(self):
        """Load API data in background"""
        try:
            with self._loading_lock:
                if not self._api_loaded:
                    if self.coordinate_system is None:
                        self.coordinate_system = CoordinateSystem()
                    
                    if self.coordinate_system.REFERENCE_PAIRS:
                        self._fetch_and_process_pois()
                    else:
                        self._load_local_pois()
                    
                    self._api_loaded = True
        except Exception as e:
            logger.error(f"Error in background loading: {e}")
            self._load_local_pois()
            self._api_loaded = True
    
    def _discover_available_maps(self):
        """Discover available maps without loading their data"""
        self.maps["main"] = MapData("Main Map", [])
        
        maps_dir = "maps"
        if os.path.exists(maps_dir):
            for filename in os.listdir(maps_dir):
                if filename.startswith("map_") and filename.endswith("_pois.txt"):
                    map_name = filename[4:-9]
                    if map_name != "main":
                        display_name = map_name.replace('_', ' ')
                        self.maps[map_name] = MapData(
                            name=display_name.title(),
                            pois=[]
                        )
    
    def _load_map_pois(self, filename: str) -> List[Tuple[str, str, str]]:
        pois = []
        try:
            with open(filename, 'r') as f:
                for line in f.readlines():
                    name, x, y = line.strip().split(',')
                    pois.append((name.strip(), x.strip(), y.strip()))
        except Exception as e:
            print(f"Error loading POIs from {filename}: {e}")
        return pois
    
    def _ensure_api_data_loaded(self, timeout=0.1):
        """Return immediately - uses cached or loading data"""
        if self._api_loaded:
            return True
        
        # If loading thread is still running, don't wait
        if self._loading_thread and self._loading_thread.is_alive():
            return False
        
        # If thread finished but flag not set, trigger load
        if not self._api_loaded:
            self._start_background_loading()
        
        return self._api_loaded
    
    def _ensure_map_data_loaded(self, map_name: str):
        """Ensure specific map data is loaded"""
        if map_name == "main":
            self._ensure_api_data_loaded()
        elif map_name in self.maps and not self.maps[map_name].pois:
            maps_dir = "maps"
            filename = os.path.join(maps_dir, f"map_{map_name}_pois.txt")
            if os.path.exists(filename):
                self.maps[map_name].pois = self._load_map_pois(filename)
    
    def _fetch_and_process_pois(self) -> None:
        try:
            response = requests.get('https://fortnite-api.com/v1/map', params={'language': 'en'}, timeout=10)
            response.raise_for_status()
            
            self.api_data = response.json().get('data', {}).get('pois', [])

            self.main_pois = []
            self.landmarks = []

            for poi in self.api_data:
                name = poi['name']
                world_x = float(poi['location']['x'])
                world_y = float(poi['location']['y'])
                screen_x, screen_y = self.coordinate_system.world_to_screen(world_x, world_y)
                
                if re.match(r'Athena\.Location\.POI\.Generic\.(?:EE\.)?\d+', poi['id']):
                    self.main_pois.append((name, str(screen_x), str(screen_y)))
                elif re.match(r'Athena\.Location\.UnNamedPOI\.(Landmark|GasStation)\.\d+', poi['id']):
                    self.landmarks.append((name, str(screen_x), str(screen_y)))

            self.maps["main"].pois = self.main_pois

        except requests.RequestException as e:
            print(f"Error fetching POIs from API: {e}")
            self._load_local_pois()
    
    def _load_local_pois(self):
        try:
            with open('pois.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split('|')
                    if len(parts) == 3:
                        name = parts[0]
                        coords = parts[1].split(',')
                        if len(coords) == 2:
                            x, y = coords[0], coords[1]
                            self.main_pois.append((name, x, y))
            
            self.maps["main"].pois = self.main_pois
            
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Error loading main POIs from file: {e}")
    
    def get_current_map(self):
        try:
            config = read_config()
            return config.get('POI', 'current_map', fallback='main')
        except Exception as e:
            print(f"Error getting current map: {e}")
            return 'main'


@dataclass
class FavoritePOI:
    """Favorite POI data container"""
    name: str
    x: str
    y: str
    source_tab: str


class FavoritesManager:
    """Manages favorite POIs with thread-safe operations"""
    
    def __init__(self, filename: str = "FAVORITE_POIS.txt"):
        self.filename = filename
        self.favorites: List[FavoritePOI] = []
        self._load_lock = threading.RLock()
        self.load_favorites()

    def _safe_write_favorites(self, data: List[dict], max_retries: int = 3) -> bool:
        for attempt in range(max_retries):
            try:
                backup_file = f"{self.filename}.backup"
                if os.path.exists(self.filename):
                    try:
                        with open(self.filename, 'r') as f:
                            backup_content = f.read()
                        with open(backup_file, 'w') as f:
                            f.write(backup_content)
                    except Exception as e:
                        logger.warning(f"Could not create backup: {e}")
                
                with open(self.filename, 'w') as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                
                if os.path.exists(backup_file):
                    try:
                        os.remove(backup_file)
                    except:
                        pass
                        
                return True
                
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed to write favorites: {e}")
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))
                    backup_file = f"{self.filename}.backup"
                    if os.path.exists(backup_file):
                        try:
                            with open(backup_file, 'r') as f:
                                backup_content = f.read()
                            with open(self.filename, 'w') as f:
                                f.write(backup_content)
                        except:
                            pass
                else:
                    return False
        
        return False

    def load_favorites(self) -> None:
        with _favorites_lock:
            if os.path.exists(self.filename):
                try:
                    with open(self.filename, 'r') as f:
                        data = json.load(f)
                        self.favorites = [FavoritePOI(**poi) for poi in data]
                except json.JSONDecodeError:
                    logger.error("Error loading favorites file. Starting with empty favorites.")
                    self.favorites = []
                except Exception as e:
                    logger.error(f"Error loading favorites: {e}")
                    self.favorites = []
            else:
                self.favorites = []

    def save_favorites(self) -> bool:
        with _favorites_lock:
            try:
                data = [vars(poi) for poi in self.favorites]
                return self._safe_write_favorites(data)
            except Exception as e:
                logger.error(f"Error saving favorites: {e}")
                return False

    def toggle_favorite(self, poi: Tuple[str, str, str], source_tab: str) -> bool:
        with _favorites_lock:
            name, x, y = poi
            existing = next((f for f in self.favorites if f.name == name), None)
            
            if existing:
                self.favorites.remove(existing)
                success = self.save_favorites()
                if not success:
                    self.favorites.append(existing)
                    logger.error(f"Failed to save favorites after removing {name}")
                    return False
                return False
            else:
                new_fav = FavoritePOI(name=name, x=x, y=y, source_tab=source_tab)
                self.favorites.append(new_fav)
                success = self.save_favorites()
                if not success:
                    self.favorites.remove(new_fav)
                    logger.error(f"Failed to save favorites after adding {name}")
                    return False
                return True

    def is_favorite(self, poi_name: str) -> bool:
        with _favorites_lock:
            return any(f.name == poi_name for f in self.favorites)

    def get_favorites_as_tuples(self) -> List[Tuple[str, str, str]]:
        with _favorites_lock:
            return [(f.name, f.x, f.y) for f in self.favorites]

    def get_source_tab(self, poi_name: str) -> Optional[str]:
        with _favorites_lock:
            fav = next((f for f in self.favorites if f.name == poi_name), None)
            return fav.source_tab if fav else None
        
    def remove_all_favorites(self) -> bool:
        with _favorites_lock:
            old_favorites = self.favorites.copy()
            self.favorites = []
            success = self.save_favorites()
            if not success:
                self.favorites = old_favorites
                logger.error("Failed to save favorites after removing all")
                return False
            return True


class POIGUI(AccessibleDialog):
    """POI selector GUI with instant opening via deferred loading"""
    
    def __init__(self, parent, poi_data, config_file: str = CONFIG_FILE):
        super().__init__(parent, title="POI Selector", helpId="POISelector")
        
        self.poi_data = poi_data
        self.config_file = config_file
        
        # Quick config read
        config = read_config()
        self.current_map = config.get('POI', 'current_map', fallback='main')
        
        # Initialize managers (fast)
        self.favorites_manager = FavoritesManager()
        
        # Store config state
        self.original_config_state = {
            'selected_poi': config.get('POI', 'selected_poi', fallback='closest, 0, 0'),
            'current_map': config.get('POI', 'current_map', fallback='main')
        }
        
        self.config_modified = False
        self.current_category_index = 0
        self.categories = []
        self.current_buttons = []
        self.current_button_index = 0
        
        # Show dialog immediately
        self.setupDialog()
    
    def makeSettings(self, settingsSizer: BoxSizerHelper):
        """Create dialog structure immediately"""
        self.notebook = wx.Notebook(self)
        settingsSizer.addItem(self.notebook, flag=wx.EXPAND, proportion=1)
        
        # Create map tabs with minimal content
        self.create_initial_tabs()
        
        # Defer data population
        wx.CallAfter(self._deferredInit)
        
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.onPageChanged)
    
    def create_initial_tabs(self):
        """Create empty tab structure immediately"""
        for map_name, map_data in self.poi_data.maps.items():
            panel = scrolled.ScrolledPanel(self.notebook)
            panel.SetupScrolling(scroll_x=False, scroll_y=True)
            
            # Add loading indicator
            sizer = wx.BoxSizer(wx.VERTICAL)
            loading_text = wx.StaticText(panel, label="Loading POIs...")
            sizer.Add(loading_text, flag=wx.ALL, border=10)
            panel.SetSizer(sizer)
            
            self.notebook.AddPage(panel, map_data.name)
    
    def _deferredInit(self):
        """Load data and populate UI after dialog is visible"""
        ensure_window_focus_and_center_mouse(self)
        
        # Check if data is ready
        if not self.poi_data._api_loaded and self.current_map == 'main':
            # Show minimal UI first, schedule check for completion
            wx.CallLater(100, self._checkDataAndRefresh)
        else:
            # Data ready - populate normally
            self._populateTabs()
            self._finalizeFocus()
    
    def _checkDataAndRefresh(self):
        """Check if background loading completed"""
        if self.poi_data._api_loaded:
            # Data loaded - refresh tabs
            self._populateTabs()
            self._finalizeFocus()
        else:
            # Still loading - check again
            wx.CallLater(100, self._checkDataAndRefresh)
    
    def _populateTabs(self):
        """Populate all map tabs with actual content"""
        # Clear existing pages
        while self.notebook.GetPageCount() > 0:
            self.notebook.DeletePage(0)
        
        # Create populated tabs
        for map_name, map_data in self.poi_data.maps.items():
            # Ensure map data is loaded
            self.poi_data._ensure_map_data_loaded(map_name)
            
            panel = scrolled.ScrolledPanel(self.notebook)
            panel.SetupScrolling(scroll_x=False, scroll_y=True)
            
            self.notebook.AddPage(panel, map_data.name)
            
            # Populate this map's content
            self.populate_map_content(panel, map_name)
    
    def _finalizeFocus(self):
        """Set focus after everything is loaded"""
        map_names = list(self.poi_data.maps.keys())
        if self.current_map in map_names:
            map_index = map_names.index(self.current_map)
            self.notebook.SetSelection(map_index)
        
        self.update_current_buttons()
        if self.current_buttons:
            self.current_button_index = 0
            self.current_buttons[0].SetFocus()
    
    def postInit(self):
        """Minimal post-init - actual work done in _deferredInit"""
        pass
    
    def populate_map_content(self, panel, map_name):
        """Populate content for a specific map"""
        categories = self.get_categories_for_map(map_name)
        
        if map_name == self.current_map:
            self.categories = categories
        else:
            self.categories = categories
            self.current_category_index = 0
        
        if self.current_category_index >= len(categories):
            self.current_category_index = 0
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        if categories:
            current_category_name = categories[self.current_category_index][0]
            category_info = wx.StaticText(panel, label=f"Category: {current_category_name} (Press Tab to switch categories)")
            font = category_info.GetFont()
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            category_info.SetFont(font)
            main_sizer.Add(category_info, flag=wx.ALL, border=10)
            
            separator = wx.StaticLine(panel)
            main_sizer.Add(separator, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)
            
            category_name, pois = categories[self.current_category_index]
            
            if pois:
                for poi in pois:
                    button_text = poi[0] if isinstance(poi, tuple) else poi
                    
                    if category_name == "Game Objects" and button_text.startswith("Closest "):
                        button_text = button_text[8:]
                    
                    if isinstance(poi, tuple) and self.favorites_manager.is_favorite(poi[0]):
                        button_text = f"⭐ {button_text}"
                    
                    if isinstance(poi, tuple) and self.should_speak_position(poi):
                        position_desc = self.get_poi_position_description(poi)
                        button_text = f"{button_text} - {position_desc}"
                    
                    button = wx.Button(panel, label=button_text)
                    
                    button.category_name = category_name
                    button.poi_data = poi
                    button.is_placeholder = False
                    
                    button.Bind(wx.EVT_CHAR_HOOK, self.onButtonCharHook)
                    button.Bind(wx.EVT_BUTTON, lambda evt, p=poi: self.select_poi(p))
                    
                    main_sizer.Add(button, flag=wx.EXPAND | wx.ALL, border=2)
                    
            else:
                if category_name == "Favorites":
                    placeholder_text = "No favorites saved - Press F on any POI to add it"
                elif category_name == "Custom POIs":
                    placeholder_text = "No custom POIs created"
                elif category_name == "Dynamic Objects":
                    placeholder_text = "No dynamic objects available"
                elif category_name == "Game Objects":
                    placeholder_text = "No game objects available for this map"
                else:
                    placeholder_text = f"No items in {category_name}"
                
                placeholder_button = wx.Button(panel, label=placeholder_text)
                placeholder_button.category_name = category_name
                placeholder_button.poi_data = None
                placeholder_button.is_placeholder = True
                
                placeholder_button.Bind(wx.EVT_CHAR_HOOK, self.onButtonCharHook)
                placeholder_button.Bind(wx.EVT_BUTTON, self.onPlaceholderClick)
                
                main_sizer.Add(placeholder_button, flag=wx.EXPAND | wx.ALL, border=2)
        else:
            no_pois_text = wx.StaticText(panel, label="No POIs available for this map")
            main_sizer.Add(no_pois_text, flag=wx.ALL, border=10)
        
        panel.SetSizer(main_sizer)
    
    def get_categories_for_map(self, map_name):
        DYNAMIC_OBJECTS = self._get_dynamic_objects()
        
        SPECIAL_POIS = [("Safe Zone", "0", "0"), ("Closest", "0", "0")]
        CLOSEST_LANDMARK = ("Closest Landmark", "0", "0")
        
        custom_pois = load_custom_pois(map_name)
        
        game_objects_map = game_object_manager.get_game_objects_for_map(map_name)
        available_types = sorted(game_objects_map.keys())
        closest_by_type = [(f"Closest {t}", "0", "0") for t in available_types]
        
        if map_name == "main":
            categories = [
                ("Main POIs", SPECIAL_POIS + sorted(self.poi_data.main_pois, key=self.poi_sort_key)),
                ("Landmarks", [CLOSEST_LANDMARK] + sorted(self.poi_data.landmarks, key=self.poi_sort_key)),
                ("Game Objects", closest_by_type),
                ("Dynamic Objects", DYNAMIC_OBJECTS),
                ("Custom POIs", sorted(custom_pois, key=self.poi_sort_key)),
                ("Favorites", self.favorites_manager.get_favorites_as_tuples())
            ]
        else:
            categories = [
                (f"{self.poi_data.maps[map_name].name} POIs", SPECIAL_POIS + sorted(self.poi_data.maps[map_name].pois, key=self.poi_sort_key)),
                ("Game Objects", closest_by_type),
                ("Dynamic Objects", DYNAMIC_OBJECTS),
                ("Custom POIs", sorted(custom_pois, key=self.poi_sort_key)),
                ("Favorites", self.favorites_manager.get_favorites_as_tuples())
            ]
        
        return categories
    
    def _get_dynamic_objects(self) -> List[Tuple[str, str, str]]:
        dynamic_objects = []
        icons_folder = 'icons'
        
        if os.path.exists(icons_folder):
            try:
                for filename in os.listdir(icons_folder):
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                        object_name = os.path.splitext(filename)[0]
                        display_name = object_name.replace('_', ' ').title()
                        dynamic_objects.append((display_name, "0", "0"))
            except Exception as e:
                print(f"Error loading dynamic objects: {e}")
        
        return sorted(dynamic_objects, key=lambda x: x[0])
    
    def update_current_buttons(self):
        self.current_buttons = []
        current_page = self.notebook.GetSelection()
        if current_page >= 0:
            page = self.notebook.GetPage(current_page)
            self.current_buttons = self.find_buttons_in_widget(page)
    
    def find_buttons_in_widget(self, widget):
        buttons = []
        for child in widget.GetChildren():
            if isinstance(child, wx.Button):
                buttons.append(child)
            else:
                buttons.extend(self.find_buttons_in_widget(child))
        return buttons
    
    def get_poi_from_button(self, button):
        if hasattr(button, 'poi_data'):
            return button.poi_data
        return None
    
    def onButtonCharHook(self, event):
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_TAB and not event.ControlDown():
            self.switch_category(not event.ShiftDown())
            return
        
        elif key_code == wx.WXK_TAB and event.ControlDown():
            self.switch_map(event.ShiftDown())
            return
        
        elif key_code == wx.WXK_UP:
            self.navigate_buttons(-1)
            return
        elif key_code == wx.WXK_DOWN:
            self.navigate_buttons(1)
            return
        elif key_code == wx.WXK_LEFT:
            self.navigate_buttons(-1)
            return
        elif key_code == wx.WXK_RIGHT:
            self.navigate_buttons(1)
            return
        
        event.Skip()
    
    def navigate_buttons(self, direction):
        if not self.current_buttons:
            return
        
        self.current_button_index = (self.current_button_index + direction) % len(self.current_buttons)
        self.current_buttons[self.current_button_index].SetFocus()
    
    def onPlaceholderClick(self, event):
        button = event.GetEventObject()
        if hasattr(button, 'category_name'):
            if button.category_name == "Favorites":
                speaker.speak("No favorites saved. Navigate to any POI and press F to add it to favorites.")
            elif button.category_name == "Custom POIs":
                speaker.speak("No custom POIs created. You can create custom POIs through the main application.")
            elif button.category_name == "Dynamic Objects":
                speaker.speak("No dynamic objects available. Add icon files to the icons folder to create dynamic objects.")
            elif button.category_name == "Game Objects":
                speaker.speak("No game objects available for this map.")
            else:
                speaker.speak(f"No items available in {button.category_name}")
    
    def switch_category(self, forward=True):
        if not self.categories:
            return
        
        if forward:
            new_index = (self.current_category_index + 1) % len(self.categories)
        else:
            new_index = (self.current_category_index - 1) % len(self.categories)
        
        self.current_category_index = new_index
        
        current_page = self.notebook.GetSelection()
        page = self.notebook.GetPage(current_page)
        page.DestroyChildren()
        self.populate_map_content(page, self.current_map)
        
        self.update_current_buttons()
        if self.current_buttons:
            self.current_button_index = 0
            self.current_buttons[0].SetFocus()
        
        category_name = self.categories[new_index][0]
        speaker.speak(category_name)
    
    def switch_map(self, backward=False):
        maps = list(self.poi_data.maps.keys())
        current_idx = maps.index(self.current_map)
        next_idx = (current_idx + (-1 if backward else 1)) % len(maps)
        new_map = maps[next_idx]
        
        self.current_map = new_map
        
        self.notebook.SetSelection(next_idx)
        
        self.categories = self.get_categories_for_map(new_map)
        self.current_category_index = 0
        
        self.update_current_buttons()
        if self.current_buttons:
            self.current_button_index = 0
            self.current_buttons[0].SetFocus()
        
        speaker.speak(f"Switched to {self.poi_data.maps[new_map].name}")
    
    def should_speak_position(self, poi: Tuple[str, str, str]) -> bool:
        SPECIAL_POIS = [("Safe Zone", "0", "0"), ("Closest", "0", "0")]
        CLOSEST_LANDMARK = ("Closest Landmark", "0", "0")
        
        if poi in SPECIAL_POIS or poi == CLOSEST_LANDMARK:
            return False
            
        if isinstance(poi, tuple) and isinstance(poi[0], str) and poi[0].lower().startswith('closest '):
            return False
        
        dynamic_objects = self._get_dynamic_objects()
        if poi in dynamic_objects:
            return False
            
        return True
    
    def onPageChanged(self, event):
        page_index = event.GetSelection()
        
        if page_index < len(self.poi_data.maps):
            maps = list(self.poi_data.maps.keys())
            new_map = maps[page_index]
            
            if new_map != self.current_map:
                self.current_map = new_map
                
                self.categories = self.get_categories_for_map(new_map)
                self.current_category_index = 0
                
                self.update_current_buttons()
                if self.current_buttons:
                    self.current_button_index = 0
                
                map_name = self.poi_data.maps[new_map].name
                speaker.speak(map_name)
        
        event.Skip()
    
    def onKeyEvent(self, event):
        key_code = event.GetKeyCode()
        
        if key_code == ord('F') or key_code == ord('f'):
            self.handle_favorite_key()
            return
        
        elif key_code == ord('R') or key_code == ord('r'):
            self.handle_remove_all_favorites()
            return
        
        elif key_code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        
        event.Skip()
    
    def handle_favorite_key(self):
        try:
            focused = self.FindFocus()
            if isinstance(focused, wx.Button):
                button_text = focused.GetLabel().replace('⭐ ', '')
                poi = self.get_poi_from_button(focused)
                
                if poi and isinstance(poi, tuple) and len(poi) >= 3:
                    button_position = self.current_button_index if hasattr(self, 'current_button_index') else 0
                    
                    source_category = getattr(focused, 'category_name', 'Unknown')
                    
                    is_added = self.favorites_manager.toggle_favorite(poi, source_category)
                    
                    if is_added is not None:
                        if is_added:
                            focused.SetLabel(f"⭐ {button_text}")
                        else:
                            focused.SetLabel(button_text)
                        
                        focused.SetFocus()
                        
                        action = "added to" if is_added else "removed from"
                        speaker.speak(f"{button_text} {action} favorites")
                    else:
                        speaker.speak(f"Failed to update favorites for {button_text}")
                        
        except Exception as e:
            logger.error(f"Error handling favorite key: {e}")
            speaker.speak("Error updating favorites")
    
    def handle_remove_all_favorites(self):
        try:
            focused = self.FindFocus()
            if isinstance(focused, wx.Button) and hasattr(focused, 'category_name'):
                if focused.category_name == "Favorites":
                    result = messageBox(
                        "Are you sure you want to remove all favorites?",
                        "Remove All Favorites",
                        wx.YES_NO | wx.ICON_QUESTION,
                        self
                    )
                    
                    if result == wx.YES:
                        success = self.favorites_manager.remove_all_favorites()
                        
                        if success:
                            current_page = self.notebook.GetSelection()
                            page = self.notebook.GetPage(current_page)
                            page.DestroyChildren()
                            self.populate_map_content(page, self.current_map)
                            
                            self.update_current_buttons()
                            
                            speaker.speak("All favorites removed")
                        else:
                            speaker.speak("Failed to remove all favorites")
                    else:
                        speaker.speak("Operation cancelled")
                        
        except Exception as e:
            logger.error(f"Error in handle_remove_all_favorites: {e}")
            speaker.speak("Error removing favorites")
    
    def select_poi(self, poi):
        try:
            poi_name = poi[0] if isinstance(poi, tuple) else poi
            
            if poi_name.lower() in ["closest", "safe zone", "closest landmark"]:
                special_poi_map = {
                    "closest": "Closest",
                    "closest landmark": "Closest Landmark",
                    "safe zone": "Safe Zone",
                }
                actual_name = special_poi_map.get(poi_name.lower(), poi_name)
                
                success = self.safe_update_config(actual_name, "0", "0")
                if success:
                    self.EndModal(wx.ID_OK)
                return
            
            source_tab = self.favorites_manager.get_source_tab(poi_name)
            if source_tab:
                for category_name, pois in self.categories:
                    if category_name == source_tab:
                        for original_poi in pois:
                            if isinstance(original_poi, tuple) and original_poi[0] == poi_name:
                                success = self.safe_update_config_from_poi_data(poi_name)
                                if success:
                                    self.EndModal(wx.ID_OK)
                                return
            else:
                success = self.safe_update_config_from_poi_data(poi_name)
                if success:
                    self.EndModal(wx.ID_OK)
                    
        except Exception as e:
            logger.error(f"Error in POI selection: {e}")
            speaker.speak("Error selecting POI")
    
    def safe_update_config(self, poi_name: str, x: str, y: str) -> bool:
        try:
            config_adapter = Config()
            config_adapter.set_poi(poi_name, x, y)
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
    
    def safe_update_config_from_poi_data(self, selected_poi_name: str) -> bool:
        try:
            logger.info(f"Updating configuration for POI: {selected_poi_name}")
            
            current_map = self.current_map
            
            if selected_poi_name.lower().startswith('closest '):
                return self.safe_update_config(selected_poi_name, "0", "0")
            
            if current_map == "main":
                poi_list = self.poi_data.main_pois + self.poi_data.landmarks
            else:
                poi_list = self.poi_data.maps[current_map].pois
                
            poi_entry = next(
                (poi for poi in poi_list if poi[0].lower() == selected_poi_name.lower()),
                None
            )
            
            if not poi_entry:
                custom_pois = load_custom_pois(current_map)
                poi_entry = next(
                    (poi for poi in custom_pois if poi[0].lower() == selected_poi_name.lower()),
                    None
                )
            
            if not poi_entry:
                game_objects_map = game_object_manager.get_game_objects_for_map(current_map)
                for obj_type in game_objects_map:
                    poi_entry = next(
                        (poi for poi in game_objects_map[obj_type] 
                         if poi[0].lower() == selected_poi_name.lower()),
                        None
                    )
                    if poi_entry:
                        break
            
            if not poi_entry:
                dynamic_objects = self._get_dynamic_objects()
                poi_entry = next(
                    (poi for poi in dynamic_objects 
                     if poi[0].lower() == selected_poi_name.lower()),
                    None
                )
            
            if poi_entry:
                return self.safe_update_config(poi_entry[0], poi_entry[1], poi_entry[2])
            else:
                logger.warning(f"Could not find POI entry for: {selected_poi_name}")
                return self.safe_update_config(selected_poi_name, "0", "0")
                
        except Exception as e:
            logger.error(f"Error updating configuration: {e}")
            return False
    
    def poi_sort_key(self, poi: Tuple[str, str, str]) -> Tuple[int, int, int, int]:
        name, x, y = poi
        try:
            x = int(float(x)) - ROI_START_ORIG[0]
            y = int(float(y)) - ROI_START_ORIG[1]
            width, height = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]
            
            quadrant = get_quadrant(x, y, width, height)
            position = get_position_in_quadrant(x, y, width // 2, height // 2)
            
            position_values = {
                "top-left": 0, "top": 1, "top-right": 2,
                "left": 3, "center": 4, "right": 5,
                "bottom-left": 6, "bottom": 7, "bottom-right": 8
            }
            
            return (quadrant, position_values.get(position, 9), y, x)
        except (ValueError, TypeError):
            return (9, 9, 9, 9)
    
    def get_poi_position_description(self, poi: Tuple[str, str, str]) -> str:
        try:
            name, x, y = poi
            x = int(float(x)) - ROI_START_ORIG[0]
            y = int(float(y)) - ROI_START_ORIG[1]
            width, height = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]
            
            quadrant = get_quadrant(x, y, width, height)
            position = get_position_in_quadrant(x, y, width // 2, height // 2)
            
            quadrant_names = ["top-left", "top-right", "bottom-left", "bottom-right"]
            return f"in the {position} of the {quadrant_names[quadrant]} quadrant"
        except (ValueError, TypeError):
            return "position unknown"


def launch_poi_selector(poi_data=None) -> None:
    try:
        app = wx.GetApp()
        if app is None:
            app = wx.App(False)
        
        if poi_data is None:
            poi_data = POIData()
        
        dlg = POIGUI(None, poi_data)
        
        ensure_window_focus_and_center_mouse(dlg)
        
        result = dlg.ShowModal()
        dlg.Destroy()
        
    except Exception as e:
        logger.error(f"Error launching POI selector GUI: {e}")
        error = DisplayableError(
            f"Error launching POI selector GUI: {str(e)}",
            "Application Error"
        )
        error.displayError()