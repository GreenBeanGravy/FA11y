"""Talks to FA11y.UI.exe, the separate window program, over JSON Lines.

Each line on the UI's stdin and stdout is one UTF-8 JSON object:

    {"type": "request",  "id": 7, "method": "home.status", "params": {}}
    {"type": "response", "id": 7, "ok": true, "result": {...}}
    {"type": "response", "id": 7, "ok": false, "error": "message"}
    {"type": "event",    "name": "ui.summon", "data": {...}}

Both sides send requests and events; request ids are per sender. Requests
from the UI run on a small thread pool through a registry of handlers, so
a slow one never blocks another. Events from the UI go to subscribers one
at a time, in order, on a single worker thread.
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import queue
import subprocess
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Deque, Dict, List, Optional, Sequence, Union

logger = logging.getLogger(__name__)

SW_SHOWNORMAL = 1
MAX_RESTARTS = 3
RESTART_WINDOW_SECONDS = 60.0
WORKERS = 8

Handler = Callable[[dict], Any]


class BridgeError(Exception):
    """A request to the UI failed, timed out, or the UI isn't running."""


class HandlerRegistry:
    """Maps request method names to the functions that answer them."""

    def __init__(self) -> None:
        self.handlers: Dict[str, Handler] = {}

    def register(self, name: str) -> Callable[[Handler], Handler]:
        def decorator(func: Handler) -> Handler:
            self.handlers[name] = func
            return func
        return decorator


registry = HandlerRegistry()
handler = registry.register


