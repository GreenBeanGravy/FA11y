"""A stand-in for FA11y's core, for testing FA11y.UI.exe without FA11y.

Starts the window the way the real core does (stdin and stdout pipes, --root,
--parent-pid), answers every request it makes with canned data, and logs all
traffic to a file. Signed in as "TestPlayer", Fortnite 31.10 installed, an
update to 99.0.0 available.

    python ui/tests/fake_core.py [--exe PATH] [--log FILE] [--hidden]
                                 [--close-action ask|tray|quit] [--seconds N]

While it runs it reads commands on its own stdin, one per line (the probe uses
this): summon, summon-content, show-page KEY, hide, notify TITLE|MESSAGE,
fortnite-running true|false, screenshot PATH (the window draws itself to a PNG), locker-category NAME,
social-tab HEADER (test builds only), quit. It prints "STARTED <ui pid>" when the
window process starts and "READY <ui pid>" when the window sends ui.ready.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_EXES = [
    os.path.join(REPO, "ui", "bin", "FA11y.UI.exe"),
    os.path.join(REPO, "ui", "src", "FA11y.UI", "bin", "Release", "net9.0-windows", "FA11y.UI.exe"),
    os.path.join(REPO, "ui", "src", "FA11y.UI", "bin", "Debug", "net9.0-windows", "FA11y.UI.exe"),
]


RARITIES = [("common", "Common", 1), ("uncommon", "Uncommon", 2), ("rare", "Rare", 3), ("epic", "Epic", 4),
            ("legendary", "Legendary", 5), ("marvel", "Marvel series", 6)]
COSMETIC_KINDS = ["Outfit", "Pickaxe", "Emote", "Glider", "Back Bling", "Wrap"]
CATEGORIES = ["All Cosmetics", "Outfit", "Back Bling", "Pickaxe", "Glider", "Emote", "Wrap", "Jam Track",
              "Lobby Track", "Banner"]


def fake_cosmetics(count: int = 3000) -> list:
    """Records shaped like the real locker.category answer (compact keys), one big mixed pool."""
    out = []
    for n in range(count):
        key, label, value = RARITIES[n % len(RARITIES)]
        out.append({"i": f"item_{n}", "n": f"Item {n:04d} {['Ace', 'Blaze', 'Cinder', 'Dusk'][n % 4]}",
                    "t": COSMETIC_KINDS[(n // 7) % len(COSMETIC_KINDS)], "r": label, "k": key, "v": value,
                    "s": f"C{1 + n % 6}S{1 + n % 9}", "c": str(1 + n % 6), "e": str(1 + n % 9),
                    "d": f"A canned description for item {n}.", "f": n % 97 == 0})
    return out


class FakeCore:
    def __init__(self, exe: str, root: str, log_path: str, hidden: bool, close_action: str):
        self.exe = exe
        self.root = root
        self.hidden = hidden
        self.close_action = close_action
        self.log_file = open(log_path, "w", encoding="utf-8")
        self.lock = threading.Lock()
        self.signed_in = True
        self.fortnite_running = False
        self.page = "home"
        self.proc: subprocess.Popen | None = None
        self.started = 0.0
        self.cosmetics = fake_cosmetics()
        self.favorite_friends = {"f3"}
        self.friends = [("f1", "Zed"), ("f2", "amy"), ("f3", "Bob"), ("f4", "Cy"), ("f5", "Dana")]
        self.party_leader = True

    def log(self, text: str) -> None:
        with self.lock:
            self.log_file.write(f"{time.time() - self.started:8.3f} {text}\n")
            self.log_file.flush()

    # Sending ---------------------------------------------------------------

    def send(self, message: dict) -> None:
        line = (json.dumps(message) + "\n").encode("utf-8")
        try:
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        except (OSError, ValueError):
            pass

    def event(self, name: str, data: dict | None = None) -> None:
        self.log(f"-> event {name} {data or {}}")
        self.send({"type": "event", "name": name, "data": data or {}})

    # Canned answers ----------------------------------------------------------

    def hello(self) -> dict:
        return {"version": "1.2.3", "keybinds_on": False, "open_keybind": "Left Alt + Left Shift + F",
                "fortnite_running": self.fortnite_running, "update": "99.0.0",
                "can_restart_to_update": True, "page": self.page}

    def account(self) -> dict:
        if self.signed_in:
            return {"name": "TestPlayer", "detail": "Signed in.", "signed_in": True, "valid": True}
        return {"name": "Signed out", "detail": "Sign in to use your locker, friends, quests, and Fortnite downloads.",
                "signed_in": False, "valid": False}

    def answer(self, method: str, params: dict):
        if method == "home.info":
            return {"keybinds_on": False, "open_keybind": "Left Alt + Left Shift + F",
                    "fortnite_running": self.fortnite_running, "can_restart_to_update": True,
                    "whats_new": "Version 1.2.3\n- A canned changelog entry for the test core.\n- Another line."}
        if method == "home.account":
            if self.signed_in:
                return {"value": "Signed in", "detail": "TestPlayer", "level": "ok", "name": "TestPlayer"}
            return {"value": "Signed out", "detail": "Sign in on the Epic account page", "level": "warn"}
        if method == "home.fa11y":
            return {"value": "1.2.3", "detail": "Update available: 99.0.0", "level": "warn", "update": "99.0.0"}
        if method == "home.fortnite":
            time.sleep(0.4)  # the real check runs legendary
            return {"value": "31.10", "detail": "Ready", "level": "ok"}
        if method == "account.state":
            return self.account()
        if method == "account.sign_in":
            time.sleep(0.5)
            self.signed_in = True
            return {"authenticated": True, **self.account()}
        if method == "account.sign_out":
            self.signed_in = False
            return self.account()
        if method == "about.info":
            return {"version": "1.2.3", "update": "99.0.0", "can_restart_to_update": True,
                    "changelog": "Version 1.2.3\n- A canned changelog entry.\n\n" + "Older entry.\n" * 60}
        if method == "about.check_updates":
            time.sleep(0.3)
            return {"found": True, "update": "99.0.0", "can_restart_to_update": True}
        if method.startswith("social."):
            return self.social(method, params)
        if method.startswith("locker."):
            return self.locker(method, params)
        if method == "app.close_action":
            return {"action": self.close_action}
        if method == "app.open_classic":
            return {"ok": True}
        if method == "app.state":
            return self.hello()
        return {}

    # Social ---------------------------------------------------------------------

    def social(self, method: str, params: dict):
        if method == "social.state":
            return {"available": self.signed_in}
        if method == "social.friends":
            friends = list(self.friends)
            if params.get("favorites_only"):
                friends = [f for f in friends if f[0] in self.favorite_friends]
            search = (params.get("search") or "").lower()
            friends = [f for f in friends if search in f[1].lower()]
            friends.sort(key=lambda f: (f[0] not in self.favorite_friends, f[1].lower()))
            kind = "favorite friends" if params.get("favorites_only") else "friends"
            return {"friends": [{"id": i, "name": n, "favorite": i in self.favorite_friends} for i, n in friends],
                    "summary": f"{len(friends)} {kind}" if friends else f"No {kind}"}
        if method == "social.requests":
            if params.get("incoming", True):
                rows = [{"id": "r1", "name": "Ann", "incoming": True}, {"id": "r2", "name": "Ben", "incoming": True}]
                return {"requests": rows, "summary": "2 incoming requests"}
            return {"requests": [{"id": "r3", "name": "Cat", "incoming": False}], "summary": "1 outgoing requests"}
        if method == "social.party":
            members = [{"id": "me", "name": "TestPlayer", "leader": self.party_leader, "me": True},
                       {"id": "p2", "name": "Pal", "leader": False, "me": False}]
            return {"members": members, "am_leader": self.party_leader, "summary": "2 party members"}
        if method == "social.account_info":
            return {"epic": "Username: TestPlayer\nEmail: test@example.com\nAccount ID: 0123456789abcdef",
                    "fortnite": "OVERALL CAREER STATS\nTotal Wins: 1,234\nTotal Kills: 5,678\n"
                                "Matches Played: 9,999\nK/D Ratio: 1.50\nWin Rate: 12.35%\n"
                                "Time Played: 120 minutes (2.0 hours / 0.1 days)",
                    "ranked": "Battle Royale: Gold II (40% to Gold III)\n  Peak: Platinum I"}
        if method == "social.toggle_favorite":
            fid = params.get("id")
            self.favorite_friends ^= {fid}
            return {}
        if method == "social.find_users":
            return {"status": "sent"}
        if method in ("social.accept_request", "social.promote", "social.kick"):
            return {}
        return {}

    # Locker ---------------------------------------------------------------------

    def locker(self, method: str, params: dict):
        if method == "locker.load":
            time.sleep(0.3)
            return {"available": True, "signed_in": self.signed_in, "name": "TestPlayer" if self.signed_in else "",
                    "owned_only": self.signed_in, "categories": CATEGORIES, "total": len(self.cosmetics)}
        if method == "locker.category":
            name = params.get("name", "")
            records = [r for r in self.cosmetics if name == "All Cosmetics" or r["t"] == name]
            records.sort(key=lambda r: (-r["v"], r["n"]))
            show_random = name not in ("All Cosmetics", "Emote")
            unequip = None if name == "All Cosmetics" else "Default" if name in ("Outfit", "Pickaxe") else "Empty"
            return {"name": name,
                    "options": {"random": show_random, "randomize": show_random and name in ("Jam Track", "Lobby Track"),
                                "unequip": unequip},
                    "special": {"random": "Random\n\nEquip the Random (shuffle) option for this slot.",
                                "randomize": "Randomize Track\n\nPick a random cosmetic from this list and equip it.",
                                "unequip": f"Unequip\n\nSearches for '{unequip}' to remove the cosmetic from this slot."},
                    "records": records}
        if method == "locker.toggle_favorite":
            for r in self.cosmetics:
                if r["i"] == params.get("id"):
                    r["f"] = not r["f"]
                    return {"result": "ok", "favorite": r["f"]}
            return {"result": "missing", "favorite": False}
        if method == "locker.set_owned_only":
            return {"owned_only": bool(params.get("value")), "messages": ["Enabled: Show only owned cosmetics"],
                    "expired": False, "error": None}
        if method == "locker.equip_plan":
            return {"kind": params.get("kind"), "id": params.get("id"), "name": "Item", "slot": 1}
        if method == "locker.equip":
            time.sleep(0.5)
            return {"ok": True, "name": "Item", "message": ""}
        if method == "locker.equipped":
            return {"text": "--- Character ---\n  Character: Item 0001 Blaze\n  Pickaxe: (empty)\n"}
        if method == "locker.loadouts":
            records = [{"id": 0, "name": "Starter", "label": "Starter [Character]", "local": False,
                        "detail": "Loadout: Starter\nSource: epic\nCategories: Character\n"},
                       {"id": 1, "name": "Mine", "label": "Mine [Character + Emotes]", "local": True,
                        "detail": "Loadout: Mine\nSource: local\nCategories: Character + Emotes\n"}]
            return {"status": "ok", "total": 2, "filters": ["All", "Multi-Category Only", "Character", "Emotes"],
                    "records": records}
        if method == "locker.save_choices":
            return {"choices": ["All Categories", "Character", "Emotes"]}
        return {}

    # Reading ------------------------------------------------------------------

    def serve(self, message: dict) -> None:
        method = message.get("method", "")
        params = message.get("params") or {}
        try:
            reply = {"type": "response", "id": message["id"], "ok": True, "result": self.answer(method, params)}
        except Exception as e:  # keep the test core alive
            reply = {"type": "response", "id": message["id"], "ok": False, "error": str(e)}
        self.log(f"<- request {method} {params} => {reply.get('result', reply.get('error'))}")
        self.send(reply)

    def read_loop(self) -> None:
        for raw in self.proc.stdout:
            try:
                message = json.loads(raw.decode("utf-8"))
            except ValueError:
                self.log(f"!! not JSON: {raw!r}")
                continue
            kind = message.get("type")
            if kind == "request":
                threading.Thread(target=self.serve, args=(message,), daemon=True).start()
            elif kind == "event":
                name = message.get("name")
                self.log(f"<- event {name} {message.get('data')}")
                if name == "ui.ready":
                    self.event("core.hello", self.hello())
                    print(f"READY {self.proc.pid}", flush=True)
                elif name == "ui.page":
                    self.page = message.get("data", {}).get("key", self.page)
            else:
                self.log(f"!! unexpected message {message}")
        self.log("UI closed its stdout")

    # Running --------------------------------------------------------------------

    def start(self) -> None:
        args = [self.exe, "--root", self.root, "--parent-pid", str(os.getpid())]
        if self.hidden:
            args.append("--hidden")
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 1
        self.started = time.time()
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, startupinfo=si, bufsize=0,
                                     env={**os.environ, "FA11Y_UI_TEST": "1"})
        try:
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(self.proc.pid)
        except Exception:
            pass
        self.log(f"started {args} pid {self.proc.pid}")
        print(f"STARTED {self.proc.pid}", flush=True)
        threading.Thread(target=self.read_loop, daemon=True).start()

    def command(self, line: str) -> bool:
        """Run one command from stdin. Returns False to stop."""
        parts = line.strip().split(" ", 1)
        name, rest = parts[0], parts[1] if len(parts) > 1 else ""
        if name == "summon":
            self.event("ui.summon", {"focus_content": False, "over_game": False})
        elif name == "summon-content":
            self.event("ui.summon", {"focus_content": True, "over_game": False})
        elif name == "show-page":
            self.event("ui.show_page", {"key": rest, "summon": False, "focus_sidebar": False})
        elif name == "hide":
            self.event("ui.hide")
        elif name == "notify":
            title, _, message = rest.partition("|")
            self.event("ui.notify", {"title": title, "message": message})
        elif name == "fortnite-running":
            self.fortnite_running = rest.strip().lower() == "true"
            self.event("fortnite.running", {"running": self.fortnite_running})
        elif name == "screenshot":
            self.event("test.screenshot", {"path": rest.strip()})
        elif name == "locker-category":
            self.event("test.locker_category", {"name": rest.strip()})
        elif name == "social-tab":
            self.event("test.social_tab", {"tab": rest.strip()})
        elif name == "quit":
            self.event("ui.quit")
            return False
        return True


def main() -> int:
    parser = argparse.ArgumentParser()
    existing = [p for p in DEFAULT_EXES if os.path.isfile(p)]
    # The newest build wins, so a fresh dotnet build is what gets tested.
    parser.add_argument("--exe", default=max(existing, key=os.path.getmtime) if existing else DEFAULT_EXES[0])
    parser.add_argument("--root", default=os.path.join(os.environ.get("TEMP", "."), "fa11y-ui-test-root"))
    parser.add_argument("--log", default=os.path.join(os.environ.get("TEMP", "."), "fa11y-fake-core.log"))
    parser.add_argument("--hidden", action="store_true")
    parser.add_argument("--close-action", default="tray", choices=("ask", "tray", "quit"))
    parser.add_argument("--seconds", type=float, default=0, help="stop after this long (0 = until quit or EOF)")
    args = parser.parse_args()

    os.makedirs(args.root, exist_ok=True)
    core = FakeCore(args.exe, args.root, args.log, args.hidden, args.close_action)
    core.start()
    deadline = time.time() + args.seconds if args.seconds else None

    def watch_stdin() -> None:
        for line in sys.stdin:
            if not core.command(line):
                break

    threading.Thread(target=watch_stdin, daemon=True).start()
    try:
        while core.proc.poll() is None and (deadline is None or time.time() < deadline):
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    if core.proc.poll() is None:
        try:
            core.proc.stdin.close()
            core.proc.wait(timeout=3)
        except Exception:
            core.proc.kill()
    core.log(f"UI exited with code {core.proc.returncode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
