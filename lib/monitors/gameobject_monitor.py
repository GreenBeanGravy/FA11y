"""
Background game object detection and spatial audio system
"""
import threading
import time
import os
from typing import Dict, Optional, Tuple
from accessible_output2.outputs.auto import Auto
from lib.utils.utilities import read_config, get_config_boolean, get_config_float, calculate_distance
from lib.monitors.background_checks import monitor
from lib.vision.object_finder import optimized_finder, OBJECT_CONFIGS
from lib.vision.player_position import find_player_position, find_minimap_icon_direction
from lib.audio.spatial_audio import SpatialAudio

class GameObjectAudioThread:
    """Manages audio for a single game object with configurable ping intervals"""
    
    def __init__(self, object_name: str, audio_instance: SpatialAudio, ping_interval: float):
        self.object_name = object_name
        self.audio_instance = audio_instance
        self.ping_interval = ping_interval
        self.stop_event = threading.Event()
        self.thread = None
        self.current_position = None
        self.current_distance = None
        self.position_lock = threading.Lock()
        
    def start(self, position: Tuple[int, int], distance: float):
        """Start the audio thread"""
        with self.position_lock:
            self.current_position = position
            self.current_distance = distance
        
        if not self.thread or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._audio_loop, daemon=True)
            self.thread.start()
    
    def update_position(self, position: Tuple[int, int], distance: float):
        """Update the object's position and distance"""
        with self.position_lock:
            self.current_position = position
            self.current_distance = distance
    
    def stop(self):
        """Stop the audio thread"""
        self.stop_event.set()
        if self.audio_instance:
            try:
                self.audio_instance.stop()
            except Exception:
                pass
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
    
    def _audio_loop(self):
        """Main audio loop that plays pings at configured intervals"""
        while not self.stop_event.is_set():
            try:
                # Get current position data
                with self.position_lock:
                    position = self.current_position
                    distance = self.current_distance
                
                if position and distance is not None:
                    # Get player angle for spatial audio
                    _, player_angle = find_minimap_icon_direction()
                    if player_angle is not None:
                        player_pos = find_player_position()
                        if player_pos:
                            self._play_spatial_audio(player_pos, player_angle, position, distance)
                
                # Wait for ping interval or stop event
                if self.stop_event.wait(timeout=self.ping_interval):
                    break
                    
            except Exception:
                # Continue on error
                time.sleep(0.1)
    
    def _play_spatial_audio(self, player_pos: Tuple[int, int], player_angle: float, 
                           object_pos: Tuple[int, int], distance: float):
        """Play spatial audio for the object"""
        if not self.audio_instance:
            return
        
        try:
            # Calculate distance and relative angle using universal calculation
            calc_distance, relative_angle = SpatialAudio.calculate_distance_and_angle(
                player_pos, player_angle, object_pos
            )
            
            # Enhanced falloff parameters
            max_distance = 250.0
            min_volume = 0.05
            max_volume = 0.3  # Reduced to avoid overwhelming with multiple objects
            
            # More aggressive falloff curve - exponential instead of linear
            distance_factor = min(distance / max_distance, 1.0)
            volume_factor = (1.0 - distance_factor) ** 1.8
            volume = min_volume + (max_volume - min_volume) * volume_factor
            
            import numpy as np
            volume = np.clip(volume, min_volume, max_volume)
            
            self.audio_instance.play_audio(
                distance=calc_distance,
                relative_angle=relative_angle,
                volume=volume
            )
            
        except Exception:
            pass

