# FORTNITE API AUTHENTICATION ANALYSIS - COMPREHENSIVE REPORT

## EXECUTIVE SUMMARY

Analysis of 723 markdown files across 36+ Epic Games services reveals a complex authentication landscape with:
- **388 endpoints requiring authentication**
- **65 public/no-auth-required endpoints**
- **5 token types** (opaque bearer, eg1 JWT, ep1 encrypted JWT, epic_id JWT, id_token OpenID)
- **Special creative discovery token** for Discovery Service v2 access
- **Fine-grained OAuth scopes** controlling endpoint access

---

## PART 1: TOKEN TYPES & AUTHENTICATION METHODS

### Token Types Available

| Token Type | Format | Use Case | Notes |
|-----------|--------|----------|-------|
| **Bearer (Default)** | 16-byte hexadecimal (e.g., `266e2719635f4a899e94bd19c4422a90`) | General API access | Most common, obtained via OAuth2 |
| **eg1 (JWT)** | Signed JWT prefixed `eg1~` | Account-based API access, Fortnite game clients | Required for many account-specific endpoints |
| **ep1** | Encrypted JWT prefixed `ep1~` | Platform-specific auth | From external_auth grant or PlatformToken API |
| **epic_id** | Signed JWT for EOS | EOS integration | From EOS Auth Web APIs |
| **id_token** | OpenID Connect JWT | EOS with openid scope | From EOS Auth Web APIs with `openid` scope |

### Authentication Methods

#### 1. **Client Credentials Flow** (Service-to-Service)
```
POST /account/api/oauth/token
Authorization: Basic {base64(clientId:clientSecret)}
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
```
- Returns opaque bearer token
- No account association
- Used for public/system services

#### 2. **Account Authentication** (User-Specific)
```
POST /account/api/oauth/token
Authorization: Basic {base64(clientId:clientSecret)}
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code={AUTHORIZATION_CODE}&token_type=eg1
```
- Returns access token + refresh token + account_id
- Can use `token_type=eg1` for JWT format
- Recommended for most game clients

#### 3. **Basic Authentication** (Direct)
- Username: Client ID
- Password: Client Secret
- Base64 encoded in Authorization header
- Used for: LauncherService, EOS Services, some admin APIs

---

## PART 2: CREATIVE DISCOVERY TOKEN

### What is it?
A special **base64-encoded bearer token** used exclusively for the **FN-Discovery-Service v2 APIs**. It's distinct from normal OAuth tokens and is **version-specific** (tied to Fortnite build branches).

### How to Obtain It
```
GET https://fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api/discovery/accessToken/{branch}
Headers:
  Authorization: Bearer {eg1_token}

Authentication Required: Yes (`fortnite:discovery:fortnite READ`)
```

**Parameters:**
- `branch`: Fortnite build identifier (e.g., `++Fortnite+Release-31.30`)

**Response:**
```json
{
  "branchName": "++Fortnite+Release-31.30",
  "appId": "Fortnite",
  "token": "6liJ9OTYJpwtx0+jApUc/OYtq2eHDXFHTIp4nfJgduc="
}
```

### What It Accesses
The discovery token grants access to:
1. **FN-Discovery-Service v2 endpoints** (newer surface queries)
2. Requires header: `X-Epic-Access-Token: {discovery_token}`
3. Does NOT provide standard OAuth scopes

### Discovery Tokens by Version
The documentation includes an archive of tokens for multiple versions:
- Available for: v22.20 through v34.10+
- Some versions missing (e.g., v25.20, v31.20)
- Used for querying discovery surfaces with player context

---

## PART 3: PUBLIC ENDPOINTS (No Authentication)

**65 endpoints require NO authentication:**

### By Service:

**Web Services (No Auth):**
- AgeGate
- Client (public client info)
- Failure/Location/SetSessionID
- EulaLatest
- Competitive data (cms, leaderboards, events)
- Product info (products, offers, ratings)
- Creative/Cosplay/Data endpoints

**Game Services (No Auth):**
- ContentKey/ContentSubkey (FN-Content)
- FN-Hotconfig
- IPDataService/HealthCheck (not RegionCheck which requires auth)
- LauncherService (DistributionHosts, Installer)
- NellyService (Report, Task)
- WexService (Manifests)

**Account Services (No Auth):**
- AccountService/PublicKey
- Web/Id endpoints for OAuth flow (DeviceCode Info, ExchangeCode Info, etc.)

---

## PART 4: AUTHENTICATION BY SERVICE

### DISCOVERY SERVICES

#### FN-Discovery-Service (Main)
**Package:** `com.epicgames.discovery`

