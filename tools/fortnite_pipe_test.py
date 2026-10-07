"""Send a deep-link command to the running Fortnite, the way the Epic Games Launcher does.

The game opens a named pipe, \\\\.\\pipe\\<accountId>\\Fortnite, when it's started with
-named_pipe=<accountId>\\Fortnite. The launcher passes island links through it as plain command
line text, for example "-IslandOverride=8765-4125-9209". The game logs what it gets under
LogExternalApplicationCommand in FortniteGame.log.

    python tools/fortnite_pipe_test.py 8765-4125-9209 [utf8|utf16] [none|qbytes|qchars|ibytes|ichars]

The account ID comes from the running game's command line.
"""
from __future__ import annotations

import os
import re
import sys
import time

import psutil

LOG = os.path.join(os.environ["LOCALAPPDATA"], "FortniteGame", "Saved", "Logs", "FortniteGame.log")


def pipe_name() -> str:
    for proc in psutil.process_iter(["name", "cmdline"]):
        if (proc.info["name"] or "").lower().startswith("fortniteclient-win64-shipping"):
            for arg in proc.info["cmdline"] or []:
                match = re.match(r"-named_pipe=(.+)", arg)
                if match:
                    return r"\\.\pipe" + "\\" + match.group(1)
    sys.exit("Fortnite isn't running, or wasn't started with -named_pipe.")


def log_size() -> int:
    try:
        return os.path.getsize(LOG)
    except OSError:
        return 0


def new_log_lines(start: int) -> list[str]:
    with open(LOG, "r", encoding="utf-8", errors="replace") as f:
        f.seek(start)
        return [line.rstrip() for line in f
                if "LogExternalApplicationCommand" in line or "LogFortDeepLinks" in line
                or "Deep Action" in line or "Link id changing" in line]


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    link = sys.argv[1]
    encoding = sys.argv[2] if len(sys.argv) > 2 else "utf8"
    message = f"-IslandOverride={link}"
    # The game reads UTF-16 text into a reused buffer; the null ends it so no earlier text is left over.
    data = (message + "\0").encode("utf-16-le" if encoding == "utf16" else "utf-8")
    header = sys.argv[3] if len(sys.argv) > 3 else "none"
    import struct
    if header == "qbytes":
        data = struct.pack("<Q", len(data)) + data
    elif header == "qchars":
        data = struct.pack("<Q", len(data) // 2) + data
    elif header == "ibytes":
        data = struct.pack("<II", len(data), 0) + data
    elif header == "ff":
        data = b"\xff" * 8 + data
    elif header == "spaces":
        data = " ".encode("utf-16-le") * 4 + data
    elif header.startswith("q="):
        data = struct.pack("<Q", int(header[2:])) + data
    elif header == "ichars":
        data = struct.pack("<II", len(data) // 2, 0) + data
    name = pipe_name()
    start = log_size()
    print(f"Sending {message!r} as {encoding} to {name}")
    with open(name, "wb", buffering=0) as pipe:
        pipe.write(data)
    time.sleep(2)
    lines = new_log_lines(start)
    print("\n".join(lines) if lines else "The game logged nothing for it.")


if __name__ == "__main__":
    main()
