"""Read Fortnite's synced settings (ClientSettings.Sav) without the game: every scalar setting.

The file is a 16-byte ECFD header, then a zlib stream holding an Unreal save with tagged
properties (UE 5.4+ layout: name, type name with parameters, size, flags, value). This reader
scans for property tags and decodes bools, numbers, strings, names and enums. It only reads;
the game uploads this file to Epic's cloud, so editing it needs much more care.

    python tools/client_settings.py                 everything
    python tools/client_settings.py sensitiv sound  only names containing these words
"""
from __future__ import annotations

import glob
import os
import re
import struct
import sys
import zlib

TAG = re.compile(rb"(?s)(.{4})([A-Za-z_][A-Za-z0-9_]{1,80})\x00(.{4})([A-Za-z]+Property)\x00")


def load(path: str | None = None) -> bytes:
    path = path or glob.glob(os.path.join(os.environ["LOCALAPPDATA"], "FortniteGame", "Saved", "Cloud", "*",
                                          "ClientSettings.Sav"))[0]
    raw = open(path, "rb").read()
    if raw[:4] != b"ECFD":
        raise ValueError("not an ECFD settings file")
    return zlib.decompress(raw[16:])


def read_fstring(d: bytes, o: int):
    n = struct.unpack_from("<i", d, o)[0]
    o += 4
    if n == 0:
        return "", o
    if n < 0:  # utf-16
        s = d[o:o - n * 2].decode("utf-16-le", "replace").rstrip("\x00")
        return s, o - n * 2
    return d[o:o + n].decode("latin1").rstrip("\x00"), o + n


def read_type(d: bytes, o: int):
    """FPropertyTypeName: name, then that many inner type names. Returns (text, offset)."""
    name, o = read_fstring(d, o)
    count = struct.unpack_from("<i", d, o)[0]
    o += 4
    inner = []
    for _ in range(max(0, min(count, 8))):
        t, o = read_type(d, o)
        inner.append(t)
    return (f"{name}({', '.join(inner)})" if inner else name), o


def settings(d: bytes):
    out = []
    for m in TAG.finditer(d):
        name_len = struct.unpack("<i", m.group(1))[0]
        if name_len != len(m.group(2)) + 1 or name_len > 82:
            continue
        name = m.group(2).decode()
        try:
            ptype, o = read_type(d, m.start(3))
            size = struct.unpack_from("<i", d, o)[0]
            flags = d[o + 4]
            o += 5
            if flags & 0x01:
                o += 4  # array index
            if flags & 0x02:
                o += 16  # property guid
            value = decode(ptype, d, o, size, flags)
        except (struct.error, IndexError, UnicodeDecodeError):
            continue
        if value is not None:
            out.append((m.start(), name, ptype, value))
    return out


def decode(ptype: str, d: bytes, o: int, size: int, flags: int):
    base = ptype.split("(")[0]
    if base == "BoolProperty":
        return bool(flags & 0x10)
    if base == "FloatProperty" and size == 4:
        return round(struct.unpack_from("<f", d, o)[0], 4)
    if base == "DoubleProperty" and size == 8:
        return round(struct.unpack_from("<d", d, o)[0], 4)
    if base in ("IntProperty", "UInt32Property") and size == 4:
        return struct.unpack_from("<i" if base == "IntProperty" else "<I", d, o)[0]
    if base in ("Int64Property", "UInt64Property") and size == 8:
        return struct.unpack_from("<q", d, o)[0]
    if base in ("StrProperty", "NameProperty", "EnumProperty") and 4 <= size < 512:
        return read_fstring(d, o)[0]
    if base == "ByteProperty":
        if size == 1:
            return d[o]
        if 4 <= size < 512:
            return read_fstring(d, o)[0]
    return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    words = [w.lower() for w in sys.argv[1:]]
    for _, name, ptype, value in settings(load()):
        if words and not any(w in name.lower() for w in words):
            continue
        print(f"{name:55} {value!r:40} {ptype}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
