"""Client: call capabilities (SPEC §5.6).

Three layers, two daemon carriers:

- L0 ``execute`` — v2 hello-world surface, keyword-or-discovered args.
- L1 ``call`` / ``stream`` / ``session`` — hosted abilities on
  ``host_stream``; unary functions are single-frame streams.
- L2 ``invoke`` / ``prepare`` — daemon unary/system abilities, with
  the seven-tuple inspectable before dispatch.

Addressing: the caller is this device (pairing identity). Product target
selection is projected to an Ability URA through the SDK Addressing provider,
and the SDK Invocation provider derives the complete canonical draft. Daemon
route policy remains behind easynet-daemon.

Per-call timeouts are client-side only: the caller's wait is bounded,
while server-side execution remains governed by the manifest's
``timeout_seconds``. Timed-out unary calls may still finish in the daemon;
the client stops waiting.
"""

from __future__ import annotations

import functools
import inspect
import math
import threading
import weakref
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal, cast

import easynet_sdk

from . import _codec
from ._addressing import (
    PICK_POLICIES,
    AbilityAddressResolver,
    ResolvedAbility,
    canonical_addressing_client,
)
from ._sdk_transport import FrameStream, Transport, UnaryDispatchPool
from .errors import (
    InvalidArgument,
    RemoteError,
    Unavailable,
    error_from_sdk,
)
from .identity import LocalIdentity, agent_ura, device_ura, hub_ura
from .invocation import (
    Invocation,
    PreparedInvocation,
    StreamSpec,
)
from .invocation_policy import (
    InvocationDerivationPolicy,
    require_invocation_policy,
    runtime_root_context,
)
from .schema import PARAMETER_ORDER_KEY, VAR_POSITIONAL_KEY

__all__ = [
    "BidiSession",
    "CallTarget",
    "Client",
    "FunctionInfo",
    "RemoteAbility",
    "RemoteFunction",
    "RemoteOwner",
    "Stream",
    "remote",
]

if TYPE_CHECKING:
    from .agent import RemoteAgent
    from .control import AbilityControl, AgentControl
    from .mission import MissionControl


@dataclass(frozen=True)
class FunctionInfo:
    """One discoverable capability.

    ``qualified_name`` remains the public EasyRemote field while
    ``ability_ura`` is the canonical name used by runtime collaborators.
    """

    name: str  # verb, e.g. "ai_inference"
    qualified_name: str  # full ability URA, daemon-issued
    owner: str
    description: str
    input_schema: dict[str, Any]
    visibility: str
    score: float
    descriptor_ref: str = ""

    @property
    def ability_ura(self) -> str:
        return self.qualified_name

    @classmethod
    def from_candidate(cls, candidate: dict[str, Any]) -> FunctionInfo:
        return cls(
            name=str(candidate.get("ability", "")),
            qualified_name=str(
                candidate.get("ability_ura") or candidate.get("qualified_name") or ""
            ),
            owner=str(candidate.get("owner", "")),
            description=str(candidate.get("description", "")),
            input_schema=dict(candidate.get("input_schema") or {}),
            visibility=str(candidate.get("visibility", "")),
            score=float(candidate.get("score", 0.0)),
            descriptor_ref=str(candidate.get("descriptor_ref") or ""),
        )

    @classmethod
    def from_catalog_row(
        cls,
        row: Mapping[str, Any],
        *,
        namespace: str,
    ) -> FunctionInfo:
        """Project one daemon catalogue row into EasyRemote's public shape.

        The daemon catalogue is the canonical discovery source. EasyRemote only
        adapts field names for its historical API; it does not own discovery,
        descriptor binding, admission, or receipt interpretation.
        """

        raw_name = str(row.get("name") or row.get("ability") or "")
        product_name = _product_function_name(raw_name, namespace)
        schema = row.get("input_schema")
        if not isinstance(schema, Mapping):
            summary = row.get("schema_summary")
            if isinstance(summary, Mapping):
                schema = summary.get("input")
        return cls(
            name=product_name,
            qualified_name=str(
                row.get("ability_ura")
                or row.get("qualified_name")
                or row.get("descriptor_ref")
                or ""
            ),
            owner=str(row.get("owner_ura") or row.get("owner") or ""),
            description=str(row.get("description") or ""),
            input_schema=dict(schema) if isinstance(schema, Mapping) else {},
            visibility=str(row.get("visibility") or ""),
            score=float(row.get("score", 1.0)),
            descriptor_ref=str(row.get("descriptor_ref") or ""),
        )


