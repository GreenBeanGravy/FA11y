"""
Command-line interface for FA11y's ClientSettings.Sav integration.

Uses FA11y's cached EpicAuth so no separate login is needed. Run from the
repo root:

    python -m lib.clientsettings.cli <subcommand> [args]

Subcommands:
    list                        list files in cloud storage
    show [path]                 parse a local/cloud save and print summary
    diff                        structural diff: local vs cloud ClientSettings.Sav
    pull                        cloud -> local (requires game closed)
    push                        local -> cloud (Fortnite can be running)
    keybinds [sub_game]         print current bindings (default ESubGame::Athena)
    set-keybind ACTION KEY      set KeyBind1 of an action, push to cloud
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from lib.clientsettings.parser import parse_file, serialize_file
from lib.clientsettings.sync import (
    CLIENT_SETTINGS_FILENAME,
    ClientSettingsManager,
    locate_local,
)

logger = logging.getLogger(__name__)


def _cmd_list(args: argparse.Namespace, mgr: ClientSettingsManager) -> int:
    files = mgr.cloud.list_files(include_restricted=args.all)
    print(f"{len(files)} files on this Epic account:")
    for f in files:
        print(f"  {f.unique_filename:45s}  {f.length:>8d} B  {f.uploaded}")
    return 0


def _cmd_show(args: argparse.Namespace, mgr: ClientSettingsManager) -> int:
    if args.path:
        data = Path(args.path).read_bytes()
    else:
        data = mgr.local.primary.read_bytes()
    parsed = parse_file(data)

    print(f"was_compressed:   {parsed.was_compressed}")
    print(f"header bytes:     {len(parsed.stream.header_bytes)}")
    print(f"top-level props:  {len(parsed.stream.properties)}")

    interesting = [
        "MouseSensitivity", "UpgradedMouseSensitivityX", "UpgradedMouseSensitivityY",
        "FocalLength", "MasterVolume", "MusicVolume", "ChatVolume",
        "VoiceChatSetting", "VoiceChatMethod", "bEnableSubtitles",
        "SelectedRegionId", "InputPresetNameForAthena", "ControllerPlatform",
        "bSmartBuildEnabled", "EditButtonHoldTime", "bNewHitmarkersEnabled",
    ]
    print("\nCommonly-adjusted settings:")
    for k in interesting:
        v = mgr.get(parsed, k)
        if v is not None:
            print(f"  {k:32s} = {v!r}")
    return 0


def _cmd_diff(args: argparse.Namespace, mgr: ClientSettingsManager) -> int:
    d = mgr.compare()
    print(d.summary())
    if d.only_local:
        print("\nonly local:")
        for k in d.only_local:
            print(f"  {k}")
    if d.only_cloud:
        print("\nonly cloud:")
        for k in d.only_cloud:
            print(f"  {k}")
    if d.different:
        print(f"\n{len(d.different)} differences:")
        for row in d.different[:50]:
            print(f"  {row['name']}")
            loc = json.dumps(row['local'], default=str)[:160]
            rem = json.dumps(row['cloud'], default=str)[:160]
            print(f"    local: {loc}")
            print(f"    cloud: {rem}")
        if len(d.different) > 50:
            print(f"  ... ({len(d.different) - 50} more, use --all to show)")
    return 0


def _cmd_pull(args: argparse.Namespace, mgr: ClientSettingsManager) -> int:
    dest = mgr.pull_from_cloud(require_game_closed=not args.force)
    print(f"wrote cloud copy to {dest}")
    return 0


def _cmd_push(args: argparse.Namespace, mgr: ClientSettingsManager) -> int:
    n = mgr.push_to_cloud()
    print(f"pushed {n} bytes -> cloud ClientSettings.Sav")
    return 0


def _cmd_keybinds(args: argparse.Namespace, mgr: ClientSettingsManager) -> int:
    parsed = mgr.read_local()
    binds = ClientSettingsManager.get_keybinds(parsed, sub_game=args.sub_game)
    print(f"{len(binds)} bindings in {args.sub_game}:")
    for b in binds:
        if b["key1"] == "None" and b["key2"] == "None":
            continue
        keys = b["key1"] if b["key2"] == "None" else f"{b['key1']} / {b['key2']}"
        suffix = ""
        if b["is_axis"]:
            suffix = f"  (axis, scale={b['input_scale']})"
        print(f"  {b['action']:40s} -> {keys}{suffix}")
    return 0


def _cmd_set_keybind(args: argparse.Namespace, mgr: ClientSettingsManager) -> int:
    parsed = mgr.read_local()
    hits = ClientSettingsManager.set_keybind(
        parsed, args.action, key1=args.key, sub_game=args.sub_game
    )
    if hits == 0:
        print(f"no binding matched action={args.action!r} in {args.sub_game}", file=sys.stderr)
        return 1
    print(f"updated {hits} binding(s): {args.action} -> {args.key}")

    if args.local_only:
        mgr.write_local(parsed, require_game_closed=not args.force)
        print(f"wrote local file")
    elif args.cloud_only:
        mgr.cloud.upload(CLIENT_SETTINGS_FILENAME, serialize_file(parsed))
        print("uploaded to cloud")
    else:
        result = mgr.apply_changes(parsed, push_cloud=True, write_local=True,
                                   require_game_closed=not args.force)
        print(json.dumps(result, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="clientsettings_cli")
    ap.add_argument("--debug", action="store_true", help="verbose logging")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="list cloud storage files")
    p.add_argument("--all", action="store_true", help="include restricted files")

    p = sub.add_parser("show", help="parse and summarize a save file")
    p.add_argument("path", nargs="?", help="path (default: local Config/ClientSettings.Sav)")

    sub.add_parser("diff", help="local vs cloud structural diff")

    p = sub.add_parser("pull", help="download cloud ClientSettings.Sav and replace local")
    p.add_argument("--force", action="store_true", help="skip the game-is-closed check")

    sub.add_parser("push", help="upload local ClientSettings.Sav to cloud")

    p = sub.add_parser("keybinds", help="print bindings for a sub-game")
    p.add_argument("sub_game", nargs="?", default="ESubGame::Athena")

    p = sub.add_parser("set-keybind", help="change a binding's primary key (KeyBind1)")
    p.add_argument("action", help="action name, e.g. 'Jump'")
    p.add_argument("key", help="key name, e.g. 'V', 'SpaceBar', 'LeftShift'")
    p.add_argument("--sub-game", default="ESubGame::Athena")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--local-only", action="store_true", help="write local only, don't push cloud")
    mode.add_argument("--cloud-only", action="store_true", help="push cloud only, don't write local")
    p.add_argument("--force", action="store_true", help="skip the game-is-closed check")

    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    mgr = ClientSettingsManager()

    dispatch = {
        "list": _cmd_list,
        "show": _cmd_show,
        "diff": _cmd_diff,
        "pull": _cmd_pull,
        "push": _cmd_push,
        "keybinds": _cmd_keybinds,
        "set-keybind": _cmd_set_keybind,
    }
    return dispatch[args.cmd](args, mgr)


if __name__ == "__main__":
    raise SystemExit(main())
