"""
Fortnite install management through legendary (the open-source Epic Games
Launcher CLI).

This module is UI free. A GUI calls it from worker threads and shows the
``progress(percent, message)`` callbacks on a gauge and a status line.

Everything here was written against legendary 0.20.34 (the version the
updater downloads). Things worth knowing about that CLI:

* Exit codes are unreliable: most failures only log an ``ERROR`` /
  ``CRITICAL`` line and then exit with code 0. Results are therefore decided
  from the parsed output as well as the exit code.
* Log lines (stderr) look like ``[cli] INFO: message``. The downloader prints
  ``= Progress: ...`` blocks through the same logger; the ``verify`` command
  writes ``Verification progress: ...`` to stdout using carriage returns.
* ``-y`` is a *global* flag and must come before the sub command.
* ``launch`` collects unknown arguments and passes them to the game, so game
  arguments simply follow the app name.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import threading
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Deque, Dict, Iterator, List, Optional, Sequence, Tuple

import psutil

logger = logging.getLogger(__name__)

APP_NAME = "Fortnite"
FORTNITE_PROCESS_NAMES = ("fortniteclient-win64-shipping.exe", "fortnitelauncher.exe")
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)

ProgressCallback = Callable[[Optional[float], str], None]

# ---------------------------------------------------------------------------
# Launch options + config
# ---------------------------------------------------------------------------

CONFIG_SECTION = "Fortnite"
_CONFIG_DEFAULTS: Dict[str, Tuple[str, str]] = {
    "LaunchAPI": (
        "default",
        "Graphics API used when FA11y launches Fortnite. Options: default, dx11, dx12, performance (the "
        "performance option uses -FeatureLevelES31).",
    ),
    "SkipSplash": (
        "false",
        "Adds -NOSPLASH when FA11y launches Fortnite so the intro splash screen is skipped.",
    ),
    "ExtraLaunchArgs": (
        "",
        "Extra command line arguments passed to Fortnite when FA11y launches it. Separate arguments with spaces.",
    ),
}

API_FLAGS: Dict[str, Optional[str]] = {
    "default": None,
    "dx11": "-dx11",
    "dx12": "-dx12",
    "performance": "-FeatureLevelES31",
}
SKIP_SPLASH_FLAG = "-NOSPLASH"


@dataclass
class LaunchOptions:
    """User chosen Fortnite launch options."""

    api: str = "default"
    skip_splash: bool = False
    extra: str = ""

    def to_args(self) -> List[str]:
        """Return the argument list to append after ``legendary launch Fortnite``."""
        args: List[str] = []
        flag = API_FLAGS.get((self.api or "default").strip().lower())
        if flag:
            args.append(flag)
        if self.skip_splash:
            args.append(SKIP_SPLASH_FLAG)
        args.extend(parse_extra_args(self.extra))
        return args


def parse_extra_args(text: str) -> List[str]:
    """Split free text launch arguments (shlex, posix=False so quotes are kept for the game)."""
    text = (text or "").strip()
    if not text:
        return []
    try:
        tokens = shlex.split(text, posix=False)
    except ValueError:
        logger.warning("Could not parse extra launch arguments with shlex, splitting on spaces")
        tokens = text.split()
    # posix=False keeps the quotes (and backslashes) as typed; drop one wrapping pair so a quoted
    # token such as "C:\My Dir\x" reaches the game as a single argument without literal quotes.
    return [t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'" else t for t in tokens]


def _encode_value(value: str) -> str:
    # Values are stored as ``value "description"``, so a literal double quote would break parsing.
    return value.replace("%", "%25").replace('"', "%22")


def _decode_value(value: str) -> str:
    return value.replace("%22", '"').replace("%25", "%")


def _read_cfg():
    from lib.utilities.utilities import read_config
    return read_config(use_cache=False)


def _write_cfg(config) -> bool:
    from lib.utilities.utilities import save_config
    return save_config(config)


def _raw_config_value(config, key: str) -> Optional[str]:
    if not config.has_section(CONFIG_SECTION) or not config.has_option(CONFIG_SECTION, key):
        return None
    return config.get(CONFIG_SECTION, key).split('"')[0].strip()


def load_launch_options() -> LaunchOptions:
    """Load launch options from the ``[Fortnite]`` config section (defaults if missing)."""
    try:
        config = _read_cfg()
    except Exception:
        logger.exception("Could not read config for Fortnite launch options")
        return LaunchOptions()
    api = (_raw_config_value(config, "LaunchAPI") or "default").lower()
    if api not in API_FLAGS:
        api = "default"
    skip = (_raw_config_value(config, "SkipSplash") or "false").lower() in ("true", "yes", "on", "1")
    extra = _decode_value(_raw_config_value(config, "ExtraLaunchArgs") or "")
    return LaunchOptions(api=api, skip_splash=skip, extra=extra)


def save_launch_options(options: LaunchOptions) -> bool:
    """Save launch options into the ``[Fortnite]`` config section. Returns True on success."""
    try:
        config = _read_cfg()
        if not config.has_section(CONFIG_SECTION):
            config.add_section(CONFIG_SECTION)
        api = (options.api or "default").strip().lower()
        if api not in API_FLAGS:
            api = "default"
        values = {
            "LaunchAPI": api,
            "SkipSplash": "true" if options.skip_splash else "false",
            "ExtraLaunchArgs": _encode_value((options.extra or "").strip()),
        }
        for key, value in values.items():
            description = _CONFIG_DEFAULTS[key][1]
            config.set(CONFIG_SECTION, key, f'{value} "{description}"' if value else f'"{description}"')
        return bool(_write_cfg(config))
    except Exception:
        logger.exception("Could not save Fortnite launch options")
        return False


# ---------------------------------------------------------------------------
# Progress parsing
# ---------------------------------------------------------------------------

_PROGRESS_RE = re.compile(
    r"= Progress: (?P<pct>\d+(?:\.\d+)?)% \((?P<done>\d+)/(?P<total>\d+)\), "
    r"Running for (?P<rt>[\d:]+), ETA: (?P<eta>[\d:]+)"
)
_DOWNLOADED_RE = re.compile(r"- Downloaded: (?P<dl>\d+(?:\.\d+)?) MiB, Written: (?P<wr>\d+(?:\.\d+)?) MiB")
_SPEED_RE = re.compile(
    r"\+ Download\s+- (?P<raw>\d+(?:\.\d+)?) MiB/s \(raw\) / (?P<unc>\d+(?:\.\d+)?) MiB/s \(decompressed\)"
)
_DL_SIZE_RE = re.compile(r"Download size: (?P<mib>\d+(?:\.\d+)?) MiB")
_VERIFY_RE = re.compile(
    r"Verification progress: (?P<num>\d+)/(?P<total>\d+) \((?P<pct>\d+(?:\.\d+)?)%\) "
    r"\[(?P<speed>\d+(?:\.\d+)?) MiB/s\]"
)
_NOISE_RE = re.compile(r"(?:= Progress:|- Downloaded:|- Cache usage:|\+ Download\s|\+ Disk\s|Verification progress:)")
_LOG_RE = re.compile(r"^\[(?P<name>[^\]]+)\] (?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL): (?P<msg>.*)$")


def format_size(mib: float) -> str:
    """Format a size given in MiB as ``MB`` or ``GB`` text."""
    if mib >= 1024:
        return f"{mib / 1024:.1f} GB"
    return f"{mib:.0f} MB"


def _format_eta(eta: str) -> str:
    try:
        h, m, s = (int(part) for part in eta.split(":"))
    except ValueError:
        return ""
    if h == m == s == 0:
        return ""
    return f"{h}:{m:02d}:{s:02d}"


class ProgressParser:
    """Turns legendary output lines into ``(percent, message)`` updates.

    ``feed`` returns ``None`` for lines that carry no new information. A
    ``percent`` of ``None`` means "message only, leave the gauge alone".
    """

    def __init__(self, verb: str = "Downloading") -> None:
        self.verb = verb
        self.percent: Optional[float] = None
        self.total_mib: Optional[float] = None
        self.downloaded_mib: Optional[float] = None
        self.speed_mib: Optional[float] = None
        self.eta = ""

    def _download_message(self) -> str:
        parts = f"{self.verb}:"
        if self.downloaded_mib is not None:
            parts += f" {format_size(self.downloaded_mib)}"
            if self.total_mib:
                parts += f" of {format_size(self.total_mib)}"
        elif self.percent is not None:
            parts += f" {self.percent:.1f}%"
        message = parts
        if self.speed_mib is not None:
            message += f", {self.speed_mib:.0f} MB/s"
        eta = _format_eta(self.eta)
        if eta:
            message += f", ETA {eta}"
        return message

    def feed(self, line: str) -> Optional[Tuple[Optional[float], str]]:
        match = _VERIFY_RE.search(line)
        if match:
            pct = float(match["pct"])
            return pct, (
                f"Verifying files: {pct:.1f}%, {match['num']} of {match['total']} files, "
                f"{float(match['speed']):.0f} MB/s"
            )
        match = _PROGRESS_RE.search(line)
        if match:
            self.percent = float(match["pct"])
            self.eta = match["eta"]
            return self.percent, self._download_message()
        match = _DOWNLOADED_RE.search(line)
        if match:
            self.downloaded_mib = float(match["dl"])
            return None
        match = _SPEED_RE.search(line)
        if match:
            self.speed_mib = float(match["raw"])
            return self.percent, self._download_message()
        match = _DL_SIZE_RE.search(line)
        if match:
            self.total_mib = float(match["mib"])
            return None
        log = _LOG_RE.match(line.strip())
        if log and log["level"] == "INFO" and log["name"] in ("cli", "Core") and len(log["msg"]) < 200:
            return None, log["msg"]
        return None


class _Reporter:
    """Maps a sub operation's 0-100 range onto part of the overall gauge."""

    def __init__(self, callback: Optional[ProgressCallback], low: float = 0.0, high: float = 100.0) -> None:
        self.callback = callback
        self.low = low
        self.high = high

    def __call__(self, percent: Optional[float], message: str) -> None:
        if self.callback is None:
            return
        scaled = None if percent is None else self.low + (self.high - self.low) * max(0.0, min(100.0, percent)) / 100.0
        try:
            self.callback(scaled, message)
        except Exception:
            logger.exception("Progress callback raised")


