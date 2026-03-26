"""
Mouse Passthrough Module for FA11y
Captures mouse input from a physical mouse and relays it through FakerInput driver.
"""

from lib.mouse_passthrough.service import MousePassthroughService

_instance = None

def get_mouse_passthrough() -> MousePassthroughService:
    """Get the singleton MousePassthroughService instance."""
    global _instance
    if _instance is None:
        _instance = MousePassthroughService()
    return _instance
