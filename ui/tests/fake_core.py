"""A stand-in for FA11y's core, for testing FA11y.UI.exe without FA11y.

Starts the window the way the real core does (stdin and stdout pipes, --root,
--parent-pid), answers every request it makes with canned data, and logs all
traffic to a file. Signed in as "TestPlayer", Fortnite 31.10 installed, an
update to 99.0.0 available.

    python ui/tests/fake_core.py [--exe PATH] [--log FILE] [--hidden]
                                 [--close-action ask|tray|quit] [--seconds N]
                                 [--first-run] [--fortnite installed|none|egl] [--startup SECONDS]

While it runs it reads commands on its own stdin, one per line (the probe uses
this): summon, summon-content, show-page KEY, hide, notify TITLE|MESSAGE,
fortnite-running true|false, fortnite-state installed|none|egl, start-setup,
screenshot PATH (the window draws itself to a PNG), locker-category NAME,
social-tab HEADER, key NAME [mods=Control,Shift] [held=LeftShift] (press a key
in the focused control; test builds only), quit. It prints "STARTED <ui pid>" when the
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
    def __init__(self, exe: str, root: str, log_path: str, hidden: bool, close_action: str,
                 first_run: bool = False, fortnite: str = "installed", startup: float = 0):
        self.exe = exe
        self.root = root
        self.hidden = hidden
        self.close_action = close_action
        self.log_file = open(log_path, "w", encoding="utf-8")
        self.lock = threading.Lock()
        self.signed_in = True
        self.fortnite_running = False
        self.page = "home"
        self.setup = first_run
        self.fortnite = fortnite
        self.startup = startup  # seconds the pretend startup takes (0: already started)
        self.startup_state = {"percent": 0, "message": "Loading settings"}
        self.operation = None  # {"id", "cancel": Event}
        self.next_operation = 0
        self.pages = None  # Discover, Quests and passes answers (fake_pages.py)
        self.proc: subprocess.Popen | None = None
        self.started = 0.0
        self.cosmetics = fake_cosmetics()
        self.favorite_friends = {"f3"}
        self.friends = [("f1", "Zed"), ("f2", "amy"), ("f3", "Bob"), ("f4", "Cy"), ("f5", "Dana")]
        self.party_leader = True
        self.handlers = self.real_handlers(root)

    @staticmethod
    def real_handlers(root: str) -> dict:
        """The core's own Settings and Keybinds handlers, running on a scratch config.txt (the default
        config) so the real schema and saving are what the window is tested against."""
        sys.path.insert(0, REPO)
        os.chdir(REPO)
        from lib.shell.handlers import settings as settings_handlers
        from lib.shell.bridge import registry
        from lib.utilities import utilities
        utilities.CONFIG_FILE = os.path.join(root, "config.txt")
        utilities.ensure_config_dir = lambda: None
        utilities.migrate_config_files = lambda: None
        if os.path.exists(utilities.CONFIG_FILE):
            os.remove(utilities.CONFIG_FILE)
        utilities.clear_config_cache()
        settings_handlers._schedule_reload = lambda parser: None
        settings_handlers._tester.play = lambda *args, **kwargs: None
        return registry.handlers

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
                "can_restart_to_update": True, "page": self.page, "setup": self.setup,
                "starting": self.startup > 0 and not self.setup, "startup": dict(self.startup_state)}

    def fortnite_state(self, check: bool) -> dict:
        base = {"checked": True, "legendary_ok": True, "default_install_base": "C:\\Program Files\\Epic Games",
                "running": self.fortnite_running, "operation": None, "remote_version": "", "install_path": ""}
        if self.fortnite == "installed":
            state = {**base, "summary": "31.10 \u00b7 managed by FA11y \u00b7 D:\\Fortnite \u00b7 60 GB",
                     "installed": True, "egl_only": False, "show_signin": False, "show_install": False,
                     "update_available": False, "egl_text": "", "install_path": "D:\\Fortnite"}
        elif self.fortnite == "egl":
            state = {**base, "summary": "Installed through the Epic Games Launcher.", "installed": False,
                     "egl_only": True, "show_signin": True, "show_install": False, "update_available": False,
                     "egl_text": "Fortnite is installed through the Epic Games Launcher at C:\\EGL\\Fortnite, version 30.00."}
        else:
            state = {**base, "summary": "Fortnite isn't installed.", "installed": False, "egl_only": False,
                     "show_signin": False, "show_install": True, "update_available": False, "egl_text": ""}
        if check:
            state["message"] = "Fortnite is up to date."
        if self.operation is not None:
            state["operation"] = {"id": self.operation["id"], "name": "Verifying", "percent": 50.0,
                                  "message": "Verifying files 50%"}
        return state

    def run_operation(self, name: str) -> dict:
        """A pretend long operation: three progress events, then finished (or cancelled)."""
        self.next_operation += 1
        op = {"id": self.next_operation, "cancel": threading.Event()}
        self.operation = op

        def work() -> None:
            for percent in (25.0, 50.0, 75.0):
                if op["cancel"].wait(0.5):
                    break
                self.event("operation.progress", {"id": op["id"], "percent": percent,
                                                  "message": f"{name} files {percent:.0f}%"})
            cancelled = op["cancel"].is_set()
            self.operation = None
            self.event("operation.finished", {"id": op["id"], "ok": not cancelled,
                                              "message": f"{name} cancelled." if cancelled else f"{name} finished.",
                                              "cancelled": cancelled})
        threading.Thread(target=work, daemon=True).start()
        return {"id": op["id"], "name": name}

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
        if method == "about.branches":
            return {"current": "overhaul", "can_switch": True, "branches": [
                {"name": "main", "label": "Stable", "description": "The tested release most people use."},
                {"name": "overhaul", "label": "Beta",
                 "description": "New FA11y window and early features, with more rough edges."}]}
        if method == "about.switch_branch":
            return {}
        if method == "about.check_updates":
            time.sleep(0.3)
            return {"found": True, "update": "99.0.0", "can_restart_to_update": True}
        if method == "fortnite.state":
            return self.fortnite_state(bool(params.get("check_updates")))
        if method in ("fortnite.install", "fortnite.update", "fortnite.verify", "fortnite.move",
                      "fortnite.uninstall", "fortnite.import_egl", "fortnite.egl_sync"):
            names = {"install": "Installing", "update": "Updating", "verify": "Verifying", "move": "Moving",
                     "uninstall": "Uninstalling", "import_egl": "Setting up", "egl_sync": "Syncing"}
            return self.run_operation(names[method.split(".")[1]])
        if method == "fortnite.cancel":
            if self.operation is not None:
                self.operation["cancel"].set()
            return {"cancelling": True}
        if method == "fortnite.install_question":
            return {"question": f"Install Fortnite in {params.get('base')}\\Fortnite? It needs about 100 GB (500 GB free)."}
        if method == "fortnite.launch_options":
            return {"api": "dx12", "skip_splash": True, "extra": "-nosound",
                    "choices": [{"key": "default", "label": "Default"}]}
        if method == "fortnite.game_check":
            return {"checks": [
                {"name": "Window mode", "status": "problem", "detail": "Windowed", "fix": "Set Window Mode to Fullscreen in Fortnite's display settings.",
                 "text": "Window mode: Windowed. Problem. Set Window Mode to Fullscreen in Fortnite's display settings."},
                {"name": "Game resolution", "status": "ok", "detail": "1920 by 1080", "fix": "", "text": "Game resolution: 1920 by 1080. OK."},
                {"name": "Screen resolution", "status": "ok", "detail": "1920 by 1080", "fix": "", "text": "Screen resolution: 1920 by 1080. OK."},
                {"name": "FakerInput driver", "status": "ok", "detail": "Connected", "fix": "", "text": "FakerInput driver: Connected. OK."},
            ]}
        if method == "fortnite.mouse":
            return {"available": True, "text": "No mouse selected for passthrough.", "detected": False}
        if method == "fortnite.detect_mouse":
            def found() -> None:
                time.sleep(0.6)
                self.event("fortnite.mouse_detected", {"available": True, "text": "Using the Test Mouse.",
                                                       "detected": True, "found": True})
            threading.Thread(target=found, daemon=True).start()
            return {"text": "Move the mouse you play with now."}
        if method == "fortnite.sign_in":
            return {"ok": True, "needs_account": False, "message": "Signed in to Fortnite downloads."}
        if method == "setup.signin_state":
            return {"signed_in": self.signed_in, "text": f"Signed in as TestPlayer." if self.signed_in else "Not signed in."}
        if method == "setup.fortnite":
            if self.fortnite == "egl":
                return {"message": "Fortnite is installed through the Epic Games Launcher at C:\\EGL\\Fortnite.",
                        "offer_choice": True}
            return {"message": "Fortnite isn't installed. After setup, open the Fortnite page to install it. "
                               "It needs about 100 GB.", "offer_choice": False}
        if method == "setup.test_sound":
            return {"message": None}
        if method == "setup.finish":
            self.setup = False
            return {"saved": True}
        if method == "app.start_setup":
            self.setup = True
            self.event("setup.start", {"summon": True})
            return {}
        if method.startswith("social."):
            return self.social(method, params)
        if method.startswith("locker."):
            return self.locker(method, params)
        # The window's own requests, answered the way the real core does.
        if method == "app.summon":
            self.event("ui.summon", {"focus_content": bool(params.get("focus_content")), "over_game": False})
            return {}
        if method == "app.show_page":
            self.event("ui.show_page", {"key": params.get("key", ""), "summon": bool(params.get("summon")),
                                        "focus_sidebar": False})
            return {}
        if method == "app.minimize_action":
            return {"to_tray": True}
        if method == "app.window_hidden":
            self.event("ui.notify", {"title": "", "message": "Running in the background. "
                                                            "Press Left Alt + Left Shift + F to open."})
            return {}
        if method == "app.quit":
            self.event("ui.quit")
            return {}
        if method == "app.close_action":
            return {"action": self.close_action}
        if method == "app.state":
            return self.hello()
        if method.startswith(("settings.", "keybinds.")) and method in self.handlers:
            return self.handlers[method](params)
        if method.startswith(("discover.", "quests.", "passes.")):
            from fake_pages import Pages
            with self.lock:
                if self.pages is None:
                    self.pages = Pages()
            return self.pages.answer(method, params, self.signed_in)
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
        if method == "social.horde_rank":
            return {"text": "Current Horde rank: Rank 3\nCurrent benefits:\nExtra starting shield.\n"
                            "Next: Rank 4\nProgress: 1,200 of 2,000 Horde eliminations.\n800 more needed.\n"
                            "Source: Epic account API. Refresh Account Information after a match to update."}
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
                    if self.startup > 0 and not self.setup:
                        threading.Thread(target=self.run_startup, daemon=True).start()
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

    def run_startup(self) -> None:
        """Five progress steps spread over the startup time, then startup.done."""
        steps = [(10, "Loading settings"), (30, "Starting keybinds"), (55, "Starting game monitors"),
                 (75, "Loading map data"), (90, "Signing in to Epic Games")]
        for percent, message in steps:
            self.startup_state = {"percent": percent, "message": message}
            self.event("startup.progress", self.startup_state)
            time.sleep(self.startup / len(steps))
        self.startup = 0
        self.event("startup.done")

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
        elif name == "fortnite-state":
            self.fortnite = rest.strip()
            self.event("fortnite.changed")
        elif name == "start-setup":
            self.setup = True
            self.event("setup.start", {"summon": True})
        elif name == "fortnite-running":
            self.fortnite_running = rest.strip().lower() == "true"
            self.event("fortnite.running", {"running": self.fortnite_running})
        elif name == "screenshot":
            self.event("test.screenshot", {"path": rest.strip()})
        elif name == "locker-category":
            self.event("test.locker_category", {"name": rest.strip()})
        elif name == "social-tab":
            self.event("test.social_tab", {"tab": rest.strip()})
        elif name == "where":
            self.event("test.where")  # the window answers with a test.focused event
        elif name == "key":
            # A key press in whatever has focus, for tests without the foreground (WPF key names: Enter, F9, ...).
            words = rest.split()
            extra = dict(w.split("=", 1) for w in words[1:] if "=" in w)  # mods=Control,Shift held=LeftShift
            data = {"key": words[0] if words else "", "mods": extra.get("mods", ""), "held": extra.get("held", "")}
            self.event("test.key", {**data, "up": False})
            self.event("test.key", {**data, "up": True})
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
    parser.add_argument("--first-run", action="store_true", help="start with first-run setup showing")
    parser.add_argument("--fortnite", default="installed", choices=("installed", "none", "egl"))
    parser.add_argument("--close-action", default="tray", choices=("ask", "tray", "quit"))
    parser.add_argument("--startup", type=float, default=0, help="start with the startup screen, taking this many seconds")
    parser.add_argument("--seconds", type=float, default=0, help="stop after this long (0 = until quit or EOF)")
    args = parser.parse_args()

    os.makedirs(args.root, exist_ok=True)
    core = FakeCore(args.exe, args.root, args.log, args.hidden, args.close_action, args.first_run, args.fortnite, args.startup)
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
