import cv2
import numpy as np
import heapq
import time
import threading
import pyautogui
import ctypes
from lib.spatial_audio import SpatialAudio
from lib.utilities import get_config_int, get_config_float, get_config_boolean, read_config
from accessible_output2.outputs.auto import Auto
from lib.player_position import find_player_position, find_minimap_icon_direction, ROI_START_ORIG, ROI_END_ORIG
from lib.icon import auto_turn_towards_poi, find_closest_poi
from lib.guis.poi_selector_gui import POIData

speaker = Auto()

# Define sound file paths
POINT_REACHED_SOUND = 'sounds/point_reached.ogg'
PATHFINDING_SUCCESS_SOUND = 'sounds/pathfinding_success.ogg'
NEXT_POINT_PING_SOUND = 'sounds/next_point_ping.ogg'
FACING_POINT_SOUND = 'sounds/facing_point.ogg'

# Initialize SpatialAudio for each sound
spatial_next_point_ping = SpatialAudio(NEXT_POINT_PING_SOUND)
spatial_point_reached = SpatialAudio(POINT_REACHED_SOUND)
spatial_pathfinding_success = SpatialAudio(PATHFINDING_SUCCESS_SOUND)
spatial_facing_point = SpatialAudio(FACING_POINT_SOUND)

# Define colors (BGR format)
INACCESSIBLE = (0, 0, 255)
WATER = (255, 0, 0)
ROADS = (0, 75, 150)

# Define costs for different terrains
COST = {
    'road': 1,
    'nothing': 2,
    'water': 3,
    'inaccessible': 255
}

def manhattan_distance(a, b):
    return abs(b[0] - a[0]) + abs(b[1] - a[1])

def create_cost_map(overlay):
    if overlay is None:
        print("Error: Overlay image not loaded")
        return None
    
    cost_map = np.full(overlay.shape[:2], COST['nothing'], dtype=np.uint8)
    
    if overlay.shape[2] == 4:  # If the image has an alpha channel
        overlay = cv2.cvtColor(overlay, cv2.COLOR_BGRA2BGR)
    
    cost_map[np.all(overlay == ROADS, axis=2)] = COST['road']
    cost_map[np.all(overlay == WATER, axis=2)] = COST['water']
    cost_map[np.all(overlay == INACCESSIBLE, axis=2)] = COST['inaccessible']
    
    return cost_map

def a_star(start, goal, cost_map):
    if cost_map is None or not (0 <= start[0] < cost_map.shape[0] and 0 <= start[1] < cost_map.shape[1]) or \
       not (0 <= goal[0] < cost_map.shape[0] and 0 <= goal[1] < cost_map.shape[1]) or \
       cost_map[start] == COST['inaccessible'] or cost_map[goal] == COST['inaccessible']:
        return None

    def get_neighbors(pos):
        x, y = pos
        for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < cost_map.shape[0] and 0 <= ny < cost_map.shape[1]:
                yield (nx, ny)

    # Use np.float64 to prevent overflow
    g_score = {start: np.float64(0)}
    f_score = {start: np.float64(manhattan_distance(start, goal))}
    open_heap = [(f_score[start], start)]
    came_from = {}

    while open_heap:
        current = heapq.heappop(open_heap)[1]

        if current == goal:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start)
            return path[::-1]

        for neighbor in get_neighbors(current):
            # Ensure the costs are cast to float64 to avoid overflow
            tentative_g_score = g_score[current] + np.float64(cost_map[neighbor])

            if neighbor not in g_score or tentative_g_score < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g_score
                f_score[neighbor] = g_score[neighbor] + np.float64(manhattan_distance(neighbor, goal))
                heapq.heappush(open_heap, (f_score[neighbor], neighbor))

    return None

def optimize_path(path, cost_map, max_distance=50):
    optimized_path = [path[0]]
    current_point = path[0]
    
    for point in path[1:]:
        if manhattan_distance(current_point, point) > max_distance:
            intermediate_path = a_star(current_point, point, cost_map)
            if intermediate_path:
                optimized_path.extend(intermediate_path[1:-1])
            optimized_path.append(point)
            current_point = point
    
    reduced_path = [optimized_path[0]]
    for i in range(1, len(optimized_path) - 1):
        if i % 3 == 0:  # Keep every 3rd point
            reduced_path.append(optimized_path[i])
    reduced_path.append(optimized_path[-1])
    
    return reduced_path