@dataclass(frozen=True)
class CallTarget:
    """An invocation target plus client-side dispatch options.

    Ability arguments live only in ``Client.call/stream/invoke`` kwargs.
    Targeting, selection, timeout, metadata, and a per-target product policy live
    here so user functions may legitimately expose parameters named ``node``,
    ``pick``, ``timeout``, ``subject``, or ``metadata`` without colliding with
    the client control plane.

    The former target-field migration notice ended with
    ``in EasyRemote 3.0.0; use invocation_policy``. No target-field adapter
    remains: invocation derivation must now be selected explicitly.
    """

    function: str
    node: str | None = None
    pick: Literal["round_robin", "random"] | None = None
    timeout: float | None = None
    sign: bool | None = None
    metadata: Mapping[str, str] | None = None
    owner_ura: str | None = None
    invocation_policy: InvocationDerivationPolicy | None = None

    def __post_init__(self) -> None:
        if not self.function.strip():
            raise InvalidArgument(
                "target function must not be empty", reason="empty_function"
            )
        if self.node is not None and self.pick is not None:
            raise InvalidArgument(
                "target cannot specify both node and pick",
                reason="ambiguous_target_selection",
            )
        if self.owner_ura is not None and (
            self.node is not None or self.pick is not None
        ):
            raise InvalidArgument(
                "target cannot combine an explicit owner with node or pick"
                " — an owner handle already names the callee",
                reason="ambiguous_target_selection",
            )
        if self.pick is not None and self.pick not in PICK_POLICIES:
            raise InvalidArgument(
                f"pick must be one of {sorted(PICK_POLICIES)}, got {self.pick!r}"
                " (resource_aware selection is not supported)",
                reason="invalid_pick_policy",
            )
        if self.timeout is not None and (
            not math.isfinite(self.timeout) or self.timeout <= 0
        ):
            raise InvalidArgument(
                f"timeout must be a positive finite number of seconds,"
                f" got {self.timeout!r}",
                reason="invalid_timeout",
            )
        if self.metadata is not None:
            object.__setattr__(self, "metadata", dict(self.metadata))
        if self.invocation_policy is not None:
            require_invocation_policy(
                self.invocation_policy,
                field="target invocation_policy",
            )


class Stream:
    """Frames from a server-stream invocation.

    The SDK Runtime Core transport adapter owns daemon frame projection,
    timeout, terminal, and wire-error semantics. This product facade exposes
    Python iteration and maps SDK errors into EasyRemote's public taxonomy.
    """

    def __init__(self, frames: FrameStream, *, timeout: float | None = None) -> None:
        self._frames = frames
        self._adapter = easynet_sdk.StreamValueAdapter(
            cast(easynet_sdk.FrameStream, frames),
            timeout=timeout,
        )

    def __iter__(self) -> Iterator[Any]:
        try:
            for item in self._adapter:
                yield item.value
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def close(self) -> None:
        self._frames.close()

    def __enter__(self) -> Stream:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


_NO_VALUE = object()  # descriptor sentinel for "no bound instance"
_DEFAULT_TIMEOUT = object()  # sentinel: use Client._timeout


