"""Reading Epic's answer to the browser sign-in.

Once the embedded browser is signed in, Epic's redirect page answers with a small JSON document that holds
the authorization code. The code is null when the browser is not signed in, and that includes a browser
that is signed in on www.epicgames.com but not on accounts.epicgames.com/fnauth, Fortnite's own sign in.
The web view can hand that document back as plain text, as page source with the JSON inside <pre>, or as
page source where the browser has formatted the JSON, so this reads all of them.
"""
import html
import json
import re
import urllib.parse
from typing import NamedTuple, Optional

REDIRECT_HOST = "www.epicgames.com"
REDIRECT_PATH = "/id/api/redirect"
# Fortnite's client is sent here with the code on a successful sign-in.
AUTH_HOST = "accounts.epicgames.com"
AUTH_PATH = "/fnauth"
FNAUTH_URL = "https://" + AUTH_HOST + AUTH_PATH

_KEY = re.compile(r'"(?:redirectUrl|authorizationCode)"')
_TAG = re.compile(r"<[^>]*>")
_MAX_OBJECT_STARTS = 20


class RedirectReply(NamedTuple):
    code: Optional[str]
    destination: Optional[str]


def safe_url(url: str) -> str:
    """Where a URL points, for the log. The query is left out because it can hold a sign-in code."""
    parsed = urllib.parse.urlparse(url or "")
    return f"{parsed.scheme}://{parsed.hostname or ''}{parsed.path}"


def is_redirect_endpoint(url: str) -> bool:
    """True for Epic's redirect page, whatever it was asked for."""
    parsed = urllib.parse.urlparse(url or "")
    return parsed.hostname == REDIRECT_HOST and parsed.path.rstrip("/") == REDIRECT_PATH


def is_fnauth_page(url: str) -> bool:
    """True on Fortnite's own sign in page once the browser is signed in there (no code yet).

    Signed out, Epic sends that address on to its sign in page, so this is where the browser comes back to
    after a successful sign in.
    """
    parsed = urllib.parse.urlparse(url or "")
    return parsed.hostname == AUTH_HOST and parsed.path.rstrip("/") == AUTH_PATH


def is_login_page(url: str) -> bool:
    """True on either of Epic's sign in pages."""
    parsed = urllib.parse.urlparse(url or "")
    return (
        (parsed.hostname == AUTH_HOST and parsed.path.startswith("/auth/login"))
        or (parsed.hostname == REDIRECT_HOST and parsed.path.startswith("/id/login"))
    )


def code_from_auth_url(url: str) -> Optional[str]:
    """The sign-in code in Fortnite's own redirect, or None.

    Other pages in a sign-in carry a code too (Google's and Facebook's come back with ``code=``), and those
    are not Epic's, so only the Fortnite redirect counts.
    """
    parsed = urllib.parse.urlparse(url or "")
    if parsed.hostname != AUTH_HOST or parsed.path.rstrip("/") != AUTH_PATH:
        return None
    return (urllib.parse.parse_qs(parsed.query).get("code") or [None])[0] or None


def _candidates(text: str):
    yield text
    stripped = html.unescape(_TAG.sub("", text))
    if stripped != text:
        yield stripped
    # Some web views return a script result as a JSON string.
    if text[:1] == '"':
        try:
            inner = json.loads(text)
        except ValueError:
            return
        if isinstance(inner, str):
            yield from _candidates(inner)


def _reply_object(text: str) -> Optional[dict]:
    decoder = json.JSONDecoder()
    for candidate in _candidates(text):
        key = _KEY.search(candidate)
        if key is None:
            continue
        start = key.start()
        for _ in range(_MAX_OBJECT_STARTS):
            start = candidate.rfind("{", 0, start)
            if start < 0:
                break
            try:
                value, _end = decoder.raw_decode(candidate, start)
            except ValueError:
                continue
            if isinstance(value, dict) and ("redirectUrl" in value or "authorizationCode" in value):
                return value
    return None


def parse_redirect_response(*texts: str) -> Optional[RedirectReply]:
    """Epic's reply from page text or source, or None when none of the texts holds one.

    ``code`` is None while the browser is not signed in. ``destination`` is the redirect Epic named.
    """
    for text in texts:
        if not text:
            continue
        value = _reply_object(text)
        if value is None:
            continue
        code = value.get("authorizationCode")
        code = code.strip() if isinstance(code, str) else ""
        destination = value.get("redirectUrl")
        destination = destination.strip() if isinstance(destination, str) else ""
        if not code and destination:
            code = (urllib.parse.parse_qs(urllib.parse.urlparse(destination).query).get("code") or [""])[0]
        return RedirectReply(code or None, destination or None)
    return None
