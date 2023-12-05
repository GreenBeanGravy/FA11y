# FA11y: Fortnite Accessibility Tool for Blind Players

## About
FA11y aims to make many important elements of Fortnite accessible to blind players. With FA11y, you can:

- Get directions to Points of Interest (POIs) and place a marker on them
- Read how much Health and Shield you have
- Check the rarity of weapons in your inventory
- Get directions to the Safe Zone, away from the number one killer of blind players, the storm!

## Keybinds

- **`]` (Right Bracket)**: Open the POI selection menu
- `` TAB `` + `` SHIFT + TAB ``: Cycles between GAME POIs, CUSTOM POIs, and GAME OBJECTS within the POI selection menu.
- **`Enter` / `Space`**: Select a POI in the menu
- **`Up Arrow` / `Down Arrow`**: Navigate through the POI menu
- **`[` (Left Bracket)**: Check the rarity of the currently selected item in your inventory. Use the left and right arrow keys to navigate between items.
- **`H`**: Invoke health and shield detection
- **`` ` `` (Grave Accent / Backtick)**: Run icon detection to give directions to the selected POI
- **``Shift + ` `` (Shift + Grave Accent / Backtick)**: Create a new custom POI at your current location.

## Installation
First, you'll need Python 3.9 or later installed on your machine. MAKE SURE you check the box to "add Python to Path" during installation!

1. Download the latest release.
2. Open a CMD/Terminal window in the folder where you downloaded FA11y.
3. Install the required Python packages using the command:
    `pip install -r requirements.txt`
4. Optional: Add your own Points of Interest (POIs) in `POI.txt`

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
- While NumLock is on, use the arrow keys to move the mouse around in game, currently using a sensitivity made for the default Fortnite values.
- 4 turns left, 8 turns up, 6 turns right, 2 turns down, and 0 turns you 180 degrees.
- Edit the `config.txt` file to toggle the Mouse Keys on and off.

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