class BidiSession:
    """A bidirectional invocation session (context manager).

    The SDK owns daemon bidi lifecycle semantics. This class keeps EasyRemote's
    public method names and maps SDK errors into EasyRemote's taxonomy.
    """

    def __init__(self, session: easynet_sdk.BidiSessionAdapter) -> None:
        self._session = session

    def send(self, frame: dict[str, Any]) -> None:
        try:
            self._session.send(frame)
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def recv(self, timeout: float | None = None) -> dict[str, Any] | None:
        try:
            return cast("dict[str, Any] | None", self._session.recv(timeout=timeout))
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def close(self) -> None:
        try:
            self._session.close()
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def cancel(self, reason: str = "client cancel") -> None:
        try:
            self._session.cancel(reason)
        except easynet_sdk.SDKError as exc:
            raise error_from_sdk(exc) from exc

    def __enter__(self) -> BidiSession:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class Client:
    """Synchronous client against the local easynet-daemon.

    ``transport``/``identity`` are injectable seams (tests, daemon
    handle reuse); production code never passes them.
    """

    def __init__(
        self,
        gateway: str | None = None,
        *,
        timeout: float = 30.0,
        namespace: str = "er",
        transport: Transport | None = None,
        identity: LocalIdentity | None = None,
        signer: easynet_sdk.Signer | None = None,
        invocation_policy: InvocationDerivationPolicy | None = None,
    ) -> None:
        self._gateway = gateway
        self._gateway_checked = False
        if not math.isfinite(timeout) or timeout <= 0:
            raise InvalidArgument(
                f"timeout must be a positive finite number of seconds, got {timeout!r}",
                reason="invalid_timeout",
            )
        self._invocation_policy = (
            require_invocation_policy(
                invocation_policy,
                field="client invocation_policy",
            )
            if invocation_policy is not None
            else None
        )
        self._timeout = timeout
        self._namespace = namespace
        self._addressing = AbilityAddressResolver(
            namespace,
            canonical_addressing_client(),
        )
        self._identity_override = identity
        self._signer = signer
        self._lock = threading.Lock()
        self._unary_pool = (
            UnaryDispatchPool.from_transport(transport)
            if transport is not None
            else UnaryDispatchPool.connect()
        )
        self._identity: LocalIdentity | None = None

    # -- L0 ------------------------------------------------------------------

    def execute(self, function: str | CallTarget, /, *args: Any, **kwargs: Any) -> Any:
        return self.call(function, *args, **kwargs)

    # -- L1 ------------------------------------------------------------------

    def call(
        self,
        function: str | CallTarget,
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        target = self._target(function)
        resolved = self._address(
            target.function, target.node, target.pick, target.owner_ura
        )
        prepared = self._prepare_resolved(
            target,
            resolved,
            args,
            kwargs,
            call_mode=_sdk_call_mode(resolved.call_carrier),
        )
        if prepared.call_carrier == "unary":
            return prepared.send().result()
        # EasyRemote abilities register stream-mode (host_stream), so a
        # result-first call drains the frame stream. A unary function
        # emits exactly one frame → return it; a generator drained via
        # `call` returns its frames as a list (use `stream()` for live
        # iteration). Empty stream → None.
        frames = list(self._open_stream(prepared, timeout=target.timeout))
        if not frames:
            return None
        return frames[0] if len(frames) == 1 else frames

    def stream(
        self, function: str | CallTarget, /, *args: Any, **kwargs: Any
    ) -> Stream:
        target = self._target(function)
        prepared = self._prepare(target, args, kwargs, call_mode="stream")
        return self._open_stream(prepared, timeout=target.timeout)

    def _open_stream(
        self, prepared: PreparedInvocation, *, timeout: float | None
    ) -> Stream:
        wait_budget = self._timeout if timeout is None else timeout
        return Stream(
            self._connected().stream(prepared.draft),
            timeout=wait_budget,
        )

    def session(
        self,
        function: str | CallTarget,
        /,
        *,
        streams: list[StreamSpec] | None = None,
        **kwargs: Any,
    ) -> BidiSession:
        target = self._target(function)
        prepared = self._prepare(target, (), kwargs, call_mode="bidi")
        descriptors = streams or [
            StreamSpec(stream_id=1, content_type="application/json")
        ]
        return BidiSession(
            easynet_sdk.BidiSessionAdapter(
                self._connected().bidi(prepared.draft, descriptors)
            )
        )

    # -- L2 ------------------------------------------------------------------

    def invoke(
        self,
        function: str | CallTarget,
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Invocation:
        return self.prepare(function, *args, **kwargs).send()

    def prepare(
        self,
        function: str | CallTarget,
        /,
        *args: Any,
        **kwargs: Any,
    ) -> PreparedInvocation:
        return self._prepare(self._target(function), args, kwargs, call_mode="rpc")

    def _prepare(
        self,
        target: CallTarget,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        call_mode: str,
    ) -> PreparedInvocation:
        resolved = self._address(
            target.function, target.node, target.pick, target.owner_ura
        )
        return self._prepare_resolved(
            target,
            resolved,
            args,
            kwargs,
            call_mode=call_mode,
        )

    def _prepare_resolved(
        self,
        target: CallTarget,
        resolved: ResolvedAbility,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        call_mode: str,
    ) -> PreparedInvocation:
        payload = self._named_arguments(resolved, args, kwargs)
        policy = (
            target.invocation_policy
            if target.invocation_policy is not None
            else self._invocation_policy
        )
        if policy is None:
            raise InvalidArgument(
                "public invocation requires an explicit derivation policy on"
                " Client or CallTarget",
                reason="missing_invocation_derivation_policy",
            )
        request = policy.derive(
            caller_ura=self._who().device_ura,
            ability_ura=resolved.ability_ura,
            resolved_subject_ura=resolved.resolved_subject_ura,
            args=payload,
            metadata=target.metadata or {},
        )
        request = replace(request, call_mode=call_mode)
        descriptor_ref = resolved.descriptor_ref or self._runtime_descriptor_ref(
            resolved,
            call_mode=call_mode,
        )
        if descriptor_ref:
            request = replace(
                request,
                descriptor_ref=descriptor_ref,
                ability_ura="",
            )
        draft = self._connected().build_target_invocation(request)

        def dispatch(prepared: PreparedInvocation) -> Invocation:
            if prepared.sign:
                return self._dispatch_signed(prepared, timeout=target.timeout)
            return self._dispatch(prepared, timeout=target.timeout)

        return PreparedInvocation(
            draft=draft,
            sign=target.sign,
            call_carrier=resolved.call_carrier,
            dispatcher=dispatch,
        )

    @staticmethod
    def target(
        function: str,
        /,
        *,
        node: str | None = None,
        pick: Literal["round_robin", "random"] | None = None,
        timeout: float | None = None,
        sign: bool | None = None,
        metadata: Mapping[str, str] | None = None,
        owner_ura: str | None = None,
        invocation_policy: InvocationDerivationPolicy | None = None,
    ) -> CallTarget:
        """Build a collision-free target for one client call.

        Prefer the ``client.device/agent/hub`` handles over a raw
        ``owner_ura`` — they build and validate the owner URA for you.
        """
        return CallTarget(
            function=function,
            node=node,
            pick=pick,
            timeout=timeout,
            sign=sign,
            metadata=metadata,
            owner_ura=owner_ura,
            invocation_policy=invocation_policy,
        )

    # -- owner handles ---------------------------------------------------------

    def device(self, device_id: str) -> RemoteOwner:
        """A handle to a device's abilities (``@handle.remote`` / ``.call``).

        ``device_id`` is a node id in this client's realm, or a full device
        owner URA (a cross-realm URA only routes where federation is
        configured). Symmetric to ``ComputeNode`` on the serving side.
        """
        return RemoteOwner(self, self._owner_ura(device_id, "device"))

    def agent(self, spec: str) -> RemoteAgent:
        """A handle to an agent's abilities.

        ``spec`` is an agent id local to the paired user, a
        ``<user-id>.<agent-id>`` owner token, or a full agent owner URA.
        """
        from .agent import RemoteAgent

        normalized = str(spec).strip()
        if not normalized:
            raise InvalidArgument(
                "agent spec must not be empty",
                reason="invalid_agent_spec",
            )
        owner_spec = normalized
        resolve_owner = (
            not self._addressing.is_owner_ura(normalized) and "." not in normalized
        )
        if resolve_owner:
            username = (self._who().username or "").strip()
            if not username:
                raise InvalidArgument(
                    "a bare agent id requires a paired user identity",
                    reason="missing_agent_owner",
                )
            owner_spec = f"{username}.{normalized}"
        owner_ura = self._owner_ura(owner_spec, "agent")
        projection = easynet_sdk.parse_ura(owner_ura)
        agent_name = str(projection.components.get("agent_id") or "").strip()
        if not agent_name:
            raise InvalidArgument(
                f"agent owner URA has no agent id: {owner_ura}",
                reason="invalid_agent_spec",
            )
        return RemoteAgent(self, owner_ura, agent_name, resolve_owner=resolve_owner)

    def _agent_call_owner_ura(self, agent_id: str, fallback_owner_ura: str) -> str:
        """Resolve a bare agent id to the daemon catalogue's canonical owner."""
        owner_ura = self._cached_agent_owner_ura(agent_id)
        if owner_ura:
            return owner_ura
        self._preflight_agent_catalogue()
        return self._cached_agent_owner_ura(agent_id) or fallback_owner_ura

    def _cached_agent_owner_ura(self, agent_id: str) -> str:
        owners = self._addressing.cache.agent_owner_uras(agent_id)
        if not owners:
            return ""
        if len(owners) == 1:
            return owners[0]
        username = (self._who().username or "").strip()
        if username:
            preferred = [
                owner_ura
                for owner_ura in owners
                if _agent_owner_user_id(owner_ura) == username
            ]
            if len(preferred) == 1:
                return preferred[0]
        raise InvalidArgument(
            f"agent id {agent_id!r} is ambiguous in the daemon catalogue; use"
            " a <user-id>.<agent-id> token or a full agent owner URA",
            reason="ambiguous_agent_owner",
        )

    def _preflight_agent_catalogue(self) -> None:
        local = self._who().device_ura
        try:
            rows = self._connected().list_ability_descriptors(
                runtime_root_context(
                    caller_ura=local,
                    callee_ura=local,
                    subject_ura=local,
                ),
                scope="realm",
            )
        except (RemoteError, easynet_sdk.SDKError):
            return
        if not isinstance(rows, list) or not all(
            isinstance(row, Mapping) for row in rows
        ):
            return
        self._addressing.cache.remember_catalog_rows(
            row for row in rows if isinstance(row, Mapping)
        )

    def hub(self) -> RemoteOwner:
        """A handle to the realm hub's abilities."""
        return RemoteOwner(self, hub_ura(self._who().realm))

    def _owner_ura(self, spec: str, kind: Literal["device", "agent"]) -> str:
        if self._addressing.is_owner_ura(spec):
            actual = self._addressing.owner_kind(spec)
            if actual != kind:
                raise InvalidArgument(
                    f"expected a {kind} owner URA, got {actual}: {spec}",
                    reason="invalid_owner_kind",
                )
            return spec
        realm = self._who().realm
        return device_ura(realm, spec) if kind == "device" else agent_ura(realm, spec)

    # -- discovery -------------------------------------------------------------

    def functions(self, query: str = "", scope: str = "device") -> list[FunctionInfo]:
        """Discoverable capabilities from the canonical daemon catalogue."""
        catalogue_scope = _catalogue_scope(scope)
        local = self._who().device_ura
        rows = self._connected().list_ability_descriptors(
            runtime_root_context(
                caller_ura=local,
                callee_ura=local,
                subject_ura=local,
            ),
            scope=catalogue_scope if catalogue_scope == "realm" else "",
        )
        if not isinstance(rows, list) or not all(
            isinstance(row, Mapping) for row in rows
        ):
            raise InvalidArgument(
                "meta.list_abilities response field 'abilities' is not an object array",
                reason="invalid_daemon_response",
            )
        infos = [
            FunctionInfo.from_catalog_row(row, namespace=self._namespace)
            for row in rows
            if _catalogue_row_matches(row, query)
        ]
        self._addressing.cache.replace(infos)
        return infos

    # -- async mirror -------------------------------------------------------------

    @property
    def aio(self) -> AsyncClient:
        return AsyncClient(self)

    @property
    def invocation_policy(self) -> InvocationDerivationPolicy | None:
        """The explicitly configured client policy, if one was supplied."""
        return self._invocation_policy

    @property
    def abilities(self) -> AbilityControl:
        """Daemon ability install/catalogue operations for this client."""
        from .control import AbilityControl

        return AbilityControl(self)

    @property
    def agents(self) -> AgentControl:
        """Daemon-owned agent lifecycle operations for this client."""
        from .control import AgentControl

        return AgentControl(self)

    @property
    def missions(self) -> MissionControl:
        """Daemon Mission/EAL execution operations for this client."""
        from .mission import MissionControl

        return MissionControl(self)

    def close(self) -> None:
        try:
            self._unary_pool.close()
        finally:
            self._addressing.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- internals ---------------------------------------------------------------

    def _dispatch(
        self, prepared: PreparedInvocation, timeout: float | None = None
    ) -> Invocation:
        budget = timeout if timeout is not None else self._timeout
        response = self._unary_pool.invoke(prepared.draft, timeout=budget)
        return Invocation.from_transport_response(response)

    def _dispatch_signed(
        self, prepared: PreparedInvocation, timeout: float | None = None
    ) -> Invocation:
        budget = timeout if timeout is not None else self._timeout
        response = self._unary_pool.invoke_signed(
            prepared.draft,
            signer=self._signer,
            timeout=budget,
        )
        return Invocation.from_transport_response(response)

    def _address(
        self,
        function: str,
        node: str | None,
        pick: str | None = None,
        owner_ura: str | None = None,
    ) -> ResolvedAbility:
        """Resolve product target selection into one SDK-owned Ability URA."""
        return self._addressing.resolve(
            function,
            identity=self._who(),
            node=node,
            pick=pick,
            owner_ura=owner_ura,
        )

    def _named_arguments(
        self, target: ResolvedAbility, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Map positionals onto names and fill advertised defaults."""
        schema = target.input_schema
        order: list[str] | None = schema.get(PARAMETER_ORDER_KEY) if schema else None
        payload = dict(kwargs)
        argument_label = target.argument_label or target.ability_ura
        if args:
            if order is None:
                raise InvalidArgument(
                    f"positional arguments for '{argument_label}' need its parameter"
                    " order — call functions() first to load the schema, use"
                    " keyword arguments, or call through a @remote stub",
                    reason="parameter_order_unknown",
                )
            var_positional = schema.get(VAR_POSITIONAL_KEY) if schema else None
            if var_positional in order:
                fixed_order = order[: order.index(var_positional)]
                if var_positional in payload:
                    message = (
                        f"argument '{var_positional}' given positionally and by keyword"
                    )
                    raise InvalidArgument(
                        message,
                        reason="duplicate_argument",
                    )
                positional_head = args[: len(fixed_order)]
                positional_tail = args[len(fixed_order) :]
                for name, value in zip(fixed_order, positional_head, strict=False):
                    if name in payload:
                        raise InvalidArgument(
                            f"argument '{name}' given positionally and by keyword",
                            reason="duplicate_argument",
                        )
                    payload[name] = value
                if positional_tail:
                    payload[var_positional] = list(positional_tail)
            elif len(args) > len(order):
                raise InvalidArgument(
                    f"'{argument_label}' takes at most {len(order)} arguments,"
                    f" got {len(args)}",
                    reason="too_many_arguments",
                )
            else:
                for name, value in zip(order, args, strict=False):
                    if name in payload:
                        raise InvalidArgument(
                            f"argument '{name}' given positionally and by keyword",
                            reason="duplicate_argument",
                        )
                    payload[name] = value
        if schema:
            for name, prop in schema.get("properties", {}).items():
                if name not in payload and "default" in prop:
                    payload[name] = prop["default"]
        return cast("dict[str, Any]", _codec.to_jsonable(payload))

    @staticmethod
    def _target(function: str | CallTarget) -> CallTarget:
        if isinstance(function, CallTarget):
            return function
        return CallTarget(function=function)

    def _who(self) -> LocalIdentity:
        if self._identity_override is not None:
            return self._identity_override
        with self._lock:
            if self._identity is None:
                self._identity = LocalIdentity.load()
                self._check_gateway(self._identity)
            return self._identity

    def _check_gateway(self, identity: LocalIdentity) -> None:
        """Classic FaaS shape: Client("hub:8443"). Transport truth lives
        with the paired daemon; a mismatch warns instead of re-routing."""
        if self._gateway is None or self._gateway_checked:
            return
        self._gateway_checked = True
        paired = identity.hub_endpoint
        if paired and self._gateway.split("://")[-1] not in paired:
            import warnings

            warnings.warn(
                f"Client(gateway={self._gateway!r}) differs from the paired hub"
                f" ({paired}) — the daemon routes via pairing; re-point it with"
                " `easynet pair`",
                UserWarning,
                stacklevel=4,
            )

    def _connected(self) -> Transport:
        return self._unary_pool.connected_transport()

    def _invocation_trace(self, request_id: str) -> easynet_sdk.InvocationTraceGraph:
        local = self._who().device_ura
        return self._connected().invocation_trace(
            runtime_root_context(
                caller_ura=local,
                callee_ura=local,
                subject_ura=local,
            ),
            request_id=request_id,
        )

    def _runtime_descriptor_ref(
        self,
        resolved: ResolvedAbility,
        *,
        call_mode: str,
    ) -> str:
        """Resolve one catalog descriptor_ref for an uncached ability."""

        local = self._who().device_ura
        try:
            row = self._connected().get_ability_descriptor(
                runtime_root_context(
                    caller_ura=local,
                    callee_ura=local,
                    subject_ura=local,
                ),
                ability_ura=resolved.ability_ura,
                call_mode=call_mode,
            )
        except RemoteError:
            return ""
        descriptor_ref = str(row.get("descriptor_ref") or "")
        if not descriptor_ref:
            return ""
        schema = row.get("input_schema")
        self._addressing.cache.remember_descriptor(
            resolved.ability_ura,
            descriptor_ref,
            dict(schema) if isinstance(schema, Mapping) else None,
        )
        return descriptor_ref

    @property
    def _transport(self) -> Transport | None:
        return self._unary_pool.current_transport


def _sdk_call_mode(carrier: str) -> str:
    if carrier == "stream":
        return "stream"
    if carrier == "unary":
        return "rpc"
    raise InvalidArgument(
        f"unsupported dispatch carrier {carrier!r}",
        reason="invalid_dispatch_carrier",
    )


def _catalogue_scope(scope: str) -> str:
    normalized = scope.strip().lower()
    if normalized in {"device", "self", "local"}:
        return "local"
    if normalized in {"user", "realm"}:
        return "realm"
    raise InvalidArgument(
        "functions scope must be one of 'device', 'self', 'local', 'user', or 'realm'",
        reason="invalid_discovery_scope",
    )


def _catalogue_row_matches(row: Mapping[str, Any], query: str) -> bool:
    needle = query.strip().lower()
    if not needle:
        return True
    haystack = " ".join(
        str(row.get(field) or "")
        for field in ("name", "ability", "ability_ura", "description", "owner_ura")
    ).lower()
    return needle in haystack


def _product_function_name(name: str, namespace: str) -> str:
    prefix = f"{namespace}."
    if namespace and name.startswith(prefix):
        return name[len(prefix) :]
    return name.rsplit(".", 1)[-1] if "." in name else name


def _agent_owner_user_id(owner_ura: str) -> str:
    try:
        projection = easynet_sdk.parse_ura(owner_ura)
    except easynet_sdk.SDKError:
        return ""
    if projection.kind != "agent":
        return ""
    return str((projection.components or {}).get("user_id") or "")


class AsyncClient:
    """Same surface, coroutine methods — a thin to-thread mirror.

    One dispatch implementation lives in :class:`Client`; this mirror
    must never grow logic of its own.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    async def execute(
        self, function: str | CallTarget, /, *args: Any, **kwargs: Any
    ) -> Any:
        return await self._to_thread(self._client.execute, function, *args, **kwargs)

    async def call(
        self, function: str | CallTarget, /, *args: Any, **kwargs: Any
    ) -> Any:
        return await self._to_thread(self._client.call, function, *args, **kwargs)

    async def stream(
        self, function: str | CallTarget, /, *args: Any, **kwargs: Any
    ) -> Stream:
        result = await self._to_thread(self._client.stream, function, *args, **kwargs)
        return cast(Stream, result)

    async def session(
        self,
        function: str | CallTarget,
        /,
        *,
        streams: list[StreamSpec] | None = None,
        **kwargs: Any,
    ) -> BidiSession:
        result = await self._to_thread(
            self._client.session,
            function,
            streams=streams,
            **kwargs,
        )
        return cast(BidiSession, result)

    async def invoke(
        self, function: str | CallTarget, /, *args: Any, **kwargs: Any
    ) -> Invocation:
        result = await self._to_thread(self._client.invoke, function, *args, **kwargs)
        return cast(Invocation, result)

    async def prepare(
        self, function: str | CallTarget, /, *args: Any, **kwargs: Any
    ) -> PreparedInvocation:
        result = await self._to_thread(self._client.prepare, function, *args, **kwargs)
        return cast(PreparedInvocation, result)

    async def functions(
        self, query: str = "", scope: str = "device"
    ) -> list[FunctionInfo]:
        result = await self._to_thread(self._client.functions, query, scope)
        return cast("list[FunctionInfo]", result)

    @staticmethod
    async def _to_thread(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        import asyncio

        return await asyncio.to_thread(fn, *args, **kwargs)


class RemoteFunction:
    """A typed stub for one remote capability — the ``@remote`` product.

    The decorated body never runs; its *signature* is the asset: it
    maps positionals to names and fills defaults locally, no discovery
    round-trip needed. Stubs represent EasyRemote-hosted host_stream
    abilities, so they expose result-first calls and live streams, not
    daemon unary ``invoke``.

    It is also a *descriptor* (the ``property`` playbook): declared on a
    class body, ``__set_name__`` adopts the attribute name as the ability
    name (no second naming), and ``__get__`` binds to the host instance —
    stripping ``self`` from the wire arguments and resolving the client
    from ``client=`` > ``instance.client`` > ``instance._client`` > a
    fresh ``Client()``. Used at module level (the original form),
    ``__get__`` never fires and behaviour is unchanged.
    """

    def __init__(
        self,
        fn: Callable[..., Any],
        *,
        name: str | None = None,
        node: str | None = None,
        timeout: float | None = None,
        client: Client | None = None,
        owner_ura: str | None = None,
        invocation_policy: InvocationDerivationPolicy | None = None,
    ) -> None:
        functools.update_wrapper(self, fn)
        self._signature = inspect.signature(fn)
        self._explicit_name = name
        self._name = name or fn.__name__
        self._node = node
        self._timeout = timeout
        self._target = CallTarget(
            self._name,
            node=node,
            timeout=timeout,
            owner_ura=owner_ura,
            invocation_policy=invocation_policy,
        )
        self._client = client
        self._bound: weakref.WeakKeyDictionary[Any, _BoundRemote] = (
            weakref.WeakKeyDictionary()
        )
        self._fallback_clients: weakref.WeakKeyDictionary[Any, Client] = (
            weakref.WeakKeyDictionary()
        )

    # -- descriptor protocol -----------------------------------------------------

    def __set_name__(self, owner: type, name: str) -> None:
        """Adopt the class-body attribute name when none was given.

        Only fires for a stub declared on a class; module-level stubs keep
        ``fn.__name__``. An explicit ``name=`` always wins.
        """
        if self._explicit_name is None:
            self._name = name
            self._target = replace(self._target, function=name)

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        """Class access yields the descriptor; instance access binds it."""
        if obj is None:
            return self
        bound = self._bound.get(obj)
        if bound is None:
            bound = _BoundRemote(self, obj)
            self._bound[obj] = bound
        return bound

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        # EasyRemote abilities register stream-mode (host_stream), so the
        # result-first call drains the frame stream for a single value —
        # same as `Client.call`. (Use `.stream(...)` for live iteration of
        # a generator ability.)
        return self._bound_client().call(
            self._target,
            **self._bind(args, kwargs),
        )

    def invoke(self, *args: Any, **kwargs: Any) -> Invocation:
        raise Unavailable(
            "@remote stubs represent EasyRemote-hosted host_stream abilities;"
            " use the stub call for result-first dispatch or .stream(...) for"
            " live frames. Client.invoke remains reserved for daemon unary/system"
            " abilities.",
            reason="host_stream_invoke_not_supported",
        )

    def stream(self, *args: Any, **kwargs: Any) -> Stream:
        return self._bound_client().stream(
            self._target,
            **self._bind(args, kwargs),
        )

    async def aio(self, *args: Any, **kwargs: Any) -> Any:
        import asyncio

        return await asyncio.to_thread(self.__call__, *args, **kwargs)

    def _bind(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        *,
        instance: Any = _NO_VALUE,
    ) -> dict[str, Any]:
        # Bound (descriptor) calls pass the host instance so it binds to the
        # method's first parameter (`self`) and is then dropped — the wire
        # carries only business arguments, never the host object.
        skip: str | None = None
        if instance is not _NO_VALUE:
            params = iter(self._signature.parameters)
            skip = next(params, None)
            bound = self._signature.bind(instance, *args, **kwargs)
        else:
            bound = self._signature.bind(*args, **kwargs)
        bound.apply_defaults()
        # `signature.bind` nests a **kwargs param under its own name and a
        # *args param as a tuple. The wire shape is flat: **kwargs keys go
        # to the top level (the ability's open object), *args stays a list
        # under its parameter name (the host re-expands it). Normalise so a
        # @remote stub sends the same args as a direct client.call.
        out: dict[str, Any] = {}
        for name, param in self._signature.parameters.items():
            if name == skip or name not in bound.arguments:
                continue
            value = bound.arguments[name]
            if param.kind is inspect.Parameter.VAR_KEYWORD:
                out.update(value)  # flatten **kwargs to the top level
            elif param.kind is inspect.Parameter.VAR_POSITIONAL:
                out[name] = list(value)  # *args as a JSON array
            else:
                out[name] = value
        return out

    def _bound_client(self, instance: Any = None) -> Client:
        # Precedence: explicit client= > instance.client > instance._client
        # > a fresh Client(). The descriptor passes the host instance.
        if self._client is not None:
            return self._client
        if instance is not None:
            host = getattr(instance, "client", None) or getattr(
                instance, "_client", None
            )
            if isinstance(host, Client):
                return host
            # A descriptor with no client= and a host that exposes none gets a
            # per-host fallback — never cache it on the shared descriptor, or
            # one client-less host would poison every other host's dispatch.
            return self._fallback_client(instance)
        self._client = Client()
        return self._client

    def _fallback_client(self, instance: Any) -> Client:
        client = self._fallback_clients.get(instance)
        if client is None:
            client = Client()
            self._fallback_clients[instance] = client
        return client


class _BoundRemote:
    """A :class:`RemoteFunction` bound to its host instance.

    The descriptor's ``__get__`` returns this when the stub is accessed
    through an instance. It forwards ``__call__``/``stream``/``aio`` to the
    descriptor, threading the host instance so ``self`` is stripped from
    the wire arguments and the host's client is reused.
    """

    def __init__(self, fn: RemoteFunction, instance: Any) -> None:
        self._fn = fn
        self._instance = instance

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._fn._bound_client(self._instance).call(
            self._fn._target,
            **self._fn._bind(args, kwargs, instance=self._instance),
        )

    def stream(self, *args: Any, **kwargs: Any) -> Stream:
        return self._fn._bound_client(self._instance).stream(
            self._fn._target,
            **self._fn._bind(args, kwargs, instance=self._instance),
        )

    async def aio(self, *args: Any, **kwargs: Any) -> Any:
        import asyncio

        return await asyncio.to_thread(self.__call__, *args, **kwargs)

    def invoke(self, *args: Any, **kwargs: Any) -> Invocation:
        return self._fn.invoke(*args, **kwargs)


def remote(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    node: str | None = None,
    timeout: float | None = None,
    client: Client | None = None,
    owner_ura: str | None = None,
    invocation_policy: InvocationDerivationPolicy | None = None,
) -> Any:
    """Declare a typed stub for a remote capability (both decorator forms).

    ``owner_ura`` targets a specific ability owner (set by
    ``RemoteOwner.remote`` / ``client.agent(...).remote`` etc.); left unset
    the stub addresses the local device. Multi-candidate selection
    (``pick`` policies) is deliberately not here yet: choosing among owners
    requires deriving a callee from a candidate's ability URA, and that
    owner-resolution contract is pinned by P0 (resource-aware additionally
    needs Cli PR-3 load data). One policy seam will land with verified
    facts, not before.
    """
    if fn is None:
        return functools.partial(
            remote,
            name=name,
            node=node,
            timeout=timeout,
            client=client,
            owner_ura=owner_ura,
            invocation_policy=invocation_policy,
        )
    return RemoteFunction(
        fn,
        name=name,
        node=node,
        timeout=timeout,
        client=client,
        owner_ura=owner_ura,
        invocation_policy=invocation_policy,
    )


class RemoteAbility:
    """Invocation-only handle to one named ability on an owner.

    Lifecycle remains owned by the canonical runtime control plane. This
    facade only makes the common cross-product call shape explicit:
    ``client.device("node").ability("nativeer.echo").call(...)``.
    """

    def __init__(self, owner: RemoteOwner, function: str) -> None:
        function = str(function).strip()
        if not function:
            raise InvalidArgument(
                "ability name must be non-empty",
                reason="invalid_ability_name",
            )
        self._owner = owner
        self._function = function

    @property
    def name(self) -> str:
        return self._function

    @property
    def owner_ura(self) -> str:
        return self._owner.owner_ura

    def call(self, *args: Any, **kwargs: Any) -> Any:
        return self._owner.call(self._function, *args, **kwargs)

    def stream(self, *args: Any, **kwargs: Any) -> Stream:
        return self._owner.stream(self._function, *args, **kwargs)

    def remote(
        self,
        fn: Callable[..., Any] | None = None,
        *,
        name: str | None = None,
        timeout: float | None = None,
        invocation_policy: InvocationDerivationPolicy | None = None,
    ) -> Any:
        """Declare a typed stub bound to this ability handle."""
        return self._owner.remote(
            fn,
            name=name or self._function,
            timeout=timeout,
            invocation_policy=invocation_policy,
        )


class RemoteOwner:
    """A handle to one ability owner — the client-side mirror of ``ComputeNode``.

    ``client.device(id)`` / ``client.agent(spec)`` / ``client.hub()`` return
    these. ``@handle.remote`` declares a typed stub bound to this owner (the
    symmetric counterpart of ``@node.register`` on the serving side), and
    ``call`` / ``stream`` dispatch ad-hoc without a stub. The owner identity
    lives on the handle, so it never clutters the call site.
    """

    def __init__(self, client: Client, owner_ura: str) -> None:
        self._client = client
        self._owner_ura = owner_ura

    @property
    def owner_ura(self) -> str:
        return self._owner_ura

    def ability(self, function: str) -> RemoteAbility:
        """Return an invocation-only handle to one ability on this owner.

        Fully-qualified names are preserved. Bare names still flow through
        the client's default namespace during canonical URA projection.
        """
        return RemoteAbility(self, function)

    def remote(
        self,
        fn: Callable[..., Any] | None = None,
        *,
        name: str | None = None,
        timeout: float | None = None,
        invocation_policy: InvocationDerivationPolicy | None = None,
    ) -> Any:
        """Declare a stub bound to this owner (bare or parameterised form)."""
        return remote(
            fn,
            name=name,
            timeout=timeout,
            client=self._client,
            owner_ura=self._owner_ura,
            invocation_policy=invocation_policy,
        )

    def call(self, function: str, /, *args: Any, **kwargs: Any) -> Any:
        return self._client.call(
            self._target(function),
            *args,
            **kwargs,
        )

    def stream(self, function: str, /, *args: Any, **kwargs: Any) -> Stream:
        return self._client.stream(
            self._target(function),
            *args,
            **kwargs,
        )

    def _target(self, function: str) -> CallTarget:
        return CallTarget(function=function, owner_ura=self._owner_ura)
