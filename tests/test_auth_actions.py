"""Tests for shared Epic authentication state wiring."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from lib.app import auth_actions, state


def test_on_auth_success_publishes_social_and_discovery_instances(monkeypatch):
    """Startup and manual login must publish to the state social actions read."""
    social_manager = MagicMock()
    discovery_api = object()
    auth = SimpleNamespace(access_token="token")

    social_module = SimpleNamespace(
        get_social_manager=MagicMock(return_value=social_manager)
    )
    discovery_module = SimpleNamespace(
        EpicDiscovery=MagicMock(return_value=discovery_api)
    )
    monkeypatch.setitem(
        sys.modules, "lib.managers.social_manager", social_module
    )
    monkeypatch.setitem(
        sys.modules, "lib.utilities.epic_discovery", discovery_module
    )
    monkeypatch.setattr(state, "_social_manager", None)
    monkeypatch.setattr(state, "_discovery_api", None)

    auth_actions.on_auth_success(auth)

    social_module.get_social_manager.assert_called_once_with(auth)
    social_manager.start_monitoring.assert_called_once_with()
    discovery_module.EpicDiscovery.assert_called_once_with(auth)
    assert state.get_social_manager() is social_manager
    assert state.get_discovery_api() is discovery_api
