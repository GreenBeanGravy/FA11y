# Accessible match options

Open Fortnite's match-options screen, then press Left Alt+O (Open Match Options in configuration). Tab moves between native Windows choices and checkboxes. Arrow keys change choices; Space toggles checkboxes. Changes apply immediately and are verified against Fortnite. Refresh reads the game again. Escape closes the accessible dialog. Close Fortnite's own options screen before using Alt+apostrophe to switch modes.

The English 1920x1080 layouts below were observed on September 8, 2026. Other 16:9 resolutions are normalized but not live-tested. Mode title and settings-heading references must both match before any click. Unsupported controls are hidden; locked Fill is disabled and announced. Enabled team icons determine available sizes, rather than a fixed Ranked allowlist.

| Mode | Build control | Ranked control | Observed team sizes |
| --- | --- | --- | --- |
| Battle Royale | Build / Zero Build | Yes | Solo, Duos, Trios, Squads; Ranked Zero Build enabled Solo/Duos, Ranked Build also enabled Trios |
| Reload | Build / Zero Build | Yes | Solo, Duos, Squads, including ranked |
| Fortnite OG | Build / Zero Build | No | Solo, Duos, Squads |
| Blitz Royale | No | No | Solo, Duos, Squads, Six Stack (6 players) |

Ranked availability was verified by selecting settings, without matchmaking. Fill was locked in observed ranked modes and Solo. The Reload map changed from Springfield to Slurp Rush while the controls stayed in place. Map artwork and map names are excluded from profile identity.

## Coordinates at 1920x1080

Build centers are (1336,128), (1640,128) wherever present. Battle Royale: Ranked (1688,254), teams at x1507/1589/1671/1753 and y380, Fill (1688,505). Reload: Ranked and Fill match Battle Royale; Solo/Duos/Squads at x1589/1671/1753 and y380. OG: Solo/Duos/Squads at x1589/1671/1753 and y252, Fill (1688,378). Blitz: Solo/Duos/Squads/Six Stack at x1507/1589/1671/1753 and y128, Fill (1688,254).

Profiles live in lib/detection/match_options.py. Changes require fresh matching state before clicking, then two consistent reads to confirm. A failed verification disables edits until Refresh; toggles are never automatically repeated. Fixtures retain only mode-title and control regions, excluding player and rank information.

## Manual Blitz selection

Close match options. Scroll down from the lobby to Discover, open By Epic, select the Sonic-themed Blitz Royale tile under Battle Royales by Epic, verify Created by Epic, then choose Select. This successfully opened Blitz even though FA11y's discovery shortcut did not respond to injected keyboard input during mapping. The cause of the user's separate Blitz search failure has not been established.
