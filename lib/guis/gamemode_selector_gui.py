from lib.guis.AccessibleUIBackend import AccessibleUIBackend
import time
import pyautogui
import os
from lib.utilities import force_focus_window
from typing import List, Tuple, Optional

GAMEMODES_FOLDER = "gamemodes"

def smooth_move_and_click(x: int, y: int, duration: float = 0.04) -> None:
    """Smoothly move to coordinates and click.
    
    Args:
        x: X coordinate
        y: Y coordinate
        duration: Movement duration in seconds
    """
    pyautogui.moveTo(x, y, duration=duration)
    pyautogui.click()

def load_gamemodes() -> List[Tuple[str, str, List[str]]]:
    """Load gamemode configurations from the gamemodes folder.
    
    Returns:
        List of tuples containing (name, gamemode_text, team_sizes)
    """
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
                        gamemode_name = filename[:-4]  # Remove .txt extension
                        gamemode_text = lines[0].strip()
                        team_sizes = lines[1].strip().split(',')
                        gamemodes.append((gamemode_name, gamemode_text, team_sizes))
            except Exception as e:
                print(f"Error reading {filename}: {str(e)}")
    return gamemodes

def select_gamemode(gamemode: Tuple[str, str, List[str]]) -> bool:
    """Perform the gamemode selection sequence.
    
    Args:
        gamemode: Tuple containing (name, gamemode_text, team_sizes)
    
    Returns:
        bool: True if selection was successful, False otherwise
    """
    try:
        # Click gamemode selection
        smooth_move_and_click(109, 67)
        time.sleep(0.5)

        # Click search field
        smooth_move_and_click(1280, 200)
        time.sleep(0.1)

        # Clear and enter new gamemode
        pyautogui.typewrite('\b' * 50, interval=0.01)
        pyautogui.write(gamemode[1])
        pyautogui.press('enter')

        # Wait for white pixel indicator
        start_time = time.time()
        while not pyautogui.pixelMatchesColor(123, 327, (255, 255, 255)):
            if time.time() - start_time > 5:
                return False
            time.sleep(0.1)
        time.sleep(0.1)

        # Complete selection sequence
        smooth_move_and_click(250, 436)
        time.sleep(0.7)
        smooth_move_and_click(285, 910)
        time.sleep(0.5)

        # Exit menus
        pyautogui.press('b', presses=2, interval=0.05)
        return True
        
    except Exception as e:
        print(f"Error selecting gamemode: {str(e)}")
        return False

def select_gamemode_tk() -> None:
    """Create and display the gamemode selector GUI."""
    gamemodes = load_gamemodes()

    if not gamemodes:
        print("No game modes available.")
        return

    ui = AccessibleUIBackend("Gamemode Selector")
    ui.add_tab("Gamemodes")

    def select_gamemode_action(gamemode: Tuple[str, str, List[str]]) -> None:
        """Handle gamemode selection and provide feedback.
        
        Args:
            gamemode: Tuple containing (name, gamemode_text, team_sizes)
        """
        ui.root.destroy()
        success = select_gamemode(gamemode)
        if not success:
            ui.speak("Failed to select gamemode. Please try again.")
        else:
            ui.speak(f"{gamemode[0]} selected")

    # Add buttons for each gamemode
    for gamemode in gamemodes:
        ui.add_button(
            "Gamemodes",
            gamemode[0],
            lambda gm=gamemode: select_gamemode_action(gm),
            custom_speech=gamemode[0]
        )

    # Set up initial focus
    def focus_first_widget() -> None:
        """Focus and announce the first gamemode."""
        if ui.widgets["Gamemodes"]:
            first_widget = ui.widgets["Gamemodes"][0]
            first_widget.focus_set()
            ui.speak(first_widget['text'])
        else:
            ui.speak("No game modes available")

    # Initialize window with no announcement
    ui.root.after(100, lambda: force_focus_window(
        ui.root,
        "",
        focus_first_widget
    ))

    ui.run()
