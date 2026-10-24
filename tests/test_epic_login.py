"""Signing in to Epic from the embedded browser: reading Epic's reply and what the sign-in window does with it."""
import json

import pytest
import wx

from lib.guis import epic_browser_login as login
from lib.utilities import epic_auth
from lib.utilities.epic_redirect import (
    FNAUTH_URL, code_from_auth_url, is_fnauth_page, is_login_page, is_redirect_endpoint,
    parse_redirect_response, safe_url,
)

REDIRECT = "https://www.epicgames.com/id/api/redirect?clientId=cid&responseType=code"
WARNING = "Do not share this code with any 3rd party service. It allows full access to your Epic account."

# What Epic answers when the browser is not signed in (captured from the live endpoint).
SIGNED_OUT = ('{"warning":"%s","redirectUrl":"https://accounts.epicgames.com/fnauth",'
              '"authorizationCode":null,"exchangeCode":null,"sid":null}' % WARNING)
SIGNED_IN = ('{"warning":"%s","redirectUrl":"https://accounts.epicgames.com/fnauth?code=abc123",'
             '"authorizationCode":"abc123","exchangeCode":null,"sid":null}' % WARNING)


# ---- reading Epic's reply ---------------------------------------------------------------------------------

def test_a_signed_out_reply_has_no_code():
    reply = parse_redirect_response(SIGNED_OUT)
    assert reply.code is None
    assert reply.destination == "https://accounts.epicgames.com/fnauth"


def test_a_signed_in_reply_gives_the_code():
    assert parse_redirect_response(SIGNED_IN).code == "abc123"


def test_the_code_comes_from_the_redirect_when_the_code_field_is_missing():
    text = json.dumps({"redirectUrl": "https://accounts.epicgames.com/fnauth?code=fromurl&state=x"})
    assert parse_redirect_response(text).code == "fromurl"


def test_the_reply_is_found_in_page_source_with_escaped_characters():
    source = ('<html><head><meta charset="utf-8"></head><body><pre>'
              '{"redirectUrl":"https://accounts.epicgames.com/fnauth?code=abc123&amp;state=x",'
              '"authorizationCode":"abc123"}</pre><div class="json-formatter-container"></div></body></html>')
    reply = parse_redirect_response(source)
    assert reply.code == "abc123"


def test_the_reply_is_found_in_formatted_page_text():
    text = '{\n  "warning": "%s",\n  "redirectUrl": "https://accounts.epicgames.com/fnauth?code=abc123",\n  "authorizationCode": "abc123"\n}' % WARNING
    assert parse_redirect_response("Pretty-print\n" + text).code == "abc123"


def test_the_reply_is_found_in_a_browser_formatted_page():
    source = ('<div class="json-formatter-container"><span>{</span><span class="key">"redirectUrl"</span>: '
              '<span class="string">"https://accounts.epicgames.com/fnauth?code=abc123"</span>, '
              '<span class="key">"authorizationCode"</span>: <span class="string">"abc123"</span><span>}</span></div>')
    assert parse_redirect_response(source).code == "abc123"


def test_the_reply_is_found_when_the_web_view_returns_it_as_a_json_string():
    assert parse_redirect_response(json.dumps(SIGNED_IN)).code == "abc123"


def test_the_first_text_with_a_reply_wins():
    assert parse_redirect_response("", "nothing here", SIGNED_OUT, SIGNED_IN).code is None


def test_a_page_without_a_reply_gives_none():
    assert parse_redirect_response("", "<html><body>Epic Games</body></html>") is None
    assert parse_redirect_response('{"redirectUrl": broken') is None


def test_a_big_page_is_read_quickly():
    page = "<script>" + '{"a":' * 20000 + "</script>" + SIGNED_IN
    assert parse_redirect_response(page).code == "abc123"


def test_the_log_form_of_a_url_leaves_the_query_out():
    assert safe_url("https://accounts.epicgames.com/fnauth?code=secret") == "https://accounts.epicgames.com/fnauth"


