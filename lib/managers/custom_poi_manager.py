"""
Custom POI manager for FA11y
Provides functions for managing custom points of interest with map-specific support
"""
from typing import Optional, Tuple, List, Dict
import os
import logging
from lib.config.config_manager import config_manager

# Initialize logger
logger = logging.getLogger(__name__)


# Custom loader/saver for CUSTOM_POI.txt
def _load_custom_pois_file(filename: str) -> List[Tuple[str, int, int, str]]:
    """
    Custom loader for CUSTOM_POI.txt format.
    
    Args:
        filename: Path to the custom POI file
        
    Returns:
        List of (poi_name, x, y, map_name) tuples
    """
    pois = []
    if not os.path.exists(filename):
        return pois
        
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                poi_data = parse_custom_poi_line(line)
                if poi_data:
                    pois.append(poi_data)
    except Exception as e:
        logger.error(f"Error loading custom POIs from {filename}: {e}")
    
    return pois


def _save_custom_pois_file(filename: str, pois: List[Tuple[str, int, int, str]]) -> bool:
    """
    Custom saver for CUSTOM_POI.txt format.
    
    Args:
        filename: Path to the custom POI file
        pois: List of (poi_name, x, y, map_name) tuples
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        # Ensure directory exists
        directory = os.path.dirname(filename)
        if directory:
            os.makedirs(directory, exist_ok=True)
            
        with open(filename, 'w', encoding='utf-8') as f:
            for poi_name, x, y, map_name in pois:
                f.write(f"{poi_name},{x},{y},{map_name}\n")
        return True
    except Exception as e:
        logger.error(f"Error saving custom POIs to {filename}: {e}")
        return False


# Register CUSTOM_POI.txt with config manager
config_manager.register(
    'custom_pois',
    'config/CUSTOM_POI.txt',
    format='custom',
    default=[],
    custom_loader=_load_custom_pois_file,
    custom_saver=_save_custom_pois_file
)

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
    try:
        # Load all POIs from config manager
        all_pois = config_manager.get('custom_pois', default=[])
        
        # Filter by map if specified
        filtered_pois = []
        for poi_data in all_pois:
            if len(poi_data) >= 4:
                name, x, y, poi_map = poi_data
                # If map_name is provided, filter by that map
                if map_name is None or poi_map == map_name:
                    filtered_pois.append((name, str(x), str(y)))
        
        return filtered_pois
    except Exception as e:
        logger.error(f"Error loading custom POIs: {e}")
        return []

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
        # Load existing POIs
        all_pois = config_manager.get('custom_pois', default=[])
        
        # Add new POI
        all_pois.append((poi_name, x, y, map_name))
        
        # Save back to config
        return config_manager.set('custom_pois', data=all_pois)
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
    try:
        # Load all custom POIs (no map filtering for direct selection)
        all_pois = config_manager.get('custom_pois', default=[])
        
        # Match selected POI name
        selected_poi_lower = selected_poi.lower()
        for poi_data in all_pois:
            if len(poi_data) >= 4:
                name, x, y, _ = poi_data  # Map name not needed for selection
                if name.lower() == selected_poi_lower:
                    return (name, (x, y))
    except Exception as e:
        logger.error(f"Error loading custom POIs: {e}")
    
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
    POI selection handler.
    
    Args:
        selected_poi: Name or type of POI to find
        use_ppi: Whether to use PPI for position detection
        
    Returns:
        Tuple of (poi_name, coordinates) or (None, None) if not found
    """
    from lib.detection.player_position import find_player_position, find_player_icon_location
    
    # Get current position based on method
    current_position = find_player_position() if use_ppi else find_player_icon_location()
    
    # Check if it's a custom POI
    custom_result = handle_custom_poi_selection(selected_poi, use_ppi)
    if custom_result[0]:
        return custom_result
        
    # Continue with existing POI handling
    return (None, None)