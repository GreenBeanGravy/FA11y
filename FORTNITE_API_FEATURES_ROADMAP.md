# Fortnite API Features Roadmap for FA11y

This document outlines potential features that could be added to FA11y based on the Fortnite API endpoints documented in `/FortniteEndpointsDocumentation/`.

**Date Created:** 2025-11-20
**Status:** Comprehensive Review Complete

---

## Available Epic Games API Services

Based on the FortniteEndpointsDocumentation folder, the following Epic Games API services are available:

### 1. **AccountService** - User Account Management
**Location:** `/FortniteEndpointsDocumentation/EpicGames/AccountService/`

**Endpoints Available:**
- GET `/account/api/public/account/{accountId}` - Get account details
- Account lookup by display name, email, account ID
- External auth management (PSN, Xbox, Nintendo, etc.)
- Device auth for persistent login
- Account metadata storage

**Current FA11y Usage:** ✅ Implemented
- Account info display in Social GUI "Me" tab
- Authentication system uses AccountService

**Potential Enhancements:**
- Display linked platforms (PSN, Xbox, Nintendo, Steam)
- Show account creation date
- Display account metadata
- Manage external auth connections

---

### 2. **FriendsService** - Social Features
**Location:** `/FortniteEndpointsDocumentation/EpicGames/FriendsService/`

**Endpoints Available:**
- Friends list management
- Friend requests (send, accept, decline)
- Block list management
- Recent players

**Current FA11y Usage:** ✅ Fully Implemented
- Friends list with favorites
- Friend requests (incoming/outgoing)
- Add/remove friends
- Block management

---

### 3. **PartyService** - Party/Lobby Management
**Location:** `/FortniteEndpointsDocumentation/EpicGames/PartyService/`

**Endpoints Available:**
- Create/join/leave party
- Invite players to party
- Kick party members
- Promote party leader
- Update party settings
- Party member metadata

**Current FA11y Usage:** ✅ Fully Implemented
- Party management in Social GUI
- Invite, kick, promote functions
- Party member list

---

### 4. **StatsProxyService** - Player Statistics
**Location:** `/FortniteEndpointsDocumentation/EpicGames/StatsProxyService/`

**Endpoints Available:**
- GET `/Stats/UserStats` - Get player stats by account ID
- GET `/Stats/UserStatsBulk` - Get stats for multiple players
- GET `/Stats/Leaderboard` - Global/regional leaderboards

**Current FA11y Usage:** ❌ NOT IMPLEMENTED

**Feature Proposal: Player Stats System**

**Priority:** HIGH

**Implementation Plan:**
```
New File: lib/utilities/epic_stats.py
- Class: EpicStatsService
  - get_player_stats(account_id, stat_name)
  - get_bulk_stats(account_ids, stat_name)
  - get_leaderboard(stat_name, window="alltime")

Available Stats:
- br_kills_keyboardmouse
- br_playersoutlived_keyboardmouse
- br_wins_keyboardmouse
- br_matchesplayed_keyboardmouse
- br_minutesplayed_keyboardmouse
- br_score_keyboardmouse
And similar for _gamepad, _touch

Leaderboards:
- "br_kills_keyboardmouse"
- "br_playersoutlived_keyboardmouse"
- "br_minutesplayed"
- Regional leaderboards (NAE, NAW, EU, etc.)

GUI Integration:
- Add "Stats" button to Social GUI "Me" tab
- Show:
  * Lifetime kills, wins, matches played
  * Win rate percentage
  * Average placement
  * Time played
  * K/D ratio
- Compare stats with friends
```

---

### 5. **EventsService** - Tournaments & Competitive
**Location:** `/FortniteEndpointsDocumentation/EpicGames/EventsService/`

**Endpoints Available:**
- GET `/Events/Leaderboard` - Tournament leaderboards
- GET `/Events/History/Event` - Event history
- GET `/Events/History/EventWindow` - Event window details
- GET `/Player/Info` - Player event participation
- GET `/Player/Tokens` - Event entry tokens

**Current FA11y Usage:** ❌ NOT IMPLEMENTED

**Feature Proposal: Competitive Events System**

**Priority:** MEDIUM

