# Fortnite Cosmetics API Integration

## Data Sources Overview

FA11y uses multiple data sources for cosmetics:

### 1. **Epic Games API** (User-Owned Cosmetics)
- **Purpose**: Get list of cosmetics owned by the authenticated user
- **Endpoint**: `fortnite/api/game/v2/profile/{accountId}/client/QueryProfile`
- **Returns**: Template IDs like `"AthenaCharacter:CID_123_Athena"`
- **Usage**: Check what cosmetics the user owns

**Example owned cosmetic ID:**
```
"AthenaCharacter:cid_035_athena_commando_m_medieval"
```

### 2. **Fortnite-API.com** (Complete Cosmetics Database)
- **Purpose**: Get metadata for all Fortnite cosmetics
- **Endpoint**: `https://fortnite-api.com/v2/cosmetics/br`
- **Returns**: JSON with detailed cosmetic info (name, rarity, description, etc.)
- **ID Format**: String IDs matching Epic's format (e.g., `"CID_035_Athena_Commando_M_Medieval"`)

**Example cosmetic from Fortnite-API.com:**
```json
{
  "id": "CID_035_Athena_Commando_M_Medieval",
  "name": "Blue Squire",
  "description": "He's a good dude.",
  "type": {
    "value": "outfit",
    "backendValue": "AthenaCharacter"
  },
  "rarity": {
    "value": "rare",
    "backendValue": "EFortRarity::Rare"
  },
  "introduction": {
    "chapter": "1",
    "season": "2"
  }
}
```

### 3. **Fortnite.gg** (Alternative Database)
- **Purpose**: Fast lookup, additional metadata, release history
- **Endpoint**: `https://fortnite.gg/data/items/all-v2.en.js`
- **Returns**: JavaScript file with numeric IDs
- **ID Format**: Numeric (e.g., `20727`)
- **Additional Data**: Sets, rarities, occurrences, last seen dates

**Example item from Fortnite.gg:**
```javascript
{
  id: 20727,
  type: 1,  // 1 = Outfit
  t: [12],
  C: [2,8,12,11,10],
  set: 1,   // Index into Sets array
  source: 1,
  r: 4,     // 4 = Epic rarity
  rarity: 4,
  added: 251117,
  name: "Mothmando Elite",
  img: 1,
  p: 800,   // V-Bucks price
  season: 38
}
```

## Current Implementation

### How the Locker GUI Works:

1. **Load Cosmetics Database**: Uses Fortnite-API.com via `get_or_create_cosmetics_cache()`
   - Provides detailed metadata (name, description, rarity, etc.)
   - Uses string IDs that match Epic's owned cosmetics

2. **Check Owned Items**: Fetches user's owned cosmetics from Epic Games API
   - Returns template IDs like `"AthenaCharacter:CID_123_Athena"`
   - Strips prefix to get `"CID_123_Athena"`

3. **Match and Display**: Matches owned IDs with the cosmetics database
   - Shows only owned cosmetics when filtered
   - Displays metadata from Fortnite-API.com

## Using the New Fortnite.gg Service

The new `fortnite_cosmetics.py` service provides:

### Basic Usage:

```python
from lib.utilities.fortnite_cosmetics import get_cosmetics_service

# Get the service instance
service = get_cosmetics_service()

# Fetch all items
items = service.fetch_items_list()
print(f"Loaded {len(items)} items")

# Search for an item
results = service.search_items("Mothmando")
for item in results:
    print(f"{item['name']} (ID: {item['id']}, Rarity: {item['r']})")

# Get item details (with Character ID)
details = service.fetch_item_details(20727)
if details:
    print(f"Character ID: {details.get('character_id')}")  # e.g., "Character_BugBandit"
    print(f"Set: {details.get('set_name')}")               # e.g., "Moth Command"
    print(f"Last Seen: {details.get('last_seen')}")        # e.g., "Nov 19, 2025"
```

### Advanced Filtering:

```python
# Get all Epic rarity items
epic_items = service.get_items_by_rarity(4)

# Get all Outfits (type 1)
outfits = service.get_items_by_type(1)

# Get items from a specific set
set_items = service.get_items_by_set(1)
set_name = service.get_set_name(1)
print(f"Items in '{set_name}' set: {len(set_items)}")
```

## Can We Use Fortnite.gg Data Instead?

**Short answer:** Not directly, but it can supplement the existing system.

**Challenges:**
1. **Different ID formats**: Fortnite.gg uses numeric IDs (20727), while Epic and Fortnite-API use string IDs ("CID_035_Athena_Commando_M_Medieval")
2. **No direct mapping**: There's no built-in way to map Fortnite.gg IDs to Epic template IDs
3. **The locker GUI relies on string IDs** to match owned cosmetics from Epic's API

**Best Use Cases for Fortnite.gg:**
- ✅ **Get Character IDs**: Extract the backend ID like `"Character_BugBandit"`
- ✅ **Release History**: See when items were last in the shop
- ✅ **Set Information**: Browse items by set
- ✅ **Fast Lookups**: The JavaScript file is smaller and faster to parse
- ✅ **Pricing Data**: V-Bucks prices included

**Recommendation:**
Use **both** data sources:
- **Fortnite-API.com**: Primary source for the locker GUI (matches Epic's ID format)
- **Fortnite.gg**: Supplementary source for additional details (Character IDs, release dates, set info)

## Type and Rarity Reference

### Item Types (Fortnite.gg):
```python
1  = Outfit
2  = Back Bling
3  = Pickaxe
4  = Glider
5  = Aura
6  = Emote
7  = Wrap
9  = Contrail
10 = Loading Screen
20 = Music
31 = Shoes (Kicks)
32 = Pet
```

### Rarities (Fortnite.gg):
```python
1  = Common (Gray)
2  = Uncommon (Green)
3  = Rare (Blue)
4  = Epic (Purple)
5  = Legendary (Orange)
11 = Mythic (Gold)
```

## Caching Behavior

### Fortnite.gg Service:
- **Items List**: Cached for 24 hours in `config/cosmetics_cache/fortnite_gg_items.json`
- **Item Details**: Cached for 7 days in `config/cosmetics_cache/item_details/{item_id}.json`
- **Rate Limiting**: 0.5 second delay between API requests

### Fortnite-API.com (existing):
- Cached in `config/cosmetics_cache.json` (check `epic_auth.py` for expiry)

## Future Integration Ideas

1. **Hybrid System**: Use Fortnite-API.com for the main database, fetch additional details from Fortnite.gg when viewing an item
2. **ID Mapping**: Create a mapping table between Fortnite.gg numeric IDs and Epic string IDs (would require manual creation or pattern matching)
3. **Shop History**: Use Fortnite.gg to show when cosmetics were last available in the shop
4. **Set Browser**: Create a UI to browse cosmetics by set using Fortnite.gg data
