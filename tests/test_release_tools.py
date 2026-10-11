"""Tests for tools/bump_legendary.py and tools/check_version_bump.py."""
import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import bump_legendary as bl  # noqa: E402
import check_version_bump as cvb  # noqa: E402

SHA = "ab" * 32


def release(tag="0.22.0", assets=None):
    if assets is None:
        assets = [{"name": "legendary_linux_x86_64", "browser_download_url": "https://x/linux"},
                  {"name": "legendary_windows_x64.exe", "digest": f"sha256:{SHA}",
                   "browser_download_url": f"https://github.com/derrod/legendary/releases/download/{tag}/legendary_windows_x64.exe"}]
    return {"tag_name": tag, "assets": assets}


@pytest.fixture
def manifest_file(tmp_path, monkeypatch):
    with open(bl.MANIFEST, encoding="utf-8") as f:
        data = json.load(f)
    path = tmp_path / "manifest.json"
    path.write_bytes(json.dumps(data, indent=2).replace("\n", "\r\n").encode() + b"\r\n")
    monkeypatch.setattr(bl, "MANIFEST", str(path))
    monkeypatch.setattr(bl.read_manifest, "__defaults__", (str(path),))
    monkeypatch.setattr(bl.write_manifest, "__defaults__", (str(path),))
    return path


def test_the_windows_asset_and_its_digest_are_used():
    asset = bl.windows_asset(release())
    assert asset["name"] == "legendary_windows_x64.exe"
    assert bl.asset_sha256(asset, download=lambda url: pytest.fail("should not download")) == SHA


def test_an_asset_without_a_digest_is_downloaded_and_hashed():
    asset = {"name": "legendary.exe", "browser_download_url": "https://x/legendary.exe"}
    assert bl.asset_sha256(asset, download=lambda url: b"exe") == hashlib.sha256(b"exe").hexdigest()


def test_a_release_without_a_windows_build_is_refused():
    with pytest.raises(SystemExit, match="no Windows build"):
        bl.windows_asset(release(assets=[{"name": "legendary_macOS"}]))


def test_check_reports_a_newer_release(manifest_file, monkeypatch, capsys):
    monkeypatch.setattr(bl, "fetch_release", lambda tag="": release("0.22.0"))
    assert bl.main(["--check"]) == 1
    assert "0.22.0 is out (pinned: 0.21.1)" in capsys.readouterr().out
    monkeypatch.setattr(bl, "fetch_release", lambda tag="": release("0.21.1"))
    assert bl.main(["--check"]) == 0


def test_bump_rewrites_only_the_legendary_pin_and_keeps_line_endings(manifest_file, monkeypatch):
    before = json.loads(manifest_file.read_text(encoding="utf-8"))
    monkeypatch.setattr(bl, "fetch_release", lambda tag="": release("0.22.0"))
    assert bl.main([]) == 0
    raw = manifest_file.read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n")
    after = json.loads(raw)
    component = bl.legendary_component(after)
    assert component["version"] == "0.22.0"
    assert component["detect"]["file_sha256"] == SHA and component["download"]["sha256"] == SHA
    assert component["download"]["url"].endswith("/0.22.0/legendary_windows_x64.exe")
    others = lambda m: [c for c in m["components"] if c["id"] != "legendary"]
    assert others(after) == others(before) and after["sync"] == before["sync"]


def test_bumping_to_the_pinned_release_changes_nothing(manifest_file, monkeypatch):
    raw = manifest_file.read_bytes()
    monkeypatch.setattr(bl, "fetch_release", lambda tag="": release(
        "0.21.1", [{"name": "legendary_windows_x64.exe",
                    "digest": "sha256:6be77857dc0a6dd33ea7442ce8b5291944ec6da53757f81ca95b57ce794baf5b",
                    "browser_download_url": "https://github.com/derrod/legendary/releases/download/0.21.1/legendary_windows_x64.exe"}]))
    assert bl.main([]) == 0
    assert manifest_file.read_bytes() == raw


