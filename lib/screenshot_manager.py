"""
Centralized screenshot management for FA11y
Provides efficient, thread-safe screenshot operations with proper resource management
"""
import threading
import time
import logging
from typing import Dict, Tuple, Optional, Union
import numpy as np
from mss import mss
import cv2

logger = logging.getLogger(__name__)

class ScreenshotManager:
    """Singleton screenshot manager for centralized screen capture operations"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ScreenshotManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize screenshot manager if not already initialized"""
        if hasattr(self, '_initialized'):
            return
            
        self._initialized = True
        
        # Thread-local storage for MSS instances
        self.thread_local = threading.local()
        self.access_lock = threading.Lock()
        
        # Screenshot cache for optimization (optional)
        self.enable_caching = False
        self.cache = {}
        self.cache_lock = threading.Lock()
        self.cache_ttl = 0.1  # Cache screenshots for 100ms max
        
        # Performance monitoring
        self.stats = {
            'screenshots_taken': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'errors': 0
        }
        
        logger.info("Screenshot manager initialized")
    
    def get_mss_instance(self):
        """Get or create thread-local MSS instance
        
        Returns:
            mss.mss: MSS instance for current thread or None if failed
        """
        try:
            if not hasattr(self.thread_local, 'mss'):
                self.thread_local.mss = mss()
                logger.debug(f"Created new MSS instance for thread {threading.current_thread().ident}")
            return self.thread_local.mss
        except Exception as e:
            logger.error(f"Error creating MSS instance: {e}")
            self.stats['errors'] += 1
            return None
    
    def cleanup_thread_resources(self):
        """Clean up MSS instance for current thread"""
        try:
            if hasattr(self.thread_local, 'mss'):
                self.thread_local.mss.close()
                delattr(self.thread_local, 'mss')
                logger.debug(f"Cleaned up MSS instance for thread {threading.current_thread().ident}")
        except Exception as e:
            logger.error(f"Error cleaning up MSS instance: {e}")
    
    def capture_region(self, region: Dict[str, int], convert_format: str = 'bgr') -> Optional[np.ndarray]:
        """Capture a specific screen region
        
        Args:
            region: Dictionary with 'left', 'top', 'width', 'height' keys
            convert_format: Output format ('bgr', 'rgb', 'gray', 'raw')
            
        Returns:
            np.ndarray: Screenshot as numpy array or None if failed
        """
        # Generate cache key if caching is enabled
        cache_key = None
        if self.enable_caching:
            cache_key = (
                region['left'], region['top'], 
                region['width'], region['height'], 
                convert_format, time.time() // self.cache_ttl
            )
            
            # Check cache first
            with self.cache_lock:
                if cache_key in self.cache:
                    self.stats['cache_hits'] += 1
                    return self.cache[cache_key].copy()
                self.stats['cache_misses'] += 1
        
        try:
            mss_instance = self.get_mss_instance()
            if mss_instance is None:
                return None
            
            # Capture screenshot
            screenshot = np.array(mss_instance.grab(region))
            self.stats['screenshots_taken'] += 1
            
            # Convert format as requested
            result = self._convert_format(screenshot, convert_format)
            
            # Cache result if caching is enabled
            if self.enable_caching and cache_key is not None:
                with self.cache_lock:
                    self.cache[cache_key] = result.copy()
                    
                    # Clean old cache entries (simple cleanup)
                    if len(self.cache) > 50:  # Limit cache size
                        oldest_key = min(self.cache.keys(), key=lambda k: k[-1])
                        del self.cache[oldest_key]
            
            return result
            
        except Exception as e:
            logger.error(f"Error capturing region {region}: {e}")
            self.stats['errors'] += 1
            return None
    
    def capture_full_screen(self, convert_format: str = 'bgr') -> Optional[np.ndarray]:
        """Capture full screen
        
        Args:
            convert_format: Output format ('bgr', 'rgb', 'gray', 'raw')
            
        Returns:
            np.ndarray: Screenshot as numpy array or None if failed
        """
        try:
            mss_instance = self.get_mss_instance()
            if mss_instance is None:
                return None
            
            # Get primary monitor
            monitor = mss_instance.monitors[1]  # Monitor 1 is usually primary
            screenshot = np.array(mss_instance.grab(monitor))
            self.stats['screenshots_taken'] += 1
            
            return self._convert_format(screenshot, convert_format)
            
        except Exception as e:
            logger.error(f"Error capturing full screen: {e}")
            self.stats['errors'] += 1
            return None
    
    def capture_coordinates(self, x: int, y: int, width: int, height: int, 
                          convert_format: str = 'bgr') -> Optional[np.ndarray]:
        """Capture screen region by coordinates
        
        Args:
            x: Left coordinate
            y: Top coordinate  
            width: Width of capture area
            height: Height of capture area
            convert_format: Output format ('bgr', 'rgb', 'gray', 'raw')
            
        Returns:
            np.ndarray: Screenshot as numpy array or None if failed
        """
        region = {
            'left': x,
            'top': y, 
            'width': width,
            'height': height
        }
        return self.capture_region(region, convert_format)
    
    def _convert_format(self, screenshot: np.ndarray, format_type: str) -> np.ndarray:
        """Convert screenshot to requested format
        
        Args:
            screenshot: Raw BGRA screenshot from MSS
            format_type: Target format ('bgr', 'rgb', 'gray', 'raw')
            
        Returns:
            np.ndarray: Converted screenshot
        """
        if format_type == 'raw':
            return screenshot
        
        # Convert from BGRA to target format
        if screenshot.shape[2] == 4:  # BGRA
            if format_type == 'bgr':
                return cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
            elif format_type == 'rgb':
                return cv2.cvtColor(screenshot, cv2.COLOR_BGRA2RGB)
            elif format_type == 'gray':
                return cv2.cvtColor(screenshot, cv2.COLOR_BGRA2GRAY)
        else:  # Assume BGR
            if format_type == 'bgr':
                return screenshot
            elif format_type == 'rgb':
                return cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB)
            elif format_type == 'gray':
                return cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        
        return screenshot
    
    def enable_screenshot_caching(self, enabled: bool = True, ttl: float = 0.1):
        """Enable or disable screenshot caching
        
        Args:
            enabled: Whether to enable caching
            ttl: Time-to-live for cache entries in seconds
        """
        self.enable_caching = enabled
        self.cache_ttl = ttl
        
        if not enabled:
            with self.cache_lock:
                self.cache.clear()
        
        logger.info(f"Screenshot caching {'enabled' if enabled else 'disabled'}")
    
    def get_stats(self) -> Dict[str, int]:
        """Get performance statistics
        
        Returns:
            dict: Performance statistics
        """
        return self.stats.copy()
    
    def reset_stats(self):
        """Reset performance statistics"""
        self.stats = {
            'screenshots_taken': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'errors': 0
        }
    
    def cleanup_all_resources(self):
        """Clean up all resources (call on application shutdown)"""
        # Clear cache
        with self.cache_lock:
            self.cache.clear()
        
        # Clean up current thread's MSS instance
        self.cleanup_thread_resources()
        
        logger.info("Screenshot manager resources cleaned up")

