import types

from lib.hub import components


def _setup(monkeypatch, tmp_path, before, after, code):
    monkeypatch.chdir(tmp_path)
    states = iter([before, after])
    monkeypatch.setattr(components, "missing", lambda: next(states))
    monkeypatch.setattr(components, "updater_path", lambda: str(tmp_path / "Updater.exe"))
    runs = []
    monkeypatch.setattr(components.subprocess, "run",
                        lambda args, **kw: runs.append(args) or types.SimpleNamespace(returncode=code))
    return runs


FAKER = [("FakerInput driver", "mouse passthrough")]
BOTH = [(".NET Runtime", "mouse passthrough"), ("FakerInput driver", "mouse passthrough")]


def test_installs_and_restarts(monkeypatch, tmp_path):
    runs = _setup(monkeypatch, tmp_path, BOTH, [], 0)
    said, restarted = [], []
    components.install(said.append, lambda: restarted.append(True))
    assert runs[0][1:] == ["--components", "--window"]
    assert said[0] == ("FA11y needs the .NET Runtime and FakerInput driver, used by mouse passthrough. "
                       "Installing now. Windows will ask for permission.")
    assert restarted


def test_declined_is_not_asked_again(monkeypatch, tmp_path):
    runs = _setup(monkeypatch, tmp_path, FAKER, FAKER, components.STILL_MISSING)
    said = []
    components.install(said.append, lambda: None)
    assert "wasn't installed" in said[-1]
    runs.clear()
    monkeypatch.setattr(components, "missing", lambda: FAKER)
    components.install(said.append, lambda: None)
    assert runs == []
    components.install(said.append, lambda: None, ask_again=True)
    assert runs


def test_old_updater_points_at_updater(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, FAKER, FAKER, 2)
    said = []
    components.install(said.append, lambda: None)
    assert said[-1].startswith("FA11y couldn't install the FakerInput driver")


def test_nothing_missing_says_nothing(monkeypatch, tmp_path):
    runs = _setup(monkeypatch, tmp_path, [], [], 0)
    said = []
    components.install(said.append, lambda: None)
    assert not said and not runs
