# FA11y: Fortnite accessibility for blind and visually impaired players

FA11y runs alongside Fortnite and makes matches and many of the menus
around them usable with a screen reader. It works with most screen reader
software.

## FA11y is not a mod

FA11y doesn't modify, inject into, or read Fortnite's game files or memory.
It reads what is on screen, what Fortnite writes to its local log files, and
what Epic's public APIs return.

Because it reads the screen, FA11y needs Windows 10 or 11, a 16:9 display
(1920 by 1080 works best, since some features read fixed positions), and
Fortnite in Fullscreen or Windowed Fullscreen with nothing covering the HUD.
The Game check on FA11y's Fortnite page tells you if any of this is off and
how to fix it.

## What it does

In a match, FA11y can:

- give directions to POIs, landmarks, game objects, your own custom POIs and
  favorites, with stereo audio and a spoken bearing
- announce health, shields, ammo, the item you're holding, height while
  skydiving, and the direction you're facing
- announce match events: knockdowns, respawns, players left, the battle bus,
  storm phases, your elimination, and who you're spectating
- move the camera and click from the keyboard, and pass your own mouse
  through to Fortnite

Outside a match, the FA11y window lets you:

- install, update, verify, move and uninstall Fortnite and set its launch
  options, without the Epic Games Launcher
- sign in to Epic and use your friends list, party and requests
- browse and equip your locker
- pick game modes and browse Creative islands on the Discover page
- follow quests and passes
- check which Reload map is live now and which is next
- change every setting and keybind

## Installing

1. Download `Updater.exe` from the latest `installer-v` release and put it
   in an empty folder. Avoid the Fortnite install folder and system folders.
2. Run `Updater.exe`. It downloads `FA11y_Launcher.exe` next to itself and
   installs FA11y into a `FA11y Files` folder, with its own copy of Python
   and the .NET runtime the window needs, so you don't install anything
   yourself. Windows asks once for permission to install the driver FA11y
   uses for mouse control. While Stable FA11y doesn't support this installer
   yet, it installs the Beta branch.
3. Start FA11y with `FA11y_Launcher.exe`. It checks for updates each time it
   starts. The `AutoUpdates` setting turns that off.
4. On the first run, FA11y walks you through setup: signing in to Epic,
   finding or installing Fortnite, and a few preferences.

If you already use an older FA11y, keep starting it as usual. The next update
moves it to the new layout and keeps your settings, with a backup in a
`FA11y_backup_` folder for two weeks.

## The FA11y window

FA11y shows a short loading screen while it starts, then opens on Home. The
pages are listed on the left: Home, Fortnite, Discover, Epic account, Locker,
Social, Quests and passes, Settings, Keybinds, and About and updates. Arrow
through the list to change pages, then press Enter or F6 to move into the
page. F6 moves back to the list, and Ctrl+Tab and Ctrl+Shift+Tab change pages
from anywhere.

When Fortnite starts, the window hides to the system tray. Bring it back with
Left Alt + Left Shift + F, the tray icon, or by starting
`FA11y_Launcher.exe` again. Escape hides it and returns you to Fortnite.
Keybinds that open a page, such as F9 for settings or Left Alt + period for
Social, also work while the window is in front.

The first time you close the window, FA11y asks whether to keep running in
the tray or quit. Minimizing also sends it to the tray. You can change both
under Settings, General, where you can also turn the Windows notifications
for "ready" and "running in the background" on or off.

To see FA11y's output while troubleshooting, run
`"FA11y_Launcher.exe" --console`. The About and updates page opens the logs
folder.

## Branches

FA11y has two branches. Stable (`main`) is the tested release most people
use. Beta (`overhaul`) has the new FA11y window and early features, and more
rough edges. FA11y remembers its branch and keeps updating from it.

To switch, open About and updates, pick a branch under "FA11y branch", and
press "Switch branch". FA11y closes, updates and starts again, and your
settings stay. To pick the branch for a fresh install, run `Updater.exe
--branch main` or `Updater.exe --branch overhaul`.

## Default keybinds

Change any keybind on the Keybinds page: select an action, press Enter, then
press the new keys. If another action already uses those keys, the two swap.

FA11y's game keybinds are off while Fortnite isn't running. Open FA11y and
Toggle keybinds always work.

### FA11y

| Keys | Action |
|---|---|
| F8 | Turn FA11y's keybinds on or off |
| Left Alt + Left Shift + F | Open or hide the FA11y window |
| F9 | Open Settings |
| F12 | Leave the match (with Fortnite's quick menu open) |

### Navigation

| Keys | Action |
|---|---|
| Grave (`` ` ``) | Start navigation to the selected POI or object |
| = / Shift + = | Next / previous POI |
| - / Shift + - | Next / previous POI category |
| 0 / Shift + 0 | Next / previous map |
| Left Alt + P | Continuous ping on the selected POI |
| Left Alt + Left Shift + B | Add or remove the selected POI as a favorite |
| Left Alt + C | Create a custom POI where you stand |
| Left Alt + Left Shift + R | Announce the Reload map rotation |

### Information

| Keys | Action |
|---|---|
| H | Health and shields |
| J | Ammo in the magazine and in reserve |
| Semicolon | Direction you're facing |
| 1 to 5 | Item in hotbar slot 1 to 5 |
| Left Alt + M | Match stats |

### Camera and mouse

| Keys | Action |
|---|---|
| Left Ctrl | Left click (fire) |
| Right Ctrl | Right click (aim) |
| Numpad 5 | Recenter the camera |
| Numpad 4 / 6 | Turn a little left / right |
| Numpad 1 / 3 | Turn left / right |
| Numpad 8 / 2 | Look up / down |
| Numpad 0 | Turn around |
| Numpad 7 / 9 | Scroll up / down |
| Left Alt + Left Shift + M | Pick the mouse used for passthrough again |
| Left Alt + Left Shift + P | Turn mouse passthrough on or off |

### Pages and menus

| Keys | Action |
|---|---|
| Left Alt + apostrophe | Discover |
| Left Alt + period | Social |
| Left Alt + Q | Quests and passes |
| Right bracket (`]`) | Locker |
| Left Alt + O | Match options |
| Left Alt + Left Shift + L | Epic sign-in |
| Left Alt + Y / Left Alt + N | Accept / decline a friend request or party invite |

## Troubleshooting

Most problems come from the display. Open the Fortnite page and read the Game
check: it lists the window mode, game resolution, screen resolution and mouse
driver, and says how to fix anything that's wrong.

## Contributing

The repository is at https://github.com/greenbeangravy/fa11y. Issues and
feature requests are welcome there.

## License

See [LICENSE](LICENSE).