def test_the_shipped_manifest_round_trips_byte_for_byte():
    """bump_legendary rewrites the file with json.dumps(indent=2); any hand formatting would be lost."""
    with open(bl.MANIFEST, encoding="utf-8", newline="") as f:
        text = f.read().replace("\r\n", "\n")
    assert json.dumps(json.loads(text), indent=2) + "\n" == text


# --- check_version_bump -----------------------------------------------------

def test_matching_follows_the_updater_rules():
    exclude = cvb.load_exclude()
    assert cvb.matches(exclude, "tests/test_x.py")
    assert cvb.matches(exclude, "legendary.exe")
    assert cvb.matches(exclude, "installer/internal/swap/swap.go")
    assert not cvb.matches(exclude, "FA11y.py")
    assert not cvb.matches(exclude, "lib/fortnite/legendary_update.py")
    assert not cvb.matches(exclude, "ui/bin/FA11y.UI.dll")
    assert not cvb.matches(exclude, "testsuite.py")  # "tests/" is a folder prefix only


def test_shipped_changes_without_a_bump_warn(monkeypatch, capsys):
    monkeypatch.setattr(cvb, "changed_paths", lambda b, h: ["FA11y.py", "tests/test_x.py", ".github/workflows/a.yml"])
    assert cvb.main(["base"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("::warning::1 file(s)") and "FA11y.py" in out and "tests/" not in out
    assert cvb.main(["base", "--strict"]) == 1
    assert capsys.readouterr().out.startswith("::error::")


def test_a_bump_or_only_unshipped_changes_pass(monkeypatch, capsys):
    monkeypatch.setattr(cvb, "changed_paths", lambda b, h: ["FA11y.py", "VERSION"])
    assert cvb.main(["base", "--strict"]) == 0
    monkeypatch.setattr(cvb, "changed_paths", lambda b, h: ["tests/a.py", "tools/b.py", "installer/cmd/x.go"])
    assert cvb.main(["base", "--strict"]) == 0
    assert "::" not in capsys.readouterr().out


# --- release_notes ----------------------------------------------------------

import release_notes as rn  # noqa: E402

OLD = "10/7/2026 #1 (overhaul branch):\n- Social.\n\n10/3/2026 #1 (19.0.0-beta.1, Beta branch):\n- Window.\n"
NOW = ("10/10/2026 #2 (19.0.0-beta.3, Beta branch):\n- Second.\n\n"
       "10/10/2026 #1 (19.0.0-beta.2, Beta branch):\n- First.\n- More.\n\n" + OLD)


def test_notes_have_every_entry_since_the_previous_release():
    notes = rn.format_notes(rn.new_entries(NOW, OLD))
    assert notes.startswith(rn.INSTALL)
    assert "**10/10/2026 #2 (19.0.0-beta.3, Beta branch)**\n- Second." in notes
    assert "**10/10/2026 #1 (19.0.0-beta.2, Beta branch)**\n- First.\n- More." in notes
    assert "Social" not in notes and "Window" not in notes


def test_notes_fall_back_to_the_top_entry():
    assert [h for h, _ in rn.new_entries(NOW, "")] == ["10/10/2026 #2 (19.0.0-beta.3, Beta branch):"]
    assert [h for h, _ in rn.new_entries(NOW, "garbage")] == ["10/10/2026 #2 (19.0.0-beta.3, Beta branch):"]
    # Nothing new since the last release (re-tagging the same changelog): still show the top entry.
    assert [h for h, _ in rn.new_entries(OLD, OLD)] == ["10/7/2026 #1 (overhaul branch):"]


def test_the_real_changelog_parses_and_its_top_entry_has_bullets():
    with open(rn.CHANGELOG, encoding="utf-8") as f:
        top = rn.entries(f.read())[0]
    assert rn.HEADER.match(top[0]) and any(line.startswith("- ") for line in top[1])
