"""Tests for lib.fortnite.legendary_manager (no real legendary / Fortnite is touched)."""
import configparser
import json
import os
import sys
import textwrap
import threading
import time

import psutil
import pytest

from lib.fortnite import legendary_manager as lm
from lib.fortnite.legendary_manager import (
    CaptureResult,
    FortniteManager,
    LaunchOptions,
    ProgressParser,
    find_egl_fortnite,
)

# Lines exactly as legendary 0.20.34 formats them (downloader/mp/manager.py, cli.py).
PROGRESS = "[DLManager] INFO: = Progress: 12.34% (123/1000), Running for 00:01:02, ETA: 00:07:30"
DOWNLOADED = "[DLManager] INFO:  - Downloaded: 4198.40 MiB, Written: 4300.00 MiB"
CACHE = "[DLManager] INFO:  - Cache usage: 512.00 MiB, active tasks: 16"
SPEED = "[DLManager] INFO:  + Download\t- 52.10 MiB/s (raw) / 80.00 MiB/s (decompressed)"
DISK = "[DLManager] INFO:  + Disk\t- 90.00 MiB/s (write) / 0.00 MiB/s (read)"
DL_SIZE = "[cli] INFO: Download size: 11059.20 MiB (Compression savings: 31.0%)"
VERIFY = "Verification progress: 123/456 (27.0%) [85.3 MiB/s]\t"


@pytest.fixture(autouse=True)
def _fortnite_not_running(monkeypatch):
    monkeypatch.setattr(lm, "is_fortnite_running", lambda: False)


# -- progress parsing ------------------------------------------------------

def test_download_progress_message():
    parser = ProgressParser("Downloading")
    assert parser.feed(DL_SIZE) is None
    pct, msg = parser.feed(PROGRESS)
    assert pct == pytest.approx(12.34)
    assert msg.startswith("Downloading:")
    assert parser.feed(DOWNLOADED) is None
    assert parser.feed(CACHE) is None
    pct, msg = parser.feed(SPEED)
    assert pct == pytest.approx(12.34)
    assert msg == "Downloading: 4.1 GB of 10.8 GB, 52 MB/s, ETA 0:07:30"
    assert parser.feed(DISK) is None


def test_verify_progress_line():
    pct, msg = ProgressParser("Verifying").feed(VERIFY)
    assert pct == pytest.approx(27.0)
    assert "123 of 456" in msg and "85 MB/s" in msg


def test_info_lines_become_message_only():
    parser = ProgressParser()
    assert parser.feed("[cli] INFO: Preparing download for \"Fortnite\" (Fortnite)...") == (
        None, "Preparing download for \"Fortnite\" (Fortnite)...")
    assert parser.feed("[DLManager] INFO: something internal") is None
    assert parser.feed("random text") is None


def test_iter_output_lines_splits_on_carriage_return():
    import io
    stream = io.BufferedReader(io.BytesIO(b"one\rtwo\r\nthree\n\nfour"))
    assert list(lm._iter_output_lines(stream)) == ["one", "two", "three", "four"]


# -- launch options ----------------------------------------------------------

@pytest.mark.parametrize("opts, expected", [
    (LaunchOptions(), []),
    (LaunchOptions(api="dx11"), ["-dx11"]),
    (LaunchOptions(api="dx12"), ["-dx12"]),
    (LaunchOptions(api="performance"), ["-FeatureLevelES31"]),
    (LaunchOptions(api="bogus"), []),
    (LaunchOptions(api="dx12", skip_splash=True), ["-dx12", "-NOSPLASH"]),
    (LaunchOptions(extra="""-foo=bar "a b" 'c d'"""), ["-foo=bar", "a b", "c d"]),
    (LaunchOptions(api="dx11", skip_splash=True, extra="-x -y"), ["-dx11", "-NOSPLASH", "-x", "-y"]),
    (LaunchOptions(extra='-bad "unterminated'), ["-bad", '"unterminated']),
])
def test_launch_options_to_args(opts, expected):
    assert opts.to_args() == expected


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    path = tmp_path / "config.txt"

    def read(*_a, **_k):
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.optionxform = str
        if path.exists():
            cfg.read(path, encoding="utf-8")
        return cfg

    def write(cfg):
        with open(path, "w", encoding="utf-8") as handle:
            cfg.write(handle)
        return True

    monkeypatch.setattr(lm, "_read_cfg", read)
    monkeypatch.setattr(lm, "_write_cfg", write)
    return path


def test_launch_options_defaults_without_section(temp_config):
    assert lm.load_launch_options() == LaunchOptions()


