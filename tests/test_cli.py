"""`easyremote doctor`: check ladder and actionable failures."""

import pytest

import easyremote.config as config
from easyremote._cli import main, run_checks


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    """Point every discovery path into an empty temp tree."""
    monkeypatch.setattr(config, "_settings", None)
    monkeypatch.setenv("EASYNET_CONTROL_JSON", str(tmp_path / "control.json"))
    monkeypatch.setenv("EASYNET_CREDENTIALS", str(tmp_path / "credentials.json"))
    monkeypatch.delenv("EASYNET_CLI_LIB", raising=False)
    monkeypatch.setattr(config, "agents_root", lambda: tmp_path / "agents")
    return tmp_path


def by_name(checks):
    return {check.name: check for check in checks}


def test_empty_machine_fails_with_fix_commands(isolated_environment):
    checks = by_name(run_checks())
    assert not checks["control.json"].ok
    assert "easynet start" in checks["control.json"].detail
    assert not checks["identity"].ok
    assert "easynet pair" in checks["identity"].detail


def test_main_prints_marks_and_returns_failure_count(isolated_environment, capsys):
    code = main(["doctor"])
    out = capsys.readouterr().out
    assert "✗" in out
    assert "checks passed" in out
    assert code > 0


def test_main_rejects_unknown_commands(capsys):
    assert main(["nope"]) == 2
    assert "usage" in capsys.readouterr().err


def test_hub_command_starts_gateway_without_blocking(monkeypatch, capsys):
    started = []

    class FakeGateway:
        endpoint = "host:9443"
        fingerprint = "AA:BB"
        pairing_guidance = "pair host"

        def __init__(self, *, port, realm, tls):
            self.port = port
            self.realm = realm
            self.tls = tls

        def start(self, *, block):
            started.append((self.port, self.realm, self.tls, block))

        def stop(self):
            raise AssertionError("no-block should not stop a foreground loop")

    monkeypatch.setattr("easyremote._cli.Gateway", FakeGateway)

    assert main(["hub", "--port", "9443", "--realm", "acme", "--no-block"]) == 0

    out = capsys.readouterr().out
    assert started == [(9443, "acme", "self-signed", False)]
    assert "hub endpoint: host:9443" in out
    assert "tls fingerprint: AA:BB" in out
    assert "pair host" in out


def test_hub_command_requires_cert_key_pair(capsys):
    assert main(["hub", "--cert-pem", "cert.pem", "--no-block"]) == 2
    assert "must be provided together" in capsys.readouterr().err
