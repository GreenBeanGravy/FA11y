# FA11y: Fortnite Accessibility Tool for Blind Players

## About
FA11y aims to make many important elements of Fortnite accessible to blind players. With FA11y, you can:

- Get directions to Points of Interest (POIs) and place a marker on them
- Read how much Health and Shield you have
- Check the rarity of weapons in your inventory
- Get directions to the Safe Zone, away from the number one killer of blind players, the storm!

## Keybinds

- **`]` (Right Bracket)**: Open the POI selection menu
- **`Enter` / `Space`**: Select a POI in the menu
- **`Up Arrow` / `Down Arrow`**: Navigate through the POI menu
- **`[` (Left Bracket)**: Check the rarity of the currently selected item in your inventory. Use the left and right arrow keys to navigate between items.
- **`H`**: Invoke health and shield detection
- **`` ` `` (Grave Accent / Backtick)**: Run icon detection to give directions to the selected POI

## Installation
First, you'll need Python 3.9 or later installed on your machine.

1. Download the latest release.
2. Open a CMD/Terminal window in the folder where you downloaded FA11y.
3. Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```
4. Optional: Add your own Points of Interest (POIs) in `POI.txt`

## Usage

### POI and Safe Zone directions
- While in-game, press `M` to open your map.
- While the map is open, press the `` ` `` (Grave Accent / Backtick) key.

### Health and Shield
- While in-game, simply press `H` to check your health and shield values.

### Rarity
- While in-game, open your inventory using the `I` key. 
- Press your `[` (Left Bracket) key to check the rarity of your currently selected weapon. You can change the selected weapon using the left and right arrow keys.
