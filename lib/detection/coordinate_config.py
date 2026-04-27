"""
Centralized coordinate configuration for FA11y.

This module provides map-specific screen coordinates for different Fortnite seasons/maps.
Coordinates are used for minimap detection, health/shield detection, hotbar detection, etc.
"""

from typing import Dict, Tuple, List, Any, Optional
from dataclasses import dataclass, field

from lib.detection.feature_matcher import DetectorType, MatcherConfig


@dataclass
class MinimapCoords:
    """Minimap detection coordinates."""
    start: Tuple[int, int]
    end: Tuple[int, int]
    min_area: int
    max_area: int
    region: Dict[str, int]  # For utilities.py MINIMAP_REGION compatibility


@dataclass
class HealthShieldCoords:
    """Health and shield detection coordinates and settings."""
    health_x: int
    health_y: int
    shield_x: int
    shield_y: int
    health_color: Tuple[int, int, int]
    shield_color: Tuple[int, int, int]
    tolerance: int
    health_decreases: List[int]
    shield_decreases: List[int]


@dataclass
class HotbarCoords:
    """Hotbar detection coordinates."""
    # Format: (left, top, right, bottom) for each slot
    primary_slots: List[Tuple[int, int, int, int]]
    secondary_slots: List[Tuple[int, int, int, int]]
    consumable_count_area: Tuple[int, int, int, int]
    ammo_y_coords: Dict[str, Tuple[int, int]]


@dataclass
class CoordinateSet:
    """Complete set of coordinates for a specific map/season."""
    minimap: MinimapCoords
    health_shield: HealthShieldCoords
    hotbar: HotbarCoords
    # Conversion factor for player_position distance calculations:
    # ``distance_meters = pixel_vector_norm * px_to_meters``.
    # Empirically 2.65 on current-season maps at 1920x1080. Split out here so
    # a rework of the detector per-map only has to retune this number.
    px_to_meters: float = 2.65
    # Per-map feature-matching overrides. ``None`` = use the global defaults
    # (from config ``[POI] feature_detector`` / ``feature_clahe``). Set this
    # for maps with known detector preferences — e.g. reload arenas where
    # AKAZE + CLAHE outperforms SIFT on the purple / berry terrain.
    matcher_override: Optional[MatcherConfig] = None


# ==============================================================================
# OG MAP COORDINATES (from FA11y-OLD - Season OG/Reload)
# ==============================================================================

OG_COORDINATES = CoordinateSet(
    minimap=MinimapCoords(
        start=(1735, 154),
        end=(1766, 184),
        min_area=600,
        max_area=3000,
        region={
            'left': 1600,  # These may need adjustment based on OG map
            'top': 20,
            'width': 300,
            'height': 300
        }
    ),
    health_shield=HealthShieldCoords(
        health_x=423,
        health_y=1024,
        shield_x=423,
        shield_y=987,
        health_color=(131, 237, 82),
        shield_color=(83, 202, 239),
        tolerance=30,
        health_decreases=[4, 3, 3],
        shield_decreases=[4, 3, 3]
    ),
    hotbar=HotbarCoords(
        primary_slots=[
            (1502, 931, 1565, 975),  # Slot 1
            (1583, 931, 1646, 975),  # Slot 2
            (1665, 931, 1728, 975),  # Slot 3
            (1747, 931, 1810, 975),  # Slot 4
            (1828, 931, 1891, 975)   # Slot 5
        ],
        secondary_slots=[
            (1502, 920, 1565, 964),  # Slot 1 (11px above)
            (1583, 920, 1646, 964),  # Slot 2
            (1665, 920, 1728, 964),  # Slot 3
            (1747, 920, 1810, 964),  # Slot 4
            (1828, 920, 1891, 964)   # Slot 5
        ],
        consumable_count_area=(1314, 927, 1392, 971),
        ammo_y_coords={
            'current': (929, 962),
            'reserve': (936, 962)
        }
    )
)

