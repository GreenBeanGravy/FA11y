"""Build the Windows icon resource for FA11y_Launcher.exe and Updater.exe.

Reads assets/images/fa11y.ico and writes rsrc_windows_amd64.syso into
each Go command folder under installer/cmd. `go build` links any .syso
file in a package folder into the executable, so the icon needs no extra
build step or tool. Run this again after changing the icon:

    python tools/make_icon_syso.py

The .syso is a COFF object holding a .rsrc section with RT_ICON entries
(one per image in the .ico) and one RT_GROUP_ICON that lists them.
"""
from __future__ import annotations

import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICO = os.path.join(ROOT, "assets", "images", "fa11y.ico")
TARGETS = [os.path.join(ROOT, "installer", "cmd", name, "rsrc_windows_amd64.syso")
           for name in ("launcher", "updater")]

RT_ICON = 3
RT_GROUP_ICON = 14
LANG_EN_US = 0x0409
IMAGE_REL_AMD64_ADDR32NB = 3


def read_ico(path):
    """[(14-byte group entry without the id, image bytes), ...]"""
    data = open(path, "rb").read()
    _reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    if kind != 1:
        raise ValueError(f"{path} is not an icon file")
    images = []
    for index in range(count):
        width, height, colours, reserved, planes, bits, size, offset = struct.unpack_from(
            "<BBBBHHII", data, 6 + 16 * index)
        header = struct.pack("<BBBBHHI", width, height, colours, reserved, planes, bits, size)
        images.append((header, data[offset:offset + size]))
    return images


def directory(entries):
    """A resource directory table: 16-byte header plus 8-byte (id, offset) entries."""
    out = struct.pack("<IIHHHH", 0, 0, 0, 0, 0, len(entries))
    for ident, offset in entries:
        out += struct.pack("<II", ident, offset)
    return out


def build_rsrc(images):
    """Return (section bytes, offsets of data-entry RVA fields needing relocation)."""
    group = struct.pack("<HHH", 0, 1, len(images))
    for number, (header, _image) in enumerate(images, start=1):
        group += header + struct.pack("<H", number)
    # (type, id, data) in the order the tree lists them: types ascending, ids ascending.
    leaves = [(RT_ICON, number, image) for number, (_header, image) in enumerate(images, start=1)]
    leaves.append((RT_GROUP_ICON, 1, group))
    types = sorted({leaf[0] for leaf in leaves})

    def dir_size(count):
        return 16 + 8 * count

    # Sizes of each level, to work out offsets before writing anything.
    root_size = dir_size(len(types))
    type_sizes = {t: dir_size(sum(1 for leaf in leaves if leaf[0] == t)) for t in types}
    lang_size = dir_size(1)
    offset = root_size
    type_offsets = {}
    for t in types:
        type_offsets[t] = offset
        offset += type_sizes[t]
    lang_offsets = []
    for _leaf in leaves:
        lang_offsets.append(offset)
        offset += lang_size
    entry_offsets = []
    for _leaf in leaves:
        entry_offsets.append(offset)
        offset += 16
    data_offsets = []
    for _t, _i, payload in leaves:
        offset = (offset + 7) & ~7
        data_offsets.append(offset)
        offset += len(payload)

    SUBDIR = 0x80000000
    out = bytearray(directory([(t, type_offsets[t] | SUBDIR) for t in types]))
    for t in types:
        out += directory([(ident, lang_offsets[n] | SUBDIR)
                          for n, (leaf_type, ident, _p) in enumerate(leaves) if leaf_type == t])
    for n in range(len(leaves)):
        out += directory([(LANG_EN_US, entry_offsets[n])])
    relocations = []
    for n, (_t, _i, payload) in enumerate(leaves):
        relocations.append(len(out))
        out += struct.pack("<IIII", data_offsets[n], len(payload), 0, 0)
    for n, (_t, _i, payload) in enumerate(leaves):
        out += b"\0" * (data_offsets[n] - len(out))
        out += payload
    return bytes(out), relocations


def build_coff(section, relocations):
    header_size = 20 + 40
    raw_offset = header_size
    reloc_offset = raw_offset + len(section)
    symbol_offset = reloc_offset + 10 * len(relocations)
    file_header = struct.pack("<HHIIIHH", 0x8664, 1, 0, symbol_offset, 1, 0, 0)
    section_header = struct.pack("<8sIIIIIIHHI", b".rsrc", 0, 0, len(section), raw_offset,
                                 reloc_offset, 0, len(relocations), 0, 0x40000040)
    relocs = b"".join(struct.pack("<IIH", address, 0, IMAGE_REL_AMD64_ADDR32NB)
                      for address in relocations)
    # One symbol for the section itself, which the relocations refer to.
    symbol = struct.pack("<8sIhHBB", b".rsrc", 0, 1, 0, 3, 0)
    string_table = struct.pack("<I", 4)
    return file_header + section_header + section + relocs + symbol + string_table


def main() -> int:
    section, relocations = build_rsrc(read_ico(ICO))
    coff = build_coff(section, relocations)
    for target in TARGETS:
        with open(target, "wb") as f:
            f.write(coff)
        print(f"Wrote {os.path.relpath(target, ROOT)} ({len(coff)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
