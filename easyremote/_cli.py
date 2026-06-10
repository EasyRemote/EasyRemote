"""`easyremote doctor` — diagnose the local EasyNet link (SPEC §4.2).

Checks run shallow-to-deep and never mutate anything: library → ABI →
discovery files → daemon liveness → identity → agent registration.
Each failure carries the exact command that fixes it; exit code is the
number of failed checks.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any

from . import config
from ._transport import abi
from .errors import RemoteError

__all__ = ["main"]


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def run_checks(namespace: str = "er") -> list[Check]:
    checks: list[Check] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append(Check(name=name, ok=ok, detail=detail))

    # 1. library + ABI handshake
    try:
        abi.library()
        add("libeasynet_cli", True, f"loaded, ABI v{abi.ABI_VERSION}")
        library_ok = True
    except RemoteError as exc:
        add("libeasynet_cli", False, str(exc))
        library_ok = False

    # 2. daemon discovery file
    control: dict[str, Any] | None = None
    try:
        control = config.read_control()
        endpoint = control.get("invocation_endpoint") or control.get("socket_path")
        add("control.json", True, f"endpoint {endpoint}")
    except RemoteError as exc:
        add("control.json", False, str(exc))

    # 3. daemon process liveness
    if control is not None:
        pid = control.get("pid")
        try:
            os.kill(int(str(pid)), 0)
            add("daemon", True, f"pid {pid} alive (v{control.get('daemon_version')})")
        except (TypeError, ValueError, ProcessLookupError, PermissionError):
            add("daemon", False, f"pid {pid} not running — start with `easynet start`")

    # 4. identity
    try:
        from .identity import LocalIdentity

        identity = LocalIdentity.load()
        add("identity", True, identity.device_ura)
    except RemoteError as exc:
        add("identity", False, str(exc))

    # 5. agent registration for the default namespace
    registry_path = config.agents_root().parent / "agents.json"
    try:
        agents = json.loads(registry_path.read_text(encoding="utf-8")).get("agents", {})
        if namespace in agents:
            add(
                "agent",
                True,
                f"'{namespace}' registered → {agents[namespace].get('root_path')}",
            )
        else:
            registered = ", ".join(sorted(agents)) or "none"
            add(
                "agent",
                False,
                f"'{namespace}' not registered (have: {registered}) — run"
                f" `easynet agent add --type claude-code {namespace}`",
            )
    except (FileNotFoundError, json.JSONDecodeError):
        add("agent", False, f"no readable {registry_path} — is the daemon paired?")

    # 6. live transport (only meaningful when everything above held)
    if library_ok and control is not None:
        try:
            from ._transport import Transport

            with Transport.connect():
                add("transport", True, "connected to daemon invocation endpoint")
        except RemoteError as exc:
            add("transport", False, str(exc))

    return checks


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] != ["doctor"]:
        print("usage: easyremote doctor [--namespace <agent>]", file=sys.stderr)
        return 2
    namespace = "er"
    if "--namespace" in argv:
        namespace = argv[argv.index("--namespace") + 1]

    checks = run_checks(namespace)
    width = max(len(check.name) for check in checks)
    for check in checks:
        mark = "✓" if check.ok else "✗"
        print(f"{mark} {check.name:<{width}}  {check.detail}")
    failed = sum(1 for check in checks if not check.ok)
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