# ---------------------------------------------------------------------------
# Results and status
# ---------------------------------------------------------------------------

@dataclass
class OperationResult:
    """Outcome of an operation. ``message`` is always user readable."""

    ok: bool
    message: str
    cancelled: bool = False
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EglInstall:
    """Fortnite as recorded by the Epic Games Launcher."""

    install_path: str
    version: str = ""
    manifest_path: str = ""
    incomplete: bool = False


@dataclass
class FortniteStatus:
    """Snapshot of the Fortnite install state."""

    installed: bool = False
    version: str = ""
    install_path: str = ""
    install_size_bytes: int = 0
    needs_verification: bool = False
    update_available: bool = False
    remote_version: str = ""
    update_checked: bool = False  # True when the remote version was refreshed from Epic during this call
    logged_in: bool = False
    account: str = ""
    managed_by: Optional[str] = None  # "legendary", "egl" or None
    egl_install_path: str = ""
    egl_version: str = ""
    running: bool = False
    legendary_available: bool = True
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def default_egl_manifest_dir() -> str:
    """Directory holding the Epic Games Launcher ``*.item`` manifests."""
    program_data = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
    return os.path.join(program_data, "Epic", "EpicGamesLauncher", "Data", "Manifests")


def find_egl_fortnite(manifest_dir: Optional[str] = None) -> Optional[EglInstall]:
    """Find Fortnite in the Epic Games Launcher manifests, or ``None``.

    Entries whose install folder no longer exists are ignored.
    """
    directory = manifest_dir or default_egl_manifest_dir()
    try:
        names = sorted(n for n in os.listdir(directory) if n.lower().endswith(".item"))
    except OSError:
        return None
    for name in names:
        path = os.path.join(directory, name)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or str(data.get("AppName", "")).lower() != APP_NAME.lower():
            continue
        location = data.get("InstallLocation") or ""
        if location and os.path.isdir(location):
            return EglInstall(
                install_path=os.path.normpath(location),
                version=str(data.get("AppVersionString", "") or ""),
                manifest_path=path,
                incomplete=bool(data.get("bIsIncompleteInstall", False)),
            )
    return None


