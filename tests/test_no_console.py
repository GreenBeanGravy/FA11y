"""Child processes started by a windowless FA11y must not open console windows."""
import subprocess
from unittest.mock import patch

from lib.app import no_console


def test_install_adds_create_no_window(monkeypatch):
    calls = []

    def fake_init(self, *args, creationflags=0, **kwargs):
        calls.append(creationflags)

    monkeypatch.setattr(subprocess.Popen, "__init__", fake_init)
    monkeypatch.setattr(subprocess.Popen, "_fa11y_no_console", False, raising=False)
    with patch.object(no_console, "has_console", return_value=False):
        no_console.install()
    subprocess.Popen(["legendary"])
    subprocess.Popen(["launcher"], creationflags=no_console.CREATE_NEW_CONSOLE)
    assert calls == [no_console.CREATE_NO_WINDOW, no_console.CREATE_NEW_CONSOLE]


def test_install_does_nothing_with_a_console(monkeypatch):
    original = subprocess.Popen.__init__
    with patch.object(no_console, "has_console", return_value=True):
        no_console.install()
    assert subprocess.Popen.__init__ is original
