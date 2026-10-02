"""
Centralized OCR management for FA11y
Provides a single RapidOCR instance shared across all modules to reduce memory usage.

RapidOCR runs PaddleOCR models on ONNX Runtime; the models ship inside the
rapidocr package, so nothing is downloaded at runtime. Results keep the
EasyOCR-style shape callers already use: (box, text, confidence) tuples,
or plain strings with detail=0.
"""
import threading
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Cap the detector's input size. Its default upscales small HUD crops to a
# 736 px short side, which made each call roughly ten times slower.
_ENGINE_PARAMS = {
    "Global.log_level": "critical",
    "Det.limit_type": "max",
    "Det.limit_side_len": 960,
}


def _to_bgr(image):
    """RapidOCR expects 3-channel images; FA11y often passes thresholded grayscale."""
    import cv2
    if getattr(image, "ndim", 3) == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image


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
        self.engine = None
        self.available = False
        self.ready_event = threading.Event()
        self.access_lock = threading.Lock()

        # Start initialization in background
        self._initialize_in_background()

    def _initialize_in_background(self):
        """Load the OCR models in a background thread"""
        def _load_ocr():
            try:
                from rapidocr import RapidOCR
                self.engine = RapidOCR(params=_ENGINE_PARAMS)
                self.available = True
                logger.info("RapidOCR successfully initialized")
            except ImportError as e:
                logger.error(f"RapidOCR not available: {e}")
                self.available = False
            except Exception as e:
                logger.error(f"RapidOCR initialization failed: {e}")
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

    def read_text(self, image, detail: int = 1, **_unused) -> List:
        """Find and read every line of text in an image

        Args:
            image: Image to process (BGR, BGRA or grayscale numpy array)
            detail: 1 for (box, text, confidence) tuples, 0 for text only
            **_unused: EasyOCR tuning arguments older callers pass; ignored

        Returns:
            list: Results top to bottom, or an empty list if OCR failed
        """
        if not self.is_ready():
            return []

        try:
            with self.access_lock:
                if self.engine is None:
                    return []
                # Pass every stage flag: RapidOCR keeps per-call flags for
                # later calls, so read_numbers' recognition-only mode would
                # otherwise carry over.
                out = self.engine(_to_bgr(image), use_det=True, use_cls=True, use_rec=True)
            if not out.txts:
                return []
            results = [(box.tolist(), text, float(score))
                       for box, text, score in zip(out.boxes, out.txts, out.scores)]
            return [r[1] for r in results] if detail == 0 else results
        except Exception as e:
            logger.error(f"Error in OCR text reading: {e}")
            return []

    def read_numbers(self, image, allowlist: str = '0123456789', detail: int = 1,
                     **_unused) -> List:
        """Read a single line of digits, such as an ammo or material count

        Skips text detection and runs recognition on the whole image, which
        is several times faster for the small, pre-cropped regions FA11y
        passes here. Characters outside allowlist are dropped.

        Args:
            image: Image of one line of text
            allowlist: Characters to keep
            detail: 1 for (box, text, confidence) tuples, 0 for text only
            **_unused: EasyOCR tuning arguments older callers pass; ignored

        Returns:
            list: At most one result, or an empty list if nothing was read
        """
        if not self.is_ready():
            return []

        try:
            with self.access_lock:
                if self.engine is None:
                    return []
                out = self.engine(_to_bgr(image), use_det=False, use_cls=False, use_rec=True)
            raw = "".join(out.txts or ())
            text = "".join(c for c in raw if c in allowlist)
            if not text:
                return []
            height, width = image.shape[:2]
            box = [[0, 0], [width, 0], [width, height], [0, height]]
            score = float(out.scores[0]) if out.scores else 0.0
            return [text] if detail == 0 else [(box, text, score)]
        except Exception as e:
            logger.error(f"Error in OCR number reading: {e}")
            return []

    def cleanup(self):
        """Clean up OCR resources"""
        with self.access_lock:
            self.engine = None
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