**Surfaces Available:**
| Surface | Endpoint | Auth Required |
|---------|----------|---|
| CreativeDiscoverySurface_Frontend | V1/V2 Main | Yes: `discovery:{accountId}:surface:query READ` |
| CreativeDiscoverySurface_Browse | V1/V2 Main | Yes: `discovery:{accountId}:surface:query READ` |
| CreativeDiscoverySurface_Library | V1/V2 Main | Yes: `discovery:{accountId}:surface:query READ` |
| CreativeDiscoverySurface_DelMar_TrackAndExperience | V1/V2 Main | Yes: `discovery:{accountId}:surface:query READ` |
| CreativeDiscoverySurface_EpicPage | V1/V2 Main | Yes: `discovery:{accountId}:surface:query READ` |

**Endpoints:**
- `POST /api/v1/discovery/surface/{accountId}` - V1 Query (OAuth token)
- `POST /api/v2/discovery/surface/{surfaceName}` - V2 Query (Discovery token via `X-Epic-Access-Token` header)
- `POST /api/v1/discovery/surface/page/{accountId}` - V1 Page query
- `POST /api/v2/discovery/surface/page/{surfaceName}` - V2 Page query
- `GET /api/v1/discovery/hub/portals` - Hub portals

**Links Management:**
- Favorites: Add/Remove/List/Check - `discovery:{accountId}:links:favorite {CREATE/DELETE/READ}`
- History: Add/Remove/List - `discovery:{accountId}:links:history {CREATE/DELETE/READ}`
- Lock-Management: List/Check/Unlock - `discovery:{accountId}:links:lock-management {READ/UPDATE/DELETE}`
- Queue: Add/List - `discovery:{accountId}:links:queue {CREATE/READ}`

**Creator Pages:**
- `GET /api/v1/creator/page/{creatorAccountId}` - Creator islands page
- Auth: `discovery:{accountId}:creator:page READ`

#### FN-Discovery-Search-Service
**Package:** `com.epicgames.dbs.discovery`

**Endpoints:**
- `POST /api/v1/search/links` - Search discovery links
  - Auth: `discovery:search:{accountId} READ`
- `POST /api/v1/search/creators` - Search creator pages
  - Auth: `discovery:search:{accountId} READ`

---

### ACCOUNT SERVICE (Authentication)

**Critical Endpoints:**

1. **Token Generation**
   - `POST /account/api/oauth/token`
   - Auth: Basic Auth (clientId:clientSecret)
   - Methods: client_credentials, authorization_code, refresh_token, external_auth, device_code, etc.

2. **Token Verification**
   - `GET /account/api/oauth/verify` - Verify token validity
   - Auth: Yes (implicit - using token being verified)

3. **Token Info (EpicId)**
   - `POST /account/api/epicid/v1/oauth/tokenInfo`
   - Auth: Yes (in Body, not Authorization header)

4. **Token Permissions**
   - `GET /account/api/oauth/permissions`
   - Auth: Yes

5. **PublicKey**
   - `GET /account/api/public/account/{accountId}/publicKey`
   - Auth: NO

6. **Clients List**
   - Contains 100+ registered OAuth clients
   - Examples: fortnitePCGameClient, fortniteIOSGameClient, launcherAppClient2, etc.

---

### GAME SERVICES (FN-Service)

**Creative Discovery Access Token:**
- `GET /fortnite/api/discovery/accessToken/{branch}`
- Auth: Yes (`fortnite:discovery:fortnite READ`)
- Returns: Version-specific discovery token for v2 APIs

**Profile & Stats:**
- Most endpoints require: `fortnite:{operation}:fortnite READ` or similar
- Examples: Stats, Catalog, Calendar, CloudStorage operations

**Entitlements:**
- EntitlementCheck - Auth required (no specific perm listed)
- EntitlementRequestAccess - Auth required

---

### FRIENDS SERVICE

**All endpoints require:** `friends:{accountId} {READ/UPDATE/DELETE}`

**Operations:**
- FriendsList - READ
- OutgoingFriendRequests - READ
- IncomingFriendRequests - READ
- Summary - READ
- Add Friend - UPDATE
- Remove Friend - DELETE
- Friend Mutuals - READ
- Friend Info - READ
- Alias operations (Edit/Remove) - UPDATE
- Note operations (Edit/Remove) - UPDATE
- AcceptBulk - UPDATE
- ClearFriendsList - DELETE
- SuggestedFriends - READ
- PrivacySettings - READ/UPDATE
- ExternalSourceSettings - READ/UPDATE
- Blocklist (Block/Unblock/List) - UPDATE/DELETE/READ

---

### PARTY SERVICE

**All endpoints require:** `social:party`

**Operations:**
- PartyInfo - READ (via query)
- UpdateParty - UPDATE
- UpdatePartyMember - UPDATE
- Leave - DELETE (implicit)
- Join - CREATE (implicit)
- Invite - CREATE
- SendRequestToJoin - CREATE
- Promote - UPDATE
- PingInfo - READ

