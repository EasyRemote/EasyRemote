"""Client: call capabilities (SPEC §5.6).

Three layers, two daemon carriers:

- L0 ``execute`` — v2 hello-world surface, keyword-or-discovered args.
- L1 ``call`` / ``stream`` / ``session`` — hosted abilities on
  ``host_stream``; unary functions are single-frame streams.
- L2 ``invoke`` / ``prepare`` — daemon unary/system abilities, with
  the seven-tuple inspectable before dispatch.

Addressing: the caller is this device (pairing identity); the callee
defaults to the local daemon's device URA, which owns routing — one
``_address()`` seam encodes that assumption so the P0 link
verification adjusts exactly one place if the dispatch contract says
otherwise. Ability URAs from `discover` are projected into explicit
tuple fields with Axon's URA parser; daemon route policy still lives
behind libeasynet_cli.

Per-call timeouts are client-side only (the C ABI unary invoke is a
blocking call with no wire-level timeout field): the caller's wait is
bounded, while server-side execution remains governed by the manifest's
``timeout_seconds``. Timed-out unary calls may still finish in the
daemon; the client stops waiting.
"""

from __future__ import annotations

import base64
import contextlib
import functools
import inspect
import math
import queue
import threading
import weakref
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal, cast

from . import _codec, _sdk_identity
from ._addressing import (
    PICK_POLICIES,
    AbilityAddressResolver,
    ResolvedAbility,
    owner_kind,
)
from ._transport import BidiChannel, FrameStream, Transport
from .errors import (
    DeadlineExceeded,
    InvalidArgument,
    Unavailable,
    error_from_wire,
)
from .identity import LocalIdentity, agent_ura, device_ura, hub_ura
from .invocation import (
    JSON_CONTENT_TYPE,
    Arguments,
    Causal,
    Invocation,
    InvocationTuple,
    PreparedInvocation,
    StreamSpec,
    encode_invocation,
    fresh_nonce,
)
from .schema import PARAMETER_ORDER_KEY, VAR_POSITIONAL_KEY

__all__ = [
    "BidiSession",
    "CallTarget",
    "Client",
    "FunctionInfo",
    "RemoteFunction",
    "RemoteOwner",
    "Stream",
    "remote",
]

if TYPE_CHECKING:
    from .control import AbilityControl, AgentControl
    from .mission import MissionControl


@dataclass(frozen=True)
class FunctionInfo:
    """One discoverable capability (a `discover` candidate, verbatim)."""

    name: str  # verb, e.g. "ai_inference"
    qualified_name: str  # full ability URA, daemon-issued
    owner: str
    description: str
    input_schema: dict[str, Any]
    visibility: str
    score: float

    @classmethod
    def from_candidate(cls, candidate: dict[str, Any]) -> FunctionInfo:
        return cls(
            name=str(candidate.get("ability", "")),
            qualified_name=str(candidate.get("qualified_name", "")),
            owner=str(candidate.get("owner", "")),
            description=str(candidate.get("description", "")),
            input_schema=dict(candidate.get("input_schema") or {}),
            visibility=str(candidate.get("visibility", "")),
            score=float(candidate.get("score", 0.0)),
        )


@dataclass(frozen=True)
class CallTarget:
    """An invocation target plus client-side dispatch options.

    Ability arguments live only in ``Client.call/stream/invoke`` kwargs.
    Targeting, selection, timeout, metadata, and tuple adjustments live
    here so user functions may legitimately expose parameters named
    ``node``, ``pick``, ``timeout``, ``subject``, or ``metadata`` without
    colliding with the client control plane.
    """

    function: str
    node: str | None = None
    pick: Literal["round_robin", "random"] | None = None
    timeout: float | None = None
    subject: str | None = None
    causal: Causal = None
    sign: bool | None = None
    metadata: Mapping[str, str] | None = None
    owner_ura: str | None = None

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
                " (resource_aware needs daemon-side load metrics — Cli PR-3)",
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


