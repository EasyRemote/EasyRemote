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
            summary = easynet_sdk.RuntimeReceipt.from_required_mapping(wire)
        except easynet_sdk.SDKError as exc:
            raise InternalError(
                f"daemon receipt summary is malformed: {exc}",
                reason="receipt_protocol",
            ) from exc
        return cls(
            index=summary.index,
            invocation_id=summary.invocation_id,
            receipt_type=summary.receipt_type,
            state=_state(summary.state),
            timestamp_unix_ms=summary.timestamp_unix_ms,
            prev_receipt_hash=summary.prev_receipt_hash(),
            self_hash=summary.self_receipt_hash(),
            payload_content_type=_optional_text(
                summary.raw.get("payload_content_type")
            ),
            cleanup_complete=bool(summary.cleanup_complete),
            reason=summary.reason,
            child_invocation_id=summary.child_invocation_id,
            raw=summary.to_json_dict(),
        )

    def verify(self, resolver: object | None = None) -> None:
        _ = resolver
        raise Unavailable(
            "cryptographic receipt verification needs the full receipt body, "
            "which the local invocation result does not provide",
            reason="full_receipt_unavailable",
            invocation_id=self.invocation_id,
        )

    def reference(self) -> easynet_sdk.ReceiptReference:
        """Project this summary to an SDK-validated scalar causal reference."""

        try:
            return easynet_sdk.ReceiptReference.from_runtime_receipt(self.raw)
        except easynet_sdk.SDKError as exc:
            raise Unavailable(
                "receipt summary does not include a daemon/Axon causal anchor",
                reason="parent_receipt_anchor_unavailable",
                invocation_id=self.invocation_id,
            ) from exc


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


def _optional_text(value: object) -> str:
    return value if isinstance(value, str) else ""
