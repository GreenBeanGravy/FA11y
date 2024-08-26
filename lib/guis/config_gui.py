import tkinter as tk
from tkinter import ttk
import configparser
from accessible_output2.outputs.auto import Auto
import os
import re
import win32api
import win32con
from lib.utilities import force_focus_window, get_config_int, get_config_float, get_config_value, get_config_boolean


speaker = Auto()

CONFIG_FILE = 'config.txt'

def speak(text):
    speaker.speak(text)

def load_config():
    config = configparser.ConfigParser()
    config.optionxform = str  # This preserves the case of the keys
    config.read(CONFIG_FILE)
    return config

def save_config(config):
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)

VK_NUMPAD = {
    'num 0': win32con.VK_NUMPAD0,
    'num 1': win32con.VK_NUMPAD1,
    'num 2': win32con.VK_NUMPAD2,
    'num 3': win32con.VK_NUMPAD3,
    'num 4': win32con.VK_NUMPAD4,
    'num 5': win32con.VK_NUMPAD5,
    'num 6': win32con.VK_NUMPAD6,
    'num 7': win32con.VK_NUMPAD7,
    'num 8': win32con.VK_NUMPAD8,
    'num 9': win32con.VK_NUMPAD9,
    'num period': win32con.VK_DECIMAL,
    'num .': win32con.VK_DECIMAL,
    'num +': win32con.VK_ADD,
    'num -': win32con.VK_SUBTRACT,
    'num *': win32con.VK_MULTIPLY,
    'num /': win32con.VK_DIVIDE,
}

SPECIAL_KEYS = {
    'lctrl': win32con.VK_LCONTROL,
    'rctrl': win32con.VK_RCONTROL,
    'lshift': win32con.VK_LSHIFT,
    'rshift': win32con.VK_RSHIFT,
    'lalt': win32con.VK_LMENU,
    'ralt': win32con.VK_RMENU,
    'f1': win32con.VK_F1,
    'f2': win32con.VK_F2,
    'f3': win32con.VK_F3,
    'f4': win32con.VK_F4,
    'f5': win32con.VK_F5,
    'f6': win32con.VK_F6,
    'f7': win32con.VK_F7,
    'f8': win32con.VK_F8,
    'f9': win32con.VK_F9,
    'f10': win32con.VK_F10,
    'f11': win32con.VK_F11,
    'f12': win32con.VK_F12,
    'tab': win32con.VK_TAB,
    'capslock': win32con.VK_CAPITAL,
    'space': win32con.VK_SPACE,
    'backspace': win32con.VK_BACK,
    'enter': win32con.VK_RETURN,
    'esc': win32con.VK_ESCAPE,
    'insert': win32con.VK_INSERT,
    'delete': win32con.VK_DELETE,
    'home': win32con.VK_HOME,
    'end': win32con.VK_END,
    'pageup': win32con.VK_PRIOR,
    'pagedown': win32con.VK_NEXT,
    'up': win32con.VK_UP,
    'down': win32con.VK_DOWN,
    'left': win32con.VK_LEFT,
    'right': win32con.VK_RIGHT,
    'printscreen': win32con.VK_PRINT,
    'scrolllock': win32con.VK_SCROLL,
    'pause': win32con.VK_PAUSE,
    'numlock': win32con.VK_NUMLOCK,
    'bracketleft': 0xDB,    # '['
    'bracketright': 0xDD,   # ']'
    'apostrophe': 0xDE,     # '''
    'grave': 0xC0,          # '`'
    'backslash': 0xDC,      # '\'
    'semicolon': 0xBA,      # ';'
    'period': 0xBE,         # '.'
}

def is_key_pressed(key):
    key_lower = key.lower()
    if key_lower in VK_NUMPAD:
        return win32api.GetAsyncKeyState(VK_NUMPAD[key_lower]) & 0x8000 != 0
    elif key_lower in SPECIAL_KEYS:
        return win32api.GetAsyncKeyState(SPECIAL_KEYS[key_lower]) & 0x8000 != 0
    else:
        try:
            vk_code = ord(key.upper())
            return win32api.GetAsyncKeyState(vk_code) & 0x8000 != 0
        except:
            print(f"Unrecognized key: {key}. Skipping...")
            return False

def get_pressed_key():
    for key in list(VK_NUMPAD.keys()) + list(SPECIAL_KEYS.keys()) + [chr(i) for i in range(65, 91)]:  # A-Z
        if is_key_pressed(key):
            return key
    return None

