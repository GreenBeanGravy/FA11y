"""Send command lines to a running Fortnite through its named pipe and show what the game logged.

Fortnite must be running and started with -named_pipe (from FA11y's Play button or the Epic Games
Launcher). Each command goes as its own message; the game's reaction is read from FortniteGame.log
until the log has been quiet for --settle seconds.

    python tools/pipe_probe.py "-IslandOverride=playlist_nobuildbr_duo"
    python tools/pipe_probe.py --uilink-classes        list every UI link (MOTD action) class
    python tools/pipe_probe.py --all-lines "uilink/NavigateToTabMOTD?Tab=Locker"

Only lines from the deep-link, UI and matchmaking categories are shown unless --all-lines is given.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lib.utilities import fortnite_pipe  # noqa: E402

KEEP = re.compile(r"LogExternalApplicationCommand: .*Parsing|LogFortDeepLinks|LogFortUIDeepLinking|LogFortUI:|"
                  r"Motd|MOTD|Prm|MatchmakingLog|LogFortIslandOverride|Deep ?[Ll]ink|UILink", re.I)
NOISE = re.compile(r"\] Called$|Pipe Init|Platform Id was not found|Disabling Sleep Mode")

# A UI link naming a class that doesn't exist makes the game log every class it does know.
UILINK_CLASS_PROBES = [
    "uilink/FA11yProbe?probe=1",
    "-uilink=uilink/FA11yProbe?probe=1",
    "-uilink=FA11yProbe?probe=1",
]


def send(path: str, command: str) -> None:
    with open(path, "wb", buffering=0) as pipe:
        pipe.write(f"    {command}\0".encode("utf-16-le"))


def read_new(start: int, settle: float, timeout: float) -> str:
    """Log text written after start, once nothing new has arrived for settle seconds."""
    text, last_size, quiet_since = "", start, time.monotonic()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.1)
        size = os.path.getsize(fortnite_pipe.LOG)
        if size != last_size:
            last_size, quiet_since = size, time.monotonic()
        elif size > start and time.monotonic() - quiet_since >= settle:
            break
    with open(fortnite_pipe.LOG, "r", encoding="utf-8", errors="replace") as f:
        f.seek(start)
        text = f.read()
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("commands", nargs="*")
    ap.add_argument("--uilink-classes", action="store_true", help="probe for the list of UI link classes")
    ap.add_argument("--all-lines", action="store_true", help="show every new log line")
    ap.add_argument("--settle", type=float, default=0.8)
    ap.add_argument("--timeout", type=float, default=6.0)
    args = ap.parse_args()

    path = fortnite_pipe.pipe_path()
    if path is None:
        print("Fortnite isn't running with -named_pipe. Start it from FA11y's Play button.")
        return 1
    commands = list(args.commands) + (UILINK_CLASS_PROBES if args.uilink_classes else [])
    if not commands:
        ap.print_help()
        return 1
    classes = set()
    for command in commands:
        start = os.path.getsize(fortnite_pipe.LOG)
        send(path, command)
        text = read_new(start, args.settle, args.timeout)
        print(f"===== {command}")
        for line in text.splitlines():
            if args.all_lines or (KEEP.search(line) and not NOISE.search(line)):
                print("  " + line[30:400])
            found = re.search(r"Available classes: (.*)", line)
            if found:
                classes.update(c.strip() for c in found.group(1).split(",") if c.strip())
    if classes:
        print("\n===== UI link classes")
        for name in sorted(classes):
            print("  " + name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
