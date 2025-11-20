# FORTNITE API AUTHENTICATION ANALYSIS - MASTER INDEX

## Overview

This comprehensive analysis explores all **723 markdown documentation files** across **36+ Epic Games API services**, documenting authentication requirements, token types, scopes, and access control patterns.

---

## Key Findings Summary

### Token Types (5 Total)
1. **Bearer Token** (Default) - 16-byte hex, 4-7 hours TTL
2. **eg1 JWT** - Account-specific, game APIs, 2 hours TTL
3. **ep1** - Platform-specific (Xbox, PSN, etc)
4. **epic_id** - EOS integration
5. **id_token** - OpenID Connect

### Authentication Requirements
- **388 endpoints** - Require authentication + OAuth scope
- **65 endpoints** - Require NO authentication (public)
- **150+ endpoints** - Require authentication only (no scope)
- **20+ endpoints** - Require basic auth (clientId:clientSecret)

### Discovery Token (Special)
- **Unique token type** obtained via `/fortnite/api/discovery/accessToken/{branch}`
- **Version-specific** for each Fortnite release
- **Required for FN-Discovery-Service v2 API**
- **Not a standard OAuth token**

---

## Analysis Documents

### 1. AUTHENTICATION_ANALYSIS.md (548 lines)
**Comprehensive deep-dive reference**

Contains:
- Token types and authentication methods (Part 1)
- Creative discovery token details (Part 2)
- Public endpoints catalog (Part 3)
- Service-by-service authentication breakdown (Part 4)
- OAuth scope/permission patterns (Part 5)
- Special cases and restrictions (Part 6)
- Error codes and meanings (Part 7)
- Discovery token usage examples (Part 8)
- Summary statistics (Part 9)
- Key recommendations (Part 10)

**Use when:** You need complete details on any API authentication

---

### 2. QUICK_AUTH_REFERENCE.md (250+ lines)
**Quick lookup guide for developers**

Contains:
- Token types at a glance
- Getting started steps with code examples
- Common OAuth clients list
- Discovery API getting started
- Common authorization scopes
- Public endpoints summary
- Endpoints by auth type
- Headers cheat sheet
- Error codes for auth issues
- Discovery token archive
- Quick integration checklist
- Common mistakes

**Use when:** You need quick answers during development

---

### 3. SERVICES_AUTH_BREAKDOWN.md (350+ lines)
**Complete service inventory**

Contains:
- Authentication requirements for all 27+ services:
  - Account Service
  - FN-Service (Game)
  - FN-Discovery-Service & Search
  - Friends Service
  - Party Service
  - Global Service
  - Stats & Rankings Services
  - Social Services
  - Launcher Service
  - Plus 17 more...
- Summary statistics
- Authentication pattern matrix
- Access control summary

**Use when:** Looking up auth for a specific service

---

## Document Navigation Guide

### If you want to...

**Integrate with Discovery API (Creative Islands)**
1. Read: QUICK_AUTH_REFERENCE.md - Discovery API section
2. Deep dive: AUTHENTICATION_ANALYSIS.md - Part 2 (Creative Discovery Token)
3. Code example: AUTHENTICATION_ANALYSIS.md - Part 8 (Discovery Token Usage)

**Get Friend List or Stats**
1. Quick: QUICK_AUTH_REFERENCE.md - Common Authorization Scopes
2. Details: SERVICES_AUTH_BREAKDOWN.md - Friends Service section
3. Error handling: QUICK_AUTH_REFERENCE.md - Error Codes

**Build OAuth2 Integration**
1. Overview: AUTHENTICATION_ANALYSIS.md - Part 1 (Token Types & Methods)
2. Clients list: QUICK_AUTH_REFERENCE.md - Common OAuth Clients
3. Flow details: AUTHENTICATION_ANALYSIS.md - Part 4 (Account Service)

**Find Public Endpoints**
1. Quick list: QUICK_AUTH_REFERENCE.md - Public Endpoints section
2. Full catalog: AUTHENTICATION_ANALYSIS.md - Part 3
3. By service: SERVICES_AUTH_BREAKDOWN.md - Individual service sections