**Implementation:**
```
New File: lib/utilities/epic_events.py
- get_active_events()
- get_event_leaderboard(event_id, event_window_id)
- get_player_event_history(account_id)
- get_event_details(event_id)

New GUI: lib/guis/events_gui.py
- List active tournaments
- Show player's tournament placements
- Display prize pool information
- View leaderboard standings
- Show event schedules

Features:
- Tournament eligibility checker
- Hype/ranking progress tracker
- Session points calculator
- Event countdown timers
```

---

### 6. **FN-Service** - Fortnite Game Service
**Location:** `/FortniteEndpointsDocumentation/EpicGames/FN-Service/`

This is the largest service with many sub-services:

#### 6a. **Profile Operations** - Player Profile Management
**Location:** `/FN-Service/Game/Profile/Operations/`

**150+ Operations Available Including:**
- `QueryProfile` - Get full player profile
- `AthenaTrackQuests` - Track/untrack quests
- `ClaimQuestReward` - Claim completed quest rewards
- `SetCosmeticLockerSlot` - Equip cosmetics (already used)
- `SetCosmeticLockerSlots` - Batch equip cosmetics
- `MarkItemSeen` - Mark items as seen
- `PurchaseCatalogEntry` - Purchase from item shop
- `GiftCatalogEntry` - Gift items to friends
- `SetHeroCosmeticVariants` - Set skin style variants
- `RefundMtxPurchase` - Refund V-Bucks purchases
- `EndBattleRoyaleGame` / `EndBattleRoyaleGameV2` - Submit match results

**Current FA11y Usage:** Partial (Locker system)

**Feature Proposals:**

**A. Quest/Challenge System**
**Priority:** HIGH
```
New File: lib/guis/quests_gui.py
- Display active daily/weekly quests
- Show quest progress (kills remaining, etc.)
- Track which quests are tracked in-game
- Display quest rewards (XP, V-Bucks)
- Quest categories (Daily, Weekly, Event, Milestone)
- Quest completion status
- Auto-track high-value quests
```

**B. Battle Pass Progress Tracker**
**Priority:** MEDIUM
```
Add to quests_gui.py or separate tab:
- Current Battle Pass level
- XP to next level
- Total seasonal XP
- Battle Stars available
- Reward preview at each level
- Season end countdown
- XP boost status
- Supercharged XP tracker
```

**C. V-Bucks & Purchase Management**
**Priority:** LOW
```
New section in "Me" tab:
- Current V-Bucks balance
- Purchase history (last 10 transactions)
- Refund tickets remaining (0-3)
- Refund eligible purchases
- Gift history
```

#### 6b. **Stats & Leaderboards**
**Location:** `/FN-Service/Game/Stats.md`, `StatsLeaderboard.md`

**Already covered under StatsProxyService above**

#### 6c. **Catalog & Item Shop**
**Location:** `/FN-Service/Game/Catalog/`

**Endpoints:**
- `Catalog.md` - Get current item shop catalog
- `GiftEligibility.md` - Check if item can be gifted
- `Keychain.md` - Storefront keychain
- `Receipts.md` - Purchase receipts

**Current FA11y Usage:** ❌ NOT IMPLEMENTED

**Feature Proposal: Item Shop Browser**
**Priority:** MEDIUM
```
New GUI: lib/guis/itemshop_gui.py
- Display current item shop
- Browse daily/featured items
- Show item prices in V-Bucks
- Display item rarity and type
- "Days since last seen" tracker
- Wishlist system (local storage)
- Price history tracking
- Bundle value analysis
- Shop rotation countdown
```

#### 6d. **Calendar & Events**
**Location:** `/FN-Service/Game/Calendar.md`

**Endpoint:**
- GET `/calendar/timeline` - Game calendar with events

**Feature Proposal: Events Calendar**
**Priority:** LOW
```
- Display active game events
- Show limited-time modes (LTMs)
- Event start/end times
- Special playlists available
- Bonus XP weekends
- In-game challenges tied to events
```

#### 6e. **Cloud Storage**
**Location:** `/FN-Service/Game/Cloudstorage/`

**Endpoints:**
- User cloud storage (save files, settings)
- System cloud storage (game configs)

**Current FA11y Usage:** ❌ NOT IMPLEMENTED
**Use Case:** Could backup FA11y settings to Epic cloud

