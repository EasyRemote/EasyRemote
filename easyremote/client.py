"""Client: call capabilities (SPEC §5.6).

Three layers, one dispatch path:

- L0 ``execute`` — v2 hello-world surface, keyword-or-discovered args.
- L1 ``call`` / ``stream`` / ``session`` — targeting and streams.
- L2 ``invoke`` / ``prepare`` — the full invocation object, with the
  seven-tuple inspectable before and after dispatch.

Addressing: the caller is this device (pairing identity); the callee
defaults to the local daemon's device URA, which owns routing — one
``_address()`` seam encodes that assumption so the P0 link
verification adjusts exactly one place if the dispatch contract says
otherwise. Ability URAs from `discover` are used verbatim, never
reconstructed.

Per-call timeouts are client-side only (the C ABI invoke is a
blocking call with no wire-level timeout field): the wait is bounded,
the server-side execution is governed by the manifest's
``timeout_seconds``.
"""

from __future__ import annotations

import functools
import inspect
import threading
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, cast

from ._transport import BidiChannel, FrameStream, Transport
from .errors import DeadlineExceeded, InvalidArgument, Unavailable
from .identity import LocalIdentity
from .invocation import (
    Arguments,
    Causal,
    Invocation,
    InvocationTuple,
    PreparedInvocation,
    StreamSpec,
    encode_invocation,
    fresh_nonce,
)
from .schema import PARAMETER_ORDER_KEY

__all__ = [
    "BidiSession",
    "Client",
    "FunctionInfo",
    "RemoteFunction",
    "Stream",
    "remote",
]


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


