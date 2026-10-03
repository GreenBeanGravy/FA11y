# FA11y: Fortnite accessibility tool for blind and visually impaired players

## FA11y is NOT a mod

FA11y runs alongside Fortnite. It does not modify, inject into, or read
Fortnite's game files or memory. It announces what is visible on screen, what
Fortnite writes to its local log files, and what Epic's public APIs return.

Because FA11y reads the screen directly, you need Windows, a 1920x1080
monitor resolution, and Fortnite running fullscreen with no overlays or
notifications covering the HUD.

## About

FA11y makes in-match Fortnite and many out-of-match menus accessible to
blind and visually impaired players. It can do the following, among other
things.

### In-match

- Get directions (stereo audio + spoken bearing) to POIs, landmarks, game
  objects, custom POIs, custom favorite locations, and the safe zone
- Announce health, shields, rarity, ammo, and held-item state
- Announce height while skydiving
- Announce the direction you are facing
- Auto-turn toward the selected POI when you start navigation
- Announce match events such as knockdowns, respawns, players remaining,
  the battle bus, storm phases, death, and spectating info
- Control the camera and mouse from the keyboard: recenter, turn, scroll, and
  left and right click

### Out of match

- The FA11y window: a sidebar of pages for your Epic account, locker,
  friends and party, quests, Discover, settings, and keybinds
- Install, update, verify, move, and uninstall Fortnite, and set its launch
  options, from the Fortnite page (no Epic Games Launcher needed)
- Browse and equip cosmetics with the Locker selector
- Select game modes with the Discovery selector (Left Alt + apostrophe)
- Browse Creative islands with the Discovery menu
- Sign in to Epic and use the social menu (friends, party, requests)
- Check the Reload map rotation on fortnite.gg and announce which map is live
  now and which is next; optionally set FA11y's `current_map` to match
- Custom POIs per map, favorites, visited-objects tracking

## Setup

1. Download `Updater.exe` and `FA11y Launcher.exe` from the latest
   `installer-v` release and put both in an empty folder (avoid the
   Fortnite install directory and system folders)
2. Run `Updater.exe`. It installs FA11y into a `FA11y Files` folder next to
   it, together with its own copy of Python and everything FA11y needs, so
   you don't need to install Python yourself. Windows asks once for
   permission to install the drivers FA11y uses for mouse control.
3. Start FA11y with `FA11y Launcher.exe`. It checks for updates each time
   it starts (turn this off with the `AutoUpdates` setting).
4. The FA11y window opens. On first run it walks you through setup: signing
   in to Epic Games, finding or installing Fortnite, and a few preferences.

## The FA11y window

The window has a list of pages on the left (Home, Fortnite, Discover, Epic
account, Locker, Social, Quests and passes, Settings, Keybinds, and About and
updates). Use the arrow keys in the list, then Enter or F6 to move into a
page; F6 moves back. Ctrl+Tab and Ctrl+Shift+Tab switch pages from anywhere.

FA11y's keybinds work while the window is open or hidden. When Fortnite
starts, the window hides to the system tray. Bring it back with
`Left Alt + F`, the tray icon, or by starting `FA11y Launcher.exe` again;
Escape hides it and returns you to Fortnite. Keybinds such as `F9` for
settings and `Left Alt + .` for the social menu open the matching page.

The first time you close the window, FA11y asks whether to keep running in
the tray or quit. Change this later under Settings, General.

To see FA11y's printed output while troubleshooting, run
`"FA11y Launcher.exe" --console`.

If you already use an older FA11y, keep starting it as usual. The next
update moves it to the new layout and keeps your settings, with a backup in
a `FA11y_backup_` folder for two weeks.

## Default keybinds

All keybinds can be changed on the Keybinds page (`F9`, then Keybinds):
select an action, press Enter, then press the new keys. If the keys belong
to another action, the two actions swap keys.

### Meta

| Key | Action |
|---|---|
| `F8` | Toggle all FA11y keybinds on/off |
| `L-Alt + F` | Open or hide the FA11y window |
| `F9` | Open FA11y settings |
| `F12` | Exit current match (requires Fortnite quick menu open) |

### Navigation

| Key | Action |
|---|---|
| `` ` `` (grave) | Start navigation to selected POI / game object |
| `Shift + `` ` `` | Check hotspot POIs (requires map open) |
| `]` | Open POI selector |
| `[` | Open Locker selector |
| `Tab` / `Shift+Tab` | Cycle POI categories (inside POI selector) |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Cycle maps (inside POI selector) |
| `=` | Cycle POI (forward) |
| `Shift + =` | Cycle POI (backward) |
| `-` | Cycle POI category (forward) |
| `Shift + -` | Cycle POI category (backward) |
| `0` | Cycle map (forward) |
| `Shift + 0` | Cycle map (backward) |
| `L-Alt + P` | Toggle continuous ping on selected object |
| `L-Alt + Shift + F` | Toggle selected POI as favorite |
| `\` | Create custom POI at player position (requires map open) |
| `L-Alt + Delete` | Mark last reached game object as bad |

### Information

| Key | Action |
|---|---|
| `H` | Announce Health & Shields |
| `J` | Announce ammo (mag + reserve) |
| `;` | Announce direction you're facing |
| `[` (inside inventory) | Announce rarity of selected item |
| `L-Alt + M` | Match stats summary |
| `1`-`5` | Announce details of hotbar slot 1-5 |

### Camera & mouse (keyboard-only control)

| Key | Action |
|---|---|
| `L-Ctrl` | Left click / Fire |
| `R-Ctrl` | Right click / Aim |
| `Num5` | Recenter camera |
| `Num4` / `Num6` | Turn slightly left / right |
| `Num1` / `Num3` | Turn left / right |
| `Num8` / `Num2` | Look up / down |
| `Num0` | Turn 180 degrees |
| `Num7` / `Num9` | Scroll up / down |

### Menus

| Key | Action |
|---|---|
| `Left Alt + '` | Discovery game mode selector |
| `L-Alt + V` | Visited-objects manager |
| `L-Alt + .` | Social menu |
| `L-Alt + '` | Discovery menu |
| `L-Alt + Shift + L` | Epic authentication dialog |
| `L-Alt + Y` / `L-Alt + N` | Accept / decline pending notification |
| `L-Alt + Shift + M` | Recapture mouse (for passthrough) |
| `L-Alt + Shift + P` | Toggle mouse passthrough |

## Troubleshooting

- Most issues come from a wrong screen resolution or Fortnite not being fullscreen. Set your resolution to 1920x1080 and put Fortnite in fullscreen (F11 toggles it while the game has focus).

## Contributing

- Main repo: https://github.com/greenbeangravy/fa11y
- Issues and feature requests are welcome there

## License

See [LICENSE](LICENSE).
