"""Epic text chat: the DMs and party chat Fortnite shows in its social sidebar.

Reading needs only the EAS token. Sending needs a signature, the same way the game signs: FA11y
makes its own Ed25519 key, registers the public half with Epic's public key service (which
answers with a signed JWT, valid about 60 days), and signs every message with the private half.
The game checks that signature before it shows a message.

A message body is base64 JSON: {"mid", "sid", "rid", "msg", "tst", "seq", "rec", "mts", "cty"}.
The signature covers the base64 text as UTF-8 bytes followed by one NUL byte.
"""
from __future__ import annotations

import base64
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests

from lib.config.config_manager import config_manager
from lib.utilities.epic_eos import EOS_BASE, EosError, EosSession, parse_time

logger = logging.getLogger(__name__)

CHAT_BASE = f"{EOS_BASE}/epic/chat/v1/public/_"
PUBLICKEY_URL = "https://publickey-service-live.ecosec.on.epicgames.com/publickey/v2/publickey/"
KEY_RENEW_BEFORE = timedelta(days=7)
TIMEOUT = 10


@dataclass
class Conversation:
    id: str
    type: str  # "dm" or "epic_party"
    members: List[str]
    unread: int = 0
    reportable: bool = True

    def other_member(self, me: str) -> str:
        return next((m for m in self.members if m != me), "")


@dataclass
class ChatMessage:
    id: str
    conversation_id: str
    sender_id: str
    text: str
    sent_at: Optional[datetime] = None
    conversation_type: str = "dm"


def decode_body(body: str) -> dict:
    """The JSON inside a message body, or {} when it isn't one."""
    try:
        raw = base64.b64decode(body + "=" * (-len(body) % 4))
        return json.loads(raw.rstrip(b"\0").decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}


def parse_message(item: dict, conversation_id: str = "", conversation_type: str = "dm") -> Optional[ChatMessage]:
    """A chat message from a history page or a push event. None for system entries."""
    message = item.get("message")
    if not isinstance(message, dict) or "body" not in message:
        return None
    body = decode_body(message["body"])
    text = body.get("msg")
    if not isinstance(text, str):
        return None
    return ChatMessage(
        id=item.get("msgId") or body.get("mid", ""),
        conversation_id=conversation_id or item.get("conversationId", ""),
        sender_id=item.get("senderId") or body.get("sid", ""),
        text=text,
        sent_at=parse_time(item.get("createdAt", "")),
        conversation_type=conversation_type,
    )


def build_body(sender_id: str, conversation_id: str, text: str) -> str:
    """The base64 message body, in the same shape the game sends."""
    payload = {"mid": uuid.uuid4().hex.upper(), "sid": sender_id, "rid": conversation_id, "msg": text,
               "tst": int(time.time()), "seq": 1, "rec": True, "mts": [], "cty": "Persistent"}
    return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")


