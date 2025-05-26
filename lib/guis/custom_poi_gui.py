"""
Custom POI creation GUI for FA11y
Provides interface for creating custom points of interest
"""
import os
import logging
import tkinter as tk
from tkinter import ttk
from typing import Optional, Tuple, Callable

from lib.guis.base_ui import AccessibleUI
from lib.guis.poi_selector_gui import POIData
from lib.utilities import force_focus_window, read_config
from lib.mouse import left_click

# Initialize logger
logger = logging.getLogger(__name__)

class CustomPOIGUI(AccessibleUI):
    """Custom POI creation GUI"""
    
    def __init__(self, use_ppi: bool = False, player_detector = None, current_map: str = "main"):
        """Initialize the custom POI GUI
        
        Args:
            use_ppi: Whether to use PPI for position detection
            player_detector: Player detection module
            current_map: Name of the map to create the POI for
        """
        super().__init__(title="Enter custom POI name")
        
        self.use_ppi = use_ppi
        self.player_detector = player_detector
        
        # Use the provided map name instead of reading from config
        self.current_map = current_map
        
        # Get initial position - we already checked in the launcher, so this should succeed
        self.coordinates = self.get_current_position()
        if not self.coordinates:
            logger.error("Unable to determine player location for custom POI")
            self.speak("Unable to determine player location for custom POI")
            self.close()
            return
            
        # Setup UI components
        self.setup()
    
    def setup(self) -> None:
        """Set up the custom POI GUI"""
        # Add custom POI tab
        self.add_tab("Custom POI")
        
        # Create GUI elements
        self.create_entry_field()
        self.create_coordinate_display()
        self.create_action_buttons()
        
        # Initialize window properties
        self.root.geometry("400x200")
        self.root.resizable(False, False)
        
        # Initialize focus
        self.root.after(100, lambda: force_focus_window(
            self.root,
            "",
            self.focus_first_widget
        ))
    
    def get_current_position(self) -> Optional[Tuple[int, int]]:
        """Get current position using either PPI or regular icon detection
        
        Returns:
            tuple or None: (x, y) coordinates or None if not found
        """
        if self.player_detector:
            return self.player_detector.get_player_position(self.use_ppi)
        return None
    
    def create_entry_field(self) -> None:
        """Create the POI name entry field"""
        frame = ttk.Frame(self.tabs["Custom POI"])
        frame.pack(fill='x', padx=5, pady=5)
        
        label = ttk.Label(frame, text="POI Name")
        label.pack(side='left')
        
        var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=var)
        entry.pack(side='right', expand=True, fill='x')
        entry.description = "Enter a name for this location"
        
        self.widgets["Custom POI"].append(entry)
        self.variables["Custom POI"]["POI Name"] = var
        
        # Add map name display
        map_frame = ttk.Frame(self.tabs["Custom POI"])
        map_frame.pack(fill='x', padx=5, pady=5)
        
        map_label = ttk.Label(map_frame, text="Current Map:")
        map_label.pack(side='left')
        
        # Format map name for display - capitalize and replace underscores
        display_map = self.current_map.replace('_', ' ').title()
        map_value = ttk.Label(map_frame, text=display_map)
        map_value.pack(side='right')
    
    def create_coordinate_display(self) -> None:
        """Create the coordinate display field"""
        frame = ttk.Frame(self.tabs["Custom POI"])
        frame.pack(fill='x', padx=5, pady=5)
        
        coord_text = f"Current Position: ({self.coordinates[0]}, {self.coordinates[1]})"
        label = ttk.Label(frame, text=coord_text)
        label.pack(side='left')
        self.coordinate_label = label
    
    def create_action_buttons(self) -> None:
        """Create the action buttons"""
        # Save POI button
        save_button = ttk.Button(
            self.tabs["Custom POI"],
            text="Save POI",
            command=self.save_poi
        )
        save_button.pack(fill='x', padx=5, pady=5)
        save_button.custom_speech = "Save POI"
        self.widgets["Custom POI"].append(save_button)

        # Refresh position button
        refresh_button = ttk.Button(
            self.tabs["Custom POI"],
            text="Refresh Position",
            command=self.refresh_coordinates
        )
        refresh_button.pack(fill='x', padx=5, pady=5)
        refresh_button.custom_speech = "Refresh Position"
        self.widgets["Custom POI"].append(refresh_button)
    
    def refresh_coordinates(self) -> None:
        """Refresh the current coordinates"""
        new_coords = self.get_current_position()
        if new_coords:
            self.coordinates = new_coords
            self.coordinate_label.config(text=f"Current Position: ({self.coordinates[0]}, {self.coordinates[1]})")
            self.speak(f"Position updated to {self.coordinates[0]}, {self.coordinates[1]}")
        else:
            self.speak("Could not determine current position")
    
    def save_poi(self) -> None:
        """Save the POI with the current coordinates"""
        poi_name = self.variables["Custom POI"]["POI Name"].get().strip()
        if not poi_name:
            self.speak("Please enter a name for the POI")
            return

        # Include the current map when saving
        if self.create_custom_poi(self.coordinates, poi_name, self.current_map):
            self.speak(f"Custom POI {poi_name} saved for {self.current_map} map")
            self.close()
            # Refocus the game window
            left_click()
        else:
            self.speak("Error saving custom POI")
    
    def create_custom_poi(self, coordinates: Tuple[int, int], name: str, map_name: str) -> bool:
        """Create a custom POI file
        
        Args:
            coordinates: (x, y) coordinates
            name: POI name
            map_name: Map name this POI belongs to
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not coordinates:
            logger.error("Could not determine current position for custom POI")
            return False
            
        x, y = coordinates
        try:
            # Save with map name included
            with open('CUSTOM_POI.txt', 'a', encoding='utf-8') as f:
                f.write(f"{name},{x},{y},{map_name}\n")
            logger.info(f"Created custom POI: {name} at {x},{y} for map {map_name}")
            return True
        except Exception as e:
            logger.error(f"Error saving custom POI: {e}")
            return False
    
    def focus_first_widget(self) -> None:
        """Focus the first widget and announce its state"""
        if self.widgets["Custom POI"]:
            first_widget = self.widgets["Custom POI"][0]
            first_widget.focus_set()
            widget_info = self.get_widget_info(first_widget)
            if widget_info:
                self.speak(widget_info)


def launch_custom_poi_creator(use_ppi: bool = False, player_detector = None, current_map: str = "main") -> None:
    """Launch the custom POI creator GUI
    
    Args:
        use_ppi: Whether to use PPI for position detection
        player_detector: Player detection module
        current_map: Name of the map to create the POI for
    """
    try:
        # First check if we can get coordinates before creating any UI
        coordinates = None
        if player_detector:
            coordinates = player_detector.get_player_position(use_ppi)
        
        if not coordinates:
            logger.error("Unable to determine player location for custom POI")
            from accessible_output2.outputs.auto import Auto
            speaker = Auto()
            speaker.speak("Unable to determine player location for custom POI")
            return  # Don't even create the GUI if we can't get coordinates
        
        # Only now create and run the GUI since we have coordinates
        gui = CustomPOIGUI(use_ppi, player_detector, current_map)
        gui.run()
    except Exception as e:
        logger.error(f"Error launching custom POI GUI: {e}")