---

### STATS & RANKINGS

**StatsProxyService:**
- UserStats - `fortnite:stats READ`
- UserStatsBulk - `fortnite:stats READ`
- Leaderboard - `fortnite:stats READ`

**FN-Habanero-Service (Ranked):**
- Tracks/Info - `rankings:{namespace}:tracks READ`
- Tracks/List - `rankings:{namespace}:tracks READ`
- Progress endpoints - Various ranking scopes

---

### GLOBAL SERVICE

**Profile Operations:**
- Profiles - `No Perm required` (but Auth: Yes)
- PrivacySettings - `No Perm required`
- LanguageUpdate - `No Perm required`
- RegionUpdate - `No Perm required`
- PrivacySettingsUpdate - `No Perm required`

**Reboot Rally:**
- All endpoints: `No Perm required` (but Auth: Yes)

---

### PRM DIALOG SERVICE (Messaging)

**All endpoints require:** Account Auth (eg1 JWT)
- ChannelTarget - eg1
- Interactions - eg1
- InteractionsContentHash - eg1
- SurfaceTarget - eg1

---

### SOCIAL SERVICES

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

### LAUNCHER SERVICE

**Premium/Commercial:**
- Purchase/CheckOffers - `launcher:purchase:offers READ`
- Assets endpoints - `launcher:download:{label}:{appName} READ`
- Library/Items - `launcher:library:items READ`

**Distribution:**
- DistributionHosts - NO AUTH
- Installer - NO AUTH

---

### TAG MANAGEMENT

**All Tag endpoints require:** Account Auth (no scope specified, implies generic account access)
- UpdateOwnTags
- UserTagsBulk
- TagsList
- OwnTags

---

### MISCELLANEOUS SERVICES

**IPDataService:**
- Region - `ipdata:region READ` (Auth required)
- RegionCheck - `ipdata:region READ` (Auth required)
- HealthCheck - NO AUTH

**Links Service (Mnemonics):**
- Most endpoints: `links:{namespace} READ`
- Create operations: `links:{namespace}:{accountId} CREATE`
- Update operations: `links:{namespace}:{accountId} UPDATE`
- Privileged create: `links:{namespace}:privileged_only CREATE`

**Lightswitch Service:**
- Status/StatusBulk - Auth required, no perm needed

**Events Service:**
- Most endpoints: `{gameId}:profile:{accountId}:commands READ`
- Leaderboard: `{gameId}:profile:{accountId}:commands READ`
- History/CreateEventWindowSession: `{gameId}:matchmaking:session UPDATE`

**Data Asset Directory:**
- Assets - `dad:{gameId}:assets:* READ`

**Artifact Delivery:**
- Patch - `delivery:public:patch:{accountId} READ`
- DownloadURLs - `delivery:public:downloadurls:{accountId} READ`

**Emerald Service:**
- Upload operations - `emerald:upload CREATE`

**KWS (Kids Web Services):**
- Update - `epic-settings:public:games:{game} UPDATE`
- Definitions - `epic-settings:public:games:{game} READ`
- SendVerifyEmail - Auth required

**WASP Service (Creative Worlds):**
- World operations - Auth required
- Invite operations - Auth required
- Grant operations - Auth required

---

## PART 5: SCOPE/PERMISSION PATTERNS

### Common Permission Structures

**Format:** `{service}:{accountId}:{resource}:{permission}`

**Operations:**
- `READ` - GET/Query operations
- `CREATE` - POST operations, new resources
- `UPDATE` - PUT/PATCH operations, modifications
- `DELETE` - DELETE operations, removal
- Combined: `READ`, `READ/UPDATE`, `CREATE/READ`, etc.

**Scope Examples:**
- `friends:{accountId} READ` - Read friend lists
- `social:party` - Full party access
- `discovery:{accountId}:surface:query READ` - Query discovery surfaces
- `fortnite:discovery:fortnite READ` - Get discovery token
- `launcher:download:{label}:{appName} READ` - Download specific app version
- `dad:{gameId}:assets:* READ` - Read all assets for game

---

## PART 6: SPECIAL CASES & RESTRICTIONS

### Account Auth Required (No Specific Perm)
Endpoints that need authenticated user but don't specify scope:
- TagManagementService (all)
- Global service profile operations
- Reboot Rally endpoints
- WexService basic operations
- Lightswitch status checks
- Library operations
- Account corrections
- Device code operations