**Understand OAuth Scopes**
1. Common scopes: QUICK_AUTH_REFERENCE.md - Common Authorization Scopes
2. Full patterns: AUTHENTICATION_ANALYSIS.md - Part 5
3. By service: SERVICES_AUTH_BREAKDOWN.md - Service-specific scopes

**Debug Auth Errors**
1. Error codes: QUICK_AUTH_REFERENCE.md - Error Codes for Auth Issues
2. Full error details: AUTHENTICATION_ANALYSIS.md - Part 7 (Error Messages)

**Set Up Service-to-Service Communication**
1. Method: QUICK_AUTH_REFERENCE.md - Getting Started (Client Credentials)
2. Details: AUTHENTICATION_ANALYSIS.md - Part 1 (Client Credentials Flow)
3. Services: SERVICES_AUTH_BREAKDOWN.md - EOS Services, Admin sections

---

## Key Insights

### Discovery Services Architecture
- **V1 API**: Uses standard OAuth token + URL-based account ID
- **V2 API**: Uses special discovery token + X-Epic-Access-Token header
- **Token Freshness**: Discovery tokens are version-specific
- **Surfaces**: 6 different discovery surfaces for different contexts

### Friends & Social APIs
- **Comprehensive scope model**: Separate READ/UPDATE/DELETE for most operations
- **Account-specific**: All friend operations are scoped to accountId
- **Blocklist support**: Full friend/blocklist management

### Global Profile Operations
- **Minimal scope requirements**: Many operations need auth only, no scope
- **Reboot Rally**: Separate but similar auth model
- **Profile data**: Settings, language, region all supported

### Public Access Patterns
- **Content/Config**: ProductKey, ContentKey, Hotconfig all public
- **Store data**: All product/offer information is public
- **OAuth helpers**: Client info and callback endpoints are public
- **Competitive**: Events and leaderboards are public

---

## Statistics

### By Category
| Item | Count |
|------|-------|
| Total Services | 36+ |
| Total Endpoints | 723+ |
| No Auth Required | 65 |
| Auth + Scope | 388 |
| Auth Only | ~150 |
| Basic Auth Only | ~20 |

### By Service Type
| Type | Count | Examples |
|------|-------|----------|
| Game/Creative | 8 | FN-Service, Discovery, Ranking |
| Social | 5 | Friends, Party, Global, Pops |
| Account | 3 | Account, Auth, Persona |
| Data | 8 | Stats, Events, Assets, Links |
| Platform | 4 | Launcher, EGS, Library, Caldera |
| System | 8+ | Others, Admin, Tools |

### Scope Patterns
- `{service}:{resource}:{permission}` format
- 4 primary operations: READ, CREATE, UPDATE, DELETE
- Account-scoped: `{service}:{accountId}:{resource}:{perm}`
- Namespace-scoped: `{service}:{namespace}:{resource}:{perm}`

---

## Special Cases

### Endpoints Requiring JWT (eg1)
- PRMDialogService (all 4 endpoints)
- Some EOS-Services
- Account correction operations
- Messaging/Dialog operations

### Endpoints Requiring Basic Auth
- EOS-Services (all)
- Some system endpoints
- Device code flows

### Endpoints with "No Perm Required"
- Global Profile operations
- Reboot Rally endpoints
- Some Launcher endpoints
- WexService basic operations
- Lightswitch status checks

### Version-Specific Access
- Discovery token per Fortnite version
- Archive provided for v22.20 through v34.10+
- Some versions missing (v25.20, v31.20)

---

## Common Integration Patterns

### Pattern 1: Game Client (eg1 Token)
```
1. Get OAuth token (fortnitePCGameClient, token_type=eg1)
2. Query discovery token for current version
3. Use eg1 token for game APIs
4. Use discovery token for v2 discovery
5. Refresh tokens before expiration
```

### Pattern 2: Backend Service (Bearer Token)
```
1. Get OAuth token (client_credentials, fortnitePCGameClient)
2. Use bearer token for service APIs
3. Check scope requirements per endpoint
4. Handle 388+ scoped endpoints appropriately
```