#### 6f. **Privacy Settings**
**Location:** `/FN-Service/Game/PrivacySettings/`

**Endpoints:**
- `GetSettings` - Get player privacy settings
- `UpdateSettings` - Update privacy settings

**Feature Proposal:** Display privacy settings in "Me" tab

#### 6g. **Creative & Discovery**
**Location:** `/FN-Service/Game/Creative/`

**Endpoints:**
- `DiscoveryAccessToken` - Get Creative discovery token
- `IslandAccolades` - Island achievements

**Current FA11y Usage:** Partial (Gamemode selector uses Discovery API)
**Status:** Advanced mode removed, but could re-add as simpler implementation

#### 6h. **EOS Services** (Epic Online Services)
**Location:** `/FN-Service/EOS-Services/`

**Sub-services:**
- **Inventory** - Player inventory management
- **Locker** - Cosmetic locker (already used)
- **Quests** - Quest system (overlaps with Profile Operations)

---

### 7. **FN-Discovery-Service** - Creative Mode Discovery
**Location:** `/FortniteEndpointsDocumentation/EpicGames/FN-Discovery-Service/`

**Endpoints:**
- Browse discovery surfaces (Featured, Trending)
- Get island details
- Player counts per island

**Current FA11y Usage:** Previously implemented, removed in advanced mode cleanup

**Status:** Not needed (gamemode selector simplified)

---

### 8. **FN-Discovery-Search-Service** - Search Creative Islands
**Location:** `/FortniteEndpointsDocumentation/EpicGames/FN-Discovery-Search-Service/`

**Endpoints:**
- `SearchLinks` - Search islands by code/name
- `SearchCreators` - Search island creators

**Current FA11y Usage:** Previously implemented, removed

---

### 9. **FN-Content** - Content Delivery
**Location:** `/FortniteEndpointsDocumentation/EpicGames/FN-Content/`

**Endpoints:**
- Content pages (news, MOTD)
- Dynamic content keys

**Feature Proposal: News/MOTD Reader**
**Priority:** LOW
```
- Display Fortnite news on startup
- Read patch notes
- Show Message of the Day
- Battle Royale news
- Save the World news (if applicable)
```

---

### 10. **UserSearchService** - User Search
**Location:** `/FortniteEndpointsDocumentation/EpicGames/UserSearchService/`

**Endpoints:**
- Search users by display name
- Fuzzy matching
- Multiple results

**Current FA11y Usage:** Used in Social GUI for adding friends

---

### 11. **LibraryService** - Game Library
**Location:** `/FortniteEndpointsDocumentation/EpicGames/LibraryService/`

**Endpoints:**
- Library items (owned games)
- Playtime tracking
- Collections management

**Use Case:** Display total Fortnite playtime

---

### 12. **LauncherService** - Epic Games Launcher
**Location:** `/FortniteEndpointsDocumentation/EpicGames/LauncherService/`

**Endpoints:**
- Distribution hosts
- Installers
- Manifest data

**Current FA11y Usage:** ❌ (Uses Legendary CLI instead)

---

### 13. **NellyService** - Reporting System
**Location:** `/FortniteEndpointsDocumentation/EpicGames/NellyService/`

**Endpoints:**
- Report players
- Report tasks

**Feature:** Add "Report Player" to social menu

---

### 14. **TagManagementService** - User Tags
**Location:** `/FortniteEndpointsDocumentation/EpicGames/TagManagementService/`

**Endpoints:**
- Get/set user tags
- Bulk tag operations

**Use Case:** Tag friends with custom labels

---

### 15. **IPDataService** - Geolocation
**Location:** `/FortniteEndpointsDocumentation/EpicGames/IPDataService/`

**Endpoints:**
- Region check
- IP geolocation

**Use Case:** Display player's region/closest server

---

## Priority Implementation Roadmap

### Phase 1: Essential Features (HIGH PRIORITY)

1. **Player Stats System** ⭐⭐⭐
   - Estimated Time: 4-6 hours
   - Files: `lib/utilities/epic_stats.py`, additions to Social GUI
   - Impact: HIGH - Users want to track their progress

