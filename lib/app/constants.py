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

# Special POI names used as sentinel values in the POI selector
SPECIAL_POI_CLOSEST = "closest"
SPECIAL_POI_SAFEZONE = "safe zone"
SPECIAL_POI_CLOSEST_LANDMARK = "closest landmark"
