"""Stop child processes from flashing console windows.

FA11y runs under pythonw.exe, which has no console. Any console program
it starts (legendary, PowerShell, or the ``dotnet`` probe pythonnet runs
on import) then gets a console window of its own, which flashes on
screen and steals focus from the screen reader. install() makes
subprocess start children with CREATE_NO_WINDOW unless the caller asked
for a console or a detached process.
"""
from __future__ import annotations

import ctypes
import subprocess
import sys

CREATE_NEW_CONSOLE = 0x00000010
DETACHED_PROCESS = 0x00000008
CREATE_NO_WINDOW = 0x08000000


def has_console() -> bool:
    return bool(ctypes.windll.kernel32.GetConsoleWindow())


def install() -> None:
    if sys.platform != "win32" or has_console() or getattr(subprocess.Popen, "_fa11y_no_console", False):
        return
    original = subprocess.Popen.__init__

    def __init__(self, *args, creationflags=0, **kwargs):
        if not creationflags & (CREATE_NEW_CONSOLE | DETACHED_PROCESS):
            creationflags |= CREATE_NO_WINDOW
        original(self, *args, creationflags=creationflags, **kwargs)

    subprocess.Popen.__init__ = __init__
    subprocess.Popen._fa11y_no_console = True
