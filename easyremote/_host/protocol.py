"""EasyRemote-owned host-stream line protocol and rolling-hash state machine."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..errors import InvalidArgument, RemoteError

EMPTY_OUTPUT_HASH = (
    "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)


@dataclass(frozen=True)
class HostRequest:
    function: str
    args: Any
    call_id: str
    caller: str
    parent_receipt: dict[str, object] | None = None

    @classmethod
    def from_envelope(cls, raw: str) -> "HostRequest":
        try:
            decoded = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise _invalid(f"host_stream envelope is not valid JSON: {exc}") from exc
        if not isinstance(decoded, dict) or not isinstance(decoded.get("request"), dict):
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


@dataclass(frozen=True)
class HostFrame:
    wire: dict[str, object]


class SessionState(Enum):
    OPEN = "open"
    TERMINAL = "terminal"
    CLOSED = "closed"


@dataclass
class HostSession:
    request: HostRequest
    state: SessionState = SessionState.OPEN
    frames: int = 0
    output_hash: str = EMPTY_OUTPUT_HASH

    @classmethod
    def from_envelope(cls, raw: str) -> "HostSession":
        return cls(HostRequest.from_envelope(raw))

    def emit(self, value: object) -> HostFrame:
        self._require_open()
        seq = self.frames
        self.output_hash = fold_output_hash(self.output_hash, seq, value)
        self.frames += 1
        return HostFrame({"stream_item": value, "seq": seq})

    def finish(self) -> HostFrame:
        self._require_open()
        self.state = SessionState.TERMINAL
        return HostFrame(
            {"terminal": {"output_hash": self.output_hash, "frames": self.frames}}
        )

    def fail(self, error: BaseException) -> HostFrame:
        self._require_open()
        self.state = SessionState.TERMINAL
        kind = getattr(error, "kind", None) or "INTERNAL"
        reason = getattr(error, "reason", None) or "host_execution_failed"
        return HostFrame(
            {"error": {"kind": str(kind), "reason": str(reason), "message": str(error)}}
        )

    def close(self) -> None:
        self.state = SessionState.CLOSED

    def _require_open(self) -> None:
        if self.state is not SessionState.OPEN:
            raise _invalid("host stream session is terminal")


@dataclass
class FrameWriter:
    frames: int = 0
    output_hash: str = EMPTY_OUTPUT_HASH
    _terminal: bool = field(default=False, init=False, repr=False)

    def write_item(self, value: object) -> HostFrame:
        if self._terminal:
            raise _invalid("host stream writer is terminal")
        frame = HostFrame({"stream_item": value, "seq": self.frames})
        self.output_hash = fold_output_hash(self.output_hash, self.frames, value)
        self.frames += 1
        return frame

    def finish(self) -> HostFrame:
        if self._terminal:
            raise _invalid("host stream writer is terminal")
        self._terminal = True
        return HostFrame(
            {"terminal": {"output_hash": self.output_hash, "frames": self.frames}}
        )


def fold_output_hash(previous: str, seq: int, value: object) -> str:
    if seq < 0:
        raise _invalid("host stream sequence must be non-negative")
    if not previous.startswith("sha256:"):
        raise _invalid("host stream hash must be sha256-prefixed")
    digest = previous.removeprefix("sha256:")
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise _invalid("host stream hash must contain 64 lowercase hex digits")
    try:
        canonical = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise _invalid(
            f"host stream frame is not valid JSON: {exc}",
            reason="invalid_json_payload",
        ) from exc
    hasher = hashlib.sha256()
    hasher.update(bytes.fromhex(digest))
    hasher.update(seq.to_bytes(8, "big"))
    hasher.update(canonical)
    return "sha256:" + hasher.hexdigest()


def _invalid(
    message: str, *, reason: str = "invalid_host_stream"
) -> InvalidArgument:
    return InvalidArgument(message, reason=reason)
