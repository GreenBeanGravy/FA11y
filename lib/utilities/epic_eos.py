"""Epic's EOS party service: the one Fortnite itself uses for parties.

The old party service (party-service-prod) no longer carries Fortnite's parties. The game talks
to Epic Parties under api.epicgames.dev with an EAS token, and so does this module. Everything
here works without the game's interface: accepting an invite or a join request takes effect in
the running game about a second and a half later, with no sidebar or popup.

The EAS token is minted from FA11y's own sign-in through a one-time exchange code. FA11y's token
is never refreshed from here: refresh tokens rotate, so a second refresher would sign FA11y out.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

DEPLOYMENT_ID = "62a9473a2dca46b29ccf17577fcf42d7"  # Fortnite's EOS deployment
EOS_BASE = "https://api.epicgames.dev"
TOKEN_URL = f"{EOS_BASE}/epic/oauth/v2/token"
PARTY_BASE = f"{EOS_BASE}/epic/party/internal"
TIMEOUT = 10


class EosError(Exception):
    """An EOS call failed. The message is short enough to speak."""


def parse_time(text: str) -> Optional[datetime]:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


class EosSession:
    """An EAS token for FA11y's signed-in account, minted when needed and reused until it expires."""

    def __init__(self, auth):
        self.auth = auth
        self._token: Optional[str] = None
        self._expires = 0.0
        self._lock = threading.Lock()

    @property
    def account_id(self) -> Optional[str]:
        return self.auth.account_id if self.auth else None

    def token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._expires:
                return self._token
            if not (self.auth and self.auth.access_token and self.auth.is_valid):
                raise EosError("Sign in on the Epic account page first.")
            code = self.auth.get_exchange_code()
            if not code:
                raise EosError("Couldn't reach Epic. Try again in a moment.")
            response = requests.post(
                TOKEN_URL,
                auth=(self.auth.CLIENT_ID, self.auth.CLIENT_SECRET),
                data={"grant_type": "exchange_code", "exchange_code": code, "deployment_id": DEPLOYMENT_ID},
                timeout=TIMEOUT,
            )
            if not response.ok:
                logger.error(f"EAS token request failed: {response.status_code}")
                raise EosError("Couldn't reach Epic. Try again in a moment.")
            data = response.json()
            self._token = data["access_token"]
            self._expires = time.time() + max(60, int(data.get("expires_in", 3600)) - 120)
            return self._token

    def forget_token(self) -> None:
        with self._lock:
            self._token = None

    def request(self, method: str, url: str, json=None, timeout: float = TIMEOUT) -> requests.Response:
        """Call an EOS service. A 401 mints a new token and tries once more."""
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {self.token()}"}
            response = requests.request(method, url, headers=headers, json=json, timeout=timeout)
            if response.status_code != 401 or attempt:
                return response
            self.forget_token()
        return response


@dataclass
class PartyInfo:
    id: str
    leader_id: str
    member_ids: List[str]
    chat_conversation_id: str = ""
    members: List[dict] = field(default_factory=list)


@dataclass
class EosInvite:
    """Someone invited us to their party."""
    party_id: str
    inviter_id: str
    inviter_name: str = ""
    sent_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


@dataclass
class EosJoinRequest:
    """Someone asked to join our party."""
    requester_id: str
    requester_name: str = ""
    sent_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


@dataclass
class PartyState:
    party: Optional[PartyInfo]
    invites: List[EosInvite]
    join_requests: List[EosJoinRequest]


def _invite_name(invite: dict) -> str:
    meta = invite.get("meta") or {}
    for key in ("inviter_dn", "sent_by_dn", "urn:epic:inviter:dn_s", "urn:epic:member:dn_s"):
        value = invite.get(key) or meta.get(key)
        if value:
            return str(value)
    return ""


def parse_party_state(data: dict) -> PartyState:
    """Read GET /v2/users/{me}: the current party, invites to us and requests to join us."""
    party = None
    current = data.get("current")
    if isinstance(current, list):
        current = current[0] if current else None
    if current:
        members = current.get("members") or []
        party = PartyInfo(
            id=current.get("id", ""),
            leader_id=current.get("party_lead", ""),
            member_ids=[m.get("account_id", "") for m in members if m.get("account_id")],
            chat_conversation_id=current.get("chat_conversation_id", ""),
            members=members,
        )
    invites = []
    for invite in data.get("invites") or []:
        inviter = invite.get("sent_by") or invite.get("inviter_id") or invite.get("inviter") or ""
        party_id = invite.get("party_id") or invite.get("partyId") or ""
        if inviter and party_id:
            invites.append(EosInvite(party_id, inviter, _invite_name(invite),
                                     parse_time(invite.get("sent_at", "")), parse_time(invite.get("expires_at", ""))))
    join_requests = []
    for request in data.get("join_requests") or []:
        requester = request.get("requester_id", "")
        if requester:
            join_requests.append(EosJoinRequest(requester, request.get("requester_dn", ""),
                                                parse_time(request.get("sent_at", "")),
                                                parse_time(request.get("expires_at", ""))))
    return PartyState(party, invites, join_requests)


