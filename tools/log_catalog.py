"""Catalogue what Fortnite's log tells an outside program: categories, how often, and example lines.

    python tools/log_catalog.py                    the current FortniteGame.log
    python tools/log_catalog.py path\\to\\file.log
    python tools/log_catalog.py --grep invite     only categories with lines matching a word

Each category shows its line count and up to three distinct example messages with numbers and ids
blanked out, so similar lines group together.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict

LOG = os.path.join(os.environ.get("LOCALAPPDATA", ""), "FortniteGame", "Saved", "Logs", "FortniteGame.log")
LINE = re.compile(r"^\[[^\]]*\]\[[^\]]*\](\w+):\s?(?:(Verbose|VeryVerbose|Display|Warning|Error):\s)?(.*)$")
IDS = re.compile(r"[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f-]{27}|0x[0-9a-fA-F]+|\d+(?:\.\d+)?")


def shape(message: str) -> str:
    return IDS.sub("#", message)[:160]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=LOG)
    ap.add_argument("--grep")
    ap.add_argument("--examples", type=int, default=3)
    args = ap.parse_args()

    counts: Counter = Counter()
    shapes: dict = defaultdict(Counter)
    with open(args.path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = LINE.match(line.rstrip("\n"))
            if not m:
                continue
            category, _, message = m.groups()
            counts[category] += 1
            shapes[category][shape(message)] += 1

    want = re.compile(args.grep, re.I) if args.grep else None
    for category, n in counts.most_common():
        examples = [s for s, _ in shapes[category].most_common() if not want or want.search(s)]
        if want and not examples and not want.search(category):
            continue
        print(f"{category:40} {n:7} lines, {len(shapes[category]):5} kinds")
        for s in examples[:args.examples]:
            print(f"      {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
