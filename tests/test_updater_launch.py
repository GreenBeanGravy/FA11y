import argparse
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import updater
from lib.app import updater_check


def test_updater_accepts_legacy_fa11y_flag(monkeypatch):
    monkeypatch.setattr("sys.argv", ["updater.py", "--run-by-fa11y"])
    assert updater.parse_arguments().run_by_fa11y is True


def test_fa11y_launches_updater_from_installation_directory(monkeypatch):
    completed = MagicMock(returncode=0, stdout="", stderr="")
    run = MagicMock(return_value=completed)
    monkeypatch.setattr(updater_check.subprocess, "run", run)

    assert updater_check.run_updater(MagicMock()) is False
    args, kwargs = run.call_args
    expected_root = Path(updater_check.__file__).resolve().parents[2]
    assert args[0] == [updater_check.sys.executable, str(expected_root / "updater.py")]
    assert Path(kwargs["cwd"]) == expected_root


def test_updated_updater_restarts_and_propagates_update_result(monkeypatch, tmp_path):
    fake_script = tmp_path / "updater.py"
    fake_script.write_text("# updated updater", encoding="utf-8")
    monkeypatch.setattr(updater, "__file__", str(fake_script))
    monkeypatch.setattr(
        updater, "parse_arguments",
        lambda: argparse.Namespace(monarch=False, branch=updater.GITHUB_BRANCH,
                                   run_by_fa11y=False),
    )
    monkeypatch.setattr(updater, "update_script", lambda _name: True)
    monkeypatch.chdir(tmp_path)
    child = MagicMock(returncode=1)
    monkeypatch.setattr(updater.subprocess, "run", MagicMock(return_value=child))

    with pytest.raises(SystemExit) as exited:
        updater.main()

    assert exited.value.code == 1
    command = updater.subprocess.run.call_args.args[0]
    assert command[:2] == [updater.sys.executable, str(fake_script)]
    assert updater.subprocess.run.call_args.kwargs["cwd"] == str(tmp_path)


def test_version_check_does_not_downgrade(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "VERSION").write_text("18.10.4", encoding="utf-8")
    monkeypatch.setattr(updater, "get_version_github", lambda *_args: "18.10.3")
    assert updater.check_version() is False
