"""
Centralized coordinate configuration for FA11y.

This module provides map-specific screen coordinates for different Fortnite seasons/maps.
Coordinates are used for minimap detection, health/shield detection, hotbar detection, etc.
"""

from typing import Dict, Tuple, List, Any
from dataclasses import dataclass


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
    attachment_detection_area: Tuple[int, int, int, int]
    ammo_y_coords: Dict[str, Tuple[int, int]]


@dataclass
class CoordinateSet:
    """Complete set of coordinates for a specific map/season."""
    minimap: MinimapCoords
    health_shield: HealthShieldCoords
    hotbar: HotbarCoords


# ==============================================================================
# OG MAP COORDINATES (from FA11y-OLD - Season OG/Reload)
# ==============================================================================

OG_COORDINATES = CoordinateSet(
    minimap=MinimapCoords(
        start=(1735, 154),
        end=(1766, 184),
        min_area=800,
        max_area=1100,
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
        shield_y=984,
        health_color=(158, 255, 99),
        shield_color=(110, 235, 255),
        tolerance=70,
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
        attachment_detection_area=(1240, 1000, 1410, 1070),
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
        max_area=1130,
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
        attachment_detection_area=(1240, 1000, 1410, 1070),
        ammo_y_coords={
            'current': (929, 962),
            'reserve': (936, 962)
        }
    )
)

# ==============================================================================
# MAP NAME MAPPINGS
# ==============================================================================

# Map identifiers that should use OG coordinates
OG_MAP_IDENTIFIERS = {'og', 'reload', 'season_og', 'fortnite_og'}

# Coordinate registry
COORDINATE_REGISTRY: Dict[str, CoordinateSet] = {
    'og': OG_COORDINATES,
    'current': CURRENT_COORDINATES,
    'main': CURRENT_COORDINATES,  # Default main map uses current coordinates
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
