# FA11y Project Notes

## Repository
- **GitHub**: https://github.com/greenbeangravy/fa11y
- **Fork**: https://github.com/ShotgunSpoon/FA11y
- **Remotes**: `origin` = ShotgunSpoon fork, `upstream` = greenbeangravy main repo

## Architecture
- **Language**: Python (wxPython GUI, pyautogui for automation)
- **Auth**: Epic Games OAuth via `lib/utilities/epic_auth.py` (EpicAuth class)
  - Uses `fortnitePCGameClient` credentials (CLIENT_ID `ec684b8c687f479fadea3cb2ad83f5c6`)
  - Tokens must be `token_type=eg1` (JWT) for EOS Connect compatibility
  - Account is migrated to Locker Service (`LockerReadDualWrite`) — all MCP locker operations (SetCosmeticLockerSlot, PutModularCosmeticLoadout, EquipModularCosmeticLoadoutPreset) return 404
  - Equipping cosmetics via API uses EOS Locker Service `PUT active-loadout-group`
  - Reading equipped/presets uses EOS Locker Service `GET items`
  - Saving new presets has no known API — saved locally in `config/fa11y_loadouts.json`

## Key Files
- `lib/utilities/epic_auth.py` — EpicAuth, LockerAPI classes, EOS Connect token exchange
- `lib/guis/locker_gui.py` — Locker GUI with category browsing, equip automation, loadout management
- `lib/config/config_manager.py` — Config storage (use `data=` param for list configs)
- `config/fa11y_loadouts.json` — Local loadout storage (merged from Epic presets)

## Equip Methods
1. **API (Locker Service)** — Instant server-side, requires game restart/new match to see changes
2. **UI Automation (pyautogui)** — Clicks through Fortnite's locker UI one item at a time, immediate visual effect

## Important Notes
- `config_manager.set()` for list configs requires `data=` keyword: `config_manager.set('fa11y_loadouts', data=list_value)`
- EOS Locker Service uses Epic account ID (not product_user_id) for the URL path
- Deployment ID for live Fortnite: `62a9473a2dca46b29ccf17577fcf42d7`
