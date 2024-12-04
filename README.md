# FA11y: Fortnite Accessibility Tool for the Blind and Visually Impaired!

## FA11y IS NOT A MOD
FA11y runs seperately from Fortnite, and does not modify, read, or in any way interact with the Fortnite game files or memory. FA11y relies entirely on what can be seen on screen in order to get the information it needs. As a result of this, FA11y requires that you set your monitor to a resolution of 1920x1080 in order to operate. No other resolutions will work! FA11y is also prone to obstructions from notifications, and will also have various issues if Fortnite is accidentally taken out of fullscreen.

## About
FA11y aims to make many important elements of Fortnite accessible to blind and visually impaired players. With FA11y, you can:

- Get directions to selected Points of Interest (P O I's), landmarks, and even the Safe Zone with stereo audio feedback.
- Check your available Health and Shields.
- Get your height while skydiving in real time.
- Check the direction you are currently facing.
- Automatically turn towards a selected P O I when navigating to it.
- Install, verify, update, and launch Fortnite accessibly!
- Select game modes easily with an accessible interface.
- Instantly leave your current match at the press of a button.
- Get announcements when you equip weapons and consumables, along with your available magazine and reserve ammo counts and consumable item count!
- Fully control and recenter your camera using just your keyboard!

## DEFAULT Keybinds (fully configurable)

### Navigation & Interaction
- **`]` (Right Bracket)**: Open P O I selection menu
  - **`Tab` / `Shift + Tab`**: Cycle between P O I categories
  - **`Enter`**: Select a P O I
- **`Up Arrow` / `Down Arrow`**: Navigate through most menus
- **`` ` `` (Grave Accent)**: Get directions to a selected P O I
- **`P`**: Toggle pathfinding to a selected P O I (Note: Currently not functional on the new season as of 12/1/2024)
- **`;` (Semicolon)**: Announce the direction you are currently facing
- **`'` (Apostrophe)**: Open the gamemode selector
- **`\` (Backslash)**: Create a custom P O I at current location

### Movement & Camera Control
- **`Left Control`**: Left mouse click / Fire
- **`Right Control`**: Right mouse click / Aim
- **`Num5`**: Recenter camera
- **`Num4`**: Turn slightly left
- **`Num1`**: Turn left
- **`Num6`**: Turn slightly right
- **`Num3`**: Turn right
- **`Num8`**: Look up
- **`Num2`**: Look down
- **`Num0`**: Turn 180 degrees
- **`Num7`**: Scroll up
- **`Num9`**: Scroll down

### Information & Status
- **`H`**: Check Health and Shields
- **`[` (Left Bracket)**: Check equipped item rarity (Note: Currently non-functional, but it remains largely unneeded)
- **`J`**: Announce current ammo counts/consumbale uses
- **`1-5`**: Equip and announce details about items in hotbar slots
- **`F8`**: Toggle all FA11y keybinds
- **`F9`**: Open FA11y configuration menu
- **`F12`**: Leave current match while the Quick Menu is open (Note: Open your Quick Menu with "`Escape`" anywhere in Fortnite)

## Setup
1. Install Python 3.9 or later (ensure "Add Python to PATH" is checked during installation)
2. Download the latest FA11y release
3. Extract to a location of your choice (avoid Fortnite directory and system folders)
4. Run `updater.py` and wait for completion
5. Launch FA11y by running `FA11y.py`

## Using Legendary CLI
Legendary is the command-line interface we use for Fortnite installation. No Epic Games launcher needed. To get started:

1. The Legendary executable should be in your FA11y folder after running the updater. If not, run `updater.py` again.
2. Open a command prompt in your FA11y folder (note: you can do this by navigating to the search field/edit field containing the current folder path, and replacing all contents with "cmd" and pressing enter)
3. Type `legendary auth` and press enter to start the login process
4. Follow the login prompts (note: you may encounter an hCaptcha - sighted assistance may be needed at this time)
5. If you see raw HTML after login, copy the authorization token and paste it in the command prompt, otherwise ignore this
6. Verify login with `legendary auth` again

## Installing Fortnite
1. Visit [Fortnite's store page](https://store.epicgames.com/en-US/p/fortnite)
2. Click "GET" and follow the prompts
3. After adding Fortnite to your account, run `FortniteManager.py` from your FA11y folder, and press the "Install/Update Fortnite" button at the top
4. During installation:
   - `P`: Announce last progress update
   - `-` / `+`: Adjust the frequency of progress updates
   - `Escape`: Cancel installation
5. Once complete, you can run Fortnite using either launch button at the bottom of the Fortnite Manager. Performance mode is recommended.