# ==============================================================================
# CURRENT SEASON COORDINATES (Chapter 6 Season 1 and onwards)
# ==============================================================================

# Full calibrated decrease pattern for current season (100 HP -> 1 HP)
CURRENT_HEALTH_DECREASES = [3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 3, 4, 4, 3, 4, 3, 3, 3, 4, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 3, 4, 3, 4, 3, 4, 3, 4, 3, 3]

CURRENT_COORDINATES = CoordinateSet(
    minimap=MinimapCoords(
        start=(1745, 144),
        end=(1776, 174),
        min_area=650,
        max_area=3000,
        region={
            'left': 1600,
            'top': 20,
            'width': 300,
            'height': 300
        }
    ),
    health_shield=HealthShieldCoords(
        health_x=408,
        health_y=1000,
        shield_x=408,
        shield_y=970,
        health_color=(247, 255, 26),
        shield_color=(213, 255, 232),
        tolerance=30,
        health_decreases=CURRENT_HEALTH_DECREASES,
        shield_decreases=CURRENT_HEALTH_DECREASES
    ),
    hotbar=HotbarCoords(
        # Current season uses same hotbar coordinates as OG
        # If these differ, update them here
        primary_slots=[
            (1502, 931, 1565, 975),  # Slot 1
            (1583, 931, 1646, 975),  # Slot 2
            (1665, 931, 1728, 975),  # Slot 3
            (1747, 931, 1810, 975),  # Slot 4
            (1828, 931, 1891, 975)   # Slot 5
        ],
        secondary_slots=[
            (1502, 920, 1565, 964),  # Slot 1 (11px above)
            (1583, 920, 1646, 964),  # Slot 2
            (1665, 920, 1728, 964),  # Slot 3
            (1747, 920, 1810, 964),  # Slot 4
            (1828, 920, 1891, 964)   # Slot 5
        ],
        consumable_count_area=(1314, 927, 1392, 971),
        ammo_y_coords={
            'current': (929, 962),
            'reserve': (936, 962)
        }
    )
)

# ==============================================================================
# MAP NAME MAPPINGS
# ==============================================================================

# Map identifiers that should use OG coordinates. Includes the canonical
# underscore slug ``o_g`` (what the config stores today) as well as legacy
# spaced / alt forms for migration safety.
OG_MAP_IDENTIFIERS = {'og', 'reload', 'season_og', 'fortnite_og', 'o g', 'o_g'}

# Coordinate registry
COORDINATE_REGISTRY: Dict[str, CoordinateSet] = {
    'og': OG_COORDINATES,
    'o_g': OG_COORDINATES,
    'current': CURRENT_COORDINATES,
    'main': CURRENT_COORDINATES,  # Default main map uses current coordinates
}


# ==============================================================================
# PER-MAP FEATURE-MATCHER OVERRIDES
# ==============================================================================
# Chosen based on ``python dev_tools/feature_match_bench.py`` runs against
# the map .pngs we ship. The bench uses synthetic 250x250 crops from each
# map — that tends to favour SIFT because there's no UI overlay, no zoom
# mismatch, no compression. Real in-game performance may prefer AKAZE in
# harder-to-match conditions (partial occlusion, scale drift).
#
# Summary of bench takeaways (success rate @ 20 synthetic crops):
#
#   * Main/OG: SIFT 100%, AKAZE 100%. SIFT kept (backward compat).
#   * reload_elite_stronghold: SIFT and AKAZE both 100%, but AKAZE is ~3×
#     faster AND user-reported real-world issues. AKAZE+CLAHE override.
#   * blitz_stranger_things (snow-heavy): SIFT 60%, SIFT+CLAHE 80%. Big
#     CLAHE win → force CLAHE on. Keep SIFT detector.
#   * Other reload arenas (venture/oasis/slurp_rush/surfcity): SIFT
#     outperforms AKAZE on synthetic crops (85–95% vs 75–80%). Keep SIFT
#     default — users can flip to AKAZE globally via [POI] feature_detector
#     if real-world data tells a different story.
#
# Users can change the global default at runtime via [POI] feature_detector
# and [POI] feature_clahe in config.txt. A per-map override defined here
# takes precedence over the global setting.

