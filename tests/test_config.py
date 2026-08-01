"""Configuration: env resolution, configure() merge, actionable errors."""

import json

import easynet_sdk
import pytest

import easyremote.config as config
from easyremote.errors import Unavailable


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch):
    """Each test starts from unconfigured state and a clean environment."""
    monkeypatch.setattr(config, "_settings", None)
    for var in ("EASYNET_CREDENTIALS", "EASYNET_CONTROL_JSON", "EASYNET_CLI_LIB"):
        monkeypatch.delenv(var, raising=False)


def test_defaults_point_into_easynet_home():
    s = config.settings()
    assert s.credentials_path.name == "credentials.json"
    assert s.control_path.name == "control.json"
    assert s.credentials_path.parent == s.control_path.parent
    assert s.library_path is None


def test_defaults_prefer_desktop_easynet_root_when_populated(monkeypatch, tmp_path):
    sdk_root = tmp_path / ".runtime-host"
    desktop_root = tmp_path / ".easynet"
    desktop_root.mkdir()
    (desktop_root / "control.json").write_text("{}")
    monkeypatch.setattr(config, "_DESKTOP_EASYNET_DIR", desktop_root)
    monkeypatch.setattr(config.easynet_sdk, "runtime_state_root", lambda: sdk_root)

    s = config.settings()

    assert s.control_path == desktop_root / "control.json"
    assert s.credentials_path == desktop_root / "credentials.json"


def test_defaults_fall_back_to_sdk_root_when_desktop_root_is_empty(
    monkeypatch, tmp_path
):
    sdk_root = tmp_path / ".runtime-host"
    desktop_root = tmp_path / ".easynet"
    monkeypatch.setattr(config, "_DESKTOP_EASYNET_DIR", desktop_root)
    monkeypatch.setattr(config.easynet_sdk, "runtime_state_root", lambda: sdk_root)

    s = config.settings()

    assert s.control_path == sdk_root / "control.json"
    assert s.credentials_path == sdk_root / "credentials.json"


def test_environment_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("EASYNET_CONTROL_JSON", str(tmp_path / "c.json"))
    monkeypatch.setenv("EASYNET_CLI_LIB", str(tmp_path / "lib.dylib"))
    s = config.settings()
    assert s.control_path == tmp_path / "c.json"
    assert s.credentials_path == tmp_path / "credentials.json"
    assert s.library_path == tmp_path / "lib.dylib"


def test_configure_merges_partially(tmp_path):
    config.configure(control=tmp_path / "c.json")
    config.configure(credentials=tmp_path / "creds.json")
    s = config.settings()
    assert s.control_path == tmp_path / "c.json"  # survived the second call
    assert s.credentials_path == tmp_path / "creds.json"
    assert config.agents_root() == tmp_path / "agents"


def test_sdk_environment_uses_configured_process_root(tmp_path):
    control = tmp_path / "control.json"
    library = tmp_path / "libeasynet_cli.dylib"
    config.configure(control=control, library_path=library)

    environment = config.sdk_environment()

    assert environment.resolved_control_path() == str(control)
    assert environment.library_path == str(library)


def test_sdk_environment_accepts_explicit_control_override(tmp_path):
    configured = tmp_path / "control.json"
    explicit = tmp_path / "other-control.json"
    config.configure(control=configured)

    environment = config.sdk_environment(control_path=explicit)

    assert environment.resolved_control_path() == str(explicit)


def test_missing_control_tells_user_to_start_daemon(tmp_path):
    config.configure(control=tmp_path / "absent.json")
    with pytest.raises(Unavailable) as exc_info:
        config.read_control()
    assert exc_info.value.reason == "daemon_not_running"
    assert "easynet start" in str(exc_info.value)


def test_control_without_device_identity_tells_user_to_pair(tmp_path):
    path = tmp_path / "control.json"
    path.write_text(
        json.dumps(
            {
                "socket_path": "/tmp/control.sock",
                "invocation_endpoint": "unix:///tmp/daemon.sock",
                "pid": 123,
                "daemon_version": "0.65.0",
                "supported_ipc_versions": {"min": 1, "max": 1},
                "capability_flags": [],
            }
        )
    )
    config.configure(control=path)
    with pytest.raises(Unavailable) as exc_info:
        config.read_credentials()
    assert exc_info.value.reason == "not_paired"
    assert "easynet pair" in str(exc_info.value)


def test_corrupt_json_is_reported(tmp_path):
    path = tmp_path / "control.json"
    path.write_text("{not json")
    config.configure(control=path)
    with pytest.raises(Unavailable) as exc_info:
        config.read_control()
    assert exc_info.value.reason == "daemon_not_running_corrupt"


def test_valid_json_round_trips(tmp_path):
    path = tmp_path / "control.json"
    path.write_text(
        json.dumps(
            {
                "socket_path": "/tmp/control.sock",
                "invocation_endpoint": "unix:///tmp/daemon.sock",
                "pid": 123,
                "daemon_version": "0.65.0",
                "supported_ipc_versions": {"min": 1, "max": 1},
                "capability_flags": ["runtime.invocation"],
            }
        )
    )
    config.configure(control=path)
    assert config.read_control() == {
        "socket_path": "/tmp/control.sock",
        "pipe_name": "",
        "invocation_endpoint": "unix:///tmp/daemon.sock",
        "pid": 123,
        "daemon_version": "0.65.0",
        "supported_ipc_versions": {"min": 1, "max": 1},
        "capability_flags": ["runtime.invocation"],
    }


def test_semantically_invalid_control_json_is_reported(tmp_path):
    path = tmp_path / "control.json"
    path.write_text(json.dumps({"socket_path": "/tmp/control.sock"}))
    config.configure(control=path)
    with pytest.raises(Unavailable) as exc_info:
        config.read_control()
    assert exc_info.value.reason == "daemon_not_running_corrupt"