### No Permission Required (But Auth Needed)
```
Auth Required: Yes (No Perm required)
```
These endpoints authenticate user but don't check scopes:
- GlobalService/Profile/* (Profiles, PrivacySettings, LanguageUpdate, RegionUpdate)
- GlobalService/RebootRally/* (Me, Friends, User)
- LauncherService/Assets/V2/* (GetLauncherBuild, GetLauncherBuildAdvanced)
- WexService/Game/* (EnabledFeatures, VersionCheck, MOTD, etc.)
- Lightswitch (Status, StatusBulk)
- Some Library endpoints

### JWT-Specific Requirements
Endpoints requiring **eg1 (JWT) token specifically:**
- PRMDialogService (all 4 endpoints)
- Some account correction endpoints
- EOS-Services endpoints

### Basic Auth Only
Services requiring **Basic Authentication (clientId:clientSecret)**:
- EOS-Services (all endpoints)
- Some account endpoints
- Device code flows

---

## PART 7: BLOCKED/UNAVAILABLE PATTERNS

### No Public List of Blocked APIs
Based on error codes, these are blocked rather than unavailable:
- APIs requiring client_only auth when using account token
- APIs restricted to specific clients
- APIs with IP restrictions
- Unimplemented endpoints (various v3, deprecated versions)

### Error Messages for Auth Failures
- `errors.com.epicgames.forbidden` - Only epic_id tokens allowed
- `errors.com.epicgames.common.client_auth_required` - Needs client credentials
- `errors.com.epicgames.common.user_required` - Needs user token
- `errors.com.epicgames.service_unavailable` - Token verification failed
- `errors.com.epicgames.account.xbl.invalid_token` - Platform token issues

---

## PART 8: DISCOVERY TOKEN USAGE EXAMPLE

### Getting Current Discovery Token
```bash
# Get token for current branch
BRANCH="++Fortnite+Release-34.10"
TOKEN=$(curl -s "https://fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api/discovery/accessToken/${BRANCH}" \
  -H "Authorization: Bearer {YOUR_EG1_TOKEN}" | jq -r '.token')
```

### Using Discovery Token (V2 API)
```bash
curl -X POST "https://fn-service-discovery-live-public.ogs.live.on.epicgames.com/api/v2/discovery/surface/CreativeDiscoverySurface_Frontend?appId=Fortnite&stream=${ENCODED_BRANCH}" \
  -H "X-Epic-Access-Token: ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "playerId": "YOUR_ACCOUNT_ID",
    "partyMemberIds": [],
    "accountLevel": 100,
    "battlepassLevel": 100,
    "locale": "en",
    "matchmakingRegion": "NA",
    "platform": "Windows",
    "isCabined": false,
    "ratingAuthority": "USK",
    "rating": "USK_AGE_12",
    "numLocalPlayers": 1
  }'
```

---

## PART 9: SUMMARY TABLE

| Category | Count | Examples |
|----------|-------|----------|
| **Total Endpoints** | 723 | Across 36+ services |
| **Auth Required** | 388 | ~54% |
| **Public Endpoints** | 65 | ~9% |
| **Token Types** | 5 | Bearer, eg1, ep1, epic_id, id_token |
| **OAuth Clients** | 100+ | Game clients, web, launcher, tools |
| **Services** | 36+ | FN-Service, Friends, Party, Discovery, etc. |
| **Scope Types** | 4+ | READ, CREATE, UPDATE, DELETE |

---

## PART 10: KEY RECOMMENDATIONS

1. **For Game Clients:**
   - Use `fortnitePCGameClient` credentials with `authorization_code` grant + `token_type=eg1`
   - Obtain discovery token for each new Fortnite version

2. **For Service-to-Service:**
   - Use `client_credentials` grant
   - Store client secrets securely

3. **For Web Integrations:**
   - Use appropriate client ID for your platform
   - Store refresh tokens securely
   - Rotate tokens regularly

4. **For Discovery API:**
   - Always fetch fresh token for current branch
   - Use v2 API with discovery token (newer)
   - V1 API also available but requires OAuth token instead

5. **Token Management:**
   - Access tokens: typically 4-7 hours TTL
   - Refresh tokens: typically 8+ hours TTL
   - Monitor expiration times and refresh proactively

---

## APPENDIX: FILE LOCATIONS

**Key Documentation Files:**
- `/EpicGames/AccountService/Authentication/README.md` - Auth overview
- `/EpicGames/AccountService/Authentication/Token.md` - Token endpoint
- `/EpicGames/FN-Service/Game/Creative/DiscoveryAccessToken.md` - Discovery token
- `/EpicGames/FN-Discovery-Service/Discovery/V2/Main.md` - V2 Discovery API
- `/EpicGames/FN-Discovery-Service/README.md` - Discovery service overview
- `/EpicGames/AccountService/Authentication/Clients.md` - OAuth clients list

**Total Files Analyzed:** 723 markdown files
**Services Covered:** 36+
**Endpoints Documented:** 388+ with auth, 65+ without auth
