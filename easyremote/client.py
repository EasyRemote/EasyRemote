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
otherwise. Ability URAs from `discover` are used verbatim, never
reconstructed.

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
import queue
import random
import threading
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from . import _codec
from ._transport import BidiChannel, FrameStream, Transport
from .errors import DeadlineExceeded, InvalidArgument, Unavailable, error_from_wire
from .identity import LocalIdentity, device_ura
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
    "Stream",
    "remote",
]

_PICK_POLICIES = frozenset({"round_robin", "random"})


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
class _ResolvedAbility:
    """One concrete invocation target plus the schema that belongs to it.

    Schemas are only safe to apply after owner selection. Two devices can
    expose the same verb with different parameter order/defaults, so a
    bare verb cache is only used when discovery proved it unambiguous.
    """

    callee: str
    ability: str
    input_schema: dict[str, Any] | None = None
    ability_ura: str | None = None
    subject: str | None = None
    argument_label: str | None = None


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
        if self.pick is not None and self.pick not in _PICK_POLICIES:
            raise InvalidArgument(
                f"pick must be one of {sorted(_PICK_POLICIES)}, got {self.pick!r}"
                " (resource_aware needs daemon-side load metrics — Cli PR-3)",
                reason="invalid_pick_policy",
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
        if (
            "payload_json" in frame
            and (
                frame.get("payload_json") is not None
                or frame.get("content_type") == JSON_CONTENT_TYPE
            )
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


def _is_ability_ura(value: str) -> bool:
    """True when `value` should be handed to the daemon as an Ability URA.

    This deliberately only recognises the scheme. Python must not parse
    owner/callee/ability facts out of the URA; the CLI/Axon
    AbilitySelector boundary is the canonical parser.
    """
    return value.strip().startswith("easynet://")


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
        self._timeout = timeout
        self._namespace = namespace
        self._transport_override = transport
        self._identity_override = identity
        self._lock = threading.Lock()
        self._invoke_lock = threading.Lock()
        self._transport: Transport | None = None
        self._retired_transports: set[Transport] = set()
        self._identity: LocalIdentity | None = None
        self._schemas: dict[str, dict[str, Any]] = {}  # unambiguous verb → schema
        self._schemas_by_ura: dict[str, dict[str, Any]] = {}
        self._candidates: dict[str, list[FunctionInfo]] = {}  # verb → discover hits
        self._round_robin: dict[str, int] = {}

    # -- L0 ------------------------------------------------------------------

    def execute(
        self, function: str | CallTarget, /, *args: Any, **kwargs: Any
    ) -> Any:
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
        if self._uses_ability_ura_dispatch(prepared):
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
        if self._uses_ability_ura_dispatch(prepared):
            raise Unavailable(
                "streaming by canonical Ability URA needs a CLI/Axon"
                " ability_ura stream surface; Python facade will not parse"
                " the URA or synthesize callee/ability",
                reason="ability_ura_stream_surface_missing",
            )
        return self._open_stream(prepared, timeout=target.timeout)

    def _open_stream(
        self, prepared: PreparedInvocation, *, timeout: float | None
    ) -> Stream:
        wait_budget = self._timeout if timeout is None else timeout
        wire = encode_invocation(prepared.tuple, metadata=prepared.metadata)
        return Stream(self._connected().stream(wire), timeout=wait_budget)

    @staticmethod
    def _uses_ability_ura_dispatch(prepared: PreparedInvocation) -> bool:
        args = prepared.tuple.arguments.json_value
        return (
            prepared.tuple.ability.endswith(".invoke")
            and isinstance(args, dict)
            and isinstance(args.get("ability_ura"), str)
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
        if _is_ability_ura(target.function):
            raise Unavailable(
                "bidi sessions by canonical Ability URA need a CLI/Axon"
                " ability_ura bidi surface; Python facade will not parse"
                " the URA or synthesize callee/ability",
                reason="ability_ura_bidi_surface_missing",
            )
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
        resolved = self._address(target.function, target.node, target.pick)
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
    ) -> CallTarget:
        """Build a collision-free target for one client call."""
        return CallTarget(
            function=function,
            node=node,
            pick=pick,
            timeout=timeout,
            subject=subject,
            causal=causal,
            sign=sign,
            metadata=metadata,
        )

    # -- discovery -------------------------------------------------------------

    def functions(self, query: str = "", scope: str = "device") -> list[FunctionInfo]:
        """Discoverable capabilities, via the daemon's `discover` ability."""
        response = self.invoke(
            f"{self._namespace}.discover", scope=scope, query=query
        ).result()
        candidates = (response or {}).get("candidates", [])
        infos = [FunctionInfo.from_candidate(c) for c in candidates]
        self._candidates.clear()
        self._schemas.clear()
        self._schemas_by_ura.clear()
        for info in infos:
            if info.name:
                self._candidates.setdefault(info.name, []).append(info)
            if info.qualified_name and info.input_schema:
                self._schemas_by_ura[info.qualified_name] = info.input_schema
        for verb, group in self._candidates.items():
            schemas = [info.input_schema for info in group]
            if (
                schemas
                and all(schema for schema in schemas)
                and all(schema == schemas[0] for schema in schemas)
            ):
                self._schemas[verb] = schemas[0]
        return infos

    # -- async mirror -------------------------------------------------------------

    @property
    def aio(self) -> AsyncClient:
        return AsyncClient(self)

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
        result: queue.Queue[tuple[bool, dict[str, Any] | BaseException]] = (
            queue.Queue(maxsize=1)
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
        self, function: str, node: str | None, pick: str | None = None
    ) -> _ResolvedAbility:
        """(callee URA, qualified ability name) for a function reference.

        Short names get this client's namespace; dotted names pass
        through. Canonical Ability URAs are never parsed here: they are
        wrapped for the daemon's ``<self>.invoke`` ability, whose CLI
        boundary owns AbilitySelector parsing and routing.
        """
        identity = self._who()
        if _is_ability_ura(function):
            if node is not None or pick is not None:
                raise InvalidArgument(
                    "a canonical Ability URA already names the callable;"
                    " do not combine it with node or pick",
                    reason="target_override_for_ability_ura",
                )
            return _ResolvedAbility(
                callee=identity.device_ura,
                ability=f"{self._namespace}.invoke",
                input_schema=self._schemas_by_ura.get(function),
                ability_ura=function,
                subject=function,
                argument_label=function,
            )
        ability = function if "." in function else f"{self._namespace}.{function}"
        verb = ability.rsplit(".", 1)[-1]
        if node is not None:
            callee = device_ura(identity.realm, node)
            return _ResolvedAbility(
                callee=callee,
                ability=ability,
                input_schema=self._schemas.get(verb),
                argument_label=ability,
            )
        if pick is not None:
            selected = self._pick(verb, pick)
            if selected is not None:
                return selected
        route = (identity.device_ura, ability)
        return _ResolvedAbility(
            callee=route[0],
            ability=route[1],
            input_schema=self._schemas.get(verb),
            argument_label=ability,
        )

    def _pick(self, verb: str, policy: str) -> _ResolvedAbility | None:
        """Select among discovered Ability URA candidates for ``verb``.

        The client chooses only a discovered Ability URA. It never
        derives callee/ability from that URA; ``<self>.invoke`` hands
        it to the daemon/CLI AbilitySelector boundary. With no usable
        candidates the default local addressing applies; call
        functions() first to populate the candidate cache.
        """
        if policy not in _PICK_POLICIES:
            raise InvalidArgument(
                f"pick must be one of {sorted(_PICK_POLICIES)}, got {policy!r}"
                " (resource_aware needs daemon-side load metrics — Cli PR-3)",
                reason="invalid_pick_policy",
            )
        candidates = [
            _ResolvedAbility(
                callee=self._who().device_ura,
                ability=f"{self._namespace}.invoke",
                input_schema=info.input_schema
                or self._schemas_by_ura.get(info.qualified_name),
                ability_ura=info.qualified_name,
                subject=info.qualified_name,
                argument_label=info.qualified_name,
            )
            for info in self._candidates.get(verb, [])
            if info.qualified_name
        ]
        if not candidates:
            return None
        if policy == "random":
            return random.choice(candidates)
        index = self._round_robin.get(verb, 0)
        self._round_robin[verb] = index + 1
        return candidates[index % len(candidates)]

    def _named_arguments(
        self, target: _ResolvedAbility, args: tuple[Any, ...], kwargs: dict[str, Any]
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
        if target.ability_ura is not None:
            payload = {"ability_ura": target.ability_ura, "args": payload}
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
    """

    def __init__(
        self,
        fn: Callable[..., Any],
        *,
        name: str | None = None,
        node: str | None = None,
        timeout: float | None = None,
        client: Client | None = None,
    ) -> None:
        functools.update_wrapper(self, fn)
        self._signature = inspect.signature(fn)
        self._name = name or fn.__name__
        self._target = CallTarget(self._name, node=node, timeout=timeout)
        self._client = client

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

    def _bind(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
        bound = self._signature.bind(*args, **kwargs)
        bound.apply_defaults()
        # `signature.bind` nests a **kwargs param under its own name and a
        # *args param as a tuple. The wire shape is flat: **kwargs keys go
        # to the top level (the ability's open object), *args stays a list
        # under its parameter name (the host re-expands it). Normalise so a
        # @remote stub sends the same args as a direct client.call.
        out: dict[str, Any] = {}
        for name, param in self._signature.parameters.items():
            if name not in bound.arguments:
                continue
            value = bound.arguments[name]
            if param.kind is inspect.Parameter.VAR_KEYWORD:
                out.update(value)  # flatten **kwargs to the top level
            elif param.kind is inspect.Parameter.VAR_POSITIONAL:
                out[name] = list(value)  # *args as a JSON array
            else:
                out[name] = value
        return out

    def _bound_client(self) -> Client:
        if self._client is None:
            self._client = Client()
        return self._client


def remote(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    node: str | None = None,
    timeout: float | None = None,
    client: Client | None = None,
) -> Any:
    """Declare a typed stub for a remote capability (both decorator forms).

    Multi-candidate selection (``pick`` policies) is deliberately not
    here yet: choosing among owners requires deriving a callee from a
    candidate's ability URA, and that owner-resolution contract is
    pinned by P0 (resource-aware additionally needs Cli PR-3 load
    data). One policy seam will land with verified facts, not before.
    """
    if fn is None:
        return functools.partial(
            remote, name=name, node=node, timeout=timeout, client=client
        )
    return RemoteFunction(fn, name=name, node=node, timeout=timeout, client=client)
