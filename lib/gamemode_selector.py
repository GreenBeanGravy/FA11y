import os
import time
import pyautogui
from accessible_output2.outputs.auto import Auto

speaker = Auto()

GAMEMODES_FOLDER = "GAMEMODES"

def load_gamemodes():
    gamemodes = []
    for filename in os.listdir(GAMEMODES_FOLDER):
        if filename.endswith(".txt"):
            with open(os.path.join(GAMEMODES_FOLDER, filename), 'r') as file:
                lines = file.readlines()
                if len(lines) >= 2:
                    gamemode_name = filename[:-4]  # Remove .txt extension
                    gamemode_text = lines[0].strip()
                    team_sizes = lines[1].strip().split(',')
                    gamemodes.append((gamemode_name, gamemode_text, team_sizes))
    return gamemodes

def select_gamemode(gamemode):
    # Check if in Fortnite Lobby
    if pyautogui.pixelMatchesColor(1310, 1012, (149, 18, 19), tolerance=15):
        speaker.speak("Please ensure that you are in the Fortnite Lobby.")
        return

    # Click on game mode selection
    pyautogui.click(172, 67)
    time.sleep(0.5)

    # Type and enter game mode
    pyautogui.write(gamemode[1])
    pyautogui.press('enter')

    # Wait for white pixel
    while not pyautogui.pixelMatchesColor(84, 328, (255, 255, 255)):
        time.sleep(0.1)
    time.sleep(0.1)

    # Click on game mode
    pyautogui.click(300, 515)
    time.sleep(0.15)

    # Click on play button
    pyautogui.click(285, 910)
    time.sleep(0.25)

    # Press 'B' twice
    pyautogui.press('b')
    time.sleep(0.05)
    pyautogui.press('b')

    speaker.speak(f"{gamemode[0]} selected")