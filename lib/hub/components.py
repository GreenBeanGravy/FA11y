"""Runtimes and drivers FA11y needs that aren't part of its own files.

The updater installs them (Updater.exe --components, one UAC prompt for all of them). FA11y checks
for them once it has started, tells the user what is missing and why, and runs the updater to put
them in. When they install, FA11y restarts so they take effect.
"""
from __future__ import annotations

import glob
import logging
import os
import subprocess
import threading
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Updater.exe --components exit codes.
INSTALLED = 0
STILL_MISSING = 5

# Remembers what the user declined, so a refused UAC prompt isn't asked again on every start.
DECLINED_FILE = ".components_declined"


def _dotnet_has(framework: str, min_major: int) -> bool:
    """True when %ProgramFiles%\\dotnet has the shared framework at min_major or newer."""
    root = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "dotnet", "shared", framework)
    for path in glob.glob(os.path.join(root, "*")):
        try:
            if int(os.path.basename(path).split(".")[0]) >= min_major:
                return True
        except ValueError:
            continue
    return False


def _fakerinput_installed() -> bool:
    import winreg
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    for root, flags in ((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
                        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
                        (winreg.HKEY_CURRENT_USER, 0)):
        try:
            with winreg.OpenKey(root, key_path, 0, winreg.KEY_READ | flags) as key:
                for index in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        with winreg.OpenKey(key, winreg.EnumKey(key, index)) as sub:
                            name = winreg.QueryValueEx(sub, "DisplayName")[0]
                    except OSError:
                        continue
                    if "fakerinput" in str(name).lower():
                        return True
        except OSError:
            continue
    return False


# (name, what it's for, check). The window needs .NET 9 or newer (FA11y.UI rolls forward to newer
# major versions); mouse passthrough needs .NET 8 or newer and the FakerInput driver.
CHECKS: Tuple[Tuple[str, str, Callable[[], bool]], ...] = (
    (".NET Desktop Runtime", "the FA11y window", lambda: _dotnet_has("Microsoft.WindowsDesktop.App", 9)),
    (".NET Runtime", "mouse passthrough", lambda: _dotnet_has("Microsoft.NETCore.App", 8)),
    ("FakerInput driver", "mouse passthrough", _fakerinput_installed),
)


def missing() -> List[Tuple[str, str]]:
    """(name, what it's for) for each missing component."""
    found = []
    for name, purpose, check in CHECKS:
        try:
            ok = check()
        except Exception:
            logger.exception("Checking for %s failed", name)
            ok = True  # don't prompt on a check that can't run
        if not ok:
            found.append((name, purpose))
    return found


def join_names(names: List[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def describe(items: List[Tuple[str, str]]) -> str:
    """'the .NET Runtime and FakerInput driver, used by mouse passthrough'."""
    purposes = []
    for _, purpose in items:
        if purpose not in purposes:
            purposes.append(purpose)
    return f"the {join_names([n for n, _ in items])}, used by {join_names(purposes)}"


def updater_path() -> Optional[str]:
    """Updater.exe in the install folder (the one holding FA11y Files), or None."""
    from lib.hub.status import launcher_path
    folders = []
    launcher = launcher_path()
    if launcher:
        folders.append(os.path.dirname(launcher))
    folders.append(os.path.dirname(os.path.abspath(os.getcwd())))
    for folder in folders:
        path = os.path.join(folder, "Updater.exe")
        if os.path.isfile(path):
            return path
    return None


def _declined() -> set:
    try:
        with open(DECLINED_FILE, encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    except OSError:
        return set()


def _set_declined(names) -> None:
    try:
        if names:
            with open(DECLINED_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(names)) + "\n")
        elif os.path.exists(DECLINED_FILE):
            os.remove(DECLINED_FILE)
    except OSError:
        logger.exception("Could not save the declined components")


def install(speak: Callable[[str], None], restart: Callable[[], None], ask_again: bool = False) -> None:
    """Install what's missing through the updater, saying what happens. Run from a worker thread.

    ask_again also asks for components the user declined before.
    """
    items = missing()
    if not items:
        _set_declined(set())
        return
    names = {n for n, _ in items}
    if not ask_again and names <= _declined():
        logger.info("Missing components were declined before: %s", sorted(names))
        return
    what = describe(items)
    updater = updater_path()
    if updater is None:
        speak(f"FA11y needs {what}. Run Updater.exe in the FA11y folder to install them.")
        return
    speak(f"FA11y needs {what}. Installing now. Windows will ask for permission.")
    try:
        code = subprocess.run([updater, "--components", "--window"], cwd=os.path.dirname(updater)).returncode
    except OSError as e:
        logger.error(f"Could not start the updater: {e}")
        speak(f"Couldn't start the updater. Run Updater.exe in the FA11y folder to install {what}.")
        return
    still = missing()
    if not still:
        _set_declined(set())
        speak("Installed. Restarting FA11y so it can use them.")
        restart()
        return
    if code not in (INSTALLED, STILL_MISSING):
        # An updater from before --components existed. It updates itself the next time FA11y updates.
        logger.warning(f"Updater.exe --components exited with code {code}")
        speak(f"FA11y couldn't install {describe(still)}. Run Updater.exe in the FA11y folder to install them.")
        return
    _set_declined({n for n, _ in still})
    verb = "wasn't" if len(still) == 1 else "weren't"
    speak(f"The {join_names([n for n, _ in still])} {verb} installed. Some features won't work until you run "
          "Updater.exe in the FA11y folder and allow it.")


def install_in_background(speak: Callable[[str], None], restart: Callable[[], None]) -> None:
    threading.Thread(target=install, args=(speak, restart), name="Components", daemon=True).start()
