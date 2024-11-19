from tkinter import ttk
import tkinter as tk
from typing import Optional, Tuple

from lib.guis.AccessibleUIBackend import AccessibleUIBackend
from lib.player_location import find_player_icon_location
from lib.utilities import force_focus_window
import pyautogui

def create_custom_poi_gui() -> None:
    """Create and display the custom POI GUI.
    
    Allows users to save a custom POI at their current location with a custom name.
    The GUI provides accessible feedback and keyboard navigation.
    """
    # Get initial coordinates
    coordinates: Optional[Tuple[int, int]] = find_player_icon_location()
    if not coordinates:
        print("Unable to determine player location for custom POI")
        return

    # Initialize UI
    ui = AccessibleUIBackend(title="Enter custom POI name")
    ui.add_tab("Custom POI")

    # Create the entry field
    def create_entry_field() -> None:
        frame = ttk.Frame(ui.tabs["Custom POI"])
        frame.pack(fill='x', padx=5, pady=5)
        
        label = ttk.Label(frame, text="POI Name")
        label.pack(side='left')
        
        var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=var, state='readonly')
        entry.pack(side='right', expand=True, fill='x')
        entry.description = "Enter a name for this location"
        
        ui.widgets["Custom POI"].append(entry)
        ui.variables["Custom POI"]["POI Name"] = var

    # Create the save button
    def create_save_button() -> None:
        button = ttk.Button(ui.tabs["Custom POI"], 
                          text="Save POI",
                          command=save_poi)
        button.pack(fill='x', padx=5, pady=5)
        button.custom_speech = "Save POI"
        ui.widgets["Custom POI"].append(button)

    # Save functionality
    def save_poi() -> None:
        """Save the POI name and coordinates to the CUSTOM_POI.txt file."""
        poi_name = ui.variables["Custom POI"]["POI Name"].get().strip()
        if poi_name:
            try:
                with open('CUSTOM_POI.txt', 'a', encoding='utf-8') as file:
                    file.write(f"{poi_name},{coordinates[0]},{coordinates[1]}\n")
                ui.speak(f"Custom P O I {poi_name} saved")
                ui.root.destroy()
                # Refocus the Fortnite window
                pyautogui.click()
            except Exception as e:
                print(f"Error saving custom POI: {e}")
                ui.speak("Error saving custom P O I")
        else:
            ui.speak("Please enter a name for the P O I")

    # Window initialization
    def initialize_window() -> None:
        """Set up window properties and size."""
        ui.root.geometry("300x150")
        ui.root.resizable(False, False)
        ui.root.protocol("WM_DELETE_WINDOW", ui.save_and_close)

    # Focus handling
    def focus_first_widget() -> None:
        """Focus the first widget and announce its state."""
        if ui.widgets["Custom POI"]:
            first_widget = ui.widgets["Custom POI"][0]
            first_widget.focus_set()
            widget_info = ui.get_widget_info(first_widget)
            if widget_info:
                ui.speak(widget_info)

    # Create interface elements
    create_entry_field()
    create_save_button()
    initialize_window()

    # Initialize focus
    ui.root.after(100, lambda: force_focus_window(
        ui.root,
        "",
        focus_first_widget
    ))

    # Start the UI
    ui.run()