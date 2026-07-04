"""`easyremote doctor` — diagnose the local EasyNet link (SPEC §4.2).

Checks run shallow-to-deep and never mutate anything: library → ABI →
discovery files → daemon liveness → identity → live transport.
Each failure carries the exact command that fixes it; exit code is the
number of failed checks.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import easynet_sdk

from . import config
from .control import AbilityControl, AgentControl
from .errors import RemoteError
from .gateway import Gateway, TLSConfig
from .mission import MissionControl

__all__ = ["main"]


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def run_checks() -> list[Check]:
    checks: list[Check] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append(Check(name=name, ok=ok, detail=detail))

    # 1. SDK facade handshake
    try:
        feature_set = easynet_sdk.SdkEnvironment(
            library_path=_library_path(),
            control_path=str(config.settings().control_path),
        ).feature_set()
        add("easynet-sdk", True, f"ABI v{feature_set.abi_version}")
        sdk_ok = True
    except (RemoteError, easynet_sdk.SDKError) as exc:
        add("easynet-sdk", False, str(exc))
        sdk_ok = False

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

    # 5. live transport (only meaningful when everything above held)
    if sdk_ok and control is not None:
        try:
            from ._sdk_transport import Transport

            with Transport.connect():
                add("transport", True, "connected to daemon invocation endpoint")
        except RemoteError as exc:
            add("transport", False, str(exc))

    return checks


def _library_path() -> str | None:
    path = config.settings().library_path
    return str(path) if path is not None else None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    if args.command == "doctor":
        return _run_doctor()
    if args.command == "hub":
        return _run_hub(args)
    if args.command == "ability":
        return _run_ability(args)
    if args.command == "agent":
        return _run_agent(args)
    if args.command == "mission":
        return _run_mission(args)
    parser.print_usage(sys.stderr)
    return 2


def _run_doctor() -> int:
    checks = run_checks()
    width = max(len(check.name) for check in checks)
    for check in checks:
        mark = "✓" if check.ok else "✗"
        print(f"{mark} {check.name:<{width}}  {check.detail}")
    failed = sum(1 for check in checks if not check.ok)
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    return failed


def _run_hub(args: argparse.Namespace) -> int:
    if bool(args.cert_pem) != bool(args.key_pem):
        print(
            "easyremote hub: --cert-pem and --key-pem must be provided together",
            file=sys.stderr,
        )
        return 2
    tls = _tls_from_args(args)
    gateway = Gateway(port=args.port, realm=args.realm, tls=tls)
    gateway.start(block=False)
    print(f"hub endpoint: {gateway.endpoint}")
    print(f"tls fingerprint: {gateway.fingerprint}")
    print(gateway.pairing_guidance)
    if args.no_block:
        return 0
    try:
        import threading

        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        gateway.stop()
    return 0


def _run_ability(args: argparse.Namespace) -> int:
    control = AbilityControl()
    if args.ability_command == "install":
        result = control.install(args.path, node=args.node)
        if args.json:
            _print_json(result.raw)
        else:
            print(f"installed: {result.ability_ura or result.install_id or args.path}")
            if result.state:
                print(f"state: {result.state}")
        return 0
    if args.ability_command == "list":
        records = control.list(
            node=args.node,
            owner_ura=args.owner_ura,
            user_id=args.user,
            scope=args.scope,
        )
        if args.json:
            _print_json([record.raw for record in records])
        else:
            _print_ability_rows(records)
        return 0
    if args.ability_command == "show":
        record = control.show(args.ability_ura, node=args.node, scope=args.scope)
        if args.json:
            _print_json(record.raw)
        else:
            _print_ability_rows([record])
        return 0
    print("easyremote ability: unknown subcommand", file=sys.stderr)
    return 2


def _run_agent(args: argparse.Namespace) -> int:
    control = AgentControl()
    if args.agent_command == "add":
        result = control.add(
            args.name,
            kind=args.type,
            model=args.model,
            label=args.label,
            command=args.command_path,
            args=args.command_args,
        )
        if args.json:
            _print_json(result.raw)
        else:
            action = "updated" if result.replaced_prior else "registered"
            print(f"{action}: {result.name}")
            print(f"type: {result.runtime}")
            if result.model:
                print(f"model: {result.model}")
            if result.root_path:
                print(f"root: {result.root_path}")
        return 0
    if args.agent_command == "list":
        records = control.list()
        if args.json:
            _print_json([record.raw for record in records])
        else:
            for record in records:
                model = f" model={record.model}" if record.model else ""
                print(f"{record.name}\t{record.runtime}{model}")
        return 0
    if args.agent_command == "refresh":
        response = control.refresh(args.name)
        if args.json:
            _print_json(response)
        else:
            scanned = response.get("agents_scanned", 0)
            registered = response.get("runtime_registered", 0)
            failed = response.get("runtime_failed", 0)
            print(
                "refreshed:"
                f" scanned={scanned} registered={registered} failed={failed}"
            )
        return 0
    print("easyremote agent: unknown subcommand", file=sys.stderr)
    return 2


def _run_mission(args: argparse.Namespace) -> int:
    control = MissionControl()
    if args.mission_command == "run":
        source = sys.stdin.read() if args.source == "-" else Path(args.source)
        run = (
            control.run_eal(source, label=args.label)
            if isinstance(source, str)
            else control.run_file(source, label=args.label)
        )
        if args.json:
            _print_json(run.raw)
        else:
            print(f"run_id: {run.run_id}")
            if run.run_dir:
                print(f"run_dir: {run.run_dir}")
        return 0
    if args.mission_command == "track":
        status = control.track(args.run_id)
        _print_json(status)
        return 0
    if args.mission_command == "cancel":
        result = control.cancel(args.run_id)
        _print_json(result)
        return 0
    print("easyremote mission: unknown subcommand", file=sys.stderr)
    return 2


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _print_ability_rows(records: list[Any]) -> None:
    for record in records:
        owner = f" owner={record.owner_ura}" if record.owner_ura else ""
        state = f" state={record.state}" if record.state else ""
        print(f"{record.ability_ura or record.name}{owner}{state}")


def _tls_from_args(args: argparse.Namespace) -> TLSConfig | Literal["self-signed"]:
    cert = args.cert_pem
    key = args.key_pem
    if cert and key:
        return TLSConfig(cert_pem=Path(cert), key_pem=Path(key))
    return "self-signed"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="easyremote")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("doctor", help="diagnose the local EasyNet link")

    hub = subcommands.add_parser(
        "hub", help="start this machine as an EasyNet hub daemon"
    )
    hub.add_argument("--port", type=int, default=8443)
    hub.add_argument("--realm", default="localhost")
    hub.add_argument("--cert-pem")
    hub.add_argument("--key-pem")
    hub.add_argument(
        "--no-block",
        action="store_true",
        help="start the hub and return immediately",
    )

    ability = subcommands.add_parser(
        "ability", help="install and inspect daemon-published abilities"
    )
    ability_sub = ability.add_subparsers(dest="ability_command", required=True)
    ability_install = ability_sub.add_parser(
        "install", help="install an ability package through the daemon"
    )
    ability_install.add_argument("path")
    ability_install.add_argument("--node", default="local")
    ability_install.add_argument("--json", action="store_true")
    ability_list = ability_sub.add_parser("list", help="list abilities")
    ability_list.add_argument("--node")
    ability_list.add_argument("--scope", choices=["local", "realm"], default="local")
    ability_list.add_argument("--owner-ura")
    ability_list.add_argument("--user")
    ability_list.add_argument("--json", action="store_true")
    ability_show = ability_sub.add_parser("show", help="show one ability")
    ability_show.add_argument("ability_ura")
    ability_show.add_argument("--node")
    ability_show.add_argument("--scope", choices=["local", "realm"], default="local")
    ability_show.add_argument("--json", action="store_true")

    agent = subcommands.add_parser("agent", help="manage daemon-owned agents")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    agent_add = agent_sub.add_parser("add", help="register an agent")
    agent_add.add_argument("name")
    agent_add.add_argument("--type", required=True)
    agent_add.add_argument("--model")
    agent_add.add_argument("--label")
    agent_add.add_argument("--command", dest="command_path")
    agent_add.add_argument("--arg", dest="command_args", action="append", default=[])
    agent_add.add_argument("--json", action="store_true")
    agent_list = agent_sub.add_parser("list", help="list registered agents")
    agent_list.add_argument("--json", action="store_true")
    agent_refresh = agent_sub.add_parser("refresh", help="refresh agent runtime rows")
    agent_refresh.add_argument("--name")
    agent_refresh.add_argument("--json", action="store_true")

    mission = subcommands.add_parser("mission", help="run and inspect EAL missions")
    mission_sub = mission.add_subparsers(dest="mission_command", required=True)
    mission_run = mission_sub.add_parser(
        "run", help="submit an EAL mission file through the daemon"
    )
    mission_run.add_argument("source", help="EAL file path, or '-' for stdin")
    mission_run.add_argument("--label")
    mission_run.add_argument("--json", action="store_true")
    mission_track = mission_sub.add_parser("track", help="fetch mission run status")
    mission_track.add_argument("run_id")
    mission_track.add_argument("--json", action="store_true")
    mission_cancel = mission_sub.add_parser("cancel", help="cancel a mission run")
    mission_cancel.add_argument("run_id")
    mission_cancel.add_argument("--json", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
