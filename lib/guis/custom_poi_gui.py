from tkinter import ttk
import tkinter as tk
from typing import Optional, Tuple
from accessible_output2.outputs.auto import Auto
from lib.guis.AccessibleUIBackend import AccessibleUIBackend
from lib.utilities import force_focus_window
from lib.custom_poi_handler import create_custom_poi
from lib.ppi import find_player_position
from lib.player_location import find_player_icon_location
import pyautogui

class CustomPOIGUI:
    def __init__(self, use_ppi: bool = False):
        self.use_ppi = use_ppi
        self.speaker = Auto()
        self.ui = None
        self.coordinates = None

    def get_current_position(self) -> Optional[Tuple[int, int]]:
        """Get current position using either PPI or regular icon detection."""
        if self.use_ppi:
            return find_player_position()
        return find_player_icon_location()

    def create_gui(self) -> None:
        """Create and display the custom POI GUI."""
        # Get initial coordinates
        self.coordinates = self.get_current_position()
        if not self.coordinates:
            self.speaker.speak("Unable to determine player location for custom POI")
            print("Unable to determine player location for custom POI")
            return

        # Initialize UI
        self.ui = AccessibleUIBackend(title="Enter custom POI name")
        self.ui.add_tab("Custom POI")

        # Create GUI elements
        self.create_entry_field()
        self.create_coordinate_display()
        self.create_save_button()
        self.create_refresh_button()
        
        # Initialize window
        self.initialize_window()
        
        # Set initial focus
        self.ui.root.after(100, lambda: force_focus_window(
            self.ui.root,
            "",
            self.focus_first_widget
        ))
        
        # Start the UI
        self.ui.run()

    def create_entry_field(self) -> None:
        """Create the POI name entry field."""
        frame = ttk.Frame(self.ui.tabs["Custom POI"])
        frame.pack(fill='x', padx=5, pady=5)
        
        label = ttk.Label(frame, text="POI Name")
        label.pack(side='left')
        
        var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=var)
        entry.pack(side='right', expand=True, fill='x')
        entry.description = "Enter a name for this location"
        
        self.ui.widgets["Custom POI"].append(entry)
        self.ui.variables["Custom POI"]["POI Name"] = var

    def create_coordinate_display(self) -> None:
        """Create the coordinate display field."""
        frame = ttk.Frame(self.ui.tabs["Custom POI"])
        frame.pack(fill='x', padx=5, pady=5)
        
        label = ttk.Label(frame, text=f"Current Position: ({self.coordinates[0]}, {self.coordinates[1]})")
        label.pack(side='left')
        self.coordinate_label = label

    def create_save_button(self) -> None:
        """Create the save button."""
        button = ttk.Button(
            self.ui.tabs["Custom POI"],
            text="Save POI",
            command=self.save_poi
        )
        button.pack(fill='x', padx=5, pady=5)
        button.custom_speech = "Save POI"
        self.ui.widgets["Custom POI"].append(button)

    def create_refresh_button(self) -> None:
        """Create the refresh coordinates button."""
        button = ttk.Button(
            self.ui.tabs["Custom POI"],
            text="Refresh Position",
            command=self.refresh_coordinates
        )
        button.pack(fill='x', padx=5, pady=5)
        button.custom_speech = "Refresh Position"
        self.ui.widgets["Custom POI"].append(button)

    def refresh_coordinates(self) -> None:
        """Refresh the current coordinates."""
        new_coords = self.get_current_position()
        if new_coords:
            self.coordinates = new_coords
            self.coordinate_label.config(text=f"Current Position: ({self.coordinates[0]}, {self.coordinates[1]})")
            self.ui.speak(f"Position updated to {self.coordinates[0]}, {self.coordinates[1]}")
        else:
            self.ui.speak("Could not determine current position")

    def save_poi(self) -> None:
        """Save the POI with the current coordinates."""
        poi_name = self.ui.variables["Custom POI"]["POI Name"].get().strip()
        if not poi_name:
            self.ui.speak("Please enter a name for the POI")
            return

        if create_custom_poi(self.coordinates, poi_name):
            self.ui.speak(f"Custom POI {poi_name} saved")
            self.ui.root.destroy()
            # Refocus the game window
            pyautogui.click()
        else:
            self.ui.speak("Error saving custom POI")

    def initialize_window(self) -> None:
        """Set up window properties."""
        self.ui.root.geometry("400x200")
        self.ui.root.resizable(False, False)
        self.ui.root.protocol("WM_DELETE_WINDOW", self.ui.save_and_close)

    def focus_first_widget(self) -> None:
        """Focus the first widget and announce its state."""
        if self.ui.widgets["Custom POI"]:
            first_widget = self.ui.widgets["Custom POI"][0]
            first_widget.focus_set()
            widget_info = self.ui.get_widget_info(first_widget)
            if widget_info:
                self.ui.speak(widget_info)

def create_custom_poi_gui(use_ppi: bool = False) -> None:
    """Create and display the custom POI GUI."""
    gui = CustomPOIGUI(use_ppi)
    gui.create_gui()
