"""Static recon of Fortnite's deep-link (named pipe) command parser.

Reads the UEFN editor DLLs on disk (the unpacked Fortnite game code). Never touches a running
game: close Fortnite first. Nothing here hooks a process or reads its memory.

    python tools/deeplink_recon.py strings TEXT [TEXT ...]   where a string lives (ascii and utf-16)
    python tools/deeplink_recon.py xrefs TEXT [TEXT ...]     functions that load that string
    python tools/deeplink_recon.py func TEXT|0xRVA [N]       disassemble the function holding it
    python tools/deeplink_recon.py calls TEXT|0xRVA          direct calls it makes, callees labelled
                                                             by the strings they load
    python tools/deeplink_recon.py callers TEXT|0xRVA        functions that call it directly
    python tools/deeplink_recon.py report                    every function loading a deep-link switch

Set FA11Y_RECON_DLL to read another module (for example the Engine DLL).

The first run indexes every RIP-relative load and direct call in .text and caches the index
under %TEMP%\\fa11y_deeplink_recon, keyed by the DLL's size and time. Later runs take seconds.
"""
from __future__ import annotations

import os
import re
import struct
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

BIN = Path(r"C:\Program Files\Epic Games\Fortnite\FortniteGame\Binaries\Win64")
DLL = Path(os.environ.get("FA11Y_RECON_DLL", BIN / "UnrealEditorFortnite-Common-Win64-Shipping.dll"))
CACHE = Path(os.environ.get("TEMP", ".")) / "fa11y_deeplink_recon"
NUL = b"\x00"

SWITCHES = ["IslandOverride", "IslandOverrides", "IslandOverrideOnFreshAccount", "browse", "SetInitialIsland",
            "evo_link", "evo/", "freshid", "src=", "pl=", "Version=", "Island=", "Region="]


def undecorate(name: str) -> str:
    """'?Find@FParse@@SA_NPEB_W0@Z' -> 'FParse::Find'. Enough to read a call."""
    special = re.match(r"\?\?([0-9A-Z_])([^@]+)@", name)
    if special:
        ops = {"0": "ctor", "1": "dtor", "4": "operator=", "A": "operator[]"}
        return f"{special.group(2)}::{ops.get(special.group(1), 'op' + special.group(1))}"
    plain = re.match(r"\?([^@?]+)@([^@]+)@", name)
    return f"{plain.group(2)}::{plain.group(1)}" if plain else name


