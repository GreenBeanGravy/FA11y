"""Find every way in or out of Fortnite: IPC imports and channel strings across its binaries.

Reads the files in FortniteGame\\Binaries\\Win64 on disk only. Close Fortnite first.

    python tools/ipc_recon.py imports        which module imports which IPC / accessibility API
    python tools/ipc_recon.py strings        pipe names, local URLs, ports, protocols, watched files
    python tools/ipc_recon.py all
"""
from __future__ import annotations

import mmap
import os
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

BIN = Path(r"C:\Program Files\Epic Games\Fortnite\FortniteGame\Binaries\Win64")

# API -> what it means as a channel.
APIS = {
    "CreateNamedPipeW": "named pipe server", "CreateNamedPipeA": "named pipe server",
    "ConnectNamedPipe": "named pipe server", "CallNamedPipeW": "named pipe client",
    "bind": "socket server", "listen": "socket server", "accept": "socket server",
    "WSAStartup": "sockets", "WinHttpWebSocketCompleteUpgrade": "websocket client",
    "HttpCreateServerSession": "http.sys server", "HttpAddUrlToUrlGroup": "http.sys server",
    "HttpReceiveHttpRequest": "http.sys server",
    "CreateFileMappingW": "shared memory", "CreateFileMappingA": "shared memory",
    "OpenFileMappingW": "shared memory", "OpenFileMappingA": "shared memory",
    "RegisterWindowMessageW": "window messages", "ChangeWindowMessageFilterEx": "window messages",
    "ReadDirectoryChangesW": "watched folder", "FindFirstChangeNotificationW": "watched folder",
    "UiaReturnRawElementProvider": "UI Automation provider (screen readers can read UI)",
    "UiaHostProviderFromHwnd": "UI Automation provider", "UiaRaiseAutomationEvent": "UI Automation events",
    "UiaClientsAreListening": "UI Automation", "UiaRaiseNotificationEvent": "UI Automation notifications",
    "CoRegisterClassObject": "COM server", "RegisterActiveObject": "COM running object",
    "CreateMailslotW": "mailslot", "DdeInitializeW": "DDE",
    "RegisterHotKey": "global hotkey", "SetWindowsHookExW": "input hook",
    "RegisterRawInputDevices": "raw input",
}

STRING_PATTERNS = {
    "pipe": r"\\\\\.\\pipe\\[\w\\%.\-{}]*",
    "local url": r"(?:https?|wss?)://(?:localhost|127\.0\.0\.1|\[::1\])[\w:/%.\-?=&{}]*",
    "protocol": r"com\.epicgames\.[\w.]+:(?://)?[\w/%.\-?=&{}]*|fortnite://[\w/%.\-?=&{}]*",
    "file channel": r"[\w]*(?:CommandLine|PartnerInfo|Ipc|IPC|Bridge|Remote|Inbox|Mailbox)\w*\.(?:txt|json|ini)",
    "shared memory": r"(?:Local|Global)\\[\w%.\-{}]+",
    "remote control": r"(?:RemoteControl|WebRemote|RemoteExecution|LiveLink|OSC|Telnet|DebugServer|"
                      r"ExternalApplicationCommand|ActivationProtocol|MessageBus|UdpMessaging|"
                      r"TcpMessaging|StorageServer|ZenServer|Insights|TraceHost)[\w.]*",
    "accessibility": r"(?:Accessib|Narrat|ScreenReader|UIAutomation|Uia)[\w.]*",
}


def pe_imports(raw: bytes):
    """[(dll, function)] from a PE's import table."""
    try:
        e = struct.unpack_from("<I", raw, 0x3C)[0]
        coff = e + 4
        nsec = struct.unpack_from("<H", raw, coff + 2)[0]
        opt = coff + 20
        st = opt + struct.unpack_from("<H", raw, coff + 16)[0]
        sects = []
        for i in range(nsec):
            o = st + i * 40
            vsz, vrva, rawsz, rawptr = struct.unpack_from("<IIII", raw, o + 8)
            sects.append((vrva, max(vsz, rawsz), rawptr, rawsz))

        def off(rva):
            for v, vs, rp, rs in sects:
                if v <= rva < v + vs and rva - v < rs:
                    return rp + rva - v
            return None

        def cstr(rva):
            o = off(rva)
            return raw[o:raw.index(b"\0", o)].decode("latin1") if o is not None else "?"

        out = []
        for dir_index in (1, 13):  # normal and delay-load imports
            rva = struct.unpack_from("<I", raw, opt + 112 + dir_index * 8)[0]
            o = off(rva) if rva else None
            while o is not None:
                if dir_index == 1:
                    ilt, _, _, name_rva, iat = struct.unpack_from("<IIIII", raw, o)
                    step = 20
                else:
                    _, name_rva, _, iat, ilt = struct.unpack_from("<IIIII", raw, o)[:5]
                    step = 32
                if not name_rva:
                    break
                dll = cstr(name_rva)
                t = off(ilt or iat)
                while t is not None:
                    v = struct.unpack_from("<Q", raw, t)[0]
                    if not v:
                        break
                    if not v >> 63:
                        out.append((dll, cstr((v & 0x7FFFFFFF) + 2)))
                    t += 8
                o += step
        return out
    except (struct.error, ValueError):
        return []


def modules():
    for p in sorted(BIN.iterdir()):
        if p.suffix.lower() in (".dll", ".exe"):
            yield p


def cmd_imports():
    found = defaultdict(set)
    for p in modules():
        for dll, fn in pe_imports(p.read_bytes()):
            if fn in APIS:
                found[(APIS[fn], fn)].add(p.name)
    for (meaning, fn), mods in sorted(found.items()):
        print(f"{meaning:52} {fn:32} {', '.join(sorted(mods))}")


def cmd_strings():
    compiled = {k: re.compile(v.encode()) for k, v in STRING_PATTERNS.items()}
    hits = defaultdict(lambda: defaultdict(set))
    for p in modules():
        with open(p, "rb") as f:
            try:
                m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            except ValueError:
                continue
            # utf-16 view: drop the zero bytes of ascii-range utf-16 text
            wide = re.sub(rb"([\x20-\x7e])\x00", rb"\1", m[:])
            for blob in (m, wide):
                for kind, rx in compiled.items():
                    for x in rx.finditer(blob):
                        s = x.group().decode("latin1")
                        if 4 <= len(s) <= 160:
                            hits[kind][s].add(p.name)
            m.close()
    for kind, strings in hits.items():
        print(f"\n===== {kind} ({len(strings)})")
        for s, mods in sorted(strings.items()):
            print(f"  {s:90} {', '.join(sorted(mods))[:80]}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("imports", "all"):
        cmd_imports()
    if cmd in ("strings", "all"):
        cmd_strings()


if __name__ == "__main__":
    main()
