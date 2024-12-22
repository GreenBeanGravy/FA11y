from tkinter import ttk
import tkinter as tk
import os
import time
from typing import List, Tuple

from lib.guis.AccessibleUIBackend import AccessibleUIBackend
from lib.utilities import force_focus_window
import pyautogui

GAMEMODES_FOLDER = "gamemodes"

def load_gamemodes() -> List[Tuple[str, str, List[str]]]:
    """Load gamemode configurations from the gamemodes folder."""
    gamemodes = []
    
    if not os.path.exists(GAMEMODES_FOLDER):
        print(f"'{GAMEMODES_FOLDER}' folder not found. Creating it.")
        os.makedirs(GAMEMODES_FOLDER)
        return gamemodes

    for filename in os.listdir(GAMEMODES_FOLDER):
        if filename.endswith(".txt"):
            try:
                with open(os.path.join(GAMEMODES_FOLDER, filename), 'r', encoding='utf-8') as file:
                    lines = file.readlines()
                    if len(lines) >= 2:
                        gamemode_name = filename[:-4]
                        gamemode_text = lines[0].strip()
                        team_sizes = lines[1].strip().split(',')
                        gamemodes.append((gamemode_name, gamemode_text, team_sizes))
            except Exception as e:
                print(f"Error reading {filename}: {str(e)}")
    return gamemodes

def select_gamemode_tk() -> None:
    """Create and display the gamemode selector GUI."""
    ui = AccessibleUIBackend("Gamemode Selector")
    ui.add_tab("Gamemodes")

    def smooth_move_and_click(x: int, y: int, duration: float = 0.04) -> None:
        pyautogui.moveTo(x, y, duration=duration)
        pyautogui.click()

    def select_gamemode(gamemode: Tuple[str, str, List[str]]) -> bool:
        try:
            smooth_move_and_click(109, 67)
            time.sleep(0.5)
            smooth_move_and_click(1280, 200)
            time.sleep(0.1)
            pyautogui.typewrite('\b' * 50, interval=0.01)
            pyautogui.write(gamemode[1])
            pyautogui.press('enter')

            start_time = time.time()
            while not pyautogui.pixelMatchesColor(135, 401, (255, 255, 255)):
                if time.time() - start_time > 5:
                    return False
                time.sleep(0.1)
            time.sleep(0.1)

            smooth_move_and_click(257, 527)
            time.sleep(0.7)
            smooth_move_and_click(285, 910)
            time.sleep(0.5)
            pyautogui.press('b', presses=2, interval=0.05)
            return True
            
        except Exception as e:
            print(f"Error selecting gamemode: {str(e)}")
            return False

    def select_gamemode_action(gamemode: Tuple[str, str, List[str]]) -> None:
        ui.root.destroy()
        success = select_gamemode(gamemode)
        if success:
            ui.speak(f"{gamemode[0]} selected, Press 'P' to ready up!")
        else:
            ui.speak("Failed to select gamemode. Please try again.")

    def search_gamemode():
        ui.speak("Enter gamemode text to search")
        search_window = tk.Toplevel(ui.root)
        search_window.title("Search Gamemode")
        search_window.attributes('-topmost', True)
        
        entry = ttk.Entry(search_window)
        entry.pack(padx=5, pady=5)
        
        def close_search():
            search_window.destroy()
            ui.root.focus_force()
            search_button.focus_set()
            
        search_window.bind('<Escape>', lambda e: close_search())
        entry.bind('<Escape>', lambda e: close_search())
        
        def on_key(event):
            if event.keysym == 'BackSpace':
                current_text = entry.get()
                if current_text:
                    ui.speak(current_text[-1])
            elif event.keysym == 'Up':
                current_text = entry.get()
                ui.speak(current_text if current_text else "blank")
                return "break"
            elif event.char and ord(event.char) >= 32:
                ui.speak(event.char)
                
        def on_focus(event):
            ui.speak("Search box, edit, blank")
            
        entry.bind('<Key>', on_key)
        entry.bind('<FocusIn>', on_focus)
        entry.bind('<Up>', lambda e: "break")
        entry.bind('<Down>', lambda e: "break")
        entry.focus_set()

        def on_search_submit(event=None):
            search_text = entry.get()
            if search_text:
                search_window.destroy()
                ui.root.destroy()
                success = select_gamemode((search_text, search_text, []))
                if success:
                    ui.speak(f"{search_text} selected, Press 'P' to ready up!")
                else:
                    ui.speak("Failed to select gamemode. Please try again.")

        search_window.bind('<Return>', on_search_submit)    # Add search button at the top
    search_button = ttk.Button(ui.tabs["Gamemodes"],
                             text="Search Custom Gamemode",
                             command=search_gamemode)
    search_button.pack(fill='x', padx=5, pady=5)
    search_button.custom_speech = "Search Custom Gamemode"
    ui.widgets["Gamemodes"].append(search_button)

    # Add regular gamemode buttons
    gamemodes = load_gamemodes()
    for gamemode in gamemodes:
        button = ttk.Button(ui.tabs["Gamemodes"],
                          text=gamemode[0],
                          command=lambda gm=gamemode: select_gamemode_action(gm))
        button.pack(fill='x', padx=5, pady=5)
        button.custom_speech = gamemode[0]
        ui.widgets["Gamemodes"].append(button)

    ui.root.resizable(False, False)
    ui.root.protocol("WM_DELETE_WINDOW", ui.save_and_close)

    def focus_first_widget():
        if ui.widgets["Gamemodes"]:
            first_widget = ui.widgets["Gamemodes"][0]
            first_widget.focus_set()
            widget_info = ui.get_widget_info(first_widget)
            if widget_info:
                ui.speak(widget_info)

    ui.root.after(100, lambda: force_focus_window(
        ui.root,
        "",
        focus_first_widget
    ))

    ui.run()