class Bridge:
    """Starts the UI, answers its requests, and lets the core send it events and requests."""

    def __init__(self, exe_path: Union[str, Sequence[str]], root: str,
                 handlers: Optional[Dict[str, Handler]] = None,
                 on_give_up: Optional[Callable[[], None]] = None,
                 args: Sequence[str] = ()):
        self._command: List[str] = [exe_path] if isinstance(exe_path, str) else list(exe_path)
        self.root = root
        self.handlers: Dict[str, Handler] = handlers if handlers is not None else registry.handlers
        self.on_give_up = on_give_up
        self._extra_args = list(args)
        self._proc: Optional[subprocess.Popen] = None
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._pending: Dict[int, Future] = {}
        self._next_id = 0
        self._executor = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="BridgeRequest")
        self._subscribers: Dict[str, List[Callable[[dict], None]]] = {}
        self._events: "queue.Queue[Optional[tuple]]" = queue.Queue()
        self._event_thread: Optional[threading.Thread] = None
        self._stopping = False
        self._gave_up = False
        self._starts: Deque[float] = deque()
        self.generation = 0  # counts UI starts, so listeners can tell a restart

    # Lifecycle -----------------------------------------------------------

    def start(self, args: Optional[Sequence[str]] = None) -> None:
        """Launch the UI, with these extra command line arguments. Does nothing if it is already running."""
        if args is not None:
            self._extra_args = list(args)
        with self._state_lock:
            if self._proc is not None and self._proc.poll() is None:
                return
            self._stopping = False
        if self._event_thread is None:
            self._event_thread = threading.Thread(target=self._event_loop, name="BridgeEvents", daemon=True)
            self._event_thread.start()
        self._launch()

    def _launch(self) -> None:
        command = self._command + ["--root", self.root, "--parent-pid", str(os.getpid())] + self._extra_args
        startupinfo = subprocess.STARTUPINFO()
        # The window must never start minimized, whatever the parent was started with.
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = SW_SHOWNORMAL
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, startupinfo=startupinfo,
                                cwd=self.root or None, bufsize=0)
        try:
            # Lets the new window take the foreground when it activates itself.
            ctypes.windll.user32.AllowSetForegroundWindow(proc.pid)
        except Exception:
            pass
        with self._state_lock:
            self._proc = proc
            self.generation += 1
            self._starts.append(time.monotonic())
        # A window that crashed and is started again should be seen.
        self._extra_args = [a for a in self._extra_args if a != "--hidden"]
        threading.Thread(target=self._read_loop, args=(proc,), name="BridgeReader", daemon=True).start()
        logger.info(f"Started the UI (pid {proc.pid})")

    def stop(self, timeout: float = 1.5) -> None:
        """Ask the UI to quit, then make sure it has."""
        with self._state_lock:
            self._stopping = True
            proc = self._proc
        if proc is None:
            return
        try:
            self.send_event("ui.quit", {})
        except Exception:
            pass
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=timeout)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        self._fail_pending("The window closed.")

    def is_running(self) -> bool:
        proc = self._proc
        return proc is not None and proc.poll() is None

    @property
    def pid(self) -> Optional[int]:
        proc = self._proc
        return proc.pid if proc is not None else None

    # Events and requests to the UI ----------------------------------------

    def send_event(self, name: str, data: Optional[dict] = None) -> bool:
        """Send an event to the UI. Returns False when the UI isn't there to get it."""
        return self._send({"type": "event", "name": name, "data": data or {}})

    def request(self, method: str, params: Optional[dict] = None, timeout: float = 10.0) -> Any:
        """Call a method in the UI and wait for its result. Raises BridgeError on failure."""
        future: Future = Future()
        with self._state_lock:
            self._next_id += 1
            request_id = self._next_id
            self._pending[request_id] = future
        if not self._send({"type": "request", "id": request_id, "method": method, "params": params or {}}):
            self._pending.pop(request_id, None)
            raise BridgeError("The window isn't running.")
        try:
            return future.result(timeout)
        except BridgeError:
            raise
        except Exception as e:
            self._pending.pop(request_id, None)
            raise BridgeError(f"{method} timed out" if "Timeout" in type(e).__name__ else str(e)) from e

    def subscribe(self, name: str, callback: Callable[[dict], None]) -> None:
        """Call callback(data) for each event the UI sends with this name."""
        self._subscribers.setdefault(name, []).append(callback)

    def _send(self, message: dict) -> bool:
        proc = self._proc
        if proc is None or proc.poll() is not None or proc.stdin is None:
            return False
        line = (json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            with self._write_lock:
                proc.stdin.write(line)
                proc.stdin.flush()
            return True
        except (OSError, ValueError):
            return False

    # Reading --------------------------------------------------------------

    def _read_loop(self, proc: subprocess.Popen) -> None:
        stream = proc.stdout
        try:
            while True:
                raw = stream.readline()
                if not raw:
                    break
                try:
                    message = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    logger.warning(f"Ignoring a line the UI sent that isn't JSON: {raw[:120]!r}")
                    continue
                if isinstance(message, dict):
                    self._dispatch(message)
        except (OSError, ValueError):
            pass
        self._on_exit(proc)

    def _dispatch(self, message: dict) -> None:
        kind = message.get("type")
        if kind == "request":
            self._executor.submit(self._serve, message)
        elif kind == "response":
            future = self._pending.pop(message.get("id"), None)
            if future is None or future.done():
                return
            if message.get("ok"):
                future.set_result(message.get("result"))
            else:
                future.set_exception(BridgeError(str(message.get("error") or "Request failed.")))
        elif kind == "event":
            self._events.put((message.get("name", ""), message.get("data") or {}))

    def _serve(self, message: dict) -> None:
        method = message.get("method", "")
        request_id = message.get("id")
        func = self.handlers.get(method)
        if func is None:
            reply = {"type": "response", "id": request_id, "ok": False, "error": f"Unknown method: {method}"}
        else:
            try:
                params = message.get("params")
                reply = {"type": "response", "id": request_id, "ok": True,
                         "result": func(params if isinstance(params, dict) else {})}
                json.dumps(reply)  # a result that can't be serialized is an error, not a crash
            except Exception as e:
                logger.exception(f"Handler {method} failed")
                reply = {"type": "response", "id": request_id, "ok": False, "error": str(e) or type(e).__name__}
        self._send(reply)

    def _event_loop(self) -> None:
        while True:
            item = self._events.get()
            if item is None:
                return
            name, data = item
            for callback in list(self._subscribers.get(name, ())):
                try:
                    callback(data)
                except Exception:
                    logger.exception(f"Event handler for {name} failed")

    # Exit and restart -----------------------------------------------------

    def _fail_pending(self, reason: str) -> None:
        with self._state_lock:
            pending, self._pending = self._pending, {}
        for future in pending.values():
            if not future.done():
                future.set_exception(BridgeError(reason))

    def _on_exit(self, proc: subprocess.Popen) -> None:
        try:
            proc.wait(timeout=2)
        except Exception:
            pass
        with self._state_lock:
            if proc is not self._proc:
                return
            stopping = self._stopping
        self._fail_pending("The window closed.")
        if stopping:
            return
        logger.warning(f"The UI exited on its own (code {proc.returncode})")
        now = time.monotonic()
        with self._state_lock:
            while self._starts and now - self._starts[0] > RESTART_WINDOW_SECONDS:
                self._starts.popleft()
            too_many = len(self._starts) > MAX_RESTARTS
        if too_many:
            self._give_up()
            return
        try:
            self._launch()
        except Exception:
            logger.exception("Could not restart the UI")
            self._give_up()

    def _give_up(self) -> None:
        if self._gave_up:
            return
        self._gave_up = True
        logger.error("The UI keeps exiting; giving up on it")
        if self.on_give_up is not None:
            try:
                self.on_give_up()
            except Exception:
                logger.exception("on_give_up failed")


def find_ui_exe(root: str) -> Optional[str]:
    """FA11y.UI.exe: the published copy in ui/bin, else a development build."""
    candidates = [
        os.path.join(root, "ui", "bin", "FA11y.UI.exe"),
        os.path.join(root, "ui", "src", "FA11y.UI", "bin", "Release", "net9.0-windows", "FA11y.UI.exe"),
        os.path.join(root, "ui", "src", "FA11y.UI", "bin", "Debug", "net9.0-windows", "FA11y.UI.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None
