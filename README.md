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
  objects, custom POIs, favorites, and the safe zone
- Announce health, shields, rarity, ammo, and held-item state
- Announce height while skydiving
- Announce the direction you are facing (read from the minimap compass)
- Auto-turn toward the selected POI when you start navigation
- Announce match events by tailing Fortnite's log: knockdowns, respawns,
  players-remaining changes, battle bus, storm phases, death, spectating,
  final placement, final-countdown counts
- Full keyboard camera and mouse control — recenter, turn, look, scroll,
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
3. Double-click `FA11y_debug.bat` — it installs the Python dependencies from
   `requirements.txt` and launches FA11y
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

## Adding a new map

`maps/` is a flat folder. Every file name uses a canonical lowercase
underscore slug (e.g. `reload_venture`, `blitz_stranger_things`, `o_g`).

To add a new map:

1. Drop these files into `maps/`:
   - `maps/<slug>.png` — the map image (screenshot or export)
   - `maps/map_<slug>_pois.txt` — lines of `Name,ScreenX,ScreenY`
   - `maps/map_<slug>_gameobjects.txt` — lines of `ObjectType,ImageX,ImageY`
     (optional; only if you want game-object detection on this map)
2. Restart FA11y. Map discovery picks the new slug up automatically.
3. To set FA11y to the new map, either cycle with `0` in-game or edit
   `config/config.txt` → `[POI] current_map = <slug>`.

If this is a Reload arena, also add a row to `DISPLAY_TO_FA11Y_MAP` in
`lib/utilities/map_rotation.py` so the Reload rotation announcement knows
about it.

## Position detection (feature-matcher)

FA11y locates you on the map by feature-matching the minimap capture against
the map image in `maps/<slug>.png`. The matcher is pluggable:

- **SIFT** (default) — best on texture-rich terrain like the main battle-royale map
- **AKAZE** — 3× faster than SIFT, better on uniform / low-contrast terrain (reload arenas)
- **ORB** — fastest, lower accuracy — rarely the right default

Plus a **CLAHE** preprocessing pass that dramatically improves matching on
snow / sand / other low-contrast areas.

Global defaults live in `config/config.txt`:

```
[POI]
feature_detector = sift       ; sift | akaze | orb
feature_clahe    = false      ; true enables CLAHE on capture + map
```

Per-map overrides trump the global setting. Two ship by default in
`lib/detection/coordinate_config.py::MAP_MATCHER_OVERRIDES`:

- `reload_elite_stronghold` → AKAZE + CLAHE (the snow-heavy Reload map)
- `blitz_stranger_things` → SIFT + CLAHE

If you find another map that matches badly, try flipping the global
`feature_detector` to `akaze` and `feature_clahe` to `true`, or add a
per-map entry to `MAP_MATCHER_OVERRIDES`.

## Developer tools

Self-contained dev utilities live under `dev_tools/`. They are not loaded by
the runtime app; run them manually from the repo root:

| Script | Purpose |
|---|---|
| `python dev_tools/pixel_picker.py` | Click-through magnifier overlay; reads pixels the way FA11y sees them |
| `python dev_tools/health_calibrator.py` | Auto-calibrate the health-bar decrease pattern |
| `python dev_tools/health_shield_debugger.py` | Live-tune health/shield bar detection |
| `python dev_tools/ppi_configurator.py` | Live-tune PPI (minimap feature matching) |
| `python dev_tools/direction_configurator.py` | Live-tune minimap icon / direction detection |
| `python dev_tools/feature_match_bench.py` | A/B benchmark every detector × CLAHE combo against every shipped `maps/*.png`; exports CSV |
| `python dev_tools/position_accuracy_check.py <slug>` | Targeted accuracy visualizer per map; supports `--region snow`, `--degrade heavy`, and `--capture <path>` to run every detector against a real minimap screenshot |
| `python dev_tools/minimap_recorder.py` | Run alongside FA11y during live play; `F10` saves the current minimap frame (+ every detector's result as JSON) to `dev_tools/captures/<map>/`, `F11` flags it BAD |
| `python dev_tools/clear_pycache.py` | Delete every `__pycache__` in the repo |

See `dev_tools/README.md` for contribution rules.

## Troubleshooting

- **"Position doesn't update / wrong position"**: verify resolution is
  exactly 1920 × 1080, Fortnite is fullscreen (not windowed-fullscreen or
  windowed), and the minimap is visible with nothing overlapping it. If it
  persists specifically on one map, try flipping `[POI] feature_detector`
  to `akaze` and `feature_clahe` to `true` in `config/config.txt`.
- **Debugging a specific bad frame**: run `python dev_tools/minimap_recorder.py`
  alongside FA11y during play, press `F11` when position goes wrong. Then
  offline, feed the saved PNG into
  `python dev_tools/position_accuracy_check.py <map_slug> --capture <path>` —
  it'll run every detector on your real capture and write overlay PNGs
  showing where each detector places you.
- **"Map I selected doesn't match"**: run `python dev_tools/ppi_configurator.py`
  to visually verify features are matching against the right `maps/<slug>.png`.
- **"Health/shield announcements are wrong"**: run
  `python dev_tools/health_calibrator.py` with a full 100 HP bar on screen.
- **Config says `current_map = reload venture` with a space**: first boot on
  this version rewrites it to the canonical `reload_venture` automatically.
  The same pass normalizes `map_name` in your favorites
  (`config/FAVORITE_POIS.txt`) and custom POIs (`config/CUSTOM_POI.txt`) so
  per-map data keeps showing up after the rename. A `.premigration` snapshot
  of each file is saved alongside (e.g. `config/config.txt.premigration`)
  so you can roll back to an older FA11y build by restoring them.
- **`FA11y_debug.bat` fails**: run `pip install -r requirements.txt` manually
  and inspect the errors.

## Contributing

- Main repo: https://github.com/greenbeangravy/fa11y
- Fork for WIP branches: https://github.com/ShotgunSpoon/FA11y
- Issues and feature requests welcome on the main repo

## License

See [LICENSE](LICENSE).
