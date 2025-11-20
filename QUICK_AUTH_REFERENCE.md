# FORTNITE API AUTHENTICATION - QUICK REFERENCE

## Token Types at a Glance

| Token Type | When to Use | Prefix | Duration | Example |
|-----------|-----------|--------|----------|---------|
| **Bearer** | General APIs, public endpoints | None | 4 hours | `266e2719635f4a899e94bd19c4422a90` |
| **eg1** | Game APIs, account-specific | `eg1~` | 2 hours | `eg1~eyJhbGc...` |
| **ep1** | Platform auth (Xbox, PSN, etc) | `ep1~` | Variable | `ep1~encrypted...` |
| **epic_id** | EOS integration | None | Variable | JWT token |
| **id_token** | OpenID Connect / EOS | None | Variable | JWT token |

---

## Getting Started

### Step 1: Get OAuth Token (Client Credentials)
```bash
curl -X POST https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token \
  -H "Authorization: Basic $(echo -n 'ec684b8c687f479fadea3cb2ad83f5c6:e1f31c211f28413186262d37a13fc84d' | base64)" \
  -d "grant_type=client_credentials"
```

**Response:**
```json
{
  "access_token": "your_token_here",
  "expires_in": 14400,
  "token_type": "bearer"
}
```

### Step 2: Use Token in API Calls
```bash
curl -H "Authorization: Bearer your_token_here" \
  https://api.example.com/endpoint
```

---

## Common OAuth Clients

| Client | Use Case | ID |
|--------|----------|-----|
| **fortnitePCGameClient** | PC Game | `ec684b8c687f479fadea3cb2ad83f5c6` |
| **fortniteIOSGameClient** | iOS | `3446cd72694c4a4485d81b77adbb2141` |
| **fortniteSwitchGameClient** | Nintendo Switch | `5229dcd3ac3845208b496649092f251b` |
| **fortniteAndroidGameClient** | Android | `3f69e56c7649492c8cc29f1af08a8a12` |
| **launcherAppClient2** | Epic Launcher | `34a02cf8f4414e29b15921876da36f9a` |

See `/EpicGames/AccountService/Authentication/Clients.md` for full list.

---

## Discovery API (Creative)

### Get Discovery Token
```bash
# For a specific Fortnite version
curl -H "Authorization: Bearer {eg1_token}" \
  https://fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api/discovery/accessToken/++Fortnite+Release-34.10
```

**Response:**
```json
{
  "token": "6liJ9OTYJpwtx0+jApUc/OYtq2eHDXFHTIp4nfJgduc=",
  "branchName": "++Fortnite+Release-34.10",
  "appId": "Fortnite"
}
```

### Use Discovery Token (V2 API)
```bash
curl -X POST https://fn-service-discovery-live-public.ogs.live.on.epicgames.com/api/v2/discovery/surface/CreativeDiscoverySurface_Frontend \
  -H "X-Epic-Access-Token: {discovery_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "playerId": "your_account_id",
    "partyMemberIds": [],
    "accountLevel": 100,
    "battlepassLevel": 100,
    "locale": "en",
    "matchmakingRegion": "NA",
    "platform": "Windows",
    "isCabined": false
  }'
```

---

## Common Authorization Scopes

### Discovery Services
- `discovery:{accountId}:surface:query READ` - Query discovery surfaces
- `discovery:{accountId}:links:favorite READ` - Read favorite links
- `discovery:search:{accountId} READ` - Search links/creators
- `fortnite:discovery:fortnite READ` - Get discovery token

### Friends Service
- `friends:{accountId} READ` - Read friends list
- `friends:{accountId} UPDATE` - Add/modify friends
- `friends:{accountId} DELETE` - Remove friends

### Party Service
- `social:party` - All party operations

### Stats & Rankings
- `fortnite:stats READ` - Read player stats
- `rankings:{namespace}:tracks READ` - Read ranking info

### Global Profile
- No permission required (auth only) - Profile operations
- No permission required - Reboot Rally endpoints

### Game Services
- `fortnite:{operation}:fortnite READ` - General game operations
- `launcher:download:{label}:{appName} READ` - Download specific version

---

## Public Endpoints (No Auth Needed)

These can be called without any token:

**Content:**
- `/account/api/public/account/{accountId}/publicKey` - JWT verification
- `/fortnite/api/v2/content` - Static content
- `/hotconfig` - Server configuration

**Web:**
- `/id/ageGate` - Age verification
- `/fortnite/cms` - Content management
- `/fortnite/competitive/` - Event data
- `/egs/products` - Store data

