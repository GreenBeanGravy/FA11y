import tkinter as tk
from tkinter import ttk
import configparser
from accessible_output2.outputs.auto import Auto
import os

speaker = Auto()

CONFIG_FILE = 'config.txt'

def speak(text):
    speaker.speak(text)

def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    return config

def save_config(config):
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)

def key_to_fa11y_format(key):
    key_mapping = {
        'control_l': 'lctrl',
        'control_r': 'rctrl',
        'alt_l': 'lalt',
        'alt_r': 'ralt',
        'shift_l': 'lshift',
        'shift_r': 'rshift',
    }
    return key_mapping.get(key, key)

def create_config_gui(update_script_callback):
    config = load_config()
    root = tk.Tk()
    root.title("FA11y Configuration")
    root.attributes('-topmost', True)

    notebook = ttk.Notebook(root)
    notebook.pack(expand=True, fill='both')

    pages = {}
    widgets_by_tab = {}
    for section in config.sections():
        page = ttk.Frame(notebook)
        notebook.add(page, text=section)
        pages[section] = page
        widgets_by_tab[section] = []

    variables = {}
    widgets = []
    currently_editing = [None]
    capturing_keybind = [False]
    last_spoken = [""]  # Variable to track the last spoken message

    for section in config.sections():
        for key, value in config.items(section):
            var = tk.StringVar(value=value)
            variables[(section, key)] = var

            frame = ttk.Frame(pages[section])
            frame.pack(fill='x', padx=5, pady=5)

            label = ttk.Label(frame, text=key.replace('_', ' ').title())
            label.pack(side='left')

            if section == 'SCRIPT KEYBINDS':
                widget = ttk.Entry(frame, textvariable=var, state='readonly')
                widget.bind('<FocusIn>', lambda e, k=key, v=value: on_keybind_focus(e, k, v))
            elif value.lower() in ['true', 'false']:
                widget = ttk.Checkbutton(frame, variable=var, onvalue='True', offvalue='False')
                widget.state(['!alternate'])
                if value.lower() == 'true':
                    widget.state(['selected'])
                else:
                    widget.state(['!selected'])
            else:
                widget = ttk.Entry(frame, textvariable=var, state='readonly')
            widget.pack(side='right', expand=True, fill='x')
            widgets.append(widget)
            widgets_by_tab[section].append(widget)

    def on_tab_change(event):
        tab = event.widget.tab('current')['text']
        speak(f"Switched to {tab} tab")
        if widgets_by_tab[tab]:
            widgets_by_tab[tab][0].focus_set()
            text = get_widget_text(widgets_by_tab[tab][0])
            value = get_widget_value(widgets_by_tab[tab][0])
            hint = get_navigation_hint(widgets_by_tab[tab][0])
            speak(f"{text}, {value}, {hint}")

    notebook.bind('<<NotebookTabChanged>>', on_tab_change)

    def get_widget_text(widget):
        if isinstance(widget, ttk.Checkbutton):
            return widget.master.winfo_children()[0].cget('text')
        elif isinstance(widget, ttk.Entry):
            return widget.master.winfo_children()[0].cget('text')
        elif isinstance(widget, ttk.Frame):
            return widget.winfo_children()[0].cget('text')
        else:
            return "Unknown widget"

    def get_widget_value(widget):
        if isinstance(widget, ttk.Checkbutton):
            return "checked" if 'selected' in widget.state() else "unchecked"
        elif isinstance(widget, ttk.Entry):
            return widget.get()
        elif isinstance(widget, ttk.Frame):
            return widget.winfo_children()[-1].get()
        else:
            return ""

    def get_navigation_hint(widget):
        if isinstance(widget, ttk.Checkbutton):
            return "press Enter to toggle"
        elif isinstance(widget, ttk.Entry):
            if notebook.tab(notebook.select(), "text") == 'SCRIPT KEYBINDS':
                return "press Enter to start capturing keybind"
            return "press Enter to edit"
        else:
            return ""

    def navigate(event):
        if capturing_keybind[0]:
            return "break"
        if currently_editing[0]:
            if event.keysym == 'Up':
                speak(f"Current value: {currently_editing[0].get()}")
            return "break"
        
        current = root.focus_get()
        current_tab = notebook.tab(notebook.select(), "text")
        current_tab_widgets = widgets_by_tab[current_tab]
        current_index = current_tab_widgets.index(current) if current in current_tab_widgets else -1
        
        if event.keysym == 'Down':
            next_index = (current_index + 1) % len(current_tab_widgets)
        else:  # Up
            next_index = (current_index - 1) % len(current_tab_widgets)
        
        next_widget = current_tab_widgets[next_index]
        next_widget.focus_set()
        
        text = get_widget_text(next_widget)
        value = get_widget_value(next_widget)
        hint = get_navigation_hint(next_widget)
        speak(f"{text}, {value}, {hint}")
        return "break"

    def on_keybind_focus(event, key, value):
        message = f"{key.replace('_', ' ').title()}, {value}, press Enter to start capturing keybind"
        if last_spoken[0] != message:  # Check if the message is the same as the last spoken message
            speak(message)
            last_spoken[0] = message  # Update last spoken message

    def on_key(event):
        if capturing_keybind[0]:
            if event.keysym not in ['Return', 'Tab', 'Escape']:
                current_widget = root.focus_get()
                key_name = key_to_fa11y_format(event.keysym.lower())
                current_widget.delete(0, tk.END)
                current_widget.insert(0, key_name)
                action_name = get_widget_text(current_widget)
                speak(f"Keybind for {action_name} set to {key_name}")
                capturing_keybind[0] = False
                current_widget.config(state='readonly')
            return "break"

    def on_enter(event):
        current = root.focus_get()
        if isinstance(current, ttk.Checkbutton):
            current.invoke()
            speak(f"{get_widget_text(current)} {get_widget_value(current)}")
        elif isinstance(current, ttk.Entry):
            if notebook.tab(notebook.select(), "text") == 'SCRIPT KEYBINDS':
                if not capturing_keybind[0]:
                    capturing_keybind[0] = True
                    current.config(state='normal')
                    action_name = get_widget_text(current)
                    speak(f"Press any key to set the keybind for {action_name}. Press Escape to cancel.")
                else:
                    capturing_keybind[0] = False
                    current.config(state='readonly')
                    speak("Keybind capture cancelled")
            elif currently_editing[0] == current:
                currently_editing[0] = None
                current.config(state='readonly')
                speak(f"{get_widget_text(current)} set to {current.get()}")
            elif not currently_editing[0]:
                currently_editing[0] = current
                current.config(state='normal')
                speak(f"Editing {get_widget_text(current)}. Current value: {current.get()}. Press Enter when done.")
        return "break"

    def save_and_close():
        for (section, key), var in variables.items():
            config[section][key] = var.get()
        save_config(config)
        update_script_callback(config)
        speak("Configuration saved and applied")
        root.destroy()

    def on_escape(event):
        if capturing_keybind[0]:
            capturing_keybind[0] = False
            root.focus_get().config(state='readonly')
            speak("Keybind capture cancelled")
        elif currently_editing[0]:
            currently_editing[0].config(state='readonly')
            currently_editing[0] = None
            speak("Cancelled editing")
        else:
            save_and_close()
        return "break"

    save_button = ttk.Button(root, text="Save and Close", command=save_and_close)
    save_button.pack(pady=10)

    def change_tab(event):
        if capturing_keybind[0] or currently_editing[0]:
            speak("Please finish editing before changing tabs")
            return "break"
        current = notebook.index(notebook.select())
        if event.state & 1:  # Shift is pressed
            next_tab = (current - 1) % notebook.index('end')
        else:
            next_tab = (current + 1) % notebook.index('end')
        notebook.select(next_tab)
        return "break"  # Prevents default tab behavior

    root.bind_all('<Up>', navigate)
    root.bind_all('<Down>', navigate)
    root.bind_all('<Return>', on_enter)
    root.bind_all('<Escape>', on_escape)
    root.bind('<Tab>', change_tab)
    root.bind('<Shift-Tab>', change_tab)
    root.bind_all('<Key>', on_key)

    def focus_first_widget():
        first_tab = notebook.tab(0, "text")
        first_widget = widgets_by_tab[first_tab][0]
        first_widget.focus_set()
        text = get_widget_text(first_widget)
        value = get_widget_value(first_widget)
        hint = get_navigation_hint(first_widget)
        speak(f"{text}, {value}, {hint}")

    def speak_controls():
        controls = [
            "Use Up and Down arrows to navigate between options",
            "Use Tab and Shift+Tab to switch between tabs",
            "Press Enter to toggle checkboxes, edit text fields, or capture keybinds",
            "When editing a text field, use Up Arrow to hear the current value",
            "Press Escape to cancel editing or save and close the configuration"
        ]
        speak(". ".join(controls))

    def force_focus():
        root.deiconify()  # Ensure the window is not minimized
        root.focus_force()  # Force focus on the window
        root.lift()  # Raise the window to the top
        focus_first_widget()
        root.after(100, speak_controls)
        root.after(100, force_focus_again)  # Call force_focus_again after 100ms

    def force_focus_again():
        root.focus_force()  # Force focus on the window again
        speak("Configuration window is now focused")

    root.protocol("WM_DELETE_WINDOW", save_and_close)  # Handle window close button

    root.after(100, force_focus)

    root.mainloop()

if __name__ == "__main__":
    # This is just for testing. In the actual implementation, 
    # you would pass the real update_script function from FA11y.py
    def dummy_update_script(config):
        print("Updating script with new configuration:")
        for section in config.sections():
            print(f"[{section}]")
            for key, value in config.items(section):
                print(f"{key} = {value}")
        print("Script updated!")

    create_config_gui(dummy_update_script)
