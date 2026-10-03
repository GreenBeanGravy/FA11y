"""Requests for the Fortnite page.

Long operations (install, update, verify, move, uninstall, the Epic Games
Launcher choices) return an operation id at once. While one runs the core
sends operation.progress {id, percent, message} (percent is null when it
can't tell) and, at the end, operation.finished {id, ok, message, cancelled}.
Only one operation runs at a time.

Other events: fortnite.mouse_detected {available, text, detected, found}.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from lib.hub import fortnite_ops, game_watch, get_hub, sounds, status
from lib.shell.bridge import handler

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_operation: Optional["_Operation"] = None
_next_id = 0
_last_status = None


class _Operation:
    def __init__(self, op_id: int, name: str):
        self.id = op_id
        self.name = name
        self.cancel = threading.Event()
        self.percent: Optional[float] = None
        self.message = f"{name}…"
        self._sent_at = 0.0
        self._sent_percent = -1.0
        self._sent_message = ""

    def info(self) -> dict:
        return {"id": self.id, "name": self.name, "percent": self.percent, "message": self.message}

    def wants_send(self, percent: Optional[float], message: str) -> bool:
        """Progress arrives often; the window needs a change it can show, not every line."""
        now = time.monotonic()
        changed = message != self._sent_message or percent is None or abs(percent - self._sent_percent) >= 0.5
        if not changed and now - self._sent_at < 1.0:
            return False
        self._sent_at, self._sent_percent, self._sent_message = now, percent if percent is not None else -1.0, message
        return True


def _manager():
    from lib.fortnite import get_manager
    return get_manager()


def _send(name: str, data: Optional[dict] = None) -> None:
    hub = get_hub()
    if hub is not None:
        hub.send(name, data)


def _remember(st) -> None:
    """Keep the latest install status for Play, Open folder and the Epic Games Launcher choices."""
    global _last_status
    _last_status = st
    status._last_install_info = st


def _cached_or_fresh_status():
    return _last_status if _last_status is not None else _fetch_status(False)


def _fetch_status(check_updates: bool):
    st = _manager().status(check_updates=check_updates)
    _remember(st)
    return st


# Status -----------------------------------------------------------------

@handler("fortnite.state")
def state(params: dict) -> dict:
    check = bool(params.get("check_updates"))
    st = _fetch_status(check)
    result = fortnite_ops.describe_status(st)
    result["running"] = game_watch.is_fortnite_running()
    result["default_install_base"] = _default_install_base()
    with _lock:
        op = _operation
    result["operation"] = op.info() if op is not None else None
    if check:
        result["message"] = fortnite_ops.check_message(st)
    return result


def _default_install_base() -> str:
    import os
    return os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Epic Games")


# Operations -----------------------------------------------------------------

def _start(name: str, operation: Callable) -> dict:
    """Run operation(progress, cancel) on a worker thread and report it with events."""
    global _operation, _next_id
    with _lock:
        if _operation is not None:
            raise RuntimeError("Wait for the current operation to finish.")
        _next_id += 1
        op = _Operation(_next_id, name)
        _operation = op

    def progress(percent, message) -> None:
        percent = None if percent is None else max(0.0, min(float(percent), 100.0))
        if message:
            op.message = message
        op.percent = percent
        if op.wants_send(percent, op.message):
            _send("operation.progress", {"id": op.id, "percent": percent, "message": op.message})

    def work() -> None:
        global _operation
        from lib.fortnite import OperationResult
        try:
            result = operation(progress, op.cancel)
        except Exception as e:
            logger.exception(f"Fortnite operation {name} failed")
            result = OperationResult(False, f"{name} failed: {e}")
        with _lock:
            _operation = None
        sounds.ui("done" if result.ok else "error")
        _send("operation.finished", {"id": op.id, "ok": bool(result.ok), "message": result.message,
                                     "cancelled": bool(getattr(result, "cancelled", False))})
        _send("home.changed")

    threading.Thread(target=work, name=f"Fortnite-{name}", daemon=True).start()
    return {"id": op.id, "name": name}


@handler("fortnite.install_question")
def install_question(params: dict) -> dict:
    base = str(params.get("base", ""))
    if not base:
        raise ValueError("Choose a folder first.")
    return {"question": fortnite_ops.install_question(base)}


@handler("fortnite.install")
def install(params: dict) -> dict:
    base = str(params.get("base", ""))
    if not base:
        raise ValueError("Choose a folder first.")
    return _start("Installing", lambda p, c: _manager().install(base, p, c))


@handler("fortnite.update")
def update(_params: dict) -> dict:
    return _start("Updating", lambda p, c: _manager().update(p, c))


@handler("fortnite.verify")
def verify(_params: dict) -> dict:
    return _start("Verifying", lambda p, c: _manager().verify_and_repair(p, c))


@handler("fortnite.move")
def move(params: dict) -> dict:
    target = str(params.get("target", ""))
    if not target:
        raise ValueError("Choose a folder first.")
    return _start("Moving", lambda p, c: _manager().move(target, p, c))


@handler("fortnite.uninstall")
def uninstall(_params: dict) -> dict:
    return _start("Uninstalling", lambda p, c: _manager().uninstall(p, c))


@handler("fortnite.import_egl")
def import_egl(_params: dict) -> dict:
    """Let FA11y manage the install the Epic Games Launcher has."""
    path = _cached_or_fresh_status().egl_install_path
    return _start("Setting up", lambda p, c: _manager().import_egl(path, p, c))


@handler("fortnite.egl_sync")
def egl_sync(_params: dict) -> dict:
    """Keep using the Epic Games Launcher and sync it with FA11y."""
    return _start("Syncing", lambda p, c: _manager().egl_sync(p, c))


@handler("fortnite.cancel")
def cancel(_params: dict) -> dict:
    with _lock:
        op = _operation
    if op is None:
        return {"cancelling": False}
    op.cancel.set()
    return {"cancelling": True}


# Other actions -------------------------------------------------------------------

@handler("fortnite.play")
def play(_params: dict) -> dict:
    """Launch Fortnite, or bring it forward. A failed launch is spoken and sent as fortnite.launch_failed."""
    from lib.hub.play import play_fortnite
    hub = get_hub()
    if hub is None:
        raise RuntimeError("FA11y is closing.")

    def failed(message: str) -> None:
        sounds.ui("error")
        hub.services.speak(message)
        _send("fortnite.launch_failed", {"message": message})

    play_fortnite(hub, _manager(), _last_status, on_failed=failed)
    return {}


@handler("fortnite.sign_in")
def sign_in(_params: dict) -> dict:
    """Sign legendary in with the Epic account FA11y already has."""
    from lib.utilities.epic_auth import get_epic_auth_instance
    auth = get_epic_auth_instance()
    if not auth or not auth.access_token or not auth.is_valid:
        return {"ok": False, "needs_account": True, "message": "Sign in to your Epic account first."}
    result = _manager().login_with_exchange_code(auth.get_exchange_code())
    sounds.ui("done" if result.ok else "error")
    return {"ok": bool(result.ok), "needs_account": False, "message": result.message}


@handler("fortnite.open_folder")
def open_folder(_params: dict) -> dict:
    path = _last_status.install_path if _last_status is not None else ""
    return {"ok": fortnite_ops.open_install_folder(path)}


# Launch options ----------------------------------------------------------------------

@handler("fortnite.launch_options")
def launch_options(_params: dict) -> dict:
    return {**fortnite_ops.launch_options(), "choices": [{"key": k, "label": v} for k, v in fortnite_ops.API_CHOICES]}


@handler("fortnite.save_launch_options")
def save_launch_options(params: dict) -> dict:
    ok = fortnite_ops.save_launch_options(str(params.get("api", "default")), bool(params.get("skip_splash")),
                                          str(params.get("extra", "")))
    return {"ok": bool(ok)}


# Mouse passthrough --------------------------------------------------------------------

@handler("fortnite.mouse")
def mouse(_params: dict) -> dict:
    return fortnite_ops.mouse_info()


@handler("fortnite.detect_mouse")
def detect_mouse(_params: dict) -> dict:
    """Start listening for the mouse to move; the answer comes as fortnite.mouse_detected."""
    from lib.mouse_passthrough import get_mouse_passthrough

    def done(device) -> None:
        sounds.ui("done" if device else "error")
        _send("fortnite.mouse_detected", fortnite_ops.mouse_after_detect(device))

    get_mouse_passthrough().recapture_mouse(on_done=done)
    return {"text": fortnite_ops.MOUSE_PROMPT}
