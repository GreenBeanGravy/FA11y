"""
ClientSettings.Sav cloud round-trip diagnostic.

Downloads the authenticated user's ``ClientSettings.Sav`` from Epic's
cloud storage, runs it through ``lib.clientsettings.parser.parse_file``
and ``serialize_file`` unchanged, and reports where the input and the
round-tripped output differ.

Fortnite currently rejects / overwrites our edits on next launch even
though a clean third-party ``.Sav`` uploaded byte-identically works
fine. That strongly implies the parse -> serialize round-trip isn't
lossless. This tool pinpoints exactly where it diverges.

Outputs under ``dev_tools/clientsettings_diag/``:

* ``cloud.sav``           — raw bytes downloaded from cloud
* ``cloud.decompressed.sav`` (if ECFD-wrapped) — the inner stream
* ``roundtrip.sav``       — our parse -> serialize of ``cloud.sav``
* ``roundtrip.decompressed.sav`` — inner stream after round-trip
* ``summary.txt``         — stats + first-divergence offset + context hex
* ``properties.json``     — the parsed property tree (via ``to_json``),
                            useful for spotting which keys were / weren't
                            parsed at all

Run this from the FA11y repo root *while FA11y is authenticated* — it
uses the same cached Epic token the Locker and STW tabs do::

    python dev_tools/clientsettings_roundtrip.py

If you want to include a trivial edit to see whether edits change the
divergence, add ``--edit MasterVolume=0.5`` (or any scalar property
that already exists).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import zlib
from pathlib import Path
from typing import Optional

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
os.chdir(_REPO_ROOT)

from lib.clientsettings.cloud import CloudStorage, CloudStorageError  # noqa: E402
from lib.clientsettings.parser import (  # noqa: E402
    parse_file,
    serialize_file,
    set_value,
    to_json,
)
from lib.clientsettings.sync import CLIENT_SETTINGS_FILENAME  # noqa: E402
from lib.utilities.epic_auth import get_epic_auth_instance  # noqa: E402


OUT_DIR = Path("dev_tools") / "clientsettings_diag"


def _hex_window(data: bytes, center: int, span: int = 32) -> str:
    """Hex dump of ``span`` bytes centered on ``center`` for readability."""
    start = max(0, center - span // 2)
    end = min(len(data), center + span // 2)
    return data[start:end].hex()


def _decompress_if_ecfd(data: bytes) -> tuple[bytes, bool]:
    if data[:4] == b"ECFD":
        return zlib.decompress(data[0x10:]), True
    return data, False


def _first_diff(a: bytes, b: bytes) -> Optional[int]:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    if len(a) != len(b):
        return n
    return None


def _apply_edit(parsed, edit_spec: str) -> None:
    """Parse ``Name=Value`` and call ``set_value``. Numeric/bool coerced."""
    if "=" not in edit_spec:
        raise SystemExit(f"--edit must be Name=Value, got {edit_spec!r}")
    name, _, raw = edit_spec.partition("=")
    raw = raw.strip()
    # Try coerce: bool, int, float, fall back to str
    val: object
    if raw.lower() in ("true", "false"):
        val = raw.lower() == "true"
    else:
        try:
            val = int(raw)
        except ValueError:
            try:
                val = float(raw)
            except ValueError:
                val = raw
    if not set_value(parsed.properties, name.strip(), val):
        raise SystemExit(f"property {name!r} not found in file")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--edit", default=None,
        help="Optional Name=Value edit to apply before re-serializing. "
             "Example: --edit MasterVolume=0.5",
    )
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("fetching cloud file…")
    auth = get_epic_auth_instance()
    if not auth or not auth.access_token or not auth.account_id:
        print("ERROR: not authenticated. Open FA11y and sign in first.",
              file=sys.stderr)
        return 2

    cloud = CloudStorage(auth)
    try:
        data = cloud.download(CLIENT_SETTINGS_FILENAME)
    except CloudStorageError as e:
        print(f"ERROR: cloud download failed: {e}", file=sys.stderr)
        return 2

    (OUT_DIR / "cloud.sav").write_bytes(data)
    inner, was_ecfd = _decompress_if_ecfd(data)
    if was_ecfd:
        (OUT_DIR / "cloud.decompressed.sav").write_bytes(inner)
    print(f"cloud file: {len(data)} bytes, ecfd={was_ecfd}, "
          f"inner={len(inner)} bytes")

    print("parsing…")
    parsed = parse_file(data)
    num_props = len(parsed.properties)
    print(f"  {num_props} top-level properties")

    (OUT_DIR / "properties.json").write_text(
        json.dumps(to_json(parsed), indent=2, default=str),
        encoding="utf-8",
    )

    if args.edit:
        print(f"applying edit: {args.edit}")
        _apply_edit(parsed, args.edit)

    print("re-serializing (round-trip)…")
    rt = serialize_file(parsed)
    (OUT_DIR / "roundtrip.sav").write_bytes(rt)
    rt_inner, rt_was_ecfd = _decompress_if_ecfd(rt)
    if rt_was_ecfd:
        (OUT_DIR / "roundtrip.decompressed.sav").write_bytes(rt_inner)

    # Summary
    outer_diff_off = _first_diff(data, rt)
    inner_diff_off = _first_diff(inner, rt_inner)

    lines = []
    lines.append(f"cloud file size:            {len(data)} bytes")
    lines.append(f"round-trip file size:       {len(rt)} bytes")
    lines.append(f"outer byte-identical:       {data == rt}")
    if outer_diff_off is not None:
        lines.append(f"outer first diff offset:    0x{outer_diff_off:x}")
        lines.append(
            f"  orig: {_hex_window(data, outer_diff_off)}"
        )
        lines.append(
            f"  ours: {_hex_window(rt, outer_diff_off)}"
        )
    lines.append("")
    lines.append(f"decompressed size (orig):   {len(inner)} bytes")
    lines.append(f"decompressed size (ours):   {len(rt_inner)} bytes")
    lines.append(f"inner byte-identical:       {inner == rt_inner}")
    if inner_diff_off is not None:
        lines.append(f"inner first diff offset:    0x{inner_diff_off:x}")
        lines.append(
            f"  orig: {_hex_window(inner, inner_diff_off)}"
        )
        lines.append(
            f"  ours: {_hex_window(rt_inner, inner_diff_off)}"
        )
    lines.append("")
    lines.append(f"top-level property count:   {num_props}")
    lines.append(
        "property names (first 40):  "
        + ", ".join(p.tag.name for p in parsed.properties[:40])
    )

    report = "\n".join(lines)
    (OUT_DIR / "summary.txt").write_text(report, encoding="utf-8")
    print()
    print(report)
    print()
    print(f"artifacts saved under {OUT_DIR}/")

    return 0 if inner == rt_inner else 1


if __name__ == "__main__":
    raise SystemExit(main())
