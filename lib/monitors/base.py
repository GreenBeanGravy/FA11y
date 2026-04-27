"""Base class for background monitors with lifecycle management.

Subclasses implement ``_monitor_loop``; use ``self.stop_event.wait(t)``
inside it so ``stop_monitoring()`` can break out cleanly.
"""
from __future__ import annotations

import threading
from typing import Optional


class BaseMonitor:
    """Lifecycle-managed background monitor.

    API:
        ``start_monitoring()``  — idempotent; no-op if already running
        ``stop_monitoring()``   — sets the stop event, joins with timeout
        ``self.running``        — True between start and stop
        ``self.stop_event``     — ``threading.Event`` the loop should observe
        ``self.thread``         — the current daemon thread (or ``None``)

    Subclass contract:
        override ``_monitor_loop`` (the function run on the daemon thread).
    """

    #: Timeout passed to ``thread.join()`` inside ``stop_monitoring``.
    _JOIN_TIMEOUT: float = 2.0

    #: Optional thread name for debuggers / ``threading.enumerate()``.
    _THREAD_NAME: Optional[str] = None

    def __init__(self) -> None:
        self.running: bool = False
        self.stop_event: threading.Event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_monitoring(self) -> None:
        """Start the monitor thread. Idempotent. No-op while wizard is open."""
        if self.running:
            return
        # No monitors while the first-run wizard is up.
        try:
            from lib.app import state
            if state.wizard_open.is_set():
                return
        except Exception:
            pass
        self.running = True
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run_safely,
            daemon=True,
            name=self._THREAD_NAME or type(self).__name__,
        )
        self.thread.start()

    def stop_monitoring(self) -> None:
        """Signal the loop to stop and wait briefly for the thread to exit."""
        self.stop_event.set()
        self.running = False
        t = self.thread
        if t is not None and t.is_alive():
            t.join(timeout=self._JOIN_TIMEOUT)
        self.thread = None

    # ------------------------------------------------------------------
    # Subclass hook
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        """Override in subclasses. Must honour ``self.stop_event``."""
        raise NotImplementedError(
            f"{type(self).__name__} must implement _monitor_loop()"
        )

    @staticmethod
    def wizard_paused() -> bool:
        """True while the first-run wizard owns the screen.

        Subclass loops should check this at the top of each iteration
        and sleep instead of doing work — keeps TTS / screen capture
        from firing while the user is configuring FA11y.
        """
        try:
            from lib.app import state
            return state.wizard_open.is_set()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal: swallow uncaught exceptions so a buggy monitor doesn't
    # silently kill the whole thread and leave ``self.running`` stale.
    # ------------------------------------------------------------------

    def _run_safely(self) -> None:
        try:
            self._monitor_loop()
        except Exception:
            import logging
            logging.getLogger(type(self).__module__).exception(
                "%s._monitor_loop crashed", type(self).__name__,
            )
        finally:
            # Make sure ``running`` reflects reality even on an unhandled
            # crash — downstream callers poll this.
            self.running = False
