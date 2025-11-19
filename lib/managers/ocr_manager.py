"""
Centralized OCR management for FA11y
Provides a single EasyOCR instance shared across all modules to reduce memory usage
"""
import threading
import logging
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)

class OCRManager:
    """Singleton OCR manager to handle all OCR operations"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(OCRManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize OCR manager if not already initialized"""
        if hasattr(self, '_initialized'):
            return
            
        self._initialized = True
        self.reader = None
        self.available = False
        self.ready_event = threading.Event()
        self.access_lock = threading.Lock()
        self.initialization_lock = threading.Lock()
        
        # Start initialization in background
        self._initialize_in_background()
    
    def _initialize_in_background(self):
        """Initialize EasyOCR in a background thread"""
        def _load_ocr():
            import warnings
            
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore')
                try:
                    import easyocr
                    with self.initialization_lock:
                        # Create readers for different purposes
                        self.reader = easyocr.Reader(['en'])
                        self.number_reader = easyocr.Reader(['en'], recognizer='number')
                        self.available = True
                        logger.info("EasyOCR successfully initialized")
                except ImportError as e:
                    logger.error(f"EasyOCR not available: {e}")
                    self.available = False
                except Exception as e:
                    logger.error(f"EasyOCR initialization failed: {e}")
                    self.available = False
                finally:
                    self.ready_event.set()
        
        init_thread = threading.Thread(target=_load_ocr, daemon=True)
        init_thread.start()
    
    def is_ready(self, timeout: float = 0.1) -> bool:
        """Check if OCR is ready to use
        
        Args:
            timeout: Maximum time to wait for initialization
            
        Returns:
            bool: True if OCR is ready, False otherwise
        """
        return self.ready_event.wait(timeout=timeout) and self.available
    
    def read_text(self, image, **kwargs) -> List[Tuple]:
        """Read text from image using general text reader
        
        Args:
            image: Image to process
            **kwargs: Additional arguments for EasyOCR
            
        Returns:
            list: OCR results or empty list if failed
        """
        if not self.is_ready():
            return []
        
        try:
            with self.access_lock:
                if self.reader is None:
                    return []
                return self.reader.readtext(image, **kwargs)
        except Exception as e:
            logger.error(f"Error in OCR text reading: {e}")
            return []
    
    def read_numbers(self, image, **kwargs) -> List[Tuple]:
        """Read numbers from image using number-optimized reader
        
        Args:
            image: Image to process  
            **kwargs: Additional arguments for EasyOCR
            
        Returns:
            list: OCR results or empty list if failed
        """
        if not self.is_ready():
            return []
        
        try:
            with self.access_lock:
                if not hasattr(self, 'number_reader') or self.number_reader is None:
                    # Fallback to regular reader
                    if self.reader is None:
                        return []
                    return self.reader.readtext(image, **kwargs)
                return self.number_reader.readtext(image, **kwargs)
        except Exception as e:
            logger.error(f"Error in OCR number reading: {e}")
            return []
    
    def cleanup(self):
        """Clean up OCR resources"""
        with self.access_lock:
            self.reader = None
            if hasattr(self, 'number_reader'):
                self.number_reader = None
            self.available = False
            logger.info("OCR resources cleaned up")

# Global OCR manager instance
ocr_manager = OCRManager()

def get_ocr_manager() -> OCRManager:
    """Get the global OCR manager instance
    
    Returns:
        OCRManager: The singleton OCR manager
    """
    return ocr_manager