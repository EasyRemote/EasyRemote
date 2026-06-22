"""Sessions over libeasynet_cli: transport handles, streams, daemons.

JSON-in/JSON-out only. Frame *interpretation* (which chunk is terminal,
what a receipt means) belongs to the public layers; what belongs here is
thread-safety around the C callback contract: chunks arrive on
library-owned background threads and are handed to consumers through
queues, and callback objects stay referenced until the C side is done
with them.
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from .._json import dumps_wire
from ..config import settings
from ..errors import InternalError, Unavailable
from .abi import Library, RawCallback, library

__all__ = ["BidiChannel", "DaemonProcess", "FrameStream", "Transport"]

_CLOSED = object()  # queue sentinel: no more frames will arrive


class Transport:
    """One connected ``EasynetHandle`` against a daemon's control.json."""

    def __init__(self, lib: Library, handle: int) -> None:
        self._lib = lib
        self._handle = handle
        self._closed = False
        self._lock = threading.Lock()

    @classmethod
    def connect(cls, control_path: str | Path | None = None) -> Transport:
        path = Path(control_path) if control_path else settings().control_path
        if not path.exists():
            raise Unavailable(
                f"no easynet-daemon discovery file at {path} — start the daemon"
                " with `easynet start`",
                reason="daemon_not_running",
            )
        lib = library()
        return cls(lib, lib.init(path))

    def invoke(self, invocation: dict[str, Any]) -> dict[str, Any]:
        """Unary invoke; returns the receipt as a dict."""
        receipt_json = self._lib.invoke(self._require_open(), _dumps(invocation))
        return _loads(receipt_json, what="receipt")

    def stream(self, invocation: dict[str, Any]) -> FrameStream:
        return FrameStream(self, invocation)

    def bidi(self, invocation: dict[str, Any]) -> BidiChannel:
        return BidiChannel(self, invocation)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._lib.shutdown(self._handle)

    def __enter__(self) -> Transport:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _require_open(self) -> int:
        if self._closed:
            raise Unavailable("transport is closed", reason="transport_closed")
        return self._handle


class _FrameQueue:
    """Shared mechanics for callback-fed frame consumers.

    Converts the C callback (background thread, borrowed string) into a
    thread-safe queue of parsed dicts. Exceptions raised while parsing
    are stashed and re-raised on the consumer thread — a callback must
    never unwind across the C ABI (header contract).
    """

    def __init__(self) -> None:
        self._frames: queue.SimpleQueue[Any] = queue.SimpleQueue()
        self._finished = threading.Event()
        # Referenced for the lifetime of this object: the C side may call
        # back until the terminal action (cancel/close) has completed.
        self.callback = RawCallback(self._on_frame)

    def _on_frame(self, _user_data: object, frame_json: bytes | None) -> None:
        try:
            if frame_json is None:
                # End-of-stream marker (C ABI contract: one final
                # callback with a null chunk). Without acting on it a
                # queue consumer blocks forever on the next `recv`.
                self.finish()
                return
            self._frames.put(_loads(frame_json.decode("utf-8"), what="frame"))
        except BaseException as exc:
            self._frames.put(exc)

    def recv(self, timeout: float | None = None) -> dict[str, Any] | None:
        """Next frame, or None once the stream is finished."""
        if self._finished.is_set() and self._frames.empty():
            return None
        try:
            item = self._frames.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError("no frame within timeout") from None
        if item is _CLOSED:
            return None
        if isinstance(item, BaseException):
            raise item
        return cast("dict[str, Any]", item)

    def finish(self) -> None:
        if not self._finished.is_set():
            self._finished.set()
            self._frames.put(_CLOSED)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        while True:
            frame = self.recv()
            if frame is None:
                return
            yield frame


class FrameStream(_FrameQueue):
    """Frames from a server-stream invocation (``InvokeStream``).

    Iteration yields raw frame dicts until :meth:`close` is called.
    Which frame is *semantically* terminal is decided by the caller —
    upon seeing one, call :meth:`close`.
    """

    def __init__(self, transport: Transport, invocation: dict[str, Any]) -> None:
        super().__init__()
        self._transport = transport
        self._stream_id = transport._lib.stream_open(
            transport._require_open(), _dumps(invocation), self.callback
        )

    def close(self) -> None:
        if not self._finished.is_set():
            self._transport._lib.stream_cancel(
                self._transport._require_open(), self._stream_id
            )
            self.finish()

    def __enter__(self) -> FrameStream:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class BidiChannel(_FrameQueue):
    """A bidirectional invocation session (``InvokeBidi``).

    Frame 0 is sent by the daemon on open (header contract); subsequent
    up-frames go through :meth:`send`. ``close()`` is the graceful EOF,
    ``cancel()`` the abort.
    """

    def __init__(self, transport: Transport, invocation: dict[str, Any]) -> None:
        super().__init__()
        self._transport = transport
        self._bidi_id = transport._lib.bidi_open(
            transport._require_open(), _dumps(invocation), self.callback
        )

    def send(self, frame: dict[str, Any]) -> None:
        self._transport._lib.bidi_send(
            self._transport._require_open(), self._bidi_id, _dumps(frame)
        )

    def close(self) -> None:
        if not self._finished.is_set():
            self._transport._lib.bidi_close(
                self._transport._require_open(), self._bidi_id
            )
            self.finish()

    def cancel(self) -> None:
        if not self._finished.is_set():
            self._transport._lib.bidi_cancel(
                self._transport._require_open(), self._bidi_id
            )
            self.finish()

    def __enter__(self) -> BidiChannel:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class DaemonProcess:
    """Lifecycle handle for an easynet-daemon started by this process."""

    def __init__(self, lib: Library, daemon_handle: int) -> None:
        self._lib = lib
        self._handle = daemon_handle
        self._stopped = False
        self._lock = threading.Lock()

    @classmethod
    def start(cls, config: dict[str, Any]) -> DaemonProcess:
        lib = library()
        return cls(lib, lib.daemon_start(_dumps(config)))

    def status(self) -> dict[str, Any]:
        return _loads(self._lib.daemon_status(self._handle), what="daemon status")

    def invocation_endpoint(self) -> str:
        return self._lib.daemon_invocation_endpoint(self._handle)

    def open_client(self) -> Transport:
        return Transport(self._lib, self._lib.daemon_open_client(self._handle))

    def stop(self) -> None:
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
        self._lib.daemon_stop(self._handle)

    def __enter__(self) -> DaemonProcess:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()


def _dumps(payload: dict[str, Any]) -> str:
    return dumps_wire(payload, what="daemon invocation payload")


def _loads(text: str, *, what: str) -> dict[str, Any]:
    try:
        data = json.loads(text) if text else {}
    except json.JSONDecodeError as exc:
        raise InternalError(
            f"daemon sent a {what} that is not valid JSON: {exc}", reason="protocol"
        ) from exc
    if not isinstance(data, dict):
        raise InternalError(
            f"daemon sent a {what} that is not a JSON object", reason="protocol"
        )
    return data
