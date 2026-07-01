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


def test_ability_install_command_uses_control(monkeypatch, tmp_path, capsys):
    calls = []

    class FakeResult:
        def __init__(self):
            self.ability_ura = "easynet:///r/acme/ability/device.dev-a.er.fn"
            self.install_id = "inst-1"
            self.state = "ACTIVE"
            self.raw = {
                "ability_ura": self.ability_ura,
                "install_id": self.install_id,
                "state": self.state,
            }

    class FakeAbilityControl:
        def install(self, path, *, node):
            calls.append((path, node))
            return FakeResult()

    monkeypatch.setattr("easyremote._cli.AbilityControl", FakeAbilityControl)
    package = tmp_path / "pkg"
    package.mkdir()

    assert main(["ability", "install", str(package), "--node", "local"]) == 0

    assert calls == [(str(package), "local")]
    assert (
        "installed: easynet:///r/acme/ability/device.dev-a.er.fn"
        in capsys.readouterr().out
    )


def test_ability_list_command_supports_json(monkeypatch, capsys):
    class FakeRecord:
        def __init__(self):
            self.raw = {"ability_ura": "u1"}
            self.ability_ura = "u1"
            self.name = "fn"
            self.owner_ura = "owner"
            self.state = "ACTIVE"

    class FakeAbilityControl:
        def list(self, *, node, owner_ura, user_id, scope):
            assert node == "gpu-1"
            assert owner_ura == "owner"
            assert user_id == "u-alice"
            assert scope == "realm"
            return [FakeRecord()]

    monkeypatch.setattr("easyremote._cli.AbilityControl", FakeAbilityControl)

    assert (
        main(
            [
                "ability",
                "list",
                "--node",
                "gpu-1",
                "--owner-ura",
                "owner",
                "--user",
                "u-alice",
                "--scope",
                "realm",
                "--json",
            ]
        )
        == 0
    )

    assert '"ability_ura": "u1"' in capsys.readouterr().out


def test_agent_add_and_list_commands_use_control(monkeypatch, capsys):
    calls = []

    class FakeStart:
        def __init__(self):
            self.name = "caesura"
            self.runtime = "claude-code"
            self.model = "sonnet"
            self.root_path = "/tmp/caesura"
            self.replaced_prior = False
            self.raw = {"name": self.name}

    class FakeAgent:
        def __init__(self):
            self.name = "caesura"
            self.runtime = "claude-code"
            self.model = "sonnet"
            self.raw = {"name": self.name}

    class FakeAgentControl:
        def add(self, name, *, kind, model, label, command, args):
            calls.append((name, kind, model, label, command, args))
            return FakeStart()

        def list(self):
            return [FakeAgent()]

    monkeypatch.setattr("easyremote._cli.AgentControl", FakeAgentControl)

    assert (
        main(
            [
                "agent",
                "add",
                "caesura",
                "--type",
                "claude-code",
                "--model",
                "sonnet",
                "--arg=--verbose",
            ]
        )
        == 0
    )
    assert calls == [
        ("caesura", "claude-code", "sonnet", None, None, ["--verbose"])
    ]
    assert "registered: caesura" in capsys.readouterr().out

    assert main(["agent", "list"]) == 0
    assert "caesura\tclaude-code model=sonnet" in capsys.readouterr().out
