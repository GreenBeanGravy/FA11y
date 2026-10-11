"""Check for, and pin, a newer Legendary release in installer/manifest.json.

FA11y installs legendary.exe from the exact release the manifest pins
(URL + SHA-256), and FA11y replaces any other copy with it on start
(lib/fortnite/legendary_update.py). This script moves the pin:

    python tools/bump_legendary.py --check   # exit 1 and say so when a newer release exists
    python tools/bump_legendary.py           # pin the latest release
    python tools/bump_legendary.py 0.21.1    # pin a given release

The SHA-256 comes from the digest GitHub records for the release asset; when
a release has none, the asset is downloaded and hashed. Test the new
legendary.exe (sign in, list, install, update, launch) before committing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "installer", "manifest.json")
REPO = "derrod/legendary"
API = f"https://api.github.com/repos/{REPO}/releases"
COMPONENT_ID = "legendary"
# Release asset names Legendary has used for the Windows build, newest first.
ASSET_NAMES = ("legendary_windows_x64.exe", "legendary.exe")


def _get(url: str) -> bytes:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "FA11y-bump-legendary"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as r:
        return r.read()


def fetch_release(tag: str = "") -> dict:
    url = f"{API}/tags/{tag}" if tag else f"{API}/latest"
    return json.loads(_get(url))


def version_key(version: str):
    return tuple(int(n) for n in re.findall(r"\d+", version))


def windows_asset(release: dict) -> dict:
    assets = {a.get("name"): a for a in release.get("assets") or []}
    for name in ASSET_NAMES:
        if name in assets:
            return assets[name]
    raise SystemExit(f"Legendary {release.get('tag_name')} has no Windows build "
                     f"(assets: {', '.join(sorted(assets)) or 'none'})")


def asset_sha256(asset: dict, download=_get) -> str:
    digest = str(asset.get("digest") or "")
    if digest.startswith("sha256:") and len(digest) == len("sha256:") + 64:
        return digest[len("sha256:"):].lower()
    return hashlib.sha256(download(asset["browser_download_url"])).hexdigest()


def legendary_component(manifest: dict) -> dict:
    for component in manifest.get("components") or []:
        if component.get("id") == COMPONENT_ID:
            return component
    raise SystemExit(f"{MANIFEST} has no '{COMPONENT_ID}' component")


def pin(manifest: dict, version: str, url: str, sha256: str) -> bool:
    """Point the legendary component at a release. Returns whether anything changed."""
    component = legendary_component(manifest)
    before = json.dumps(component, sort_keys=True)
    component["version"] = version
    component.setdefault("detect", {})["file_sha256"] = sha256
    component.setdefault("download", {}).update({"url": url, "sha256": sha256})
    return json.dumps(component, sort_keys=True) != before


def read_manifest(path: str = MANIFEST):
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    return json.loads(text), ("\r\n" if "\r\n" in text else "\n")


def write_manifest(manifest: dict, newline: str, path: str = MANIFEST) -> None:
    text = json.dumps(manifest, indent=2) + "\n"
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace("\n", newline))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version", nargs="?", default="", help="release tag to pin (default: the latest release)")
    parser.add_argument("--check", action="store_true", help="only report whether a newer release exists")
    args = parser.parse_args(argv)

    manifest, newline = read_manifest()
    pinned = str(legendary_component(manifest).get("version") or "")
    release = fetch_release(args.version)
    latest = str(release.get("tag_name") or "").lstrip("v")

    if args.check:
        if pinned and version_key(latest) <= version_key(pinned):
            print(f"Legendary {pinned} is pinned; the latest release is {latest}.")
            return 0
        print(f"Legendary {latest} is out (pinned: {pinned or 'none'}). "
              f"Run: python tools/bump_legendary.py {latest}")
        return 1

    asset = windows_asset(release)
    sha = asset_sha256(asset)
    if pin(manifest, latest, asset["browser_download_url"], sha):
        write_manifest(manifest, newline)
        print(f"Pinned Legendary {latest}: {asset['browser_download_url']} sha256 {sha}")
    else:
        print(f"Legendary {latest} is already pinned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
