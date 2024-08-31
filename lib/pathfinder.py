import cv2
import numpy as np
import heapq
import time
import threading
import pygame
import pyautogui
import ctypes
import soundfile as sf
from lib.ppi import find_player_position
from lib.utilities import get_config_int, get_config_float, get_config_boolean, read_config
from accessible_output2.outputs.auto import Auto
from lib.player_location import ROI_START_ORIG, ROI_END_ORIG, calculate_poi_info, generate_poi_message
from lib.minimap_direction import find_minimap_icon_direction
from lib.mouse import smooth_move_mouse
from lib.icon import auto_turn_towards_poi

# Try to import simpleaudio, but provide a fallback if it's not available
try:
    import simpleaudio as sa
    SIMPLEAUDIO_AVAILABLE = True
except ImportError:
    SIMPLEAUDIO_AVAILABLE = False
    print("simpleaudio is not available. Some audio features will be disabled.")

speaker = Auto()

# Initialize pygame mixer
pygame.mixer.init()

# Define sound file paths
POINT_REACHED_SOUND = 'sounds/point_reached.ogg'
PATHFINDING_SUCCESS_SOUND = 'sounds/pathfinding_success.ogg'
NEXT_POINT_PING_SOUND = 'sounds/next_point_ping.ogg'

# Load sounds
point_reached_sound = pygame.mixer.Sound(POINT_REACHED_SOUND)
pathfinding_success_sound = pygame.mixer.Sound(PATHFINDING_SUCCESS_SOUND)
next_point_ping_sound = pygame.mixer.Sound(NEXT_POINT_PING_SOUND)

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
    
    print(f"Overlay shape: {overlay.shape}")
    cost_map = np.full(overlay.shape[:2], COST['nothing'], dtype=np.uint8)
    
    if overlay.shape[2] == 4:  # If the image has an alpha channel
        overlay = cv2.cvtColor(overlay, cv2.COLOR_BGRA2BGR)
    
    cost_map[np.all(overlay == ROADS, axis=2)] = COST['road']
    cost_map[np.all(overlay == WATER, axis=2)] = COST['water']
    cost_map[np.all(overlay == INACCESSIBLE, axis=2)] = COST['inaccessible']
    
    print(f"Cost map shape: {cost_map.shape}")
    print(f"Unique values in cost map: {np.unique(cost_map)}")
    return cost_map

