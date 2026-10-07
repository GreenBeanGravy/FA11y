"""Epic Connect: the push channel that delivers chat messages as they are sent.

A websocket to connect.epicgames.dev speaking STOMP, authorised with the EAS token. After
CONNECT, subscribing to "{deployment}/account/{me}" delivers new DMs and party chat messages
within a second, along with party and conversation changes. Party invites and join requests do
not arrive here; the social manager polls for those.

The server wants a heartbeat (a bare newline) at least every 45 seconds, or it closes the
connection with "Inactive timeout".
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from typing import Callable, Optional

from lib.utilities.epic_eos import DEPLOYMENT_ID, EosError, EosSession

logger = logging.getLogger(__name__)

CONNECT_URL = "wss://connect.epicgames.dev"
HEARTBEAT_SECONDS = 30
RECONNECT_DELAYS = (5, 15, 30, 60, 120)


def parse_frame(frame: str):
    """(command, headers, body) of one STOMP frame."""
    frame = frame.replace("\0", "")
    head, _, body = frame.partition("\n\n")
    lines = head.split("\n")
    headers = {}
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if sep:
            headers[name] = value
    return lines[0].strip(), headers, body


class PushListener:
    """Keeps the push connection open on a background thread and passes each event to on_event.

    on_event receives the decoded JSON event: {"type": ..., "payload": {...}, ...}. Chat
    messages carry payload.conversation and payload.message.
    """

    def __init__(self, session: EosSession, on_event: Callable[[dict], None]):
        self.session = session
        self.on_event = on_event
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._ws = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="EpicPush", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _run(self) -> None:
        failures = 0
        while self._running:
            started = time.time()
            try:
                self._session_once()
            except EosError as e:
                logger.debug(f"Push channel not connected: {e}")
            except Exception as e:
                logger.info(f"Push channel dropped: {e}")
            self._ws = None
            if not self._running:
                break
            # A connection that lasted a while starts the backoff again.
            failures = 0 if time.time() - started > 300 else failures + 1
            delay = RECONNECT_DELAYS[min(failures, len(RECONNECT_DELAYS) - 1)]
            for _ in range(delay * 2):
                if not self._running:
                    return
                time.sleep(0.5)

    def _session_once(self) -> None:
        import websocket
        me = self.session.account_id
        try:
            ws = websocket.create_connection(
                CONNECT_URL,
                header={"Authorization": f"Bearer {self.session.token()}", "Epic-Connect-Protocol": "stomp",
                        "Epic-Connect-Device-Id": uuid.uuid4().hex},
                timeout=10)
        except websocket.WebSocketBadStatusException as e:
            if e.status_code == 401:
                self.session.forget_token()
            raise
        self._ws = ws
        try:
            ws.send("CONNECT\naccept-version:1.0,1.1,1.2\nheart-beat:35000,0\n\n\0")
            ws.settimeout(5)
            last_beat = time.time()
            subscribed = False
            while self._running:
                try:
                    frame = ws.recv()
                except websocket.WebSocketTimeoutException:
                    frame = ""
                if time.time() - last_beat > HEARTBEAT_SECONDS:
                    ws.send("\n")
                    last_beat = time.time()
                if isinstance(frame, bytes):
                    frame = frame.decode("utf-8", "replace")
                if not frame.strip():
                    if frame == "" and not ws.connected:
                        return
                    continue
                command, _headers, body = parse_frame(frame)
                if command == "CONNECTED" and not subscribed:
                    ws.send(f"SUBSCRIBE\nid:sub-0\ndestination:{DEPLOYMENT_ID}/account/{me}\n\n\0")
                    subscribed = True
                    logger.info("Push channel connected")
                elif command == "MESSAGE":
                    try:
                        event = json.loads(body)
                    except ValueError:
                        continue
                    try:
                        self.on_event(event)
                    except Exception:
                        logger.exception("Push event handler failed")
                elif command == "ERROR":
                    logger.info(f"Push channel error: {body[:200]}")
                    return
        finally:
            try:
                ws.close()
            except Exception:
                pass
