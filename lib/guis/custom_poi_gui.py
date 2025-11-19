<<<<<<< HEAD
"""
Custom POI creation GUI for FA11y
Provides interface for creating custom points of interest
"""
import os
import logging
from typing import Optional, Tuple, Callable

import wx
import pyautogui
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import (
    AccessibleDialog, BoxSizerHelper, ButtonHelper, 
    messageBox, force_focus_window, ensure_window_focus_and_center_mouse,
    BORDER_FOR_DIALOGS
)
from lib.managers.poi_data_manager import POIData
from lib.utilities.utilities import read_config

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


class CustomPOIGUI(AccessibleDialog):
    """Custom POI creation GUI with instant opening"""
    
    def __init__(self, parent, use_ppi: bool = False, player_detector=None, current_map: str = "main"):
        super().__init__(parent, title="Create Custom POI", helpId="CustomPOICreator")
        
        self.use_ppi = use_ppi
        self.player_detector = player_detector
        self.current_map = current_map
        self.creation_successful = False
        
        # Get position quickly - this is the only potentially slow operation
        self.coordinates = self.get_current_position()
        if not self.coordinates:
            logger.error("Unable to determine player location for custom POI")
            error = DisplayableError(
                "Unable to determine player location for custom POI",
                "Position Error"
            )
            error.displayError(parent)
            return
            
        self.setupDialog()
    
    def get_current_position(self) -> Optional[Tuple[int, int]]:
        """Get current position using either PPI or regular icon detection"""
        try:
            if self.player_detector:
                return self.player_detector.get_player_position(self.use_ppi)
            else:
                try:
                    from lib.guis.coordinate_utils import get_current_coordinates
                    return get_current_coordinates()
                except ImportError:
                    logger.warning("No coordinate utilities available")
                    return None
        except Exception as e:
            logger.error(f"Error getting current position: {e}")
            return None
    
    def makeSettings(self, settingsSizer: BoxSizerHelper):
        """Create dialog content"""
        
        display_map = self.current_map.replace('_', ' ').title()
        current_map_text = wx.StaticText(self, label=f"Current Map: {display_map}")
        font = current_map_text.GetFont()
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        current_map_text.SetFont(font)
        settingsSizer.addItem(current_map_text)
        
        coord_text = f"Current Position: ({self.coordinates[0]}, {self.coordinates[1]})"
        self.coordinate_label = wx.StaticText(self, label=coord_text)
        settingsSizer.addItem(self.coordinate_label)
        
        settingsSizer.addItem(wx.StaticLine(self), flag=wx.EXPAND)
        
        self.poi_name_entry = settingsSizer.addLabeledControl(
            "POI Name:",
            wx.TextCtrl,
            style=wx.TE_PROCESS_ENTER
        )
        
        self.poi_name_entry.Bind(wx.EVT_CHAR_HOOK, self.onTextCharHook)
        self.poi_name_entry.Bind(wx.EVT_TEXT_ENTER, self.onSavePOI)
        
        instructions = wx.StaticText(self, 
            label="Enter a name for this POI. Use Enter to save, Escape to cancel, F5 to refresh position.")
        instructions.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_ITALIC, wx.FONTWEIGHT_NORMAL))
        settingsSizer.addItem(instructions)
        
        settingsSizer.addItem(wx.StaticLine(self), flag=wx.EXPAND)
        
        button_helper = ButtonHelper(wx.HORIZONTAL)
        
        refresh_button = button_helper.addButton(self, label="&Refresh Position")
        refresh_button.Bind(wx.EVT_BUTTON, self.onRefreshPosition)
        refresh_button.Bind(wx.EVT_CHAR_HOOK, self.onButtonCharHook)
        refresh_button.SetToolTip("Update current position coordinates (F5)")
        
        save_button = button_helper.addButton(self, label="&Save POI")
        save_button.Bind(wx.EVT_BUTTON, self.onSavePOI)
        save_button.Bind(wx.EVT_CHAR_HOOK, self.onButtonCharHook)
        save_button.SetToolTip("Save the custom POI with the entered name (Enter)")
        
        cancel_button = button_helper.addButton(self, label="&Cancel")
        cancel_button.Bind(wx.EVT_BUTTON, self.onCancel)
        cancel_button.Bind(wx.EVT_CHAR_HOOK, self.onButtonCharHook)
        cancel_button.SetToolTip("Cancel POI creation (Escape)")
        
        settingsSizer.addItem(button_helper)
        
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)
    
    def onTextCharHook(self, event):
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_TAB:
            event.Skip()
            return
        
        if key_code in [wx.WXK_UP, wx.WXK_DOWN]:
            return
        
        event.Skip()
    
    def onButtonCharHook(self, event):
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_TAB:
            event.Skip()
            return
        
        if key_code in [wx.WXK_UP, wx.WXK_DOWN, wx.WXK_LEFT, wx.WXK_RIGHT]:
            return
        
        event.Skip()
    
    def postInit(self):
        wx.CallAfter(self._postInitFocus)
    
    def _postInitFocus(self):
        ensure_window_focus_and_center_mouse(self)
        self.poi_name_entry.SetFocus()
    
    def onKeyEvent(self, event):
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_RETURN or key_code == wx.WXK_NUMPAD_ENTER:
            poi_name = self.poi_name_entry.GetValue().strip()
            if poi_name:
                self.onSavePOI(event)
            else:
                speaker.speak("Please enter a POI name first")
            return
        
        elif key_code == wx.WXK_ESCAPE:
            poi_name = self.poi_name_entry.GetValue().strip()
            if poi_name:
                result = messageBox(
                    "Save the POI before closing?",
                    "POI Name Entered",
                    wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
                    self
                )
                
                if result == wx.YES:
                    self.onSavePOI(event)
                elif result == wx.NO:
                    self.onCancel(event)
            else:
                self.onCancel(event)
            return
        
        elif key_code == wx.WXK_F5:
            self.onRefreshPosition(event)
            return
        
        event.Skip()
    
    def onRefreshPosition(self, event):
        try:
            original_coords = self.coordinates
            new_coords = self.get_current_position()
            
            if new_coords:
                self.coordinates = new_coords
                coord_text = f"Current Position: ({self.coordinates[0]}, {self.coordinates[1]})"
                self.coordinate_label.SetLabel(coord_text)
                
                if original_coords != new_coords:
                    speaker.speak(f"Position updated to {self.coordinates[0]}, {self.coordinates[1]}")
                else:
                    speaker.speak("Position unchanged")
                    
                self.Layout()
            else:
                speaker.speak("Unable to detect current position")
                logger.error("Failed to refresh position")
                
        except Exception as e:
            logger.error(f"Error refreshing position: {e}")
            speaker.speak("Error refreshing position")
    
    def onSavePOI(self, event):
        poi_name = self.poi_name_entry.GetValue().strip()
        
        if not poi_name:
            speaker.speak("Please enter a POI name")
            self.poi_name_entry.SetFocus()
            return
        
        if len(poi_name) < 2:
            speaker.speak("POI name must be at least 2 characters long")
            self.poi_name_entry.SetFocus()
            return
        
        invalid_chars = [',', '|', '\n', '\r', '\t']
        found_invalid = [char for char in invalid_chars if char in poi_name]
        if found_invalid:
            speaker.speak(f"POI name contains invalid characters: {', '.join(found_invalid)}. Please use only letters, numbers, spaces, and basic punctuation.")
            self.poi_name_entry.SetFocus()
            return
        
        if self.poi_name_exists(poi_name):
            result = messageBox(
                f"A POI named '{poi_name}' already exists on this map. Overwrite it?",
                "POI Already Exists",
                wx.YES_NO | wx.ICON_QUESTION,
                self
            )
            
            if result != wx.YES:
                self.poi_name_entry.SetFocus()
                return
        
        success = self.create_custom_poi(self.coordinates, poi_name, self.current_map)
        
        if success:
            self.creation_successful = True
            speaker.speak(f"Custom POI '{poi_name}' created successfully")
            self.EndModal(wx.ID_OK)
            wx.CallLater(500, self._return_focus_to_game)
        else:
            speaker.speak("Error saving custom POI")
            logger.error("Failed to save custom POI")
    
    def onCancel(self, event):
        self.creation_successful = False
        self.EndModal(wx.ID_CANCEL)
        wx.CallAfter(self._return_focus_to_game)
    
    def _return_focus_to_game(self):
        try:
            pyautogui.click()
        except Exception as e:
            logger.debug(f"Could not return focus to game: {e}")
    
    def poi_name_exists(self, poi_name: str) -> bool:
        try:
            if not os.path.exists('config/CUSTOM_POI.txt'):
                return False
                
            with open('config/CUSTOM_POI.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                        
                    parts = line.split(',')
                    if len(parts) >= 4:
                        existing_name = parts[0].strip()
                        existing_map = parts[3].strip()
                        
                        if (existing_name.lower() == poi_name.lower() and 
                            existing_map == self.current_map):
                            return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking POI existence: {e}")
            return False
    
    def create_custom_poi(self, coordinates: Tuple[int, int], name: str, map_name: str) -> bool:
        if not coordinates:
            logger.error("Could not determine current position for custom POI")
            return False
            
        x, y = coordinates
        
        try:
            poi_file_dir = os.path.dirname('config/CUSTOM_POI.txt')
            if poi_file_dir:
                os.makedirs(poi_file_dir, exist_ok=True)
            
            if os.path.exists('config/CUSTOM_POI.txt'):
                lines = []
                try:
                    with open('config/CUSTOM_POI.txt', 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                except Exception as e:
                    logger.error(f"Error reading existing POI file: {e}")
                    return False
                
                filtered_lines = []
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    parts = line.split(',')
                    if len(parts) >= 4:
                        existing_name = parts[0].strip()
                        existing_map = parts[3].strip()
                        
                        if not (existing_name.lower() == name.lower() and existing_map == map_name):
                            filtered_lines.append(line + '\n')
                    else:
                        filtered_lines.append(line + '\n')
                
                try:
                    with open('config/CUSTOM_POI.txt', 'w', encoding='utf-8') as f:
                        f.writelines(filtered_lines)
                except Exception as e:
                    logger.error(f"Error writing filtered POI file: {e}")
                    return False
            
            try:
                with open('config/CUSTOM_POI.txt', 'a', encoding='utf-8') as f:
                    f.write(f"{name},{x},{y},{map_name}\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as e:
                logger.error(f"Error appending new POI: {e}")
                return False
            
            logger.info(f"Created custom POI: {name} at {x},{y} for map {map_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving custom POI: {e}")
            return False


def launch_custom_poi_creator(use_ppi: bool = False, player_detector=None, current_map: str = "main") -> bool:
    try:
        coordinates = None
        
        if player_detector:
            try:
                coordinates = player_detector.get_player_position(use_ppi)
            except Exception as e:
                logger.error(f"Error using player detector: {e}")
        
        if not coordinates:
            try:
                from lib.guis.coordinate_utils import get_current_coordinates
                coordinates = get_current_coordinates()
            except ImportError:
                logger.error("No coordinate utilities available")
            except Exception as e:
                logger.error(f"Error using coordinate utilities: {e}")
        
        if not coordinates:
            logger.error("Unable to determine player location for custom POI")
            speaker.speak("Unable to determine player location for custom POI")
            return False
        
        app = wx.GetApp()
        if app is None:
            app = wx.App(False)
        
        dlg = CustomPOIGUI(None, use_ppi, player_detector, current_map)
        
        if dlg and hasattr(dlg, 'coordinates') and dlg.coordinates:
            ensure_window_focus_and_center_mouse(dlg)
            
            result = dlg.ShowModal()
            creation_successful = getattr(dlg, 'creation_successful', False)
            
            dlg.Destroy()
            
            return creation_successful
        else:
            if dlg:
                dlg.Destroy()
            return False
        
    except Exception as e:
        logger.error(f"Error launching custom POI GUI: {e}")
        error = DisplayableError(
            f"Error launching custom POI GUI: {str(e)}",
            "Application Error"
        )
        error.displayError()
        speaker.speak("Error opening custom POI creator")
=======
"""
Custom POI creation GUI for FA11y
Provides interface for creating custom points of interest
"""
import os
import logging
from typing import Optional, Tuple, Callable

import wx
import pyautogui
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import (
    AccessibleDialog, BoxSizerHelper, ButtonHelper, 
    messageBox, force_focus_window, ensure_window_focus_and_center_mouse,
    BORDER_FOR_DIALOGS
)
from lib.managers.poi_data_manager import POIData
from lib.utilities.utilities import read_config

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


class CustomPOIGUI(AccessibleDialog):
    """Custom POI creation GUI with instant opening"""
    
    def __init__(self, parent, use_ppi: bool = False, player_detector=None, current_map: str = "main"):
        super().__init__(parent, title="Create Custom POI", helpId="CustomPOICreator")
        
        self.use_ppi = use_ppi
        self.player_detector = player_detector
        self.current_map = current_map
        self.creation_successful = False
        
        # Get position quickly - this is the only potentially slow operation
        self.coordinates = self.get_current_position()
        if not self.coordinates:
            logger.error("Unable to determine player location for custom POI")
            error = DisplayableError(
                "Unable to determine player location for custom POI",
                "Position Error"
            )
            error.displayError(parent)
            return
            
        self.setupDialog()
    
    def get_current_position(self) -> Optional[Tuple[int, int]]:
        """Get current position using either PPI or regular icon detection"""
        try:
            if self.player_detector:
                return self.player_detector.get_player_position(self.use_ppi)
            else:
                try:
                    from lib.guis.coordinate_utils import get_current_coordinates
                    return get_current_coordinates()
                except ImportError:
                    logger.warning("No coordinate utilities available")
                    return None
        except Exception as e:
            logger.error(f"Error getting current position: {e}")
            return None
    
    def makeSettings(self, settingsSizer: BoxSizerHelper):
        """Create dialog content"""
        
        display_map = self.current_map.replace('_', ' ').title()
        current_map_text = wx.StaticText(self, label=f"Current Map: {display_map}")
        font = current_map_text.GetFont()
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        current_map_text.SetFont(font)
        settingsSizer.addItem(current_map_text)
        
        coord_text = f"Current Position: ({self.coordinates[0]}, {self.coordinates[1]})"
        self.coordinate_label = wx.StaticText(self, label=coord_text)
        settingsSizer.addItem(self.coordinate_label)
        
        settingsSizer.addItem(wx.StaticLine(self), flag=wx.EXPAND)
        
        self.poi_name_entry = settingsSizer.addLabeledControl(
            "POI Name:",
            wx.TextCtrl,
            style=wx.TE_PROCESS_ENTER
        )
        
        self.poi_name_entry.Bind(wx.EVT_CHAR_HOOK, self.onTextCharHook)
        self.poi_name_entry.Bind(wx.EVT_TEXT_ENTER, self.onSavePOI)
        
        instructions = wx.StaticText(self, 
            label="Enter a name for this POI. Use Enter to save, Escape to cancel, F5 to refresh position.")
        instructions.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_ITALIC, wx.FONTWEIGHT_NORMAL))
        settingsSizer.addItem(instructions)
        
        settingsSizer.addItem(wx.StaticLine(self), flag=wx.EXPAND)
        
        button_helper = ButtonHelper(wx.HORIZONTAL)
        
        refresh_button = button_helper.addButton(self, label="&Refresh Position")
        refresh_button.Bind(wx.EVT_BUTTON, self.onRefreshPosition)
        refresh_button.Bind(wx.EVT_CHAR_HOOK, self.onButtonCharHook)
        refresh_button.SetToolTip("Update current position coordinates (F5)")
        
        save_button = button_helper.addButton(self, label="&Save POI")
        save_button.Bind(wx.EVT_BUTTON, self.onSavePOI)
        save_button.Bind(wx.EVT_CHAR_HOOK, self.onButtonCharHook)
        save_button.SetToolTip("Save the custom POI with the entered name (Enter)")
        
        cancel_button = button_helper.addButton(self, label="&Cancel")
        cancel_button.Bind(wx.EVT_BUTTON, self.onCancel)
        cancel_button.Bind(wx.EVT_CHAR_HOOK, self.onButtonCharHook)
        cancel_button.SetToolTip("Cancel POI creation (Escape)")
        
        settingsSizer.addItem(button_helper)
        
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)
    
    def onTextCharHook(self, event):
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_TAB:
            event.Skip()
            return
        
        if key_code in [wx.WXK_UP, wx.WXK_DOWN]:
            return
        
        event.Skip()
    
    def onButtonCharHook(self, event):
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_TAB:
            event.Skip()
            return
        
        if key_code in [wx.WXK_UP, wx.WXK_DOWN, wx.WXK_LEFT, wx.WXK_RIGHT]:
            return
        
        event.Skip()
    
    def postInit(self):
        wx.CallAfter(self._postInitFocus)
    
    def _postInitFocus(self):
        ensure_window_focus_and_center_mouse(self)
        self.poi_name_entry.SetFocus()
    
    def onKeyEvent(self, event):
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_RETURN or key_code == wx.WXK_NUMPAD_ENTER:
            poi_name = self.poi_name_entry.GetValue().strip()
            if poi_name:
                self.onSavePOI(event)
            else:
                speaker.speak("Please enter a POI name first")
            return
        
        elif key_code == wx.WXK_ESCAPE:
            poi_name = self.poi_name_entry.GetValue().strip()
            if poi_name:
                result = messageBox(
                    "Save the POI before closing?",
                    "POI Name Entered",
                    wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
                    self
                )
                
                if result == wx.YES:
                    self.onSavePOI(event)
                elif result == wx.NO:
                    self.onCancel(event)
            else:
                self.onCancel(event)
            return
        
        elif key_code == wx.WXK_F5:
            self.onRefreshPosition(event)
            return
        
        event.Skip()
    
    def onRefreshPosition(self, event):
        try:
            original_coords = self.coordinates
            new_coords = self.get_current_position()
            
            if new_coords:
                self.coordinates = new_coords
                coord_text = f"Current Position: ({self.coordinates[0]}, {self.coordinates[1]})"
                self.coordinate_label.SetLabel(coord_text)
                
                if original_coords != new_coords:
                    speaker.speak(f"Position updated to {self.coordinates[0]}, {self.coordinates[1]}")
                else:
                    speaker.speak("Position unchanged")
                    
                self.Layout()
            else:
                speaker.speak("Unable to detect current position")
                logger.error("Failed to refresh position")
                
        except Exception as e:
            logger.error(f"Error refreshing position: {e}")
            speaker.speak("Error refreshing position")
    
    def onSavePOI(self, event):
        poi_name = self.poi_name_entry.GetValue().strip()
        
        if not poi_name:
            speaker.speak("Please enter a POI name")
            self.poi_name_entry.SetFocus()
            return
        
        if len(poi_name) < 2:
            speaker.speak("POI name must be at least 2 characters long")
            self.poi_name_entry.SetFocus()
            return
        
        invalid_chars = [',', '|', '\n', '\r', '\t']
        found_invalid = [char for char in invalid_chars if char in poi_name]
        if found_invalid:
            speaker.speak(f"POI name contains invalid characters: {', '.join(found_invalid)}. Please use only letters, numbers, spaces, and basic punctuation.")
            self.poi_name_entry.SetFocus()
            return
        
        if self.poi_name_exists(poi_name):
            result = messageBox(
                f"A POI named '{poi_name}' already exists on this map. Overwrite it?",
                "POI Already Exists",
                wx.YES_NO | wx.ICON_QUESTION,
                self
            )
            
            if result != wx.YES:
                self.poi_name_entry.SetFocus()
                return
        
        success = self.create_custom_poi(self.coordinates, poi_name, self.current_map)
        
        if success:
            self.creation_successful = True
            speaker.speak(f"Custom POI '{poi_name}' created successfully")
            self.EndModal(wx.ID_OK)
            wx.CallLater(500, self._return_focus_to_game)
        else:
            speaker.speak("Error saving custom POI")
            logger.error("Failed to save custom POI")
    
    def onCancel(self, event):
        self.creation_successful = False
        self.EndModal(wx.ID_CANCEL)
        wx.CallAfter(self._return_focus_to_game)
    
    def _return_focus_to_game(self):
        try:
            pyautogui.click()
        except Exception as e:
            logger.debug(f"Could not return focus to game: {e}")
    
    def poi_name_exists(self, poi_name: str) -> bool:
        try:
            if not os.path.exists('config/CUSTOM_POI.txt'):
                return False
                
            with open('config/CUSTOM_POI.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                        
                    parts = line.split(',')
                    if len(parts) >= 4:
                        existing_name = parts[0].strip()
                        existing_map = parts[3].strip()
                        
                        if (existing_name.lower() == poi_name.lower() and 
                            existing_map == self.current_map):
                            return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking POI existence: {e}")
            return False
    
    def create_custom_poi(self, coordinates: Tuple[int, int], name: str, map_name: str) -> bool:
        if not coordinates:
            logger.error("Could not determine current position for custom POI")
            return False
            
        x, y = coordinates
        
        try:
            poi_file_dir = os.path.dirname('config/CUSTOM_POI.txt')
            if poi_file_dir:
                os.makedirs(poi_file_dir, exist_ok=True)
            
            if os.path.exists('config/CUSTOM_POI.txt'):
                lines = []
                try:
                    with open('config/CUSTOM_POI.txt', 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                except Exception as e:
                    logger.error(f"Error reading existing POI file: {e}")
                    return False
                
                filtered_lines = []
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    parts = line.split(',')
                    if len(parts) >= 4:
                        existing_name = parts[0].strip()
                        existing_map = parts[3].strip()
                        
                        if not (existing_name.lower() == name.lower() and existing_map == map_name):
                            filtered_lines.append(line + '\n')
                    else:
                        filtered_lines.append(line + '\n')
                
                try:
                    with open('config/CUSTOM_POI.txt', 'w', encoding='utf-8') as f:
                        f.writelines(filtered_lines)
                except Exception as e:
                    logger.error(f"Error writing filtered POI file: {e}")
                    return False
            
            try:
                with open('config/CUSTOM_POI.txt', 'a', encoding='utf-8') as f:
                    f.write(f"{name},{x},{y},{map_name}\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as e:
                logger.error(f"Error appending new POI: {e}")
                return False
            
            logger.info(f"Created custom POI: {name} at {x},{y} for map {map_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving custom POI: {e}")
            return False


def launch_custom_poi_creator(use_ppi: bool = False, player_detector=None, current_map: str = "main") -> bool:
    try:
        coordinates = None
        
        if player_detector:
            try:
                coordinates = player_detector.get_player_position(use_ppi)
            except Exception as e:
                logger.error(f"Error using player detector: {e}")
        
        if not coordinates:
            try:
                from lib.guis.coordinate_utils import get_current_coordinates
                coordinates = get_current_coordinates()
            except ImportError:
                logger.error("No coordinate utilities available")
            except Exception as e:
                logger.error(f"Error using coordinate utilities: {e}")
        
        if not coordinates:
            logger.error("Unable to determine player location for custom POI")
            speaker.speak("Unable to determine player location for custom POI")
            return False
        
        app = wx.GetApp()
        if app is None:
            app = wx.App(False)
        
        dlg = CustomPOIGUI(None, use_ppi, player_detector, current_map)
        
        if dlg and hasattr(dlg, 'coordinates') and dlg.coordinates:
            ensure_window_focus_and_center_mouse(dlg)
            
            result = dlg.ShowModal()
            creation_successful = getattr(dlg, 'creation_successful', False)
            
            dlg.Destroy()
            
            return creation_successful
        else:
            if dlg:
                dlg.Destroy()
            return False
        
    except Exception as e:
        logger.error(f"Error launching custom POI GUI: {e}")
        error = DisplayableError(
            f"Error launching custom POI GUI: {str(e)}",
            "Application Error"
        )
        error.displayError()
        speaker.speak("Error opening custom POI creator")
>>>>>>> 7c21c23a460e8f25bc96524c200b22c8b26c9b15
        return False