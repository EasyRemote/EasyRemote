"""Daemon lifecycle facade: typed start config and handle delegation."""

import pytest

from easyremote.daemon import DaemonHandle, DaemonStartConfig
from easyremote.errors import InvalidArgument


def test_hub_start_config_wire_shape():
    assert DaemonStartConfig.hub("acme").to_wire() == {
        "mode": "hub",
        "realm": "acme",
    }


def test_device_start_config_wire_shape():
    assert DaemonStartConfig.device("dev-a").to_wire() == {
        "mode": "device",
        "node_id": "dev-a",
    }


def test_hub_realm_must_not_be_empty():
    with pytest.raises(InvalidArgument) as exc_info:
        DaemonStartConfig.hub(" ")
    assert exc_info.value.reason == "empty_realm"


def test_handle_delegates_to_process():
    class FakeProcess:
        def __init__(self):
            self.stopped = False

        def status(self):
            return {"ok": True}

        def invocation_endpoint(self):
            return "daemon.sock"

        def stop(self):
            self.stopped = True

    process = FakeProcess()
    handle = DaemonHandle(process)  # type: ignore[arg-type]

    assert handle.status() == {"ok": True}
    assert handle.invocation_endpoint() == "daemon.sock"
    handle.stop()
    assert process.stopped
