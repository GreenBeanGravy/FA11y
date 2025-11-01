"""
Game Object Manager for FA11y
Manages per-map game object data loaded from text files in format:
ObjectType,X,Y
Objects are assigned IDs based on spatial position (top-left to bottom-right)
"""
import os
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
import numpy as np
from lib.utilities.utilities import calculate_distance

# Map image dimensions and screen bounds
MAP_IMAGE_WIDTH = 866
MAP_IMAGE_HEIGHT = 926
SCREEN_BOUNDS_X1, SCREEN_BOUNDS_Y1 = 524, 84
SCREEN_BOUNDS_X2, SCREEN_BOUNDS_Y2 = 1390, 1010

@dataclass
class GameObjectData:
    """Represents game object data for a specific map"""
    map_name: str
    objects: Dict[str, List[Tuple[str, str, str]]] = field(default_factory=dict)  # type -> [(name, x, y), ...]
    load_time: float = 0.0
    file_modified_time: float = 0.0

class GameObjectManager:
    """Manages game objects across multiple maps"""
    
    def __init__(self):
        self.loaded_maps: Dict[str, GameObjectData] = {}
        self.cache_timeout = 30.0
        self._last_spam_prevention = {}
    
    def _get_game_object_file_path(self, map_name: str) -> str:
        """Get the file path for a map's game objects file"""
        if map_name == 'main':
            return os.path.join('maps', 'map_main_gameobjects.txt')
        else:
            safe = (map_name or 'main').strip().lower().replace(' ', '_')
            import re as _re
            safe = _re.sub(r'[^a-z0-9_]+', '', safe)
            return os.path.join('maps', f'map_{safe}_gameobjects.txt')
    
    def _convert_image_coords_to_screen(self, image_x: float, image_y: float) -> Tuple[int, int]:
        """Convert image coordinates to screen coordinates
        
        Args:
            image_x: X coordinate relative to map image (0-866)
            image_y: Y coordinate relative to map image (0-926)
            
        Returns:
            Tuple of screen coordinates (x, y)
        """
        # Calculate screen dimensions
        screen_width = SCREEN_BOUNDS_X2 - SCREEN_BOUNDS_X1
        screen_height = SCREEN_BOUNDS_Y2 - SCREEN_BOUNDS_Y1
        
        # Convert from image space to screen space
        screen_x = int(SCREEN_BOUNDS_X1 + (image_x / MAP_IMAGE_WIDTH) * screen_width)
        screen_y = int(SCREEN_BOUNDS_Y1 + (image_y / MAP_IMAGE_HEIGHT) * screen_height)
        
        return screen_x, screen_y
    
    def _parse_game_object_line(self, line: str) -> Optional[Tuple[str, str, str]]:
        """Parse a line from a game objects file
        
        Args:
            line: Line in format "ObjectType,X,Y"
            
        Returns:
            Tuple of (object_type, screen_x, screen_y) or None if invalid
        """
        try:
            line = line.strip()
            if not line or line.startswith('#'):
                return None
            
            parts = line.split(',')
            if len(parts) != 3:
                return None
            
            object_type = parts[0].strip()
            image_x = float(parts[1].strip())
            image_y = float(parts[2].strip())
            
            # Convert to screen coordinates
            screen_x, screen_y = self._convert_image_coords_to_screen(image_x, image_y)
            
            return object_type, str(screen_x), str(screen_y)
            
        except (ValueError, IndexError):
            return None
    
    def _sort_objects_spatially(self, objects: List[Tuple[str, str, str]]) -> List[Tuple[str, str, str]]:
        """Sort objects spatially from top-left to bottom-right for consistent ID assignment"""
        def spatial_sort_key(obj):
            try:
                x, y = float(obj[1]), float(obj[2])
                # Primary sort by Y (top to bottom), secondary by X (left to right)
                return (y, x)
            except (ValueError, TypeError):
                return (float('inf'), float('inf'))  # Put invalid coords at end
        
        return sorted(objects, key=spatial_sort_key)
    
    def _should_reload_map_data(self, map_name: str) -> bool:
        """Check if map data should be reloaded"""
        import time
        current_time = time.time()
        
        # Check if not loaded or cache expired
        if (map_name not in self.loaded_maps or 
            current_time - self.loaded_maps[map_name].load_time > self.cache_timeout):
            return True
        
        # Check if file has been modified
        file_path = self._get_game_object_file_path(map_name)
        if os.path.exists(file_path):
            try:
                file_modified_time = os.path.getmtime(file_path)
                if file_modified_time > self.loaded_maps[map_name].file_modified_time:
                    return True
            except OSError:
                pass
        
        return False
    
    def _load_game_objects_for_map(self, map_name: str) -> GameObjectData:
        """Load game objects from file for a specific map"""
        import time
        
        file_path = self._get_game_object_file_path(map_name)
        game_object_data = GameObjectData(map_name=map_name, load_time=time.time())
        
        if os.path.exists(file_path):
            try:
                game_object_data.file_modified_time = os.path.getmtime(file_path)
            except OSError:
                game_object_data.file_modified_time = 0
        
        if not os.path.exists(file_path):
            # Only print this message once per session to prevent spam
            if map_name not in self._last_spam_prevention:
                self._last_spam_prevention[map_name] = 'not_found'
                print(f"Game objects file not found: {file_path}")
            return game_object_data
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Parse all objects first, grouped by type
            objects_by_type = {}
            for line_num, line in enumerate(lines, 1):
                parsed = self._parse_game_object_line(line)
                if parsed:
                    object_type, screen_x, screen_y = parsed
                    
                    if object_type not in objects_by_type:
                        objects_by_type[object_type] = []
                    
                    objects_by_type[object_type].append((object_type, screen_x, screen_y))
            
            # Sort each object type spatially and assign IDs
            for object_type, objects_list in objects_by_type.items():
                sorted_objects = self._sort_objects_spatially(objects_list)
                game_object_data.objects[object_type] = []
                
                for i, (obj_type, x, y) in enumerate(sorted_objects, 1):
                    # Create object name with spatial ID
                    object_name = obj_type  # Simple name without explicit ID in name
                    game_object_data.objects[object_type].append((object_name, x, y))
        
        except Exception as e:
            if map_name not in self._last_spam_prevention:
                self._last_spam_prevention[map_name] = 'error'
                print(f"Error loading game objects from {file_path}: {e}")
            return game_object_data
        
        total_objects = sum(len(objs) for objs in game_object_data.objects.values())
        
        # Only print loading message if it's different from last time or first load
        load_key = f"{map_name}_{total_objects}"
        if self._last_spam_prevention.get(map_name) != load_key:
            self._last_spam_prevention[map_name] = load_key
            if total_objects > 0:
                print(f"Loaded {total_objects} game objects for map '{map_name}'")
        
        return game_object_data
    
    def get_game_objects_for_map(self, map_name: str) -> Dict[str, List[Tuple[str, str, str]]]:
        """Get all game objects for a specific map
        
        Args:
            map_name: Name of the map
            
        Returns:
            Dictionary mapping object type to list of (name, x, y) tuples
        """
        # Only reload if necessary
        if self._should_reload_map_data(map_name):
            self.loaded_maps[map_name] = self._load_game_objects_for_map(map_name)
        
        return self.loaded_maps[map_name].objects
    
    def get_object_instance_count(self, map_name: str, object_type: str) -> int:
        """Get the number of instances of a specific object type on the map"""
        game_objects = self.get_game_objects_for_map(map_name)
        return len(game_objects.get(object_type, []))
    
    def get_available_object_types(self, map_name: str) -> Set[str]:
        """Get all available object types for a map"""
        game_objects = self.get_game_objects_for_map(map_name)
        return set(game_objects.keys())
    
    def get_objects_of_type(self, map_name: str, object_type: str) -> List[Tuple[str, str, str]]:
        """Get all objects of a specific type for a map"""
        game_objects = self.get_game_objects_for_map(map_name)
        return game_objects.get(object_type, [])
    
    def find_nearest_object_of_type(self, map_name: str, object_type: str, 
                                  player_position: Tuple[int, int]) -> Optional[Tuple[str, Tuple[float, float], float]]:
        """Find the nearest object of a specific type
        
        Args:
            map_name: Name of the map
            object_type: Type of object to find
            player_position: Current player position (x, y)
            
        Returns:
            Tuple of (object_name, (x, y), distance) or None if not found
        """
        objects = self.get_objects_of_type(map_name, object_type)
        if not objects:
            return None
        
        nearest = None
        min_distance = float('inf')
        
        for obj_name, x_str, y_str in objects:
            try:
                x, y = float(x_str), float(y_str)
                distance = calculate_distance(player_position, (x, y))
                
                if distance < min_distance:
                    min_distance = distance
                    nearest = (obj_name, (x, y), distance)
                    
            except (ValueError, TypeError):
                continue
        
        return nearest
    
    def find_nearest_unvisited_object_of_type(self, map_name: str, object_type: str, 
                                            player_position: Tuple[int, int],
                                            visited_coords: Set[Tuple[float, float]]) -> Optional[Tuple[str, Tuple[float, float], float]]:
        """Find the nearest unvisited object of a specific type
        
        Args:
            map_name: Name of the map
            object_type: Type of object to find
            player_position: Current player position (x, y)
            visited_coords: Set of visited coordinates
            
        Returns:
            Tuple of (object_name, (x, y), distance) or None if not found
        """
        objects = self.get_objects_of_type(map_name, object_type)
        if not objects:
            return None
        
        nearest = None
        min_distance = float('inf')
        
        for obj_name, x_str, y_str in objects:
            try:
                x, y = float(x_str), float(y_str)
                coords = (x, y)
                
                # Skip if already visited
                if coords in visited_coords:
                    continue
                
                distance = calculate_distance(player_position, coords)
                
                if distance < min_distance:
                    min_distance = distance
                    nearest = (obj_name, coords, distance)
                    
            except (ValueError, TypeError):
                continue
        
        return nearest
    
    def find_all_objects_within_radius(self, map_name: str, player_position: Tuple[int, int], 
                                     radius: float) -> Dict[str, List[Tuple[str, Tuple[float, float], float]]]:
        """Find all objects within a certain radius of the player
        
        Args:
            map_name: Name of the map
            player_position: Current player position (x, y)
            radius: Search radius in meters
            
        Returns:
            Dictionary mapping object type to list of (name, (x, y), distance) tuples
        """
        all_objects = self.get_game_objects_for_map(map_name)
        nearby_objects = {}
        
        for object_type, objects in all_objects.items():
            nearby_of_type = []
            
            for obj_name, x_str, y_str in objects:
                try:
                    x, y = float(x_str), float(y_str)
                    distance = calculate_distance(player_position, (x, y))
                    
                    if distance <= radius:
                        nearby_of_type.append((obj_name, (x, y), distance))
                        
                except (ValueError, TypeError):
                    continue
            
            if nearby_of_type:
                # Sort by distance
                nearby_of_type.sort(key=lambda x: x[2])
                nearby_objects[object_type] = nearby_of_type
        
        return nearby_objects
    
    def get_object_count_by_type(self, map_name: str) -> Dict[str, int]:
        """Get count of objects by type for a map"""
        game_objects = self.get_game_objects_for_map(map_name)
        return {obj_type: len(objects) for obj_type, objects in game_objects.items()}
    
    def reload_map_data(self, map_name: str = None):
        """Force reload of map data (clears cache)"""
        if map_name:
            if map_name in self.loaded_maps:
                del self.loaded_maps[map_name]
            if map_name in self._last_spam_prevention:
                del self._last_spam_prevention[map_name]
        else:
            self.loaded_maps.clear()
            self._last_spam_prevention.clear()
        print(f"Reloaded game object data for {'all maps' if not map_name else map_name}")
    
    def create_sample_game_object_files(self):
        """Create sample game object files for testing"""
        sample_data = {
            'main': [
                'Bushes,455.106306,281.286056',
                'Bushes,640.500416,160.437149',
                'Bushes,664.036236,186.350325',
                'Campfires,88.835060,456.695273',
                'Campfires,243.006568,309.695455',
                'Campfires,495.838331,89.829689',
                'Trees,123.456789,234.567890',
                'Trees,345.678901,456.789012',
                'Rocks,567.890123,678.901234',
                'Rocks,789.012345,890.123456',
            ],
            'athena': [
                'Bushes,200.5,150.3',
                'Bushes,300.7,250.9',
                'Campfires,400.1,350.6',
                'Trees,500.2,450.8',
            ],
            'apollo': [
                'Rocks,100.1,200.2',
                'Rocks,300.3,400.4',
                'Bushes,500.5,600.6',
            ]
        }
        
        for map_name, objects in sample_data.items():
            file_path = self._get_game_object_file_path(map_name)
            try:
                # Ensure maps directory exists
                os.makedirs('maps', exist_ok=True)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Game objects for {map_name} map\n")
                    f.write("# Format: ObjectType,X,Y (coordinates relative to map image)\n")
                    f.write("#\n")
                    for obj_line in objects:
                        f.write(obj_line + '\n')
                print(f"Created sample game objects file: {file_path}")
            except Exception as e:
                print(f"Error creating sample file {file_path}: {e}")

# Global instance
game_object_manager = GameObjectManager()