class GameObjectMonitor:
    """Background monitor for nearby game objects with spatial audio"""
    
    def __init__(self):
        self.speaker = Auto()
        self.running = False
        self.stop_event = threading.Event()
        
        # Separate threads for detection and audio management
        self.detection_thread = None
        
        # Audio system for game objects
        self.audio_instances = {}
        self.default_audio = None
        self.active_audio_threads = {}  # object_name -> GameObjectAudioThread
        
        # Thread-safe communication
        self.detection_data = {}
        self.detection_lock = threading.Lock()
        
        # Timing configuration
        self.detection_interval = 6.0
        self.object_timeout = 8.0  # Increased timeout for better stability
        self.min_distance_for_audio = 10.0
        
        self.initialize_audio()
    
    def initialize_audio(self):
        """Initialize spatial audio instances for each game object"""
        default_sound_path = 'sounds/gameobject.ogg'
        
        if os.path.exists(default_sound_path):
            try:
                self.default_audio = SpatialAudio(default_sound_path)
                # Set up volume management
                config = read_config()
                master_volume, gameobject_volume = SpatialAudio.get_volume_from_config(
                    config, 'GameObjectVolume', 'MasterVolume', 1.0
                )
                self.default_audio.set_master_volume(master_volume)
                self.default_audio.set_individual_volume(gameobject_volume)
            except Exception:
                self.default_audio = None
        
        for object_name in OBJECT_CONFIGS.keys():
            object_sound_path = f'sounds/{object_name}.ogg'
            
            if os.path.exists(object_sound_path):
                try:
                    audio_instance = SpatialAudio(object_sound_path)
                    # Set up volume management for individual object sounds
                    config = read_config()
                    master_volume, individual_volume = SpatialAudio.get_volume_from_config(
                        config, f"{object_name.replace('_', '').title()}Volume", 'MasterVolume', 1.0
                    )
                    audio_instance.set_master_volume(master_volume)
                    audio_instance.set_individual_volume(individual_volume)
                    self.audio_instances[object_name] = audio_instance
                except Exception:
                    continue
    
    def get_audio_instance(self, object_name: str) -> Optional[SpatialAudio]:
        """Get audio instance for specific object, fall back to default"""
        return self.audio_instances.get(object_name, self.default_audio)
    
    def is_enabled(self) -> bool:
        """Check if game object monitoring is enabled in config"""
        config = read_config()
        return get_config_boolean(config, 'MonitorGameObjects', False)
    
    def should_monitor(self) -> bool:
        """Check if monitoring should be active"""
        return self.is_enabled() and not monitor.map_open
    
    def is_object_enabled(self, object_name: str) -> bool:
        """Check if a specific object type is enabled for monitoring"""
        config = read_config()
        config_key = f"Monitor{object_name.replace('_', '').title()}"
        return get_config_boolean(config, config_key, True)
    
    def get_object_ping_interval(self, object_name: str) -> float:
        """Get the ping interval for a specific object type"""
        config = read_config()
        config_key = f"{object_name.replace('_', '').title()}PingInterval"
        return get_config_float(config, config_key, 2.0)
    
    def detect_objects_on_minimap(self) -> Dict[str, Tuple[int, int]]:
        """Detects objects on the minimap and returns their screen coordinates."""
        try:
            enabled_objects = [
                obj_name for obj_name in OBJECT_CONFIGS.keys()
                if self.is_object_enabled(obj_name)
            ]
            
            if not enabled_objects:
                return {}
            
            detected_objects = optimized_finder.find_objects_on_minimap_screen(enabled_objects)
            return detected_objects
            
        except Exception:
            return {}
    
    def should_play_audio_for_distance(self, distance: float) -> bool:
        """Check if audio should play based on distance"""
        return distance > self.min_distance_for_audio
    
    def detection_loop(self):
        """Dedicated thread for object detection with fixed timing"""
        last_detection_time = 0
        
        while not self.stop_event.is_set():
            try:
                current_time = time.time()
                
                if not self.should_monitor():
                    self.cleanup_all_audio_threads()
                    time.sleep(2.0)
                    continue
                
                # Perform detection at fixed intervals only
                if current_time - last_detection_time >= self.detection_interval:
                    last_detection_time = current_time
                    
                    # Step 1: Detect on minimap, get screen coords
                    detected_minimap_objects = self.detect_objects_on_minimap()
                    
                    detection_update = {}
                    
                    if detected_minimap_objects:
                        # Step 2: Get player position only if objects are found
                        player_pos = find_player_position()
                        if player_pos:
                            # Step 3: Convert to fullmap coords and prepare update data
                            for obj_name, minimap_coords in detected_minimap_objects.items():
                                fullmap_coords = optimized_finder.convert_minimap_to_fullmap_coords(
                                    minimap_coords, player_pos
                                )
                                distance = calculate_distance(player_pos, fullmap_coords)
                                detection_update[obj_name] = {
                                    'coords': fullmap_coords,
                                    'distance': distance,
                                    'last_seen': current_time,
                                    'player_pos': player_pos
                                }
                    
                    # This structure ensures that if no objects are detected, or if player_pos is not found,
                    # an empty detection_update dict is passed to update_audio_threads, which will
                    # correctly clean up any old, no-longer-visible object threads.
                    with self.detection_lock:
                        self.detection_data = detection_update
                    
                    self.update_audio_threads(detection_update, current_time)
                
                # Fixed sleep time
                time.sleep(1.5)
                
            except Exception:
                time.sleep(3.0)
    
    def update_audio_threads(self, detected_objects: Dict, current_time: float):
        """Update audio threads based on detected objects"""
        if not self.should_monitor():
            self.cleanup_all_audio_threads()
            return
        
        # Stop threads for objects that are no longer detected or too close
        objects_to_remove = []
        for obj_name, audio_thread in list(self.active_audio_threads.items()):
            if obj_name not in detected_objects:
                audio_thread.stop()
                objects_to_remove.append(obj_name)
            else:
                obj_data = detected_objects[obj_name]
                if not self.should_play_audio_for_distance(obj_data['distance']):
                    audio_thread.stop()
                    objects_to_remove.append(obj_name)
        
        for obj_name in objects_to_remove:
            if obj_name in self.active_audio_threads:
                del self.active_audio_threads[obj_name]
        
        for obj_name, obj_data in detected_objects.items():
            distance = obj_data['distance']
            coords = obj_data['coords']
            
            if self.should_play_audio_for_distance(distance):
                if obj_name in self.active_audio_threads:
                    self.active_audio_threads[obj_name].update_position(coords, distance)
                else:
                    audio_instance = self.get_audio_instance(obj_name)
                    if audio_instance:
                        ping_interval = self.get_object_ping_interval(obj_name)
                        audio_thread = GameObjectAudioThread(obj_name, audio_instance, ping_interval)
                        audio_thread.start(coords, distance)
                        self.active_audio_threads[obj_name] = audio_thread
    
    def cleanup_all_audio_threads(self):
        """Stop and clean up all active audio threads"""
        for audio_thread in list(self.active_audio_threads.values()):
            audio_thread.stop()
        self.active_audio_threads.clear()
    
    def start_monitoring(self):
        """Start the game object monitoring"""
        if not self.running:
            self.running = True
            self.stop_event.clear()
            
            self.detection_thread = threading.Thread(target=self.detection_loop, daemon=True)
            self.detection_thread.start()
    
    def stop_monitoring(self):
        """Stop the game object monitoring"""
        self.stop_event.set()
        self.running = False
        
        self.cleanup_all_audio_threads()
        
        if self.detection_thread:
            self.detection_thread.join(timeout=3.0)
        
        if self.default_audio:
            try:
                self.default_audio.stop()
            except Exception:
                pass
        
        for audio_instance in self.audio_instances.values():
            try:
                audio_instance.stop()
            except Exception:
                pass

gameobject_monitor = GameObjectMonitor()