def a_star(start, goal, cost_map):
    print(f"A* search from {start} to {goal}")
    if cost_map is None:
        print("Error: Cost map is None")
        return None
    
    if not (0 <= start[0] < cost_map.shape[0] and 0 <= start[1] < cost_map.shape[1]):
        print(f"Error: Start position {start} is out of bounds")
        return None
    
    if not (0 <= goal[0] < cost_map.shape[0] and 0 <= goal[1] < cost_map.shape[1]):
        print(f"Error: Goal position {goal} is out of bounds")
        return None
    
    if cost_map[start] == COST['inaccessible'] or cost_map[goal] == COST['inaccessible']:
        print("Error: Start or goal is in an inaccessible area")
        return None

    def get_neighbors(pos):
        x, y = pos
        for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < cost_map.shape[0] and 0 <= ny < cost_map.shape[1]:
                yield (nx, ny)

    g_score = {start: 0}
    f_score = {start: manhattan_distance(start, goal)}
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
            tentative_g_score = g_score[current] + cost_map[neighbor]

            if neighbor not in g_score or tentative_g_score < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g_score
                f_score[neighbor] = g_score[neighbor] + manhattan_distance(neighbor, goal)
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
    
    # Further reduce the number of points, but keep more than before
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
        self.last_check_time = 0
        self.pathfinding_thread = None
        self.auto_turn_thread = None
        self.movement_check_thread = None
        self.audio_ping_thread = None
        self.stop_event = threading.Event()
        self.consecutive_position_fails = 0
        self.auto_turn_failures = 0
        self.last_position = None
        self.poi_name = ""
        self.update_config()
        self.load_audio()
        self.threads = []
        self.current_sound = None

    def load_audio(self):
        try:
            audio_data, self.sample_rate = sf.read(NEXT_POINT_PING_SOUND)
            self.ping_sound = audio_data.astype(np.float32)
            if self.ping_sound.ndim == 2:
                self.ping_sound = self.ping_sound.mean(axis=1)  # Convert stereo to mono
            self.ping_sound = self.ping_sound / np.max(np.abs(self.ping_sound))  # Normalize
        except Exception as e:
            print(f"Error loading audio: {e}")
            self.ping_sound = None
            self.sample_rate = None

    def update_config(self):
        self.config = read_config()  # Re-read the config
        self.auto_turn_enabled = get_config_boolean(self.config, 'SETTINGS', 'AutoTurn', False)
        self.pathfinding_check_interval = get_config_float(self.config, 'SETTINGS', 'PathfindingCheckInterval', 0.2)
        self.pathfinding_point_radius = get_config_int(self.config, 'SETTINGS', 'PathfindingPointRadius', 10)
        self.minimum_movement_distance = get_config_float(self.config, 'SETTINGS', 'MinimumMovementDistance', 2)

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
        print(f"Starting pathfinding from {start} to {goal}")
        start_overlay = self.convert_to_overlay_coordinates(*start)
        goal_overlay = self.convert_to_overlay_coordinates(*goal)
        print(f"Converted coordinates: start {start_overlay}, goal {goal_overlay}")

        self.poi_name = poi_name
        speaker.speak(f"Pathfinding to {self.poi_name}")

        self.current_path = a_star(start_overlay, goal_overlay, self.cost_map)
        if self.current_path:
            self.current_path = optimize_path(self.current_path, self.cost_map)
            self.current_path = [self.convert_to_screen_coordinates(y, x) for y, x in self.current_path]
            self.current_point_index = 0
            self.active = True
            self.last_check_time = 0
            self.stop_event.clear()

            self.threads = []
            self.threads.append(threading.Thread(target=self.pathfinding_loop))
            self.threads.append(threading.Thread(target=self.movement_check_loop))
            
            if self.auto_turn_enabled:
                self.threads.append(threading.Thread(target=self.auto_turn_loop))
            else:
                self.threads.append(threading.Thread(target=self.audio_ping_loop))
            
            for thread in self.threads:
                thread.start()
        else:
            speaker.speak("Unable to find a path")

    def stop_pathfinding(self):
        self.active = False
        self.stop_event.set()

        # Stop any currently playing sound
        if self.current_sound:
            self.current_sound.stop()
            self.current_sound = None

        # Forcefully terminate all threads
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

        # Wait a short time for threads to terminate
        time.sleep(0.1)

        # Clear the threads list
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
        while not self.stop_event.is_set():
            if self.current_point_index < len(self.current_path):
                player_position = find_player_position()
                player_direction, _ = find_minimap_icon_direction()
                if player_position and player_direction:
                    next_point = self.current_path[self.current_point_index]
                    distance = self.calculate_distance(player_position, next_point)
                    angle = self.calculate_angle(player_position, player_direction, next_point)
                    
                    print(f"Player at {player_position}, facing {player_direction}")
                    print(f"Next point at {next_point}, distance: {distance:.2f}, angle: {angle:.2f}")
                    
                    self.play_spatial_sound(distance, angle)
                    
                    time.sleep(0.5)  # Play the ping every second
            time.sleep(0.01)

    def calculate_distance(self, start, end):
        return np.linalg.norm(np.array(start) - np.array(end)) * 2.65

    def calculate_angle(self, player_pos, player_dir, target_pos):
        target_vector = np.array(target_pos) - np.array(player_pos)
        target_angle = np.degrees(np.arctan2(target_vector[1], target_vector[0]))
        
        direction_to_angle = {
            'North': 0, 'Northeast': 45, 'East': 90, 'Southeast': 135,
            'South': 180, 'Southwest': 225, 'West': 270, 'Northwest': 315
        }
        player_angle = direction_to_angle.get(player_dir, 0)
        
        relative_angle = (target_angle - player_angle) % 360
        return relative_angle

    def play_spatial_sound(self, distance, angle):
        if self.current_sound:
            self.current_sound.stop()
            self.current_sound = None

        if not SIMPLEAUDIO_AVAILABLE:
            # Fallback to pygame for audio playback
            next_point_ping_sound.set_volume(1 - min(distance / 100, 1))
            next_point_ping_sound.play()
            return

        max_distance = 100  # Maximum distance at which the ping is audible
        volume_factor = 1 - min(distance / max_distance, 1)
        
        # Adjust volume based on distance
        adjusted_sound = self.ping_sound * volume_factor

        # Adjust angle so that 0 degrees is directly in front of the player
        adjusted_angle = (90 - angle) % 360

        # Calculate pan based on adjusted angle
        # -1 is full left, 1 is full right
        pan = np.sin(np.radians(adjusted_angle))

        # Create stereo sound
        left_volume = np.clip((1 - pan) / 2, 0, 1)
        right_volume = np.clip((1 + pan) / 2, 0, 1)
        
        stereo_sound = np.column_stack((adjusted_sound * left_volume, adjusted_sound * right_volume))

        # Ensure the audio data is in the correct format for simpleaudio
        stereo_sound = (stereo_sound * 32767).astype(np.int16)

        # Play the sound
        self.current_sound = sa.play_buffer(stereo_sound, 2, 2, self.sample_rate)

        print(f"Playing sound: distance={distance:.2f}, angle={angle:.2f}, "
              f"adjusted_angle={adjusted_angle:.2f}, pan={pan:.2f}, "
              f"left_volume={left_volume:.2f}, right_volume={right_volume:.2f}")

    def movement_check_loop(self):
        while not self.stop_event.is_set():
            player_position = find_player_position()
            if player_position:
                if self.last_position:
                    distance_moved = np.linalg.norm(np.array(player_position) - np.array(self.last_position))
                    if distance_moved < self.minimum_movement_distance:
                        print(f"Player moved less than {self.minimum_movement_distance} meters")
                self.last_position = player_position
            time.sleep(1)  # Check every second

    def check_progress(self):
        player_position = find_player_position()

        if player_position is None:
            self.consecutive_position_fails += 1
            if self.consecutive_position_fails >= 3:
                speaker.speak("Unable to determine player position. Stopping pathfinding.")
                self.stop_event.set()  # Signal to stop pathfinding
            return
        self.consecutive_position_fails = 0

        while self.current_point_index < len(self.current_path):
            current_point = self.current_path[self.current_point_index]
            distance = self.calculate_distance(player_position, current_point)

            if distance <= self.pathfinding_point_radius:
                point_reached_sound.play()  # Play sound when reaching a point
                self.current_point_index += 1
                if self.current_point_index >= len(self.current_path):
                    pathfinding_success_sound.play()  # Play success sound
                    speaker.speak(f"Reached {self.poi_name}")
                    self.stop_event.set()  # Signal to stop pathfinding
                    return
                else:
                    speaker.speak(f"Point {self.current_point_index} of {len(self.current_path)}")
            else:
                break

    def calculate_distance(self, start, end):
        return np.linalg.norm(np.array(start) - np.array(end)) * 2.65

pathfinder_instance = None

def toggle_pathfinding():
    global pathfinder_instance
    
    if pathfinder_instance is None:
        pathfinder_instance = Pathfinder()
    else:
        pathfinder_instance.update_config()  # Ensure config is up-to-date

    config = read_config()
    selected_poi = config['POI']['selected_poi'].split(', ')
    
    print(f"Selected POI: {selected_poi}")
    
    if len(selected_poi) == 3:
        start = find_player_position()
        goal = (int(selected_poi[1]), int(selected_poi[2]))
        poi_name = selected_poi[0]  # Get POI name
        print(f"Start: {start}, Goal: {goal}")
        if start:
            if pathfinder_instance.active:
                pathfinder_instance.stop_pathfinding()
            else:
                pathfinder_instance.start_pathfinding(start, goal, poi_name)
        else:
            speaker.speak("Unable to determine player position")
    else:
        speaker.speak("No valid POI selected")
