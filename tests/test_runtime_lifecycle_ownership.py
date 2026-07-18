"""Ownership gate for daemon and Hub lifecycle authority."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "easyremote"

RETIRED_MODULES = {
    "bootstrap.py",
    "daemon.py",
    "gateway.py",
    "_toml.py",
}
FORBIDDEN_LIFECYCLE_SYMBOLS = {
    "DaemonHandle",
    "DaemonLifecycleFacade",
    "DaemonProcess",
    "DaemonStartConfig",
    "DaemonStartProjection",
    "DaemonMode",
    "DeviceRuntimeBootstrap",
    "DeviceRuntimeLease",
    "RuntimeBootstrap",
    "RuntimeBootstrapState",
    "RuntimeHost",
    "RuntimeHostStartProjection",
    "RuntimeLifecycle",
}
FORBIDDEN_LIFECYCLE_CALLS = {
    "daemon_control",
    "runtime_lifecycle",
    "start_daemon",
    "start_device",
    "start_hub",
    "start_runtime_host",
}
FORBIDDEN_AUTHORITY_MODULES = {"cryptography", "multiprocessing", "subprocess"}
FORBIDDEN_CONFIGURATION_MARKERS = {
    "daemon-config.toml",
    "listen_tcp",
    "tls_cert_path",
    "tls_key_path",
    "_generate_self_signed",
}


def test_easyremote_has_no_daemon_or_hub_lifecycle_authority() -> None:
    assert {path.name for path in PACKAGE.iterdir()} & RETIRED_MODULES == set()
    assert _lifecycle_authority_violations(_production_sources()) == []


def test_compute_node_consumes_sdk_runtime_connection_provider() -> None:
    provider = (PACKAGE / "runtime_provider.py").read_text(encoding="utf-8")
    node = (PACKAGE / "node.py").read_text(encoding="utf-8")
    cli = (PACKAGE / "_cli.py").read_text(encoding="utf-8")
    package = (PACKAGE / "__init__.py").read_text(encoding="utf-8")
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "self._environment_factory().runtime_connection()" in provider
    assert "runtime_provider or LocalRuntimeProvider()" in node
    assert "runtime_provider.connect()" in node
    assert "connection.close()" in node
    assert 'args.command == "hub"' not in cli
    assert 'add_parser("hub"' not in cli
    assert not FORBIDDEN_LIFECYCLE_SYMBOLS & _top_level_exports(package)
    assert "gateway = [" not in project
    assert "cryptography" not in project


def test_lifecycle_ownership_gate_rejects_authority_mutations() -> None:
    config_writer = {
        "bad_config.py": """
from pathlib import Path

Path("daemon-config.toml").write_text("listen_tcp = '0.0.0.0:8443'")
""",
    }
    process_owner = {
        "bad_process.py": """
import subprocess

subprocess.Popen(["easynet", "start"])
""",
    }
    tls_owner = {
        "bad_tls.py": """
from cryptography import x509

certificate = x509.CertificateBuilder()
""",
    }
    sdk_lifecycle_owner = {
        "bad_lifecycle.py": """
from easynet_sdk import DaemonStartProjection

def start(environment):
    return environment.daemon_control().start(
        DaemonStartProjection.hub("acme")
    )
""",
    }
    duplicate_state_machine = {
        "bad_state.py": """
from enum import StrEnum

class RuntimeBootstrapState(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
""",
    }

    assert _lifecycle_authority_violations(config_writer)
    assert _lifecycle_authority_violations(process_owner)
    assert _lifecycle_authority_violations(tls_owner)
    assert _lifecycle_authority_violations(sdk_lifecycle_owner)
    assert _lifecycle_authority_violations(duplicate_state_machine)


def _production_sources() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): path.read_text(encoding="utf-8")
        for path in sorted(PACKAGE.rglob("*.py"))
    }


def _lifecycle_authority_violations(sources: dict[str, str]) -> list[str]:
    violations: list[str] = []
    for name, source in sources.items():
        tree = ast.parse(source, filename=name)
        for marker in FORBIDDEN_CONFIGURATION_MARKERS:
            if marker in source:
                violations.append(f"{name}: owns runtime configuration marker {marker}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if (
                        alias.name.split(".", maxsplit=1)[0]
                        in FORBIDDEN_AUTHORITY_MODULES
                    ):
                        violations.append(
                            f"{name}: imports lifecycle authority {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".", maxsplit=1)[0]
                if module in FORBIDDEN_AUTHORITY_MODULES:
                    violations.append(f"{name}: imports lifecycle authority {module}")
                for alias in node.names:
                    if alias.name in FORBIDDEN_LIFECYCLE_SYMBOLS:
                        violations.append(
                            f"{name}: imports lifecycle authority {alias.name}"
                        )
            elif (
                isinstance(node, ast.ClassDef)
                and node.name in FORBIDDEN_LIFECYCLE_SYMBOLS
            ):
                violations.append(f"{name}: defines lifecycle authority {node.name}")
            elif isinstance(node, ast.Call):
                call_name = _call_name(node.func)
                if call_name in (
                    FORBIDDEN_LIFECYCLE_CALLS | FORBIDDEN_LIFECYCLE_SYMBOLS
                ):
                    violations.append(f"{name}: calls lifecycle authority {call_name}")
    return sorted(set(violations))


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _top_level_exports(source: str) -> set[str]:
    tree = ast.parse(source)
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        )
    )
    assert isinstance(assignment.value, ast.List)
    return {
        element.value
        for element in assignment.value.elts
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    }
