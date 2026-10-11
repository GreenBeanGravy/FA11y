"""Tests for keeping legendary.exe at the pinned release (lib/fortnite/legendary_update.py)."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

from lib.fortnite import legendary_update as lu
from lib.fortnite.legendary_manager import OperationResult

NEW = b"legendary 0.21.1 binary"
NEW_SHA = hashlib.sha256(NEW).hexdigest()
URL = "https://github.com/derrod/legendary/releases/download/0.21.1/legendary_windows_x64.exe"


def manifest(sha=NEW_SHA, url=URL, version="0.21.1"):
    return {"components": [
        {"id": "dotnet8", "download": {"url": "https://example.com/x.exe", "sha512": "0" * 128}},
        {"id": "legendary", "version": version, "download": {"url": url, "sha256": sha}},
    ]}


def write_manifest(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


@pytest.fixture
def root(tmp_path):
    write_manifest(str(tmp_path / lu.MANIFEST_COPY), manifest())
    return tmp_path


class FakeResponse:
    def __init__(self, body, status=200):
        self.body, self.status = body, status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self.body), 4):
            yield self.body[i:i + 4]


class FakeSession:
    def __init__(self, body=NEW, status=200):
        self.body, self.status, self.urls = body, status, []

    def get(self, url, stream=False, timeout=None):
        self.urls.append(url)
        return FakeResponse(self.body, self.status)


class FakeManager:
    def __init__(self, busy=None):
        self.current_operation = busy
        self.ran = []

    def _exclusive(self, name, func):
        self.ran.append(name)
        return func()


def listing(path):
    return sorted(os.listdir(path))


# --- the pin ---------------------------------------------------------------

def test_pin_comes_from_the_manifest_copy_the_updater_saves(root):
    pin = lu.load_pin(str(root))
    assert pin == lu.Pin("0.21.1", URL, NEW_SHA)


def test_pin_falls_back_to_the_repo_manifest_in_a_checkout(tmp_path):
    write_manifest(str(tmp_path / "installer" / "manifest.json"), manifest(version="9.9"))
    assert lu.load_pin(str(tmp_path)).version == "9.9"


def test_the_saved_copy_wins_over_the_repo_manifest(root):
    write_manifest(str(root / "installer" / "manifest.json"), manifest(version="9.9"))
    assert lu.load_pin(str(root)).version == "0.21.1"


@pytest.mark.parametrize("data", [
    manifest(sha="abc"),
    manifest(url="http://insecure.example/legendary.exe"),
    {"components": [{"id": "dotnet8"}]},
    {"components": "nonsense"},
])
def test_no_pin_without_a_usable_legendary_entry(tmp_path, data):
    write_manifest(str(tmp_path / lu.MANIFEST_COPY), data)
    assert lu.load_pin(str(tmp_path)) is None


def test_no_pin_from_a_broken_manifest(tmp_path):
    (tmp_path / lu.MANIFEST_COPY).write_text("{not json", encoding="utf-8")
    assert lu.load_pin(str(tmp_path)) is None


def test_the_shipped_manifest_pins_0_21_1():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pin = lu.load_pin(repo)
    assert pin.version == "0.21.1"
    assert pin.url.endswith("/0.21.1/legendary_windows_x64.exe")
    assert pin.sha256 == "6be77857dc0a6dd33ea7442ce8b5291944ec6da53757f81ca95b57ce794baf5b"


# --- checking --------------------------------------------------------------

def test_check_states(root):
    exe = root / lu.EXE_NAME
    assert lu.check(str(root)).state == "missing"
    exe.write_bytes(b"old legendary")
    assert lu.check(str(root)).state == "outdated"
    exe.write_bytes(NEW)
    assert lu.check(str(root)).state == "current"


def test_check_without_a_pin_is_unknown(tmp_path):
    (tmp_path / lu.EXE_NAME).write_bytes(b"whatever")
    assert lu.check(str(tmp_path)).state == "unknown"
    os.remove(tmp_path / lu.EXE_NAME)
    assert lu.check(str(tmp_path)).state == "unknown"


def test_installed_version_reads_the_version_line(tmp_path):
    script = tmp_path / "fake_legendary.py"
    script.write_text('print(\'legendary version "0.20.34", codename "Direct Intervention"\')', encoding="utf-8")
    real_run = subprocess.run
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        return real_run([sys.executable, str(script)], **kw)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(lu.subprocess, "run", run)
        assert lu.installed_version("legendary.exe") == "0.20.34"
    assert seen == [["legendary.exe", "--version"]]


def test_installed_version_is_empty_when_it_cannot_run(tmp_path):
    assert lu.installed_version(str(tmp_path / "nope.exe")) == ""


# --- downloading -----------------------------------------------------------

def test_download_puts_the_verified_file_in_place(tmp_path):
    target = tmp_path / lu.EXE_NAME
    target.write_bytes(b"old")
    session = FakeSession()
    lu.download(lu.Pin("0.21.1", URL, NEW_SHA), str(target), session)
    assert target.read_bytes() == NEW
    assert session.urls == [URL]
    assert listing(tmp_path) == [lu.EXE_NAME]


def test_a_download_with_the_wrong_hash_is_rejected_and_nothing_changes(tmp_path):
    target = tmp_path / lu.EXE_NAME
    target.write_bytes(b"old")
    with pytest.raises(ValueError, match="SHA-256"):
        lu.download(lu.Pin("0.21.1", URL, NEW_SHA), str(target), FakeSession(body=b"tampered"))
    assert target.read_bytes() == b"old"
    assert listing(tmp_path) == [lu.EXE_NAME]


def test_a_failed_request_leaves_nothing_behind(tmp_path):
    target = tmp_path / lu.EXE_NAME
    target.write_bytes(b"old")
    with pytest.raises(RuntimeError):
        lu.download(lu.Pin("0.21.1", URL, NEW_SHA), str(target), FakeSession(status=404))
    assert listing(tmp_path) == [lu.EXE_NAME]


def running_copy(path):
    """Start a copy of ping.exe at path, so the file is a loaded image like a running legendary.exe."""
    ping = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "PING.EXE")
    if sys.platform != "win32" or not os.path.isfile(ping):
        pytest.skip("needs Windows")
    shutil.copyfile(ping, path)
    proc = subprocess.Popen([path, "-n", "30", "127.0.0.1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.3)
    try:
        os.remove(path)
    except OSError:
        return proc
    proc.kill()
    proc.wait()
    pytest.skip("this system deletes running executables")


def stop(proc):
    proc.kill()
    proc.wait()
    time.sleep(0.2)


def test_download_replaces_a_running_legendary_and_cleanup_removes_it_later(tmp_path):
    target = str(tmp_path / lu.EXE_NAME)
    proc = running_copy(target)
    try:
        lu.download(lu.Pin("0.21.1", URL, NEW_SHA), target, FakeSession())
        with open(target, "rb") as f:
            assert f.read() == NEW
        assert listing(tmp_path) == [lu.EXE_NAME, lu.EXE_NAME + ".old"]
        lu.cleanup(target)  # still running: kept
        assert listing(tmp_path) == [lu.EXE_NAME, lu.EXE_NAME + ".old"]
    finally:
        stop(proc)
    lu.cleanup(target)
    assert listing(tmp_path) == [lu.EXE_NAME]


def test_a_running_set_aside_copy_does_not_block_the_next_replace(tmp_path):
    target = str(tmp_path / lu.EXE_NAME)
    first = running_copy(str(tmp_path / "first.exe"))
    second = running_copy(str(tmp_path / "second.exe"))
    try:
        os.rename(str(tmp_path / "first.exe"), target + ".old")  # left over and still running
        os.rename(str(tmp_path / "second.exe"), target)  # the current one, also running
        lu.download(lu.Pin("0.21.1", URL, NEW_SHA), target, FakeSession())
        with open(target, "rb") as f:
            assert f.read() == NEW
        assert listing(tmp_path) == [lu.EXE_NAME, lu.EXE_NAME + ".1.old", lu.EXE_NAME + ".old"]
    finally:
        stop(first)
        stop(second)
    lu.cleanup(target)
    assert listing(tmp_path) == [lu.EXE_NAME]


# --- ensure_current --------------------------------------------------------

def test_ensure_current_updates_an_old_copy_through_the_manager(root):
    (root / lu.EXE_NAME).write_bytes(b"old")
    manager = FakeManager()
    message = lu.ensure_current(str(root), manager, FakeSession())
    assert message == "Updated Legendary to version 0.21.1."
    assert manager.ran == ["legendary update"]
    assert (root / lu.EXE_NAME).read_bytes() == NEW


def test_ensure_current_installs_a_missing_copy(root):
    assert lu.ensure_current(str(root), None, FakeSession()) == "Updated Legendary to version 0.21.1."
    assert (root / lu.EXE_NAME).read_bytes() == NEW


def test_ensure_current_does_nothing_when_current(root):
    (root / lu.EXE_NAME).write_bytes(NEW)
    session = FakeSession()
    assert lu.ensure_current(str(root), FakeManager(), session) is None
    assert session.urls == []


def test_ensure_current_waits_while_the_manager_is_busy(root):
    (root / lu.EXE_NAME).write_bytes(b"old")
    manager, session = FakeManager(busy="update"), FakeSession()
    assert lu.ensure_current(str(root), manager, session) is None
    assert manager.ran == [] and session.urls == []
    assert (root / lu.EXE_NAME).read_bytes() == b"old"


def test_ensure_current_reports_nothing_when_the_download_is_bad(root):
    (root / lu.EXE_NAME).write_bytes(b"old")
    assert lu.ensure_current(str(root), FakeManager(), FakeSession(body=b"bad")) is None
    assert (root / lu.EXE_NAME).read_bytes() == b"old"
    assert listing(root) == sorted([lu.EXE_NAME, lu.MANIFEST_COPY])


def test_ensure_current_with_the_real_manager_lock(root, monkeypatch):
    """_exclusive refuses when another operation holds the lock; ensure_current then reports nothing."""
    (root / lu.EXE_NAME).write_bytes(b"old")

    class Locked(FakeManager):
        def _exclusive(self, name, func):
            return OperationResult(False, "Another operation is already running")

    assert lu.ensure_current(str(root), Locked(), FakeSession()) is None
    assert (root / lu.EXE_NAME).read_bytes() == b"old"


def test_ensure_current_cleans_up_old_set_aside_copies(root):
    (root / lu.EXE_NAME).write_bytes(NEW)
    for name in (".old", ".1.old", ".7.old"):
        (root / (lu.EXE_NAME + name)).write_bytes(b"x")
    lu.ensure_current(str(root), None, FakeSession())
    assert listing(root) == sorted([lu.EXE_NAME, lu.MANIFEST_COPY])