class Pathfinder:
    def __init__(self):
        self.config = read_config()
        self.overlay = cv2.imread('overlay.png', cv2.IMREAD_UNCHANGED)
        if self.overlay is None:
            print("Error: Failed to load overlay.png")
        else:
            print(f"Loaded overlay.png, shape: {self.overlay.shape}")
        self.cost_map = create_cost_map(self.overlay)
        self.current_path = []
        self.current_point_index = 0
        self.active = False
        self.stop_event = threading.Event()
        self.consecutive_position_fails = 0
        self.auto_turn_failures = 0
        self.last_position = None
        self.poi_name = ""
        self.update_config()
        self.current_sound = None
        self.current_facing_point_index = -1
        self.last_facing_state = False

    def update_config(self):
        self.config = read_config()  # Re-read the config
        self.auto_turn_enabled = get_config_boolean(self.config, 'AutoTurn', False)
        self.pathfinding_check_interval = get_config_float(self.config, 'PathfindingCheckInterval', 0.2)
        self.pathfinding_point_radius = get_config_int(self.config, 'PathfindingPointRadius', 10)
        self.minimum_movement_distance = get_config_float(self.config, 'MinimumMovementDistance', 2)
        self.ping_volume_max_distance = get_config_float(self.config, 'PingVolumeMaxDistance', 100)
        self.ping_frequency = get_config_float(self.config, 'PingFrequency', 0.5)
        self.facing_point_angle_threshold = get_config_float(self.config, 'FacingPointAngleThreshold', 30)
        self.perform_facing_check = get_config_boolean(self.config, 'PerformFacingCheck', True)

    def convert_to_overlay_coordinates(self, x, y):
        overlay_x = int((x - ROI_START_ORIG[0]) * (self.overlay.shape[1] / (ROI_END_ORIG[0] - ROI_START_ORIG[0])))
        overlay_y = int((y - ROI_START_ORIG[1]) * (self.overlay.shape[0] / (ROI_END_ORIG[1] - ROI_START_ORIG[1])))
        return (overlay_y, overlay_x)

    def convert_to_screen_coordinates(self, y, x):
        screen_x = int(x * ((ROI_END_ORIG[0] - ROI_START_ORIG[0]) / self.overlay.shape[1]) + ROI_START_ORIG[0])
        screen_y = int(y * ((ROI_END_ORIG[1] - ROI_START_ORIG[1]) / self.overlay.shape[0]) + ROI_START_ORIG[1])
        return (screen_x, screen_y)

    def start_pathfinding(self, start, goal, poi_name):
        self.update_config()
        start_overlay = self.convert_to_overlay_coordinates(*start)
        goal_overlay = self.convert_to_overlay_coordinates(*goal)
        print(f"Starting pathfinding from {start_overlay} to {goal_overlay}")

        self.poi_name = poi_name
        speaker.speak(f"Pathfinding to {self.poi_name}")

        self.current_path = a_star(start_overlay, goal_overlay, self.cost_map)
        if self.current_path:
            self.current_path = optimize_path(self.current_path, self.cost_map)
            self.current_path = [self.convert_to_screen_coordinates(y, x) for y, x in self.current_path]
            self.current_point_index = 0
            self.active = True
            self.stop_event.clear()

            self.threads = [
                threading.Thread(target=self.pathfinding_loop),
                threading.Thread(target=self.movement_check_loop),
                threading.Thread(target=self.auto_turn_loop if self.auto_turn_enabled else self.audio_ping_loop)
            ]
            
            for thread in self.threads:
                thread.start()
        else:
            speaker.speak("Unable to find a path")

    def stop_pathfinding(self):
        self.active = False
        self.stop_event.set()

        if self.current_sound:
            self.current_sound.stop()
            self.current_sound = None

        for thread in self.threads:
            if thread.is_alive():
                try:
                    thread_id = thread.ident
                    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread_id), ctypes.py_object(SystemExit))
                    if res > 1:
                        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread_id), None)
                        print(f"Exception raise failure for thread {thread_id}")
                except Exception as e:
                    print(f"Error terminating thread: {e}")

        time.sleep(0.1)
        self.threads.clear()
        speaker.speak("Pathfinding stopped")

    def pathfinding_loop(self):
        while not self.stop_event.is_set():
            try:
                self.check_progress()
                time.sleep(self.pathfinding_check_interval)
            except Exception as e:
                print(f"Error in pathfinding loop: {e}")
                self.stop_event.set()

    def audio_ping_loop(self):
        """Audio ping loop to give feedback on the player's position relative to the next waypoint."""
        while not self.stop_event.is_set():
            if self.current_point_index < len(self.current_path):
                player_position = find_player_position()
                player_direction, _ = find_minimap_icon_direction()
                if player_position and player_direction:
                    next_point = self.current_path[self.current_point_index]
                    distance = self.calculate_distance(player_position, next_point)
                    angle = self.calculate_angle(player_position, player_direction, next_point)
                    
                    if self.perform_facing_check:
                        facing_point = abs(angle) <= self.facing_point_angle_threshold
                        
                        if facing_point:
                            if not self.last_facing_state or self.current_facing_point_index != self.current_point_index:
                                spatial_facing_point.play_audio(left_weight=1.0, right_weight=1.0, volume=1.0)
                                self.current_facing_point_index = self.current_point_index
                        else:
                            self.play_spatial_sound(distance, angle)
                        
                        self.last_facing_state = facing_point
                    else:
                        # Always play the next point sound when perform_facing_check is off
                        self.play_spatial_sound(distance, angle)
                    
                    time.sleep(self.ping_frequency)
            else:
                self.current_facing_point_index = -1
                self.last_facing_state = False
            time.sleep(0.01)

    def calculate_distance(self, start, end):
        return np.linalg.norm(np.array(start) - np.array(end)) * 2.65

    def calculate_angle(self, player_pos, player_dir, target_pos):
        player_pos = np.array(player_pos)
        target_pos = np.array(target_pos)
        
        direction_to_vector = {
            'North': [0, -1], 'Northeast': [1, -1], 'East': [1, 0], 'Southeast': [1, 1],
            'South': [0, 1], 'Southwest': [-1, 1], 'West': [-1, 0], 'Northwest': [-1, -1]
        }
        player_vector = np.array(direction_to_vector.get(player_dir, [0, -1]))
        
        target_vector = target_pos - player_pos
        
        player_vector = player_vector / np.linalg.norm(player_vector)
        target_vector = target_vector / np.linalg.norm(target_vector)
        
        dot_product = np.dot(player_vector, target_vector)
        angle = np.degrees(np.arccos(np.clip(dot_product, -1.0, 1.0)))
        
        cross_product = np.cross(player_vector, target_vector)
        if cross_product < 0:
            angle = -angle
        
        return angle

    def play_spatial_sound(self, distance, angle):
        """Play a spatial sound based on the player's distance and angle to the next waypoint."""
        # Stop any currently playing sound
        if self.current_sound:
            self.current_sound.stop()
            self.current_sound = None

        # Calculate volume based on distance
        volume_factor = 1 - min(distance / self.ping_volume_max_distance, 1)

        # Calculate stereo panning based on angle
        pan = np.clip(angle / 90, -1, 1)
        left_volume = np.clip((1 - pan) / 2, 0, 1)
        right_volume = np.clip((1 + pan) / 2, 0, 1)

        # Play the spatial audio using the ping sound
        spatial_next_point_ping.play_audio(
            left_weight=left_volume,
            right_weight=right_volume,
            volume=volume_factor
        )

    def movement_check_loop(self):
        while not self.stop_event.is_set():
            player_position = find_player_position()
            if player_position:
                if self.last_position:
                    distance_moved = np.linalg.norm(np.array(player_position) - np.array(self.last_position))
                    if distance_moved < self.minimum_movement_distance:
                        print(f"Player moved less than {self.minimum_movement_distance} meters")
                self.last_position = player_position
            time.sleep(1)

    def check_progress(self):
        player_position = find_player_position()

        if player_position is None:
            self.consecutive_position_fails += 1
            if self.consecutive_position_fails >= 3:
                speaker.speak("Unable to determine player position. Stopping pathfinding.")
                self.stop_event.set()
            return
        self.consecutive_position_fails = 0

        while self.current_point_index < len(self.current_path):
            current_point = self.current_path[self.current_point_index]
            distance_to_current = self.calculate_distance(player_position, current_point)

            # Check if the player is closer to any further point on the path
            for i in range(self.current_point_index + 1, len(self.current_path)):
                next_point = self.current_path[i]
                distance_to_next = self.calculate_distance(player_position, next_point)
                
                if distance_to_next < distance_to_current:
                    # Player is closer to a further point, consider current point reached
                    self.current_point_index = i  # Update to the furthest point the player is closer to
                    spatial_point_reached.play_audio(left_weight=1.0, right_weight=1.0, volume=1.0)
                    points_left = len(self.current_path) - self.current_point_index
                    
                    if points_left > 0:
                        speaker.speak(f"{points_left} point{'s' if points_left > 1 else ''} left")
                        self.current_facing_point_index = -1
                        self.last_facing_state = False
                    
                    if self.current_point_index >= len(self.current_path):
                        spatial_pathfinding_success.play_audio(left_weight=1.0, right_weight=1.0, volume=1.0)
                        speaker.speak(f"Reached {self.poi_name}")
                        self.stop_pathfinding()
                        self.stop_event.set()
                        return
                    
                    break  # Exit the inner loop and continue checking from the new current point
            else:
                # If we didn't break from the inner loop, check if we're close enough to the current point
                if distance_to_current <= self.pathfinding_point_radius:
                    self.current_point_index += 1
                    spatial_point_reached.play_audio(left_weight=1.0, right_weight=1.0, volume=1.0)
                    points_left = len(self.current_path) - self.current_point_index
                    
                    if points_left > 0:
                        speaker.speak(f"{points_left} point{'s' if points_left > 1 else ''} left")
                        self.current_facing_point_index = -1
                        self.last_facing_state = False
                    
                    if self.current_point_index >= len(self.current_path):
                        spatial_pathfinding_success.play_audio(left_weight=1.0, right_weight=1.0, volume=1.0)
                        speaker.speak(f"Reached {self.poi_name}")
                        self.stop_pathfinding()
                        self.stop_event.set()
                        return
                else:
                    break  # Exit the outer loop if we're not close enough to the current point

    def auto_turn_loop(self):
        """Auto-turn loop for navigating towards waypoints."""
        while not self.stop_event.is_set():
            if self.current_point_index < len(self.current_path):
                player_position = find_player_position()
                player_direction, _ = find_minimap_icon_direction()
                if player_position and player_direction:
                    next_point = self.current_path[self.current_point_index]
                    angle = self.calculate_angle(player_position, player_direction, next_point)
                    
                    if self.perform_facing_check:
                        facing_point = abs(angle) <= self.facing_point_angle_threshold
                        
                        if facing_point:
                            if not self.last_facing_state or self.current_facing_point_index != self.current_point_index:
                                spatial_facing_point.play_audio(left_weight=1.0, right_weight=1.0, volume=1.0)
                                self.current_facing_point_index = self.current_point_index
                            self.auto_turn_failures = 0
                        else:
                            success = auto_turn_towards_poi(player_position, next_point, f"Point {self.current_point_index + 1}")
                            if success:
                                self.auto_turn_failures = 0
                            else:
                                self.auto_turn_failures += 1
                                if self.auto_turn_failures >= 3:
                                    speaker.speak("Auto-turn failed multiple times. Please turn manually.")
                                    self.auto_turn_failures = 0
                        
                        self.last_facing_state = facing_point
                    else:
                        # When perform_facing_check is off, always attempt to auto-turn
                        auto_turn_towards_poi(player_position, next_point, f"Point {self.current_point_index + 1}")
                
                time.sleep(0.5)
            else:
                self.current_facing_point_index = -1
                self.last_facing_state = False
            time.sleep(0.01)

