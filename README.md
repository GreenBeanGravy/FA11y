# FA11y — Fortnite Accessibility Tool for the Blind and Visually Impaired

## FA11y is NOT a mod

FA11y runs alongside Fortnite. It does not modify, inject into, or read
Fortnite's game files or memory. Everything it announces is derived from what
is visible on screen, what Fortnite writes to its local log files, and what
Epic's public APIs return.

Because FA11y reads the screen directly, it requires:

- **Monitor resolution**: 1920 × 1080
- **Fortnite**: running fullscreen, no overlays/notifications blocking the HUD
- **OS**: Windows

## About

FA11y makes in-match Fortnite and a large chunk of out-of-match menus
accessible to blind and visually impaired players. A non-exhaustive list of
what it currently does:

### In-match

- Get directions (stereo audio + spoken bearing) to POIs, landmarks, game
  objects, custom POIs, custom favorite locations, and the safe zone
- Announce health, shields, rarity, ammo, and held-item state
- Announce height while skydiving
- Announce the direction you are facing
- Auto-turn toward the selected POI when you start navigation
- Announce match events like knockdowns, respawns,
  players-remaining changes, battle bus, storm phases, death, and spectating info
- Full keyboard camera and mouse control — recentering camera, turning, scrolling,
  left/right click

### Out of match

- Install, verify, update, and launch Fortnite via `FortniteManager.py`
  (uses [Legendary](https://github.com/derrod/legendary) — no Epic launcher
  required)
- Browse and equip cosmetics via the Locker selector
- Select and queue game modes via the Gamemode selector
- Browse Creative islands via the Discovery menu
- Epic authentication / social menu (friends, party, requests)
- Reload map rotation — query fortnite.gg and announce which map is live now
  and what's next; optionally sync FA11y's `current_map` to it automatically
- Custom POIs per map, favorites, visited-objects tracking

## Setup

1. Install Python 3.10+ (check "Add Python to PATH" during install)
2. Download the latest FA11y release and extract it (avoid the Fortnite
   install directory and system folders)
3. From the extracted folder, run `pip install -r requirements.txt` to install
   dependencies, then launch with `python FA11y.py`
4. On first run, FA11y creates `config/config.txt` with default keybinds;
   press `F9` in-game to open the configuration menu

## Default keybinds

All keybinds are configurable via `F9` → FA11y configuration menu.

### Meta

| Key | Action |
|---|---|
| `F8` | Toggle all FA11y keybinds on/off |
| `F9` | Open FA11y configuration menu |
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
| `1`–`5` | Announce details of hotbar slot 1–5 |

### Camera & mouse (keyboard-only control)

| Key | Action |
|---|---|
| `L-Ctrl` | Left click / Fire |
| `R-Ctrl` | Right click / Aim |
| `Num5` | Recenter camera |
| `Num4` / `Num6` | Turn slightly left / right |
| `Num1` / `Num3` | Turn left / right |
| `Num8` / `Num2` | Look up / down |
| `Num0` | Turn 180° |
| `Num7` / `Num9` | Scroll up / down |

### Menus

| Key | Action |
|---|---|
| `'` | Gamemode selector |
| `L-Alt + V` | Visited-objects manager |
| `L-Alt + .` | Social menu |
| `L-Alt + '` | Discovery menu |
| `L-Alt + Shift + L` | Epic authentication dialog |
| `L-Alt + Y` / `L-Alt + N` | Accept / decline pending notification |
| `L-Alt + Shift + M` | Recapture mouse (for passthrough) |
| `L-Alt + Shift + P` | Toggle mouse passthrough |

## Installing Fortnite (first time)

1. Visit [Fortnite's store page](https://store.epicgames.com/en-US/p/fortnite)
   and add it to your account ("GET")
2. From your FA11y folder run `python FortniteManager.py`
3. Log in with Legendary: in the Fortnite Manager press "Authenticate", or
   open a command prompt in the FA11y folder and run `legendary auth`
   (sighted help may be needed for the hCaptcha)
4. Press "Install / Update Fortnite" in the Fortnite Manager
5. During installation:
   - `P`: announce progress
   - `-` / `+`: adjust progress-update frequency
   - `Escape`: cancel

Launch Fortnite afterwards from the Fortnite Manager (performance mode is
recommended).

## Troubleshooting

- **"Position doesn't update / wrong position"**: verify resolution is
  exactly 1920 × 1080, Fortnite is fullscreen (not windowed-fullscreen or
  windowed), and the minimap is visible with nothing overlapping it. If it
  persists specifically on one map, try flipping `[POI] feature_detector`
  to `akaze` and `feature_clahe` to `true` in `config/config.txt`.

## Contributing

- Main repo: https://github.com/greenbeangravy/fa11y
- Issues and feature requests welcome on the main repo

## License

See [LICENSE](LICENSE).
