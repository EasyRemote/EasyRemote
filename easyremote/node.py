"""ComputeNode: register local functions as agent-owned abilities (SPEC §5.4).

Materialization, verified against EasyNet-Cli sources:

- One manifest per function at
  ``~/.easynet/agents/<namespace>/abilities/<fn>.ability.toml``
  (``config::agents_root()`` + ``runtime::directory`` contract; the
  daemon publishes it as ``<namespace>.<fn>``).
- Exec binding: ``[exec] kind = "shell"`` with an argv that runs the
  :mod:`easyremote._host.forward` shim and one ``{{ param }}``
  template slot per parameter (``template.rs`` substitution model).
- The function itself stays resident in this process —
  :class:`~easyremote._host.HostServer` keeps models warm; the daemon
  only ever spawns the thin forwarder.

Executor-model constraints (all converge on the daemon host-attach
enabler, SPEC §9 PR-1) — rejected loudly, never degraded silently:

- generator/stream functions: the shell executor captures stdout
  whole; there is no frame path.
- Context-taking functions: neither caller identity nor invocation id
  traverses argv, and fabricating them would corrupt the receipt
  chain.
- omitted optional parameters: a missing template name is a hard
  render error, so generated manifests mark every parameter required
  and advertise defaults; callers fill them client-side.
"""

from __future__ import annotations

import dataclasses
import functools
import inspect
import json
import math
import re
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import _toml, config
from ._host import HostServer
from ._host.server import HostedFunction
from .context import Context
from .errors import InvalidArgument, Unavailable
from .schema import PARAMETER_ORDER_KEY, derive

__all__ = ["AbilityInfo", "ComputeNode", "RegisteredFunction"]

_MANIFEST_SCHEMA_VERSION = "1"

# Manifest file stems are the authoritative verb portion of the
# ability name; dots are structural (namespace separators) and
# therefore forbidden inside a single name.
_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")

_HOST_ATTACH_HINT = (
    " — supported once the daemon external-host-attach protocol lands"
    " (SPEC §9, Cli PR-1)"
)