# Global screenshot manager instance
screenshot_manager = ScreenshotManager()

def get_screenshot_manager() -> ScreenshotManager:
    """Get the global screenshot manager instance
    
    Returns:
        ScreenshotManager: The singleton screenshot manager
    """
    return screenshot_manager

# Convenience functions for common operations
def capture_region(region: Dict[str, int], convert_format: str = 'bgr') -> Optional[np.ndarray]:
    """Convenience function to capture a screen region
    
    Args:
        region: Dictionary with 'left', 'top', 'width', 'height' keys
        convert_format: Output format ('bgr', 'rgb', 'gray', 'raw')
        
    Returns:
        np.ndarray: Screenshot as numpy array or None if failed
    """
    return screenshot_manager.capture_region(region, convert_format)

def capture_coordinates(x: int, y: int, width: int, height: int, 
                       convert_format: str = 'bgr') -> Optional[np.ndarray]:
    """Convenience function to capture screen region by coordinates
    
    Args:
        x: Left coordinate
        y: Top coordinate
        width: Width of capture area
        height: Height of capture area
        convert_format: Output format ('bgr', 'rgb', 'gray', 'raw')
        
    Returns:
        np.ndarray: Screenshot as numpy array or None if failed
    """
    return screenshot_manager.capture_coordinates(x, y, width, height, convert_format)

def capture_full_screen(convert_format: str = 'bgr') -> Optional[np.ndarray]:
    """Convenience function to capture full screen
    
    Args:
        convert_format: Output format ('bgr', 'rgb', 'gray', 'raw')
        
    Returns:
        np.ndarray: Screenshot as numpy array or None if failed
    """
    return screenshot_manager.capture_full_screen(convert_format)