def game_connection(members: List[dict], account_id: str) -> Optional[dict]:
    """The running game's connection in a party record, in the shape a join request sends."""
    for member in members:
        if member.get("account_id") != account_id:
            continue
        for connection in member.get("connections") or []:
            if (connection.get("meta") or {}).get("game") == "fn" or "#sub-eas-" in connection.get("id", ""):
                return {"id": connection["id"], "deployment_id": connection.get("deployment_id", DEPLOYMENT_ID),
                        "meta": connection.get("meta") or {}}
    return None


class EpicParties:
    """Party actions on Epic Parties. Each returns normally or raises EosError with a spoken reason."""

    def __init__(self, session: EosSession):
        self.session = session

    @property
    def me(self) -> str:
        return self.session.account_id or ""

    def _call(self, method: str, path: str, json=None, ok=(200, 201, 204)) -> requests.Response:
        try:
            response = self.session.request(method, PARTY_BASE + path, json=json)
        except requests.RequestException as e:
            logger.error(f"Party call {method} failed: {e}")
            raise EosError("Couldn't reach Epic. Try again in a moment.") from e
        if response.status_code not in ok:
            logger.error(f"Party call {method} {path} returned {response.status_code}: {response.text[:300]}")
        return response

    def state(self) -> PartyState:
        response = self._call("GET", f"/v2/users/{self.me}")
        if response.status_code == 404:
            return PartyState(None, [], [])
        if not response.ok:
            raise EosError("Couldn't load your party.")
        return parse_party_state(response.json())

    def party(self, party_id: str) -> Optional[dict]:
        response = self._call("GET", f"/v2/parties/{party_id}", ok=(200, 404))
        return response.json() if response.status_code == 200 else None

    def invite(self, friend_id: str) -> None:
        """Invite a friend to our party. Also how a request to join us is accepted."""
        response = self._call("POST", f"/v2/users/{friend_id}/invites/{self.me}", json={}, ok=(200, 201, 204, 409))
        if response.status_code not in (200, 201, 204, 409):
            raise EosError("Couldn't send the invite.")

    def accept_invite(self, invite: EosInvite) -> None:
        """Leave our party and join theirs with the running game's connection, so the game follows."""
        target = self.party(invite.party_id)
        if target is None:
            raise EosError("That invite has expired.")
        state = self.state()
        connection = game_connection(state.party.members, self.me) if state.party else None
        if connection is None and state.party:
            record = self.party(state.party.id)
            connection = game_connection((record or {}).get("members") or [], self.me)
        if connection is None:
            raise EosError("Start Fortnite to join a party.")
        if state.party and state.party.id != invite.party_id:
            self._call("DELETE", f"/v2/parties/{state.party.id}/members/{self.me}", ok=(200, 204, 404))
        response = self._call("POST", f"/v2/parties/{invite.party_id}/members/{self.me}/join",
                              json={"connection": connection, "meta": {}})
        if not response.ok:
            raise EosError("Couldn't join the party.")

    def decline_invite(self, inviter_id: str) -> None:
        response = self._call("DELETE", f"/v2/users/{self.me}/invites/{inviter_id}", ok=(200, 204, 404))
        if response.status_code not in (200, 204, 404):
            raise EosError("Couldn't decline the invite.")

    def accept_join_request(self, requester_id: str) -> None:
        self.invite(requester_id)

    def decline_join_request(self, requester_id: str) -> None:
        response = self._call("DELETE", f"/v2/users/{self.me}/joinRequests/{requester_id}", ok=(200, 204, 404))
        if response.status_code not in (200, 204, 404):
            raise EosError("Couldn't decline the request.")

    def request_to_join(self, friend_id: str) -> None:
        response = self._call("POST", f"/v2/users/{friend_id}/joinRequests/{self.me}", json={},
                              ok=(200, 201, 204, 409))
        if response.status_code == 404:
            raise EosError("They aren't in a party you can join.")
        if response.status_code not in (200, 201, 204, 409):
            raise EosError("Couldn't send the join request.")

    def leave(self) -> None:
        state = self.state()
        if not state.party:
            return
        response = self._call("DELETE", f"/v2/parties/{state.party.id}/members/{self.me}", ok=(200, 204, 404))
        if response.status_code not in (200, 204, 404):
            raise EosError("Couldn't leave the party.")

    def kick(self, member_id: str) -> None:
        state = self.state()
        if not state.party:
            raise EosError("You aren't in a party.")
        response = self._call("DELETE", f"/v2/parties/{state.party.id}/members/{member_id}", ok=(200, 204, 404))
        if response.status_code not in (200, 204, 404):
            raise EosError("Couldn't kick that member. Only the party leader can.")

    def promote(self, member_id: str) -> None:
        state = self.state()
        if not state.party:
            raise EosError("You aren't in a party.")
        response = self._call("POST", f"/v2/parties/{state.party.id}/members/{member_id}/promote", json={})
        if not response.ok:
            raise EosError("Couldn't promote that member. Only the party leader can.")