@dataclass(frozen=True)
class AbilityInfo:
    """One registered capability, as materialized on disk.

    The ability URA and MCP tool projection are deliberately absent:
    credentials field names and projection naming are unverified until
    P0 — absent beats invented.
    """

    name: str
    qualified_name: str
    manifest_path: Path


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
    """A device-side capability publisher.

    The node never talks to the hub itself — its local easynet-daemon
    owns identity, transport, and federation. The node's job is:
    derive schemas, materialize manifests, keep functions warm, and
    announce changes (``easynet agent refresh`` — the daemon's hot
    registrar, P0-verified to require no restart).

    Two root modes:

    - **daemon-managed** (production, default): ``namespace`` must name
      an agent already registered with the daemon; the agent root is
      read back from ``agents.json`` — never assumed. Agent *identity*
      creation stays with `easynet agent add` (the current AgentType
      set is AI-CLI wrappers only; a manifest-only type is a pending
      Cli enhancement).
    - **explicit root** (tests / externally managed trees): pass
      ``agents_root`` and no CLI is ever touched.
    """

    def __init__(
        self,
        *,
        namespace: str = "er",
        agents_root: Path | None = None,
        cli_runner: Callable[[list[str]], None] | None = None,
    ) -> None:
        if not _NAME_PATTERN.match(namespace):
            raise InvalidArgument(
                f"namespace {namespace!r} must match {_NAME_PATTERN.pattern}",
                reason="invalid_namespace",
            )
        self._namespace = namespace
        self._explicit_root = agents_root
        self._run_cli = cli_runner or _run_easynet
        self._agent_root: Path | None = None
        self._host: HostServer | None = None
        self._abilities: dict[str, AbilityInfo] = {}
        self._started = False

    def _materialized(self) -> tuple[Path, HostServer]:
        """Resolve the agent root and host lazily, on first use."""
        if self._agent_root is None:
            if self._explicit_root is not None:
                self._agent_root = self._explicit_root / self._namespace
            else:
                self._agent_root = self._registered_agent_root()
            self._host = HostServer(self._agent_root / ".easyremote" / "host.sock")
        assert self._host is not None
        return self._agent_root, self._host

    def _registered_agent_root(self) -> Path:
        registry_path = config.agents_root().parent / "agents.json"
        try:
            agents = json.loads(registry_path.read_text(encoding="utf-8")).get(
                "agents", {}
            )
        except (FileNotFoundError, json.JSONDecodeError):
            agents = {}
        entry = agents.get(self._namespace)
        if entry is None or not entry.get("root_path"):
            raise Unavailable(
                f"agent '{self._namespace}' is not registered with the daemon —"
                f" register it once with `easynet agent add --type claude-code"
                f" {self._namespace}` (a manifest-only agent type is a pending"
                " EasyNet-Cli enhancement), or pass agents_root= for an"
                " externally managed tree",
                reason="agent_not_registered",
            )
        return Path(entry["root_path"])

    # -- registration ------------------------------------------------------

    def register(
        self,
        fn: Callable[..., Any] | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
        timeout: float | None = None,
        schema: dict[str, Any] | None = None,
    ) -> Any:
        """Project a function into a capability (decorator, both forms)."""
        if fn is None:
            return functools.partial(
                self.register,
                name=name,
                description=description,
                timeout=timeout,
                schema=schema,
            )

        signature = derive(fn, context_type=Context)
        if signature.takes_context:
            raise Unavailable(
                f"'{getattr(fn, '__name__', fn)}' takes a Context — the shell"
                " executor cannot deliver caller identity or invocation ids to"
                " a warm host" + _HOST_ATTACH_HINT,
                reason="context_requires_host_attach",
            )
        if signature.is_stream:
            raise Unavailable(
                f"'{getattr(fn, '__name__', fn)}' is a generator — the shell"
                " executor captures stdout whole, so frames cannot stream"
                + _HOST_ATTACH_HINT,
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

        _, host = self._materialized()
        manifest_path = self._write_manifest(
            ability_name,
            description or _first_doc_line(fn) or f"{ability_name} (easyremote)",
            timeout,
            signature.input_schema,
            signature.output_schema,
        )
        hosted = HostedFunction(name=ability_name, fn=fn, signature=signature)
        host.add(hosted)
        info = AbilityInfo(
            name=ability_name,
            qualified_name=f"{self._namespace}.{ability_name}",
            manifest_path=manifest_path,
        )
        self._abilities[ability_name] = info
        if self._started:
            self._refresh()  # post-start registration: announce immediately
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
        _, host = self._materialized()
        host.start()
        self._started = True
        self._refresh()

    def stop(self) -> None:
        if self._host is not None:
            self._host.stop()
        self._started = False

    def _refresh(self) -> None:
        """Announce manifest changes to the live daemon.

        ``easynet agent refresh --agent <ns>`` drives the daemon's hot
        registrar (P0-verified: no restart needed). Explicit-root mode
        is daemon-less by definition, so there is nothing to announce.
        """
        if self._explicit_root is not None:
            return
        self._run_cli(["agent", "refresh", "--agent", self._namespace])

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
        _, host = self._materialized()
        return host.socket_path

    # -- internals ---------------------------------------------------------------

    def _write_manifest(
        self,
        ability_name: str,
        description: str,
        timeout: float | None,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any] | None,
    ) -> Path:
        agent_root, host = self._materialized()
        order: list[str] = input_schema[PARAMETER_ORDER_KEY]
        manifest_input = dict(input_schema)
        # Executor constraint: a missing template name is a render
        # error, so the published contract requires every parameter.
        # Property-level "default" values tell callers what to fill.
        if order:
            manifest_input["required"] = list(order)

        manifest: dict[str, Any] = {
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "name": ability_name,
            "description": description,
        }
        if timeout is not None:
            manifest["timeout_seconds"] = max(1, math.ceil(timeout))
        manifest["input_schema"] = manifest_input
        if output_schema is not None:
            manifest["output_schema"] = output_schema
        manifest["exec"] = {
            "kind": "shell",
            "argv": [
                sys.executable,
                "-m",
                "easyremote._host.forward",
                str(host.socket_path),
                ability_name,
                *(f"{{{{ {param} }}}}" for param in order),
            ],
        }

        path = agent_root / "abilities" / f"{ability_name}.ability.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_toml.dumps(manifest), encoding="utf-8")
        return path


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
            " announce abilities to the daemon",
            reason="easynet_cli_missing",
        ) from None
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip()
        raise Unavailable(
            f"`easynet {' '.join(args)}` failed: {detail}",
            reason="easynet_cli_failed",
        ) from None
