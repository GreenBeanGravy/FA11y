import tkinter as tk
import pyautogui
from accessible_output2.outputs.auto import Auto
from lib.player_location import find_player_icon_location
from lib.utilities import force_focus_window

speaker = Auto()

def speak_element(text):
    spoken_text = text.replace("POI", "P O I")
    speaker.speak(spoken_text)

def smooth_move_and_click(x, y, duration=0.05):
    pyautogui.moveTo(x, y, duration=duration)
    pyautogui.click()

def create_custom_poi_gui():
    coordinates = find_player_icon_location()
    if not coordinates:
        speaker.speak("Unable to determine player location for custom POI")
        return

    root = tk.Tk()
    root.title("Enter custom POI name")
    root.attributes('-topmost', True)
    
    speak_element("Enter custom P O I name")
    
    label = tk.Label(root, text="Enter POI Name:")
    label.pack(pady=5)
    speak_element("Enter P O I Name")
    
    name_entry = tk.Entry(root)
    name_entry.pack(pady=5)
    
    def on_key_press(event):
        if event.char:
            speak_element(event.char)
    
    name_entry.bind('<KeyPress>', on_key_press)
    
    def save_poi():
        poi_name = name_entry.get().strip()
        if poi_name:
            with open('CUSTOM_POI.txt', 'a') as file:
                file.write(f"{poi_name},{coordinates[0]},{coordinates[1]}\n")
            speak_element(f"Custom P O I {poi_name} saved")
            root.destroy()
            # Perform a smooth move and click to refocus on the Fortnite window
            smooth_move_and_click(pyautogui.position()[0], pyautogui.position()[1])
        else:
            speak_element("Please enter a name for the P O I")
    
    def on_enter(event):
        save_poi()
    
    def on_up_arrow(event):
        content = name_entry.get()
        speak_element(content if content else "Text box is empty")
    
    def on_tab(event):
        focused = root.focus_get()
        if focused == name_entry:
            save_button.focus_set()
            speak_element("Save P O I button")
        else:
            name_entry.focus_set()
            speak_element("P O I Name entry field")
        return "break"  # Prevents default tab behavior
    
    save_button = tk.Button(root, text="Save POI", command=save_poi)
    save_button.pack(pady=10)
    
    root.bind('<Return>', on_enter)
    root.bind('<Up>', on_up_arrow)
    root.bind('<Tab>', on_tab)
    
    def on_escape(event):
        speak_element("Cancelling Custom P O I creation")
        root.destroy()
    
    root.bind('<Escape>', on_escape)
    
    root.geometry("300x150")
    
    root.after(100, lambda: force_focus_window(root, "P O I Name entry field", name_entry))

    root.mainloop()