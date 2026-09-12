"""Provider-side duplex channel over the Runtime-owned resident-host socket."""

from __future__ import annotations

import asyncio
import socket
from threading import Lock
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._host.protocol import HostSession
from .errors import InvalidArgument


class Duplex:
    """Injected provider input/output lane. Iterate until caller half-closes.

    Exactly one receive runs at a time; send and receive may run concurrently.
    Socket backpressure bounds buffering. Returning from the function completes
    the output lane; callers may half-close input and still receive results.
    """

    def __init__(self, connection: socket.socket, session: HostSession):
        self._connection = connection
        self._session = session
        self._read_lock = Lock()
        self._write_lock = Lock()
        self._input_closed = False
        self._sequence = 0

    def recv(self) -> Any:
        from ._host.protocol import FrameKind, decode_item, receive_frame
        with self._read_lock:
            if self._input_closed:
                raise StopIteration
            frame = receive_frame(self._connection)
            if frame.sequence != self._sequence:
                raise InvalidArgument(
                    "duplex input sequence gap", reason="stream_truncated"
                )
            if frame.kind is FrameKind.HALF_CLOSE:
                if frame.payload or frame.content_type:
                    raise InvalidArgument(
                        "invalid duplex half-close", reason="bad_request"
                    )
                self._input_closed = True
                raise StopIteration
            if frame.kind is not FrameKind.ITEM:
                raise InvalidArgument(
                    "expected duplex input item", reason="bad_request"
                )
            self._sequence += 1
            return decode_item(frame)

    def send(self, value: Any) -> None:
        with self._write_lock:
            self._connection.sendall(self._session.emit(value).to_bytes())

    def __iter__(self) -> Duplex:
        return self

    def __next__(self) -> Any:
        return self.recv()

    async def asend(self, value: Any) -> None:
        await asyncio.to_thread(self.send, value)

    async def arecv(self) -> Any:
        def receive() -> tuple[bool, Any]:
            try:
                return True, self.recv()
            except StopIteration:
                return False, None

        available, value = await asyncio.to_thread(receive)
        if not available:
            raise StopAsyncIteration
        return value

    def __aiter__(self) -> Duplex:
        return self

    async def __anext__(self) -> Any:
        return await self.arecv()