def test_launch_options_config_round_trip(temp_config):
    opts = LaunchOptions(api="dx12", skip_splash=True, extra='-ini:"a b" -x%y')
    assert lm.save_launch_options(opts)
    text = temp_config.read_text(encoding="utf-8")
    assert "[Fortnite]" in text
    assert 'LaunchAPI = dx12 "' in text and 'SkipSplash = true "' in text
    assert lm.load_launch_options() == opts
    # Empty extra args keep the `"description"` only form and load as empty.
    assert lm.save_launch_options(LaunchOptions())
    assert lm.load_launch_options() == LaunchOptions()


def test_launch_options_invalid_stored_api(temp_config):
    temp_config.write_text('[Fortnite]\nLaunchAPI = vulkan "x"\nSkipSplash = TRUE "x"\n', encoding="utf-8")
    loaded = lm.load_launch_options()
    assert loaded.api == "default" and loaded.skip_splash is True


# -- EGL manifests -------------------------------------------------------------

def test_find_egl_fortnite(tmp_path):
    manifests = tmp_path / "Manifests"
    manifests.mkdir()
    game_dir = tmp_path / "Epic Games" / "Fortnite"
    game_dir.mkdir(parents=True)
    (manifests / "AAA.item").write_text(json.dumps(
        {"AppName": "SomethingElse", "InstallLocation": str(tmp_path)}), encoding="utf-8")
    (manifests / "BBB.item").write_text("not json", encoding="utf-8")
    (manifests / "CCC.item").write_text(json.dumps(
        {"AppName": "Fortnite", "InstallLocation": str(game_dir), "AppVersionString": "++Fortnite+Release-1.0"}),
        encoding="utf-8")
    found = find_egl_fortnite(str(manifests))
    assert found is not None
    assert found.install_path == os.path.normpath(str(game_dir))
    assert found.version == "++Fortnite+Release-1.0"
    assert found.manifest_path.endswith("CCC.item")


def test_find_egl_fortnite_missing(tmp_path):
    assert find_egl_fortnite(str(tmp_path / "nope")) is None
    manifests = tmp_path / "m"
    manifests.mkdir()
    (manifests / "x.item").write_text(json.dumps(
        {"AppName": "Fortnite", "InstallLocation": str(tmp_path / "deleted")}), encoding="utf-8")
    assert find_egl_fortnite(str(manifests)) is None


# -- status() with a fake legendary ----------------------------------------------

def _fake_capture(installed=True, logged_in=True, remote="2.0", local="1.0"):
    calls = []

    def run(self, args, timeout=90.0):
        calls.append(list(args))
        if args[0] == "list-installed" and "--check-updates" not in args:
            data = [{"app_name": "Fortnite", "version": local, "install_path": "C:/Games/Fortnite",
                     "install_size": 123456, "needs_verification": False}] if installed else []
            return CaptureResult(0, "[cli] noise\n" + json.dumps(data))
        if args[0] == "list-installed":
            return CaptureResult(0, "[]")
        if args[0] == "status":
            return CaptureResult(0, json.dumps({"account": "Player" if logged_in else "<not logged in>"}))
        if args[0] == "info":
            return CaptureResult(0, json.dumps({"game": {"version": remote}, "install": {}, "manifest": {}}))
        return CaptureResult(1, "", "unexpected")

    return run, calls


def test_status_installed_update_available(monkeypatch):
    run, calls = _fake_capture()
    monkeypatch.setattr(FortniteManager, "_run_capture", run)
    monkeypatch.setattr(lm, "find_egl_fortnite", lambda *a, **k: None)
    mgr = FortniteManager(legendary_cmd=["fake"])
    st = mgr.status()
    assert st.installed and st.version == "1.0" and st.install_size_bytes == 123456
    assert st.install_path == "C:/Games/Fortnite"
    assert st.logged_in and st.account == "Player"
    assert st.update_available and st.remote_version == "2.0" and not st.update_checked
    assert st.managed_by == "legendary" and st.egl_install_path == ""
    assert ["list-installed", "--check-updates", "--json"] not in calls
    assert st.to_dict()["installed"] is True


def test_status_check_updates_and_up_to_date(monkeypatch):
    run, calls = _fake_capture(remote="1.0")
    monkeypatch.setattr(FortniteManager, "_run_capture", run)
    monkeypatch.setattr(lm, "find_egl_fortnite", lambda *a, **k: None)
    st = FortniteManager(legendary_cmd=["fake"]).status(check_updates=True)
    assert ["list-installed", "--check-updates", "--json"] in calls
    assert st.update_checked and not st.update_available


def test_status_egl_only_and_not_logged_in(monkeypatch):
    run, _ = _fake_capture(installed=False, logged_in=False)
    monkeypatch.setattr(FortniteManager, "_run_capture", run)
    monkeypatch.setattr(lm, "find_egl_fortnite",
                        lambda *a, **k: lm.EglInstall(install_path="D:/Epic/Fortnite", version="9"))
    monkeypatch.setattr(lm, "is_fortnite_running", lambda: True)
    st = FortniteManager(legendary_cmd=["fake"]).status()
    assert not st.installed and not st.logged_in
    assert st.managed_by == "egl" and st.egl_install_path == "D:/Epic/Fortnite"
    assert st.running


