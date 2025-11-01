"""
Match tracking system for FA11y
Tracks visited game objects per match and resets when a new match starts
"""
import os
import threading
import time
import uuid
from typing import Dict, Set, List, Tuple, Optional
from dataclasses import dataclass, field
from accessible_output2.outputs.auto import Auto
from lib.utilities.utilities import read_config, get_config_boolean, get_config_float, get_config_int, calculate_distance

@dataclass
class VisitedGameObject:
    """Represents a visited game object in a match"""
    name: str
    coordinates: Tuple[float, float]
    visit_time: float
    distance_when_visited: float

@dataclass
class MatchSession:
    """Represents a single match session"""
    match_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_time: float = field(default_factory=time.time)
    visited_objects: Dict[str, List[VisitedGameObject]] = field(default_factory=dict)
    is_active: bool = True

class MatchTracker:
    """Tracks game object visits across matches"""
    
    def __init__(self):
        self.speaker = Auto()
        self.current_match: Optional[MatchSession] = None
        self.match_history: List[MatchSession] = []
        
        # State tracking
        self.monitoring_active = False
        self.monitor_thread = None
        self.stop_event = threading.Event()
        
        # Height indicator state tracking with stability
        self.height_indicator_was_visible = False
        self.height_indicator_check_interval = 0.1
        self.last_height_check = 0
        self.height_stable_count = 0
        self.height_stability_threshold = 3  # Require 3 consecutive checks for state change
        
        # Thread safety
        self.match_lock = threading.RLock()
        
        # Performance tracking
        self.last_position_update = 0
        self.position_update_interval = 0.5  # Configurable
        self.current_player_position = None
    
    def start_monitoring(self):
        """Start monitoring for match changes and game object visits"""
        if not self.monitoring_active:
            self.monitoring_active = True
            self.stop_event.clear()
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            print("Match tracking started")
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.monitoring_active = False
        self.stop_event.set()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
        print("Match tracking stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while not self.stop_event.is_set():
            try:
                current_time = time.time()
                
                # Check for height indicator state changes
                if current_time - self.last_height_check >= self.height_indicator_check_interval:
                    self._check_height_indicator_transition()
                    self.last_height_check = current_time
                
                # Update position at configured interval
                if current_time - self.last_position_update >= self.get_position_update_interval():
                    self._update_player_position()
                    self.last_position_update = current_time
                
                # Check for nearby game objects to mark as visited
                self._check_nearby_game_objects()
                
                time.sleep(0.1)  # Main loop frequency
                
            except Exception as e:
                print(f"Error in match tracker loop: {e}")
                time.sleep(1.0)
    
    def _check_height_indicator_transition(self):
        """Check for height indicator visibility transitions with stability checking"""
        try:
            from lib.monitors.height_monitor import is_height_indicator_visible
            
            current_visible = is_height_indicator_visible()
            
            # Only process state changes if we have a stable reading
            if current_visible == self.height_indicator_was_visible:
                # State is stable, reset counter
                self.height_stable_count = 0
                return
            
            # State has changed, increment stability counter
            self.height_stable_count += 1
            
            # Only act on state change if we've had enough consecutive different readings
            if self.height_stable_count >= self.height_stability_threshold:
                # Detect transition from visible to not visible
                if self.height_indicator_was_visible and not current_visible:
                    print("Height indicator disappeared - starting new match")
                    self._start_new_match()
                elif not self.height_indicator_was_visible and current_visible:
                    print("Height indicator appeared")
                
                # Update state
                self.height_indicator_was_visible = current_visible
                self.height_stable_count = 0
            
        except Exception as e:
            print(f"Error checking height indicator transition: {e}")
    
    def _is_height_indicator_visible(self):
        """Safe wrapper for height indicator visibility check"""
        try:
            from lib.monitors.height_monitor import is_height_indicator_visible
            return is_height_indicator_visible()
        except Exception:
            return False
    
    def _update_player_position(self):
        """Update current player position using PPI"""
        try:
            from lib.detection.player_position import find_player_position
            position = find_player_position()
            if position:
                self.current_player_position = position
        except Exception:
            pass
    
    def _start_new_match(self):
        """Start a new match session"""
        with self.match_lock:
            # Close current match if active
            if self.current_match and self.current_match.is_active:
                self.current_match.is_active = False
                self.match_history.append(self.current_match)
                print(f"Match {self.current_match.match_id[:8]} completed")
            
            # Start new match
            self.current_match = MatchSession()
            print(f"New match started: {self.current_match.match_id[:8]}")
            
            # Clear visited objects cache
            self._clear_visited_objects_cache()
            
            # Announce if configured
            config = read_config()
            if get_config_boolean(config, 'AnnounceNewMatch', True):
                self.speaker.speak("New match started")
    
    def _clear_visited_objects_cache(self):
        """Clear the visited objects cache when starting a new match"""
        try:
            # Import here to avoid circular imports
            from lib.guis.visited_objects_gui import ObjectData
            
            # Get the singleton instance and clear its cache
            object_data = ObjectData()
            object_data.clear_cache()
            
            print("Visited objects cache cleared for new match")
            
        except Exception as e:
            print(f"Error clearing visited objects cache: {e}")
    
    def start_new_match(self):
        """Public method to manually start a new match"""
        self._start_new_match()
    
    def _check_nearby_game_objects(self):
        """Check for nearby game objects that should be marked as visited"""
        if not self.current_player_position or not self.current_match:
            return
        
        # Prevent announcements/marking while the height indicator is visible
        if self._is_height_indicator_visible():
            return
            
        try:
            from lib.managers.game_object_manager import game_object_manager
            
            # Get current map
            config = read_config()
            current_map = config.get('POI', 'current_map', fallback='main')
            
            # Get game objects for current map
            game_objects = game_object_manager.get_game_objects_for_map(current_map)
            if not game_objects:
                return
            
            current_time = time.time()
            
            # Check each game object type
            for obj_type, positions in game_objects.items():
                if not self._should_track_object_type(obj_type, current_map):
                    continue
                
                visit_distance = self._get_visit_distance_for_object_type(obj_type, current_map)
                
                for obj_name, x, y in positions:
                    obj_coords = (float(x), float(y))
                    distance = calculate_distance(self.current_player_position, obj_coords)
                    
                    # Check if close enough to mark as visited
                    if distance <= visit_distance:
                        # Mark as visited if not already visited in this match
                        if self._mark_object_visited(obj_type, obj_name, obj_coords, distance, current_time):
                            # This is a new visit, so announce it if configured
                            config = read_config()
                            clean_type = obj_type.replace(' ', '').replace('_', '').replace('-', '').title()
                            announce_key = f'Announce{clean_type}Visits'
                            
                            if self._get_config_boolean_for_map(config, announce_key, current_map, False):
                                self.speaker.speak(f"Reached {obj_type}")
                            
                            print(f"Reached {obj_type} at {obj_coords} (distance: {distance:.1f}m)")
                        
        except Exception as e:
            print(f"Error checking nearby game objects: {e}")
    
    def _should_track_object_type(self, obj_type: str, current_map: str) -> bool:
        """Check if we should track visits for this object type on the current map"""
        config = read_config()
        clean_type = obj_type.replace(' ', '').replace('_', '').replace('-', '').title()
        config_key = f"TrackVisits{clean_type}"
        return self._get_config_boolean_for_map(config, config_key, current_map, True)
    
    def _get_visit_distance_for_object_type(self, obj_type: str, current_map: str) -> float:
        """Get the visit distance threshold for this object type on the current map"""
        config = read_config()
        clean_type = obj_type.replace(' ', '').replace('_', '').replace('-', '').title()
        config_key = f"{clean_type}VisitDistance"
        return self._get_config_float_for_map(config, config_key, current_map, 8.0)  # Default 8 meters
    
    def _get_config_boolean_for_map(self, config, key: str, current_map: str, fallback: bool) -> bool:
        """Get a boolean config value from the appropriate map-specific section"""
        # Determine the appropriate section based on the map
        if current_map == 'main':
            section = 'GameObjects_Main'
        else:
            section = f'GameObjects_{current_map.title()}'
        
        # Try map-specific section first
        if config.has_section(section) and config.has_option(section, key):
            value = config.get(section, key).split('"')[0].strip()
            return value.lower() in ('true', 'yes', 'on', '1')
        
        # Fallback to general GameObjects section
        if config.has_section('GameObjects') and config.has_option('GameObjects', key):
            value = config.get('GameObjects', key).split('"')[0].strip()
            return value.lower() in ('true', 'yes', 'on', '1')
        
        return fallback
    
    def _get_config_float_for_map(self, config, key: str, current_map: str, fallback: float) -> float:
        """Get a float config value from the appropriate map-specific section"""
        # Determine the appropriate section based on the map
        if current_map == 'main':
            section = 'GameObjects_Main'
        else:
            section = f'GameObjects_{current_map.title()}'
        
        # Try map-specific section first
        if config.has_section(section) and config.has_option(section, key):
            value = config.get(section, key).split('"')[0].strip()
            try:
                return float(value)
            except (ValueError, TypeError):
                pass
        
        # Fallback to general GameObjects section
        if config.has_section('GameObjects') and config.has_option('GameObjects', key):
            value = config.get('GameObjects', key).split('"')[0].strip()
            try:
                return float(value)
            except (ValueError, TypeError):
                pass
        
        return fallback
    
    def _mark_object_visited(self, obj_type: str, obj_name: str, coordinates: Tuple[float, float], 
                           distance: float, visit_time: float) -> bool:
        """Mark a game object as visited
        
        Returns:
            bool: True if this is a new visit, False if already visited
        """
        with self.match_lock:
            if not self.current_match:
                return False
            
            # Check if already visited this specific object in this match
            if obj_type in self.current_match.visited_objects:
                for visited in self.current_match.visited_objects[obj_type]:
                    if visited.coordinates == coordinates:
                        return False  # Already visited
            
            # Mark as visited
            visited_obj = VisitedGameObject(
                name=obj_name,
                coordinates=coordinates,
                visit_time=visit_time,
                distance_when_visited=distance
            )
            
            if obj_type not in self.current_match.visited_objects:
                self.current_match.visited_objects[obj_type] = []
            
            self.current_match.visited_objects[obj_type].append(visited_obj)
            return True
    
    def get_position_update_interval(self) -> float:
        """Get the position update interval from config"""
        config = read_config()
        return get_config_float(config, 'PositionUpdateInterval', 0.5)
    
    def get_current_match_stats(self) -> Dict:
        """Get statistics for the current match"""
        with self.match_lock:
            if not self.current_match:
                return {}
            
            stats = {
                'match_id': self.current_match.match_id,
                'start_time': self.current_match.start_time,
                'duration': time.time() - self.current_match.start_time,
                'is_active': self.current_match.is_active,
                'visited_object_types': list(self.current_match.visited_objects.keys()),
                'total_visits': sum(len(visits) for visits in self.current_match.visited_objects.values())
            }
            
            # Add per-type visit counts
            for obj_type, visits in self.current_match.visited_objects.items():
                stats[f'{obj_type}_visits'] = len(visits)
            
            return stats
    
    def get_visited_objects_of_type(self, obj_type: str) -> List[VisitedGameObject]:
        """Get all visited objects of a specific type in the current match"""
        with self.match_lock:
            if not self.current_match or obj_type not in self.current_match.visited_objects:
                return []
            return self.current_match.visited_objects[obj_type].copy()
    
    def has_visited_object_type(self, obj_type: str) -> bool:
        """Check if any object of this type has been visited in the current match"""
        with self.match_lock:
            if not self.current_match:
                return False
            return obj_type in self.current_match.visited_objects and len(self.current_match.visited_objects[obj_type]) > 0
    
    def get_visited_coordinates_for_type(self, obj_type: str) -> Set[Tuple[float, float]]:
        """Get set of visited coordinates for a specific object type"""
        with self.match_lock:
            if not self.current_match or obj_type not in self.current_match.visited_objects:
                return set()
            return {visited.coordinates for visited in self.current_match.visited_objects[obj_type]}
    
    def get_nearest_unvisited_object(self, obj_type: str) -> Optional[Tuple[str, Tuple[float, float]]]:
        """Get the nearest unvisited object of the specified type"""
        if not self.current_player_position:
            return None
        
        try:
            from lib.managers.game_object_manager import game_object_manager
            
            # Get current map
            config = read_config()
            current_map = config.get('POI', 'current_map', fallback='main')
            
            # Get visited coordinates for this type
            visited_coords = self.get_visited_coordinates_for_type(obj_type)
            
            # Use the new method that excludes visited objects
            nearest = game_object_manager.find_nearest_unvisited_object_of_type(
                current_map, obj_type, self.current_player_position, visited_coords
            )
            
            if nearest:
                obj_name, coords, distance = nearest
                return (obj_name, coords)
            
            return None
            
        except Exception as e:
            print(f"Error finding nearest unvisited object: {e}")
            return None

# Global instance
match_tracker = MatchTracker()