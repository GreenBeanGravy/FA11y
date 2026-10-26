from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from lib.utilities import epic_discovery as discovery


def test_browser_transport_and_cache(monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=200, text="<html>islands</html>")

    monkeypatch.setattr(discovery, "browser_requests", SimpleNamespace(get=get))
    monkeypatch.setattr(discovery.time, "sleep", lambda _: None)
    api = discovery.EpicDiscovery()
    for _ in range(2):
        assert api._fetch_url_cached("https://fortnite.gg/creative", {
            "User-Agent": "outdated", "Referer": "https://fortnite.gg/",
        }) == "<html>islands</html>"
    assert len(calls) == 1
    assert calls[0][1]["impersonate"] == "chrome"
    assert "User-Agent" not in calls[0][1]["headers"]


def test_challenge_is_not_cached(monkeypatch):
    monkeypatch.setattr(discovery, "browser_requests", SimpleNamespace(
        get=lambda *args, **kwargs: SimpleNamespace(
            status_code=200, text="<script>window._cf_chl_opt = {};</script>")))
    monkeypatch.setattr(discovery.time, "sleep", lambda _: None)
    api = discovery.EpicDiscovery()
    assert api._fetch_url_cached("https://fortnite.gg/creative", {}) is None
    assert not api._response_cache


def test_search_and_creator_parameters_are_encoded(monkeypatch):
    api = discovery.EpicDiscovery()
    urls = []
    monkeypatch.setattr(api, "_fetch_url_cached", lambda url, headers: urls.append(url))
    query = "hide & seek #1"
    api.scrape_fortnite_gg(query)
    api._fetch_and_parse_creator_page(query, 2)
    assert parse_qs(urlsplit(urls[0]).query) == {"search": [query]}
    assert parse_qs(urlsplit(urls[1]).query) == {"name": [query], "page": ["2"]}