def test_only_fortnites_own_redirect_counts_as_a_code():
    assert code_from_auth_url("https://accounts.epicgames.com/fnauth?code=abc") == "abc"
    assert code_from_auth_url("https://www.epicgames.com/id/login/google/callback?code=abc&state=x") is None
    assert code_from_auth_url("https://evil.example/fnauth?code=abc") is None
    assert code_from_auth_url("https://accounts.epicgames.com/fnauth") is None
    assert code_from_auth_url("") is None


def test_the_pages_of_the_sign_in_are_told_apart():
    assert is_redirect_endpoint(REDIRECT)
    assert not is_redirect_endpoint("https://www.epicgames.com/id/login")
    assert is_fnauth_page(FNAUTH_URL) and is_fnauth_page(FNAUTH_URL + "/")
    assert not is_fnauth_page("https://accounts.epicgames.com/auth/login?clientId=1&returnPath=%2Ffnauth")
    assert is_login_page("https://accounts.epicgames.com/auth/login?clientId=1&returnPath=%2Ffnauth")
    assert is_login_page("https://www.epicgames.com/id/login?lang=en")
    assert not is_login_page(FNAUTH_URL)


# ---- why Epic refused a code ------------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status, body, text=""):
        self.status_code = status
        self._body = body
        self.text = text or json.dumps(body)

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def make_auth():
    auth = epic_auth.EpicAuth.__new__(epic_auth.EpicAuth)
    auth.CLIENT_ID, auth.CLIENT_SECRET = "cid", "secret"
    auth.OAUTH_TOKEN_URL = "https://example.invalid/token"
    auth.last_error = ""
    return auth


def test_a_refused_code_records_epics_error_code(monkeypatch):
    code = "errors.com.epicgames.account.oauth.authorization_code_not_found"
    monkeypatch.setattr(epic_auth.requests, "post", lambda *a, **k: FakeResponse(400, {"errorCode": code}))
    auth = make_auth()
    assert auth.exchange_code_for_token("abc") is False
    assert auth.last_error == code


def test_a_refused_code_without_a_body_records_the_status(monkeypatch):
    monkeypatch.setattr(epic_auth.requests, "post", lambda *a, **k: FakeResponse(503, ValueError("html"), "<html>bad gateway</html>"))
    auth = make_auth()
    assert auth.exchange_code_for_token("abc") is False
    assert auth.last_error == "HTTP 503"


def test_no_connection_is_recorded_as_such(monkeypatch):
    def fail(*a, **k):
        raise epic_auth.requests.ConnectionError("offline")

    monkeypatch.setattr(epic_auth.requests, "post", fail)
    auth = make_auth()
    assert auth.exchange_code_for_token("abc") is False
    assert auth.last_error == "could not reach Epic"


# ---- the sign-in window -----------------------------------------------------------------------------------

class FakeTime:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeAuth:
    CLIENT_ID = "cid"
    display_name = "Player"

    def __init__(self, accept=True, error="errors.com.epicgames.oauth.example"):
        self.accept, self.error = accept, error
        self.exchanged = []
        self.is_valid, self.access_token, self.last_error = False, None, ""

    def get_authorization_url(self):
        return REDIRECT

    def exchange_code_for_token(self, code):
        self.exchanged.append(code)
        if self.accept:
            self.is_valid, self.access_token = True, "token"
            return True
        self.last_error = self.error
        return False


class FakeBrowser:
    """Plays one page per ``GetCurrentURL`` call: (url, text, loaded), the last page staying."""

    def __init__(self, owner, stages):
        self.owner, self.stages, self.polls = owner, stages, 0
        self.loads = []

    def LoadURL(self, url):
        self.loads.append(url)

    def _stage(self):
        return self.stages[min(self.polls, len(self.stages) - 1)]

    def GetCurrentURL(self):
        self.polls += 1
        url, _text, loaded = self._stage()
        if loaded:
            self.owner._redirect_loaded = True
        return url

    def GetPageText(self):
        return self._stage()[1]

    def GetPageSource(self):
        return "<html><body><pre>%s</pre></body></html>" % self._stage()[1]