class Stream:
    """Frames from a server-stream invocation.

    Yields raw frame dicts; which frame is terminal — and how results
    embed in frames — is pinned by P0 against a live daemon. Until
    then the stream ends when the daemon closes or ``close()`` runs.
    """

    def __init__(self, frames: FrameStream) -> None:
        self._frames = frames

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._frames)

    def close(self) -> None:
        self._frames.close()

    def __enter__(self) -> Stream:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


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
        *,
        timeout: float = 30.0,
        namespace: str = "er",
        transport: Transport | None = None,
        identity: LocalIdentity | None = None,
    ) -> None:
        self._timeout = timeout
        self._namespace = namespace
        self._transport_override = transport
        self._identity_override = identity
        self._lock = threading.Lock()
        self._transport: Transport | None = None
        self._identity: LocalIdentity | None = None
        self._schemas: dict[str, dict[str, Any]] = {}  # ability name → input_schema
        self._round_robin: dict[str, int] = {}

    # -- L0 ------------------------------------------------------------------

    def execute(self, function: str, *args: Any, **kwargs: Any) -> Any:
        return self.call(function, *args, **kwargs)

    # -- L1 ------------------------------------------------------------------

    def call(
        self,
        function: str,
        /,
        *args: Any,
        node: str | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        return self.invoke(
            function, *args, node=node, timeout=timeout, **kwargs
        ).result()

    def stream(self, function: str, /, *args: Any, **kwargs: Any) -> Stream:
        node = kwargs.pop("node", None)
        prepared = self.prepare(function, *args, node=node, **kwargs)
        wire = encode_invocation(prepared.tuple, metadata=prepared.metadata)
        return Stream(self._connected().stream(wire))

    def session(
        self,
        function: str,
        /,
        *,
        streams: list[StreamSpec] | None = None,
        node: str | None = None,
        **kwargs: Any,
    ) -> BidiSession:
        prepared = self.prepare(function, node=node, **kwargs)
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
        function: str,
        /,
        *args: Any,
        subject: str | None = None,
        causal: Causal = None,
        sign: bool | None = None,
        metadata: Mapping[str, str] | None = None,
        node: str | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Invocation:
        prepared = self.prepare(
            function,
            *args,
            subject=subject,
            causal=causal,
            sign=sign,
            metadata=metadata,
            node=node,
            **kwargs,
        )
        return self._dispatch(prepared, timeout=timeout)

    def prepare(
        self,
        function: str,
        /,
        *args: Any,
        subject: str | None = None,
        causal: Causal = None,
        sign: bool | None = None,
        metadata: Mapping[str, str] | None = None,
        node: str | None = None,
        **kwargs: Any,
    ) -> PreparedInvocation:
        if sign:
            raise Unavailable(
                "caller signing needs the pairing key material contract, which"
                " is verified in P0 — local-fast admission (unsigned) is the"
                " only path wired today",
                reason="signing_path_pending",
            )
        callee, ability = self._address(function, node)
        payload = self._named_arguments(ability, args, kwargs)
        tuple_ = InvocationTuple(
            caller=self._who().device_ura,
            callee=callee,
            ability=ability,
            subject=subject if subject is not None else callee,
            nonce=fresh_nonce(),
            causal=causal,
            arguments=Arguments.from_json(payload),
        )
        return PreparedInvocation(
            tuple=tuple_, metadata=metadata, sign=sign, dispatcher=self._dispatch
        )

    # -- discovery -------------------------------------------------------------

    def functions(self, query: str = "", scope: str = "device") -> list[FunctionInfo]:
        """Discoverable capabilities, via the daemon's `discover` ability."""
        response = self.invoke(
            f"{self._namespace}.discover", scope=scope, query=query
        ).result()
        candidates = (response or {}).get("candidates", [])
        infos = [FunctionInfo.from_candidate(c) for c in candidates]
        for info in infos:
            if info.name and info.input_schema:
                self._schemas.setdefault(info.name, info.input_schema)
        return infos

    # -- async mirror -------------------------------------------------------------

    @property
    def aio(self) -> AsyncClient:
        return AsyncClient(self)

    def close(self) -> None:
        with self._lock:
            if self._transport is not None:
                self._transport.close()
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
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(transport.invoke, wire)
            try:
                response = future.result(timeout=budget)
            except FutureTimeoutError:
                raise DeadlineExceeded(
                    f"no response within {budget}s — the server-side execution"
                    " is still governed by the ability's timeout_seconds",
                    reason="client_wait_timeout",
                ) from None
        return Invocation(prepared.tuple, response)

    def _address(self, function: str, node: str | None) -> tuple[str, str]:
        """(callee URA, qualified ability name) for a function reference.

        Assumption pinned for P0: the daemon's invocation service
        resolves agent abilities by qualified name with the device as
        callee (AbilitySelector owns owner disambiguation). Bare names
        get this client's namespace; dotted names pass through.
        """
        identity = self._who()
        ability = function if "." in function else f"{self._namespace}.{function}"
        if node is None:
            return identity.device_ura, ability
        return f"easynet:///r/{identity.realm}/device/{node}", ability

    def _named_arguments(
        self, ability: str, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Map positionals onto names and fill advertised defaults."""
        schema = self._schemas.get(ability.rsplit(".", 1)[-1])
        order: list[str] | None = schema.get(PARAMETER_ORDER_KEY) if schema else None
        payload = dict(kwargs)
        if args:
            if order is None:
                raise InvalidArgument(
                    f"positional arguments for '{ability}' need its parameter"
                    " order — call functions() first to load the schema, use"
                    " keyword arguments, or call through a @remote stub",
                    reason="parameter_order_unknown",
                )
            if len(args) > len(order):
                raise InvalidArgument(
                    f"'{ability}' takes at most {len(order)} arguments,"
                    f" got {len(args)}",
                    reason="too_many_arguments",
                )
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
        return payload

    def _who(self) -> LocalIdentity:
        if self._identity_override is not None:
            return self._identity_override
        with self._lock:
            if self._identity is None:
                self._identity = LocalIdentity.load()
            return self._identity

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

    async def execute(self, function: str, *args: Any, **kwargs: Any) -> Any:
        return await self._to_thread(self._client.execute, function, *args, **kwargs)

    async def call(self, function: str, *args: Any, **kwargs: Any) -> Any:
        return await self._to_thread(self._client.call, function, *args, **kwargs)

    async def invoke(self, function: str, *args: Any, **kwargs: Any) -> Invocation:
        result = await self._to_thread(self._client.invoke, function, *args, **kwargs)
        return cast(Invocation, result)

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
    round-trip needed.
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
        self._node = node
        self._timeout = timeout
        self._client = client

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.invoke(*args, **kwargs).result()

    def invoke(self, *args: Any, **kwargs: Any) -> Invocation:
        return self._bound_client().invoke(
            self._name,
            node=self._node,
            timeout=self._timeout,
            **self._bind(args, kwargs),
        )

    def stream(self, *args: Any, **kwargs: Any) -> Stream:
        return self._bound_client().stream(
            self._name, node=self._node, **self._bind(args, kwargs)
        )

    async def aio(self, *args: Any, **kwargs: Any) -> Any:
        import asyncio

        return await asyncio.to_thread(self.__call__, *args, **kwargs)

    def _bind(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
        bound = self._signature.bind(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)

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