_AKAZE_CLAHE = MatcherConfig(
    detector=DetectorType.AKAZE,
    akaze_threshold=0.0008,    # Slightly lower than default — more keypoints
    preprocess_clahe=True,
    clahe_clip_limit=2.5,
    lowe_ratio=0.80,           # AKAZE matches are tighter; loosen the ratio
    min_good_matches=15,       # AKAZE typically produces fewer matches overall
)

_SIFT_CLAHE = MatcherConfig(
    detector=DetectorType.SIFT,
    sift_contrast_threshold=0.02,  # Even more permissive than ppi.py default
    preprocess_clahe=True,
    clahe_clip_limit=2.5,
    lowe_ratio=0.75,
    min_good_matches=20,
)

MAP_MATCHER_OVERRIDES: Dict[str, MatcherConfig] = {
    'reload_elite_stronghold': _AKAZE_CLAHE,  # New map, user-reported issues
    'blitz_stranger_things':   _SIFT_CLAHE,   # Snow-heavy; CLAHE +20pp success
    # Other reload arenas intentionally NOT overridden — synthetic bench
    # favours SIFT and they've been fine in production. Revisit if real
    # minimap capture data shows otherwise.
}


# ==============================================================================
# PUBLIC API
# ==============================================================================

def get_coordinates(map_name: str = 'main') -> CoordinateSet:
    """
    Get the appropriate coordinate set for the given map.
    
    Args:
        map_name: Name of the map from config (e.g., 'main', 'og', 'reload')
        
    Returns:
        CoordinateSet for the specified map
    """
    # Normalize map name
    map_key = map_name.lower().strip()
    
    # Check if it's an OG map identifier
    if map_key in OG_MAP_IDENTIFIERS:
        return COORDINATE_REGISTRY['og']
    
    # Check if we have specific coordinates for this map
    if map_key in COORDINATE_REGISTRY:
        return COORDINATE_REGISTRY[map_key]
    
    # Default to current season coordinates
    return COORDINATE_REGISTRY['current']


def get_minimap_coords(map_name: str = 'main') -> MinimapCoords:
    """Get minimap coordinates for the specified map."""
    return get_coordinates(map_name).minimap


def get_health_shield_coords(map_name: str = 'main') -> HealthShieldCoords:
    """Get health/shield coordinates for the specified map."""
    return get_coordinates(map_name).health_shield


def get_hotbar_coords(map_name: str = 'main') -> HotbarCoords:
    """Get hotbar coordinates for the specified map."""
    return get_coordinates(map_name).hotbar


def get_px_to_meters(map_name: str = 'main') -> float:
    """Pixel-to-meters scaling factor for the given map."""
    return get_coordinates(map_name).px_to_meters


def get_matcher_config(map_name: str = 'main') -> Optional[MatcherConfig]:
    """Return the per-map feature-matcher override, if any.

    ``None`` means: use whatever the global config (POI.feature_detector +
    POI.feature_clahe) says.
    """
    return MAP_MATCHER_OVERRIDES.get(map_name.lower().strip())


def get_minimap_region(map_name: str = 'main') -> Dict[str, int]:
    """
    Get minimap region dict (for backward compatibility with utilities.py).
    
    Args:
        map_name: Name of the map from config
        
    Returns:
        Dictionary with 'left', 'top', 'width', 'height' keys
    """
    return get_minimap_coords(map_name).region


def is_og_map(map_name: str) -> bool:
    """
    Check if the given map name corresponds to an OG map.
    
    Args:
        map_name: Name of the map from config
        
    Returns:
        True if this is an OG map, False otherwise
    """
    return map_name.lower().strip() in OG_MAP_IDENTIFIERS
