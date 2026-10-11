"""Warn when files users receive change without a VERSION bump.

Updater.exe up to installer-v1.0.2 decides "FA11y is up to date" by
comparing VERSION alone, so changes pushed without a bump never reach
users of those updaters. Newer updaters also compare the files themselves,
but until every install has one, a bump is what ships a change.

    python tools/check_version_bump.py <base-commit> [<head-commit>] [--strict]

Lists the changed paths the updater installs (everything not excluded by
installer/manifest.json's sync rules). Exit code 1 only with --strict.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "installer", "manifest.json")


def matches(patterns, path: str) -> bool:
    """The updater's rule (installer/internal/manifest matchAny): "dir/" is a prefix, else exact."""
    for p in patterns:
        if p.endswith("/") and path.startswith(p) or path == p:
            return True
    return False


def load_exclude(path: str = MANIFEST):
    with open(path, encoding="utf-8") as f:
        return list((json.load(f).get("sync") or {}).get("exclude") or [])


def shipped(changed, exclude):
    return [p for p in changed if p != "VERSION" and not matches(exclude, p)]


def changed_paths(base: str, head: str):
    out = subprocess.run(["git", "diff", "--name-only", base, head], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base")
    parser.add_argument("head", nargs="?", default="HEAD")
    parser.add_argument("--strict", action="store_true", help="exit 1 instead of only warning")
    args = parser.parse_args(argv)

    changed = changed_paths(args.base, args.head)
    files = shipped(changed, load_exclude())
    if not files or "VERSION" in changed:
        print(f"{len(files)} installed file(s) changed; VERSION {'changed' if 'VERSION' in changed else 'unchanged'}.")
        return 0
    listed = ", ".join(files[:10]) + (f" and {len(files) - 10} more" if len(files) > 10 else "")
    level = "error" if args.strict else "warning"
    print(f"::{level}::{len(files)} file(s) users receive changed without a VERSION bump, so "
          f"updaters before installer-v1.0.3 won't install them: {listed}")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