class PE:
    def __init__(self, path: Path):
        self.path = path
        self.raw = path.read_bytes()
        raw = self.raw
        e = struct.unpack_from("<I", raw, 0x3C)[0]
        coff = e + 4
        nsec = struct.unpack_from("<H", raw, coff + 2)[0]
        self.opt = coff + 20
        st = self.opt + struct.unpack_from("<H", raw, coff + 16)[0]
        exc_rva, exc_size = struct.unpack_from("<II", raw, self.opt + 112 + 3 * 8)
        self.sects = []
        for i in range(nsec):
            o = st + i * 40
            name = raw[o:o + 8].rstrip(NUL).decode("latin1")
            vsz, vrva, rawsz, rawptr = struct.unpack_from("<IIII", raw, o + 8)
            self.sects.append((name, vrva, max(vsz, rawsz), rawptr, rawsz))
        self.text = next(s for s in self.sects if s[0] == ".text")
        pd = np.frombuffer(raw, dtype=np.uint32, count=exc_size // 4,
                           offset=self.rva2off(exc_rva)).reshape(-1, 3)
        self.pdata = pd[np.argsort(pd[:, 0])]
        self._imports = None

    def rva2off(self, rva: int):
        for _, v, vs, rp, rs in self.sects:
            if v <= rva < v + vs and rva - v < rs:
                return rp + (rva - v)
        return None

    def off2rva(self, off: int):
        for _, v, _, rp, rs in self.sects:
            if rp <= off < rp + rs:
                return v + (off - rp)
        return None

    def cstr(self, rva: int) -> str:
        o = self.rva2off(rva)
        return self.raw[o:self.raw.index(NUL, o)].decode("latin1")

    @property
    def imports(self) -> dict:
        """IAT slot rva -> 'Module!Class::Function'."""
        if self._imports is None:
            self._imports = {}
            imp_rva = struct.unpack_from("<I", self.raw, self.opt + 112 + 1 * 8)[0]
            off = self.rva2off(imp_rva)
            while off is not None:
                ilt, _, _, name_rva, iat = struct.unpack_from("<IIIII", self.raw, off)
                if not iat:
                    break
                dll = self.cstr(name_rva)
                short = dll.split("-")[1] if dll.count("-") >= 2 else dll
                thunk, slot = self.rva2off(ilt or iat), iat
                while thunk is not None:
                    v = struct.unpack_from("<Q", self.raw, thunk)[0]
                    if not v:
                        break
                    name = f"#{v & 0xFFFF}" if v >> 63 else self.cstr((v & 0x7FFFFFFF) + 2)
                    self._imports[slot] = f"{short}!{undecorate(name)}"
                    thunk += 8
                    slot += 8
                off += 20
        return self._imports

    # functions ----------------------------------------------------------------------------
    def _primary(self, idx: int) -> int:
        """Follow chained unwind info (pieces split off a function) back to the main entry."""
        for _ in range(8):
            unwind = int(self.pdata[idx, 2])
            off = self.rva2off(unwind & ~1)
            if off is None or not (self.raw[off] >> 3) & 0x4:  # UNW_FLAG_CHAININFO
                return idx
            count = self.raw[off + 2]
            parent = struct.unpack_from("<I", self.raw, off + 4 + ((count + 1) & ~1) * 2)[0]
            j = int(np.searchsorted(self.pdata[:, 0], parent))
            if j >= len(self.pdata) or self.pdata[j, 0] != parent:
                return idx
            idx = j
        return idx

    def func_of(self, rva: int):
        """(start, end) of the function holding rva."""
        i = int(np.searchsorted(self.pdata[:, 0], rva, side="right")) - 1
        if i < 0 or not (self.pdata[i, 0] <= rva < self.pdata[i, 1]):
            return None
        p = self._primary(i)
        return int(self.pdata[p, 0]), int(self.pdata[p, 1])

    # strings ------------------------------------------------------------------------------
    def find_strings(self, text: str):
        """[(rva, encoding, whole string)] for every string containing text."""
        hits = set()
        for enc, unit in (("ascii", 1), ("utf-16-le", 2)):
            zero = NUL * unit
            for m in re.finditer(re.escape(text.encode(enc)), self.raw):
                b = m.start()
                while b - unit >= 0 and self.raw[b - unit:b] != zero and m.start() - b < 400:
                    b -= unit
                e = m.end()
                while self.raw[e:e + unit] != zero and e - m.end() < 400:
                    e += unit
                rva = self.off2rva(b)
                if rva is not None:
                    hits.add((rva, enc, self.raw[b:e].decode(enc, "replace")))
        return sorted(hits)

    def string_at(self, rva: int):
        off = self.rva2off(rva)
        if off is None:
            return None
        chunk = self.raw[off:off + 512]
        if len(chunk) > 3 and chunk[1] == 0 and 0x20 <= chunk[0] < 0x7F and chunk[3] == 0:
            end = 0
            while end + 1 < len(chunk) and chunk[end:end + 2] != NUL * 2:
                end += 2
            s = chunk[:end].decode("utf-16-le", "replace")
            if len(s) >= 1 and all(32 <= ord(c) < 127 for c in s):
                return 'u"' + s + '"'
        end = chunk.find(NUL)
        if end >= 3 and all(32 <= c < 127 for c in chunk[:end]):
            return '"' + chunk[:end].decode("ascii") + '"'
        return None


# indexes ---------------------------------------------------------------------------------------

def _cache(p: PE, kind: str, build):
    st = p.path.stat()
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{p.path.stem}-{st.st_size}-{int(st.st_mtime)}-{kind}.npz"
    if path.exists():
        d = np.load(path)
        return d["a"], d["b"]
    a, b = build()
    np.savez(path, a=a, b=b)
    return a, b


