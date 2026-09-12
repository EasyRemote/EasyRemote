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
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import easynet_sdk

from ._binding_lease import MAX_BINDINGS, BindingLeaseWorker
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
_BINDING_CONTROL_TIMEOUT_SECONDS = 2.0
_BINDING_CLEANUP_TIMEOUT_SECONDS = 3.0


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
        activation_id: str | None = None,
        node: str = "local",
        timeout: float | None = None,
    ) -> object: ...

    def renew_bindings(
        self,
        bindings: tuple[easynet_sdk.BindingLeaseRef, ...],
        *,
        node: str = "local",
        timeout: float,
    ) -> object: ...


class PublicationState(StrEnum):
    """Observable host/publication lifecycle without claiming early realm visibility."""

    STOPPED = "STOPPED"
    LOCAL_ACTIVE = "LOCAL_ACTIVE"
    ADVERTISE_PENDING = "ADVERTISE_PENDING"
    REALM_VISIBLE = "REALM_VISIBLE"
    LEASE_FAILED = "LEASE_FAILED"


class _ProviderState(StrEnum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    ACTIVE = "ACTIVE"
    STOPPING = "STOPPING"
    FAILED = "FAILED"


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
    activation_id: str | None = None


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
        self._lease_worker: BindingLeaseWorker | None = None
        self._lease_failure: BaseException | None = None
        self._serve_exit = threading.Event()
        self._lifecycle_lock = threading.RLock()
        self._provider_state = _ProviderState.STOPPED
        self._generation = 0

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
        if len(self._abilities) >= MAX_BINDINGS:
            raise InvalidArgument(
                "A provider supports at most 256 functions",
                reason="binding_limit_exceeded",
            )
        with self._lifecycle_lock:
            self._check_lease_health()
            if self._provider_state not in (
                _ProviderState.STOPPED,
                _ProviderState.ACTIVE,
            ):
                raise Unavailable(
                    "Provider lifecycle is changing", reason="provider_busy"
                )
            generation = self._generation

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
                with self._lifecycle_lock:
                    self._require_generation(generation)
                    self._abilities[ability_name] = info
                    self._track_binding(info)
                    self._check_lease_health()
                    self._publication_state = PublicationState.ADVERTISE_PENDING
        except BaseException as error:
            with self._lifecycle_lock:
                if self._generation != generation:
                    raise
                deployed = self._abilities.pop(ability_name, None)
                self._host.remove(qualified)
            if deployed is not None and deployed.install_id is not None:
                try:
                    self._revoke_binding(deployed, _BINDING_CONTROL_TIMEOUT_SECONDS)
                except BaseException as cleanup_error:
                    error.add_note(f"registration rollback failed: {cleanup_error}")
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
            self._serve_exit.wait()
            self._check_lease_health()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._provider_state is _ProviderState.ACTIVE:
                self._check_lease_health()
                return
            if self._provider_state is not _ProviderState.STOPPED:
                self._check_lease_health()
                raise Unavailable(
                    "Provider lifecycle is changing", reason="provider_busy"
                )
            self._provider_state = _ProviderState.STARTING
            self._generation += 1
            generation = self._generation
            self._lease_failure = None
            self._serve_exit.clear()
        try:
            self._check_gateway()
            connection = self._runtime_provider.connect()
            with self._lifecycle_lock:
                stale_connection = self._generation != generation
                if not stale_connection:
                    self._runtime_connection = connection
                    self._host.start()
                    self._publication_state = PublicationState.LOCAL_ACTIVE
            if stale_connection:
                _close_runtime_connection(connection)
                self._require_generation(generation)
            for ability_name, info in list(self._abilities.items()):
                self._check_lease_health()
                deployed = self._deploy(info)
                with self._lifecycle_lock:
                    self._require_generation(generation)
                    self._abilities[ability_name] = deployed
                    self._track_binding(deployed)
                    self._check_lease_health()
            with self._lifecycle_lock:
                self._require_generation(generation)
                self._check_lease_health()
                self._publication_state = PublicationState.ADVERTISE_PENDING
                self._started = True
                self._provider_state = _ProviderState.ACTIVE
        except BaseException as error:
            try:
                self._shutdown(expected_generation=generation)
            except BaseException as cleanup_error:
                error.add_note(f"provider rollback failed: {cleanup_error}")
            raise

    def stop(self) -> None:
        self._shutdown()

    def _shutdown(self, *, expected_generation: int | None = None) -> None:
        with self._lifecycle_lock:
            if (
                expected_generation is not None
                and expected_generation != self._generation
            ):
                return
            if self._provider_state is _ProviderState.STOPPED:
                return
            if self._provider_state is _ProviderState.STOPPING:
                raise Unavailable(
                    "Provider is already stopping", reason="provider_busy"
                )
            self._provider_state = _ProviderState.STOPPING
            self._generation += 1
            self._serve_exit.set()
        failure: BaseException | None = None
        try:
            if self._lease_worker is not None:
                self._lease_worker.stop()
            self._revoke_deployments()
        except BaseException as error:
            failure = error
        finally:
            try:
                self._host.stop()
            finally:
                connection = self._runtime_connection
                self._runtime_connection = None
                self._started = False
                self._publication_state = PublicationState.STOPPED
                self._lease_worker = None
                try:
                    if connection is not None:
                        _close_runtime_connection(connection)
                finally:
                    with self._lifecycle_lock:
                        self._provider_state = _ProviderState.STOPPED
        if failure is not None:
            raise failure

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
        if self._lease_worker is not None and self._lease_worker.failure is not None:
            return PublicationState.LEASE_FAILED
        return self._publication_state

    @property
    def lease_failure(self) -> BaseException | None:
        if self._lease_worker is not None and self._lease_worker.failure is not None:
            return self._lease_worker.failure
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
        activation_id = getattr(result, "activation_id", None)
        if not all(
            isinstance(value, str) and value.strip()
            for value in (ability_ura, install_id, activation_id)
        ):
            raise Unavailable(
                "Runtime did not acknowledge a complete process binding; "
                "use a Runtime supporting activation-guarded binding renewal",
                reason="binding_activation_missing",
            )
        return dataclasses.replace(
            info, ura=ability_ura, install_id=install_id, activation_id=activation_id
        )

    def _track_binding(self, info: AbilityInfo) -> None:
        if self._lease_worker is None:
            generation = self._generation
            self._lease_worker = BindingLeaseWorker(
                lambda refs, timeout: self._ability_control.renew_bindings(
                    refs, node="local", timeout=timeout
                ),
                lambda error: self._binding_lease_failed(generation, error),
                interval=_BINDING_RENEW_INTERVAL_SECONDS,
                timeout=_BINDING_CONTROL_TIMEOUT_SECONDS,
            )
        assert info.ura and info.install_id and info.activation_id
        self._lease_worker.add(
            easynet_sdk.BindingLeaseRef(
                ability_ura=info.ura,
                install_id=info.install_id,
                activation_id=info.activation_id,
            )
        )

    def _binding_lease_failed(self, generation: int, error: BaseException) -> None:
        with self._lifecycle_lock:
            if generation != self._generation:
                return
            self._lease_failure = error
            self._publication_state = PublicationState.LEASE_FAILED
            self._provider_state = _ProviderState.FAILED
            self._serve_exit.set()
        self._host.stop()

    def _require_generation(self, generation: int) -> None:
        if generation != self._generation:
            raise Unavailable(
                "Provider startup was stopped; late deployment cannot be renewed",
                reason="provider_start_cancelled",
            )

    def _check_lease_health(self) -> None:
        failure = self.lease_failure
        if failure is not None:
            raise Unavailable(
                "Provider binding renewal failed; stop the provider, inspect the "
                "Runtime error, then explicitly restart",
                reason="binding_lease_failed",
            ) from failure

    def _revoke_binding(self, info: AbilityInfo, timeout: float) -> None:
        if info.install_id is None or info.ura is None or info.activation_id is None:
            return
        self._ability_control.uninstall(
            info.ura,
            install_id=info.install_id,
            activation_id=info.activation_id,
            node="local",
            timeout=timeout,
        )

    def _revoke_deployments(self) -> None:
        deadline = time.monotonic() + _BINDING_CLEANUP_TIMEOUT_SECONDS
        failure: BaseException | None = None
        for ability_name, info in reversed(list(self._abilities.items())):
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Unavailable(
                        "Binding cleanup deadline elapsed; "
                        "remaining leases will expire",
                        reason="binding_cleanup_timeout",
                    )
                self._revoke_binding(info, remaining)
            except BaseException as error:
                if failure is None:
                    failure = error
            finally:
                self._abilities[ability_name] = dataclasses.replace(
                    info, install_id=None, activation_id=None
                )
        if failure is not None:
            raise failure

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