class Stream:
    """Frames from a server-stream invocation.

    Yields each ability frame's decoded result value until the terminal
    frame arrives, then closes the underlying transport stream and stops
    iteration. Recognising the terminal frame is the stream consumer's
    job (the daemon keeps the carrier open after the last chunk), so this
    layer — not the raw frame queue — owns end-of-stream detection.

    A terminal frame with an error surfaces as :class:`RemoteError`; a
    clean terminal frame (the daemon's end-of-stream marker) simply ends
    iteration. Empty-payload terminal frames are not yielded.
    """

    def __init__(self, frames: FrameStream, *, timeout: float | None = None) -> None:
        self._frames = frames
        self._timeout = timeout

    def __iter__(self) -> Iterator[Any]:
        try:
            for frame in self._raw_frames():
                # Transport-level error on the chunk envelope.
                error = frame.get("error")
                if error:
                    raise error_from_wire(error)
                value = self._frame_value(frame)
                # Ability-level stream error: a generator that raised is
                # propagated by the warm host as a single `{"error": {...}}`
                # payload frame (host_stream wire), which the daemon relays
                # as the chunk's value rather than on the envelope. Detect
                # that exact shape and raise instead of yielding it as data.
                stream_err = _stream_error_payload(value)
                if stream_err is not None:
                    raise error_from_wire(stream_err)
                if value is not _NO_VALUE:
                    yield value
                if frame.get("terminal"):
                    return
        finally:
            self.close()

    def _raw_frames(self) -> Iterator[dict[str, Any]]:
        """Yield daemon chunk frames with an optional per-frame idle bound.

        A stream may be long-lived; the client timeout therefore limits
        how long the consumer waits for the next frame, not total stream
        lifetime. ``FrameStream`` provides ``recv(timeout=...)`` while
        simple tests may only implement iteration.
        """
        recv = getattr(self._frames, "recv", None)
        if not callable(recv):
            yield from self._frames
            return

        while True:
            try:
                frame = recv(timeout=self._timeout)
            except TimeoutError:
                raise DeadlineExceeded(
                    f"no stream frame within {self._timeout}s — the server-side"
                    " execution is still governed by the ability's timeout_seconds",
                    reason="client_wait_timeout",
                ) from None
            if frame is None:
                return
            yield frame

    @staticmethod
    def _frame_value(frame: dict[str, Any]) -> Any:
        """The ability's emitted value for one chunk frame.

        Prefers the daemon's decoded ``payload_json``; falls back to
        base64 payload bytes. A terminal frame that carries no payload
        (the bare end-of-stream marker) yields the sentinel so the
        consumer does not see a spurious ``None`` frame.
        """
        if (
            frame.get("terminal")
            and frame.get("payload_json") is None
            and not frame.get("payload_base64")
        ):
            return _NO_VALUE
        if "payload_json" in frame and (
            frame.get("payload_json") is not None
            or frame.get("content_type") == JSON_CONTENT_TYPE
        ):
            return frame["payload_json"]
        encoded = frame.get("payload_base64")
        if encoded:
            return base64.b64decode(encoded)
        return _NO_VALUE

    def close(self) -> None:
        self._frames.close()

    def __enter__(self) -> Stream:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


_NO_VALUE = object()  # sentinel: a frame carried no payload value
_DEFAULT_TIMEOUT = object()  # sentinel: use Client._timeout


def _stream_error_payload(value: Any) -> dict[str, Any] | None:
    """Return the wire error dict iff `value` is a host stream-error frame.

    The warm host emits a raised generator's failure as exactly
    ``{"error": {"kind", "reason", "message"}}`` (see
    ``_host.server._stream_error``). Matching that precise shape — a
    single ``error`` key whose value is a dict carrying a ``kind`` — keeps
    ordinary ability output that merely *contains* an ``error`` field from
    being mistaken for a stream failure.
    """
    if (
        isinstance(value, dict)
        and set(value) == {"error"}
        and isinstance(value["error"], dict)
        and "kind" in value["error"]
    ):
        return value["error"]
    return None


