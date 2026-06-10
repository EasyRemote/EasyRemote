"""`easyremote doctor`: check ladder and actionable failures."""

import json

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
    assert not checks["agent"].ok


def test_registered_agent_passes(isolated_environment):
    tmp = isolated_environment
    (tmp / "agents.json").write_text(
        json.dumps({"agents": {"er": {"root_path": str(tmp / "er")}}})
    )
    checks = by_name(run_checks())
    assert checks["agent"].ok


def test_namespace_flag_changes_target(isolated_environment):
    tmp = isolated_environment
    (tmp / "agents.json").write_text(
        json.dumps({"agents": {"demo": {"root_path": str(tmp / "demo")}}})
    )
    checks = by_name(run_checks("demo"))
    assert checks["agent"].ok


def test_main_prints_marks_and_returns_failure_count(isolated_environment, capsys):
    code = main(["doctor"])
    out = capsys.readouterr().out
    assert "✗" in out
    assert "checks passed" in out
    assert code > 0


def test_main_rejects_unknown_commands(capsys):
    assert main(["nope"]) == 2
    assert "usage" in capsys.readouterr().err
