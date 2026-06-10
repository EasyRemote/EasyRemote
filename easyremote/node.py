"""ComputeNode: publish local functions as device-owned abilities.

Ontology, corrected: **a node is a device, not an agent.** Registered
functions become device-owned abilities —

    easynet:///r/<realm>/ability/device.<node-id>.<namespace>.<fn>

— deployed through ``easynet ability deploy --node local`` with the
scaffold-authoritative ``ability.json`` (verified via
``easynet ability new``). The runtime invokes the ability's ``command``
with the args JSON on **stdin** and reads the result from **stdout**;
our command is the :mod:`easyremote._host.forward` shim, which relays
to the warm host where the function (and its model) stays resident.

The stdin/stdout contract is strictly better than the agent-side
argv-template path: optional parameters stay optional, JSON types
arrive intact, and no required-all schema rewriting exists.

Still rejected loudly — a one-shot stdin/stdout exchange cannot carry
them (both resolved by the daemon host-attach enabler, SPEC §9 PR-1):

- generator/stream functions (no frame path),
- Context-taking functions (caller/invocation_id are not in the
  stdin payload, and fabricating them would corrupt the receipt chain).
"""

from __future__ import annotations

import dataclasses
import functools
import inspect
import json
import re
import subprocess
import sys
import threading
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._host import HostServer
from ._host.server import HostedFunction
from ._version import __version__
from .context import Context
from .errors import InvalidArgument, Unavailable
from .schema import PARAMETER_ORDER_KEY, derive

__all__ = ["AbilityInfo", "ComputeNode", "RegisteredFunction"]

_EASYREMOTE_DIR = Path.home() / ".easynet" / "easyremote"

_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")

_HOST_ATTACH_HINT = (
    " — supported once the daemon external-host-attach protocol lands"
    " (SPEC §9, Cli PR-1)"
)


@dataclass(frozen=True)
class AbilityInfo:
    """One registered capability, as packaged on disk.

    ``ura`` is the canonical device-ability URA when this machine is
    paired (RFC-001 shape, mirrored from `easynet ability invoke`'s own
    documentation); None in unpaired/test environments.
    """

    name: str
    qualified_name: str
    package_dir: Path
    ura: str | None


class RegisteredFunction:
    """Handle returned by ``register`` — still a plain local callable."""

    def __init__(self, hosted: HostedFunction, info: AbilityInfo) -> None:
        self._hosted = hosted
        self.info = info
        functools.update_wrapper(self, hosted.fn)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._hosted.fn(*args, **kwargs)

    @property
    def name(self) -> str:
        return self.info.name

    @property
    def qualified_name(self) -> str:
        return self.info.qualified_name


