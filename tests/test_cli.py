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


def test_hub_lifecycle_command_is_not_owned_by_easyremote(capsys):
    assert main(["hub"]) == 2
    assert "invalid choice" in capsys.readouterr().err


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

        def stop(self, name):
            calls.append(("stop", name))

            class FakeStop:
                def __init__(self):
                    self.stopped = True
                    self.name = "caesura"
                    self.agent_ura = "easynet:///r/acme/agent/caesura"
                    self.raw = {
                        "name": self.name,
                        "stopped": self.stopped,
                        "agent_ura": self.agent_ura,
                    }

            return FakeStop()

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
    assert calls == [("caesura", "claude-code", "sonnet", None, None, ["--verbose"])]
    assert "registered: caesura" in capsys.readouterr().out

    assert main(["agent", "list"]) == 0
    assert "caesura\tclaude-code model=sonnet" in capsys.readouterr().out

    assert main(["agent", "stop", "caesura"]) == 0
    assert ("stop", "caesura") in calls
    stop_out = capsys.readouterr().out
    assert "stopped: caesura" in stop_out
    assert "agent_ura: easynet:///r/acme/agent/caesura" in stop_out


def test_mission_run_track_cancel_commands_use_control(monkeypatch, tmp_path, capsys):
    calls = []

    class FakeRun:
        def __init__(self):
            self.run_id = "run-1"
            self.run_dir = "/tmp/run-1"
            self.raw = {"run_id": self.run_id, "run_dir": self.run_dir}

    class FakeMissionControl:
        def run_file(self, path, *, label):
            calls.append(("run_file", path, label))
            return FakeRun()

        def run_eal(self, source, *, label):
            calls.append(("run_eal", source, label))
            return FakeRun()

        def track(self, run_id):
            calls.append(("track", run_id))
            return {"state": "running"}

        def cancel(self, run_id):
            calls.append(("cancel", run_id))
            return {"cancelled": True}

    monkeypatch.setattr("easyremote._cli.MissionControl", FakeMissionControl)
    source = tmp_path / "nightly.eal"
    source.write_text('mission "nightly" {}\n')

    assert main(["mission", "run", str(source), "--label", "nightly"]) == 0
    assert calls[-1] == ("run_file", source, "nightly")
    assert "run_id: run-1" in capsys.readouterr().out

    assert main(["mission", "track", "run-1"]) == 0
    assert calls[-1] == ("track", "run-1")
    assert '"state": "running"' in capsys.readouterr().out

    assert main(["mission", "cancel", "run-1"]) == 0
    assert calls[-1] == ("cancel", "run-1")
    assert '"cancelled": true' in capsys.readouterr().out


def test_mission_run_accepts_stdin(monkeypatch, capsys):
    calls = []

    class FakeRun:
        def __init__(self):
            self.run_id = "run-stdin"
            self.run_dir = ""
            self.raw = {"run_id": self.run_id}

    class FakeMissionControl:
        def run_eal(self, source, *, label):
            calls.append((source, label))
            return FakeRun()

    monkeypatch.setattr("easyremote._cli.MissionControl", FakeMissionControl)
    monkeypatch.setattr("sys.stdin", type("Stdin", (), {"read": lambda self: "eal"})())

    assert main(["mission", "run", "-", "--label", "stdin"]) == 0
    assert calls == [("eal", "stdin")]
    assert "run_id: run-stdin" in capsys.readouterr().out