pathfinder_instance = None

def toggle_pathfinding():
    global pathfinder_instance
    
    if pathfinder_instance is None:
        pathfinder_instance = Pathfinder()
    else:
        pathfinder_instance.update_config()

    config = read_config()
    selected_poi = config['POI']['selected_poi'].split(', ')
    
    if len(selected_poi) == 3:
        start = find_player_position()
        if start:
            poi_name = selected_poi[0]
            if poi_name.lower() == 'closest':
                # Initialize POI data with new coordinate system
                poi_data = POIData()
                # Combine main POIs and landmarks
                all_pois = [(poi[0], int(float(poi[1])), int(float(poi[2]))) 
                           for poi in poi_data.main_pois + poi_data.landmarks]
                closest_poi = find_closest_poi(start, all_pois)
                if closest_poi:
                    poi_name, coordinates = closest_poi
                    goal = coordinates
                else:
                    speaker.speak("No POIs found to pathfind to.")
                    return
            else:
                try:
                    x = int(float(selected_poi[1]))
                    y = int(float(selected_poi[2]))
                    goal = (x, y)
                except ValueError:
                    speaker.speak("Invalid POI coordinates")
                    return

            if pathfinder_instance.active:
                pathfinder_instance.stop_pathfinding()
            else:
                pathfinder_instance.start_pathfinding(start, goal, poi_name)
        else:
            speaker.speak("Unable to determine player position")
    else:
        speaker.speak("No valid POI selected")