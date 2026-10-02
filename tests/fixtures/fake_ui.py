"""A tiny stand-in for FA11y.UI.exe that speaks the bridge protocol, for tests.

    python fake_ui.py --log FILE [--exit-after SECONDS] [--call JSON] [--emit JSON] [--no-ready]

Writes every message it receives, one JSON object per line, to FILE. Sends the
event ui.ready when it starts (unless --no-ready). Answers requests with
{"echo": method, "params": params}; "fail" answers with an error and "slow"
waits a moment first. Exits on the event ui.quit, and with code 5 after
--exit-after seconds (to look like a crash). --emit sends a list of events {name, data} first. --call sends a request (or a list of
them, ids 1, 2, ...) to the core right after ui.ready and logs the responses.
"""
import argparse
import json
import sys
import threading
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True)
    parser.add_argument("--exit-after", type=float, default=0)
    parser.add_argument("--call", default="")
    parser.add_argument("--no-ready", action="store_true")
    parser.add_argument("--emit", default="")
    parser.add_argument("--root")
    parser.add_argument("--parent-pid")
    parser.add_argument("--hidden", action="store_true")
    args = parser.parse_args()

    log = open(args.log, "a", encoding="utf-8")
    lock = threading.Lock()

    def record(obj) -> None:
        with lock:
            log.write(json.dumps(obj) + "\n")
            log.flush()

    def send(obj) -> None:
        with lock:
            sys.stdout.write(json.dumps(obj) + "\n")
            sys.stdout.flush()

    record({"started": True, "argv": sys.argv[1:]})
    if not args.no_ready:
        send({"type": "event", "name": "ui.ready", "data": {}})
    if args.emit:
        for event in json.loads(args.emit):
            send({"type": "event", "name": event["name"], "data": event.get("data", {})})
    if args.call:
        calls = json.loads(args.call)
        for number, call in enumerate(calls if isinstance(calls, list) else [calls], start=1):
            send({"type": "request", "id": number, **call})
    if args.exit_after:
        threading.Timer(args.exit_after, lambda: (log.flush(), sys.stdout.flush(), __import__("os")._exit(5))).start()

    for line in sys.stdin:
        message = json.loads(line)
        record(message)
        kind = message.get("type")
        if kind == "event" and message.get("name") == "ui.quit":
            return 0
        if kind == "request":
            method = message.get("method")
            if method == "slow":
                time.sleep(0.3)
            if method == "fail":
                send({"type": "response", "id": message["id"], "ok": False, "error": "it failed"})
            else:
                send({"type": "response", "id": message["id"], "ok": True,
                      "result": {"echo": method, "params": message.get("params")}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
