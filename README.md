# FA11y: Fortnite Accessibility Tool for Blind Players

## About
FA11y aims to make many important elements of Fortnite accessible to blind and visually impaired players. With FA11y, you can:

- Get directions to Points of Interest (POIs) and place an audible, stereo marker on them!
- Check your available Health and Shields!
- Check the rarity of selected weapons in your inventory!
- Get directions to the Safe Zone, away from the number one killer of blind players, the storm!
- Get directions to seasonal POIs, and even set your own custom POIs!
- Get your height while skydiving in real time!
- Install and verify Fortnite accessibly!
- Launch Fortnite accessibly in either performance mode or Direct X 11!
- Select game modes easily with an accessible interface!
- Customize most FA11y settings through an accessible configuration menu!

## DEFAULT Keybinds (configurable to your liking!)

- **`]` (Right Bracket)**: Open the POI selection menu
- **`Tab` / `Shift + Tab`**: Cycle between GAME POIs, CUSTOM POIs, and GAME OBJECTS within the POI selection menu
- **`Enter` / `Space`**: Select a POI in the menu
- **`Up Arrow` / `Down Arrow`**: Navigate through the POI menu
- **`[` (Left Bracket)**: Check the rarity of the currently selected item in your inventory
- **`H`**: Check your Health and Shields
- **`` ` `` (Grave Accent / Backtick)**: Run player icon detection on the map to give directions to the selected POI, and with AutoTurn enabled, automatically face the POI!
- **``Shift + ` `` (Shift + Grave Accent / Backtick)**: Create a new custom POI at your current location
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

## Installation
1. Ensure you have Python 3.9 or later installed. Make sure to check the box to "Add Python to PATH" during installation.
2. Download the latest release of FA11y.
3. Extract the folder to a location of your choice. Avoid placing it inside the Fortnite directory or any system folders.
4. Open the folder and run `updater.py`. Wait for it to complete.
5. You should now be able to run `FA11y.py` without issues.
6. Optional: Configure your FA11y settings and keybinds by pressing `F10` when FA11y has started!

## Usage

### POI and Safe Zone Directions
- In-game, press `M` to open your map.
- If you haven't already, open the POI Selector by pressing the `]` (Right Bracket) key, and select where you want to go.
- While the map is open, press the `` ` `` (Grave Accent / Backtick) key to get directions to the POI you just selected.

### Create a Custom POI
- In-game, press `M` to open your map.
- While the map is open, press ``Shift + ` `` (Shift + Grave Accent / Backtick).
- Give a name to your new POI, and voila!

### Health and Shield
- In-game, press `H` to check your health and shield values. This also works while spectating other players to view their Health and Shields.

### Weapon Rarity
- In-game, open your inventory using the `I` key.
- Press `[` (Left Bracket) to check the rarity of your currently selected weapon.
- Use left and right arrow keys to navigate between items, starting on the first item in your inventory.

### Mouse Keys
- With NumLock on, use the NumPad keys to control the mouse in-game.
- Default settings are listed in the keybinds section above.

### Player Direction
- Press `;` (Semicolon) to hear the direction you are currently facing.

### Game Mode Selection
- Press `'` (Apostrophe) to open the game mode selection menu.
- Use arrow keys to navigate and Enter to select. Wait for confirmation that the gamemode has been selected.

### Configuration
- Press `F9` to open the configuration menu.
- Configuration menu navigation tips and keybinds are provided when you open the menu.

## Customization
- Use the configuration menu (F10) to adjust settings and keybinds to your preferences.
- You can add custom game modes by creating text files in the `GAMEMODES` folder (advanced users).

## Features
- Automatic updates
- Desktop shortcut creation
- Accessible Fortnite installation and verification
- Performance mode and DirectX 11 launching options
- Real-time player height announcements while skydiving
- Detection of various game objects (e.g., quest icons, storm towers, reboot cards and vans..)
- Customizable turn sensitivity
- Much more!

## Upcoming Features
- Elimination count tracking
- Players remaining in match
- Battle Bus jump timing assistant
- Full Fortnite GUI access
- Game settings management and sharing
- Stereo audio feedback aim assist

Enjoy playing Fortnite with enhanced accessibility!