class ComputeNode:
    """A device contributing capabilities to the network.

    ``gateway`` is accepted for the classic FaaS shape — but transport
    truth lives with the local easynet-daemon, whose hub binding comes
    from pairing. When both are known and disagree, you get a warning,
    not silent re-routing: changing hubs is `easynet pair`'s job.

    ``cli_runner``/``abilities_dir`` are injectable seams (tests);
    production code never passes them.
    """

    def __init__(
        self,
        gateway: str | None = None,
        *,
        namespace: str = "er",
        abilities_dir: Path | None = None,
        cli_runner: Callable[[list[str]], None] | None = None,
    ) -> None:
        if not _NAME_PATTERN.match(namespace):
            raise InvalidArgument(
                f"namespace {namespace!r} must match {_NAME_PATTERN.pattern}",
                reason="invalid_namespace",
            )
        self._gateway = gateway
        self._namespace = namespace
        self._abilities_dir = abilities_dir or (_EASYREMOTE_DIR / "abilities")
        self._run_cli = cli_runner or _run_easynet
        self._host = HostServer(self._abilities_dir.parent / "host.sock")
        self._abilities: dict[str, AbilityInfo] = {}
        self._started = False
        self._gateway_checked = False

    # -- registration ------------------------------------------------------

    def register(
        self,
        fn: Callable[..., Any] | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> Any:
        """Project a function into a device capability (decorator, both forms)."""
        if fn is None:
            return functools.partial(
                self.register, name=name, description=description, schema=schema
            )

        signature = derive(fn, context_type=Context)
        if signature.takes_context:
            raise Unavailable(
                f"'{getattr(fn, '__name__', fn)}' takes a Context — the device"
                " ability stdin payload carries args only, not caller identity"
                " or invocation ids" + _HOST_ATTACH_HINT,
                reason="context_requires_host_attach",
            )
        if signature.is_stream:
            raise Unavailable(
                f"'{getattr(fn, '__name__', fn)}' is a generator — the device"
                " ability exchange is one stdin/stdout round trip; frames"
                " cannot stream" + _HOST_ATTACH_HINT,
                reason="stream_requires_host_attach",
            )

        ability_name = name or fn.__name__
        if not _NAME_PATTERN.match(ability_name):
            raise InvalidArgument(
                f"ability name {ability_name!r} must match {_NAME_PATTERN.pattern}"
                " (dots are namespace separators, not name characters)",
                reason="invalid_ability_name",
            )
        if ability_name in self._abilities:
            raise InvalidArgument(
                f"'{ability_name}' is already registered on this node",
                reason="duplicate_function",
            )

        if schema is not None:
            input_schema = dict(schema)
            input_schema.setdefault(
                PARAMETER_ORDER_KEY, signature.input_schema[PARAMETER_ORDER_KEY]
            )
            signature = dataclasses.replace(signature, input_schema=input_schema)

        qualified = f"{self._namespace}.{ability_name}"
        package_dir = self._write_package(
            qualified,
            description or _first_doc_line(fn) or f"{ability_name} (easyremote)",
            signature.input_schema,
            signature.output_schema,
        )
        hosted = HostedFunction(name=qualified, fn=fn, signature=signature)
        self._host.add(hosted)
        info = AbilityInfo(
            name=ability_name,
            qualified_name=qualified,
            package_dir=package_dir,
            ura=self._device_ability_ura(ability_name),
        )
        self._abilities[ability_name] = info
        if self._started:
            self._deploy(info)  # post-start registration: publish immediately
        return RegisteredFunction(hosted, info)

    # -- lifecycle -----------------------------------------------------------

    def serve(self) -> None:
        """Blocking serve; Ctrl-C exits cleanly."""
        self.start()
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def start(self) -> None:
        self._check_gateway()
        self._host.start()
        self._started = True
        for info in self._abilities.values():
            self._deploy(info)

    def stop(self) -> None:
        self._host.stop()
        self._started = False

    def __enter__(self) -> ComputeNode:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    # -- introspection ---------------------------------------------------------

    @property
    def namespace(self) -> str:
        return self._namespace

    @property
    def abilities(self) -> list[AbilityInfo]:
        return list(self._abilities.values())

    @property
    def host_socket(self) -> Path:
        return self._host.socket_path

    # -- internals ---------------------------------------------------------------

    def _deploy(self, info: AbilityInfo) -> None:
        """Publish onto this device's own ability registry."""
        self._run_cli(["ability", "deploy", str(info.package_dir), "--node", "local"])

    def _write_package(
        self,
        qualified: str,
        description: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any] | None,
    ) -> Path:
        # Field set mirrors the `easynet ability new` scaffold. Schemas
        # keep their true semantics: the stdin contract has no
        # missing-template failure mode, so optionals stay optional.
        manifest: dict[str, Any] = {
            "category": "easyremote",
            "command": (
                f"{sys.executable} -m easyremote._host.forward"
                f" {self._host.socket_path} {qualified}"
            ),
            "description": description,
            "destructive_hint": False,
            "idempotent_hint": False,
            "input_schema": input_schema,
            "instructions": description,
            "name": qualified,
            "open_world_hint": False,
            "prerequisites": [],
            "read_only_hint": False,
            "tags": ["easyremote"],
            "tool_name": qualified,
            "version": __version__,
        }
        if output_schema is not None:
            manifest["output_schema"] = output_schema

        package_dir = self._abilities_dir / qualified
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "ability.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return package_dir

    def _device_ability_ura(self, ability_name: str) -> str | None:
        try:
            from .identity import LocalIdentity, device_ability_ura

            identity = LocalIdentity.load()
        except Exception:
            return None  # unpaired / test environment: absent beats invented
        return device_ability_ura(
            identity.realm, identity.node_id, self._namespace, ability_name
        )

    def _check_gateway(self) -> None:
        """Soft-validate the classic gateway address against pairing truth."""
        if self._gateway is None or self._gateway_checked:
            return
        self._gateway_checked = True
        try:
            from .identity import LocalIdentity

            paired = LocalIdentity.load().hub_endpoint
        except Exception:
            return  # doctor reports unpaired machines with the fix command
        if paired and self._gateway.split("://")[-1] not in paired:
            warnings.warn(
                f"ComputeNode(gateway={self._gateway!r}) differs from the paired"
                f" hub ({paired}) — the daemon routes via pairing; re-point it"
                " with `easynet pair`",
                UserWarning,
                stacklevel=3,
            )


def _first_doc_line(fn: Callable[..., Any]) -> str:
    doc = inspect.getdoc(fn)
    return doc.splitlines()[0].strip() if doc else ""


def _run_easynet(args: list[str]) -> None:
    """Run one `easynet` CLI command, folding failures into the taxonomy."""
    try:
        subprocess.run(["easynet", *args], capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise Unavailable(
            "`easynet` CLI not found on PATH — install the EasyNet CLI to"
            " publish abilities to the daemon",
            reason="easynet_cli_missing",
        ) from None
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip()
        raise Unavailable(
            f"`easynet {' '.join(args)}` failed: {detail}",
            reason="easynet_cli_failed",
        ) from None
