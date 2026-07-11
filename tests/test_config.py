"""Configuration: env resolution, configure() merge, actionable errors."""

import json

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
    assert s.credentials_path.parent.name == ".easynet"
    assert s.library_path is None


def test_environment_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("EASYNET_CONTROL_JSON", str(tmp_path / "c.json"))
    monkeypatch.setenv("EASYNET_CLI_LIB", str(tmp_path / "lib.dylib"))
    s = config.settings()
    assert s.control_path == tmp_path / "c.json"
    assert s.library_path == tmp_path / "lib.dylib"


def test_configure_merges_partially(tmp_path):
    config.configure(control=tmp_path / "c.json")
    config.configure(credentials=tmp_path / "creds.json")
    s = config.settings()
    assert s.control_path == tmp_path / "c.json"  # survived the second call
    assert s.credentials_path == tmp_path / "creds.json"
    assert config.agents_root() == tmp_path / "agents"


def test_missing_control_tells_user_to_start_daemon(tmp_path):
    config.configure(control=tmp_path / "absent.json")
    with pytest.raises(Unavailable) as exc_info:
        config.read_control()
    assert exc_info.value.reason == "daemon_not_running"
    assert "easynet start" in str(exc_info.value)


def test_missing_credentials_tells_user_to_pair(tmp_path):
    config.configure(credentials=tmp_path / "absent.json")
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
                "pages_port": 8080,
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
        "pages_port": 8080,
    }


def test_semantically_invalid_control_json_is_reported(tmp_path):
    path = tmp_path / "control.json"
    path.write_text(json.dumps({"socket_path": "/tmp/control.sock"}))
    config.configure(control=path)
    with pytest.raises(Unavailable) as exc_info:
        config.read_control()
    assert exc_info.value.reason == "daemon_not_running_corrupt"
