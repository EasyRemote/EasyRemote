"""EasyRemote resident-host binary protocol and terminal state machine."""

from __future__ import annotations

import hashlib
import json
import socket
import struct
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Any

from .. import _codec
from .._json import dumps_wire
from ..errors import InvalidArgument
from ..frame import StreamFrame

MAGIC = b"ERHS"
VERSION = 1
HEADER = struct.Struct("!4sBBHQHI")
MAX_CONTENT_TYPE_BYTES = 1024
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
EMPTY_OUTPUT_DIGEST = hashlib.sha256(b"").digest()


class FrameKind(IntEnum):
    REQUEST = 1
    ITEM = 2
    TERMINAL = 3
    ERROR = 4
    HALF_CLOSE = 5


@dataclass(frozen=True, slots=True)
class HostRequest:
    function: str
    args: Any
    call_id: str
    caller: str
    parent_receipt: dict[str, object] | None = None

    @classmethod
    def from_payload(cls, raw: bytes) -> HostRequest:
        try:
            decoded = json.loads(raw)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _invalid(f"host_stream envelope is not valid JSON: {exc}") from exc
        if not isinstance(decoded, dict) or not isinstance(
            decoded.get("request"), dict
        ):
            raise _invalid("host_stream envelope requires a request object")
        request = decoded["request"]
        for field_name in ("fn", "call_id", "caller"):
            value = request.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise _invalid(f"host_stream request {field_name} is required")
        if "args" not in request:
            raise _invalid("host_stream request args is required")
        parent = request.get("parent_receipt")
        if parent is not None and not isinstance(parent, dict):
            raise _invalid("host_stream parent_receipt must be an object")
        return cls(
            function=request["fn"],
            args=request["args"],
            call_id=request["call_id"],
            caller=request["caller"],
            parent_receipt=dict(parent) if parent is not None else None,
        )


@dataclass(frozen=True, slots=True)
class HostFrame:
    kind: FrameKind
    sequence: int
    content_type: str = ""
    payload: bytes = b""

    def to_bytes(self) -> bytes:
        content_type = self.content_type.encode("utf-8")
        if len(content_type) > MAX_CONTENT_TYPE_BYTES:
            raise _invalid("host stream content type exceeds protocol limit")
        if len(self.payload) > MAX_PAYLOAD_BYTES:
            raise _invalid("host stream payload exceeds protocol limit")
        return b"".join(
            (
                HEADER.pack(
                    MAGIC,
                    VERSION,
                    int(self.kind),
                    0,
                    self.sequence,
                    len(content_type),
                    len(self.payload),
                ),
                content_type,
                self.payload,
            )
        )


class SessionState(Enum):
    OPEN = "open"
    TERMINAL = "terminal"
    CLOSED = "closed"


@dataclass(slots=True)
class HostSession:
    request: HostRequest
    state: SessionState = SessionState.OPEN
    frames: int = 0
    output_digest: bytes = EMPTY_OUTPUT_DIGEST

    @classmethod
    def receive(cls, connection: socket.socket) -> HostSession:
        frame = receive_frame(connection)
        if frame.kind is not FrameKind.REQUEST:
            raise _invalid("first host_stream frame must be a request")
        if frame.sequence != 0 or frame.content_type != "application/json":
            raise _invalid(
                "host_stream request requires sequence 0 and application/json"
            )
        return cls(HostRequest.from_payload(frame.payload))

    def emit(self, value: object) -> HostFrame:
        self._require_open()
        content_type, payload = encode_value(value)
        sequence = self.frames
        self.output_digest = fold_output_digest(
            self.output_digest,
            sequence,
            content_type,
            payload,
        )
        self.frames += 1
        return HostFrame(FrameKind.ITEM, sequence, content_type, payload)

    def finish(self) -> HostFrame:
        self._require_open()
        self.state = SessionState.TERMINAL
        return HostFrame(FrameKind.TERMINAL, self.frames, payload=self.output_digest)

    def fail(self, kind: str, reason: str, message: str) -> HostFrame:
        self._require_open()
        self.state = SessionState.TERMINAL
        return error_frame(kind, reason, message, sequence=self.frames)

    def close(self) -> None:
        self.state = SessionState.CLOSED

    def _require_open(self) -> None:
        if self.state is not SessionState.OPEN:
            raise _invalid("host stream session is terminal")


