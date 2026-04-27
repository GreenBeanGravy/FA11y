"""FA11y-OW companion-service SSE client.

Streams ``/api/subscribe`` from the local FA11y-OW helper, maintains a live
state cache, and dispatches change callbacks to subscribers. When the helper
isn't running, the client sits idle and quietly retries — every consumer
registered through ``add_listener`` simply doesn't fire.

Design notes:
    - One background daemon thread shared by all consumers (singleton).
    - Listeners are dispatched on the SSE thread; they must be cheap and not
      block. Anything heavy (TTS, screen capture) should hop off via wx /
      ``threading.Thread`` if the existing audio code path doesn't already
      tolerate being called from a worker thread.
    - The SSE thread does not raise into callers' code; listener exceptions
      get logged and swallowed so one buggy listener can't sever the stream.

Public surface:
    ``client.start()`` / ``client.stop()`` — lifecycle
    ``client.is_running()``                — True between start/stop
    ``client.is_connected()``              — True only while the SSE socket
                                              is actively delivering events
    ``client.get_state()``                 — last known full state dict
                                              (empty {} until first event)
    ``client.add_listener(key_or_type, cb)``
    ``client.remove_listener(key_or_type, cb)``

Event types passed to listeners:
    ``"stateChange"``   — payload: (changedKey, previousValue, newState)
    ``"killEvent"``     — payload: kill dict from FA11y-OW
    ``"teammateEvent"`` — payload: teammate-event dict
    ``"itemEquipped"``  — payload: hotbar-item dict (or None when slot
                          becomes empty)
    ``"itemPickup"``    — payload: hotbar-item dict
    ``<changedKey>``    — fires alongside ``stateChange`` for the specific
                          key, payload (previousValue, newState)
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


_API_BASE = "http://127.0.0.1:6767"
_SUBSCRIBE_URL = _API_BASE + "/api/subscribe"

# SSE backoff: first retry quickly so we feel alive when the helper is
# starting up; cap at 10s so we don't hammer when it's just not running.
_INITIAL_BACKOFF = 0.5
_MAX_BACKOFF = 10.0


ListenerCallable = Callable[..., None]


class _Fa11yOwClient:
    """Thread-safe singleton. Don't construct directly — use ``client``."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._listeners: Dict[str, List[ListenerCallable]] = {}
        self._state: Dict[str, Any] = {}
        self._connected: bool = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Reuse a single Session to amortize connection setup; fresh sessions
        # are created on reconnect when the previous one is poisoned.
        self._session: Optional[requests.Session] = None

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="Fa11yOwSseClient",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            session = self._session
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=1.0)
        with self._lock:
            self._thread = None
            self._connected = False

    def is_running(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive()

    def is_connected(self) -> bool:
        return self._connected

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    # -- listeners --------------------------------------------------------

    def add_listener(self, event_type: str, callback: ListenerCallable) -> None:
        with self._lock:
            self._listeners.setdefault(event_type, []).append(callback)

    def remove_listener(self, event_type: str, callback: ListenerCallable) -> None:
        with self._lock:
            lst = self._listeners.get(event_type)
            if not lst:
                return
            try:
                lst.remove(callback)
            except ValueError:
                pass

    # -- SSE thread -------------------------------------------------------

    def _run(self) -> None:
        backoff = _INITIAL_BACKOFF
        while not self._stop_event.is_set():
            try:
                self._stream_once()
                # Clean disconnect (server closed); reset backoff.
                backoff = _INITIAL_BACKOFF
            except (requests.RequestException, ValueError) as e:
                # ConnectionRefused / timeout / chunked-decode / JSON errors —
                # totally expected when the helper isn't up. Stay quiet on
                # the common case (refused) and only log the noisy ones.
                if not isinstance(e, requests.ConnectionError):
                    logger.debug("FA11y-OW SSE error: %s", e)
            except Exception:
                logger.exception("FA11y-OW SSE crashed")

            self._connected = False
            if self._stop_event.wait(backoff):
                return
            backoff = min(backoff * 2, _MAX_BACKOFF)

    def _stream_once(self) -> None:
        with self._lock:
            if self._session is None:
                self._session = requests.Session()
            session = self._session

        # Short connect timeout so we fail fast when the helper isn't there;
        # no read timeout (we're a long-lived consumer).
        with session.get(
            _SUBSCRIBE_URL,
            stream=True,
            timeout=(2.0, None),
            headers={"Accept": "text/event-stream"},
        ) as resp:
            resp.raise_for_status()
            self._connected = True
            buf: List[str] = []
            for raw_line in resp.iter_lines(decode_unicode=True):
                if self._stop_event.is_set():
                    return
                if raw_line is None:
                    continue
                if raw_line == "":
                    # Blank line terminates an SSE event.
                    if buf:
                        self._dispatch_buffer(buf)
                        buf = []
                    continue
                if raw_line.startswith(":"):
                    # Comment / heartbeat
                    continue
                buf.append(raw_line)

            if buf:
                self._dispatch_buffer(buf)

    def _dispatch_buffer(self, lines: List[str]) -> None:
        # Take only the data: lines, concatenate per the SSE spec.
        data_lines = [ln[5:].lstrip() if ln.startswith("data:") else None for ln in lines]
        data_lines = [ln for ln in data_lines if ln is not None]
        if not data_lines:
            return
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            logger.debug("FA11y-OW: dropped malformed SSE payload")
            return
        try:
            self._handle_payload(payload)
        except Exception:
            logger.exception("FA11y-OW: listener dispatch failed")

    def _handle_payload(self, payload: Dict[str, Any]) -> None:
        msg_type = payload.get("type")
        # The first message after connect carries the full snapshot.
        if msg_type == "connected":
            with self._lock:
                self._state = dict(payload.get("data") or {})
            return

        if msg_type == "stateChange":
            new_state = payload.get("data") or {}
            changed_key = payload.get("changedKey")
            previous_value = payload.get("previousValue")
            with self._lock:
                self._state = dict(new_state)
            self._fire("stateChange", changed_key, previous_value, new_state)
            if changed_key:
                self._fire(changed_key, previous_value, new_state)
            return

        if msg_type == "killEvent":
            self._fire("killEvent", payload.get("data"))
            return
        if msg_type == "teammateEvent":
            self._fire("teammateEvent", payload.get("data"))
            return
        if msg_type == "itemEquipped":
            self._fire("itemEquipped", payload.get("data"))
            return
        if msg_type == "itemPickup":
            self._fire("itemPickup", payload.get("data"))
            return

    def _fire(self, event_type: str, *args: Any) -> None:
        with self._lock:
            listeners = list(self._listeners.get(event_type, ()))
        for cb in listeners:
            try:
                cb(*args)
            except Exception:
                logger.exception("FA11y-OW listener for %r raised", event_type)


# Module-level singleton.
client = _Fa11yOwClient()