def is_fortnite_running() -> bool:
    """True when a Fortnite game or launcher process exists."""
    try:
        for proc in psutil.process_iter(["name"]):
            name = (proc.info.get("name") or "").lower()
            if name in FORTNITE_PROCESS_NAMES:
                return True
    except Exception:
        logger.debug("Process scan failed", exc_info=True)
    return False


def _directory_size(path: str) -> int:
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


# ---------------------------------------------------------------------------
# Process helpers
# ---------------------------------------------------------------------------

def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Terminate a process and everything it spawned (legendary uses worker processes)."""
    try:
        parent = psutil.Process(proc.pid)
        procs = parent.children(recursive=True) + [parent]
    except psutil.NoSuchProcess:
        return
    for p in procs:
        try:
            p.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(procs, timeout=3)
    for p in alive:
        try:
            p.kill()
        except psutil.Error:
            pass


def _iter_output_lines(stream) -> Iterator[str]:
    """Yield lines from a binary stream, splitting on both ``\\r`` and ``\\n``."""
    buffer = b""
    reader = getattr(stream, "read1", None) or stream.read
    while True:
        chunk = reader(4096)
        if not chunk:
            break
        buffer += chunk
        parts = re.split(rb"[\r\n]+", buffer)
        buffer = parts.pop()
        for part in parts:
            if part:
                yield part.decode("utf-8", "replace")
    if buffer:
        yield buffer.decode("utf-8", "replace")


@dataclass
class CaptureResult:
    returncode: Optional[int]
    stdout: str = ""
    stderr: str = ""
    error: str = ""


@dataclass
class RunOutcome:
    """Result of a streamed legendary run."""

    returncode: Optional[int]
    lines: List[str] = field(default_factory=list)
    cancelled: bool = False
    start_error: str = ""

    def contains(self, text: str) -> bool:
        return any(text in line for line in self.lines)

    def error_lines(self) -> List[str]:
        found = []
        for line in self.lines:
            match = _LOG_RE.match(line.strip())
            if match and match["level"] in ("ERROR", "CRITICAL"):
                found.append(match["msg"])
        return found

    def failure_lines(self) -> List[str]:
        """Requirement failures printed as `` ! Failure: ...`` (for example not enough disk space)."""
        return [line.strip()[len("! Failure:"):].strip() for line in self.lines
                if line.strip().startswith("! Failure:")]


_EXCEPTION_RE = re.compile(r"^(?:[A-Za-z_][\w.]*(?:Error|Exception)): .+$")
NOT_SIGNED_IN = ("Fortnite needs your Epic account to start. Sign in on the Epic account page, "
                 "then press Play again.")


def _exception_line(outcome: RunOutcome) -> str:
    """The exception line of a crash traceback (``ValueError: No saved credentials``), or ""."""
    if not outcome.contains("Traceback (most recent call last)"):
        return ""
    for line in reversed(outcome.lines):
        if _EXCEPTION_RE.match(line.strip()):
            return line.strip()
    return ""


def _friendly_error(outcome: RunOutcome, fallback: str) -> str:
    failures = outcome.failure_lines()
    if failures:
        return "; ".join(failures)
    errors = outcome.error_lines()
    text = errors[-1] if errors else _exception_line(outcome)
    if not text:
        for line in reversed(outcome.lines):
            match = _LOG_RE.match(line.strip())
            if match and match["level"] in ("WARNING",):
                text = match["msg"]
                break
    lowered = text.lower()
    if "no saved credentials" in lowered:
        return NOT_SIGNED_IN
    if "login failed" in lowered or "log in failed" in lowered:
        return "You are not logged in to Epic Games, or the login expired. Log in and try again."
    if "installed data lock" in lowered:
        return "Another legendary operation (install, import or move) is already running. Wait for it to finish."
    if "not installed" in lowered or "not currently installed" in lowered:
        return "Fortnite is not installed through legendary."
    if text:
        return text
    if outcome.returncode not in (None, 0):
        last = outcome.lines[-1].strip() if outcome.lines else ""
        return f"{fallback} (legendary exited with code {outcome.returncode}{': ' + last if last else ''})"
    return fallback


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class FortniteManager:
    """Manages the Fortnite install through legendary. One long operation runs at a time."""

    def __init__(self, legendary_cmd: Optional[Sequence[str]] = None, files_dir: Optional[str] = None) -> None:
        self._files_dir = files_dir or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self._legendary_cmd = list(legendary_cmd) if legendary_cmd else None
        self._op_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._current_op: Optional[str] = None

    # -- locating / running legendary ------------------------------------

    def legendary_command(self) -> Optional[List[str]]:
        """Command prefix used to run legendary, or ``None`` if it cannot be found."""
        if self._legendary_cmd:
            return list(self._legendary_cmd)
        candidates = [os.path.join(self._files_dir, "legendary.exe"), os.path.join(os.getcwd(), "legendary.exe")]
        for candidate in candidates:
            if os.path.isfile(candidate):
                return [candidate]
        found = shutil.which("legendary")
        return [found] if found else None

    @property
    def current_operation(self) -> Optional[str]:
        """Name of the running long operation, or ``None``."""
        with self._state_lock:
            return self._current_op

    def _env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"  # legendary is a frozen Python app; keep piped output unbuffered
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def _missing_message(self) -> str:
        return f"legendary.exe was not found in {self._files_dir}. Run the FA11y updater to download it."

    def _run_capture(self, args: Sequence[str], timeout: float = 90.0) -> CaptureResult:
        """Run legendary to completion and capture stdout and stderr separately."""
        cmd = self.legendary_command()
        if cmd is None:
            return CaptureResult(None, error=self._missing_message())
        try:
            completed = subprocess.run(
                cmd + list(args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=self._files_dir if os.path.isdir(self._files_dir) else None, env=self._env(),
                creationflags=CREATE_NO_WINDOW, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return CaptureResult(None, error="legendary took too long to respond.")
        except OSError as exc:
            return CaptureResult(None, error=f"Could not run legendary: {exc}")
        return CaptureResult(
            completed.returncode,
            completed.stdout.decode("utf-8", "replace"),
            completed.stderr.decode("utf-8", "replace"),
        )

    def _capture_json(self, args: Sequence[str], timeout: float = 90.0) -> Tuple[Any, str]:
        """Run a ``--json`` command. Returns ``(data, error_message)``."""
        result = self._run_capture(args, timeout)
        if result.error:
            return None, result.error
        text = result.stdout.strip()
        try:
            return json.loads(text), ""
        except ValueError:
            pass
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line[:1] in ("{", "["):
                try:
                    return json.loads(line), ""
                except ValueError:
                    continue
        stderr_lines = [ln for ln in result.stderr.splitlines() if ln.strip()]
        return None, stderr_lines[-1].strip() if stderr_lines else "legendary returned no data."

    def _run_streaming(self, args: Sequence[str], parser: Optional[ProgressParser], report: _Reporter,
                       cancel: Optional[threading.Event]) -> RunOutcome:
        """Run legendary, feeding output to ``parser``; kill the process tree when ``cancel`` is set."""
        cmd = self.legendary_command()
        if cmd is None:
            return RunOutcome(None, start_error=self._missing_message())
        if cancel is not None and cancel.is_set():
            return RunOutcome(None, cancelled=True)
        try:
            proc = subprocess.Popen(
                cmd + list(args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                cwd=self._files_dir if os.path.isdir(self._files_dir) else None, env=self._env(),
                creationflags=CREATE_NO_WINDOW,
            )
        except OSError as exc:
            return RunOutcome(None, start_error=f"Could not start legendary: {exc}")

        killed = threading.Event()
        done = threading.Event()

        def watch() -> None:
            while not done.wait(0.2):
                if cancel is not None and cancel.is_set():
                    killed.set()
                    _kill_process_tree(proc)
                    return

        watcher = None
        if cancel is not None:
            watcher = threading.Thread(target=watch, name="legendary-cancel-watch", daemon=True)
            watcher.start()

        lines: Deque[str] = deque(maxlen=400)
        try:
            for line in _iter_output_lines(proc.stdout):
                update = parser.feed(line) if parser is not None else None
                if update is not None:
                    report(*update)
                if _NOISE_RE.search(line):
                    continue  # per-second progress spam would push useful lines out of the tail
                lines.append(line)
            proc.wait()
        finally:
            done.set()
            if proc.poll() is None:
                _kill_process_tree(proc)
            try:
                proc.stdout.close()
            except OSError:
                pass
        return RunOutcome(proc.returncode, list(lines), cancelled=killed.is_set())

    # -- result helpers ----------------------------------------------------

    def _finish(self, outcome: RunOutcome, label: str, success: str, *, fail_markers: Sequence[str] = (),
                ok_markers: Sequence[str] = (), data: Optional[Dict[str, Any]] = None) -> OperationResult:
        """Turn a run outcome into an OperationResult."""
        if outcome.start_error:
            return OperationResult(False, outcome.start_error)
        if outcome.cancelled:
            return OperationResult(False, f"{label} cancelled. Progress is kept and resumes next time.", cancelled=True)
        for marker in fail_markers:
            if outcome.contains(marker):
                return OperationResult(False, _friendly_error(outcome, f"{label} failed."))
        has_ok_marker = any(outcome.contains(m) for m in ok_markers)
        if outcome.returncode != 0 or (outcome.error_lines() and not has_ok_marker) or outcome.failure_lines():
            return OperationResult(False, _friendly_error(outcome, f"{label} failed."))
        return OperationResult(True, success, data=data or {})

    def _exclusive(self, name: str, func: Callable[[], OperationResult]) -> OperationResult:
        if not self._op_lock.acquire(blocking=False):
            return OperationResult(False, f"Another operation is already running ({self.current_operation}). "
                                          "Wait for it to finish or cancel it first.")
        with self._state_lock:
            self._current_op = name
        try:
            return func()
        except Exception:
            logger.exception("Unexpected error during %s", name)
            return OperationResult(False, f"Unexpected error during {name}. See the FA11y log for details.")
        finally:
            with self._state_lock:
                self._current_op = None
            self._op_lock.release()

    def _precheck(self, needs_closed: bool) -> Optional[OperationResult]:
        if self.legendary_command() is None:
            return OperationResult(False, self._missing_message())
        if needs_closed and is_fortnite_running():
            return OperationResult(False, "Fortnite is running. Close it and try again.")
        return None

    # -- status --------------------------------------------------------------

    def status(self, check_updates: bool = False) -> FortniteStatus:
        """Report the install state.

        Runs two or three short legendary commands (each takes a second or two since
        legendary.exe is a one-file executable); call it from a worker thread.
        With ``check_updates`` legendary also logs in and refreshes Epic's latest
        version so ``update_available`` is current; otherwise the cached version is used.
        """
        st = FortniteStatus()
        st.running = is_fortnite_running()
        egl = find_egl_fortnite()
        if egl:
            st.egl_install_path = egl.install_path
            st.egl_version = egl.version

        if self.legendary_command() is None:
            st.legendary_available = False
            st.error = self._missing_message()
            st.managed_by = "egl" if egl else None
            return st

        installed_list, error = self._capture_json(["list-installed", "--json"])
        if error:
            st.error = error
        game = None
        if isinstance(installed_list, list):
            for item in installed_list:
                if isinstance(item, dict) and item.get("app_name") == APP_NAME:
                    game = item
                    break
        if game:
            st.installed = True
            st.version = str(game.get("version") or "")
            st.install_path = str(game.get("install_path") or "")
            st.needs_verification = bool(game.get("needs_verification", False))
            size = int(game.get("install_size") or 0)
            if not size and st.install_path and os.path.isdir(st.install_path):
                size = _directory_size(st.install_path)
            st.install_size_bytes = size

        account_info, _ = self._capture_json(["status", "--offline", "--json"])
        if isinstance(account_info, dict):
            account = str(account_info.get("account") or "")
            st.logged_in = bool(account) and account != "<not logged in>"
            st.account = account if st.logged_in else ""

        if st.installed:
            if check_updates and st.logged_in:
                _, refresh_error = self._capture_json(["list-installed", "--check-updates", "--json"], timeout=180)
                st.update_checked = not refresh_error
                if refresh_error and not st.error:
                    st.error = f"Could not check for updates: {refresh_error}"
            info, _ = self._capture_json(["info", APP_NAME, "--offline", "--json"])
            if isinstance(info, dict) and isinstance(info.get("game"), dict):
                st.remote_version = str(info["game"].get("version") or "")
            if st.remote_version and st.version:
                st.update_available = st.remote_version != st.version

        if st.installed:
            st.managed_by = "legendary"
        elif egl:
            st.managed_by = "egl"
        return st

    # -- long operations -------------------------------------------------------

    def install(self, base_path: str, progress: Optional[ProgressCallback] = None,
                cancel: Optional[threading.Event] = None) -> OperationResult:
        """Install Fortnite under ``base_path`` (legendary adds a ``Fortnite`` folder)."""
        def run() -> OperationResult:
            problem = self._precheck(needs_closed=False)
            if problem:
                return problem
            if not base_path or not str(base_path).strip():
                return OperationResult(False, "Choose a folder to install Fortnite into.")
            report = _Reporter(progress)
            report(None, "Preparing download")
            outcome = self._run_streaming(
                ["-y", "install", APP_NAME, "--base-path", str(base_path), "--skip-sdl", "--skip-dlcs"],
                ProgressParser("Downloading"), report, cancel)
            result = self._finish(outcome, "Install", "Fortnite is installed.",
                                  fail_markers=("Installation failed after",),
                                  ok_markers=("Finished installation process",))
            if result.ok:
                report(100.0, result.message)
            return result
        return self._exclusive("install", run)

    def update(self, progress: Optional[ProgressCallback] = None,
               cancel: Optional[threading.Event] = None) -> OperationResult:
        """Update the legendary-managed Fortnite install to the latest version."""
        def run() -> OperationResult:
            problem = self._precheck(needs_closed=True)
            if problem:
                return problem
            report = _Reporter(progress)
            report(None, "Checking for updates")
            outcome = self._run_streaming(
                ["-y", "update", APP_NAME, "--update-only", "--skip-sdl", "--skip-dlcs"],
                ProgressParser("Downloading"), report, cancel)
            up_to_date = outcome.contains("Download size is 0")
            result = self._finish(outcome, "Update", "Fortnite is up to date." if up_to_date else "Fortnite was updated.",
                                  fail_markers=("Installation failed after",),
                                  ok_markers=("Finished installation process", "Download size is 0"),
                                  data={"already_up_to_date": up_to_date})
            if result.ok:
                report(100.0, result.message)
            return result
        return self._exclusive("update", run)

    def verify_and_repair(self, progress: Optional[ProgressCallback] = None,
                          cancel: Optional[threading.Event] = None) -> OperationResult:
        """Verify every game file and download any that are damaged or missing.

        Runs ``legendary verify`` (hash check, writes legendary's repair file) and, only
        if it reports problems, ``legendary repair`` which re-downloads just those files.
        Verification fills 0-30 percent of the gauge and repair 30-100.
        """
        def run() -> OperationResult:
            problem = self._precheck(needs_closed=True)
            if problem:
                return problem
            verify_report = _Reporter(progress, 0.0, 30.0)
            verify_report(None, "Verifying files")
            verified = self._run_streaming(["verify", APP_NAME], ProgressParser("Verifying"), verify_report, cancel)
            if verified.start_error or verified.cancelled:
                return self._finish(verified, "Verification", "")
            if verified.contains("Verification finished successfully"):
                if progress:
                    _Reporter(progress)(100.0, "All Fortnite files are intact.")
                return OperationResult(True, "All Fortnite files are intact.", data={"repaired": False})
            failed = verified.contains("Verification failed")
            if not failed:
                return OperationResult(False, _friendly_error(verified, "Verification failed."))

            damaged = missing = 0
            for line in verified.lines:
                match = re.search(r"(\d+) file\(s\) corrupted, (\d+) file\(s\) are missing", line)
                if match:
                    damaged, missing = int(match.group(1)), int(match.group(2))
            repair_report = _Reporter(progress, 30.0, 100.0)
            repair_report(0.0, f"Found {damaged} damaged and {missing} missing files. Repairing")
            repaired = self._run_streaming(["-y", "repair", APP_NAME, "--skip-sdl"],
                                           ProgressParser("Repairing"), repair_report, cancel)
            result = self._finish(
                repaired, "Repair", f"Repaired {damaged + missing} files.",
                fail_markers=("Installation failed after",),
                ok_markers=("Finished installation process", "Download size is 0"),
                data={"repaired": True, "damaged": damaged, "missing": missing})
            if result.ok:
                repair_report(100.0, result.message)
            return result
        return self._exclusive("verify_and_repair", run)

    def move(self, new_base_path: str, progress: Optional[ProgressCallback] = None,
             cancel: Optional[threading.Event] = None) -> OperationResult:
        """Move the install to ``new_base_path`` (legendary adds the game folder name).

        ``legendary move`` renames the folder, which only works on the same drive. For another
        drive the files are copied here (with progress), then legendary's metadata is updated
        with ``move --skip-move`` and the old copy is removed.
        """
        def run() -> OperationResult:
            problem = self._precheck(needs_closed=True)
            if problem:
                return problem
            if not new_base_path or not str(new_base_path).strip():
                return OperationResult(False, "Choose a folder to move Fortnite to.")
            report = _Reporter(progress)
            report(None, "Moving Fortnite")
            outcome = self._run_streaming(["move", APP_NAME, str(new_base_path)], ProgressParser(), report, cancel)
            if not outcome.contains("different drive"):
                result = self._finish(outcome, "Move", f"Fortnite was moved to {new_base_path}.",
                                      ok_markers=("Finished.",))
                if result.ok:
                    report(100.0, result.message)
                return result
            return self._move_across_drives(str(new_base_path), report, cancel)
        return self._exclusive("move", run)

    def _installed_path(self) -> str:
        data, _ = self._capture_json(["list-installed", "--json"])
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("app_name") == APP_NAME:
                    return str(item.get("install_path") or "")
        return ""

    def _move_across_drives(self, new_base: str, report: _Reporter, cancel: Optional[threading.Event]) -> OperationResult:
        source = self._installed_path()
        if not source or not os.path.isdir(source):
            return OperationResult(False, "Fortnite's install folder could not be found.")
        destination = os.path.join(new_base, os.path.basename(os.path.normpath(source)))
        if os.path.exists(destination):
            return OperationResult(False, f"The folder {destination} already exists. Remove or rename it first.")
        try:
            copied = _copy_tree(source, destination, report, cancel)
        except OSError as exc:
            shutil.rmtree(destination, ignore_errors=True)
            return OperationResult(False, f"Copying Fortnite failed: {exc.strerror or exc}")
        if not copied:
            shutil.rmtree(destination, ignore_errors=True)
            return OperationResult(False, "Move cancelled. The original install was not changed.", cancelled=True)
        report(None, "Updating legendary")
        outcome = self._run_streaming(["move", APP_NAME, new_base, "--skip-move"], None, report, None)
        result = self._finish(outcome, "Move", "")
        if not result.ok:
            return OperationResult(False, f"Files were copied to {destination} but legendary could not be updated: "
                                          f"{result.message} The original install was left in place.")
        report(99.0, "Removing the old copy")
        shutil.rmtree(source, ignore_errors=True)
        message = f"Fortnite was moved to {destination}."
        if os.path.exists(source):
            message += f" Some files in the old folder {source} could not be removed; delete it manually."
        report(100.0, message)
        return OperationResult(True, message, data={"install_path": destination})

    def uninstall(self, progress: Optional[ProgressCallback] = None,
                  cancel: Optional[threading.Event] = None) -> OperationResult:
        """Uninstall Fortnite and delete its files."""
        def run() -> OperationResult:
            problem = self._precheck(needs_closed=True)
            if problem:
                return problem
            report = _Reporter(progress)
            report(None, "Uninstalling Fortnite")
            outcome = self._run_streaming(["-y", "uninstall", APP_NAME, "--skip-uninstaller"],
                                          ProgressParser(), report, cancel)
            result = self._finish(outcome, "Uninstall", "Fortnite was uninstalled.",
                                  fail_markers=("Removing game failed",),
                                  ok_markers=("Game has been uninstalled",))
            if result.ok:
                report(100.0, result.message)
            return result
        return self._exclusive("uninstall", run)

    def import_egl(self, path: str, progress: Optional[ProgressCallback] = None,
                   cancel: Optional[threading.Event] = None) -> OperationResult:
        """Import an existing install (for example the Epic Games Launcher's) into legendary."""
        def run() -> OperationResult:
            problem = self._precheck(needs_closed=True)
            if problem:
                return problem
            if not path or not os.path.isdir(path):
                return OperationResult(False, f"The folder {path} does not exist.")
            report = _Reporter(progress)
            report(None, "Importing Fortnite")
            outcome = self._run_streaming(["-y", "import", APP_NAME, str(path), "--skip-dlcs"],
                                          ProgressParser(), report, cancel)
            needs_verify = outcome.contains("will have to be verified")
            result = self._finish(outcome, "Import",
                                  "Fortnite was imported." + (" It will be verified before the next update." if needs_verify else ""),
                                  ok_markers=("install appears to be complete", "Some files are missing"),
                                  data={"needs_verification": needs_verify})
            if result.ok:
                report(100.0, result.message)
            return result
        return self._exclusive("import", run)

    def egl_sync(self, progress: Optional[ProgressCallback] = None,
                 cancel: Optional[threading.Event] = None) -> OperationResult:
        """Run a one-time two way sync with the Epic Games Launcher (no automatic sync is enabled)."""
        def run() -> OperationResult:
            problem = self._precheck(needs_closed=False)
            if problem:
                return problem
            report = _Reporter(progress)
            report(None, "Syncing with the Epic Games Launcher")
            outcome = self._run_streaming(["-y", "egl-sync", "--one-shot"], ProgressParser(), report, cancel)
            result = self._finish(outcome, "Sync", "Synced with the Epic Games Launcher.")
            if result.ok:
                report(100.0, result.message)
            return result
        return self._exclusive("egl_sync", run)

    # -- legendary sign-in -------------------------------------------------------

    def login_with_exchange_code(self, exchange_code: str) -> OperationResult:
        """Sign legendary in with an exchange code from FA11y's own Epic login.

        Exchange codes are single use and expire within minutes, so the
        caller should request a fresh one right before calling this.
        """
        if self.legendary_command() is None:
            return OperationResult(False, self._missing_message())
        if not exchange_code:
            return OperationResult(False, "Epic connection is recovering automatically. Launch will be available when it returns.")
        result = self._run_capture(["auth", "--token", exchange_code], timeout=60)
        if result.error:
            return OperationResult(False, result.error)
        output = f"{result.stdout}\n{result.stderr}"
        if "Successfully logged in as" in output or "Stored credentials are still valid" in output:
            return OperationResult(True, "Signed in for downloads and updates.")
        outcome = RunOutcome(result.returncode, output.splitlines()[-100:])
        return OperationResult(False, _friendly_error(outcome, "Signing in for downloads failed."))

    def logout(self) -> OperationResult:
        if self.legendary_command() is None:
            return OperationResult(False, self._missing_message())
        result = self._run_capture(["auth", "--delete"], timeout=30)
        if result.error:
            return OperationResult(False, result.error)
        return OperationResult(True, "Signed out of downloads and updates.")

    # -- launching ---------------------------------------------------------------

    def _account_id(self) -> Optional[str]:
        """The Epic account legendary is signed in as, from its saved login, or None."""
        folder = os.environ.get("LEGENDARY_CONFIG_PATH") or os.path.join(os.path.expanduser("~"), ".config", "legendary")
        try:
            with open(os.path.join(folder, "user.json"), "r", encoding="utf-8") as handle:
                account = json.load(handle).get("account_id")
        except (OSError, ValueError, AttributeError):
            return None
        return account if isinstance(account, str) and re.fullmatch(r"[0-9a-f]{32}", account) else None

    def is_logged_in(self) -> bool:
        """True when legendary has a saved Epic login of its own."""
        info, _ = self._capture_json(["status", "--offline", "--json"])
        if not isinstance(info, dict):
            return False
        account = str(info.get("account") or "")
        return bool(account) and account != "<not logged in>"

    def _ensure_login(self, get_exchange_code: Optional[Callable[[], str]]) -> Optional[str]:
        """Sign legendary in before a launch when it has no login. Returns a message when that fails.

        Without a saved login, ``legendary launch`` crashes with ``ValueError: No saved credentials``.
        """
        if self.is_logged_in():
            return None
        if get_exchange_code is None:
            return NOT_SIGNED_IN
        try:
            code = get_exchange_code()
        except Exception:
            logger.exception("Could not get an exchange code for legendary")
            code = ""
        if not code:
            return NOT_SIGNED_IN
        result = self.login_with_exchange_code(code)
        if not result.ok:
            logger.warning("Signing legendary in before launch failed: %s", result.message)
            return NOT_SIGNED_IN
        return None

    def launch(self, extra_args: Optional[Sequence[str]] = None, skip_version_check: bool = False,
               on_done: Optional[Callable[[OperationResult], None]] = None,
               get_exchange_code: Optional[Callable[[], str]] = None) -> OperationResult:
        """Start Fortnite with ``legendary launch Fortnite <extra_args>`` without blocking.

        ``extra_args`` defaults to the saved launch options. legendary logs in and checks the
        game version first, so it exits quickly with an error if that fails; ``on_done`` (if
        given) is called from a background thread with the final result of the legendary
        process, which ends once the game has started. When legendary has no login of its own,
        ``get_exchange_code`` (FA11y's Epic session) signs it in first.
        """
        if self.current_operation:
            return OperationResult(False, f"Wait for the {self.current_operation} operation to finish first.")
        cmd = self.legendary_command()
        if cmd is None:
            return OperationResult(False, self._missing_message())
        if is_fortnite_running():
            return OperationResult(False, "Fortnite is already running.")
        if extra_args is None:
            extra_args = load_launch_options().to_args()
        args = ["launch", APP_NAME]
        if skip_version_check:
            args.append("--skip-version-check")
        args.extend(str(a) for a in extra_args)
        if not any(str(a).lower().startswith("-named_pipe=") for a in extra_args):
            # Lets FA11y choose the lobby's island over a pipe, as the Epic Games Launcher does.
            from lib.utilities.fortnite_pipe import launch_arg
            args.append(launch_arg(self._account_id()))

        def done(result: OperationResult) -> None:
            if on_done is not None:
                try:
                    on_done(result)
                except Exception:
                    logger.exception("Launch callback raised")

        def wait() -> None:
            problem = None if skip_version_check else self._ensure_login(get_exchange_code)
            if problem:
                done(OperationResult(False, problem))
                return
            try:
                proc = subprocess.Popen(
                    cmd + args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    cwd=self._files_dir if os.path.isdir(self._files_dir) else None, env=self._env(),
                    creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
                )
            except OSError as exc:
                done(OperationResult(False, f"Could not start legendary: {exc}"))
                return
            lines: List[str] = []
            try:
                for line in _iter_output_lines(proc.stdout):
                    lines.append(line)
                proc.wait()
            except Exception:
                logger.debug("Launch watcher failed", exc_info=True)
            outcome = RunOutcome(proc.returncode, lines[-100:])
            result = self._finish(outcome, "Launch", "Fortnite started.")
            if not result.ok:
                # The whole output, so a crash's traceback reaches the FA11y log.
                logger.warning("Launching Fortnite failed: %s\n%s", result.message, "\n".join(outcome.lines))
            done(result)

        threading.Thread(target=wait, name="fortnite-launch-watch", daemon=True).start()
        return OperationResult(True, "Launching Fortnite.", data={"args": list(extra_args)})


def _copy_tree(source: str, destination: str, report: _Reporter, cancel: Optional[threading.Event]) -> bool:
    """Copy a directory tree with byte based progress. Returns False if cancelled."""
    files: List[Tuple[str, str, int]] = []
    for root, _dirs, names in os.walk(source):
        rel = os.path.relpath(root, source)
        target_dir = destination if rel == "." else os.path.join(destination, rel)
        os.makedirs(target_dir, exist_ok=True)
        for name in names:
            src = os.path.join(root, name)
            try:
                size = os.path.getsize(src)
            except OSError:
                size = 0
            files.append((src, os.path.join(target_dir, name), size))
    total = sum(f[2] for f in files) or 1
    copied = 0
    chunk = 8 * 1024 * 1024
    for src, dst, _size in files:
        with open(src, "rb") as fin, open(dst, "wb") as fout:
            while True:
                if cancel is not None and cancel.is_set():
                    return False
                data = fin.read(chunk)
                if not data:
                    break
                fout.write(data)
                copied += len(data)
                report(copied / total * 98.0, f"Copying: {format_size(copied / 1048576)} of {format_size(total / 1048576)}")
        shutil.copystat(src, dst, follow_symlinks=False)
    return True


_manager: Optional[FortniteManager] = None
_manager_lock = threading.Lock()


def get_manager() -> FortniteManager:
    """Return the process-wide FortniteManager."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = FortniteManager()
        return _manager
