"""
Base class for background monitors.

Every FA11y monitor (bloom, material, resource, storm, match events, STW
alerts, …) needs the same lifecycle plumbing: a running flag, a stop event,
a daemon thread, idempotent start/stop, and a timed join on shutdown.
Before this class, each monitor reinvented that dance — and several had
subtle variants (missing stop-events, underscored field names, no join
timeout, race between the flag and the event).

Subclasses implement ``_monitor_loop`` — the function that runs on the
daemon thread. Inside the loop they should call ``self.stop_event.wait(t)``
or check ``self.stop_event.is_set()`` instead of sleeping so that
``stop_monitoring()`` actually breaks them out.
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
        """Start the monitor thread. Idempotent."""
        if self.running:
            return
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
