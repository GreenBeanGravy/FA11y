import json
from unittest.mock import MagicMock

import pytest

from lib.app import branch, updater_check
from lib.hub import status
from lib.shell.handlers import about

LIST = [{"name": "main", "label": "Stable", "description": "x"},
        {"name": "overhaul", "label": "Beta", "description": "y"}]


@pytest.fixture(autouse=True)
def _reset(monkeypatch, tmp_path):
    monkeypatch.setattr(branch, "_ROOT", str(tmp_path))
    monkeypatch.setattr(branch, "_cache", None)


def test_no_saved_branch_is_main(tmp_path):
    assert branch.current_branch() == "main"


def test_version_url_follows_saved_branch(tmp_path):
    (tmp_path / branch.STATE_FILE).write_text(json.dumps({"files": {}, "branch": "overhaul"}))
    assert branch.current_branch() == "overhaul"
    assert updater_check.version_url().endswith("/FA11y/overhaul/VERSION")
    assert updater_check.changelog_url().endswith("/FA11y/overhaul/CHANGELOG.txt")


def test_branch_list_falls_back_to_local_copy(monkeypatch, tmp_path):
    (tmp_path / "installer").mkdir()
    (tmp_path / "installer" / "branches.json").write_text(json.dumps(LIST))
    monkeypatch.setattr(branch.requests, "get", MagicMock(side_effect=branch.requests.ConnectionError()))
    assert [b["name"] for b in branch.available_branches()] == ["main", "overhaul"]
    assert branch.branch_info("overhaul")["label"] == "Beta"


def test_switch_rejects_unknown_branch(monkeypatch):
    monkeypatch.setattr(branch, "_cache", LIST)
    popen = MagicMock()
    monkeypatch.setattr(status.subprocess, "Popen", popen)
    with pytest.raises(ValueError):
        about.about_switch_branch({"name": "nope"})
    popen.assert_not_called()


def test_switch_starts_launcher_with_branch(monkeypatch, tmp_path):
    launcher = tmp_path / "FA11y Launcher.exe"
    launcher.write_text("")
    monkeypatch.setenv("FA11Y_LAUNCHER", str(launcher))
    monkeypatch.setattr(branch, "_cache", LIST)
    popen = MagicMock()
    monkeypatch.setattr(status.subprocess, "Popen", popen)
    hub = MagicMock()
    monkeypatch.setattr("lib.shell.handlers.app._hub", lambda: hub)
    about.about_switch_branch({"name": "overhaul"})
    assert popen.call_args[0][0] == [str(launcher), "--update", "--branch", "overhaul"]
    hub.quit.assert_called_once()


def test_versions_order_pre_releases_before_their_release():
    from lib.app.updater_check import parse_version as v
    assert v("18.11.17") < v("19.0.0-beta.1") < v("19.0.0-beta.2") < v("19.0.0")
    assert v("18.11.16") < v("18.11.17")
