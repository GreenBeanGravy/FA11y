# SERVICES AUTHENTICATION BREAKDOWN

## Complete Service Inventory with Auth Requirements

### 1. ACCOUNT SERVICE
**Package:** `com.epicgames.account`
**Base URL:** `account-public-service-prod.ol.epicgames.com/account/api`

**OAuth Token Endpoints:**
- `POST /oauth/token` - Basic Auth (clientId:clientSecret) - Get tokens
- `GET /oauth/verify` - Bearer token - Verify token
- `GET /oauth/permissions` - Bearer token - Get token permissions
- `POST /epicid/v1/oauth/tokenInfo` - Token in body - EpicId token info

**Account Operations:**
- `GET /public/account/{accountId}/publicKey` - NO AUTH - Get JWT public key
- Account info, creation, email management - Various auth requirements

---

### 2. FN-SERVICE (Game)
**Package:** `com.epicgames.fortnite.game`
**Base URL:** `fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api`

**Discovery:**
- `GET /discovery/accessToken/{branch}` - `fortnite:discovery:fortnite READ` - Get discovery token

**Profile & Stats:**
- Stats endpoints - `fortnite:stats READ` or similar
- Calendar, Catalog endpoints - Game-specific perms
- CloudStorage operations - `fortnite:cloudstorage READ`
- EntitlementCheck - Auth required

**Creative:**
- DiscoveryAccessToken - `fortnite:discovery:fortnite READ`

---

### 3. FN-DISCOVERY-SERVICE
**Package:** `com.epicgames.discovery`
**Base URL:** `fn-service-discovery-live-public.ogs.live.on.epicgames.com/api`

**Discovery Surface Queries:**
- `POST /v1/discovery/surface/{accountId}` - `discovery:{accountId}:surface:query READ`
- `POST /v1/discovery/surface/page/{accountId}` - `discovery:{accountId}:surface:query READ`
- `POST /v2/discovery/surface/{surfaceName}` - Header: `X-Epic-Access-Token` (discovery token)
- `POST /v2/discovery/surface/page/{surfaceName}` - Header: `X-Epic-Access-Token`
- `GET /v1/discovery/hub/portals` - Auth required

**Creator Pages:**
- `GET /v1/creator/page/{creatorAccountId}` - `discovery:{accountId}:creator:page READ`

**Links Management:**
- Favorites: `discovery:{accountId}:links:favorite {CREATE/DELETE/READ}`
- History: `discovery:{accountId}:links:history {CREATE/DELETE/READ}`
- Lock-Management: `discovery:{accountId}:links:lock-management {READ/UPDATE/DELETE}`
- Queue: `discovery:{accountId}:links:queue {CREATE/READ}`

---

### 4. FN-DISCOVERY-SEARCH-SERVICE
**Package:** `com.epicgames.dbs.discovery`
**Base URL:** `fn-service-discovery-live-public.ogs.live.on.epicgames.com/api/v1/search`

**Search Endpoints:**
- `POST /links` - `discovery:search:{accountId} READ`
- `POST /creators` - `discovery:search:{accountId} READ`

---

### 5. FRIENDS SERVICE
**Package:** `com.epicgames.friends`
**Base URL:** `friends-public-service-prod.ol.epicgames.com/friends/api`

**All endpoints:** `friends:{accountId} {READ/UPDATE/DELETE}`

**Operations:**
- FriendsList - READ
- Friend Requests (incoming/outgoing) - READ
- Summary - READ
- Add/Remove Friend - UPDATE/DELETE
- Mutual Friends - READ
- Friend Info - READ
- Alias (Edit/Remove) - UPDATE
- Notes (Edit/Remove) - UPDATE
- AcceptBulk - UPDATE
- ClearFriendsList - DELETE
- SuggestedFriends - READ
- PrivacySettings - READ/UPDATE
- ExternalSourceSettings - READ/UPDATE
- Blocklist - READ/UPDATE/DELETE

---

### 6. PARTY SERVICE
**Package:** `com.epicgames.sociallobby`
**Base URL:** `sociallobby-service-prod.ol.epicgames.com/sociallobby/api`