class BidiSession:
    """A bidirectional invocation session (context manager)."""

    def __init__(self, channel: BidiChannel) -> None:
        self._channel = channel

    def send(self, frame: dict[str, Any]) -> None:
        self._channel.send(frame)

    def recv(self, timeout: float | None = None) -> dict[str, Any] | None:
        return self._channel.recv(timeout=timeout)

    def close(self) -> None:
        self._channel.close()

    def cancel(self) -> None:
        self._channel.cancel()

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
    ) -> None:
        self._gateway = gateway
        self._gateway_checked = False
        if not math.isfinite(timeout) or timeout <= 0:
            raise InvalidArgument(
                f"timeout must be a positive finite number of seconds, got {timeout!r}",
                reason="invalid_timeout",
            )
        self._timeout = timeout
        self._namespace = namespace
        self._addressing = AbilityAddressResolver(namespace)
        self._transport_override = transport
        self._identity_override = identity
        self._lock = threading.Lock()
        self._invoke_lock = threading.Lock()
        self._transport: Transport | None = None
        self._retired_transports: set[Transport] = set()
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
        prepared = self.prepare(target, *args, **kwargs)
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
        prepared = self.prepare(target, *args, **kwargs)
        return self._open_stream(prepared, timeout=target.timeout)

    def _open_stream(
        self, prepared: PreparedInvocation, *, timeout: float | None
    ) -> Stream:
        wait_budget = self._timeout if timeout is None else timeout
        wire = encode_invocation(prepared.tuple, metadata=prepared.metadata)
        return Stream(self._connected().stream(wire), timeout=wait_budget)

    def session(
        self,
        function: str | CallTarget,
        /,
        *,
        streams: list[StreamSpec] | None = None,
        **kwargs: Any,
    ) -> BidiSession:
        target = self._target(function)
        prepared = self.prepare(target, **kwargs)
        wire = encode_invocation(
            prepared.tuple,
            metadata=prepared.metadata,
            bidi_streams=streams
            or [StreamSpec(stream_id=0, content_type="application/json")],
        )
        return BidiSession(self._connected().bidi(wire))

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
        target = self._target(function)
        if target.sign:
            raise Unavailable(
                "caller signing needs the pairing key material contract, which"
                " is verified in P0 — local-fast admission (unsigned) is the"
                " only path wired today",
                reason="signing_path_pending",
            )
        resolved = self._address(
            target.function, target.node, target.pick, target.owner_ura
        )
        payload = self._named_arguments(resolved, args, kwargs)
        tuple_ = InvocationTuple(
            caller=self._who().device_ura,
            callee=resolved.callee,
            ability=resolved.ability,
            subject=target.subject
            if target.subject is not None
            else (resolved.subject or resolved.callee),
            nonce=fresh_nonce(),
            causal=target.causal,
            arguments=Arguments.from_json(payload),
        )

        def dispatch(prepared: PreparedInvocation) -> Invocation:
            return self._dispatch(prepared, timeout=target.timeout)

        return PreparedInvocation(
            tuple=tuple_,
            metadata=target.metadata,
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
        subject: str | None = None,
        causal: Causal = None,
        sign: bool | None = None,
        metadata: Mapping[str, str] | None = None,
        owner_ura: str | None = None,
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
            subject=subject,
            causal=causal,
            sign=sign,
            metadata=metadata,
            owner_ura=owner_ura,
        )

    # -- owner handles ---------------------------------------------------------

    def device(self, device_id: str) -> RemoteOwner:
        """A handle to a device's abilities (``@handle.remote`` / ``.call``).

        ``device_id`` is a node id in this client's realm, or a full device
        owner URA (a cross-realm URA only routes where federation is
        configured). Symmetric to ``ComputeNode`` on the serving side.
        """
        return RemoteOwner(self, self._owner_ura(device_id, "device"))

    def agent(self, spec: str) -> RemoteOwner:
        """A handle to an agent's abilities.

        ``spec`` is the ``<user-id>.<agent-id>`` owner token in this
        client's realm, or a full agent owner URA. Agent callees are a
        first-class daemon route (hosted locally or on a same-realm device).
        """
        return RemoteOwner(self, self._owner_ura(spec, "agent"))

    def hub(self) -> RemoteOwner:
        """A handle to the realm hub's abilities."""
        return RemoteOwner(self, hub_ura(self._who().realm))

    def _owner_ura(self, spec: str, kind: Literal["device", "agent"]) -> str:
        if _sdk_identity.is_easynet_ura_text(spec):
            actual = owner_kind(spec)
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
        """Discoverable capabilities, via the daemon's `discover` ability."""
        response = self.invoke("discover", scope=scope, query=query).result()
        candidates = (response or {}).get("candidates", [])
        infos = [FunctionInfo.from_candidate(c) for c in candidates]
        self._addressing.cache.replace(infos)
        return infos

    # -- async mirror -------------------------------------------------------------

    @property
    def aio(self) -> AsyncClient:
        return AsyncClient(self)

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
        # Do not shutdown a libeasynet_cli handle while a timed-out unary
        # invoke is still running on its C stack. If a call is active, close
        # retires the handle from reuse and lets the worker close it after
        # the C call returns; the caller's close remains bounded.
        if self._transport_override is not None:
            return
        if self._invoke_lock.acquire(blocking=False):
            try:
                self._close_idle_transport()
            finally:
                self._invoke_lock.release()
            return
        self._retire_active_transport_for_close()

    def _close_idle_transport(self) -> None:
        with self._lock:
            transport = self._transport
            self._transport = None
        if transport is not None:
            transport.close()

    def _retire_active_transport_for_close(self) -> None:
        with self._lock:
            if self._transport is not None:
                self._retired_transports.add(self._transport)
                self._transport = None

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- internals ---------------------------------------------------------------

    def _dispatch(
        self, prepared: PreparedInvocation, timeout: float | None = None
    ) -> Invocation:
        wire = encode_invocation(prepared.tuple, metadata=prepared.metadata)
        budget = timeout if timeout is not None else self._timeout
        transport = self._connected()
        result: queue.Queue[tuple[bool, dict[str, Any] | BaseException]] = queue.Queue(
            maxsize=1
        )
        timed_out = threading.Event()

        def invoke_on_transport() -> None:
            try:
                with self._invoke_lock:
                    result.put((True, transport.invoke(wire)))
            except BaseException as exc:
                result.put((False, exc))
            finally:
                retired = self._take_retired_transport(transport)
                if self._transport_override is None and (timed_out.is_set() or retired):
                    with contextlib.suppress(BaseException):
                        transport.close()

        threading.Thread(
            target=invoke_on_transport,
            name="easyremote-unary-invoke",
            daemon=True,
        ).start()
        try:
            ok, payload = result.get(timeout=budget)
        except queue.Empty:
            timed_out.set()
            self._retire_timed_out_transport(transport)
            raise DeadlineExceeded(
                f"no response within {budget}s — the server-side execution"
                " is still governed by the ability's timeout_seconds",
                reason="client_wait_timeout",
            ) from None
        if not ok:
            assert isinstance(payload, BaseException)
            raise payload
        response = cast("dict[str, Any]", payload)
        return Invocation(prepared.tuple, response)

    def _retire_timed_out_transport(self, transport: Transport) -> None:
        """Remove a timed-out handle from the reuse pool without closing it.

        C ABI unary invoke has no cancellation hook. Closing the handle
        while the background thread is still inside ``invoke`` risks
        invalid-handle races, so the worker closes this retired handle only
        after the C call returns. The next invocation opens a fresh handle.
        """
        if self._transport_override is not None:
            return
        with self._lock:
            if self._transport is transport:
                self._transport = None
            self._retired_transports.add(transport)

    def _take_retired_transport(self, transport: Transport) -> bool:
        with self._lock:
            if transport not in self._retired_transports:
                return False
            self._retired_transports.remove(transport)
            return True

    def _address(
        self,
        function: str,
        node: str | None,
        pick: str | None = None,
        owner_ura: str | None = None,
    ) -> ResolvedAbility:
        """(callee URA, qualified ability name) for a function reference.

        Short names get this client's namespace; dotted names pass
        through. An explicit ``owner_ura`` (an owner handle) projects the
        function onto that owner instead of the local device. Canonical
        Ability URAs are projected through the Axon URA parser into
        explicit Invocation tuple fields; daemon route policy still lives
        behind libeasynet_cli.
        """
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
        argument_label = target.argument_label or target.ability
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
        if self._transport_override is not None:
            return self._transport_override
        with self._lock:
            if self._transport is None:
                self._transport = Transport.connect()
            return self._transport


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
            self._client.session, function, streams=streams, **kwargs
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
    ) -> None:
        functools.update_wrapper(self, fn)
        self._signature = inspect.signature(fn)
        self._explicit_name = name
        self._name = name or fn.__name__
        self._node = node
        self._timeout = timeout
        self._target = CallTarget(
            self._name, node=node, timeout=timeout, owner_ura=owner_ura
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
        return self._bound_client().stream(self._target, **self._bind(args, kwargs))

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
        )
    return RemoteFunction(
        fn, name=name, node=node, timeout=timeout, client=client, owner_ura=owner_ura
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

    def remote(
        self,
        fn: Callable[..., Any] | None = None,
        *,
        name: str | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Declare a stub bound to this owner (bare or parameterised form)."""
        return remote(
            fn,
            name=name,
            timeout=timeout,
            client=self._client,
            owner_ura=self._owner_ura,
        )

    def call(self, function: str, /, *args: Any, **kwargs: Any) -> Any:
        return self._client.call(self._target(function), *args, **kwargs)

    def stream(self, function: str, /, *args: Any, **kwargs: Any) -> Stream:
        return self._client.stream(self._target(function), *args, **kwargs)

    def _target(self, function: str) -> CallTarget:
        return CallTarget(function=function, owner_ura=self._owner_ura)
