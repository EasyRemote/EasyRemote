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


def test_explicit_detached_uses_ffi_field_name():
    config = DaemonStartConfig(
        mode="device",
        node_id="dev-a",
        detached=True,
    )
    assert config.to_wire()["detach"] is True
    assert "detached" not in config.to_wire()


def test_factory_options_are_carried_in_wire(tmp_path):
    config = DaemonStartConfig.hub(
        "acme",
        env={"RUST_LOG": "info"},
        log_path=tmp_path / "daemon.log",
        detached=True,
    )
    assert config.to_wire() == {
        "mode": "hub",
        "realm": "acme",
        "env": {"RUST_LOG": "info"},
        "log_path": str(tmp_path / "daemon.log"),
        "detach": True,
    }


def test_explicit_foreground_is_preserved():
    assert DaemonStartConfig(
        mode="device",
        node_id="dev-a",
        detached=False,
    ).to_wire()["detach"] is False


def test_device_start_config_requires_node_id():
    with pytest.raises(InvalidArgument) as exc_info:
        DaemonStartConfig.device().to_wire()
    assert exc_info.value.reason == "missing_node_id"


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


def test_handle_convenience_start_methods(monkeypatch):
    started = []

    class FakeProcess:
        @classmethod
        def start(cls, config):
            started.append(config)
            return cls()

    monkeypatch.setattr("easyremote.daemon.DaemonProcess", FakeProcess)

    hub = DaemonHandle.start_hub("acme", detached=True)
    device = DaemonHandle.start_device("dev-a")

    assert isinstance(hub, DaemonHandle)
    assert isinstance(device, DaemonHandle)
    assert [config.to_wire_dict() for config in started] == [
        {"mode": "hub", "realm": "acme", "detach": True},
        {"mode": "device", "node_id": "dev-a"},
    ]
