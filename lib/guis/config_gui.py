import tkinter as tk
import configparser
from lib.guis.AccessibleUIBackend import AccessibleUIBackend
from lib.utilities import force_focus_window, DEFAULT_CONFIG
from tkinter import ttk
from typing import Callable, Optional

def create_config_gui(update_script_callback: Callable[[configparser.ConfigParser], None]) -> None:
    """Create and display the configuration GUI.
    
    Args:
        update_script_callback: Callback function to update the main script with new configuration
    """
    # Load the default configuration
    default_config = configparser.ConfigParser(interpolation=None)
    default_config.optionxform = str  # Preserve case
    default_config.read_string(DEFAULT_CONFIG)

    # Initialize the Accessible UI Backend
    ui = AccessibleUIBackend(
        title="FA11y Configuration", 
        config_file='config.txt', 
        default_config=default_config
    )
    config = ui.config

    # Add all configuration sections and their widgets
    for section in config.sections():
        ui.add_tab(section)
        for key in config[section]:
            value_string = config[section][key]
            value, description = ui.extract_value_and_description(value_string)

            if section == 'SCRIPT KEYBINDS':
                ui.add_keybind(section, key, initial_value=value_string)
            elif value.lower() in ['true', 'false']:
                ui.add_checkbox(section, key, initial_value=value_string)
            else:
                ui.add_entry(section, key, initial_value=value_string)

    def save_and_close() -> None:
        """Save configuration, update the script, and close the GUI."""
        try:
            # Save all sections
            for tab_name in ui.tabs:
                if tab_name not in ui.config.sections():
                    ui.config.add_section(tab_name)

                # Save all variables in each section
                for key, var in ui.variables[tab_name].items():
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

                    if isinstance(var, tk.BooleanVar):
                        value = 'true' if var.get() else 'false'
                    else:
                        value = var.get()

                    ui.config[tab_name][key] = f"{value} \"{description}\"" if description else value

            # Save configuration and update the script
            ui.save_config()
            update_script_callback(ui.config)
            ui.speak("Configuration saved and applied")
        except Exception as e:
            print(f"Error saving configuration: {e}")
            ui.speak("Error saving configuration")
        finally:
            ui.root.destroy()

    # Override the default save_and_close method
    ui.save_and_close = save_and_close
    ui.root.protocol("WM_DELETE_WINDOW", save_and_close)

    def focus_first_widget() -> None:
        """Set focus to the first widget and provide initial instructions."""
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

    # Set up initial focus with help message
    ui.root.after(100, lambda: force_focus_window(
        ui.root,
        "Press H for help!",
        focus_first_widget
    ))

    # Run the UI
    ui.run()