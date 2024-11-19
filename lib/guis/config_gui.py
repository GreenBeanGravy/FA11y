from tkinter import ttk
import tkinter as tk
import configparser
from typing import Callable, Dict

from lib.guis.AccessibleUIBackend import AccessibleUIBackend
from lib.utilities import force_focus_window, DEFAULT_CONFIG

def create_config_gui(update_script_callback: Callable[[configparser.ConfigParser], None]) -> None:
    """Create and display the configuration GUI.
    
    A multi-tabbed interface for managing script settings, values, and keybinds.
    Provides accessible feedback and keyboard navigation.
    
    Args:
        update_script_callback: Callback function to update the main script with new configuration
    """
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

    # Configuration mapping
    section_tab_mapping: Dict[str, Dict[str, str]] = {
        "SETTINGS": {},  # Will be populated with key -> tab mappings
        "SCRIPT KEYBINDS": {},  # All keys go to "Keybinds" tab
    }

    # Tab creation
    def create_tabs() -> None:
        """Create and initialize all tabs."""
        ui.add_tab("Toggles")
        ui.add_tab("Values")
        ui.add_tab("Keybinds")

    # Configuration analysis
    def analyze_config() -> None:
        """Analyze configuration to determine appropriate tab mappings."""
        for section in config.sections():
            if section == "POI":  # Skip POI section
                continue
                
            for key in config[section]:
                value_string = config[section][key]
                value, _ = ui.extract_value_and_description(value_string)

                if section == "SCRIPT KEYBINDS":
                    section_tab_mapping[section][key] = "Keybinds"
                elif value.lower() in ['true', 'false']:
                    section_tab_mapping["SETTINGS"][key] = "Toggles"
                else:
                    section_tab_mapping["SETTINGS"][key] = "Values"

    # Widget creation functions
    def create_keybind_entry(tab_name: str, key: str, value_string: str) -> None:
        """Create a keybind entry widget."""
        value, description = ui.extract_value_and_description(value_string)
        var = tk.StringVar(value=value)
        frame = ttk.Frame(ui.tabs[tab_name])
        frame.pack(fill='x', padx=5, pady=5)
        
        label = ttk.Label(frame, text=key)
        label.pack(side='left')
        
        entry = ttk.Entry(frame, textvariable=var, state='readonly')
        entry.pack(side='right', expand=True, fill='x')
        entry.is_keybind = True
        entry.description = description
        
        ui.widgets[tab_name].append(entry)
        ui.variables[tab_name][key] = var
        
        if value:
            ui.keybind_map[value.lower()] = key

    def create_checkbox(tab_name: str, key: str, value_string: str) -> None:
        """Create a checkbox widget."""
        value, description = ui.extract_value_and_description(value_string)
        bool_value = value.lower() == 'true'
        var = tk.BooleanVar(value=bool_value)
        
        checkbox = ttk.Checkbutton(ui.tabs[tab_name], text=key, variable=var)
        checkbox.pack(fill='x', padx=5, pady=5)
        checkbox.description = description
        
        ui.widgets[tab_name].append(checkbox)
        ui.variables[tab_name][key] = var

    def create_value_entry(tab_name: str, key: str, value_string: str) -> None:
        """Create a value entry widget."""
        value, description = ui.extract_value_and_description(value_string)
        var = tk.StringVar(value=value)
        frame = ttk.Frame(ui.tabs[tab_name])
        frame.pack(fill='x', padx=5, pady=5)
        
        label = ttk.Label(frame, text=key)
        label.pack(side='left')
        
        entry = ttk.Entry(frame, textvariable=var, state='readonly')
        entry.pack(side='right', expand=True, fill='x')
        entry.description = description
        
        ui.widgets[tab_name].append(entry)
        ui.variables[tab_name][key] = var

    def create_widgets() -> None:
        """Create all widgets based on configuration."""
        for section in config.sections():
            if section == "POI":  # Skip POI section
                continue
                
            for key in config[section]:
                value_string = config[section][key]
                tab_name = section_tab_mapping[section].get(key)
                
                if tab_name == "Keybinds":
                    create_keybind_entry(tab_name, key, value_string)
                elif tab_name == "Toggles":
                    create_checkbox(tab_name, key, value_string)
                elif tab_name == "Values":
                    create_value_entry(tab_name, key, value_string)

    # Save functionality
    def save_and_close() -> None:
        """Save configuration, update the script, and close the GUI."""
        try:
            # Ensure all original sections exist
            for section in ["SETTINGS", "SCRIPT KEYBINDS", "POI"]:
                if section not in ui.config.sections():
                    ui.config.add_section(section)

            # Save POI section as is if it exists
            if "POI" in config.sections():
                for key in config["POI"]:
                    ui.config["POI"][key] = config["POI"][key]

            # Save values back to their original sections
            for section, mappings in section_tab_mapping.items():
                for key, tab_name in mappings.items():
                    if tab_name in ui.variables and key in ui.variables[tab_name]:
                        widget = None
                        # Find the corresponding widget
                        for w in ui.widgets[tab_name]:
                            if isinstance(w, ttk.Checkbutton) and w.cget('text') == key:
                                widget = w
                                break
                            elif hasattr(w, 'master') and w.master.winfo_children() and \
                                 w.master.winfo_children()[0].cget('text') == key:
                                widget = w
                                break

                        description = getattr(widget, 'description', '') if widget else ''
                        var = ui.variables[tab_name][key]

                        if isinstance(var, tk.BooleanVar):
                            value = 'true' if var.get() else 'false'
                        else:
                            value = var.get()

                        ui.config[section][key] = f"{value} \"{description}\"" if description else value

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