# FA11y: Fortnite Accessibility Tool for the blind and visually impaired!

## About
FA11y aims to make many important elements of Fortnite accessible to blind and visually impaired players. With FA11y, you can:

- Get directions to Points of Interest (POIs) and place an audible, stereo marker on them!
- Check your available Health and Shields!
- Check the rarity of selected weapons in your inventory!
- Get directions to the Safe Zone, away from the number one killer of blind players, the storm!
- Get directions to seasonal POIs!
- Get your height while skydiving in real time!
- Get the direction you are currently facing!
- Automatically turn towards a selected POI!
- Install and verify Fortnite accessibly!
- Launch Fortnite accessibly in either performance mode or Direct X 11!
- Select game modes easily with an accessible interface!
- Instantly leave the current match at the press of a button!
- Customize most FA11y settings through an accessible configuration menu!

## DEFAULT Keybinds (configurable to your liking!)

- **`]` (Right Bracket)**: Open the POI selection menu
- **`Tab` / `Shift + Tab`**: Cycle between GAME POIs and GAME OBJECTS within the POI selection menu
- **`Enter` / `Space`**: Select a POI in the menu
- **`Up Arrow` / `Down Arrow`**: Navigate through the POI menu
- **`[` (Left Bracket)**: Check the rarity of the currently selected item in your inventory
- **`H`**: Check your Health and Shields
- **`` ` `` (Grave Accent / Backtick)**: Run player icon detection on the map to give directions to the selected POI, and with AutoTurn enabled, automatically face the POI!
- **`Left Control`**: Left click
- **`Right Control`**: Right click
- **`Num5`**: Recenter the camera
- **`Num4`**: Turn slightly left
- **`Num1`**: Turn left
- **`Num6`**: Turn slightly right
- **`Num3`**: Turn right
- **`Num8`**: Look up
- **`Num2`**: Look down
- **`Num0`**: Turn 180 degrees
- **`Num7`**: Scroll up
- **`Num9`**: Scroll down
- **`;` (Semicolon)**: Speak the direction that the player is currently facing
- **`'` (Apostrophe)**: Open the gamemode selector
- **`F9`**: Open the FA11y configuration menu
- **`F12`**: Leave current match

## Setup
1. Ensure you have Python 3.9 or later installed. Make sure to check the box to "Add Python to PATH" during installation.
2. Download the latest release of FA11y.
3. Extract the folder to a location of your choice. Avoid placing it inside the Fortnite directory or any system folders.
4. Open the folder and run `updater.py`. Wait for it to complete.
5. You should now be able to run `FA11y.py` without issues.
6. Optional: Configure your FA11y settings and keybinds by pressing `F9` when FA11y has started!

## Using Legendary:
Legendary is a command line interface for the Epic Games Launcher. You won't need the Epic Games launcher installed to use Legendary. In order to install Fortnite, follow these steps:
* Open a command line window in the directory of your `"Legendary.exe"` file, which should be your root `FA11y` folder. If Legendary did not get added to your system PATH automatically, you may need to begin all commands with "`.\`". If you do NOT have `"Legendary.exe"` in your root FA11y folder, run the `"updater.py"` script.
* Once you have opened the command line window, type the command `"Legendary auth"`. This will bring up a page to log into your Epic Games account, where you will need to log in to your Epic Games account, log in with another service, or create a new account. Additionally, you may be hit with an inaccessible hCaptcha at some point during the login process. This is being worked on, but in the mean time, you may need to get sighted assistance if you DO receieve this captcha.
* If after you successfully log in, you get a screen showing raw HTML code, copy the listed authorization token, without the quotations, to your clipboard, and paste it into the command line window. Otherwise, you can ignore this.
* Assuming everything went smoothly for you, you should now be logged into Legendary! You can easily check this by running the `"Legendary auth"` command again.

## Getting Fortnite:
* Go to [the following link](https://store.epicgames.com/en-US/p/fortnite) to open the Fortnite page on the Epic Games store website, which you should now already be logged into.
* Find and click on the `"GET"` button.
* Follow the prompts that appear near the bottom of the page.
* After you successfully have added Fortnite to your Epic Games account, you can now run the `"Fortnite_Installer.py"` script found in your `FA11y` directory! While the installer is running, you can use the keybinds: `"P"` to get the last progress update, `"-"` or  `"+"` to adjust the speed of progress update announcements, and `"ESCAPE"` to cancel the entire install process.
* After the installer has completed, you can now run either of the batch files that launch Fortnite, preferably, use the `"performance_fortnite_launcher.bat"` one for best performance.
