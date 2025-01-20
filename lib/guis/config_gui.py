from tkinter import ttk
import tkinter as tk
import configparser
from typing import Callable, Dict

from lib.guis.AccessibleUIBackend import AccessibleUIBackend
from lib.utilities import force_focus_window, DEFAULT_CONFIG

def create_config_gui(update_script_callback: Callable[[configparser.ConfigParser], None]) -> None:
    """Create and display the configuration GUI."""
    # Load default configuration
    default_config = configparser.ConfigParser(interpolation=None)
    default_config.optionxform = str  # Preserve case
    default_config.read_string(DEFAULT_CONFIG)

    # Initialize UI
    ui = AccessibleUIBackend(
        title="FA11y Configuration", 
        config_file='config.txt', 
        default_config=default_config
    )
    config = ui.config

    # Configuration mapping - just map everything directly to its appropriate tab
    section_tab_mapping: Dict[str, Dict[str, str]] = {
        "Toggles": {},     # All toggle settings
        "Values": {},      # All value settings
        "Keybinds": {},   # All keybind settings
    }

    # Tab creation
    def create_tabs() -> None:
        """Create and initialize all tabs."""
        ui.add_tab("Toggles")
        ui.add_tab("Values")
        ui.add_tab("Keybinds")

    # Modified Configuration analysis
    def analyze_config() -> None:
        """Analyze configuration to determine appropriate tab mappings."""
        for section in config.sections():
            if section == "POI":  # Skip POI section
                continue
                
            for key in config[section]:
                value_string = config[section][key]
                value, _ = ui.extract_value_and_description(value_string)

                # Map items based on their section
                if section == "Toggles":
                    section_tab_mapping["Toggles"][key] = "Toggles"
                elif section == "Values":
                    section_tab_mapping["Values"][key] = "Values"
                elif section == "Keybinds":
                    section_tab_mapping["Keybinds"][key] = "Keybinds"
                # Handle legacy format if needed
                elif section == "SETTINGS":
                    if value.lower() in ['true', 'false']:
                        section_tab_mapping["Toggles"][key] = "Toggles"
                    else:
                        section_tab_mapping["Values"][key] = "Values"
                elif section == "SCRIPT KEYBINDS":
                    section_tab_mapping["Keybinds"][key] = "Keybinds"

    # Widget creation functions
    def create_keybind_entry(tab_name: str, key: str, value_string: str) -> None:
        """Create a keybind entry widget."""
        value, description = ui.extract_value_and_description(value_string)
        ui.add_keybind(tab_name, key, value_string)

    def create_checkbox(tab_name: str, key: str, value_string: str) -> None:
        """Create a checkbox widget."""
        ui.add_checkbox(tab_name, key, value_string)

    def create_value_entry(tab_name: str, key: str, value_string: str) -> None:
        """Create a value entry widget."""
        ui.add_entry(tab_name, key, value_string)

    def create_widgets() -> None:
        """Create all widgets based on configuration."""
        for section in config.sections():
            if section == "POI":  # Skip POI section
                continue
                
            for key in config[section]:
                value_string = config[section][key]
                tab_name = None

                # Determine tab based on section
                if section == "Toggles" or (section == "SETTINGS" and value_string.lower().startswith('true') or value_string.lower().startswith('false')):
                    tab_name = "Toggles"
                    create_checkbox(tab_name, key, value_string)
                elif section == "Keybinds" or section == "SCRIPT KEYBINDS":
                    tab_name = "Keybinds"
                    create_keybind_entry(tab_name, key, value_string)
                elif section == "Values" or section == "SETTINGS":
                    tab_name = "Values"
                    create_value_entry(tab_name, key, value_string)

    # Modified save functionality
    def save_and_close() -> None:
        """Save configuration, update the script, and close the GUI."""
        try:
            # Ensure all sections exist
            for section in ["Toggles", "Values", "Keybinds", "POI"]:
                if section not in ui.config.sections():
                    ui.config.add_section(section)

            # Save POI section as is if it exists
            if "POI" in config.sections():
                for key in config["POI"]:
                    ui.config["POI"][key] = config["POI"][key]

            # Save values back to their appropriate sections based on tab
            for key, widget in ui.variables["Toggles"].items():
                if isinstance(widget, tk.BooleanVar):
                    description = ""
                    for w in ui.widgets["Toggles"]:
                        if isinstance(w, ttk.Checkbutton) and w.cget('text') == key:
                            description = getattr(w, 'description', '')
                            break
                    value = 'true' if widget.get() else 'false'
                    ui.config["Toggles"][key] = f"{value} \"{description}\"" if description else value

            for key, widget in ui.variables["Values"].items():
                value = widget.get()
                description = ""
                for w in ui.widgets["Values"]:
                    if hasattr(w, 'master') and w.master.winfo_children() and \
                       w.master.winfo_children()[0].cget('text') == key:
                        description = getattr(w, 'description', '')
                        break
                ui.config["Values"][key] = f"{value} \"{description}\"" if description else value

            for key, widget in ui.variables["Keybinds"].items():
                value = widget.get()
                description = ""
                for w in ui.widgets["Keybinds"]:
                    if hasattr(w, 'master') and w.master.winfo_children() and \
                       w.master.winfo_children()[0].cget('text') == key:
                        description = getattr(w, 'description', '')
                        break
                ui.config["Keybinds"][key] = f"{value} \"{description}\"" if description else value

            # Save configuration and update the script
            ui.save_config()
            update_script_callback(ui.config)
            ui.speak("Configuration saved and applied")
        except Exception as e:
            print(f"Error saving configuration: {e}")
            ui.speak("Error saving configuration")
        finally:
            ui.root.destroy()

    # Window initialization
    def initialize_window() -> None:
        """Set up window properties."""
        ui.root.resizable(False, False)
        ui.root.protocol("WM_DELETE_WINDOW", save_and_close)
        # Override the default save_and_close method
        ui.save_and_close = save_and_close

    # Focus handling
    def focus_first_widget() -> None:
        """Focus the first widget and announce its state."""
        first_tab = ui.notebook.tabs()[0]
        ui.notebook.select(first_tab)
        current_tab = ui.notebook.tab(first_tab, "text")
        if ui.widgets[current_tab]:
            first_widget = ui.widgets[current_tab][0]
            first_widget.focus_set()
            ui.speak(f"{current_tab} tab.")
            widget_info = ui.get_widget_info(first_widget)
            if widget_info:
                ui.speak(widget_info)

    # Create interface elements
    create_tabs()
    analyze_config()
    create_widgets()
    initialize_window()

    # Initialize focus with help message
    ui.root.after(100, lambda: force_focus_window(
        ui.root,
        "Press H for help!",
        focus_first_widget
    ))

    # Start the UI
    ui.run()