class FakeLabel:
    def __init__(self):
        self.text = ""

    def SetLabel(self, text):
        self.text = text


class FakeEvent:
    def __init__(self, url):
        self.url = url

    def GetURL(self):
        return self.url


@pytest.fixture
def calls(monkeypatch):
    recorded = {"after": [], "later": [], "box": []}
    monkeypatch.setattr(login, "time", FakeTime())
    monkeypatch.setattr(login.wx, "SafeYield", lambda *a: None)
    monkeypatch.setattr(login.wx, "CallAfter", lambda fn, *a: recorded["after"].append((fn.__name__, a)))
    monkeypatch.setattr(login.wx, "CallLater", lambda ms, fn, *a: recorded["later"].append(fn.__name__))
    monkeypatch.setattr(login.wx, "MessageBox", lambda message, caption, style=0: recorded["box"].append((caption, message)))
    return recorded


def make_dialog(stages, auth=None):
    dialog = login.EpicBrowserLoginDialog.__new__(login.EpicBrowserLoginDialog)
    dialog.auth_instance = auth or FakeAuth()
    dialog.login_successful = False
    dialog._login_detected = False
    dialog._auto_completing = False
    dialog._auto_attempts = 0
    dialog._auto_hold = False
    dialog._redirect_loaded = False
    dialog._failure_kind = ""
    dialog._failure_detail = ""
    dialog.status_label = FakeLabel()
    dialog.browser = FakeBrowser(dialog, stages)
    return dialog


def test_the_code_in_epics_reply_signs_in(calls):
    dialog = make_dialog([("https://www.epicgames.com/id/login", "", False),
                          (REDIRECT, SIGNED_IN, True)])
    dialog._on_logged_in_clicked(None)
    assert dialog.auth_instance.exchanged == ["abc123"]
    assert dialog.login_successful
    assert calls["box"] == []
    assert dialog.browser.loads == [REDIRECT]


def test_a_code_in_fortnites_redirect_signs_in_without_the_reply(calls):
    dialog = make_dialog([(REDIRECT, "", False), ("https://accounts.epicgames.com/fnauth?code=zzz", "", True)])
    dialog._on_logged_in_clicked(None)
    assert dialog.auth_instance.exchanged == ["zzz"]
    assert dialog.login_successful


def test_a_signed_out_reply_says_so_and_puts_the_sign_in_page_back(calls):
    dialog = make_dialog([(REDIRECT, SIGNED_OUT, True)])
    dialog._on_logged_in_clicked(None)
    assert not dialog.login_successful
    assert dialog.auth_instance.exchanged == []
    assert dialog.browser.loads == [REDIRECT, FNAUTH_URL]
    (caption, message), = calls["box"]
    assert caption == "Verification Failed"
    assert "not signed in" in message
    assert dialog._auto_hold


def test_a_refused_code_shows_why(calls):
    code = "errors.com.epicgames.account.oauth.authorization_code_not_found"
    dialog = make_dialog([(REDIRECT, SIGNED_IN, True)], FakeAuth(accept=False, error=code))
    dialog._on_logged_in_clicked(None)
    (_caption, message), = calls["box"]
    assert "did not accept" in message and code in message
    assert dialog.browser.loads == [REDIRECT]          # the person is not sent back to sign in


def test_the_page_we_came_from_is_not_taken_for_epics_reply(calls):
    old_page = ("https://www.epicgames.com/account/personal", SIGNED_IN, False)
    dialog = make_dialog([old_page])
    dialog._on_logged_in_clicked(None)
    assert dialog.auth_instance.exchanged == []
    assert "could not read" in calls["box"][0][1]


def test_an_old_reply_is_not_read_before_the_new_one_has_loaded(calls):
    dialog = make_dialog([(REDIRECT, SIGNED_OUT, False),      # the previous reply, still on screen
                          (REDIRECT, SIGNED_OUT, False),
                          (REDIRECT, SIGNED_IN, True)])      # the new one
    dialog._on_logged_in_clicked(None)
    assert dialog.auth_instance.exchanged == ["abc123"]
    assert calls["box"] == []


