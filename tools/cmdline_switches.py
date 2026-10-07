"""List the command-line switches Fortnite code reads: every FParse::Param / FParse::Value call
whose switch name is a string literal. Reads the UEFN DLLs on disk.

    python tools/cmdline_switches.py [Common|Engine]
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
import deeplink_recon as r  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    which = sys.argv[1] if len(sys.argv) > 1 else "Common"
    if which != "Common":
        r.DLL = r.BIN / f"UnrealEditorFortnite-{which}-Win64-Shipping.dll"
    p = r.pe()
    slots = {slot: name for slot, name in p.imports.items() if "FParse::" in name or "FCommandLine::" in name}
    _, trva, _, toff, trawsz = p.text
    text = p.raw[toff:toff + trawsz]
    found = {}
    for m in re.finditer(rb"\xff\x15", text):
        i = m.start()
        target = trva + i + 6 + struct.unpack_from("<i", text, i + 2)[0]
        fn = slots.get(target)
        if not fn:
            continue
        # The switch is the second argument: the nearest earlier lea rdx,[rip+x].
        for j in range(i - 3, max(i - 64, 0), -1):
            if text[j:j + 3] == b"\x48\x8d\x15":
                s = p.string_at(trva + j + 7 + struct.unpack_from("<i", text, j + 3)[0])
                if s:
                    found.setdefault(s, set()).add(fn.split("!")[1])
                break
    for s, fns in sorted(found.items(), key=lambda kv: kv[0].lower()):
        print(f"{s:60} {', '.join(sorted(fns))}")
    print(len(found), "switches")


if __name__ == "__main__":
    main()