def _text(p: PE):
    _, trva, _, toff, trawsz = p.text
    return trva, np.frombuffer(p.raw, dtype=np.uint8, count=trawsz, offset=toff)


def _rel32(a, idx):
    d = (a[idx].astype(np.int64) | (a[idx + 1].astype(np.int64) << 8)
         | (a[idx + 2].astype(np.int64) << 16) | (a[idx + 3].astype(np.int64) << 24))
    return d.astype(np.uint32).view(np.int32).astype(np.int64)


@lru_cache(maxsize=None)
def rip_index():
    """(instruction rva, target rva), sorted by target, for LEA/MOV reg,[rip+disp32]."""
    p = pe()

    def build():
        trva, a = _text(p)
        rex = np.flatnonzero((a[:-7] == 0x48) | (a[:-7] == 0x4C))
        ins_all, tgt_all = [], []
        for op in (0x8D, 0x8B):
            idx = rex[(a[rex + 1] == op) & ((a[rex + 2] & 0xC7) == 0x05)]
            ins = trva + idx.astype(np.int64)
            ins_all.append(ins)
            tgt_all.append(ins + 7 + _rel32(a, idx + 3))
        ins, tgt = np.concatenate(ins_all), np.concatenate(tgt_all)
        order = np.argsort(tgt, kind="stable")
        return ins[order], tgt[order]

    return _cache(p, "rip", build)


@lru_cache(maxsize=None)
def call_index():
    """(call rva, target rva), sorted by call rva, for E8 calls landing on a function start."""
    p = pe()

    def build():
        trva, a = _text(p)
        idx = np.flatnonzero(a[:-5] == 0xE8)
        src = trva + idx.astype(np.int64)
        dst = src + 5 + _rel32(a, idx + 1)
        ok = np.isin(dst, p.pdata[:, 0].astype(np.int64))
        return src[ok], dst[ok]

    return _cache(p, "call", build)


@lru_cache(maxsize=None)
def pe() -> PE:
    return PE(DLL)


def _direct_xrefs(rva: int):
    ins, tgt = rip_index()
    lo, hi = np.searchsorted(tgt, rva), np.searchsorted(tgt, rva, side="right")
    return [int(x) for x in ins[lo:hi]]


def xrefs_to(rva: int):
    """Code loading rva, or, for log formats, loading the static log record that points at it
    (UE_LOG keeps the format in a record; the code loads the record, not the string)."""
    direct = _direct_xrefs(rva)
    if direct:
        return direct
    p = pe()
    base = struct.unpack_from("<Q", p.raw, p.opt + 24)[0]
    out = []
    for m in re.finditer(re.escape(struct.pack("<Q", base + rva)), p.raw):
        slot = p.off2rva(m.start())
        if slot is not None:
            out += _direct_xrefs(slot)
    return out


def strings_in(start: int, end: int):
    """Strings a function loads, in address order."""
    p = pe()
    ins, tgt = rip_index()
    sel = (ins >= start) & (ins < end)
    out = []
    for i, t in sorted(zip(ins[sel].tolist(), tgt[sel].tolist())):
        s = p.string_at(int(t))
        if s:
            out.append((i, s))
    return out


@lru_cache(maxsize=None)
def label(func_start: int, limit: int = 3) -> str:
    f = pe().func_of(func_start)
    if not f:
        return ""
    return ", ".join(list(dict.fromkeys(s for _, s in strings_in(*f)))[:limit])


def log_format(rva: int):
    """'log: <format>' when rva is a static log record whose first field points at a string."""
    p = pe()
    off = p.rva2off(rva)
    if off is None or off + 8 > len(p.raw):
        return None
    base = struct.unpack_from("<Q", p.raw, p.opt + 24)[0]
    target = struct.unpack_from("<Q", p.raw, off)[0] - base
    if not 0 < target < 1 << 32:
        return None
    s = p.string_at(int(target))
    return f"log: {s}" if s else None


