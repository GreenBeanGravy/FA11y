from lib.guis.AccessibleUIBackend import AccessibleUIBackend
import pyautogui
from lib.player_location import find_player_icon_location
from lib.utilities import force_focus_window
from typing import Optional, Tuple

def create_custom_poi_gui() -> None:
    """Create a GUI for adding custom Points of Interest (POIs) at the player's current location.
    
    This GUI allows users to:
    1. Enter a name for a new POI
    2. Save the POI at the current player coordinates
    3. Provides audio feedback for all actions
    """
    coordinates: Optional[Tuple[int, int]] = find_player_icon_location()
    if not coordinates:
        print("Unable to determine player location for custom POI")
        return

    ui = AccessibleUIBackend(title="Enter custom POI name")
    
    # Set up the main tab
    ui.add_tab("Custom POI")
    
    # Add the POI name entry field
    ui.add_entry(
        "Custom POI",
        "POI Name",
        "Enter a name for this location"
    )

    def save_poi() -> None:
        """Save the POI name and coordinates to the CUSTOM_POI.txt file.
        
        Validates the POI name and provides appropriate feedback.
        Also refocuses the game window after saving.
        """
        poi_name = ui.variables["Custom POI"]["POI Name"].get().strip()
        if poi_name:
            try:
                with open('CUSTOM_POI.txt', 'a', encoding='utf-8') as file:
                    file.write(f"{poi_name},{coordinates[0]},{coordinates[1]}\n")
                ui.speak(f"Custom P O I {poi_name} saved")
                ui.root.destroy()
                # Refocus the Fortnite window at current mouse position
                pyautogui.click()
            except Exception as e:
                print(f"Error saving custom POI: {e}")
                ui.speak("Error saving custom P O I")
        else:
            ui.speak("Please enter a name for the P O I")

    # Add save button with custom speech
    ui.add_button(
        "Custom POI",
        "Save POI",
        save_poi,
        custom_speech="Save POI"
    )

    # Configure window size
    ui.root.geometry("300x150")
    
    # Set up initial focus
    def focus_first_widget() -> None:
        """Focus the POI name entry field."""
        ui.widgets["Custom POI"][0].focus_set()

    # Initialize window with no announcement
    ui.root.after(100, lambda: force_focus_window(
        ui.root,
        "",
        focus_first_widget
    ))

    ui.run()