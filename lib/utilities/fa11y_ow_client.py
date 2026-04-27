"""
FA11y-OW companion client.

Subscribes to the FA11y-OW Electron app's local HTTP API at 127.0.0.1:6767.
That app uses Overwolf's Game Events Provider (GEP) to mirror Fortnite state
and exposes it both as REST endpoints and as a Server-Sent Events stream.

This module keeps a live cached state snapshot in-memory by tailing the SSE
stream on a daemon thread, and lets consumers either pull a value
synchronously or register a callback for state changes.

When FA11y-OW is not running, is_connected stays False and get(...) returns
the supplied default. Consumers use that signal to fall back to their
existing visual detection path.
"""

import json
import logging
import threading
from typing import Any, Callable, Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "http://127.0.0.1:6767/api"
SSE_URL = f"{BASE_URL}/subscribe"

# Connect timeout for the SSE handshake. Read timeout is intentionally None:
# once we're streaming, an idle period just means the game state hasn't
# changed and the server's 30s heartbeat will tickle the socket.
SSE_CONNECT_TIMEOUT = 2.0

# Backoff between reconnect attempts when the companion isn't reachable.
# Keep this short enough that the user doesn't have to wait long after
# launching FA11y-OW for FA11y to pick it up.
SSE_RECONNECT_DELAY = 3.0


class FA11yOWClient:
    """Live client for the FA11y-OW HTTP API.

    Single instance per process — use get_client() to obtain it. Starts a
    background thread on first start() that maintains the SSE subscription
    and reconnects on its own if the companion is restarted.
    """

    def __init__(self):
        self._state: dict = {}
        self._lock = threading.RLock()
        self._connected = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # changed_key -> [callback(changed_key, full_state), ...]
        self._listeners: dict = {}

    def start(self):
        """Start the SSE subscriber thread. Idempotent."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run, daemon=True, name='FA11y-OW-Client'
            )
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        thread = self._thread
        if thread:
            thread.join(timeout=2.0)

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_state(self) -> Optional[dict]:
        """Shallow copy of the cached state, or None if disconnected."""
        with self._lock:
            if not self._connected:
                return None
            return dict(self._state)

    def get(self, *path: str, default: Any = None) -> Any:
        """Read a value from cached state by key path.

        Returns default if disconnected or any path component is missing.

            client.get('health')          # 100
            client.get('location', 'x')   # nested
            client.get('inventory')       # the whole inventory dict
        """
        with self._lock:
            if not self._connected:
                return default
            value: Any = self._state
            for key in path:
                if not isinstance(value, dict) or key not in value:
                    return default
                value = value[key]
            return value

    def on_event(self, changed_key: str, callback: Callable[[str, dict], None]):
        """Register a callback fired when SSE reports a state change.

        changed_key is the GEP key name ('phase', 'health', 'kill', 'death',
        'matchStart', 'matchEnd', 'selected_slot', 'item_X', ...). Use '*' to
        receive every change.

        callback signature: (changed_key, state_snapshot) -> None
        Callbacks run on the SSE thread; keep them short and don't block.
        """
        with self._lock:
            self._listeners.setdefault(changed_key, []).append(callback)

    # --- Internal -------------------------------------------------------

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._stream_session()
            except Exception as e:
                logger.debug(f"FA11y-OW SSE session error: {e}")
            self._set_connected(False)
            if self._stop_event.wait(SSE_RECONNECT_DELAY):
                return

    def _stream_session(self):
        """One SSE connection lifetime. Returns on disconnect or stop."""
        try:
            response = requests.get(
                SSE_URL,
                stream=True,
                timeout=(SSE_CONNECT_TIMEOUT, None),
                headers={'Accept': 'text/event-stream'},
            )
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            # Expected when companion isn't running — caller will back off.
            return

        with response:
            if response.status_code != 200:
                return
            self._set_connected(True)
            for raw in response.iter_lines(decode_unicode=True):
                if self._stop_event.is_set():
                    return
                if not raw or not raw.startswith('data: '):
                    continue
                payload = raw[6:]
                try:
                    msg = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                self._handle_message(msg)

    def _handle_message(self, msg: dict):
        msg_type = msg.get('type')
        if msg_type not in ('connected', 'stateChange'):
            return
        data = msg.get('data')
        if not isinstance(data, dict):
            return
        with self._lock:
            self._state = data
        self._fire_listeners(msg.get('changedKey'), data)

    def _fire_listeners(self, changed_key: Optional[str], state: dict):
        with self._lock:
            specific = list(self._listeners.get(changed_key, [])) if changed_key else []
            wildcard = list(self._listeners.get('*', []))
        for cb in specific + wildcard:
            try:
                cb(changed_key or '', state)
            except Exception as e:
                logger.debug(f"FA11y-OW listener error: {e}")

    def _set_connected(self, value: bool):
        with self._lock:
            was = self._connected
            self._connected = value
        if was and not value:
            logger.info("FA11y-OW disconnected")
        elif not was and value:
            logger.info("FA11y-OW connected")


_client: Optional[FA11yOWClient] = None
_client_lock = threading.Lock()


def get_client() -> FA11yOWClient:
    """Return the process-wide singleton client, starting it on first call."""
    global _client
    with _client_lock:
        if _client is None:
            _client = FA11yOWClient()
            _client.start()
        return _client


def is_available() -> bool:
    """True iff the companion app is currently connected."""
    return get_client().is_connected
