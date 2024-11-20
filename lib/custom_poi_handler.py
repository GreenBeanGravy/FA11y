from typing import Optional, Tuple, List, Dict
import configparser
import os

def parse_custom_poi_line(line: str) -> Optional[Tuple[str, int, int]]:
    """
    Parse a line from CUSTOM_POI.txt safely.
    
    Args:
        line: Raw line from CUSTOM_POI.txt
        
    Returns:
        Tuple of (poi_name, x, y) or None if invalid
    """
    try:
        # Remove whitespace and split
        parts = [p.strip() for p in line.strip().split(',')]
        if len(parts) != 3:
            return None
            
        # Extract name and coordinates
        poi_name = parts[0]
        x = int(float(parts[1]))
        y = int(float(parts[2]))
        
        return (poi_name, x, y)
    except (ValueError, IndexError):
        print(f"Warning: Invalid custom POI line: {line}")
        return None

def load_custom_pois() -> List[Tuple[str, int, int]]:
    """
    Load and validate all custom POIs from file.
    
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
                    custom_pois.append(poi_data)
    except Exception as e:
        print(f"Error loading custom POIs: {e}")
        
    return custom_pois

def save_custom_poi(poi_name: str, x: int, y: int) -> bool:
    """
    Save a new custom POI to file.
    
    Args:
        poi_name: Name of the POI
        x: X coordinate
        y: Y coordinate
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        with open('CUSTOM_POI.txt', 'a', encoding='utf-8') as f:
            f.write(f"{poi_name},{x},{y}\n")
        return True
    except Exception as e:
        print(f"Error saving custom POI: {e}")
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
    # Load all custom POIs
    custom_pois = load_custom_pois()
    
    # Match selected POI name
    selected_poi = selected_poi.lower()
    for poi_name, x, y in custom_pois:
        if poi_name.lower() == selected_poi:
            return (poi_name, (x, y))
            
    return (None, None)

def create_custom_poi(current_position: Optional[Tuple[int, int]], poi_name: str) -> bool:
    """
    Create a new custom POI at the current position.
    
    Args:
        current_position: Current coordinates (x, y)
        poi_name: Name for the new POI
        
    Returns:
        True if POI was created successfully, False otherwise
    """
    if not current_position:
        print("Error: Could not determine current position")
        return False
        
    x, y = current_position
    return save_custom_poi(poi_name, x, y)

# Update the POI handling in icon.py to use these functions:
def update_poi_handler(selected_poi: str, use_ppi: bool = False) -> Tuple[Optional[str], Optional[Tuple[int, int]]]:
    """
    Enhanced POI selection handler with PPI support.
    
    Args:
        selected_poi: Name or type of POI to find
        use_ppi: Whether to use PPI for position detection
        
    Returns:
        Tuple of (poi_name, coordinates) or (None, None) if not found
    """
    from lib.ppi import find_player_position
    from lib.player_location import find_player_icon_location
    
    # Get current position based on method
    current_position = find_player_position() if use_ppi else find_player_icon_location()
    
    # Check if it's a custom POI
    custom_result = handle_custom_poi_selection(selected_poi, use_ppi)
    if custom_result[0]:
        return custom_result
        
    # Continue with existing POI handling
    return (None, None)
