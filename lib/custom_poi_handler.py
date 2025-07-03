"""
Custom POI handler for FA11y
Provides functions for managing custom points of interest with map-specific support
"""
from typing import Optional, Tuple, List, Dict
import os
import logging

# Initialize logger
logger = logging.getLogger(__name__)

def parse_custom_poi_line(line: str) -> Optional[Tuple[str, int, int, str]]:
    """
    Parse a line from CUSTOM_POI.txt safely.
    
    Args:
        line: Raw line from CUSTOM_POI.txt
        
    Returns:
        Tuple of (poi_name, x, y, map_name) or None if invalid
    """
    try:
        # Remove whitespace and split
        parts = [p.strip() for p in line.strip().split(',')]
        if len(parts) < 3:
            return None
            
        # Extract name and coordinates
        poi_name = parts[0]
        x = int(float(parts[1]))
        y = int(float(parts[2]))
        
        # Extract map name if available (backward compatibility)
        map_name = parts[3] if len(parts) > 3 else "main"
        
        return (poi_name, x, y, map_name)
    except (ValueError, IndexError):
        logger.warning(f"Warning: Invalid custom POI line: {line}")
        return None

def load_custom_pois(map_name: str = None) -> List[Tuple[str, str, str]]:
    """
    Load and validate custom POIs from file, optionally filtering by map.
    
    Args:
        map_name: Optional map name to filter POIs
        
    Returns:
        List of valid (name, x, y) POI tuples
    """
    custom_pois = []
    
    if not os.path.exists('CUSTOM_POI.txt'):
        return custom_pois
        
    try:
        with open('CUSTOM_POI.txt', 'r', encoding='utf-8') as f:
            for line in f:
                poi_data = parse_custom_poi_line(line)
                if poi_data:
                    name, x, y, poi_map = poi_data
                    
                    # If map_name is provided, filter by that map
                    if map_name is None or poi_map == map_name:
                        custom_pois.append((name, str(x), str(y)))
    except Exception as e:
        logger.error(f"Error loading custom POIs: {e}")
        
    return custom_pois

def save_custom_poi(poi_name: str, x: int, y: int, map_name: str = "main") -> bool:
    """
    Save a new custom POI to file.
    
    Args:
        poi_name: Name of the POI
        x: X coordinate
        y: Y coordinate
        map_name: Map name this POI belongs to
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        with open('CUSTOM_POI.txt', 'a', encoding='utf-8') as f:
            f.write(f"{poi_name},{x},{y},{map_name}\n")
        return True
    except Exception as e:
        logger.error(f"Error saving custom POI: {e}")
        return False

def handle_custom_poi_selection(selected_poi: str, use_ppi: bool = False) -> Tuple[Optional[str], Optional[Tuple[int, int]]]:
    """
    Handle selection of a custom POI with PPI support.
    
    Args:
        selected_poi: Name of the selected POI
        use_ppi: Whether to use PPI for position detection
        
    Returns:
        Tuple of (poi_name, (x, y)) or (None, None) if not found
    """
    # Load all custom POIs (no map filtering for direct selection)
    custom_pois = []
    
    if os.path.exists('CUSTOM_POI.txt'):
        try:
            with open('CUSTOM_POI.txt', 'r', encoding='utf-8') as f:
                for line in f:
                    poi_data = parse_custom_poi_line(line)
                    if poi_data:
                        name, x, y, _ = poi_data  # Map name not needed for selection
                        custom_pois.append((name, x, y))
        except Exception as e:
            logger.error(f"Error loading custom POIs: {e}")
    
    # Match selected POI name
    selected_poi = selected_poi.lower()
    for poi_name, x, y in custom_pois:
        if poi_name.lower() == selected_poi:
            return (poi_name, (x, y))
            
    return (None, None)

def create_custom_poi(current_position: Optional[Tuple[int, int]], poi_name: str, map_name: str = "main") -> bool:
    """
    Create a new custom POI at the current position.
    
    Args:
        current_position: Current coordinates (x, y)
        poi_name: Name for the new POI
        map_name: Map name this POI belongs to
        
    Returns:
        True if POI was created successfully, False otherwise
    """
    if not current_position:
        logger.error("Error: Could not determine current position")
        return False
        
    x, y = current_position
    return save_custom_poi(poi_name, x, y, map_name)

def update_poi_handler(selected_poi: str, use_ppi: bool = False) -> Tuple[Optional[str], Optional[Tuple[int, int]]]:
    """
    Enhanced POI selection handler with PPI support.
    
    Args:
        selected_poi: Name or type of POI to find
        use_ppi: Whether to use PPI for position detection
        
    Returns:
        Tuple of (poi_name, coordinates) or (None, None) if not found
    """
    from lib.player_position import find_player_position, find_player_icon_location
    
    # Get current position based on method
    current_position = find_player_position() if use_ppi else find_player_icon_location()
    
    # Check if it's a custom POI
    custom_result = handle_custom_poi_selection(selected_poi, use_ppi)
    if custom_result[0]:
        return custom_result
        
    # Continue with existing POI handling
    return (None, None)