**All endpoints:** `social:party` (no granular READ/UPDATE/DELETE)

**Operations:**
- PartyInfo
- UpdateParty
- UpdatePartyMember
- Leave
- Join
- Invite
- SendRequestToJoin
- Promote
- PingInfo

---

### 7. GLOBAL SERVICE
**Package:** `com.epicgames.global`
**Base URL:** `global-service-prod.ol.epicgames.com/global/api`

**Profile Operations:**
- Profiles - No perm required (auth only)
- PrivacySettings - No perm required
- LanguageUpdate - No perm required
- RegionUpdate - No perm required
- PrivacySettingsUpdate - No perm required

**Reboot Rally:**
- All endpoints: No perm required (auth only)

---

### 8. STATS & RANKINGS SERVICES

**StatsProxyService:**
- `fortnite:stats READ` - All stats endpoints

**FN-Habanero-Service:**
- Tracks endpoints - `rankings:{namespace}:tracks READ`
- Progress endpoints - Various ranking scopes

**EventsService:**
- Most: `{gameId}:profile:{accountId}:commands READ`
- History: `{gameId}:matchmaking:session UPDATE`

---

### 9. SOCIAL SERVICES

**User Search Service:**
- SearchUsers - `social:search:{accountId} READ`

**Persona Service:**
- AccountLookup - `persona:account:lookup READ`

**Pops Service (Creator Pages):**
- GetPlayerPage - `pops:playerpage:{accountId} READ`
- GetPlayerPageBulk - `pops:playerpage:{accountId} READ`
- CheckHasPlayerPage - `pops:playerpage READ`
- FollowPlayerPage - `pops:follow:{accountId} UPDATE`
- UnfollowPlayerPage - `pops:follow:{accountId} DELETE`

---

### 10. LAUNCHER SERVICE
**Package:** `com.epicgames.epl`
**Base URL:** `launcher-service-prod.ol.epicgames.com/launcher/api`

**Public:**
- DistributionHosts - NO AUTH
- Installer - NO AUTH

**Protected:**
- Purchase/CheckOffers - `launcher:purchase:offers READ`
- Assets - `launcher:download:{label}:{appName} READ`
- Library/Items - `launcher:library:items READ`
- LauncherBuild endpoints - No perm required (auth only)

---

### 11. TAG MANAGEMENT SERVICE
**Package:** `com.epicgames.tags`

**All endpoints:** Account Auth (no scope specified)
- UpdateOwnTags
- UserTagsBulk
- TagsList
- OwnTags

---

### 12. PRM DIALOG SERVICE
**Package:** `com.epicgames.prmservice`

**All endpoints:** Account Auth (eg1 JWT required)
- ChannelTarget
- Interactions
- InteractionsContentHash
- SurfaceTarget

---

### 13. LINKS SERVICE (Mnemonics)
**Package:** `com.epicgames.links`

**Most endpoints:** `links:{namespace} READ`
**Create:** `links:{namespace}:{accountId} CREATE`
**Update:** `links:{namespace}:{accountId} UPDATE`
**Privileged:** `links:{namespace}:privileged_only CREATE`

---

### 14. LIGHTSWITCH SERVICE
**Package:** `com.epicgames.lightswitch`

**Status endpoints:**
- Status - No perm required (auth only)
- StatusBulk - No perm required (auth only)

---

### 15. DATA & DELIVERY SERVICES

**Data Asset Directory Service:**
- Assets - `dad:{gameId}:assets:* READ`

**Artifact Delivery Service:**
- Patch - `delivery:public:patch:{accountId} READ`
- DownloadURLs - `delivery:public:downloadurls:{accountId} READ`

**Emerald Service:**
- Upload operations - `emerald:upload CREATE`

---

### 16. IP & LOCATION SERVICES

**IPDataService:**
- Region - `ipdata:region READ` (auth required)
- RegionCheck - `ipdata:region READ` (auth required)
- HealthCheck - NO AUTH

---

### 17. KWS (KIDS WEB SERVICES)
**Package:** `com.epicgames.kws`