def receive_frame(connection: socket.socket) -> HostFrame:
    raw_header = _receive_exact(connection, HEADER.size)
    magic, version, raw_kind, flags, sequence, content_len, payload_len = (
        HEADER.unpack(raw_header)
    )
    if magic != MAGIC:
        raise _invalid("host stream frame has invalid magic")
    if version != VERSION:
        raise _invalid(f"unsupported host stream protocol version {version}")
    if flags != 0:
        raise _invalid(f"host stream frame has unsupported flags {flags:#06x}")
    try:
        kind = FrameKind(raw_kind)
    except ValueError as exc:
        raise _invalid(f"host stream frame has unsupported kind {raw_kind}") from exc
    if content_len > MAX_CONTENT_TYPE_BYTES:
        raise _invalid("host stream content type exceeds protocol limit")
    if payload_len > MAX_PAYLOAD_BYTES:
        raise _invalid("host stream payload exceeds protocol limit")
    try:
        content_type = _receive_exact(connection, content_len).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _invalid("host stream content type is not UTF-8") from exc
    payload = _receive_exact(connection, payload_len)
    return HostFrame(kind, sequence, content_type, payload)


def encode_value(value: object) -> tuple[str, bytes]:
    if isinstance(value, StreamFrame):
        return value.content_type, value.payload
    if isinstance(value, bytes):
        return "application/octet-stream", value
    if isinstance(value, (bytearray, memoryview)):
        return "application/octet-stream", bytes(value)
    jsonable = _codec.to_jsonable(value)
    payload = dumps_wire(jsonable, what="host_stream JSON frame").encode("utf-8")
    return "application/json", payload


def request_frame(envelope: object) -> HostFrame:
    payload = dumps_wire(envelope, what="host_stream request").encode("utf-8")
    return HostFrame(
        FrameKind.REQUEST,
        0,
        content_type="application/json",
        payload=payload,
    )


def decode_item(frame: HostFrame) -> object:
    if frame.kind is not FrameKind.ITEM:
        raise _invalid("only an item frame has an ability value")
    if frame.content_type == "application/json":
        try:
            return json.loads(frame.payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _invalid(f"host stream JSON item is invalid: {exc}") from exc
    return StreamFrame(frame.payload, frame.content_type)


def error_frame(
    kind: str,
    reason: str,
    message: str,
    *,
    sequence: int = 0,
) -> HostFrame:
    payload = dumps_wire(
        {"kind": kind, "reason": reason, "message": message},
        what="host_stream error",
    ).encode("utf-8")
    return HostFrame(
        FrameKind.ERROR,
        sequence,
        content_type="application/json",
        payload=payload,
    )


def fold_output_digest(
    previous: bytes,
    sequence: int,
    content_type: str,
    payload: bytes,
) -> bytes:
    if len(previous) != 32:
        raise _invalid("host stream previous digest must be 32 bytes")
    if sequence < 0:
        raise _invalid("host stream sequence must be non-negative")
    content_type_bytes = content_type.encode("utf-8")
    if not content_type_bytes or len(content_type_bytes) > MAX_CONTENT_TYPE_BYTES:
        raise _invalid("host stream item content type is invalid")
    hasher = hashlib.sha256()
    hasher.update(previous)
    hasher.update(sequence.to_bytes(8, "big"))
    hasher.update(len(content_type_bytes).to_bytes(2, "big"))
    hasher.update(content_type_bytes)
    hasher.update(payload)
    return hasher.digest()


@dataclass(slots=True)
class FrameWriter:
    """Protocol hash helper used by cross-language contract tests."""

    frames: int = 0
    output_digest: bytes = EMPTY_OUTPUT_DIGEST

    @property
    def output_hash(self) -> str:
        return "sha256:" + self.output_digest.hex()

    def write_item(self, value: object) -> HostFrame:
        content_type, payload = encode_value(value)
        frame = HostFrame(
            FrameKind.ITEM,
            self.frames,
            content_type=content_type,
            payload=payload,
        )
        self.output_digest = fold_output_digest(
            self.output_digest,
            self.frames,
            content_type,
            payload,
        )
        self.frames += 1
        return frame


def _receive_exact(connection: socket.socket, length: int) -> bytes:
    data = bytearray(length)
    view = memoryview(data)
    received = 0
    while received < length:
        count = connection.recv_into(view[received:])
        if count == 0:
            raise _invalid("host stream closed before a complete frame arrived")
        received += count
    return bytes(data)


def _invalid(
    message: str, *, reason: str = "invalid_host_stream"
) -> InvalidArgument:
    return InvalidArgument(message, reason=reason)
