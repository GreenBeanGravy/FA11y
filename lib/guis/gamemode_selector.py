import tkinter as tk
import time
import pyautogui
import os
from accessible_output2.outputs.auto import Auto
from functools import partial

speaker = Auto()

GAMEMODES_FOLDER = "GAMEMODES"

def speak(s):
    speaker.speak(s)

def delayed_speak(s):
    time.sleep(0.2)
    speak(s)

def smooth_move_and_click(x, y, duration=0.04):
    pyautogui.moveTo(x, y, duration=duration)
    pyautogui.click()

def load_gamemodes():
    gamemodes = []
    if not os.path.exists(GAMEMODES_FOLDER):
        print(f"'{GAMEMODES_FOLDER}' folder not found. Creating it.")
        os.makedirs(GAMEMODES_FOLDER)
        return gamemodes

    for filename in os.listdir(GAMEMODES_FOLDER):
        if filename.endswith(".txt"):
            try:
                with open(os.path.join(GAMEMODES_FOLDER, filename), 'r') as file:
                    lines = file.readlines()
                    if len(lines) >= 2:
                        gamemode_name = filename[:-4]  # Remove .txt extension
                        gamemode_text = lines[0].strip()
                        team_sizes = lines[1].strip().split(',')
                        gamemodes.append((gamemode_name, gamemode_text, team_sizes))
            except Exception as e:
                print(f"Error reading {filename}: {str(e)}")
    return gamemodes

def select_gamemode(gamemode):
    # Click on game mode selection
    smooth_move_and_click(172, 67)
    time.sleep(0.5)

    # Click at 900, 200
    smooth_move_and_click(900, 200)
    time.sleep(0.1)  # Wait 100ms before clearing the field

    # Clear the field using backspace - improved method
    pyautogui.typewrite('\b' * 50, interval=0.01)

    # Type the new gamemode
    pyautogui.write(gamemode[1])
    pyautogui.press('enter')

    # Wait for white pixel with a 5-second timeout
    start_time = time.time()
    while not pyautogui.pixelMatchesColor(84, 328, (255, 255, 255)):
        if time.time() - start_time > 5:
            speaker.speak("Timed out waiting for game mode to load.")
            return False
        time.sleep(0.1)
    time.sleep(0.1)

    # Click on game mode
    smooth_move_and_click(300, 515)
    time.sleep(0.7)

    # Click on play button
    smooth_move_and_click(285, 910)
    time.sleep(0.5)

    # Press 'B' twice
    pyautogui.press('b')
    time.sleep(0.05)
    pyautogui.press('b')

    speaker.speak(f"{gamemode[0]} selected")
    return True

def select_gamemode_tk():
    gamemodes = load_gamemodes()

    if not gamemodes:
        speak("No game modes available. Please add game mode files to the GAMEMODES folder.")
        return

    root = tk.Tk()
    root.title("Gamemode Selector")
    root.attributes('-topmost', True)
    
    buttons_frame = tk.Frame(root)
    buttons_frame.pack()

    def select_gamemode_action(gamemode):
        root.destroy()
        if select_gamemode(gamemode):
            return
        speak("Failed to select gamemode. Please try again.")

    buttons = []
    for gamemode in gamemodes:
        button = tk.Button(buttons_frame, text=gamemode[0], command=partial(select_gamemode_action, gamemode))
        button.pack()
        buttons.append(button)

    def navigate(event):
        focused = root.focus_get()
        if focused in buttons:
            current = buttons.index(focused)
            next_index = (current + (1 if event.keysym == 'Down' else -1)) % len(buttons)
        else:
            next_index = 0
        buttons[next_index].focus_set()
        speak(buttons[next_index]['text'])

    def on_return(event):
        focused = root.focus_get()
        if isinstance(focused, tk.Button):
            select_gamemode_action(gamemodes[buttons.index(focused)])

    def on_escape(event):
        speak("Closing gamemode selector")
        root.destroy()

    root.bind('<Up>', navigate)
    root.bind('<Down>', navigate)
    root.bind('<Return>', on_return)
    root.bind('<Escape>', on_escape)

    if buttons:
        buttons[0].focus_set()
        root.after(100, lambda: delayed_speak(buttons[0]['text']))

    root.update()
    root.deiconify()
    root.lift()
    root.focus_force()
    root.mainloop()

if __name__ == "__main__":
    select_gamemode_tk()