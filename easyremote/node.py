"""ComputeNode: publish local functions as device-owned abilities.

Ontology, corrected: **a node is a device, not an agent.** Registered
functions become device-owned abilities —

    easynet:///r/<realm>/ability/device.<node-id>.<namespace>.<fn>

— deployed through the Python ``AbilityControl`` facade, which invokes
the daemon's canonical ``ability.deploy`` install transaction. Every
EasyRemote ability binds to the daemon-owned ``host_stream`` executor:
the daemon opens the warm host socket, sends the JSON argument object
plus read-only caller identity, and receives one or many stream frames.
Unary functions are single-frame streams; generators are multi-frame
streams.

This module owns packaging and local host registration only. Invocation
admission, descriptor binding, routing, receipt production, and stream
terminal semantics stay with ``easynet-daemon`` / Axon.
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import inspect
import re
import threading
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ._host import HostServer
from ._host.server import HostedFunction
from ._json import dumps_wire
from ._version import __version__
from .bootstrap import DeviceRuntimeBootstrap, DeviceRuntimeLease, RuntimeBootstrap
from .config import settings
from .context import Context
from .control import AbilityControl
from .errors import InvalidArgument, Unavailable
from .schema import PARAMETER_ORDER_KEY, derive

__all__ = ["AbilityInfo", "ComputeNode", "RegisteredFunction"]

_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class _AbilityInstaller(Protocol):
    def install(self, path: str | Path, *, node: str = "local") -> object: ...


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

    ``ability_control``/``abilities_dir`` are injectable seams (tests);
    production code never passes them.
    """

    def __init__(
        self,
        gateway: str | None = None,
        *,
        namespace: str = "er",
        abilities_dir: Path | None = None,
        ability_control: _AbilityInstaller | None = None,
        runtime_bootstrap: RuntimeBootstrap | None = None,
    ) -> None:
        if not _NAME_PATTERN.match(namespace):
            raise InvalidArgument(
                f"namespace {namespace!r} must match {_NAME_PATTERN.pattern}",
                reason="invalid_namespace",
            )
        self._gateway = gateway
        self._namespace = namespace
        self._abilities_dir = abilities_dir or (
            _default_easyremote_root() / "abilities"
        )
        self._ability_control = ability_control or AbilityControl()
        self._runtime_bootstrap = runtime_bootstrap or DeviceRuntimeBootstrap()
        self._runtime_lease: DeviceRuntimeLease | None = None
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

        ability_name = name if name is not None else str(getattr(fn, "__name__", ""))
        if name is None and not _NAME_PATTERN.match(ability_name):
            # A lambda / partial has no public ability-safe name. Mint a
            # stable name from its source location and bound arguments so
            # repeated registration of the same callable is idempotent. An
            # explicit name= always wins.
            ability_name = _derived_lambda_name(fn)
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
        # A Context-taking function also routes through host_stream: that
        # is the only exec path that carries the caller identity / call_id
        # the host needs to build the Context. (A unary Context function's
        # single return value rides back as one terminal frame.)
        package_dir = self._write_package(
            ability_name,
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
        try:
            self._abilities[ability_name] = info
            if self._started:
                self._deploy(info)  # post-start registration: publish immediately
        except BaseException:
            self._abilities.pop(ability_name, None)
            self._host.remove(qualified)
            raise
        return RegisteredFunction(hosted, info)

    # -- lifecycle -----------------------------------------------------------

    def serve(self) -> None:
        """Blocking serve; Ctrl-C exits cleanly."""
        try:
            self.start()
        except Unavailable as exc:
            if exc.reason != "onboarding_required":
                raise
            print(exc)
            return
        self._print_ready()
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def start(self) -> None:
        if self._started:
            return
        self._check_gateway()
        runtime_lease = self._runtime_bootstrap.ensure()
        self._host.start()
        try:
            for info in self._abilities.values():
                self._deploy(info)
        except BaseException:
            self._host.stop()
            runtime_lease.close()
            self._started = False
            raise
        self._runtime_lease = runtime_lease
        self._started = True

    def stop(self) -> None:
        try:
            self._host.stop()
        finally:
            lease = self._runtime_lease
            self._runtime_lease = None
            self._started = False
            if lease is not None:
                lease.close()

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
        self._ability_control.install(info.package_dir, node="local")

    def _print_ready(self) -> None:
        """Show the user what became callable without exposing bootstrap APIs."""

        lease = self._runtime_lease
        if lease is None:
            return
        action = "started" if lease.started_daemon else "reused"
        print(f"✓ {action} easynet-daemon for {lease.identity.device_ura}")
        for ability in self._abilities.values():
            print(f"✓ Published {ability.ura or ability.qualified_name}")

    def _write_package(
        self,
        local_name: str,
        qualified: str,
        description: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any] | None,
    ) -> Path:
        # Canonical manifest for the daemon's `ability.deploy` install
        # transaction. `name` is the verb only (the daemon's
        # AbilityManifest.name forbids dots); `namespace` carries the
        # `er` segment separately, and the daemon assembles the wire key
        # `er.<verb>` from them. `tool_name` keeps the qualified form for
        # human-facing surfaces. Schemas keep their true semantics: the
        # stdin contract has no missing-template failure mode, so
        # optionals stay optional.
        manifest: dict[str, Any] = {
            "category": "easyremote",
            "description": description,
            "destructive_hint": False,
            "idempotent_hint": False,
            "input_schema": input_schema,
            "instructions": description,
            "name": local_name,
            "namespace": self._namespace,
            "open_world_hint": False,
            "prerequisites": [],
            "read_only_hint": False,
            "tags": ["easyremote"],
            "tool_name": qualified,
            "version": __version__,
        }
        if output_schema is not None:
            manifest["output_schema"] = output_schema
        # EVERY ability routes through the host_stream executor: it carries
        # full args + caller identity in the request frame (the shell
        # executor nulls stdin and only templates argv, so it cannot pass
        # arbitrary JSON args or the caller). A unary function emits one
        # terminal frame; a generator emits many. One path, no exec
        # mismatch. Field names match the daemon's AbilityExec::HostStream
        # serde shape (internally tagged `kind`, snake_case) verbatim.
        manifest["exec"] = {
            "kind": "host_stream",
            "host_socket": str(self._host.socket_path),
            "function": qualified,
        }

        package_dir = self._abilities_dir / qualified
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "ability.json").write_text(
            dumps_wire(manifest, what="ability manifest", indent=2) + "\n",
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


def _derived_lambda_name(fn: Callable[..., Any]) -> str:
    """A stable, valid ability name for a lambda or partial."""
    code = getattr(fn, "__code__", None)
    if code is not None:
        seed = f"lambda:{code.co_filename}:{code.co_firstlineno}"
    elif isinstance(fn, functools.partial):
        inner = getattr(fn.func, "__code__", None)
        if inner is not None:
            seed = (
                f"partial:{inner.co_filename}:{inner.co_firstlineno}:"
                f"{_stable_repr(fn.args)}:{_stable_repr(fn.keywords or {})}"
            )
        else:
            seed = f"partial:{type(fn.func).__module__}.{type(fn.func).__qualname__}"
    else:
        seed = f"callable:{type(fn).__module__}.{type(fn).__qualname__}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"fn_{digest}"


def _default_easyremote_root() -> Path:
    """Product-local EasyRemote root under the configured EasyNet process root."""
    return settings().control_path.parent / "easyremote"


def _stable_repr(value: Any) -> str:
    """Stable-ish representation for callable-name seeds.

    Primitive JSON-like values keep their literal representation. Other
    objects fall back to type identity rather than memory address so names
    do not change only because a process restarted.
    """
    if isinstance(value, (str, int, float, bool, type(None))):
        return repr(value)
    if isinstance(value, tuple):
        return "(" + ",".join(_stable_repr(item) for item in value) + ")"
    if isinstance(value, list):
        return "[" + ",".join(_stable_repr(item) for item in value) + "]"
    if isinstance(value, dict):
        items = sorted((repr(key), _stable_repr(item)) for key, item in value.items())
        return "{" + ",".join(f"{key}:{item}" for key, item in items) + "}"
    return f"<{type(value).__module__}.{type(value).__qualname__}>"


def _first_doc_line(fn: Callable[..., Any]) -> str:
    doc = inspect.getdoc(fn)
    return doc.splitlines()[0].strip() if doc else ""
