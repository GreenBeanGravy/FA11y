# FA11y: Fortnite Accessibility Tool for Blind Players

## About
FA11y aims to make many important elements of Fortnite accessible to blind players. With FA11y, you can:

- Get directions to Points of Interest (POIs) and place a marker on them
- Read how much Health and Shield you have
- Check the rarity of weapons in your inventory
- Get directions to the Safe Zone, away from the number one killer of blind players, the storm!
- Much, much, much more!

## DEFAULT Keybinds

- **`]` (Right Bracket)**: Open the POI selection menu
- `` TAB `` + `` SHIFT + TAB ``: Cycles between GAME POIs, CUSTOM POIs, and GAME OBJECTS within the POI selection menu.
- **`Enter` / `Space`**: Select a POI in the menu
- **`Up Arrow` / `Down Arrow`**: Navigate through the POI menu
- **`[` (Left Bracket)**: Check the rarity of the currently selected item in your inventory. Use the left and right arrow keys to navigate between items.
- **`H`**: Invoke health and shield detection
- **`` ` `` (Grave Accent / Backtick)**: Run icon detection to give directions to the selected POI
- **``Shift + ` `` (Shift + Grave Accent / Backtick)**: Create a new custom POI at your current location.
- **`Left Control`**: Left clicks
- **`Right Control`**: Right clicks
- **`Num5`**: Recenter the camera
- **`Num4`**: Turns slightly left
- **`Num1`**: Turns left
- **`Num6`**: Turns slightly right
- **`Num3`**: Turns right
- **`Num8`**: Looks up
- **`Num2`**: Looks down
- **`Num0`**: Turns 180 degrees
- **`Num7`**: Scrolls up
- **`Num9`**: Scrolls down

## Installation
First, you'll need any version of Python 3.9 installed. MAKE SURE you check the box to "add Python to Path" during installation!

1. Download the latest release.
2. Extract and place the folder anywhere. Make sure you do not place the folder inside of the Fortnite directory, or inside of any System Folders.
3. Open the folder, and run `installer.py`. Wait until it closes to proceed.
4. Viola! You should now be able to run `FA11y.py` with no issues.
5. Optional: Add your own Points of Interest (POIs) in `CUSTOM_POI.txt`

## Usage

### POI and Safe Zone directions
- While in-game, press `M` to open your map.
- While the map is open, press the `` ` `` (Grave Accent / Backtick) key.

### Create a custom POI
- While in-game, press `M` to open your map.
- While the map is open, press the key combo ``Shift + ` `` (Shift + Grave Accent / Backtick) key.

### Health and Shield
- While in-game, simply press `H` to check your health and shield values.

### Rarity
- While in-game, open your inventory using the `I` key. 
- Press your `[` (Left Bracket) key to check the rarity of your currently selected weapon. You can change the selected weapon using the left and right arrow keys.

### Mouse Keys
- While NumLock is on, use the NumPad arrow keys to move the mouse around in game, currently using a sensitivity made for the default Fortnite values.
- By default, 4 turns slightly left, 1 turns left, 8 turns up, 6 turns slightly right, 3 turns right, 2 turns down, 0 turns you 180 degrees, 5 recenters the camera, 9 invokes a scroll-down, and 7 invokes a scroll-up.
- Edit the `config.txt` file to toggle the Mouse Keys on and off by changing the variable `MouseKeys` to True/False.

## Upcoming Features, the farther down you go the better it gets!
- Your height off the ground while skydiving.
- The amount of eliminations you have.
- The amount of players remaining in a match.
- Other important map icons, such as combat caches, radar towers, supply drops, etc.
- A system that will notify you when to jump from the Battle Bus in order to take the shortest distance possible to your currently selected POI.
- More expansion on how you look around, ~~the ability to toggle this feature~~, change keybinds, change sensitivity, everything!
- Full Fortnite GUI access.
- The ability to change all of your keybinds and the ability to apply and share your keybinds with others!
- The ability to change every game setting, including applying and sharing presets!
- Full stereo audio feedback aim assist.
