"""The warm host: a Unix-socket server keeping registered functions resident.

Wire protocol (one JSON line each way, UTF-8):

    → {"fn": "<name>", "values": ["<rendered argv value>", ...]}
    ← {"ok": true, "result": <json>}
    ← {"ok": false, "error": {"kind": "...", "reason": "...", "message": "..."}}

``values`` arrive exactly as the daemon's shell executor rendered them
(``template.rs`` model: strings bare, everything else JSON-encoded),
positionally matching the function's parameter order. Re-typing uses
the registered function's derived schema — the host is the only place
that knows it.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import InternalError, InvalidArgument, RemoteError
from ..schema import PARAMETER_ORDER_KEY, DerivedSignature

__all__ = ["HostServer", "HostedFunction"]


@dataclass(frozen=True)
class HostedFunction:
    """One resident function plus the schema that types its wire values."""

    name: str
    fn: Callable[..., Any]
    signature: DerivedSignature

    def call_with_rendered(self, values: list[str]) -> Any:
        order: list[str] = self.signature.input_schema[PARAMETER_ORDER_KEY]
        if len(values) != len(order):
            raise InvalidArgument(
                f"'{self.name}' expects {len(order)} values, got {len(values)}",
                reason="arity_mismatch",
            )
        properties = self.signature.input_schema["properties"]
        kwargs = {
            param: _decode_rendered(value, properties.get(param, {}))
            for param, value in zip(order, values, strict=True)
        }
        result = self.fn(**kwargs)
        if inspect.iscoroutine(result):
            return asyncio.run(result)
        return result


def _decode_rendered(value: str, prop_schema: dict[str, Any]) -> Any:
    """Invert the shell executor's rendering using the parameter schema.

    template.rs renders strings bare and everything else as JSON text;
    the schema decides which way to read each value back.
    """
    if prop_schema.get("contentEncoding") == "base64":
        return base64.b64decode(value)
    if prop_schema.get("type") == "string":
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        # Permissive ({}) or anyOf schemas may legitimately carry bare
        # strings — the only non-JSON rendering the executor produces.
        return value


class HostServer:
    """Threaded Unix-socket server for :class:`HostedFunction` entries.

    One connection = one request/response = one forwarder process —
    matching the daemon's invocation granularity, so no in-connection
    multiplexing is needed.
    """

    def __init__(self, socket_path: Path) -> None:
        self._socket_path = socket_path
        self._functions: dict[str, HostedFunction] = {}
        self._listener: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._stopping = threading.Event()

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

    def start(self) -> None:
        if self._listener is not None:
            return
        # AF_UNIX sun_path is ~104 bytes on macOS / 108 on Linux; a
        # too-long path fails at bind with an unhelpful OSError.
        if len(str(self._socket_path).encode()) > 100:
            raise InvalidArgument(
                f"host socket path is too long for AF_UNIX: {self._socket_path}"
                " — use a shorter agents_root",
                reason="socket_path_too_long",
            )
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._socket_path.unlink(missing_ok=True)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self._socket_path))
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
            response = self._handle(line)
            connection.sendall(
                (json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8")
            )

    def _handle(self, line: str) -> dict[str, Any]:
        try:
            request = json.loads(line)
            name = request["fn"]
            values = request["values"]
            hosted = self._functions.get(name)
            if hosted is None:
                raise InvalidArgument(
                    f"no function '{name}' on this node", reason="not_found"
                )
            return {"ok": True, "result": hosted.call_with_rendered(values)}
        except RemoteError as exc:
            return _error_response(exc.kind, exc.reason, str(exc))
        except (KeyError, json.JSONDecodeError, TypeError) as exc:
            return _error_response(
                InvalidArgument.KIND, "bad_request", f"{type(exc).__name__}: {exc}"
            )
        except Exception as exc:
            return _error_response(
                InternalError.KIND, "function_raised", f"{type(exc).__name__}: {exc}"
            )


def _error_response(kind: str, reason: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"kind": kind, "reason": reason, "message": message}}