**Launcher:**
- `/launcher/api/v1/distributionhosts` - Download locations
- `/launcher/api/v1/installers` - Installer info

**Service Info:**
- `/ipdata/v1/healthcheck` - Service health

---

## Discovery Surfaces

These are queryable via Discovery API:

| Surface | Purpose |
|---------|---------|
| `CreativeDiscoverySurface_Frontend` | Main discovery home |
| `CreativeDiscoverySurface_Browse` | Browse islands |
| `CreativeDiscoverySurface_Library` | Player's saved islands |
| `CreativeDiscoverySurface_EpicPage` | Epic Games featured |
| `CreativeDiscoverySurface_CreatorPage` | Creator pages |
| `CreativeDiscoverySurface_DelMar_TrackAndExperience` | Rocket Racing |

---

## Endpoints by Auth Type

### No Auth Required (65 total)
- Client info endpoints
- Age gate
- Product/offer data
- Competitive data (leaderboards, events)
- Distribution/installer info
- Service health checks

### Account Auth Only (No Scope)
- Tag management (all)
- Global profile updates
- Reboot Rally
- Library operations
- Account corrections
- Device code flows

### Auth + Specific Scope (388 total)
- Discovery APIs: `discovery:*`
- Friends APIs: `friends:*`
- Party APIs: `social:party`
- Stats APIs: `fortnite:stats`
- Game APIs: `fortnite:*`
- And many more...

### JWT (eg1) Required
- PRM Dialog Service (messaging)
- Some EOS services
- Some account operations

### Basic Auth Required
- EOS Services (direct clientId:clientSecret)
- Some admin/system endpoints

---

## Headers Cheat Sheet

### Standard Authorization
```
Authorization: Bearer {token}
```

### Discovery Token
```
X-Epic-Access-Token: {discovery_token}
```

### Basic Auth (clientId:clientSecret)
```
Authorization: Basic {base64(clientId:clientSecret)}
```

### Content Type
```
Content-Type: application/x-www-form-urlencoded
OR
Content-Type: application/json
```

### Additional
```
User-Agent: Fortnite/++Fortnite+Release-X.XX
X-Epic-Device-ID: {random_device_id}
```

---

## Error Codes for Auth Issues

| Error | Meaning | Solution |
|-------|---------|----------|
| `1002, 1031, 1032` | Token verification failed | Get new token |
| `1003` | Only epic_id allowed | Use eg1 or epic_id token |
| `1024` | Account auth required | Use account token, not client |
| `1097` | Client auth required | Use client credentials |
| `18001` | OAuth code not found/invalid | Get new exchange code |
| `18055` | AccountID mismatch | Verify URL accountId matches token |
| `18071` | Invalid access token | Get fresh token |

---

## Discovery Token Archive

Available versions with pre-computed tokens:
- v22.20 through v34.10+
- Missing: v25.20, v31.20
- Located in: `/EpicGames/FN-Service/Game/Creative/DiscoveryAccessToken.md`

---

## Quick Integration Checklist

- [ ] Obtain client credentials (ID + Secret)
- [ ] Get OAuth token for your client
- [ ] Determine required OAuth scopes for your endpoints
- [ ] Build Authorization header correctly
- [ ] For Discovery: Get discovery token for current version
- [ ] Implement token refresh before expiration
- [ ] Handle auth error responses (1xxx, 18xxx codes)
- [ ] Test with public endpoints first
- [ ] Validate all required headers present

---

## Key Files in Documentation

| File | Purpose |
|------|---------|
| `/AccountService/Authentication/README.md` | Auth overview & flows |
| `/AccountService/Authentication/Token.md` | Token endpoint details |
| `/AccountService/Authentication/Clients.md` | OAuth clients list |
| `/FN-Service/Game/Creative/DiscoveryAccessToken.md` | Discovery tokens |
| `/FN-Discovery-Service/README.md` | Discovery service guide |
| `/FN-Discovery-Service/Discovery/V2/Main.md` | V2 API details |
| `/Errors.md` | All error codes |

---

## Common Mistakes

1. **Using opaque token for JWT endpoints** - Use eg1 token instead
2. **Not refreshing expired tokens** - Access tokens expire in 2-7 hours
3. **Wrong authorization header format** - Must be `Bearer {token}` or `Basic {base64}`
4. **Missing discovery token** - V2 API requires special token, not OAuth
5. **AccountID mismatch** - URL accountId must match token's accountId
6. **Not including required scopes** - Some endpoints need specific permissions
7. **Forgetting content-type header** - Often required for POST/PUT

---

Generated from analysis of 723 endpoint files across 36+ Epic Games services.
