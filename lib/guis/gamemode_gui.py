"""
Gamemode selector GUI for FA11y
Provides interface for selecting game modes
"""
import os
import time
import logging
import tkinter as tk
from tkinter import ttk
from typing import List, Tuple, Optional, Callable, Dict

from lib.guis.base_ui import AccessibleUI
from lib.utils.utilities import force_focus_window
import pyautogui

# Initialize logger
logger = logging.getLogger(__name__)

# Constants
GAMEMODES_FOLDER = "gamemodes"

class GamemodeGUI(AccessibleUI):
    """Gamemode selector GUI"""
    
    def __init__(self):
        """Initialize the gamemode selector GUI"""
        super().__init__(title="Gamemode Selector")
        
        # Load available gamemodes
        self.gamemodes = self.load_gamemodes()
        
        # Setup UI components
        self.setup()
    
    def setup(self) -> None:
        """Set up the gamemode selector GUI"""
        # Add gamemodes tab
        self.add_tab("Gamemodes")
        
        # Create search button at the top
        self.create_search_button()
        
        # Create gamemode buttons
        self.create_gamemode_buttons()
        
        # Window initialization
        self.root.resizable(False, False)
        
        # Initialize focus
        self.root.after(100, lambda: force_focus_window(
            self.root,
            "",
            self.focus_first_widget
        ))
    
    def load_gamemodes(self) -> List[Tuple[str, str, List[str]]]:
        """Load gamemode configurations from the gamemodes folder
        
        Returns:
            list: List of (gamemode_name, display_text, team_sizes) tuples
        """
        gamemodes = []
        
        # Path to the gamemodes folder
        gamemodes_path = GAMEMODES_FOLDER
        logger.info(f"Looking for gamemodes in: {gamemodes_path}")
        
        # Create gamemodes folder if it doesn't exist
        if not os.path.exists(gamemodes_path):
            logger.info(f"'{gamemodes_path}' folder not found. Creating it.")
            os.makedirs(gamemodes_path, exist_ok=True)
            # No need to return here - we'll check for files after creating
        
        try:
            # List all files in the directory
            files = os.listdir(gamemodes_path)
            logger.info(f"Found {len(files)} files in gamemodes directory: {files}")
            
            # Parse gamemode files
            for filename in files:
                if filename.endswith(".txt"):
                    try:
                        file_path = os.path.join(gamemodes_path, filename)
                        with open(file_path, 'r', encoding='utf-8') as file:
                            lines = file.readlines()
                            if len(lines) >= 2:
                                gamemode_name = filename[:-4]
                                gamemode_text = lines[0].strip()
                                team_sizes = lines[1].strip().split(',')
                                gamemodes.append((gamemode_name, gamemode_text, team_sizes))
                                logger.info(f"Loaded gamemode: {gamemode_name}, text: {gamemode_text}, team sizes: {team_sizes}")
                            else:
                                logger.warning(f"Gamemode file {filename} has fewer than 2 lines")
                    except Exception as e:
                        logger.error(f"Error reading {filename}: {str(e)}")
        except Exception as e:
            logger.error(f"Error accessing gamemodes directory: {str(e)}")
        
        logger.info(f"Loaded {len(gamemodes)} gamemodes")
        return gamemodes
    
    def create_search_button(self) -> None:
        """Create the custom gamemode search button"""
        search_button = ttk.Button(
            self.tabs["Gamemodes"],
            text="Search Custom Gamemode",
            command=self.search_gamemode
        )
        search_button.pack(fill='x', padx=5, pady=5)
        search_button.custom_speech = "Search Custom Gamemode"
        self.widgets["Gamemodes"].append(search_button)
    
    def create_gamemode_buttons(self) -> None:
        """Create buttons for available gamemodes"""
        for gamemode in self.gamemodes:
            button = ttk.Button(
                self.tabs["Gamemodes"],
                text=gamemode[0],
                command=lambda gm=gamemode: self.select_gamemode_action(gm)
            )
            button.pack(fill='x', padx=5, pady=5)
            button.custom_speech = gamemode[0]
            self.widgets["Gamemodes"].append(button)
    
    def search_gamemode(self) -> None:
        """Open a search dialog for custom gamemodes"""
        self.speak("Enter gamemode text to search")
        
        # Create search window
        search_window = tk.Toplevel(self.root)
        search_window.title("Search Gamemode")
        search_window.attributes('-topmost', True)
        
        # Create search entry
        entry = ttk.Entry(search_window)
        entry.pack(padx=5, pady=5)
        
        # Define close function
        def close_search():
            search_window.destroy()
            self.root.focus_force()
            self.widgets["Gamemodes"][0].focus_set()  # Focus search button
        
        # Bind escape key to close
        search_window.bind('<Escape>', lambda e: close_search())
        entry.bind('<Escape>', lambda e: close_search())
        
        # Key handling
        def on_key(event):
            if event.keysym == 'BackSpace':
                current_text = entry.get()
                if current_text:
                    self.speak(current_text[-1])
            elif event.keysym == 'Up':
                current_text = entry.get()
                self.speak(current_text if current_text else "blank")
                return "break"
            elif event.char and ord(event.char) >= 32:
                self.speak(event.char)
        
        # Focus handling
        def on_focus(event):
            self.speak("Search box, edit, blank")
            
        # Bind events
        entry.bind('<Key>', on_key)
        entry.bind('<FocusIn>', on_focus)
        entry.bind('<Up>', lambda e: "break")
        entry.bind('<Down>', lambda e: "break")
        
        # Set initial focus
        entry.focus_set()

        # Search submission handling
        def on_search_submit(event=None):
            search_text = entry.get()
            if search_text:
                search_window.destroy()
                self.root.destroy()
                success = self.select_gamemode((search_text, search_text, []))
                if success:
                    self.speak(f"{search_text} selected, Press 'P' to ready up!")
                else:
                    self.speak("Failed to select gamemode. Please try again.")

        # Bind enter key to submit
        search_window.bind('<Return>', on_search_submit)
    
    def smooth_move_and_click(self, x: int, y: int, duration: float = 0.04) -> None:
        """Move to a position and click smoothly
        
        Args:
            x: X coordinate
            y: Y coordinate
            duration: Movement duration
        """
        pyautogui.moveTo(x, y, duration=duration)
        pyautogui.click()
    
    def select_gamemode(self, gamemode: Tuple[str, str, List[str]]) -> bool:
        """Select a gamemode by automating UI interactions
        
        Args:
            gamemode: Gamemode data tuple
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Click game selector
            self.smooth_move_and_click(109, 67)
            time.sleep(0.5)
            
            # Click search box
            self.smooth_move_and_click(1280, 200)
            time.sleep(0.1)
            
            # Clear search box and enter gamemode text
            pyautogui.typewrite('\b' * 50, interval=0.01)
            pyautogui.write(gamemode[1])
            pyautogui.press('enter')

            # Wait for white pixel to appear (loading indicator)
            start_time = time.time()
            while not pyautogui.pixelMatchesColor(135, 401, (255, 255, 255)):
                if time.time() - start_time > 5:
                    return False
                time.sleep(0.1)
            time.sleep(0.1)

            # Click to select
            self.smooth_move_and_click(257, 527)
            time.sleep(0.7)
            self.smooth_move_and_click(285, 910)
            time.sleep(0.5)
            
            # Press 'b' twice to exit menus
            pyautogui.press('b', presses=2, interval=0.05)
            return True
            
        except Exception as e:
            logger.error(f"Error selecting gamemode: {str(e)}")
            return False
    
    def select_gamemode_action(self, gamemode: Tuple[str, str, List[str]]) -> None:
        """Handle gamemode selection action
        
        Args:
            gamemode: Gamemode data tuple
        """
        self.root.destroy()
        success = self.select_gamemode(gamemode)
        if success:
            self.speak(f"{gamemode[0]} selected, Press 'P' to ready up!")
        else:
            self.speak("Failed to select gamemode. Please try again.")
    
    def focus_first_widget(self) -> None:
        """Focus the first widget and announce its state"""
        if self.widgets["Gamemodes"]:
            first_widget = self.widgets["Gamemodes"][0]
            first_widget.focus_set()
            widget_info = self.get_widget_info(first_widget)
            if widget_info:
                self.speak(widget_info)


def launch_gamemode_selector() -> None:
    """Launch the gamemode selector GUI"""
    try:
        gui = GamemodeGUI()
        gui.run()
    except Exception as e:
        logger.error(f"Error launching gamemode selector GUI: {e}")
