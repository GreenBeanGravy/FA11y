"""What the running Fortnite exposes to other programs, seen from outside the game.

Uses only system-wide tables (sockets, named pipes, windows, files on disk). It never opens the
game's memory, so it is safe with Easy Anti-Cheat running.

    python tools/live_surface.py snapshot before.json   with Fortnite closed
    python tools/live_surface.py snapshot after.json    with Fortnite in the lobby
    python tools/live_surface.py diff before.json after.json
    python tools/live_surface.py now                    what the game has open right now
    python tools/live_surface.py watch [seconds]        new pipes, ports and changed files as they appear
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

import psutil

GAME_NAMES = ("fortniteclient-win64-shipping", "fortnitelauncher", "fortnite", "easyanticheat",
              "eossdk", "epicgameslauncher", "epicwebhelper")
WATCH_DIRS = [Path(os.environ.get("LOCALAPPDATA", "")) / "FortniteGame" / "Saved",
              Path(os.environ.get("LOCALAPPDATA", "")) / "EpicGamesLauncher" / "Saved"]


def game_pids() -> dict:
    out = {}
    for p in psutil.process_iter(["name", "pid"]):
        name = (p.info["name"] or "").lower()
        if name.startswith(GAME_NAMES):
            out[p.info["pid"]] = p.info["name"]
    return out


def pipes() -> list:
    try:
        return sorted(os.listdir("\\\\.\\pipe\\"))
    except OSError:
        return []


def sockets(pids: dict) -> list:
    out = []
    for c in psutil.net_connections(kind="inet"):
        if c.pid in pids:
            local = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else ""
            remote = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else ""
            kind = "udp" if c.type == 2 else "tcp"
            out.append({"proc": pids[c.pid], "kind": kind, "local": local, "remote": remote,
                        "status": c.status})
    return sorted(out, key=lambda s: (s["proc"], s["kind"], s["status"], s["local"]))


def windows(pids: dict) -> list:
    user32 = ctypes.windll.user32
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            cls = ctypes.create_unicode_buffer(256)
            title = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            user32.GetWindowTextW(hwnd, title, 256)
            out.append({"proc": pids[pid.value], "class": cls.value, "title": title.value,
                        "visible": bool(user32.IsWindowVisible(hwnd))})
        return True

    user32.EnumWindows(each, 0)
    return sorted(out, key=lambda w: (w["proc"], w["class"], w["title"]))


def files() -> dict:
    out = {}
    for root in WATCH_DIRS:
        if not root.exists():
            continue
        for dirpath, _, names in os.walk(root):
            for n in names:
                p = os.path.join(dirpath, n)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                out[p] = [st.st_size, int(st.st_mtime)]
    return out


def snapshot() -> dict:
    pids = game_pids()
    return {"time": time.time(), "processes": sorted(set(pids.values())), "pipes": pipes(),
            "sockets": sockets(pids), "windows": windows(pids), "files": files()}


def show_now(snap: dict) -> None:
    print("processes:", ", ".join(snap["processes"]) or "none")
    print("\nsockets:")
    for s in snap["sockets"]:
        print(f"  {s['proc']:40} {s['kind']} {s['status']:12} {s['local']:24} {s['remote']}")
    print("\nwindows:")
    for w in snap["windows"]:
        print(f"  {w['proc']:40} {w['class']:40} {w['title']!r} {'visible' if w['visible'] else ''}")


def diff(a: dict, b: dict) -> None:
    print("processes started:", sorted(set(b["processes"]) - set(a["processes"])))
    print("\nnew pipes:")
    for p in sorted(set(b["pipes"]) - set(a["pipes"])):
        print("  \\\\.\\pipe\\" + p)
    print("\ngame sockets (after):")
    for s in b["sockets"]:
        print(f"  {s['proc']:40} {s['kind']} {s['status']:12} {s['local']:24} {s['remote']}")
    print("\ngame windows (after):")
    for w in b["windows"]:
        print(f"  {w['proc']:40} {w['class']:40} {w['title']!r}")
    print("\nfiles created or changed:")
    for path, meta in sorted(b["files"].items()):
        if a["files"].get(path) != meta:
            print(f"  {'new' if path not in a['files'] else 'changed':8} {meta[0]:>12,}  {path}")


def watch(seconds: float) -> None:
    base = snapshot()
    seen_pipes, seen_socks = set(base["pipes"]), {json.dumps(s) for s in base["sockets"]}
    files_before = base["files"]
    print(f"watching for {seconds:.0f}s. Do things in the game now.")
    end = time.time() + seconds
    while time.time() < end:
        time.sleep(1.0)
        pids = game_pids()
        for p in pipes():
            if p not in seen_pipes:
                seen_pipes.add(p)
                print(f"[{time.strftime('%H:%M:%S')}] new pipe \\\\.\\pipe\\{p}")
        for s in sockets(pids):
            key = json.dumps(s)
            if key not in seen_socks and (s["status"] == "LISTEN" or s["kind"] == "udp"):
                seen_socks.add(key)
                print(f"[{time.strftime('%H:%M:%S')}] {s['proc']} {s['kind']} {s['status']} {s['local']} {s['remote']}")
    now_files = files()
    print("\nfiles created or changed while watching:")
    for path, meta in sorted(now_files.items()):
        if files_before.get(path) != meta:
            print(f"  {meta[0]:>12,}  {path}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "snapshot":
        Path(sys.argv[2]).write_text(json.dumps(snapshot()), encoding="utf-8")
        print("saved", sys.argv[2])
    elif cmd == "diff":
        diff(*(json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[2:4]))
    elif cmd == "now":
        show_now(snapshot())
    elif cmd == "watch":
        watch(float(sys.argv[2]) if len(sys.argv) > 2 else 120)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