def disasm(start: int, end: int, limit: int = 4000):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    p = pe()
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    off = p.rva2off(start)
    for n, insn in enumerate(md.disasm(p.raw[off:off + (end - start)], start)):
        if n >= limit:
            break
        note = ""
        m = re.search(r"\[rip ([+-]) 0x([0-9a-f]+)\]", insn.op_str)
        if m:
            t = insn.address + insn.size + int(m.group(2), 16) * (1 if m.group(1) == "+" else -1)
            note = p.string_at(t) or p.imports.get(t) or log_format(t) or f"-> {t:#x}"
        elif insn.mnemonic in ("call", "jmp") and insn.op_str.startswith("0x"):
            t = int(insn.op_str, 16)
            if p.func_of(t) and p.func_of(t)[0] == t:
                note = label(t)
        yield insn.address, insn.mnemonic, insn.op_str, note


# commands ------------------------------------------------------------------------------------

def resolve(arg: str) -> int:
    if arg.lower().startswith("0x"):
        return int(arg, 16)
    hits = pe().find_strings(arg)
    for rva, _, _ in [h for h in hits if h[2] == arg] or hits:
        for x in xrefs_to(rva):
            f = pe().func_of(x)
            if f:
                return f[0]
    raise SystemExit(f"no function loads {arg!r}")


def cmd_strings(args):
    for a in args:
        for rva, enc, s in pe().find_strings(a):
            print(f"{rva:#010x} {enc:9} {s[:160]!r}  xrefs={len(xrefs_to(rva))}")


def cmd_xrefs(args):
    p = pe()
    for a in args:
        print(f"== {a!r}")
        for rva, enc, s in p.find_strings(a):
            for x in xrefs_to(rva):
                f = p.func_of(x)
                where = f"func {f[0]:#x}-{f[1]:#x}" if f else "?"
                print(f"  {enc:9} {s[:60]!r:64} at {x:#x} in {where}")


def cmd_func(args):
    start = resolve(args[0])
    # Leaf functions have no unwind entry: read until the next one starts.
    f = pe().func_of(start) or (start, int(pe().pdata[np.searchsorted(pe().pdata[:, 0], start), 0]))
    n = int(args[1]) if len(args) > 1 else 4000
    print(f"== func {f[0]:#x}-{f[1]:#x} ({f[1] - f[0]} bytes)")
    for addr, mn, ops, note in disasm(*f, limit=n):
        print(f"{addr:#010x}  {mn:7} {ops:48} {('; ' + note) if note else ''}")


def cmd_calls(args):
    f = pe().func_of(resolve(args[0]))
    src, dst = call_index()
    sel = (src >= f[0]) & (src < f[1])
    print(f"== calls from {f[0]:#x}")
    for s, d in zip(src[sel].tolist(), dst[sel].tolist()):
        print(f"  {s:#x} -> {d:#x}  {label(d)}")


def cmd_callers(args):
    target = pe().func_of(resolve(args[0]))[0]
    src, dst = call_index()
    print(f"== callers of {target:#x}")
    for s in src[dst == target].tolist():
        f = pe().func_of(s)
        print(f"  {s:#x} in {f[0]:#x}  {label(f[0]) if f else ''}")


def cmd_report(_args):
    p = pe()
    funcs = {}
    for sw in SWITCHES:
        for rva, _, s in p.find_strings(sw):
            if s != sw:
                continue
            for x in xrefs_to(rva):
                f = p.func_of(x)
                if f:
                    funcs.setdefault(f, set()).add(sw)
    print("== functions loading deep-link switch strings")
    for f, sws in sorted(funcs.items()):
        print(f"  {f[0]:#x}-{f[1]:#x} ({f[1] - f[0]:6} bytes): {sorted(sws)}")
    for f in sorted(funcs):
        print(f"\n== strings in {f[0]:#x}")
        for i, s in strings_in(*f):
            print(f"  {i:#x} {s[:140]}")


COMMANDS = {"strings": cmd_strings, "xrefs": cmd_xrefs, "func": cmd_func, "calls": cmd_calls,
            "callers": cmd_callers, "report": cmd_report}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        raise SystemExit(__doc__)
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