def test_status_nothing_installed(monkeypatch):
    run, _ = _fake_capture(installed=False)
    monkeypatch.setattr(FortniteManager, "_run_capture", run)
    monkeypatch.setattr(lm, "find_egl_fortnite", lambda *a, **k: None)
    st = FortniteManager(legendary_cmd=["fake"]).status()
    assert st.managed_by is None and not st.installed and not st.update_available


def test_status_legendary_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(lm, "find_egl_fortnite", lambda *a, **k: None)
    monkeypatch.setattr(lm.shutil, "which", lambda name: None)
    monkeypatch.chdir(tmp_path)
    st = FortniteManager(files_dir=str(tmp_path)).status()
    assert not st.legendary_available and "legendary.exe" in st.error


# -- long operations against a fake legendary process -------------------------------

FAKE_LEGENDARY = textwrap.dedent('''
    import sys, time, os
    args = sys.argv[1:]

    def out(text):
        sys.stdout.write(text + "\\n")
        sys.stdout.flush()

    cmd = [a for a in args if not a.startswith("-")][0]
    if cmd == "install":
        if "HANG" in args:
            out("[cli] INFO: pid=%d" % os.getpid())
            out("[DLManager] INFO: = Progress: 5.00% (5/100), Running for 00:00:01, ETA: 00:00:19")
            time.sleep(60)
        out("[cli] INFO: Download size: 1024.00 MiB (Compression savings: 0.0%)")
        for pct in (25.0, 100.0):
            out("[DLManager] INFO: = Progress: %.2f%% (1/4), Running for 00:00:01, ETA: 00:00:01" % pct)
            out("[DLManager] INFO:  - Downloaded: %.2f MiB, Written: 0.00 MiB" % (pct * 10.24))
            out("[DLManager] INFO:  + Download\\t- 50.00 MiB/s (raw) / 60.00 MiB/s (decompressed)")
        out("[cli] INFO: Finished installation process in 3.00 seconds.")
    elif cmd == "update":
        out("[cli] ERROR: Login failed! Cannot continue with download process.")
    elif cmd == "verify":
        sys.stdout.write("Verification progress: 1/2 (50.0%) [10.0 MiB/s]\\t\\r")
        sys.stdout.write("Verification progress: 2/2 (100.0%) [10.0 MiB/s]\\t\\n")
        sys.stdout.flush()
        if "CLEAN" in os.environ.get("FAKE_MODE", ""):
            out("[cli] INFO: Verification finished successfully.")
        else:
            out('[cli] ERROR: File is missing: "a.pak"')
            out("[cli] ERROR: Verification failed, 1 file(s) corrupted, 2 file(s) are missing.")
    elif cmd == "repair":
        out("[cli] INFO: Download size: 100.00 MiB (Compression savings: 0.0%)")
        out("[DLManager] INFO: = Progress: 100.00% (4/4), Running for 00:00:01, ETA: 00:00:00")
        out("[cli] INFO: Finished installation process in 1.00 seconds.")
    elif cmd == "uninstall":
        out("[cli] INFO: Removing x")
        out("[cli] WARNING: Removing game failed: PermissionError, please remove C:/x manually.")
''')


@pytest.fixture
def fake_mgr(tmp_path):
    script = tmp_path / "fake_legendary.py"
    script.write_text(FAKE_LEGENDARY, encoding="utf-8")
    return FortniteManager(legendary_cmd=[sys.executable, str(script)], files_dir=str(tmp_path))


def test_install_reports_progress(fake_mgr, tmp_path):
    updates = []
    result = fake_mgr.install(str(tmp_path), progress=lambda p, m: updates.append((p, m)))
    assert result.ok, result.message
    percents = [p for p, _ in updates if p is not None]
    assert percents[-1] == 100.0 and 25.0 in percents
    assert any("MB/s" in m for _, m in updates)
    assert fake_mgr.current_operation is None


def test_exit_code_zero_with_error_line_is_failure(fake_mgr):
    result = fake_mgr.update()
    assert not result.ok and not result.cancelled
    assert "not logged in" in result.message.lower()
    assert "Traceback" not in result.message


def test_verify_and_repair_finds_problems_then_repairs(fake_mgr, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "BROKEN")
    updates = []
    result = fake_mgr.verify_and_repair(progress=lambda p, m: updates.append((p, m)))
    assert result.ok, result.message
    assert result.data == {"repaired": True, "damaged": 1, "missing": 2}
    percents = [p for p, _ in updates if p is not None]
    assert percents == sorted(percents)  # gauge never goes backwards
    assert percents[-1] == 100.0


