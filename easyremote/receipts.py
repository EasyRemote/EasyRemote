"""EasyRemote receipt presentation over opaque generic runtime receipt facts."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeAlias

import easynet_sdk

from .errors import InternalError, Unavailable

__all__ = ["InvocationState", "Receipt", "ReceiptChain"]

InvocationState: TypeAlias = easynet_sdk.InvocationLifecycleState

_STATE_NAMES = {
    "unspecified": InvocationState.UNSPECIFIED,
    "accepted": InvocationState.ACCEPTED,
    "admitted": InvocationState.ADMITTED,
    "dispatched": InvocationState.DISPATCHED,
    "running": InvocationState.RUNNING,
    "completed": InvocationState.COMPLETED,
    "failed": InvocationState.FAILED,
    "timed_out": InvocationState.TIMED_OUT,
    "cancelled": InvocationState.CANCELLED,
}


@dataclass(frozen=True)
class Receipt:
    """Product-facing projection of one daemon terminal receipt summary."""

    index: int
    invocation_id: str
    receipt_type: str
    state: InvocationState
    timestamp_unix_ms: int
    prev_receipt_hash: bytes
    self_hash: bytes
    payload_content_type: str
    cleanup_complete: bool
    reason: str
    child_invocation_id: str
    raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_wire(cls, wire: dict[str, Any]) -> "Receipt":
        try:
            index = _integer(wire["index"])
            timestamp = _integer(wire["timestamp_unix_ms"])
            invocation_id = _required_text(wire["invocation_id"], "invocation_id")
            receipt_type = _required_text(wire["receipt_type"], "receipt_type")
            previous = bytes.fromhex(str(wire["prev_receipt_hash_hex"]))
            current = bytes.fromhex(str(wire["self_hash_hex"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise InternalError(
                f"daemon receipt summary is malformed: {exc}",
                reason="receipt_protocol",
            ) from exc
        if len(previous) != 32 or len(current) != 32:
            raise InternalError(
                "daemon receipt hashes must be 32 bytes",
                reason="receipt_protocol",
            )
        return cls(
            index=index,
            invocation_id=invocation_id,
            receipt_type=receipt_type,
            state=_state(wire.get("state")),
            timestamp_unix_ms=timestamp,
            prev_receipt_hash=previous,
            self_hash=current,
            payload_content_type=str(wire.get("payload_content_type", "")),
            cleanup_complete=bool(wire.get("cleanup_complete", False)),
            reason=str(wire.get("reason", "")),
            child_invocation_id=str(wire.get("child_invocation_id", "")),
            raw=dict(wire),
        )

    def verify(self, resolver: object | None = None) -> None:
        _ = resolver
        raise Unavailable(
            "cryptographic receipt verification needs the full receipt body, "
            "which the local invocation result does not provide",
            reason="full_receipt_unavailable",
            invocation_id=self.invocation_id,
        )


class ReceiptChain(Sequence[Receipt]):
    """Ordered product receipt summaries with explicit hash-link validation."""

    def __init__(self, receipts: Sequence[Receipt]) -> None:
        self._receipts = tuple(receipts)

    def __len__(self) -> int:
        return len(self._receipts)

    def __getitem__(self, index: int) -> Receipt:  # type: ignore[override]
        return self._receipts[index]

    def __iter__(self) -> Iterator[Receipt]:
        return iter(self._receipts)

    def verify_continuity(self) -> None:
        for position, (previous, current) in enumerate(
            zip(self._receipts, self._receipts[1:], strict=False), start=1
        ):
            if current.prev_receipt_hash != previous.self_hash:
                raise InternalError(
                    f"receipt chain broken at index {position}: "
                    "prev_receipt_hash does not match predecessor self_hash",
                    reason="receipt_chain_broken",
                    invocation_id=current.invocation_id,
                )


def _state(value: object) -> InvocationState:
    if isinstance(value, str):
        named = _STATE_NAMES.get(value.strip().lower())
        if named is not None:
            return named
    try:
        return InvocationState(int(value))
    except (TypeError, ValueError):
        return InvocationState.UNSPECIFIED


def _integer(value: object) -> int:
    if isinstance(value, bool):
        raise TypeError("boolean is not an integer")
    return int(value)  # type: ignore[arg-type]


def _required_text(value: object, field_name: str) -> str:
    text = str(value)
    if not text:
        raise ValueError(f"{field_name} is required")
    return text
