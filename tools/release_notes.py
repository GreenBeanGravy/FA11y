"""Release notes for an installer release: install instructions plus the
CHANGELOG.txt entries added since the previous release.

    python tools/release_notes.py [--previous-tag installer-v1.0.2] [--current-tag installer-v1.0.3] [--output notes.md]

Without --previous-tag, the newest "installer-v*" tag other than the
current one is used. An entry is new when its header line wasn't the top
entry of CHANGELOG.txt at the previous tag; when that can't be worked out,
only the top entry is used.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANGELOG = os.path.join(ROOT, "CHANGELOG.txt")
INSTALL = "Download Updater.exe, put it in an empty folder, and run it."
# "10/10/2026 #1 (19.0.0-beta.2, Beta branch):", "10/1/2026 #1:"
HEADER = re.compile(r"^\d{1,2}/\d{1,2}/\d{4} #\d+.*:\s*$")


def entries(text: str):
    """[(header, body lines)] in file order."""
    out = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if HEADER.match(line):
            out.append((line.strip(), []))
        elif out:
            out[-1][1].append(line.rstrip())
    return out


def new_entries(current: str, previous: str):
    """Entries of current above the one that topped previous (just the top one if unknown)."""
    now = entries(current)
    before = entries(previous)
    if not now:
        return []
    if before:
        top = before[0][0]
        for i, (header, _) in enumerate(now):
            if header == top:
                return now[:i] or now[:1]
    return now[:1]


def format_notes(selected) -> str:
    parts = [INSTALL, "", "## What's new", ""]
    for header, body in selected:
        lines = [ln for ln in body if ln.strip()]
        parts.append(f"**{header.rstrip(':')}**")
        parts.extend(lines)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def previous_tag(current: str) -> str:
    tags = [t for t in _git("tag", "--list", "installer-v*", "--sort=-v:refname").split() if t != current]
    return tags[0] if tags else ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--previous-tag", default=None)
    parser.add_argument("--current-tag", default="")
    parser.add_argument("--output", default="", help="write the notes to this file (UTF-8) instead of stdout")
    args = parser.parse_args(argv)

    with open(CHANGELOG, encoding="utf-8") as f:
        current = f.read()
    tag = previous_tag(args.current_tag) if args.previous_tag is None else args.previous_tag
    previous = ""
    if tag:
        try:
            previous = _git("show", f"{tag}:CHANGELOG.txt")
        except subprocess.CalledProcessError:
            previous = ""
    notes = format_notes(new_entries(current, previous))
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(notes)
    else:
        sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
