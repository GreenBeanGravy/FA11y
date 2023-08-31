# FA11y: Fortnite Accessibility Tool for Blind Players

## About
FA11y aims to make Fortnite's GUI elements accessible to blind players. With FA11y, you can:

- Get simple directions to Points of Interest (POIs)
- Have your Health, Shield, and Weapon Rarity read out loud
- Place a ping on the center of the storm for easier navigation

FA11y uses computer vision, Python's pyautogui library, and screen readers to make these features available.

## Keybinds
Here are the keybindings for FA11y:

- **`]` (Right Bracket)**: Open the POI selection menu
- **`Enter` / `Space`**: Select a POI in the menu
- **`Up Arrow` / `Down Arrow`**: Navigate through the POI menu
- **`[` (Left Bracket)**: Enable rarity detection while in the inventory
- **`H`**: Invoke health and shield detection
- **`` ` `` (Grave Accent / Backtick)**: Run icon detection to give directions to the selected POI

## Installation
First, you'll need Python 3.6 or later installed on your machine.

1. Download the latest release.
2. Open a CMD/Terminal window in the folder where you downloaded FA11y.
3. Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```
4. Optional: Add your own Points of Interest (POIs) in `POI.txt`

## Usage

### POI Directions/Icon Detection
- While in-game, press `M` to open your map.
- While the map is open, press the `` ` `` (Grave Accent / Backtick) key.

### Storm Detection
- While in-game, press `M` to open your map.
- While the map is open, press the key combo `ALT + S` to ping the center of the storm. Listen for the stereo sound, close the map, turn in that direction, and repeat.

### Health and Shield
- While in-game, simply press `H` to check your health and shield values.

### Rarity
- While in-game, open your inventory using the `I` key. 
- Press your `[` (Left Bracket) key to check the rarity of your currently selected weapon. You can change the selected weapon using the left and right arrow keys.
