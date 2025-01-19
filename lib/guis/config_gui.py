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
        "Toggles": {},      # All toggle settings
        "Values": {},       # All value settings
        "Keybinds": {},     # All keybind settings
        "VoiceCommands": {},# Voice command settings
    }

    # ----------------------------
    # 1) CREATE TABS
    # ----------------------------
    def create_tabs() -> None:
        """Create and initialize all tabs."""
        ui.add_tab("Toggles")
        ui.add_tab("Values")
        ui.add_tab("Keybinds")
        ui.add_tab("VoiceCommands")

    # ----------------------------
    # 2) ANALYZE EXISTING CONFIG
    # ----------------------------
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
                elif section == "VoiceCommands":
                    section_tab_mapping["VoiceCommands"][key] = "VoiceCommands"
                # Legacy format if needed
                elif section == "SETTINGS":
                    if value.lower() in ['true', 'false']:
                        section_tab_mapping["Toggles"][key] = "Toggles"
                    else:
                        section_tab_mapping["Values"][key] = "Values"
                elif section == "SCRIPT KEYBINDS":
                    section_tab_mapping["Keybinds"][key] = "Keybinds"

    # ----------------------------
    # 3) WIDGET-CREATION HELPERS
    # ----------------------------
    def create_keybind_entry(tab_name: str, key: str, value_string: str) -> None:
        """Create a keybind entry widget."""
        ui.add_keybind(tab_name, key, value_string)

    def create_checkbox(tab_name: str, key: str, value_string: str) -> None:
        """Create a checkbox widget."""
        ui.add_checkbox(tab_name, key, value_string)

    def create_value_entry(tab_name: str, key: str, value_string: str) -> None:
        """Create a value entry widget."""
        ui.add_entry(tab_name, key, value_string)

    # ----------------------------
    # 4) MAKE WIDGETS
    # ----------------------------
    def create_widgets() -> None:
        """Create all widgets based on the existing config."""
        for section in config.sections():
            if section == "POI":  # Skip POI
                continue

            for key in config[section]:
                value_string = config[section][key]
                tab_name = None

                # Decide which tab
                if section == "Toggles" or (
                    section == "SETTINGS" and
                    (value_string.lower().startswith('true') or value_string.lower().startswith('false'))
                ):
                    tab_name = "Toggles"
                    create_checkbox(tab_name, key, value_string)

                elif section in ["Keybinds", "SCRIPT KEYBINDS"]:
                    tab_name = "Keybinds"
                    create_keybind_entry(tab_name, key, value_string)

                elif section in ["Values", "SETTINGS"]:
                    tab_name = "Values"
                    create_value_entry(tab_name, key, value_string)

                elif section == "VoiceCommands":
                    # Just treat them like normal values
                    tab_name = "VoiceCommands"
                    create_value_entry(tab_name, key, value_string)

    # ----------------------------
    # 5) SAVE-AND-CLOSE LOGIC
    # ----------------------------
    def save_and_close() -> None:
        """Save configuration, update the script, and close the GUI."""
        try:
            # Ensure all relevant sections exist
            for section in ["Toggles", "Values", "Keybinds", "POI", "VoiceCommands"]:
                if section not in ui.config.sections():
                    ui.config.add_section(section)

            # Preserve POI section if it exists
            if "POI" in config.sections():
                for key in config["POI"]:
                    ui.config["POI"][key] = config["POI"][key]

            # Save each tab's variables
            for tab_name, variables in ui.variables.items():
                for key, widget_var in variables.items():
                    target_section = None
                    if tab_name == "Toggles":
                        target_section = "Toggles"
                    elif tab_name == "Values":
                        target_section = "Values"
                    elif tab_name == "Keybinds":
                        target_section = "Keybinds"
                    elif tab_name == "VoiceCommands":
                        target_section = "VoiceCommands"
                    
                    if not target_section:
                        continue

                    # Convert widget value
                    if isinstance(widget_var, tk.BooleanVar):
                        raw_val = 'true' if widget_var.get() else 'false'
                    else:
                        # If user empties the field, fallback to default (like the other code).
                        val = widget_var.get()
                        raw_val = val if val else default_config.get(
                            target_section, key, fallback=""
                        )

                    # Try to keep the old description if it existed
                    old_full = config.get(target_section, key, fallback=raw_val)
                    old_value, old_desc = ui.extract_value_and_description(old_full)
                    
                    # Check if this widget had a "description" we stored
                    # (like we do for checkboxes)
                    new_desc = ""
                    for w in ui.widgets[tab_name]:
                        if (
                            isinstance(w, ttk.Checkbutton) and w.cget('text') == key
                        ) or (
                            hasattr(w, 'master') and w.master.winfo_children() and
                            w.master.winfo_children()[0].cget('text') == key
                        ):
                            new_desc = getattr(w, 'description', '')
                            break

                    # If there's already a description in config, prefer it unless empty
                    if old_desc and old_desc.strip():
                        final_desc = old_desc
                    else:
                        # If old_desc was empty, then we can store new_desc
                        final_desc = new_desc

                    # If there's STILL no desc, just store the raw value
                    if final_desc.strip():
                        ui.config[target_section][key] = f"{raw_val} \"{final_desc}\""
                    else:
                        ui.config[target_section][key] = raw_val

            # Actually write to file, call the update callback, speak success
            ui.save_config()
            update_script_callback(ui.config)
            ui.speak("Configuration saved and applied")

        except Exception as e:
            print(f"Error saving configuration: {e}")
            ui.speak("Error saving configuration")
        finally:
            ui.root.destroy()

    # ----------------------------
    # 6) WINDOW INIT
    # ----------------------------
    def initialize_window() -> None:
        """Set up the window properties."""
        ui.root.resizable(False, False)
        ui.root.protocol("WM_DELETE_WINDOW", save_and_close)
        # Override the default method
        ui.save_and_close = save_and_close

    # ----------------------------
    # 7) FOCUS-HANDLING
    # ----------------------------
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

    # ----------------------------
    # 8) GO
    # ----------------------------
    create_tabs()
    analyze_config()
    create_widgets()
    initialize_window()

    # After slight delay, force focus and read help
    ui.root.after(
        100,
        lambda: force_focus_window(ui.root, "Press H for help!", focus_first_widget)
    )

    ui.run()