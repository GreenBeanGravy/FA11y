"""Try changing the selected game mode through Epic's party service, with no screen reading.

Fortnite keeps each party member's chosen mode in their member data, under
Default:MatchmakingInfo_j -> MatchmakingInfo.islandSelection.island (JSON stored as a string)
with a LinkId (an island code like 1234-5678-9012, or a playlist like playlist_defaultsquad)
and a timestamp. This script reads that, changes the LinkId, and then watches whether the game
keeps the change or puts its own back.

Run it with Fortnite open in the lobby:
    python tools/party_mode_test.py

You sign in through your browser and paste the code it shows. The sign-in stays in this script's
memory only and is ended when the script quits. FA11y's own saved sign-in is not touched.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import webbrowser
from datetime import datetime, timezone

import requests

CLIENT_ID = "ec684b8c687f479fadea3cb2ad83f5c6"
CLIENT_SECRET = "e1f31c211f28413186262d37a13fc84d"
TOKEN_URL = "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/token"
KILL_URL = "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/sessions/kill/"
PARTY_BASE = "https://party-service-prod.ol.epicgames.com/party/api/v1/Fortnite"
AUTH_URL = f"https://www.epicgames.com/id/api/redirect?clientId={CLIENT_ID}&responseType=code"
DISCOVERY = "https://fn-service-discovery-live-public.ogs.live.on.epicgames.com/api/v1/links/queue"
KEY = "Default:MatchmakingInfo_j"
DUMP_DIR = "party_mode_test"


def sign_in() -> tuple[str, str, str]:
    print("Your browser opens Epic's sign-in page. After signing in it shows a short text with")
    print('"authorizationCode". Copy the code (or the whole text) and paste it here.')
    print(f"If the browser doesn't open, go to: {AUTH_URL}")
    webbrowser.open(AUTH_URL)
    raw = input("Code: ").strip()
    code = raw
    if raw.startswith("{"):
        try:
            code = json.loads(raw).get("authorizationCode") or ""
        except ValueError:
            pass
    code = code.strip().strip('"')
    basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    r = requests.post(TOKEN_URL, headers={"Authorization": f"Basic {basic}"},
                      data={"grant_type": "authorization_code", "code": code, "token_type": "eg1"}, timeout=30)
    if r.status_code != 200:
        sys.exit(f"Sign-in failed ({r.status_code}): {r.text[:300]}")
    data = r.json()
    print(f"Signed in as {data.get('displayName')}.")
    return data["access_token"], data["account_id"], data.get("displayName", "")


class Party:
    def __init__(self, token: str, account_id: str):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.account_id = account_id
        self.raw: dict = {}

    def refresh(self) -> bool:
        r = self.session.get(f"{PARTY_BASE}/user/{self.account_id}", timeout=15)
        r.raise_for_status()
        current = r.json().get("current") or []
        self.raw = current[0] if current else {}
        return bool(self.raw)

    @property
    def me(self) -> dict:
        return next((m for m in self.raw.get("members", []) if m.get("account_id") == self.account_id), {})

    def info(self) -> dict:
        """MatchmakingInfo from my member data, with island decoded."""
        value = (self.me.get("meta") or {}).get(KEY)
        if not value:
            return {}
        return json.loads(value).get("MatchmakingInfo", {})

    def link_id(self) -> str:
        try:
            return json.loads(self.info()["islandSelection"]["island"]).get("LinkId", "")
        except (KeyError, ValueError, TypeError):
            return ""

    def set_link(self, link: str) -> requests.Response:
        info = self.info()
        if not info:
            raise RuntimeError(f"Your member data has no {KEY}. Use 'dump' and share the file.")
        island = json.loads(info["islandSelection"]["island"])
        island["LinkId"] = link
        sizes = island.get("MatchmakingSettingsV2")
        if isinstance(sizes, dict):
            for word, size in (("solo", "Solo"), ("duo", "Duo"), ("trio", "Trio"), ("squad", "Squad")):
                if word in link.lower():
                    sizes["/Fortnite.com/BattleRoyale/Matchmaking:TeamSize"] = size
        info["islandSelection"]["island"] = json.dumps(island)
        info["islandSelection"]["timestamp"] = int(datetime.now(timezone.utc).timestamp())
        body = {"delete": [], "revision": self.me.get("revision", 0),
                "update": {KEY: json.dumps({"MatchmakingInfo": info})}}
        url = f"{PARTY_BASE}/parties/{self.raw['id']}/members/{self.account_id}/meta"
        return self.session.patch(url, json=body, timeout=15)

    def dump(self, label: str) -> str:
        os.makedirs(DUMP_DIR, exist_ok=True)
        path = os.path.join(DUMP_DIR, f"{datetime.now():%H%M%S}_{label}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.raw, f, indent=2)
        return path


def watch(party: Party, wanted: str, seconds: int = 15) -> None:
    """Report whether the change stays, or the game writes its own choice back."""
    print(f"Watching for {seconds} seconds. Check whether the lobby in Fortnite changed.")
    last = None
    for _ in range(seconds):
        time.sleep(1)
        try:
            party.refresh()
        except requests.RequestException as e:
            print(f"  Couldn't read the party: {e}")
            continue
        now = party.link_id()
        if now != last:
            state = "still ours" if now == wanted else "CHANGED BACK by something else"
            print(f"  LinkId is {now} ({state}), member revision {party.me.get('revision')}")
            last = now


def main() -> None:
    token, account_id, _ = sign_in()
    party = Party(token, account_id)
    try:
        if not party.refresh():
            sys.exit("You aren't in a party. Open Fortnite and wait for the lobby first.")
        print(f"Party {party.raw['id']}, {len(party.raw.get('members', []))} member(s).")
        print(f"Your current LinkId: {party.link_id() or '(none)'}")
        print("Commands: a link to set in your party data (island code or playlist, e.g. playlist_defaultsquad),")
        print("  queue CODE (Discovery's link queue, maybe what fortnite.com's Play button uses),")
        print("  queuelist, show, dump, or quit.")
        while True:
            command = input("> ").strip()
            if not command:
                continue
            if command.lower() in ("q", "quit", "exit"):
                break
            if command.lower() == "queuelist":
                r = party.session.get(f"{DISCOVERY}/{account_id}", timeout=15)
                print(f"{r.status_code}: {r.text[:1500]}")
                continue
            if command.lower().startswith("queue "):
                link = command[6:].strip()
                r = party.session.post(f"{DISCOVERY}/{account_id}/{link}", timeout=15)
                print(f"{r.status_code}: {r.text[:1500]}")
                print("Check whether Fortnite selected it or showed anything.")
                continue
            party.refresh()
            if command.lower() == "show":
                print(f"LinkId: {party.link_id()}, member revision {party.me.get('revision')}")
                print(json.dumps(party.info(), indent=2)[:2000])
                continue
            if command.lower() == "dump":
                print(f"Saved the whole party to {party.dump('party')}")
                continue
            before = party.dump("before")
            r = party.set_link(command)
            if r.status_code == 409 or "stale_revision" in r.text:
                party.refresh()
                r = party.set_link(command)
            if r.status_code in (200, 204):
                print(f"Sent. Party saved before the change to {before}.")
                watch(party, command)
                print(f"Party now saved to {party.dump('after')}")
            else:
                print(f"The party service refused it ({r.status_code}): {r.text[:500]}")
    finally:
        try:
            requests.delete(KILL_URL + token, headers={"Authorization": f"Bearer {token}"}, timeout=10)
            print("Signed out of this test session.")
        except requests.RequestException:
            pass


if __name__ == "__main__":
    main()
