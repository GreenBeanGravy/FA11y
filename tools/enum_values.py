"""Print a UE enum's names with their numeric values, read from the reflection tables on disk.

    python tools/enum_values.py EFortSidebarButtonType [EOtherEnum ...]
"""
import re
import struct
import sys

sys.path.insert(0, __import__("os").path.dirname(__file__))
import deeplink_recon as r  # noqa: E402


def values(enum: str):
    p = r.pe()
    base = struct.unpack_from("<Q", p.raw, p.opt + 24)[0]
    out = {}
    for m in re.finditer(re.escape(enum.encode()) + rb"::([A-Za-z_0-9]+)\x00", p.raw):
        rva = p.off2rva(m.start())
        for slot in re.finditer(re.escape(struct.pack("<Q", base + rva)), p.raw):
            value = struct.unpack_from("<q", p.raw, slot.start() + 8)[0]
            if -1 <= value < 1 << 16:
                out[m.group(1).decode()] = value
    return sorted(out.items(), key=lambda kv: kv[1])


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(name, ", ".join(f"{k}={v}" for k, v in values(name)))