class ChatKey:
    """FA11y's chat signing key, kept in config/chat_key.json and registered with Epic when needed."""

    def __init__(self, auth):
        self.auth = auth
        self._lock = threading.Lock()
        config_manager.register("chat_key", "config/chat_key.json", format="json", default={})

    def _registered(self) -> Optional[dict]:
        data = config_manager.get("chat_key") or {}
        if data.get("account_id") != self.auth.account_id or not data.get("jwt") or not data.get("private_key"):
            return None
        expires = parse_time(data.get("expires", ""))
        if expires is None or expires - datetime.now(timezone.utc) < KEY_RENEW_BEFORE:
            return None
        return data

    def get(self):
        """(private key, JWT), registering a new key first when there is none or it expires soon."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        with self._lock:
            data = self._registered()
            if data:
                return Ed25519PrivateKey.from_private_bytes(base64.b64decode(data["private_key"])), data["jwt"]
            key = Ed25519PrivateKey.generate()
            public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            try:
                response = requests.post(PUBLICKEY_URL, headers={"Authorization": f"Bearer {self.auth.access_token}"},
                                         json={"key": base64.b64encode(public).decode("ascii"), "algorithm": "ed25519"},
                                         timeout=TIMEOUT)
            except requests.RequestException as e:
                raise EosError("Couldn't reach Epic. Try again in a moment.") from e
            if not response.ok:
                logger.error(f"Chat key registration failed: {response.status_code} {response.text[:200]}")
                raise EosError("Couldn't set up chat. Try again in a moment.")
            answer = response.json()
            private = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                        serialization.NoEncryption())
            config_manager.set("chat_key", data={
                "account_id": self.auth.account_id,
                "private_key": base64.b64encode(private).decode("ascii"),
                "jwt": answer["jwt"],
                "expires": answer.get("expiration", ""),
            })
            logger.info("Registered a new chat signing key")
            return key, answer["jwt"]


class EpicChat:
    """Conversations, history and sending."""

    def __init__(self, session: EosSession):
        self.session = session
        self.key = ChatKey(session.auth)
        self._dm_ids: Dict[str, str] = {}

    @property
    def me(self) -> str:
        return self.session.account_id or ""

    def _get(self, path: str) -> dict:
        try:
            response = self.session.request("GET", CHAT_BASE + path)
        except requests.RequestException as e:
            raise EosError("Couldn't reach Epic. Try again in a moment.") from e
        if not response.ok:
            logger.error(f"Chat GET returned {response.status_code}: {response.text[:200]}")
            raise EosError("Couldn't load your messages.")
        return response.json()

    def conversations(self) -> List[Conversation]:
        data = self._get(f"/users/{self.me}/conversations")
        return [Conversation(c["conversationId"], c.get("type", "dm"), list(c.get("members") or []),
                             int(c.get("unreadCount") or 0), bool(c.get("isReportable", True)))
                for c in data.get("conversations") or [] if c.get("conversationId")]

    def dm_conversation_id(self, friend_id: str) -> str:
        if friend_id not in self._dm_ids:
            data = self._get(f"/users/{self.me}/conversations/dm/{friend_id}")
            if not data.get("conversationId"):
                raise EosError("Couldn't open a conversation with them.")
            self._dm_ids[friend_id] = data["conversationId"]
        return self._dm_ids[friend_id]

    def messages(self, conversation_id: str, conversation_type: str = "dm") -> List[ChatMessage]:
        """The conversation's history, oldest first."""
        data = self._get(f"/conversations/{conversation_id}/messages?requestingAccountId={self.me}")
        found = [m for m in (parse_message(item, conversation_id, conversation_type)
                             for item in data.get("page") or []) if m]
        found.sort(key=lambda m: m.sent_at or datetime.min.replace(tzinfo=timezone.utc))
        return found

    def send(self, conversation_id: str, recipients: List[str], text: str, party: bool = False) -> None:
        text = text.strip()
        if not text:
            raise EosError("The message is empty.")
        key, jwt = self.key.get()
        body = build_body(self.me, conversation_id, text)
        metadata = {"TmV": "2", "Pub": jwt, "Sig": base64.b64encode(key.sign(body.encode("ascii") + b"\0")).decode("ascii"),
                    "PlfNm": "WIN", "PlfId": self.me}
        if party:
            metadata["NPM"] = "1"
        url = f"{CHAT_BASE}/conversations/{conversation_id}/messages?fromAccountId={self.me}"
        reportable = True
        for _ in range(2):
            request = {"allowedRecipients": [r for r in recipients if r != self.me], "message": {"body": body},
                       "isReportable": reportable, "metadata": metadata}
            try:
                response = self.session.request("POST", url, json=request)
            except requests.RequestException as e:
                raise EosError("Couldn't reach Epic. Try again in a moment.") from e
            if response.ok:
                return
            # The flag has to match the conversation's; try the other value once.
            if response.status_code == 409 and "is_reportable_mismatch" in response.text:
                reportable = not reportable
                continue
            break
        logger.error(f"Chat send returned {response.status_code}: {response.text[:300]}")
        raise EosError("Couldn't send the message.")

    def send_dm(self, friend_id: str, text: str) -> None:
        self.send(self.dm_conversation_id(friend_id), [friend_id], text)
