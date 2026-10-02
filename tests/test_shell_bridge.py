"""The JSON Lines bridge to FA11y.UI.exe, tested against a fake UI (tests/fixtures/fake_ui.py)."""
import json
import os
import sys
import threading
import time

import pytest

from lib.shell.bridge import Bridge, BridgeError, HandlerRegistry

FAKE_UI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "fake_ui.py")


def wait_for(condition, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = condition()
        if result:
            return result
        time.sleep(0.02)
    raise AssertionError("timed out waiting for the condition")


def read_log(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.fixture
def make_bridge(tmp_path):
    bridges = []

    def make(handlers=None, ui_args=(), **kwargs):
        log = str(tmp_path / "ui.log")
        bridge = Bridge([sys.executable, FAKE_UI, "--log", log, *ui_args], str(tmp_path),
                        handlers if handlers is not None else {}, **kwargs)
        bridges.append(bridge)
        return bridge, log

    yield make
    for bridge in bridges:
        bridge.stop(timeout=2)


def test_request_round_trip(make_bridge):
    bridge, _ = make_bridge()
    bridge.start()
    result = bridge.request("anything", {"a": 1}, timeout=8)
    assert result == {"echo": "anything", "params": {"a": 1}}


def test_error_response_raises(make_bridge):
    bridge, _ = make_bridge()
    bridge.start()
    with pytest.raises(BridgeError, match="it failed"):
        bridge.request("fail", timeout=8)


def test_slow_ui_requests_do_not_block_each_other(make_bridge):
    registry = HandlerRegistry()

    @registry.register("test.slow")
    def slow(params):
        time.sleep(0.5)
        return {"which": "slow"}

    @registry.register("test.fast")
    def fast(params):
        return {"which": "fast"}

    calls = [{"method": "test.slow"}, {"method": "test.fast"}]
    bridge, log = make_bridge(registry.handlers, ui_args=("--call", json.dumps(calls)))
    bridge.start()
    wait_for(lambda: len([m for m in read_log(log) if m.get("type") == "response"]) == 2)
    order = [m["result"]["which"] for m in read_log(log) if m.get("type") == "response"]
    assert order == ["fast", "slow"]


def test_events_reach_the_ui_and_the_ui_events_reach_subscribers(make_bridge):
    bridge, log = make_bridge()
    ready = []
    bridge.subscribe("ui.ready", ready.append)
    bridge.start()
    wait_for(lambda: ready)
    bridge.send_event("ui.summon", {"focus_content": True})
    wait_for(lambda: any(m.get("name") == "ui.summon" for m in read_log(log)))
    message = next(m for m in read_log(log) if m.get("name") == "ui.summon")
    assert message == {"type": "event", "name": "ui.summon", "data": {"focus_content": True}}


def test_ui_requests_run_through_the_handler_registry(make_bridge):
    registry = HandlerRegistry()

    @registry.register("test.add")
    def add(params):
        return {"sum": params["a"] + params["b"]}

    bridge, log = make_bridge(registry.handlers,
                              ui_args=("--call", json.dumps({"method": "test.add", "params": {"a": 2, "b": 3}})))
    bridge.start()
    response = wait_for(lambda: next((m for m in read_log(log) if m.get("type") == "response"), None))
    assert response["ok"] is True
    assert response["result"] == {"sum": 5}
    assert response["id"] == 1


def test_handler_errors_and_unknown_methods_become_error_responses(make_bridge):
    registry = HandlerRegistry()

    @registry.register("test.boom")
    def boom(params):
        raise ValueError("kaboom")

    @registry.register("test.unserializable")
    def unserializable(params):
        return {"thing": object()}

    for method, expected in (("test.boom", "kaboom"), ("test.nothing", "Unknown method"),
                             ("test.unserializable", "not JSON serializable")):
        bridge, log = make_bridge(registry.handlers, ui_args=("--call", json.dumps({"method": method})))
        bridge.start()
        response = wait_for(lambda: next((m for m in read_log(log) if m.get("type") == "response"), None))
        assert response["ok"] is False
        assert expected in response["error"]
        bridge.stop(timeout=2)
        os.remove(log)


def test_the_ui_is_started_with_root_and_parent_pid(make_bridge, tmp_path):
    bridge, log = make_bridge(args=["--hidden"])
    bridge.start()
    started = wait_for(lambda: next((m for m in read_log(log) if m.get("started")), None))
    argv = started["argv"]
    assert argv[argv.index("--root") + 1] == str(tmp_path)
    assert argv[argv.index("--parent-pid") + 1] == str(os.getpid())
    assert "--hidden" in argv


def test_restarts_when_the_ui_crashes_then_gives_up(make_bridge):
    gave_up = threading.Event()
    bridge, log = make_bridge(ui_args=("--exit-after", "0.2"), on_give_up=gave_up.set)
    bridge.start()
    assert gave_up.wait(30)
    starts = [m for m in read_log(log) if m.get("started")]
    assert len(starts) == 4  # the first start and three restarts
    assert not bridge.is_running()


def test_a_restarted_window_is_not_hidden(make_bridge):
    bridge, log = make_bridge(ui_args=("--exit-after", "0.3"), args=["--hidden"])
    bridge.start()
    wait_for(lambda: len([m for m in read_log(log) if m.get("started")]) >= 2)
    starts = [m for m in read_log(log) if m.get("started")]
    assert "--hidden" in starts[0]["argv"]
    assert "--hidden" not in starts[1]["argv"]


def test_stop_ends_the_ui_without_restarting(make_bridge):
    bridge, log = make_bridge()
    bridge.start()
    wait_for(lambda: bridge.is_running())
    bridge.stop(timeout=3)
    assert not bridge.is_running()
    time.sleep(0.3)
    assert len([m for m in read_log(log) if m.get("started")]) == 1


def test_requests_fail_when_the_ui_is_gone(make_bridge):
    bridge, _ = make_bridge()
    bridge.start()
    bridge.request("ping", timeout=8)
    bridge.stop(timeout=3)
    with pytest.raises(BridgeError):
        bridge.request("ping", timeout=1)
