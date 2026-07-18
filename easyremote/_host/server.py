"""The warm host: a Unix-socket server keeping registered functions resident.

Wire protocol (one JSON line in, many JSON lines out, UTF-8):

    -> {"request": {"fn": "<qualified>", "args": {...}, "caller": "..."}}
    <- {"stream_item": <json>, "seq": 0}
    <- {"terminal": {"output_hash": "sha256:<hex>", "frames": 1}}
    <- {"error": {"kind": "...", "reason": "...", "message": "..."}}

``args`` is the host_stream stdin payload verbatim — real JSON types,
so functions receive their keyword arguments without shell-template
re-typing. ``bytes`` parameters are the one schema-driven exception:
they travel as base64 strings (contentEncoding) and are decoded here.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import socket
import threading
import typing
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import easynet_sdk

from .. import _codec
from .._context_dispatch import dispatcher_from_parent_receipt
from .._json import dumps_wire
from ..context import Context, ContextChildDispatcher
from ..errors import InternalError, InvalidArgument, RemoteError
from ..receipts import receipt_from_mapping
from ..schema import PARAMETER_ORDER_KEY, VAR_POSITIONAL_KEY, DerivedSignature
from .protocol import HostFrame, HostRequest, HostSession

__all__ = ["HostServer", "HostedFunction"]

_MAX_UNIX_SOCKET_PATH_BYTES = 100
_HOST_DIR_MODE = 0o700
_HOST_SOCKET_MODE = 0o600


@dataclass(frozen=True)
class HostedFunction:
    """One resident function plus the type intent that rehydrates its args."""

    name: str
    fn: Callable[..., Any]
    signature: DerivedSignature
    _hints: dict[str, Any] = field(init=False, repr=False, compare=False)
    _inspect_signature: inspect.Signature = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        try:
            hints = typing.get_type_hints(self.fn)
        except Exception:  # unresolvable forward refs degrade to raw JSON
            hints = {}
        object.__setattr__(self, "_hints", hints)
        object.__setattr__(self, "_inspect_signature", inspect.signature(self.fn))

    def call(self, args: dict[str, Any], context: Any = None) -> Any:
        pos, kwargs = self._call_args(args, context)
        result = self.fn(*pos, **kwargs)
        if inspect.iscoroutine(result):
            result = asyncio.run(result)
        return _codec.to_jsonable(result)

    def stream(self, args: dict[str, Any], context: Any = None) -> Iterator[Any]:
        """Yield each frame of a generator ability, JSON-encoded.

        Sync and async generators are both supported; an async generator
        is drained on a private event loop so the per-frame contract is
        identical to the sync path. Argument errors surface the same way
        as :meth:`call` (before the first frame). When the function takes
        a Context, it is injected as the first positional argument.
        """
        pos, kwargs = self._call_args(args, context)
        gen = self.fn(*pos, **kwargs)
        if inspect.isasyncgen(gen):
            yield from _drain_async_gen(gen)
        else:
            for frame in gen:
                yield _codec.to_jsonable(frame)

    def _call_args(
        self, args: dict[str, Any], context: Any
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        kwargs = self._bind_kwargs(args)
        pos, kwargs = self._split_call_args(kwargs)
        if self.signature.takes_context:
            pos = (context, *pos)  # Context is the injected first parameter
        try:
            self._inspect_signature.bind(*pos, **kwargs)
        except TypeError as exc:
            raise InvalidArgument(
                f"'{self.name}' rejected its arguments: {exc}",
                reason="argument_mismatch",
            ) from None
        return pos, kwargs

    def _split_call_args(
        self, kwargs: dict[str, Any]
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        """Re-expand a `*args` tail into positional arguments.

        When the function declares `*args`, every parameter *before* it in
        declaration order must also be passed positionally — otherwise the
        splatted tail would collide with those names (``got multiple
        values for argument``). So: bind the leading params as positionals
        in order, splat the tail array, and leave the rest (keyword-only
        params + any `**kwargs` passthrough) as keyword arguments. With no
        `*args`, everything stays keyword."""
        var_positional = self.signature.input_schema.get(VAR_POSITIONAL_KEY)
        if var_positional is None or var_positional not in kwargs:
            return (), kwargs
        rest = dict(kwargs)
        tail = rest.pop(var_positional)
        if not isinstance(tail, (list, tuple)):
            raise InvalidArgument(
                f"'{self.name}' *{var_positional} must be a JSON array,"
                f" got {type(tail).__name__}",
                reason="argument_mismatch",
            )
        order = self.signature.input_schema.get(PARAMETER_ORDER_KEY, [])
        leading = (
            order[: order.index(var_positional)] if var_positional in order else []
        )
        pos = []
        for name in leading:
            if name in rest:
                pos.append(rest.pop(name))
                continue
            parameter = self._inspect_signature.parameters.get(name)
            if (
                parameter is not None
                and parameter.default is not inspect.Parameter.empty
            ):
                pos.append(parameter.default)
                continue
            raise InvalidArgument(
                f"'{self.name}' missing required positional argument '{name}'"
                f" before *{var_positional}",
                reason="argument_mismatch",
            )
        pos.extend(tail)
        return tuple(pos), rest

    def _bind_kwargs(self, args: dict[str, Any]) -> dict[str, Any]:
        hints = self._hints
        kwargs: dict[str, Any] = {}
        for param, value in args.items():
            try:
                kwargs[param] = (
                    _codec.rehydrate(value, hints[param])
                    if param in hints
                    else self._schema_fallback(param, value)
                )
            except Exception as exc:
                raise InvalidArgument(
                    f"'{self.name}' argument '{param}' does not fit its"
                    f" annotated type: {type(exc).__name__}: {exc}",
                    reason="argument_mismatch",
                ) from None
        return kwargs

    def _schema_fallback(self, param: str, value: Any) -> Any:
        """Schema-override registrations have no annotation to drive
        rehydration; honor the one wire-level encoding schemas declare."""
        prop = self.signature.input_schema.get("properties", {}).get(param, {})
        if prop.get("contentEncoding") == "base64" and isinstance(value, str):
            return base64.b64decode(value)
        return value


class HostServer:
    """Threaded Unix-socket server for :class:`HostedFunction` entries.

    One connection = one host_stream invocation. The daemon owns
    multiplexing; this process only executes the function mapped by the
    incoming request and emits its stream frames.
    """

    def __init__(
        self,
        socket_path: Path,
        *,
        context_dispatcher_factory: Callable[
            [easynet_sdk.RuntimeReceipt | None], ContextChildDispatcher | None
        ]
        | None = None,
    ) -> None:
        self._socket_path = socket_path
        self._functions: dict[str, HostedFunction] = {}
        self._listener: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._context_dispatcher_factory = (
            context_dispatcher_factory or dispatcher_from_parent_receipt
        )

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    def add(self, hosted: HostedFunction) -> None:
        if hosted.name in self._functions:
            raise InvalidArgument(
                f"'{hosted.name}' is already registered on this node",
                reason="duplicate_function",
            )
        self._functions[hosted.name] = hosted

    def remove(self, name: str) -> None:
        self._functions.pop(name, None)

    def start(self) -> None:
        if self._listener is not None:
            return
        # AF_UNIX sun_path is ~104 bytes on macOS / 108 on Linux; a
        # too-long path fails at bind with an unhelpful OSError.
        if len(str(self._socket_path).encode()) > _MAX_UNIX_SOCKET_PATH_BYTES:
            raise InvalidArgument(
                f"host socket path is too long for AF_UNIX: {self._socket_path}"
                " — use a shorter abilities_dir",
                reason="socket_path_too_long",
            )
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._socket_path.parent.chmod(_HOST_DIR_MODE)
        self._socket_path.unlink(missing_ok=True)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self._socket_path))
        self._socket_path.chmod(_HOST_SOCKET_MODE)
        listener.listen()
        self._listener = listener
        self._stopping.clear()
        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="easyremote-host", daemon=True
        )
        self._accept_thread.start()

    def stop(self) -> None:
        if self._listener is None:
            return
        self._stopping.set()
        self._listener.close()
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=5)
        self._listener = None
        self._accept_thread = None
        self._socket_path.unlink(missing_ok=True)

    def __enter__(self) -> HostServer:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    # -- internals ---------------------------------------------------------

    def _accept_loop(self) -> None:
        assert self._listener is not None
        while not self._stopping.is_set():
            try:
                connection, _ = self._listener.accept()
            except OSError:
                return  # listener closed by stop()
            threading.Thread(
                target=self._serve_connection, args=(connection,), daemon=True
            ).start()

    def _serve_connection(self, connection: socket.socket) -> None:
        with connection:
            reader = connection.makefile("r", encoding="utf-8")
            line = reader.readline()
            if not line:
                return
            try:
                session = HostSession.from_envelope(line)
            except InvalidArgument as exc:
                self._send_error(
                    connection,
                    InvalidArgument.KIND,
                    "bad_request",
                    str(exc),
                )
                return
            self._serve_stream(connection, session)

    def _send_frame(self, connection: socket.socket, frame: HostFrame) -> None:
        connection.sendall(
            (dumps_wire(frame.wire, what="host_stream frame") + "\n").encode("utf-8")
        )

    def _send_error(
        self, connection: socket.socket, kind: str, reason: str, message: str
    ) -> None:
        self._send_frame(
            connection,
            HostFrame({"error": {"kind": kind, "reason": reason, "message": message}}),
        )

    def _serve_stream(self, connection: socket.socket, session: HostSession) -> None:
        """Stream a generator ability's frames per the host_stream wire.

        Emits `{"stream_item", "seq"}` per frame with a rolling hash
        folded in `seq` order, then a single `{"terminal"}` carrying the
        final `output_hash` and frame count — or a single `{"error"}` if
        the ability is missing, mis-typed, or raises. terminal and error
        are mutually exclusive and each sent at most once.
        """
        request = session.request
        name = request.function
        args = request.args
        hosted = self._functions.get(name) if isinstance(name, str) else None
        if hosted is None:
            self._send_error(
                connection,
                InvalidArgument.KIND,
                "not_found",
                f"no function '{name}' on this node",
            )
            return
        # The host_stream wire serves EVERY ability: generators stream
        # many frames; a plain unary (or Context-taking unary) function
        # delivers its single return value as one frame. Routing all
        # abilities here keeps one exec path — the shell executor cannot
        # carry arbitrary JSON args or the caller identity.
        sig = hosted.signature
        if not isinstance(args, dict):
            self._send_error(
                connection,
                InvalidArgument.KIND,
                "bad_request",
                "args must be a JSON object",
            )
            return

        # Build the injected Context from the envelope the daemon relays.
        context = None
        if sig.takes_context:
            context = self._context_for_request(request)

        try:
            frames = (
                hosted.stream(args, context=context)
                if sig.is_stream
                else iter([hosted.call(args, context=context)])
            )
            for frame in frames:
                self._send_frame(connection, session.emit(frame))
        except RemoteError as exc:
            self._send_error(connection, exc.kind, exc.reason, str(exc))
            return
        except Exception as exc:
            self._send_error(
                connection,
                InternalError.KIND,
                "function_raised",
                f"{type(exc).__name__}: {exc}",
            )
            return
        finally:
            if context is not None:
                context.close()
        self._send_frame(connection, session.finish())

    def _context_for_request(self, request: HostRequest) -> Context:
        parent = (
            receipt_from_mapping(dict(request.parent_receipt))
            if request.parent_receipt is not None
            else None
        )
        return Context(
            invocation_id=request.call_id,
            caller=request.caller,
            _child_dispatcher=self._context_dispatcher_factory(parent),
        )


def _drain_async_gen(gen: Any) -> Iterator[Any]:
    """Drain an async generator on a private event loop, yielding each
    frame JSON-encoded — identical per-frame contract to the sync path."""
    loop = asyncio.new_event_loop()
    try:
        iterator = gen.__aiter__()
        while True:
            try:
                frame = loop.run_until_complete(iterator.__anext__())
            except StopAsyncIteration:
                break
            yield _codec.to_jsonable(frame)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