### Pattern 3: Web Integration (Multiple Clients)
```
1. Use appropriate web client for domain
2. OAuth2 authorization_code flow
3. Store and rotate refresh tokens
4. Handle account-specific endpoints
```

### Pattern 4: System/Admin (Basic Auth)
```
1. Use clientId:clientSecret directly
2. Basic auth header (base64 encoded)
3. For EOS and system services
4. Limited to specific endpoints
```

---

## Critical Implementation Details

### Token Lifecycle
- **Access token TTL**: 2-14 hours depending on token type
- **Refresh token TTL**: 8+ hours
- **Discovery token**: Valid for duration of Fortnite version
- **Proactive refresh**: Implement before expiration

### Scope Validation
- Account ID must match in URL and token
- Scope must match endpoint requirements
- Some endpoints don't check scopes but still require auth
- Mismatch results in error codes 1024, 1097, 18055

### Header Requirements
- `Authorization: Bearer {token}` - Standard
- `X-Epic-Access-Token: {token}` - Discovery v2 only
- `Authorization: Basic {base64}` - System endpoints
- `Content-Type: application/json` - Often required
- `User-Agent: Fortnite/...` - Sometimes required

### Error Handling
- 1000-1100 range: General auth errors
- 18000-18100 range: OAuth/token errors
- Token verification failed: Get new token
- Account ID mismatch: Verify URL parameters
- Scope issues: Check endpoint documentation

---

## References

### Original Documentation Locations
- **Account Service**: `/EpicGames/AccountService/Authentication/`
- **Discovery Services**: `/EpicGames/FN-Discovery-Service/`
- **Game APIs**: `/EpicGames/FN-Service/Game/`
- **Friends & Social**: `/EpicGames/Friends*/` and `/EpicGames/Pops*/`
- **Launchers & Tools**: `/EpicGames/Launcher*/` and `/EpicGames/WexService/`
- **All Error Codes**: `/EpicGames/Errors.md`

### OAuth Clients
- **Complete list**: `/EpicGames/AccountService/Authentication/Clients.md` (100+ clients)
- **Main game client**: `fortnitePCGameClient` (ID: `ec684b8c687f479fadea3cb2ad83f5c6`)

### Token Details
- **Token endpoint**: `/EpicGames/AccountService/Authentication/Token.md`
- **Token verification**: `/EpicGames/AccountService/Authentication/Verify.md`
- **Discovery token**: `/EpicGames/FN-Service/Game/Creative/DiscoveryAccessToken.md`

---

## Maintenance Notes

### Document Coverage
- Analyzed: 723 markdown files
- Services: 36+ documented
- Endpoints: 453+ documented (388 auth required, 65 public)
- Last major version: Fortnite v34.10+ (Discovery token included)

### Known Gaps
- Some v3 endpoints may not be documented
- Deprecated endpoints not fully listed
- Admin/internal APIs not public
- Real-time rate limits not documented
- Regional variations not specified

---

## How to Use These Documents

### For Quick Lookups
Start with **QUICK_AUTH_REFERENCE.md** - Most common questions answered in tables and examples.

### For Full Understanding
Read **AUTHENTICATION_ANALYSIS.md** in order - Builds comprehensive knowledge from basics to advanced.

### For Service Integration
Use **SERVICES_AUTH_BREAKDOWN.md** - Find your service, see all auth requirements.

### For Production Implementation
1. Review QUICK_AUTH_REFERENCE.md - Integration checklist
2. Implement error handling from error code table
3. Set up token refresh logic from token lifecycle section
4. Test with public endpoints first
5. Validate all headers and scopes

---

## Contact & Updates

These documents were generated from analysis of FortniteEndpointsDocumentation directory.
For latest API changes, always check official Epic Games documentation endpoints.

Last analyzed: November 2024
Total analysis time: Comprehensive
Analysis method: Pattern-based search across 723+ markdown files

---

**Start with your specific need and reference the appropriate document above.**
