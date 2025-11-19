# Complete Fortnite API Integration Guide

## 🎯 What We Can Do Now

With the new Fortnite API integration, you can:

### ✅ **Direct Cosmetic Equipping** (No UI Automation!)
- Equip cosmetics via API (instant, reliable)
- Set variants/styles programmatically
- Equip multiple items at once
- Manage favorites
- Get current loadout

### ✅ **Data Sources**
1. **Epic Games API** - User's owned cosmetics + equipping
2. **Fortnite-API.com** - Complete cosmetics database with proper CIDs
3. **Fortnite.gg** - Supplementary data (sets, release dates, character IDs)

## 📊 Understanding the ID Formats

### Epic Games API (What You Own)
```
Template ID: "AthenaCharacter:CID_029_Athena_Commando_F_Halloween"
           ↓
Format: "{BackendType}:{CosmeticID}"
```

**Examples:**
- Outfit: `AthenaCharacter:CID_035_Athena_Commando_M_Medieval`
- Back Bling: `AthenaBackpack:BID_123_BlackKnight`
- Pickaxe: `AthenaPickaxe:Pickaxe_ID_029_Medieval`
- Emote: `AthenaDance:EID_DanceMoves`

### Fortnite-API.com (Complete Database)
```json
{
  "id": "CID_035_Athena_Commando_M_Medieval",  ← Matches Epic's format!
  "name": "Blue Squire",
  "type": {
    "backendValue": "AthenaCharacter"  ← Backend type
  }
}
```

**This matches perfectly with Epic's template IDs!**

### Fortnite.gg (Supplementary Data)
```javascript
{
  id: 20727,  ← Numeric ID (Fortnite.gg specific)
  name: "Mothmando Elite",
  type: 1  ← 1 = Outfit
}
```

**Item Details:**
```
Character ID: "Character_BugBandit"  ← Asset/pak name (NOT the CID!)
```

## 🔑 The ID Mapping Challenge

**Problem:** Fortnite.gg's "Character ID" ≠ Epic's "CID"

**Fortnite.gg:**
```
ID: 20727
Character ID: "Character_BugBandit"  ← This is the asset name
```

**Epic API:**
```
Template ID: "AthenaCharacter:CID_035_Athena_Commando_M_Medieval"  ← We need this!
```

**Solution:** Use **Fortnite-API.com** as the bridge!
- It has the proper CIDs
- It has the names to search
- It matches Epic's format

## 🏗️ Recommended Architecture

### **Hybrid System** (Best Approach)

```
User Wants to Equip "Mothmando Elite"
           ↓
1. Search in Fortnite-API.com database
   → Find by name: "Mothmando Elite"
   → Get CID: "CID_035_Athena_Commando_..."
           ↓
2. Build template ID
   → Combine: "AthenaCharacter:CID_035_Athena_Commando_..."
           ↓
3. Call Epic API to equip
   → POST /SetCosmeticLockerSlot
   → Body: { "itemToSlot": "AthenaCharacter:CID_035_..." }
           ↓
4. Optionally fetch Fortnite.gg details for extra info
   → Last seen, set name, occurrences, etc.
```

### **Data Flow Diagram**

```
┌─────────────────────┐
│  Fortnite-API.com   │  ← Primary source (has proper CIDs)
│  Complete cosmetics │
│  database           │
└──────────┬──────────┘
           │
           │ Name + CID
           ↓
┌─────────────────────┐     ┌──────────────────────┐
│   Epic Games API    │ ←── │  Fortnite Locker GUI │
│   - QueryProfile    │     │  (User Interface)    │
│   - SetCosmeticSlot │     └──────────────────────┘
│   - Get owned items │              ↓
└─────────────────────┘      Search & Filter
           ↑                         ↓
           │                 ┌──────────────────────┐
           │                 │   Fortnite.gg API    │
           └─────────────────│  (Supplementary)     │
                             │  - Release dates     │
                             │  - Set information   │
                             │  - Shop history      │
                             └──────────────────────┘
```

## 💻 Implementation Examples

### Example 1: Load Owned Cosmetics
```python
from lib.utilities.fortnite_locker_api import get_locker_api
from lib.utilities.epic_auth import get_epic_auth_instance

# Get auth instance
auth = get_epic_auth_instance()

# Create locker API
locker = get_locker_api(auth)

# Load profile
locker.load_profile()

# Get owned cosmetic IDs
owned_ids = locker.get_owned_cosmetic_ids()
print(f"You own {len(owned_ids)} cosmetics")

# Example owned IDs:
# ["CID_035_Athena_Commando_M_Medieval", "BID_123_BlackKnight", ...]
```

### Example 2: Equip a Cosmetic Directly (No UI!)
```python
# Method 1: If you know the full template ID
template_id = "AthenaCharacter:CID_035_Athena_Commando_M_Medieval"
locker.equip_cosmetic(template_id, category="Character", slot_index=0)

# Method 2: Build from parts
cosmetic_id = "CID_035_Athena_Commando_M_Medieval"
template_id = locker.build_template_id("Outfit", cosmetic_id)
locker.equip_cosmetic(template_id, category="Character")

# For emotes (multiple slots)
emote_template = "AthenaDance:EID_DanceMoves"
locker.equip_cosmetic(emote_template, category="Dance", slot_index=2)  # Slot 3

# For wraps (7 slots)
wrap_template = "AthenaItemWrap:Wrap_123_Camo"
locker.equip_cosmetic(wrap_template, category="ItemWrap", slot_index=0)  # Rifles
```