def test_verify_clean_skips_repair(fake_mgr, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "CLEAN")
    result = fake_mgr.verify_and_repair()
    assert result.ok and result.data == {"repaired": False}


def test_uninstall_warning_marker_is_failure(fake_mgr):
    result = fake_mgr.uninstall()
    assert not result.ok and "manually" in result.message


def test_refuses_when_fortnite_running(fake_mgr, monkeypatch):
    monkeypatch.setattr(lm, "is_fortnite_running", lambda: True)
    result = fake_mgr.update()
    assert not result.ok and "running" in result.message.lower()


def test_legendary_missing_returns_result(tmp_path, monkeypatch):
    monkeypatch.setattr(lm.shutil, "which", lambda name: None)
    monkeypatch.chdir(tmp_path)
    result = FortniteManager(files_dir=str(tmp_path)).install(str(tmp_path))
    assert not result.ok and "legendary.exe" in result.message


def test_cancel_terminates_process_tree_and_second_op_is_rejected(fake_mgr):
    seen = {}
    got_pid = threading.Event()
    cancel = threading.Event()

    def progress(percent, message):
        if message.startswith("pid="):
            seen["pid"] = int(message.split("=")[1])
            got_pid.set()

    results = []
    worker = threading.Thread(
        target=lambda: results.append(fake_mgr.install("HANG", progress=progress, cancel=cancel)))
    worker.start()
    assert got_pid.wait(15), "fake legendary never started"
    assert psutil.pid_exists(seen["pid"])

    busy = fake_mgr.update()
    assert not busy.ok and "already running" in busy.message

    started = time.time()
    cancel.set()
    worker.join(15)
    assert not worker.is_alive()
    assert time.time() - started < 10
    assert results[0].cancelled and not results[0].ok
    deadline = time.time() + 5
    while psutil.pid_exists(seen["pid"]) and time.time() < deadline:
        time.sleep(0.1)
    assert not psutil.pid_exists(seen["pid"])
    assert fake_mgr.current_operation is None


def test_launch_passes_extra_args(fake_mgr, tmp_path, monkeypatch):
    captured = {}

    class FakeProc:
        stdout = None
        returncode = 0

        def wait(self):
            return 0

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        import io
        proc = FakeProc()
        proc.stdout = io.BufferedReader(io.BytesIO(b"[cli] INFO: Launching Fortnite...\n"))
        return proc

    monkeypatch.setattr(lm.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(fake_mgr, "is_logged_in", lambda: True)
    done = threading.Event()
    result = fake_mgr.launch(["-dx11", "-NOSPLASH"], on_done=lambda r: done.set())
    assert result.ok
    assert done.wait(5)
    assert captured["cmd"][-5:-1] == ["launch", "Fortnite", "-dx11", "-NOSPLASH"]
    assert captured["cmd"][-1].startswith("-named_pipe=") and captured["cmd"][-1].endswith("\\Fortnite")
    assert captured["kwargs"]["stdin"] == lm.subprocess.DEVNULL
    assert captured["kwargs"]["creationflags"] & lm.CREATE_NO_WINDOW


def test_launch_signs_legendary_in_first(fake_mgr, monkeypatch):
    """Without a login, legendary launch crashes with "No saved credentials", so sign it in first."""
    codes = []
    monkeypatch.setattr(fake_mgr, "is_logged_in", lambda: False)
    monkeypatch.setattr(fake_mgr, "login_with_exchange_code",
                        lambda code: codes.append(code) or lm.OperationResult(False, "nope"))
    monkeypatch.setattr(lm.subprocess, "Popen", lambda *a, **k: pytest.fail("launched without a login"))
    results = []
    done = threading.Event()
    fake_mgr.launch([], on_done=lambda r: (results.append(r), done.set()), get_exchange_code=lambda: "abc")
    assert done.wait(5)
    assert codes == ["abc"]
    assert not results[0].ok and results[0].message == lm.NOT_SIGNED_IN


def test_crash_traceback_gives_its_exception():
    outcome = lm.RunOutcome(1, [
        "[cli] INFO: Logging in...",
        "Traceback (most recent call last):",
        '  File "legendary\\core.py", line 190, in _login',
        "ValueError: No saved credentials",
        "[2460] Failed to execute script 'cli' due to unhandled exception!",
    ])
    assert lm._friendly_error(outcome, "Launch failed.") == lm.NOT_SIGNED_IN
    outcome.lines[3] = "KeyError: 'Fortnite'"
    assert lm._friendly_error(outcome, "Launch failed.") == "KeyError: 'Fortnite'"


def test_get_manager_is_singleton():
    assert lm.get_manager() is lm.get_manager()
