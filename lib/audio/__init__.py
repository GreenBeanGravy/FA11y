"""
FA11y Audio Engine package.

Provides a centralized audio engine with Steam Audio HRTF support
and Windows IAudioClient3 low-latency backend.
"""

import threading
import logging

logger = logging.getLogger(__name__)

_engine = None
_lock = threading.Lock()


def get_engine():
    """Get or create the FA11y audio engine singleton."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                from lib.audio.engine import FA11yAudioEngine
                _engine = FA11yAudioEngine()
                if not _engine.initialize(use_low_latency=True):
                    logger.error("Audio engine failed to initialize")
    return _engine


def shutdown_engine():
    """Shutdown the audio engine and release all resources."""
    global _engine
    with _lock:
        if _engine is not None:
            try:
                _engine.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down audio engine: {e}")
            _engine = None