- Settings/Update - `epic-settings:public:games:{game} UPDATE`
- Settings/Definitions - `epic-settings:public:games:{game} READ`
- Settings/SendVerifyEmail - Auth required

---

### 18. WASP SERVICE (Creative Worlds)
**Package:** `com.epicgames.wasp`

**All endpoints:** Auth required
- World CRUD operations
- Invite management
- Grant management
- Player metadata
- World tokens

---

### 19. EOSSERVICES
**Package:** `com.epicgames.eosservices`

**All endpoints:** Basic Auth (clientId:clientSecret)
- Quests
- Locker
- Inventory

---

### 20. FULFILLMENT SERVICE
**Package:** `com.epicgames.fulfillment`

- Code redemption - Auth required

---

### 21. LIBRARY SERVICE
**Package:** `com.epicgames.library`

- Items - `launcher:library:items READ`
- Collections - Auth required
- Playtime info - Auth required

---

### 22. CALDERA SERVICE (Launcher)
**Package:** `com.epicgames.caldera`

- RACP endpoint - NO AUTH

---

### 23. HOTCONFIG SERVICE
**Package:** `com.epicgames.hotconfig`

- Hotconfig - NO AUTH

---

### 24. FN-CONTENT SERVICE
**Package:** `com.epicgames.content`

- ContentKey - NO AUTH
- ContentSubkey - NO AUTH

---

### 25. WEX SERVICE
**Package:** `com.epicgames.wex`

**No perm required (auth only):**
- EnabledFeatures
- VersionCheck
- MOTD
- Catalog operations
- Push notifications

**Other:**
- SearchFriends - Auth required
- ItemRanking - Auth required

---

### 26. WEB SERVICES

**Public endpoints (NO AUTH):**
- `/id/ageGate`
- `/id/client` - Public client info
- `/fortnite/cms` - Content
- `/fortnite/competitive/*` - Events, leaderboards
- `/egs/products/*` - Store data
- `/redeem/*` - Redeem endpoints (some)

**Protected endpoints:**
- `/id/auth/*` - OAuth flow endpoints (various)
- `/fortnite/account/*` - Account info

---

### 27. ADMIN & SYSTEM SERVICES

**EGS Platform Service:**
- Most products/offers endpoints - NO AUTH or minimal
- Subscriptions - `subscription:public:...`

**GraphQL:**
- Various endpoints with different auth

**Nellyservice:**
- Report - NO AUTH
- Task - NO AUTH

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Total Services | 36+ |
| Endpoints | 723+ |
| No Auth Required | 65 |
| Auth + Scope | 388 |
| Auth Only | ~150 |
| Basic Auth | ~20 |

---

## Authentication Pattern Matrix

### By Operation Type

| Operation | Auth Level | Example Service |
|-----------|-----------|-----------------|
| **Read Public Data** | None | PublicKey, ContentKey, Product data |
| **Read Protected Data** | Scope | Friends READ, Stats READ |
| **Create Resource** | Scope | Friends UPDATE, Links CREATE |
| **Update Resource** | Scope | Friends UPDATE, Party UPDATE |
| **Delete Resource** | Scope | Friends DELETE, Links DELETE |
| **Account Operations** | Auth only | Profile updates, Tag management |
| **System Operations** | Basic Auth | EOS services, Admin APIs |

### By Token Type

| Token Type | Services | Count |
|-----------|----------|-------|
| Bearer (default) | Most game APIs, web | 300+ |
| eg1 (JWT) | Messaging, some game APIs | 20+ |
| Basic Auth | EOS, Admin, System | 15+ |
| Discovery Token | Discovery v2 API | 8+ |
| No Auth | Public content | 65 |

---

## Access Control Summary

**Public Access (No Auth):**
- Content distribution
- Product/offer information
- Configuration (hotconfig)
- Service health checks
- OAuth flow helpers

**Account-Scoped (Auth Required):**
- Profile operations
- Friend management
- Party operations
- Game stats
- Cloud storage
- Creative content

**Privileged Operations:**
- Admin/system operations
- EOS service integration
- Launcher operations
- Account corrections