### Example 3: Equip Full Loadout
```python
loadout = [
    {
        "category": "Character",
        "itemToSlot": "AthenaCharacter:CID_035_Athena_Commando_M_Medieval",
        "slotIndex": 0,
        "variantUpdates": []
    },
    {
        "category": "Backpack",
        "itemToSlot": "AthenaBackpack:BID_123_BlackKnight",
        "slotIndex": 0,
        "variantUpdates": []
    },
    {
        "category": "Pickaxe",
        "itemToSlot": "AthenaPickaxe:Pickaxe_ID_029_Medieval",
        "slotIndex": 0,
        "variantUpdates": []
    }
]

locker.equip_multiple_cosmetics(loadout)
```

### Example 4: Set Favorites
```python
# Get template ID for an item
template_id = "AthenaCharacter:CID_035_Athena_Commando_M_Medieval"

# Get the GUID from the template_id_map
if template_id in locker.template_id_map:
    guid = locker.template_id_map[template_id]
    locker.set_favorite(guid, True)

# Batch set favorites
favorites = [
    (guid1, True),   # Favorite
    (guid2, False),  # Unfavorite
    (guid3, True)
]
locker.set_favorites_batch(favorites)
```

### Example 5: Using Fortnite.gg for Browse + Epic API to Equip
```python
from lib.utilities.fortnite_cosmetics import get_cosmetics_service
from lib.utilities.fortnite_locker_api import get_locker_api
from lib.utilities.epic_auth import get_epic_auth_instance

# Load Fortnite.gg data
cosmetics_service = get_cosmetics_service()
cosmetics_service.fetch_items_list()

# Search for an item
results = cosmetics_service.search_items("Mothmando")
for item in results:
    print(f"Found: {item['name']} (ID: {item['id']})")

    # Get details (includes Character_ID but we won't use it for equipping)
    details = cosmetics_service.fetch_item_details(item['id'])
    if details:
        print(f"Set: {details.get('set_name')}")
        print(f"Last Seen: {details.get('last_seen')}")

# To equip, use Fortnite-API.com data instead
# (Has the proper CIDs that match Epic's format)
from lib.utilities.epic_auth import get_or_create_cosmetics_cache

fortnite_api_cosmetics = get_or_create_cosmetics_cache()

# Find by name in Fortnite-API.com data
target = next((c for c in fortnite_api_cosmetics if c['name'] == "Mothmando Elite"), None)

if target:
    # Build template ID
    auth = get_epic_auth_instance()
    locker = get_locker_api(auth)

    cosmetic_type = target['type']  # "AthenaCharacter"
    cosmetic_id = target['id']  # "CID_XXX_..."
    template_id = f"{cosmetic_type}:{cosmetic_id}"

    # Equip via API!
    locker.equip_cosmetic(template_id, category="Character")
    print("✅ Equipped via API!")
```

## 🎮 Available MCP Operations

### Core Operations (Implemented)
- ✅ `QueryProfile` - Load profile data
- ✅ `SetCosmeticLockerSlot` - Equip single item
- ✅ `SetCosmeticLockerSlots` - Equip multiple items
- ✅ `SetItemFavoriteStatus` - Set favorite (single)
- ✅ `SetItemFavoriteStatusBatch` - Set favorites (batch)

### Additional Available Operations (Not Yet Implemented)
- `SetHeroCosmeticVariants` - Set variants/styles
- `CopyCosmeticLoadout` - Copy loadout
- `DeleteCosmeticLoadout` - Delete loadout
- `SetCosmeticLockerName` - Rename loadout
- `SetRandomCosmeticLoadoutFlag` - Enable/disable random
- `PutModularCosmeticLoadout` - Full loadout management with presets

## 🔧 Next Steps for Full Implementation

1. **Create New Locker GUI**
   - Use Fortnite-API.com data as primary source
   - Show Fortnite.gg supplementary details when viewing items
   - Use API to equip (no more UI automation!)

2. **ID Mapping Service**
   - Map Fortnite.gg numeric IDs → names → Fortnite-API.com CIDs
   - Create lookup cache for fast searches

3. **Variant Support**
   - Implement `SetHeroCosmeticVariants` for styles
   - UI to select variants before equipping

4. **Loadout Presets**
   - Implement `PutModularCosmeticLoadout`
   - Save/load full loadout presets

## ⚡ Performance Benefits

### Old System (UI Automation)
- ⏱️ 5-10 seconds per item
- ❌ Requires Fortnite to be open and focused
- ❌ Mouse/keyboard simulation
- ❌ Can fail if UI changes

### New System (Direct API)
- ⏱️ < 1 second per item
- ✅ Works in background
- ✅ No UI interaction needed
- ✅ Reliable, won't break with UI updates
- ✅ Can equip multiple items at once

## 📝 Summary

**Best Approach:**
1. Use **Fortnite-API.com** for main cosmetics database (has proper CIDs)
2. Use **Epic API** to equip cosmetics (fast, reliable)
3. Use **Fortnite.gg** for extra details (sets, release dates)

**Do NOT try to use Fortnite.gg's Character_ID for equipping** - it's not the CID!

The Character_ID (e.g., "Character_BugBandit") is the asset/pak file name, not the cosmetic ID needed for the Epic API.