2. **Quest/Challenge Tracker** ⭐⭐⭐
   - Estimated Time: 6-8 hours
   - Files: `lib/guis/quests_gui.py`, `lib/utilities/epic_quests.py`
   - Impact: HIGH - Helps users complete challenges accessibly

3. **Battle Pass Progress** ⭐⭐
   - Estimated Time: 3-4 hours
   - Files: Addition to quests_gui.py
   - Impact: MEDIUM-HIGH - Track seasonal progression

### Phase 2: Social & Competitive (MEDIUM PRIORITY)

4. **Tournament/Events Viewer** ⭐⭐
   - Estimated Time: 5-7 hours
   - Files: `lib/guis/events_gui.py`, `lib/utilities/epic_events.py`
   - Impact: MEDIUM - For competitive players

5. **Leaderboards** ⭐⭐
   - Estimated Time: 3-4 hours
   - Files: Addition to stats system
   - Impact: MEDIUM - Social comparison

6. **Enhanced Account Info** ⭐
   - Estimated Time: 2-3 hours
   - Files: Updates to social_gui.py "Me" tab
   - Impact: LOW-MEDIUM - Nice-to-have details

### Phase 3: Economy & Shop (LOW-MEDIUM PRIORITY)

7. **Item Shop Browser** ⭐
   - Estimated Time: 6-8 hours
   - Files: `lib/guis/itemshop_gui.py`
   - Impact: MEDIUM - Popular feature request

8. **V-Bucks & Purchase History** ⭐
   - Estimated Time: 2-3 hours
   - Files: Addition to "Me" tab
   - Impact: LOW - Informational

### Phase 4: Nice-to-Have Features (LOW PRIORITY)

9. **News/MOTD Reader**
   - Estimated Time: 2-3 hours
   - Impact: LOW

10. **Events Calendar**
    - Estimated Time: 3-4 hours
    - Impact: LOW

11. **Privacy Settings Display**
    - Estimated Time: 1-2 hours
    - Impact: LOW

---

## Technical Considerations

### Authentication Requirements
All Epic Games API endpoints require:
- Valid OAuth2 bearer token
- Proper client credentials
- Token refresh on 401 errors (notify user, don't auto-refresh per requirements)

### Rate Limiting
Epic Games APIs have rate limits:
- Implement caching for frequently accessed data
- Cache duration recommendations:
  - Stats: 5 minutes
  - Quest progress: 2 minutes
  - Item shop: 1 hour (changes daily)
  - Account info: Session-based
  - Leaderboards: 10 minutes

### Error Handling
- Network failures: Retry with backoff
- 401 Unauthorized: Notify user to re-authenticate
- 403 Forbidden: Display appropriate error
- 429 Too Many Requests: Implement backoff
- 5xx Server Errors: Retry with exponential backoff

### Caching Strategy
Store cached API responses in:
- `config/cache/` directory
- JSON format with timestamps
- Invalidate based on cache duration
- Use `config_manager` for thread-safe access

---

## Implementation Status

**Completed (Phase 0 - December 2024):**
- ✅ Logging system with rotating log files
- ✅ POI favorite keybind (ALT+SHIFT+F)
- ✅ Removed unused keybinds
- ✅ Fixed late authentication issue
- ✅ Added "Me" tab with account info to Social GUI
- ✅ Removed advanced mode from gamemode selector

**Next Steps:**
1. Implement Player Stats System (Phase 1, Item #1)
2. Implement Quest/Challenge Tracker (Phase 1, Item #2)
3. Add Battle Pass Progress (Phase 1, Item #3)

---

## API Documentation Reference

Full API documentation is available in:
```
/FortniteEndpointsDocumentation/EpicGames/
```

Key documentation files:
- `AccountService/README.md` - Account endpoints
- `StatsProxyService/README.md` - Statistics endpoints
- `EventsService/README.md` - Tournament endpoints
- `FN-Service/README.md` - Main Fortnite service
- `FN-Service/Game/Profile/Operations/` - Profile operations (150+ endpoints)

---

## Notes

- All features must maintain FA11y's accessibility standards
- Screen reader compatibility required for all GUIs
- Audio feedback for all user actions
- Keyboard navigation for all interfaces
- Error messages must be clear and spoken aloud

**Last Updated:** 2025-11-20
