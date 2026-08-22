"""ComputeNode: publish local functions on a Device execution host.

Ontology, corrected: **a node is a device, not an agent.** Registered
functions become ability-management SystemAgent-owned abilities, deployed through the
Python ``AbilityControl`` facade, which invokes
the daemon's canonical ``ability.deploy`` install transaction. Every
EasyRemote ability binds to the daemon-owned ``host_stream`` executor:
the daemon opens the warm host socket, sends the JSON argument object
plus read-only caller identity, and receives one or many stream frames.
That executor is an implementation transport. The public descriptor remains
RPC for ordinary functions and Stream for generators.

This module owns packaging and local host registration only. Runtime process
lifecycle, Invocation admission, descriptor binding, routing, receipt
production, and stream terminal semantics stay with the canonical SDK runtime.
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
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import easynet_sdk

from ._host import HostServer
from ._host.server import HostedFunction
from ._json import dumps_wire
from .config import settings
from .context import Context
from .control import AbilityControl
from .errors import InvalidArgument, Unavailable, error_from_sdk
from .runtime_provider import LocalRuntimeProvider, RuntimeConnectionProvider
from .schema import PARAMETER_ORDER_KEY, derive

__all__ = ["AbilityInfo", "ComputeNode", "PublicationState", "RegisteredFunction"]

_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_BINDING_LEASE_MS = 9_000
_BINDING_RENEW_INTERVAL_SECONDS = 3.0


class _AbilityInstaller(Protocol):
    def install(
        self,
        path: str | Path,
        *,
        node: str = "local",
        binding_lease_ms: int | None = None,
    ) -> object: ...

    def uninstall(
        self,
        ability_ura: str,
        *,
        install_id: str | None = None,
        node: str = "local",
    ) -> object: ...


class PublicationState(StrEnum):
    """Observable host/publication lifecycle without claiming early realm visibility."""

    STOPPED = "STOPPED"
    LOCAL_ACTIVE = "LOCAL_ACTIVE"
    ADVERTISE_PENDING = "ADVERTISE_PENDING"
    REALM_VISIBLE = "REALM_VISIBLE"


@dataclass(frozen=True)
class AbilityInfo:
    """One registered capability, as packaged on disk.

    ``ura`` is the canonical SystemAgent-owned Ability URA when this machine is
    paired (RFC-001 shape, mirrored from `easynet ability invoke`'s own
    documentation); None in unpaired/test environments.
    """

    name: str
    qualified_name: str
    package_dir: Path
    ura: str | None
    install_id: str | None = None


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

    ``ability_control``/``abilities_dir``/``runtime_provider`` are injectable
    seams; production code uses the canonical local runtime provider.
    """

    def __init__(
        self,
        gateway: str | None = None,
        *,
        namespace: str = "er",
        abilities_dir: Path | None = None,
        ability_control: _AbilityInstaller | None = None,
        runtime_provider: RuntimeConnectionProvider | None = None,
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
        self._runtime_provider = runtime_provider or LocalRuntimeProvider()
        self._runtime_connection: easynet_sdk.RuntimeConnection | None = None
        self._host = HostServer(self._abilities_dir.parent / "host.sock")
        self._abilities: dict[str, AbilityInfo] = {}
        self._started = False
        self._publication_state = PublicationState.STOPPED
        self._gateway_checked = False
        self._lease_stop = threading.Event()
        self._lease_thread: threading.Thread | None = None
        self._lease_failure: BaseException | None = None

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
            signature.is_stream,
        )
        hosted = HostedFunction(name=qualified, fn=fn, signature=signature)
        self._host.add(hosted)
        info = AbilityInfo(
            name=ability_name,
            qualified_name=qualified,
            package_dir=package_dir,
            ura=self._hosted_ability_ura(ability_name),
        )
        try:
            self._abilities[ability_name] = info
            if self._started:
                info = self._deploy(info)
                self._abilities[ability_name] = info
                self._publication_state = PublicationState.ADVERTISE_PENDING
                self._start_binding_lease_renewal()
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
        connection = self._runtime_provider.connect()
        try:
            self._host.start()
            self._publication_state = PublicationState.LOCAL_ACTIVE
            for ability_name, info in list(self._abilities.items()):
                self._abilities[ability_name] = self._deploy(info)
            self._publication_state = PublicationState.ADVERTISE_PENDING
        except BaseException as error:
            try:
                self._revoke_deployments()
            except BaseException as revoke_error:
                error.add_note(f"rollback ability.uninstall failed: {revoke_error}")
            self._host.stop()
            _close_runtime_connection(connection)
            self._started = False
            self._publication_state = PublicationState.STOPPED
            raise
        self._runtime_connection = connection
        self._started = True
        self._start_binding_lease_renewal()

    def stop(self) -> None:
        if not self._started:
            return
        self._stop_binding_lease_renewal()
        self._revoke_deployments()
        try:
            self._host.stop()
        finally:
            connection = self._runtime_connection
            self._runtime_connection = None
            self._started = False
            self._publication_state = PublicationState.STOPPED
            if connection is not None:
                _close_runtime_connection(connection)

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

    @property
    def publication_state(self) -> PublicationState:
        return self._publication_state

    @property
    def lease_failure(self) -> BaseException | None:
        return self._lease_failure

    # -- internals ---------------------------------------------------------------

    def _deploy(self, info: AbilityInfo) -> AbilityInfo:
        """Bind the live host implementation and retain its revocation identity."""
        result = self._ability_control.install(
            info.package_dir,
            node="local",
            binding_lease_ms=_BINDING_LEASE_MS,
        )
        ability_ura = getattr(result, "ability_ura", None) or info.ura
        install_id = getattr(result, "install_id", None)
        return dataclasses.replace(info, ura=ability_ura, install_id=install_id)

    def _start_binding_lease_renewal(self) -> None:
        if not self._abilities or self._lease_thread is not None:
            return
        self._lease_stop.clear()
        self._lease_failure = None
        self._lease_thread = threading.Thread(
            target=self._renew_binding_leases,
            name="easyremote-binding-lease",
            daemon=True,
        )
        self._lease_thread.start()

    def _stop_binding_lease_renewal(self) -> None:
        self._lease_stop.set()
        thread = self._lease_thread
        if thread is not None:
            thread.join()
        self._lease_thread = None

    def _renew_binding_leases(self) -> None:
        while not self._lease_stop.wait(_BINDING_RENEW_INTERVAL_SECONDS):
            try:
                for ability_name, info in list(self._abilities.items()):
                    if self._lease_stop.is_set():
                        return
                    self._abilities[ability_name] = self._deploy(info)
                self._lease_failure = None
                self._publication_state = PublicationState.ADVERTISE_PENDING
            except BaseException as error:
                self._lease_failure = error
                self._publication_state = PublicationState.LOCAL_ACTIVE

    def _revoke_deployments(self) -> None:
        for ability_name, info in reversed(list(self._abilities.items())):
            if info.install_id is None or info.ura is None:
                continue
            self._ability_control.uninstall(
                info.ura,
                install_id=info.install_id,
                node="local",
            )
            self._abilities[ability_name] = dataclasses.replace(info, install_id=None)

    def _print_ready(self) -> None:
        """Show the user what became callable through the connected runtime."""

        if self._runtime_connection is None:
            return
        print("✓ Connected to canonical runtime")
        for ability in self._abilities.values():
            print(f"✓ Local active {ability.ura or ability.qualified_name}")
        if self._abilities:
            print("… Realm advertisement pending")

    def _write_package(
        self,
        local_name: str,
        qualified: str,
        description: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any] | None,
        is_stream: bool,
    ) -> Path:
        # Canonical manifest for the daemon's `ability.deploy` install
        # transaction. The SDK builder owns the deploy-bundle DTO shape so this
        # product package cannot drift into legacy manifest metadata
        # (`category`, `tool_name`, `version`, hint fields). `name` is the verb
        # only; `namespace` carries the public key segment, and the daemon
        # assembles the wire key `er.<verb>` from them. Schemas keep their true
        # semantics: the stdin contract has no missing-template failure mode,
        # so optionals stay optional.
        #
        # EVERY ability routes through the host_stream transport: it carries
        # full args + caller identity in the request frame (the shell
        # executor nulls stdin and only templates argv, so it cannot pass
        # arbitrary JSON args or the caller). Descriptor geometry follows
        # the function signature: unary functions are RPC and generators are
        # server-stream. Field names match the daemon's AbilityExec::HostStream
        # serde shape (internally tagged `kind`, snake_case) verbatim.
        manifest = easynet_sdk.RuntimeAbilityPackageManifest(
            name=local_name,
            namespace=self._namespace,
            description=description,
            admission_action="stream" if is_stream else "invoke",
            exposure="task",
            input_schema=input_schema,
            output_schema=output_schema,
            exec=easynet_sdk.HostStreamExec(
                host_socket=str(self._host.socket_path),
                function=qualified,
                protocol="binary_v1",
            ),
        ).to_mapping()

        package_dir = self._abilities_dir / qualified
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "ability.json").write_text(
            dumps_wire(manifest, what="ability manifest", indent=2) + "\n",
            encoding="utf-8",
        )
        return package_dir

    def _hosted_ability_ura(self, ability_name: str) -> str | None:
        try:
            from ._product_abilities import SystemAgentId
            from .identity import LocalIdentity, system_agent_ability_ura

            identity = LocalIdentity.load()
        except Exception:
            return None  # unpaired / test environment: absent beats invented
        return system_agent_ability_ura(
            identity.realm,
            identity.node_id,
            str(SystemAgentId.ABILITY_MANAGEMENT),
            f"{self._namespace}.{ability_name}",
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


def _close_runtime_connection(connection: easynet_sdk.RuntimeConnection) -> None:
    try:
        connection.close()
    except easynet_sdk.SDKError as exc:
        raise error_from_sdk(exc) from exc


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