def test_a_reply_that_never_reports_loading_is_read_after_a_wait(calls):
    dialog = make_dialog([(REDIRECT, SIGNED_IN, False)])
    dialog._on_logged_in_clicked(None)
    assert dialog.auth_instance.exchanged == ["abc123"]


def test_a_code_is_never_used_twice(calls):
    dialog = make_dialog([(REDIRECT, "", False)])
    dialog._auto_completing = True                  # an attempt is already running
    dialog._extract_and_use_auth_code("https://accounts.epicgames.com/fnauth?code=zzz")
    dialog._on_logged_in_clicked(None)
    assert dialog.auth_instance.exchanged == []


def test_another_sites_code_is_not_sent_to_epic(calls):
    dialog = make_dialog([(REDIRECT, "", False)])
    dialog._on_navigated(FakeEvent("https://www.epicgames.com/id/login/google/callback?code=abc&state=x"))
    dialog._on_page_loaded(FakeEvent("https://www.epicgames.com/id/login/google/callback?code=abc&state=x"))
    assert calls["after"] == []


def test_coming_back_to_fortnites_page_starts_the_check(calls):
    dialog = make_dialog([(REDIRECT, "", False)])
    dialog._on_navigated(FakeEvent(FNAUTH_URL))
    assert calls["after"] == [("_auto_complete_login", ())]


def test_the_automatic_check_waits_until_the_person_is_back_at_the_sign_in_page(calls):
    dialog = make_dialog([(REDIRECT, SIGNED_OUT, True)])
    dialog._auto_complete_login()                    # first try fails and puts the sign in page back
    assert dialog._auto_hold and dialog._auto_attempts == 1
    loads = list(dialog.browser.loads)
    dialog._auto_complete_login()                    # the sign in page loading must not start another try
    assert dialog.browser.loads == loads
    dialog._on_page_loaded(FakeEvent("https://accounts.epicgames.com/auth/login?clientId=1&returnPath=%2Ffnauth"))
    assert not dialog._auto_hold and dialog._auto_attempts == 0


def test_the_automatic_check_stops_after_two_tries(calls):
    dialog = make_dialog([(REDIRECT, "", False)])
    dialog._auto_complete_login()
    dialog._auto_complete_login()
    loads = len(dialog.browser.loads)
    dialog._auto_complete_login()
    assert len(dialog.browser.loads) == loads


def test_signing_in_starts_on_fortnites_own_page(calls):
    dialog = make_dialog([(REDIRECT, "", False)])
    dialog._start_login()
    assert dialog.browser.loads == [FNAUTH_URL]


# ---- the background sign-in -------------------------------------------------------------------------------

def make_silent(stages, auth=None):
    silent = login.SilentAuthDialog.__new__(login.SilentAuthDialog)
    silent.auth_instance = auth or FakeAuth()
    silent.auth_successful = False
    silent._finished = False
    silent._redirect_requested = False
    silent._followed = set()
    silent.browser = FakeBrowser(None, stages)
    return silent


def test_the_background_sign_in_asks_for_the_code_once_fortnites_page_shows(calls):
    silent = make_silent([(FNAUTH_URL, "", False)])
    silent._handle_navigation(FNAUTH_URL)
    silent._handle_navigation(FNAUTH_URL)
    assert silent.browser.loads == [REDIRECT]


def test_the_background_sign_in_uses_the_code_in_epics_reply(calls):
    silent = make_silent([(REDIRECT, SIGNED_IN, True)])
    silent._check_page_source()
    assert silent.auth_instance.exchanged == ["abc123"]
    assert silent.auth_successful
    assert calls["after"] == [("_finish", (True,))]


def test_the_background_sign_in_follows_a_redirect_once(calls):
    silent = make_silent([(REDIRECT, SIGNED_OUT, True)])
    silent._check_page_source()
    silent._check_page_source()
    assert silent.browser.loads == [FNAUTH_URL]
    assert silent.auth_instance.exchanged == []