def is_numeric(value):
    return re.match(r'^-?\d*\.?\d*$', value) is not None

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
    keybind_map = {}  # To keep track of which action is bound to which key

    for section in config.sections():
        for key in config[section]:
            value, description = get_config_value(config, section, key)
            
            frame = ttk.Frame(pages[section])
            frame.pack(fill='x', padx=5, pady=5)

            label = ttk.Label(frame, text=key)
            label.pack(side='left')

            if section == 'SCRIPT KEYBINDS':
                var = tk.StringVar(value=value)
                widget = ttk.Entry(frame, textvariable=var, state='readonly')
                if value:  # Only add to keybind_map if there's a value
                    keybind_map[value.lower()] = key
            elif value.lower() in ['true', 'false']:
                var = tk.BooleanVar(value=value.lower() == 'true')
                widget = ttk.Checkbutton(frame, variable=var, onvalue=True, offvalue=False)
                widget.state(['!alternate'])
                if value.lower() == 'true':
                    widget.state(['selected'])
                else:
                    widget.state(['!selected'])
            else:
                var = tk.StringVar(value=value)
                widget = ttk.Entry(frame, textvariable=var, state='readonly')
            
            widget.pack(side='right', expand=True, fill='x')
            widgets.append(widget)
            widgets_by_tab[section].append(widget)
            variables[(section, key)] = var

            # Store the description as an attribute of the widget
            widget.description = description

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
            return widget.get() or "No keybind set"
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
        description = getattr(next_widget, 'description', '')
        speak(f"{text}, {value}, {hint}. {description}")
        return "break"

    def on_keybind_focus(event, key):
        speak(f"Current keybind for {key} is {event.widget.get() or 'Not set'}. Press Enter to start capturing a new keybind.")

    def speak_help():
        controls = [
            "Use Up and Down arrows to navigate between options",
            "Use Tab and Shift+Tab to switch between tabs",
            "Press Enter to toggle checkboxes, edit text fields, or capture keybinds",
            "When editing a text field, use Up Arrow to hear the current value",
            "Press Escape to cancel editing a config entry, or to save and close the config panel",
            "When capturing a keybind, press Backspace to disable the keybind",
            "Press H at any time to hear these instructions again"
        ]
        speak(". ".join(controls))

    def capture_keybind():
        current_widget = root.focus_get()
        action_name = get_widget_text(current_widget)
        
        while True:
            key = get_pressed_key()
            if key:
                if key == 'backspace':
                    current_widget.delete(0, tk.END)
                    speak(f"Keybind for {action_name} disabled")
                    if action_name in keybind_map.values():
                        old_key = next(k for k, v in keybind_map.items() if v == action_name)
                        del keybind_map[old_key]
                else:
                    if key.lower() in keybind_map:
                        old_action = keybind_map[key.lower()]
                        if old_action != action_name:
                            speak(f"Warning: {key} was previously bound to {old_action}. That keybind has been removed.")
                            for widget in widgets:
                                if isinstance(widget, ttk.Entry) and widget.get().lower() == key.lower():
                                    widget.delete(0, tk.END)
                                    variables[(notebook.tab(notebook.select(), "text"), get_widget_text(widget))].set('')
                                    break
                    if action_name in keybind_map.values():
                        old_key = next(k for k, v in keybind_map.items() if v == action_name)
                        del keybind_map[old_key]
                    keybind_map[key.lower()] = action_name
                    current_widget.delete(0, tk.END)
                    current_widget.insert(0, key)
                    variables[(notebook.tab(notebook.select(), "text"), action_name)].set(key)
                    speak(f"Keybind for {action_name} set to {key}")
                return
            root.update()

    def on_key(event):
        if event.keysym.lower() == 'h':
            speak_help()
            return "break"
        
        if capturing_keybind[0]:
            capture_keybind()
            capturing_keybind[0] = False
            root.focus_get().config(state='readonly')
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
                    speak(f"Press any key to set the keybind for {action_name}. Press Backspace to disable this keybind. Press Escape to cancel.")
                else:
                    capturing_keybind[0] = False
                    current.config(state='readonly')
                    speak("Keybind capture cancelled")
            elif currently_editing[0] == current:
                currently_editing[0] = None
                current.config(state='readonly')
                if is_numeric(current.get()) or current.get() == "":
                    speak(f"{get_widget_text(current)} set to {current.get() or 'empty'}")
                else:
                    speak(f"Invalid input. {get_widget_text(current)} must be a number. Value not changed.")
                    current.delete(0, tk.END)
                    current.insert(0, variables[(notebook.tab(notebook.select(), "text"), get_widget_text(current))].get())
            elif not currently_editing[0]:
                currently_editing[0] = current
                current.config(state='normal')
                speak(f"Editing {get_widget_text(current)}. Current value: {current.get()}. Press Enter when done.")
        return "break"

    def save_and_close():
        for (section, key), var in variables.items():
            description = getattr(widgets[list(variables.keys()).index((section, key))], 'description', '')
            if isinstance(var, tk.BooleanVar):
                value = 'true' if var.get() else 'false'
            else:
                value = var.get()
            config[section][key] = f"{value} \"{description}\""
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
        description = getattr(first_widget, 'description', '')
        speak(f"{first_tab} tab. {text}, {value}, {hint}. {description}")

    root.after(100, lambda: force_focus_window(root, "Press H for help!", focus_first_widget))

    root.protocol("WM_DELETE_WINDOW", save_and_close)  # Handle window close button

    root.mainloop()