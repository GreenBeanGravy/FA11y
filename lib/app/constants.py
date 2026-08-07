"""
Shared string constants used by FA11y action handlers.

These are imported by many of the ``lib.app.*`` action modules and by
``FA11y.py`` itself. Keeping them in one place prevents drift from
copy-paste during further extractions.
"""

# POI categories
POI_CATEGORY_SPECIAL = "special"
POI_CATEGORY_REGULAR = "regular"
POI_CATEGORY_LANDMARK = "landmark"
POI_CATEGORY_FAVORITE = "favorite"
POI_CATEGORY_CUSTOM = "custom"
POI_CATEGORY_GAMEOBJECT = "gameobject"
POI_CATEGORY_BOSS = "boss"
POI_CATEGORY_VAULT = "vault"

# Boss-spawn game-object types (stored in map_<map>_gameobjects.txt).
# FIXED bosses have a single spawn and are navigated to directly by name.
# CLOSEST bosses spawn from a shared pool of candidate points and are surfaced
# as "Closest <Type>", using the game-object closest-unvisited + visited-tracking
# machinery. These types are shown under the dedicated Boss Spawns category and
# excluded from the generic Game Object category.
BOSS_FIXED_TYPES = ("Harley Quinn", "Catwoman", "Poison Ivy")
BOSS_CLOSEST_TYPES = ("Boss Rift Spawn",)

# Main-map underground vaults (RelicVault keycard vaults). Deliberately NOT
# stored in the game-objects file: a looter must be able to re-navigate to the
# same vault to find the exit portapotty after looting, so these must never be
# marked "visited". They are fixed entries with a distance-based "Closest Vault".
# Format: (display_name, screen_x, screen_y). Coordinates are the door/scanner
# interactable, converted from UE world coords via the aligner pipeline.
MAIN_VAULTS = (
    # Large walk-in relic vaults (interior loot + exit portapotty):
    ("Frosted Flats Vault", 1031, 574),
    ("Sinister Strip Vault", 853, 698),
    # Smaller keycard bunker vaults (map-marked), spread across the map:
    ("Lifty Lodge Vault", 699, 296),
    ("The Bus Stop Vault", 863, 290),
    ("Calamari Canyon Vault", 720, 561),
    ("The Zero Point Vault", 915, 501),
    ("Collider Corridor Gamma Vault", 1060, 441),
    ("Heatwave Harbor Vault", 686, 764),
    ("Wettest-Bones Research Facility Vault", 951, 810),
    ("Shaken Sanctuary Vault", 1117, 803),
)

# Special POI names used as sentinel values in the POI selector
SPECIAL_POI_CLOSEST = "closest"
SPECIAL_POI_SAFEZONE = "safe zone"
SPECIAL_POI_CLOSEST_LANDMARK = "closest landmark"
SPECIAL_POI_CLOSEST_VAULT = "closest vault"
